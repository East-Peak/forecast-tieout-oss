"""The capacity term of the forward function.

Pipeline not yet created is ``created deals per ramped AE-month`` times the
ramped AE-months a roster is expected to supply on each future day. The rate
is fitted from the trailing year before the cutoff; the roster is the one
known at the cutoff, plus signed hires and any planned hires. Everything else
(deal size, conversion, close timing) is Goal 1's, unchanged. Whether this
beats the flat trailing rate is decided by ``adoption``; when it does not, the
forward function keeps the flat rate.

Forward attrition is an expectation in ``per_day`` (a constant daily hazard)
and a geometric draw per departure in ``draws``, which are centred on it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from . import capacity_rules as rules
from .capacity_config import CapacityConfig
from .forecast import Creation
from .ramp import Attrition, RampFit, fit_attrition, fit_ramp
from .roster import Member, RampCurve, ramped_ae_months, roster_at, segments

ZERO = Decimal(0)


@dataclass(frozen=True)
class CapacityFit:
    cutoff: date
    ramp: RampFit
    attrition: Attrition
    rate: Decimal  # created deals per ramped AE-month
    trailing_deals: int
    trailing_ramped_months: Decimal
    unavailable: str = ""

    @property
    def curve(self) -> RampCurve:
        return self.ramp.curve


def fit_capacity(
    deals, members, cutoff: date, since: date, cfg: CapacityConfig
) -> CapacityFit:
    """Everything capacity needs, from what was known on ``cutoff``: ``deals``
    created after it and departures or hires after it are ignored."""
    known = [d for d in deals if d.created <= cutoff]
    view = roster_at(members, cutoff)
    ramp = fit_ramp(known, view, cutoff, cfg.ramp)
    attrition = fit_attrition(view, cutoff, since, cfg.attrition)
    start = cutoff - timedelta(days=rules.TRAILING_DAYS)
    count = sum(1 for d in known if d.created > start)
    months = ramped_ae_months(view, ramp.curve, start, cutoff)
    why = "" if months else "no ramped AE-months in the trailing year: nobody employed"
    rate = Decimal(count) / months if months else ZERO
    return CapacityFit(cutoff, ramp, attrition, rate, count, months, why)


def daily_survival(monthly_attrition: Decimal) -> Decimal:
    """Chance of still being employed one day later, from a monthly rate."""
    return ((1 - monthly_attrition).ln() / rules.DAYS_PER_AE_MONTH).exp()


def project(
    fit: CapacityFit, members: Sequence[Member], as_of: date, horizon_days: int
) -> Creation:
    """Expected deals created on each of the ``horizon_days`` days after
    ``as_of`` by ``members`` (the signed roster and any planned hires)."""
    s = daily_survival(fit.attrition.rate)
    power = [Decimal(1)]
    for _ in range(horizon_days):
        power.append(power[-1] * s)
    first, last = as_of + timedelta(days=1), as_of + timedelta(days=horizon_days)
    expected = [ZERO] * horizon_days
    heads = [ZERO] * horizon_days
    leaving = [ZERO] * horizon_days
    static = np.zeros(horizon_days)  # reps whose end is known, or who never leave
    at_risk = []  # (weights, first offset, hazard clock starts at this offset)
    for m in members:
        origin = max(0, (m.start - as_of).days)  # a hire's first day is certain
        weights = [ZERO] * horizon_days
        for lo, hi, w in segments(m, fit.curve, first, last):
            for i in range((lo - first).days, (hi - first).days + 1):
                weights[i] = w
        lo, hi = max(first, m.start), last if m.end is None else min(last, m.end)
        if m.end is not None:
            for i, w in enumerate(weights):
                expected[i] += w
            for i in range((lo - first).days, (hi - first).days + 1):
                heads[i] += 1
            if first <= m.end <= last:
                leaving[(m.end - first).days] += 1
            static += np.array([float(w) for w in weights])
        else:
            for i, w in enumerate(weights):
                expected[i] += w * power[i + 1 - origin]
            for i in range((lo - first).days, (hi - first).days + 1):
                heads[i] += power[i + 1 - origin]
                if (
                    i + 1 > origin
                ):  # leaves during this day, having been there at its start
                    leaving[i] += power[i - origin] * (1 - s)
            at_risk.append((np.array([float(w) for w in weights]), origin))
    per_month = rules.DAYS_PER_AE_MONTH
    ramped = tuple(x / per_month for x in expected)
    per_day = tuple(fit.rate * x for x in ramped)
    rate = float(fit.rate)
    log_s = math.log(float(s)) if s < 1 else 0.0

    def draws(rng: np.random.Generator, n: int) -> np.ndarray:
        ramped_draws = np.tile(static, (n, 1))
        offsets = np.arange(1, horizon_days + 1)
        for weights, origin in at_risk:
            if log_s:  # the last day (offset) a rep is still employed
                gone_after = np.floor(np.log(1 - rng.random(n)) / log_s)
            else:
                gone_after = np.full(n, np.inf)
            alive = (offsets[None, :] - origin) <= gone_after[:, None]
            ramped_draws += alive * weights[None, :]
        return ramped_draws / float(per_month) * rate

    text = (
        f"new pipeline is created at {fit.rate:.4f} deals per ramped AE-month (trailing "
        f"{rules.TRAILING_DAYS} days) times the expected ramped AE-months of the roster"
    )
    return Creation(per_day, text, ramped, tuple(heads), tuple(leaving), draws)

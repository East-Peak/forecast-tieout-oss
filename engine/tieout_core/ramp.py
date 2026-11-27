"""Fit a ramp curve and an attrition rate from the company's own history.

Ramp: created deals per rep by tenure month, relative to reps with twelve or
more months' tenure in the same calendar month, so company growth is not
mistaken for ramp. Fitted only with enough reps observed from hire and enough
tenured reps; otherwise the entered curve (or the default) is used and the
curve says so. Attrition: departures over AE-months; with too few departures
the entered rate (or the default) is used.

Both fits take the whole history and a cutoff and use only what was known on
that date: deals created by the cutoff, and ``roster_at(cutoff)``.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from . import capacity_rules as rules
from .fiscal import add_months, month_end
from .rates import DEFAULT, ENTERED, FITTED
from .roster import RampCurve, employed, roster_at, tenure_month

Z95 = 1.959964
TENURED = "tenured"


@dataclass(frozen=True)
class RampFit:
    curve: RampCurve
    reps_observed: int  # reps observed from hire through their sixth month
    tenured_reps: int  # reps with twelve or more months' tenure in the months used
    reason: str = ""  # why the curve is not fitted; empty when it is
    deals_left_out: int = (
        0  # created after their owner's last day (or before their start)
    )
    left_out_reason: str = ""
    tail: str = ""  # where the fitted months end and what stands in for the rest


def fit_ramp(deals, members, cutoff: date, entered=None) -> RampFit:
    deals = [d for d in deals if d.created <= cutoff]
    members = roster_at(members, cutoff)
    first = min((d.created for d in deals), default=None)
    observed = tenured = left_out = 0
    if first is not None:
        exposure, made, left_out = _by_month(deals, members, first, cutoff)
        tenured = len(_tenured_ids(exposure))
        observed = _observed_from_hire(members, exposure, first, cutoff)
    problems = []
    if observed < rules.RAMP_MIN_REPS:
        problems.append(
            f"{observed} reps observed from hire through their sixth month; "
            f"{rules.RAMP_MIN_REPS} are needed"
        )
    if tenured < rules.RAMP_MIN_TENURED:
        problems.append(
            f"{tenured} tenured reps (twelve or more months) alongside; "
            f"{rules.RAMP_MIN_TENURED} are needed"
        )
    why = _left_out_reason(left_out)
    if problems:
        return RampFit(
            _fallback(entered, observed), observed, tenured, "; ".join(problems),
            left_out, why,
        )  # fmt: skip
    curve, tail = _fit_curve(exposure, made, observed, entered)
    return RampFit(curve, observed, tenured, "", left_out, why, tail)


def _left_out_reason(n: int) -> str:
    if not n:
        return ""
    return (
        f"{n} deals were left out of the ramp fit: they were created when their owner was not "
        "employed (before their start or after their last day), so they cannot say how fast a "
        "rep at that tenure creates"
    )


def _observed_from_hire(members, exposure, first: date, cutoff: date) -> int:
    """Reps seen from hire through their sixth month: started on or after the
    first deal, employed through that month's end, with tenured reps present in
    every month used that the six months touch."""
    tenured_months = {
        ms for (ms, cls, _), days in exposure.items() if cls == TENURED and days
    }
    count = 0
    for m in members:
        sixth = add_months(m.start, rules.RAMP_ELIGIBLE_MONTHS) - timedelta(days=1)
        if m.start < first or sixth > cutoff or (m.end is not None and m.end < sixth):
            continue
        touched = {ms for (ms, _, who) in exposure if who == m.id and ms <= sixth}
        if touched and touched <= tenured_months:
            count += 1
    return count


def _fallback(entered, observed: int) -> RampCurve:
    if entered:
        return RampCurve(tuple(entered), ENTERED, observed)
    return RampCurve(rules.DEFAULT_RAMP, DEFAULT, observed)


def _tenured_ids(exposure) -> set:
    """Tenured reps present in a month in which someone was still ramping."""
    ramping = {ms for (ms, cls, _), days in exposure.items() if cls != TENURED and days}
    return {
        who
        for (ms, cls, who), days in exposure.items()
        if cls == TENURED and days and ms in ramping
    }


def _months(first: date, cutoff: date) -> list[tuple[date, date]]:
    """Whole calendar months inside [first, cutoff]."""
    out = []
    start = first if first.day == 1 else month_end(first) + timedelta(days=1)
    while month_end(start) <= cutoff:
        out.append((start, month_end(start)))
        start = month_end(start) + timedelta(days=1)
    return out


def _by_month(deals, members, first: date, cutoff: date):
    """Exposure in rep-days and deals made, per (month, class, rep) where class
    is a tenure month 1..11 or TENURED. Months 12 is neither and is left out."""
    months = _months(first, cutoff)
    exposure: dict[tuple, int] = defaultdict(int)
    for m in members:
        bounds = [add_months(m.start, k) for k in range(rules.TENURED_AFTER_MONTHS + 1)]
        end = m.end or cutoff
        for ms, me in months:
            lo, hi = max(ms, m.start), min(me, end, cutoff)
            if lo > hi:
                continue
            for k in range(1, rules.TENURED_AFTER_MONTHS):
                a, b = max(lo, bounds[k - 1]), min(hi, bounds[k] - timedelta(days=1))
                if a <= b:
                    exposure[(ms, k, m.id)] += (b - a).days + 1
            a = max(lo, bounds[-1])
            if a <= hi:
                exposure[(ms, TENURED, m.id)] += (hi - a).days + 1
    by_id = {m.id: m for m in members}
    month_of = {ms: (ms, me) for ms, me in months}
    made: dict[tuple, int] = defaultdict(int)
    left_out = 0
    for d in deals:
        m = by_id.get(d.owner_id)
        if m is None:
            continue
        ms = date(d.created.year, d.created.month, 1)
        if ms not in month_of:
            continue
        if not employed(m, d.created):
            left_out += 1
            continue
        k = tenure_month(m, d.created)
        if 1 <= k < rules.TENURED_AFTER_MONTHS:
            made[(ms, k)] += 1
        elif k > rules.TENURED_AFTER_MONTHS:
            made[(ms, TENURED)] += 1
    return exposure, made, left_out


def _fit_curve(exposure, made, observed: int, entered=None):
    rep_days: dict[tuple, int] = defaultdict(int)
    for (ms, cls, _), days in exposure.items():
        rep_days[(ms, cls)] += days
    months = sorted({ms for ms, _ in rep_days})
    weights, ranges = [], []
    for k in range(1, rules.TENURED_AFTER_MONTHS):
        expected = Fraction(
            0
        )  # deals the reps in tenure month k would have made as tenured reps
        variance = Fraction(0)  # of that, from the reference rate's own noise
        got = 0
        for ms in months:
            x_ten, t_ten, x_k = (
                rep_days[(ms, TENURED)],
                made[(ms, TENURED)],
                rep_days[(ms, k)],
            )
            if not x_ten or not x_k:
                continue
            expected += Fraction(x_k * t_ten, x_ten)
            variance += Fraction(x_k * x_k * t_ten, x_ten * x_ten)
            got += made[(ms, k)]
        if not expected:
            break  # no evidence from here on
        w = Fraction(got) / expected
        point = min(w, Fraction(1))
        if got:
            sd = math.sqrt(1 / got + float(variance / (expected * expected)))
            low, high = float(w) * math.exp(-Z95 * sd), float(w) * math.exp(Z95 * sd)
        else:
            low, high = 0.0, float(3 / expected)
        weights.append(Decimal(point.numerator) / Decimal(point.denominator))
        ranges.append((max(0.0, min(low, 1.0)), min(1.0, high)))
    fitted = len(weights)
    tail = ""
    if fitted < rules.TENURED_AFTER_MONTHS - 1:
        stand_in = tuple(entered or ())[fitted : rules.TENURED_AFTER_MONTHS - 1]
        weights += list(stand_in)
        tail = (
            f"fitted for tenure months 1 to {fitted}; no rep was observed longer, so "
            + (
                f"months {fitted + 1} to {fitted + len(stand_in)} use the entered weights and "
                "later months are taken as fully ramped"
                if stand_in
                else f"months from {fitted + 1} are taken as fully ramped"
            )
        )
    return RampCurve(tuple(weights), FITTED, observed, tuple(ranges)), tail


# ---------------------------------------------------------------- attrition


@dataclass(frozen=True)
class Attrition:
    rate: Decimal  # departures per AE-month
    source: str
    departures: int
    ae_months: Decimal
    low95: float | None = None
    high95: float | None = None
    reason: str = ""


def fit_attrition(members, cutoff: date, since: date, entered=None) -> Attrition:
    """Departures dated within [since, cutoff] over AE-months employed in it."""
    members = roster_at(members, cutoff)
    departures = sum(
        1 for m in members if m.end is not None and since <= m.end <= cutoff
    )
    days = 0
    for m in members:
        lo, hi = max(m.start, since), min(m.end or cutoff, cutoff)
        if lo <= hi:
            days += (hi - lo).days + 1
    ae_months = Decimal(days) / rules.DAYS_PER_AE_MONTH
    if departures >= rules.MIN_DEPARTURES and ae_months:
        low, high = _poisson_interval(departures)
        rate = Decimal(departures) / ae_months
        return Attrition(rate, FITTED, departures, ae_months,
                         low / float(ae_months), high / float(ae_months))  # fmt: skip
    why = f"{departures} departures; {rules.MIN_DEPARTURES} are needed to fit a rate"
    if entered is not None:
        return Attrition(Decimal(entered), ENTERED, departures, ae_months, reason=why)
    return Attrition(
        rules.DEFAULT_MONTHLY_ATTRITION, DEFAULT, departures, ae_months, reason=why
    )


def _poisson_interval(count: int, z: float = Z95) -> tuple[float, float]:
    """Approximate 95% interval for a Poisson mean from one count (Wilson-Hilferty)."""
    low = count * (1 - 1 / (9 * count) - z / (3 * math.sqrt(count))) ** 3
    n = count + 1
    high = n * (1 - 1 / (9 * n) + z / (3 * math.sqrt(n))) ** 3
    return max(0.0, low), high

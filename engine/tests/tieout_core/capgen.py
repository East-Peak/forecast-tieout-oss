"""A test-only generator of reps and the deals they create, with a known ramp
and attrition. Its mechanics differ from the fit's: a rep's creation rate
climbs linearly by the day over the ramp, departures are a daily coin flip,
and deals are Poisson per rep per day; the fit counts deals and exposure by
tenure month and never sees these parameters."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from engine.tieout_core.capacity_rules import DAYS_PER_AE_MONTH
from engine.tieout_core.records import Deal
from engine.tieout_core.roster import Member

MONTH = float(DAYS_PER_AE_MONTH)


@dataclass(frozen=True)
class World:
    members: tuple[Member, ...]
    deals: tuple[Deal, ...]
    history_start: date
    cutoff: date
    true_ramp: tuple[float, ...]  # tenure months 1..11
    true_attrition: float  # departures per AE-month


def true_ramp(ramp_months: int, fitted_months: int = 11) -> tuple[float, ...]:
    """The linear-by-the-day ramp averaged over an average month."""
    return tuple(min(1.0, (k - 0.5) / ramp_months) for k in range(1, fitted_months + 1))


def make_world(
    seed: int,
    *,
    tenured: int = 8,
    hires: int = 40,
    deals_per_month: float = 8.0,
    ramp_months: int = 6,
    monthly_attrition: float = 0.0,
    start: date = date(2023, 1, 1),
    months: int = 36,
    hire_window_months: int = 18,
) -> World:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    cutoff = start + timedelta(days=round(months * MONTH)) - timedelta(days=1)
    n_days = (cutoff - start).days + 1
    q = monthly_attrition / MONTH  # daily chance of leaving
    members = []
    for i in range(tenured + hires):
        if i < tenured:
            begin = start - timedelta(days=rng.randint(800, 1500))
        else:
            begin = start + timedelta(
                days=rng.randint(0, round(hire_window_months * MONTH))
            )
        end = None
        if q:  # a geometric lifetime: a daily coin flip
            last = begin + timedelta(
                days=int(math.log(1 - rng.random()) / math.log(1 - q))
            )
            end = last if last <= cutoff else None
        members.append(Member(f"R{i:03d}", "ae", "mm", begin, end, Decimal(1_000_000)))
    days = np.arange(n_days)
    deals = []
    counter = 0
    for m in members:
        since = (days + (start - m.start).days) + 1
        alive = since >= 1
        if m.end is not None:
            alive &= days <= (m.end - start).days
        weight = np.minimum(1.0, since / (ramp_months * MONTH))
        counts = np_rng.poisson(np.where(alive, deals_per_month / MONTH * weight, 0.0))
        for d in np.nonzero(counts)[0]:
            for _ in range(int(counts[d])):
                counter += 1
                deals.append(
                    Deal(0, f"D{counter:06d}", "new_business", m.segment, "S1",
                         Decimal(100), start + timedelta(days=int(d)), None, False, False,
                         m.id)
                )  # fmt: skip
    deals.sort(key=lambda d: (d.created, d.id))
    return World(
        tuple(members),
        tuple(deals),
        start,
        cutoff,
        true_ramp(ramp_months),
        monthly_attrition,
    )

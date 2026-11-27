"""People and their ramped capacity.

A rep's capacity on a day is their ramp weight for that day's tenure month
(1 once the curve ends). An AE-month is ``DAYS_PER_AE_MONTH`` days, so ramped
AE-months are ramped AE-days over that constant. ``roster_at`` is the only way
a past cutoff's roster is built: it shows starts and departures that had
happened by then and hides everything later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from .capacity_rules import DAYS_PER_AE_MONTH
from .fiscal import add_months

ONE = Decimal(1)
ZERO = Decimal(0)


@dataclass(frozen=True)
class Member:
    id: str
    role: str
    segment: str
    start: date
    end: date | None  # the last day employed; None while employed
    annual_quota: Decimal | None  # full-ramp, per year


@dataclass(frozen=True)
class RampCurve:
    """Share of a fully ramped rep's creation by tenure month 1, 2, ...; 1 after
    the last entry. ``source`` is fitted, entered or default; ``n`` is the
    sample behind a fitted curve (reps observed from hire); ``ranges`` holds a
    fitted entry's 95% range."""

    weights: tuple[Decimal, ...]
    source: str
    n: int = 0
    ranges: tuple[tuple[float, float], ...] = ()

    def weight(self, tenure: int) -> Decimal:
        if tenure < 1:
            return ZERO
        return self.weights[tenure - 1] if tenure <= len(self.weights) else ONE


def employed(m: Member, on: date) -> bool:
    return m.start <= on and (m.end is None or on <= m.end)


def heads_on(members, on: date) -> int:
    return sum(1 for m in members if employed(m, on))


def tenure_month(m: Member, on: date) -> int:
    """1 for the first anniversary month, 0 before the start."""
    if on < m.start:
        return 0
    k = (on.year - m.start.year) * 12 + on.month - m.start.month
    if add_months(m.start, k) > on:
        k -= 1
    return k + 1


def roster_at(members, cutoff: date) -> tuple[Member, ...]:
    """The roster as known on ``cutoff``: people who had started by then, each
    still employed unless their departure is dated on or before it."""
    seen = []
    for m in members:
        if m.start > cutoff:
            continue
        seen.append(m if m.end is None or m.end <= cutoff else _still_employed(m))
    return tuple(seen)


def _still_employed(m: Member) -> Member:
    return Member(m.id, m.role, m.segment, m.start, None, m.annual_quota)


def segments(m: Member, ramp: RampCurve, first: date, last: date):
    """(from, through, weight) runs of constant weight for ``m`` within the
    closed day range [first, last], clipped to their employment."""
    a = max(first, m.start)
    b = last if m.end is None else min(last, m.end)
    if a > b:
        return
    bounds = [add_months(m.start, k) for k in range(len(ramp.weights) + 1)]
    for k, weight in enumerate(
        ramp.weights
    ):  # tenure month k+1 = [bounds[k], bounds[k+1])
        lo, hi = max(a, bounds[k]), min(b, bounds[k + 1] - timedelta(days=1))
        if lo <= hi:
            yield lo, hi, weight
    lo = max(a, bounds[-1])
    if lo <= b:
        yield lo, b, ONE


def daily_ramped(members, ramp: RampCurve, first: date, last: date) -> list[Decimal]:
    """Ramped AE-days on each day of [first, last]."""
    out = [ZERO] * ((last - first).days + 1)
    for m in members:
        for lo, hi, w in segments(m, ramp, first, last):
            for i in range((lo - first).days, (hi - first).days + 1):
                out[i] += w
    return out


def ramped_ae_months(members, ramp: RampCurve, after: date, through: date) -> Decimal:
    """Ramped AE-months over the days in (after, through]."""
    total = ZERO
    first, last = after + timedelta(days=1), through
    for m in members:
        for lo, hi, w in segments(m, ramp, first, last):
            total += w * ((hi - lo).days + 1)
    return total / DAYS_PER_AE_MONTH


def ramped_heads_on(members, ramp: RampCurve, on: date) -> Decimal:
    """Ramped equivalents on a day: the sum of ramp weights of people employed."""
    return sum(
        (ramp.weight(tenure_month(m, on)) for m in members if employed(m, on)), ZERO
    )

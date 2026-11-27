"""The company's own past, read one fiscal creation quarter at a time (the rules are in
``worksheet_rules``). Everything here depends only on the files and the as-of date, never on a
plan, so a prepared company computes it once."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta
from decimal import Decimal

from .fiscal import add_months
from .records import Deal
from .worksheet_rules import Quarter, quarter_label

ZERO = Decimal(0)


def _quarter_starts(first: date, as_of: date, fy_start: date) -> list[date]:
    """Starts of every complete fiscal quarter beginning on or after ``first`` and ending by
    ``as_of``. The calendar is the profile's: quarters are three months from its fiscal start."""
    start = fy_start
    while start > first:
        start = add_months(start, -3)
    if start < first:
        start = add_months(start, 3)
    out = []
    while add_months(start, 3) - timedelta(days=1) <= as_of:
        out.append(start)
        start = add_months(start, 3)
    return out


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, ZERO) / len(values) if values else None


def observe(
    deals: Sequence[Deal],
    as_of: date,
    fy_start: date,
    horizon_days: int,
    exposure_of: Callable[[date, date], Decimal],
) -> list[Quarter]:
    """One ``Quarter`` per complete fiscal quarter in which deals could have been created.
    A win counts when it closed by the as-of date within ``horizon_days`` of creation.
    ``exposure_of(start, end)`` is the capacity the quarter had to create pipeline (ramped
    AE-months, or days where the capacity term is not in use)."""
    if not deals:
        return []
    first = min(d.created for d in deals)
    out = []
    for start in _quarter_starts(first, as_of, fy_start):
        end = add_months(start, 3) - timedelta(days=1)
        cohort = [d for d in deals if start <= d.created <= end]
        wins = [
            d
            for d in cohort
            if d.is_won
            and d.close is not None
            and d.close <= as_of
            and (d.close - d.created).days <= horizon_days
        ]
        exposure = exposure_of(start, end)
        out.append(
            Quarter(
                label=quarter_label(start, fy_start),
                start=start,
                end=end,
                created=len(cohort),
                wins=len(wins),
                mature=end + timedelta(days=horizon_days) <= as_of,
                exposure=exposure,
                win_rate=Decimal(len(wins)) / len(cohort) if cohort else None,
                won_arr=_mean([d.arr for d in wins]),
                cycle_days=_mean([Decimal((d.close - d.created).days) for d in wins]),
                productivity=Decimal(len(cohort)) / exposure if exposure > 0 else None,
            )
        )
    return out

"""MQL signal computations.

- `compute_mql_signals_from_buckets()` — weekly MQL counts trailing N days
- `compute_monthly_mql_actuals_from_buckets()` — monthly MQL counts for a
  fiscal calendar

There's no MQL representation in the connector's `fetch_*()` surface, so
these pure functions take pre-bucketed weekly/monthly counts as input.
The caller (backend) supplies already-shaped buckets — CSV backends pass
seed values from profile config; backends with native MQL data fetch
directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class MQLSignals:
    """Weekly MQL volume signals over a trailing window."""

    weekly_counts: list[dict] = field(default_factory=list)
    # Each entry: {"week_start": ISO_date, "count": int}
    total: int = 0
    avg_per_week: Optional[float] = None
    lookback_days: int = 0
    source: Optional[str] = None  # filled in by backend


@dataclass
class MonthlyMQLSeries:
    """Monthly MQL counts keyed by month-start date."""

    monthly_counts: dict[date, int] = field(default_factory=dict)
    fy_start: Optional[date] = None
    source: Optional[str] = None  # filled in by backend


def compute_mql_signals_from_buckets(
    weekly_buckets: list[dict],
    lookback_days: int,
    source: Optional[str] = None,
) -> MQLSignals:
    """Build an MQLSignals from already-bucketed weekly counts.

    Backends fetch raw weekly counts and call this with the pre-bucketed
    list. The function aggregates totals and averages.

    Args:
        weekly_buckets: list of {"week_start": ISO_date_str, "count": int}.
        lookback_days: For provenance.
        source: For provenance.

    Returns:
        MQLSignals with the buckets, total, and average.
    """
    weekly = list(weekly_buckets)
    total = sum(int(b.get("count") or 0) for b in weekly)
    avg = total / len(weekly) if weekly else None
    return MQLSignals(
        weekly_counts=weekly,
        total=total,
        avg_per_week=avg,
        lookback_days=lookback_days,
        source=source,
    )


def compute_monthly_mql_from_buckets(
    monthly_buckets: dict[date, int] | dict[str, int],
    fy_start: Optional[date] = None,
    source: Optional[str] = None,
) -> MonthlyMQLSeries:
    """Build a MonthlyMQLSeries from already-bucketed monthly counts.

    Args:
        monthly_buckets: {month_start_date_or_iso_str: count}.
        fy_start: Fiscal-year-start anchor for provenance.
        source: For provenance.

    Returns:
        MonthlyMQLSeries normalized to date keys.
    """
    normalized: dict[date, int] = {}
    for k, v in monthly_buckets.items():
        if isinstance(k, date):
            normalized[k] = int(v)
        else:
            try:
                normalized[date.fromisoformat(str(k)[:10])] = int(v)
            except ValueError:
                continue
    return MonthlyMQLSeries(
        monthly_counts=normalized,
        fy_start=fy_start,
        source=source,
    )

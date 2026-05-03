"""Pure-function port of `TieoutDataAccess.get_monthly_actuals()`.

Computes per-month bookings, losses, opportunity creation, and S2-entry
volumes from raw deal data.

Legacy implementation (engine/gtm_model/tieout/infra/data_access.py:511)
fetched these via source-specific aggregation calls (warehouse/SF). Per ARCHITECTURE.md,
this pure function reads the already-fetched deals.

Semantics for "first-S2-entry" (which determines the bucket month for the
monthly_entered_s2_amount series): see Deal.first_s2_entry_date, populated
by connectors that have stage history. Falls back to created_date when
first_s2_entry_date is None (heuristic — old behavior was equivalent for
deals that were created already in S2).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from engine.connectors.interface import Deal


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


@dataclass
class MonthlyActuals:
    """Monthly time series for bookings, losses, creation, S2 entry."""

    monthly_bookings: dict[date, float] = field(default_factory=dict)
    monthly_closed_lost: dict[date, float] = field(default_factory=dict)
    monthly_pipeline_creation: dict[date, float] = field(default_factory=dict)
    monthly_entered_s2: dict[date, float] = field(default_factory=dict)

    def as_rows(self) -> dict[str, list[dict]]:
        """Serialize to the legacy [{month: ISO, total: float}, ...] shape."""

        def rows(series: dict[date, float]) -> list[dict]:
            return [
                {"month": month.isoformat(), "total": float(total or 0.0)}
                for month, total in sorted(series.items())
            ]

        return {
            "monthly_bookings": rows(self.monthly_bookings),
            "monthly_closed_lost": rows(self.monthly_closed_lost),
            "monthly_pipeline_creation": rows(self.monthly_pipeline_creation),
            "monthly_entered_s2": rows(self.monthly_entered_s2),
        }


def compute_monthly_actuals(
    deals: Iterable[Deal],
    period_start: date,
    period_end: date,
) -> MonthlyActuals:
    """Compute per-month series from raw deals over a date period.

    Args:
        deals: All deals from the connector.
        period_start: Inclusive lower bound on the buckets returned.
        period_end: Inclusive upper bound.

    Returns:
        MonthlyActuals with four series keyed by month-start date.
        Bookings amounts use Year_1_ARR when available, else Amount.
    """
    bookings: dict[date, float] = defaultdict(float)
    losses: dict[date, float] = defaultdict(float)
    creation: dict[date, float] = defaultdict(float)
    entered_s2: dict[date, float] = defaultdict(float)

    for deal in deals:
        amount = float(
            deal.year_1_arr if deal.year_1_arr is not None else (deal.amount or 0.0)
        )

        # Bookings — closed-won, bucketed by close_date
        if deal.is_won and deal.close_date is not None:
            month = _month_floor(deal.close_date)
            if period_start <= deal.close_date <= period_end:
                bookings[month] += amount

        # Losses — closed (not won), bucketed by close_date
        if deal.is_closed and not deal.is_won and deal.close_date is not None:
            month = _month_floor(deal.close_date)
            if period_start <= deal.close_date <= period_end:
                losses[month] += amount

        # Pipeline creation — bucketed by created_date
        if deal.created_date is not None:
            month = _month_floor(deal.created_date)
            if period_start <= deal.created_date <= period_end:
                creation[month] += amount

        # Entered S2 — bucketed by first_s2_entry_date (or created_date fallback)
        anchor = deal.first_s2_entry_date or deal.created_date
        if anchor is not None and period_start <= anchor <= period_end:
            month = _month_floor(anchor)
            entered_s2[month] += amount

    return MonthlyActuals(
        monthly_bookings=dict(bookings),
        monthly_closed_lost=dict(losses),
        monthly_pipeline_creation=dict(creation),
        monthly_entered_s2=dict(entered_s2),
    )

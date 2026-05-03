"""Pure-function port of `TieoutDataAccess.get_closed_won_finance_summary()`.

Computes Amount / Year_1_ARR / ARR / NACV / non-recurring totals for
closed-won deals in a date period, grouped by deal type.

Legacy implementation (engine/gtm_model/tieout/infra/data_access.py:360)
wrapped this in a warehouse → Salesforce → empty fallback chain. Per ARCHITECTURE.md,
that source-routing is a backend concern, not a derivation concern.
This pure function operates on already-fetched deals.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Iterable, Optional

from engine.connectors.interface import Deal


@dataclass
class FinanceTotals:
    won_count: int = 0
    amount: float = 0.0
    year1_arr: float = 0.0
    arr: float = 0.0
    nacv: float = 0.0
    non_recurring: float = 0.0


@dataclass
class FinanceSummary:
    """Closed-won finance totals for a period, with by-type breakdown."""

    totals: FinanceTotals = field(default_factory=FinanceTotals)
    by_type: dict[str, FinanceTotals] = field(default_factory=dict)
    period: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize in the legacy shape consumed by snapshot/api code."""
        return {
            "totals": asdict(self.totals),
            "by_type": {k: asdict(v) for k, v in self.by_type.items()},
            "period": dict(self.period),
        }


def _accumulate(totals: FinanceTotals, deal: Deal) -> None:
    totals.won_count += 1
    totals.amount += float(deal.amount or 0.0)
    totals.year1_arr += float(deal.year_1_arr or 0.0)
    totals.arr += float(deal.arr or 0.0)
    totals.nacv += float(deal.nacv or 0.0)
    totals.non_recurring += float(deal.non_recurring or 0.0)


def compute_closed_won_finance_summary(
    deals: Iterable[Deal],
    period_start: date,
    period_end: date,
) -> FinanceSummary:
    """Sum closed-won finance totals over a date period, grouped by deal type.

    Args:
        deals: All deals from the connector (filter happens here).
        period_start: Inclusive period start (filters by Deal.close_date).
        period_end: Inclusive period end.

    Returns:
        FinanceSummary with overall totals and per-type breakdown.
        `by_type` keys are Deal.type strings; deals with no type bucket
        under "Unknown".

    Notes:
        - Deals with `is_won=False` or no close_date are excluded.
        - close_date is compared as a date; if a deal's close_date is
          None it's excluded (no period information).
        - Numeric fields default to 0 when None on the Deal.
    """
    summary = FinanceSummary(
        period={
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        }
    )
    by_type: dict[str, FinanceTotals] = defaultdict(FinanceTotals)

    for deal in deals:
        if not deal.is_won:
            continue
        if deal.close_date is None:
            continue
        if not (period_start <= deal.close_date <= period_end):
            continue
        _accumulate(summary.totals, deal)
        _accumulate(by_type[deal.type or "Unknown"], deal)

    summary.by_type = dict(by_type)
    return summary

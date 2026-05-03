"""Pure-function port of `_get_observed_arr_movements()`.

Builds an ARR waterfall (New Logo / Expansion / Contraction / Churn)
from raw closed deals.

Legacy implementation (engine/gtm_model/tieout/runtime/observed.py:525)
queried Salesforce or warehouse for aggregated movements. Per ARCHITECTURE.md, this
pure function operates on already-fetched deals via the `revenue_type`
field on Deal (set by the connector).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from engine.connectors.interface import Deal


@dataclass
class ARRMovements:
    """ARR waterfall components for a period."""

    new_logo_arr: float = 0.0
    expansion_arr: float = 0.0
    contraction_arr: float = 0.0  # negative downsells, tracked as positive numbers
    churn_arr: float = 0.0  # lost customers, tracked as positive numbers
    new_logo_count: int = 0
    expansion_count: int = 0
    contraction_count: int = 0
    churn_count: int = 0
    period_start: date | None = None
    period_end: date | None = None
    source: Optional[str] = None  # filled in by backend ("derived"/"warehouse"/"Salesforce")
    # Annual rate fields are computed by the consumer (assembly.py / plan
    # churn rate logic) which combines these absolute movements with
    # config-driven base ARR. Included here as Optional placeholders so
    # the legacy contract is preserved without forcing this
    # module to know about churn-rate config.
    observed_annual_churn_rate: Optional[float] = None
    observed_annual_expansion_rate: Optional[float] = None


# Maps Deal.revenue_type values to ARRMovements buckets. Profiles can use
# their own revenue_type vocabulary; the connector normalizes to the
# canonical set here.
_REVENUE_TYPE_BUCKETS = {
    "new_logo": "new_logo",
    "new_business": "new_logo",
    "expansion": "expansion",
    "upsell": "expansion",
    "cross_sell": "expansion",
    "contraction": "contraction",
    "downsell": "contraction",
    "churn": "churn",
    "renewal": None,  # renewals don't change ARR; skipped
}


def compute_arr_movements(
    deals: Iterable[Deal],
    period_start: date,
    period_end: date,
) -> ARRMovements:
    """Compute ARR waterfall components from won deals in a period.

    Args:
        deals: All deals from the connector.
        period_start: Inclusive period start (filters by close_date).
        period_end: Inclusive period end.

    Returns:
        ARRMovements with new-logo / expansion / contraction / churn
        components. Uses Deal.year_1_arr (or Deal.arr fallback) as the
        ARR contribution. Deals without a recognized revenue_type bucket
        under "expansion" by convention (matches legacy behavior).
    """
    movements = ARRMovements(period_start=period_start, period_end=period_end)

    for deal in deals:
        if not deal.is_won or deal.close_date is None:
            continue
        if not (period_start <= deal.close_date <= period_end):
            continue

        rt = (deal.revenue_type or "").lower().replace(" ", "_")
        if rt in _REVENUE_TYPE_BUCKETS:
            bucket = _REVENUE_TYPE_BUCKETS[rt]
            if bucket is None:
                # Recognized type that doesn't move ARR (e.g. renewal)
                continue
        elif rt:
            # Unknown but non-empty type — best guess: expansion
            bucket = "expansion"
        else:
            # Missing revenue_type → default to new_logo
            bucket = "new_logo"

        contribution = float(
            deal.year_1_arr if deal.year_1_arr is not None else (deal.arr or 0.0)
        )

        if bucket == "new_logo":
            movements.new_logo_arr += contribution
            movements.new_logo_count += 1
        elif bucket == "expansion":
            movements.expansion_arr += contribution
            movements.expansion_count += 1
        elif bucket == "contraction":
            movements.contraction_arr += abs(contribution)
            movements.contraction_count += 1
        elif bucket == "churn":
            movements.churn_arr += abs(contribution)
            movements.churn_count += 1

    return movements

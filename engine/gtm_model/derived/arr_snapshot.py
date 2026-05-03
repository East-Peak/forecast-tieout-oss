"""Pure-function port of `TieoutDataAccess.get_beginning_arr_snapshot()`.

Computes the fiscal-year-start ARR base from active won opportunities
whose effective period brackets the period_start anchor.

Legacy implementation (engine/gtm_model/tieout/infra/data_access.py:266)
delegated to warehouse or Salesforce aggregate methods. Per ARCHITECTURE.md, those
source-system aggregations are a backend concern; this pure function
operates on already-fetched deals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from engine.connectors.interface import Deal


@dataclass
class ARRSnapshot:
    """Resolved beginning-ARR with provenance metadata."""

    value: float = 0.0
    opp_count: int = 0
    method: str = "active_won_opportunity_window"
    is_live: bool = True
    as_of: Optional[str] = None
    metric_used: str = "year_1_arr"
    source: Optional[str] = None  # Filled in by the backend
    warning: Optional[str] = None
    extras: dict = field(default_factory=dict)

    def to_tuple(self) -> tuple[float, dict]:
        """Match the legacy (value, provenance_dict) return shape."""
        provenance = {
            "value": self.value,
            "method": self.method,
            "metric_used": self.metric_used,
            "is_live": self.is_live,
            "opp_count": self.opp_count,
        }
        if self.as_of is not None:
            provenance["as_of"] = self.as_of
        if self.source is not None:
            provenance["source"] = self.source
        if self.warning is not None:
            provenance["warning"] = self.warning
        provenance.update(self.extras)
        return self.value, provenance


def compute_beginning_arr(
    deals: Iterable[Deal],
    period_start: date,
    fallback_arr: float = 0.0,
    fallback_label: Optional[str] = None,
) -> ARRSnapshot:
    """Sum Year_1_ARR over deals whose effective period brackets period_start.

    Args:
        deals: All deals from the connector. Only is_won deals with
            an effective_start_date <= period_start <= effective_end_date
            contribute.
        period_start: The fiscal-year-start anchor date.
        fallback_arr: Configured beginning_arr from targets.yaml. Used
            when the computed value is 0 (no qualifying deals).
        fallback_label: Optional label for the fallback source (e.g.
            "targets.yaml"); used in the snapshot's provenance dict.

    Returns:
        ARRSnapshot with the computed value, opp count, and provenance.
        When the computed value is 0, falls back to `fallback_arr` with
        is_live=False and a warning.
    """
    total = 0.0
    count = 0
    for deal in deals:
        if not deal.is_won:
            continue
        if deal.effective_start_date is None or deal.effective_end_date is None:
            continue
        if not (deal.effective_start_date <= period_start <= deal.effective_end_date):
            continue
        # Prefer Year_1_ARR; fall back to ARR if unavailable.
        contribution = (
            deal.year_1_arr if deal.year_1_arr is not None else deal.arr
        )
        if contribution is None:
            continue
        total += float(contribution)
        count += 1

    if count == 0 or total <= 0:
        return ARRSnapshot(
            value=float(fallback_arr or 0.0),
            opp_count=0,
            method="config_fallback",
            metric_used="targets.beginning_arr",
            is_live=False,
            as_of=period_start.isoformat(),
            source=fallback_label,
            warning=(
                "Using configured beginning ARR — no qualifying won "
                "opportunities had an effective period bracketing "
                f"{period_start.isoformat()}."
            ),
        )

    return ARRSnapshot(
        value=total,
        opp_count=count,
        method="active_won_opportunity_window",
        metric_used="year_1_arr",
        is_live=True,
        as_of=period_start.isoformat(),
    )

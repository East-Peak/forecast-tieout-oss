"""Pure-function port of `TieoutDataAccess.get_open_inventory_snapshot()`.

Computes the current open opportunity inventory from raw deals (filtered
to is_closed=False, S2+).

Legacy implementation (engine/gtm_model/tieout/infra/data_access.py:62)
delegated to source-specific aggregations. Per ARCHITECTURE.md, this pure function
operates on already-fetched deals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Optional

from engine.connectors.interface import Deal


# Stages considered "open pipeline" for inventory analytics. Pre-S2 deals
# are excluded — they're earlier in the funnel and not yet committed.
INVENTORY_STAGES: frozenset[str] = frozenset({"S2", "S3", "S4", "S5"})


@dataclass
class OpenInventoryOpportunity:
    """One row in the open-inventory snapshot.

    Field shape matches the consumer contract in
    engine/gtm_model/pipeline_rollforward.py:16 + the snapshot serializer.
    """

    opp_id: str
    opp_name: str
    stage: str
    amount: float = 0.0
    arr: Optional[float] = None
    metric_value: Optional[float] = None  # populated from year_1_arr or amount
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    record_type_name: Optional[str] = None
    forecast_category: Optional[str] = None
    source_stream: Optional[str] = None
    close_date: Optional[str] = None  # ISO date
    created_date: Optional[str] = None  # ISO date
    s2_date: Optional[str] = None  # ISO date
    raw_stage: Optional[str] = None
    is_renewal: bool = False
    is_open_stage: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "opp_id": self.opp_id,
            "opp_name": self.opp_name,
            "stage": self.stage,
            "amount": self.amount,
            "arr": self.arr,
            "metric_value": self.metric_value,
            "owner_id": self.owner_id,
            "owner_name": self.owner_name,
            "record_type_name": self.record_type_name,
            "forecast_category": self.forecast_category,
            "source_stream": self.source_stream,
            "close_date": self.close_date,
            "created_date": self.created_date,
            "s2_date": self.s2_date,
            "raw_stage": self.raw_stage,
            "is_renewal": self.is_renewal,
            "is_open_stage": self.is_open_stage,
        }


@dataclass
class OpenInventorySnapshot:
    as_of: date
    opportunities: list[OpenInventoryOpportunity] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "opportunities": [o.to_dict() for o in self.opportunities],
            "provenance": dict(self.provenance),
        }


def compute_open_inventory_snapshot(
    deals: Iterable[Deal],
    as_of: date,
) -> OpenInventorySnapshot:
    """Build an open-inventory snapshot of S2+ open deals.

    Args:
        deals: All deals from the connector.
        as_of: Snapshot timestamp (recorded in provenance).

    Returns:
        OpenInventorySnapshot with one entry per open S2+ deal,
        sorted by amount descending. Empty list when no qualifying deals.
    """
    opportunities: list[OpenInventoryOpportunity] = []
    for deal in deals:
        if deal.is_closed or deal.is_won:
            continue
        if deal.stage not in INVENTORY_STAGES:
            continue

        metric_value = (
            float(deal.year_1_arr) if deal.year_1_arr is not None
            else float(deal.amount or 0.0)
        )
        is_renewal = (deal.revenue_type or "").lower() == "renewal" or (
            (deal.type or "").lower() == "renewal"
        )
        opportunities.append(
            OpenInventoryOpportunity(
                opp_id=deal.id,
                opp_name=deal.name,
                stage=deal.stage,
                amount=float(deal.amount or 0.0),
                arr=float(deal.arr) if deal.arr is not None else None,
                metric_value=metric_value,
                owner_id=deal.owner_id or None,
                owner_name=deal.owner_name,
                record_type_name=deal.type,
                forecast_category=deal.forecast_category,
                source_stream=deal.source_stream,
                close_date=(
                    deal.close_date.isoformat() if deal.close_date else None
                ),
                created_date=(
                    deal.created_date.isoformat() if deal.created_date else None
                ),
                s2_date=(
                    deal.first_s2_entry_date.isoformat()
                    if deal.first_s2_entry_date
                    else None
                ),
                raw_stage=deal.raw_stage,
                is_renewal=is_renewal,
                is_open_stage=True,
            )
        )

    opportunities.sort(key=lambda o: o.amount, reverse=True)

    return OpenInventorySnapshot(
        as_of=as_of,
        opportunities=opportunities,
        provenance={
            "source": "derived",
            "method": "filter_open_s2_plus",
            "is_live": True,
            "opp_count": len(opportunities),
        },
    )

"""Open inventory resolution: ProfileBackend → warehouse → Salesforce → empty."""

from __future__ import annotations

import copy
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


class OpenInventoryMixin:
    def get_open_inventory_snapshot(self, as_of: Optional[date] = None):
        """Return the current open opportunity inventory.

        Resolution order (per ARCHITECTURE.md):
        1. ProfileBackend (CSV/Snowflake/Salesforce/custom) when configured
        2. Legacy warehouse gateway
        3. Legacy Salesforce gateway
        4. Empty snapshot (config-only mode)
        """
        from gtm_model.pipeline_rollforward import (
            OpenInventorySnapshot,
            build_open_inventory_snapshot_from_cdw,
            build_open_inventory_snapshot_from_salesforce,
        )

        as_of = as_of or date.today()
        cache = self.get_open_inventory_cache()
        if as_of in cache:
            return copy.deepcopy(cache[as_of])

        # Backend-first path (CSV / pluggable). Returns immediately when
        # the backend produces deals; falls through to warehouse/SF otherwise.
        backend_snapshot = self._open_inventory_from_backend(as_of)
        if backend_snapshot is not None and backend_snapshot.opportunities:
            cache[as_of] = copy.deepcopy(backend_snapshot)
            return backend_snapshot

        cdw_status = "not_attempted"

        cdw = self.get_cdw()
        if cdw is not None and not self.is_cdw_query_failed():
            try:
                rows = cdw.get_open_pipeline_detail()
                snapshot = build_open_inventory_snapshot_from_cdw(rows, as_of=as_of)
                if snapshot.opportunities:
                    cache[as_of] = copy.deepcopy(snapshot)
                    return snapshot
                cdw_status = "empty"
            except Exception as exc:
                logger.warning("Open inventory warehouse query failed: %s", exc)
                cdw_status = "query_failed"

        sf = self.get_sf()
        if sf is not None:
            try:
                rows = sf.get_pipeline_detail()
                snapshot = build_open_inventory_snapshot_from_salesforce(rows, as_of=as_of)
                if snapshot.opportunities:
                    snapshot.provenance["fallback_from"] = "warehouse"
                    snapshot.provenance["fallback_reason"] = cdw_status
                    cache[as_of] = copy.deepcopy(snapshot)
                    return snapshot
            except Exception as exc:
                logger.warning("Open inventory Salesforce query failed: %s", exc)

        snapshot = OpenInventorySnapshot(
            as_of=as_of,
            opportunities=[],
            provenance={
                "source": "unavailable",
                "is_live": False,
                "fallback_from": "warehouse",
                "fallback_reason": cdw_status,
            },
        )
        cache[as_of] = copy.deepcopy(snapshot)
        return snapshot

    def _open_inventory_from_backend(self, as_of: date):
        """Build a legacy-shape OpenInventorySnapshot from a ProfileBackend.

        Returns None when no backend is configured (legacy mode) or
        when the backend fetch raises. Returns an empty snapshot rather
        than None when the backend returns zero qualifying deals — the
        caller treats empty as "ProfileBackend was tried but had no data,"
        which is distinct from "no backend configured."
        """
        if self.get_backend is None:
            return None
        try:
            backend = self.get_backend()
        except Exception as exc:
            logger.warning("ProfileBackend resolution failed: %s", exc)
            return None
        if backend is None:
            return None

        from gtm_model.pipeline_rollforward import (
            OpenInventorySnapshot,
            OpenOpportunity,
            OPEN_STAGE_ORDER,
        )

        try:
            deals = backend.fetch_deals()
        except Exception as exc:
            logger.warning("ProfileBackend.fetch_deals() failed: %s", exc)
            return None

        opportunities: list[OpenOpportunity] = []
        for deal in deals:
            if deal.is_closed or deal.is_won:
                continue
            if deal.stage not in OPEN_STAGE_ORDER:
                continue
            opportunities.append(
                OpenOpportunity(
                    opp_id=deal.id,
                    stage=deal.stage,
                    amount=float(deal.amount or 0.0),
                    arr=float(deal.arr or 0.0),
                    close_date=deal.close_date,
                    created_date=deal.created_date,
                    source_stream=(deal.source_stream or deal.source or "unknown"),
                    opp_type=deal.type or "",
                    raw_stage_name=(deal.raw_stage or deal.stage),
                    record_type_name=deal.type or "",
                    forecast_category=deal.forecast_category or "",
                    owner_name=deal.owner_name or "",
                    metric_source=("ARR" if deal.arr else "Amount"),
                )
            )

        return OpenInventorySnapshot(
            as_of=as_of,
            opportunities=opportunities,
            provenance={
                "source": "ProfileBackend",
                "method": "backend_fetch_deals",
                "is_live": True,
                "opp_count": len(opportunities),
            },
        )


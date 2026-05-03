"""Connector bootstrap and warehouse/SF query helpers for Planning Tie-Out."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from gtm_model.tieout.runtime.env import detect_snow_cli_command, get_active_snowflake_session

logger = logging.getLogger(__name__)


@dataclass
class TieoutConnectorGateway:
    """Lazy-init connectors and wrap warehouse/SF query entrypoints."""

    owner: Any

    def get_sf_connector(self):
        """Legacy seam — returns None.

        No Salesforce connector ships with the OSS. To wire one, follow
        the ConnectorInterface pattern in
        `engine/connectors/csv_connector.py` and register a backend via
        `engine/profile_backend/factory.py`. See ARCHITECTURE.md.
        """
        self.owner._sf_checked = True
        self.owner.sf = None
        return None

    def get_cdw_connector(self):
        """Legacy seam — returns None.

        No warehouse connector ships with the OSS. Wire your warehouse
        via ConnectorInterface + ProfileBackend. See ARCHITECTURE.md.
        """
        self.owner._cdw_checked = True
        self.owner.cdw = None
        return None

    def try_cdw_freshness(self) -> dict:
        """Check warehouse freshness; returns empty dict on failure."""
        if self.owner._cdw_freshness_loaded:
            return dict(self.owner._cdw_freshness_cache or {})
        cdw = self.owner._get_cdw()
        if cdw is None or self.owner._cdw_queries_failed:
            self.owner._cdw_freshness_loaded = True
            self.owner._cdw_freshness_cache = {}
            return {}
        try:
            freshness = cdw.get_mart_freshness()
            self.owner._cdw_freshness_loaded = True
            self.owner._cdw_freshness_cache = dict(freshness or {})
            return dict(self.owner._cdw_freshness_cache)
        except Exception as exc:
            logger.warning("warehouse freshness check failed: %s", exc)
            self.owner._cdw_freshness_loaded = True
            self.owner._cdw_freshness_cache = {}
            return {}

    def try_funnel_from_cdw(self, quarter: str) -> Optional[dict]:
        """Try to build funnel from warehouse; returns None on failure."""
        cdw = self.owner._get_cdw()
        if cdw is None or self.owner._cdw_queries_failed:
            return None
        try:
            from gtm_model.funnel_engine import build_funnel_from_cdw

            return build_funnel_from_cdw(cdw, quarter)
        except Exception as exc:
            logger.warning("warehouse funnel build failed for %s: %s", quarter, exc)
            return None

    def try_cdw_bookings(self, quarter: str) -> Optional[float]:
        """Try to get warehouse bookings; returns None on failure."""
        if quarter in self.owner._cdw_bookings_cache:
            return self.owner._cdw_bookings_cache[quarter]
        cdw = self.owner._get_cdw()
        if cdw is None or self.owner._cdw_queries_failed:
            self.owner._cdw_bookings_cache[quarter] = None
            return None
        try:
            bookings = cdw.get_bookings(quarter)
            self.owner._cdw_bookings_cache[quarter] = bookings
            return bookings
        except Exception as exc:
            logger.warning("warehouse bookings query failed for %s: %s", quarter, exc)
            self.owner._cdw_bookings_cache[quarter] = None
            return None

    def try_sf_bookings(self, quarter: str) -> Optional[float]:
        """Try to get SF bookings for reconciliation; returns None on failure."""
        if quarter in self.owner._sf_bookings_cache:
            return self.owner._sf_bookings_cache[quarter]
        cdw = self.owner._get_cdw()
        if cdw is None or self.owner._cdw_queries_failed:
            self.owner._sf_bookings_cache[quarter] = None
            return None
        try:
            bookings = cdw.get_sf_bookings_for_reconciliation(quarter)
            self.owner._sf_bookings_cache[quarter] = bookings
            return bookings
        except Exception as exc:
            logger.warning("SF bookings reconciliation failed for %s: %s", quarter, exc)
            self.owner._sf_bookings_cache[quarter] = None
            return None

    def try_closed_won_timing(self) -> Optional[list[dict]]:
        """Try to get closed-won timing distribution; returns None on failure.

        Fallback chain: warehouse (≥30 deals) → Salesforce → None.
        """
        if self.owner._closed_won_timing_loaded:
            return self.owner._closed_won_timing_cache

        # --- Tier 1: warehouse ---
        cdw = self.owner._get_cdw()
        if cdw is not None and not self.owner._cdw_queries_failed:
            try:
                timing = cdw.get_closed_won_timing(lookback_months=12)
                if timing:
                    total = sum(entry["count"] for entry in timing)
                    if total >= 30:
                        self.owner._closed_won_timing_loaded = True
                        self.owner._closed_won_timing_cache = timing
                        self.owner._closed_won_timing_source = "warehouse"
                        return timing
                    logger.info("warehouse close timing has only %d deals (need 30); trying Salesforce", total)
            except Exception as exc:
                logger.warning("warehouse closed-won timing query failed: %s", exc)

        # --- Tier 2: Salesforce ---
        # Route Salesforce access through the owner seam so tests can
        # hermetically stub `_get_sf` without duplicating connector internals.
        sf = self.owner._get_sf()
        if sf is not None:
            try:
                # Salesforce stage-history sample is thinner than warehouse, but still
                # useful when it clears a smaller minimum and matches config.
                timing = sf.get_close_timing_distribution(lookback_months=18, min_sample=10)
                if timing is not None:
                    self.owner._closed_won_timing_loaded = True
                    self.owner._closed_won_timing_cache = timing
                    self.owner._closed_won_timing_source = "Salesforce"
                    return timing
            except Exception as exc:
                logger.warning("Salesforce close timing query failed: %s", exc)

        # --- Tier 3: give up ---
        self.owner._closed_won_timing_loaded = True
        self.owner._closed_won_timing_cache = None
        self.owner._closed_won_timing_source = None
        return None

    def try_weekly_targets_from_cdw(self, quarter: str) -> Optional[dict]:
        """Try to get weekly targets from warehouse seeds; returns None on failure."""
        if quarter in self.owner._weekly_targets_cache:
            return self.owner._weekly_targets_cache[quarter]
        cdw = self.owner._get_cdw()
        if cdw is None or self.owner._cdw_queries_failed:
            self.owner._weekly_targets_cache[quarter] = None
            return None
        try:
            weekly_targets = cdw.get_weekly_targets(quarter)
            self.owner._weekly_targets_cache[quarter] = weekly_targets
            return weekly_targets
        except Exception as exc:
            logger.warning("warehouse weekly targets query failed for %s: %s", quarter, exc)
            self.owner._weekly_targets_cache[quarter] = None
            return None

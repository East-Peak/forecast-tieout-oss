"""Beginning ARR resolution and bookings summary cache."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BeginningArrMixin:
    def get_beginning_arr_snapshot(self) -> tuple[float, dict]:
        """Resolve FY beginning ARR using active won-opportunity window logic.

        Resolution order (per ARCHITECTURE.md):
        1. ProfileBackend.compute_beginning_arr() when configured
        2. Legacy warehouse gateway
        3. Legacy Salesforce gateway
        4. targets.yaml config fallback
        """
        cached = self.get_beginning_arr_cache()
        if cached is not None:
            return cached

        targets = self.get_targets()
        quarter_dates = self.get_quarter_dates()
        fallback_arr = float(targets.get("beginning_arr", 0.0) or 0.0)
        # Pick the first (chronologically earliest) quarter as the fiscal-year
        # start anchor. quarter_dates is an ordered dict keyed by quarter label;
        # iteration order = chronological order per get_quarter_dates contract.
        first_q_label = next(iter(quarter_dates), None)
        first_q_start = quarter_dates[first_q_label][0] if first_q_label else None
        fiscal_year_start = (
            targets.get("fiscal_year_start")
            or (first_q_start.isoformat() if first_q_start else None)
        )
        period_start = first_q_start

        fallback = (
            fallback_arr,
            {
                "value": fallback_arr,
                "source": "targets.yaml",
                "method": "top_down_config_fallback",
                "as_of": fiscal_year_start,
                "is_live": False,
                "warning": "Using configured beginning ARR because a credible CRM-derived start-of-year ARR base was not available.",
            },
        )

        # Backend-first path
        if period_start is not None and self.get_backend is not None:
            try:
                backend = self.get_backend()
            except Exception:
                backend = None
            if backend is not None:
                try:
                    arr_snapshot = backend.compute_beginning_arr(
                        period_start=period_start,
                        fallback_arr=fallback_arr,
                        fallback_label="targets.yaml",
                    )
                    value, provenance = arr_snapshot.to_tuple()
                    if value > 0 and arr_snapshot.is_live:
                        # Backend produced a real signal — use it.
                        resolved = (value, provenance)
                        self.set_beginning_arr_cache(resolved)
                        return resolved
                except Exception as exc:
                    logger.warning("ProfileBackend beginning ARR failed: %s", exc)

        cdw = self.get_cdw()
        try:
            if cdw is not None and not self.is_cdw_query_failed():
                snapshot = cdw.get_beginning_arr_snapshot(period_start)
                value = float(snapshot.get("total_year1_arr") or 0.0)
                if value > 0:
                    resolved = (
                        value,
                        {
                            "value": value,
                            "source": "warehouse",
                            "method": "active_won_opportunity_window",
                            "metric_used": "YEAR_1_ARR__c",
                            "as_of": fiscal_year_start,
                            "is_live": True,
                            "opp_count": int(snapshot.get("opp_count") or 0),
                            "snapshot": snapshot,
                        },
                    )
                    self.set_beginning_arr_cache(resolved)
                    return resolved
        except Exception as exc:
            logger.warning("warehouse beginning ARR snapshot failed: %s", exc)

        sf = self.get_sf()
        if sf is None:
            self.set_beginning_arr_cache(fallback)
            return fallback

        try:
            snapshot = sf.get_beginning_arr_snapshot(period_start)
            year1_arr = float(snapshot.get("total_year1_arr") or 0.0)
            arr = float(snapshot.get("total_arr") or 0.0)
            chosen_value = year1_arr if year1_arr > 0 else arr
            metric_used = "Year_1_ARR__c" if year1_arr > 0 else "ARR__c"
            if chosen_value > 0:
                resolved = (
                    chosen_value,
                    {
                        "value": chosen_value,
                        "source": "Salesforce",
                        "method": "active_won_opportunity_window",
                        "metric_used": metric_used,
                        "as_of": fiscal_year_start,
                        "is_live": True,
                        "opp_count": int(snapshot.get("opp_count") or 0),
                        "snapshot": snapshot,
                    },
                )
                self.set_beginning_arr_cache(resolved)
                return resolved
        except Exception as exc:
            logger.warning("Salesforce beginning ARR snapshot failed; using config fallback: %s", exc)
            provenance = dict(fallback[1])
            provenance["warning"] = f"Salesforce ARR snapshot failed: {exc}"
            resolved = (fallback_arr, provenance)
            self.set_beginning_arr_cache(resolved)
            return resolved

        self.set_beginning_arr_cache(fallback)
        return fallback

    def _cache_bookings_summary(self, cache_key: str, resolved) -> None:
        """Write a finance-summary result into the as_of-keyed cache.

        Tolerates a legacy single-tuple cache shape: if the current
        cache isn't a dict, replace it with one keyed under cache_key.
        """
        cached = self.get_bookings_summary_cache()
        if not isinstance(cached, dict):
            cached = {}
        cached[cache_key] = resolved
        self.set_bookings_summary_cache(cached)


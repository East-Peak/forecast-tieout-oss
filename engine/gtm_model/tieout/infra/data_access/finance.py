"""Closed-won finance summary and monthly amount-series resolution."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from gtm_model.tieout.infra.data_access._helpers import _monthly_series_to_rows

logger = logging.getLogger(__name__)


class FinanceMixin:
    def get_closed_won_finance_summary(
        self, as_of: Optional[date] = None
    ) -> tuple[dict, dict]:
        """Return closed-won finance totals for Amount vs ARR vs NACV display.

        Cache is keyed by `as_of` so repeated calls with different cutoff
        dates don't return stale results (e.g. parity-test reruns under
        different --as-of values within a single PlanningTieout instance).
        """
        cache_key = as_of.isoformat() if as_of is not None else "__today__"
        cached = self.get_bookings_summary_cache()
        if isinstance(cached, dict) and cache_key in cached:
            return cached[cache_key]

        empty_summary = {
            "totals": {
                "won_count": 0,
                "amount": 0.0,
                "year1_arr": 0.0,
                "arr": 0.0,
                "nacv": 0.0,
                "non_recurring": 0.0,
            },
            "by_type": {},
        }
        empty_provenance = {
            "source": "unavailable",
            "method": "none",
            "warning": "Closed-won finance summary unavailable.",
            "is_live": False,
        }

        # Pick the first quarter chronologically — quarter_dates iteration
        # order is fiscal-year-start order per the contract.
        _quarter_dates = self.get_quarter_dates()
        _first_q_label = next(iter(_quarter_dates), None)
        period_start = _quarter_dates[_first_q_label][0] if _first_q_label else date.today()
        # Honor --as-of for deterministic snapshots (per ARCHITECTURE.md).
        period_end = as_of or date.today()
        cdw_status = "not_attempted"

        # Backend-first path (per ARCHITECTURE.md)
        if self.get_backend is not None:
            try:
                backend = self.get_backend()
            except Exception:
                backend = None
            if backend is not None:
                try:
                    summary_obj = backend.compute_closed_won_finance_summary(
                        period_start, period_end
                    )
                    summary_dict = summary_obj.to_dict()
                    if summary_dict["totals"]["won_count"] > 0:
                        resolved = (
                            summary_dict,
                            {
                                "source": "ProfileBackend",
                                "method": "backend_compute_closed_won_finance_summary",
                                "is_live": True,
                                "period": summary_dict.get("period", {}),
                            },
                        )
                        self._cache_bookings_summary(cache_key, resolved)
                        return resolved
                except Exception as exc:
                    logger.warning(
                        "ProfileBackend closed-won finance summary failed: %s", exc
                    )

        try:
            cdw = self.get_cdw()
            if cdw is not None and not self.is_cdw_query_failed():
                summary = cdw.get_closed_won_finance_summary(
                    start_date=period_start,
                    end_date=period_end,
                )
                resolved = (
                    summary,
                    {
                        "source": "warehouse",
                        "method": "closed_won_aggregate",
                        "is_live": True,
                        "period": summary.get("period", {}),
                        "snapshot_time": summary.get("snapshot_time"),
                        "warning": "NACV may be 0 if your warehouse doesn't replicate the source NACV field.",
                    },
                )
                self._cache_bookings_summary(cache_key, resolved)
                return resolved
        except Exception as exc:
            logger.warning("warehouse closed-won finance summary failed: %s", exc)
            cdw_status = "query_failed"

        sf = self.get_sf()
        try:
            if sf is not None:
                summary = sf.get_closed_won_finance_summary(
                    start_date=period_start,
                    end_date=period_end,
                )
                resolved = (
                    summary,
                    {
                        "source": "Salesforce",
                        "method": "closed_won_aggregate",
                        "is_live": True,
                        "period": summary.get("period", {}),
                        "snapshot_time": summary.get("snapshot_time"),
                        "fallback_from": "warehouse",
                        "fallback_reason": cdw_status,
                    },
                )
                self._cache_bookings_summary(cache_key, resolved)
                return resolved
        except Exception as exc:
            logger.warning("Salesforce closed-won finance summary failed: %s", exc)

        resolved = (empty_summary, empty_provenance)
        self._cache_bookings_summary(cache_key, resolved)
        return resolved

    def _resolve_monthly_amount_series(
        self,
        *,
        start_date: date,
        end_date: date,
        cdw_loader: Callable[[Any, date, date], dict[date, float]],
        sf_loader: Callable[[Any, date, date], dict[date, float]],
        cdw_method: str,
        sf_method: str,
        unavailable_warning: str,
    ) -> tuple[dict[date, float], dict]:
        """Resolve a monthly amount series from warehouse first, then Salesforce."""
        period = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        cdw_status = "not_attempted"

        try:
            cdw = self.get_cdw()
            if cdw is not None and not self.is_cdw_query_failed():
                series = dict(cdw_loader(cdw, start_date, end_date) or {})
                return (
                    series,
                    {
                        "source": "warehouse",
                        "method": cdw_method,
                        "is_live": True,
                        "period": period,
                        "points": len(series),
                    },
                )
            cdw_status = "unavailable"
        except Exception as exc:
            logger.warning("warehouse monthly series failed (%s): %s", cdw_method, exc)
            cdw_status = "query_failed"

        try:
            sf = self.get_sf()
            if sf is not None:
                series = dict(sf_loader(sf, start_date, end_date) or {})
                return (
                    series,
                    {
                        "source": "Salesforce",
                        "method": sf_method,
                        "is_live": True,
                        "period": period,
                        "points": len(series),
                        "fallback_from": "warehouse",
                        "fallback_reason": cdw_status,
                    },
                )
        except Exception as exc:
            logger.warning("Salesforce monthly series failed (%s): %s", sf_method, exc)

        return (
            {},
            {
                "source": "unavailable",
                "method": "none",
                "is_live": False,
                "period": period,
                "warning": unavailable_warning,
            },
        )


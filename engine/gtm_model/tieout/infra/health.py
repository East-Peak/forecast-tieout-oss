"""Health-check helpers for Planning Tie-Out."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TieoutHealthChecker:
    """Run the tieout health diagnostics via the public wrapper methods."""

    owner: Any

    def _q1_actual_bookings_from_snapshot(self, runtime_snapshot: Any | None) -> tuple[float | None, str | None]:
        """Sum Q1 monthly bookings from a shared runtime snapshot when available."""
        if runtime_snapshot is None:
            return None, None

        actuals = getattr(runtime_snapshot, "monthly_actuals", None) or {}
        rows = actuals.get("bookings_by_month") or []
        provenance = (actuals.get("provenance") or {}).get("bookings_by_month") or {}
        source = provenance.get("source")
        start, end = self.owner.QUARTER_DATES["Q1FY26"]
        total = 0.0
        matched = False
        for row in rows:
            raw_month = row.get("month")
            if not raw_month:
                continue
            try:
                month_start = date.fromisoformat(str(raw_month)[:10])
            except (TypeError, ValueError):
                continue
            if start <= month_start <= end:
                total += float(row.get("total") or 0.0)
                matched = True
        return (total if matched else 0.0), (str(source) if source else None)

    def run(self, runtime_snapshot: Any | None = None) -> dict:
        """Run all health checks. Returns {} if warehouse is unavailable."""
        try:
            from gtm_model.data_health import assess_freshness

            freshness_data = self.owner.connector_gateway.try_cdw_freshness()
            if not freshness_data:
                return {
                    "overall_status": "yellow",
                    "freshness": {
                        "status": "yellow",
                        "use_warehouse": False,
                        "hours_old": None,
                        "message": "Warehouse unavailable; using config-only mode.",
                    },
                    "bookings_reconciliation": {"status": "ok", "message": "Skipped (Warehouse unavailable)"},
                    "decay_curve": {"status": "yellow", "message": "No observed close-timing data — using config assumption"},
                    "targets": {"status": "aligned", "message": "Skipped (Warehouse unavailable)"},
                }

            freshness_result = assess_freshness(freshness_data)

            # Bookings reconciliation: prefer the shared runtime snapshot so
            # health, scenario actuals, and the saved artifact all reconcile to
            # the same canonical monthly actuals series.
            q1_bookings, q1_source = self._q1_actual_bookings_from_snapshot(runtime_snapshot)
            if q1_bookings is not None:
                source_label = q1_source or "warehouse"
                bookings_result = {
                    "status": "ok",
                    "message": f"{source_label} Q1 bookings: ${q1_bookings:,.0f}",
                    "q1_bookings": q1_bookings,
                    "source": source_label,
                }
            else:
                cdw_bookings = self.owner.connector_gateway.try_cdw_bookings("Q1FY26")
                if cdw_bookings is not None:
                    bookings_result = {
                        "status": "ok",
                        "message": f"warehouse Q1 bookings: ${cdw_bookings:,.0f}",
                        "q1_bookings": cdw_bookings,
                        "source": "warehouse",
                    }
                else:
                    bookings_result = {"status": "ok", "message": "Skipped (warehouse bookings unavailable)"}

            observed = (
                getattr(runtime_snapshot, "observed_decay_curve", None)
                if runtime_snapshot is not None
                else None
            ) or self.owner._get_observed_decay_curve()
            observed_source = observed.get("source", "config")
            observed_curve = observed.get("curve", [])
            assumed_curve = self.owner._get_decay_curve()
            if observed_source in ("warehouse", "Salesforce") and any(v > 0 for v in observed_curve):
                from gtm_model.data_health import validate_decay_curve

                fallback_validation = validate_decay_curve(assumed_curve, observed_curve)
                sample = int(observed.get("sample", 0) or 0)
                minimum_sample = int(observed.get("minimum_sample", 0) or 0)
                sample_quality = str(observed.get("sample_quality", "") or "")
                decay_result = {
                    "status": "green" if sample >= minimum_sample else "yellow",
                    "message": f"Using {observed_source} observed close-timing curve (n={sample}).",
                    "source": observed_source,
                    "sample": sample,
                    "minimum_sample": minimum_sample,
                    "sample_quality": sample_quality or None,
                    "runtime_curve": observed_curve,
                    "fallback_validation": fallback_validation,
                }
                if observed_source == "warehouse":
                    decay_result["note"] = (
                        "Warehouse-derived per-deal timing is the active "
                        "runtime source."
                    )
                else:
                    decay_result["note"] = (
                        "Salesforce OpportunityFieldHistory is the active "
                        "runtime timing source. Config fallback validation "
                        "is recorded separately for hermetic paths."
                    )
            else:
                decay_result = {"status": "yellow", "message": "No observed close-timing data — using config assumption"}

            yaml_q1_pipeline = self.owner.targets.get("quarterly_targets", {}).get(
                "Q1FY26", {}
            ).get("pipeline_target", 0)
            cdw_weekly = self.owner.connector_gateway.try_weekly_targets_from_cdw("Q1FY26")
            if cdw_weekly:
                cdw_weekly_sum = sum(week.get("pipeline", 0) for week in cdw_weekly.values())
                from gtm_model.data_health import reconcile_targets

                targets_result = reconcile_targets(yaml_q1_pipeline, cdw_weekly_sum)
            else:
                targets_result = {"status": "aligned", "message": "Skipped (warehouse weekly targets unavailable)"}

            from gtm_model.data_health import _worst_status

            overall = _worst_status(
                freshness_result["status"],
                bookings_result["status"],
                decay_result["status"],
                targets_result["status"],
            )

            return {
                "freshness": freshness_result,
                "bookings_reconciliation": bookings_result,
                "decay_curve": decay_result,
                "targets": targets_result,
                "overall_status": overall,
            }
        except Exception as exc:
            logger.warning("Health checks failed: %s", exc)
            return {
                "overall_status": "yellow",
                "message": f"Health checks failed: {exc}",
            }

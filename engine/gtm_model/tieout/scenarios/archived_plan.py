"""Archived-plan computation helpers for Planning Tie-Out."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

from gtm_model.rate_defaults import get_default_funnel_rates


@dataclass
class TieoutArchivedPlanCalculator:
    """Compute config-driven and warehouse-driven archived-plan quarter payloads."""

    quarter_dates: dict[str, tuple]
    get_assumptions: Callable[[], dict]
    get_targets: Callable[[], dict]
    get_config_conversion_rates: Callable[[str, dict], dict]
    estimate_ae_selfgen_s0_weekly: Callable[[dict], int]
    rebalance_projection_pipeline_values: Callable[[dict, dict], dict]
    try_roster: Callable[[Optional[dict]], Optional[list[dict]]]
    get_observed_decay_curve: Callable[[], dict]
    get_s2_to_won_rate: Callable[[], float]
    summarize_source_breakdown: Callable[..., dict]
    try_cdw_bookings: Callable[[str], Optional[float]]

    def _quarter_actual_bookings_from_snapshot(
        self,
        quarter: str,
        runtime_snapshot: Any | None,
    ) -> float | None:
        """Sum monthly bookings from the shared runtime snapshot for a quarter."""
        if runtime_snapshot is None:
            return None

        actuals = getattr(runtime_snapshot, "monthly_actuals", None) or {}
        rows = actuals.get("bookings_by_month") or []
        start, end = self.quarter_dates[quarter]
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
        return total if matched else 0.0

    def _fallback_total_aes(
        self,
        quarter: str,
        ae_overrides: Optional[dict] = None,
        apply_overrides: bool = True,
    ) -> int:
        """Resolve fallback AE count from headcount targets."""
        targets = self.get_targets()
        total_aes = targets.get("headcount_targets", {}).get(quarter, {}).get("account_executives", 12)
        if apply_overrides and ae_overrides:
            if "total_aes" in ae_overrides:
                total_aes = ae_overrides["total_aes"]
            elif "add_aes" in ae_overrides:
                total_aes += ae_overrides["add_aes"]
        return total_aes

    def _resolve_capacity(
        self,
        quarter: str,
        ae_overrides: Optional[dict] = None,
        runtime_snapshot: Any | None = None,
    ) -> tuple[list[float], Optional[list[dict]]]:
        """Build the 12-month capacity vector and optional roster timeline."""
        start, _ = self.quarter_dates[quarter]
        roster = runtime_snapshot.roster if runtime_snapshot is not None and ae_overrides is None else self.try_roster(ae_overrides)
        if roster:
            from gtm_model.roster import project_capacity_timeline

            cap_timeline = project_capacity_timeline(
                roster=roster,
                start_month=start,
                months=12,
            )
            return [month["total"] for month in cap_timeline], cap_timeline

        assumptions = self.get_assumptions()
        seg_prod = assumptions.get("segment_productivity", {})
        ent_quota = seg_prod.get("enterprise", {}).get("annual_quota", 1_400_000)
        attainment = assumptions.get("capacity", {}).get("attainment_rate", 0.80)
        total_aes = self._fallback_total_aes(quarter, ae_overrides, apply_overrides=True)
        monthly_cap = total_aes * (ent_quota / 12) * attainment
        return [monthly_cap] * 12, None

    @staticmethod
    def _headcount_from_timeline(cap_timeline: list[dict]) -> tuple[int, int, float]:
        """Extract current headcount state from a roster timeline.

        Uses the latest month in the timeline (not the first) to reflect
        the most current AE count. For a 3-month quarter, using the first
        month understates headcount when hires join mid-quarter.
        """
        from datetime import date as _date

        # Find the month closest to today, or use the last month
        today = _date.today()
        best = cap_timeline[-1]  # default to last month
        for entry in cap_timeline:
            entry_month = entry.get("month")
            if entry_month and hasattr(entry_month, "year"):
                if entry_month.year == today.year and entry_month.month == today.month:
                    best = entry
                    break
                if entry_month <= today:
                    best = entry  # keep updating to the most recent past month

        ramped_aes = best.get("ramped_count", 0)
        total_aes_count = best.get("total_count", 0)
        blended = ramped_aes / max(total_aes_count, 1)
        return ramped_aes, total_aes_count, blended

    def _project_bookings(
        self,
        monthly_creation: list[float],
        monthly_capacity: list[float],
        overflow_mode: str,
        runtime_snapshot: Any | None = None,
    ) -> tuple[dict, float]:
        """Run the cohort model on a quarter's monthly creation profile."""
        from gtm_model.cohort_model import project_bookings

        if runtime_snapshot is not None:
            decay_curve = list((runtime_snapshot.observed_decay_curve or {}).get("curve", []) or [])
            win_rate = runtime_snapshot.s2_to_won_rate
        else:
            decay_curve = self.get_observed_decay_curve()["curve"]
            win_rate = self.get_s2_to_won_rate()
        haircutted_creation = [value * win_rate for value in monthly_creation]

        bookings_result = project_bookings(
            monthly_creation=haircutted_creation,
            decay_curve=decay_curve,
            monthly_capacity=monthly_capacity,
            overflow=overflow_mode,
        )
        capped = bookings_result["capped"]
        sales_led = sum(capped[:min(3, len(capped))])
        return bookings_result, sales_led

    def _quarterly_plg_target(self, quarter: str) -> float:
        """Resolve PLG target for the quarter."""
        assumptions = self.get_assumptions()
        return assumptions.get("self_serve", {}).get("quarterly_targets", {}).get(quarter, 0)

    def config_driven(
        self,
        quarter: str,
        td: dict,
        overflow_mode: str = "push",
        conversion_overrides: Optional[dict] = None,
        ae_overrides: Optional[dict] = None,
        monthly_creation_override: Optional[list] = None,
        plg_override: Optional[float] = None,
        runtime_snapshot: Any | None = None,
    ) -> dict:
        """Compute the archived plan path using only config data."""
        from gtm_model.funnel_engine import compute_three_source_pipeline

        assumptions = self.get_assumptions()
        funnel_defaults = get_default_funnel_rates()
        funnel_cfg = assumptions.get("funnel", {})
        rates = self.get_config_conversion_rates(quarter, td)
        if conversion_overrides:
            for key in ("mql_to_s0", "s0_to_s1", "s1_to_s2"):
                if key in conversion_overrides:
                    rates[key] = conversion_overrides[key]

        if monthly_creation_override is not None:
            if isinstance(monthly_creation_override, dict):
                projection = copy.deepcopy(monthly_creation_override)
                monthly_creation = list(projection.get("total_monthly_creation", []) or [])
            else:
                monthly_creation = list(monthly_creation_override)
                projection = {
                    "total_monthly_creation": monthly_creation,
                    "total_weekly_s0_count": 0,
                    "total_weekly_s1_count": 0,
                    "total_weekly_s2_count": 0,
                    "_trajectory_override": True,
                }

            while len(monthly_creation) < 3:
                monthly_creation.append(0.0)
            monthly_creation = monthly_creation[:3]
            projection["total_monthly_creation"] = monthly_creation
            projection.setdefault("total_weekly_s0_count", 0)
            projection.setdefault("total_weekly_s1_count", 0)
            projection.setdefault("total_weekly_s2_count", 0)
            projection["_trajectory_override"] = True

            for stream_key in ("marketing_sdr", "ae_selfgen", "plg"):
                if stream_key not in projection:
                    continue
                stream = projection[stream_key] or {}
                monthly_vals = list(stream.get("monthly_creation", []) or [])
                while len(monthly_vals) < 3:
                    monthly_vals.append(0.0)
                stream["monthly_creation"] = monthly_vals[:3]
                projection[stream_key] = stream
            # Prefer trajectory MQL projection over top-down plan target.
            # When the override carries trajectory data, marketing_sdr.weekly_input
            # reflects the actual modeled MQL rate (e.g. ~56/wk) rather than the
            # top-down plan target (e.g. 396/wk).
            traj_mql = (projection.get("marketing_sdr") or {}).get("weekly_input")
            if traj_mql and traj_mql > 0:
                mql_weekly = int(traj_mql)
            else:
                mql_weekly = td["mqls_weekly"] if td["mqls_weekly"] > 0 else 264
        else:
            mql_weekly = td["mqls_weekly"] if td["mqls_weekly"] > 0 else 264
            projection = compute_three_source_pipeline(
                marketing_sdr_mqls_weekly=mql_weekly,
                ae_selfgen_s0_weekly=self.estimate_ae_selfgen_s0_weekly(td),
                plg_signups_weekly=50,
                rates=rates,
                weeks=td.get("weeks_in_quarter", 13),
                avg_deal_size=funnel_cfg.get("avg_acv", 300_000),
            )
            projection = self.rebalance_projection_pipeline_values(projection, td)
            monthly_creation = projection["total_monthly_creation"]

        monthly_capacity, cap_timeline = self._resolve_capacity(
            quarter,
            ae_overrides,
            runtime_snapshot=runtime_snapshot,
        )
        bookings_result, sales_led = self._project_bookings(
            monthly_creation=monthly_creation,
            monthly_capacity=monthly_capacity,
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        )

        if plg_override is not None:
            quarterly_plg = plg_override
        else:
            quarterly_plg = self._quarterly_plg_target(quarter)

        if cap_timeline and len(cap_timeline) >= 1:
            ramped_aes, total_aes_count, blended = self._headcount_from_timeline(cap_timeline)
        else:
            total_aes_count = self._fallback_total_aes(quarter, ae_overrides, apply_overrides=True)
            ramped_aes = total_aes_count
            blended = 1.0

        mql_to_s0 = rates["mql_to_s0"]
        s0_to_s1 = rates["s0_to_s1"]
        s1_to_s2 = rates["s1_to_s2"]
        bu_s0 = int(projection.get("total_weekly_s0_count", mql_weekly * mql_to_s0))
        bu_s1 = int(projection.get("total_weekly_s1_count", bu_s0 * s0_to_s1))
        bu_s2 = int(projection.get("total_weekly_s2_count", bu_s1 * s1_to_s2))

        conv_rates = {
            key: {
                "blended": {
                    "rate": rates[key],
                    "n": 0,
                    "source": "plan",
                }
            }
            for key in ("mql_to_s0", "s0_to_s1", "s1_to_s2")
        }

        funnel_tieout = {
            metric: {
                "plan": td[metric],
                "actual": 0,
                "delta": -td[metric],
            }
            for metric in ("mqls_weekly", "s0_weekly", "s1_weekly", "s2_weekly")
        }

        return {
            "sales_led": sales_led,
            "plg": quarterly_plg,
            "expansion": 0.0,
            "total": sales_led + quarterly_plg,
            "ramped_aes": ramped_aes,
            "total_aes": total_aes_count,
            "blended_ramp": blended,
            "mqls_projected": mql_weekly,
            "s0_projected": bu_s0,
            "s1_projected": bu_s1,
            "s2_projected": bu_s2,
            "conversion_rates": conv_rates,
            "funnel_tieout": funnel_tieout,
            "source_breakdown": self.summarize_source_breakdown(projection, mode="config"),
            "actual_bookings": 0.0,
            "actual_pipeline": 0.0,
            "actual_mqls": 0,
            "actual_s0": 0,
            "actual_s1": 0,
            "actual_s2": 0,
            "monthly_creation": monthly_creation,
            "overflow_amounts": bookings_result.get("overflow_amounts", []),
        }

    def cdw(
        self,
        quarter: str,
        td: dict,
        funnel_result: dict,
        overflow_mode: str = "push",
        ae_overrides: Optional[dict] = None,
        runtime_snapshot: Any | None = None,
    ) -> dict:
        """Compute the archived plan path from warehouse funnel data."""
        funnel_defaults = get_default_funnel_rates()
        projections = funnel_result.get("projections", {})
        monthly_creation = projections.get("total_monthly_creation", [0, 0, 0])
        monthly_capacity, cap_timeline = self._resolve_capacity(
            quarter,
            ae_overrides,
            runtime_snapshot=runtime_snapshot,
        )
        bookings_result, sales_led = self._project_bookings(
            monthly_creation=monthly_creation,
            monthly_capacity=monthly_capacity,
            overflow_mode=overflow_mode,
            runtime_snapshot=runtime_snapshot,
        )

        quarterly_plg = self._quarterly_plg_target(quarter)

        if cap_timeline and len(cap_timeline) >= 1:
            ramped_aes, total_aes_count, blended = self._headcount_from_timeline(cap_timeline)
        else:
            total_aes_count = self._fallback_total_aes(quarter, ae_overrides, apply_overrides=False)
            ramped_aes = total_aes_count
            blended = 1.0

        actuals = funnel_result.get("actuals", {})
        volumes = actuals.get("funnel_volumes", {})

        def _avg_weekly(series_key: str) -> int:
            series = volumes.get(series_key, [])
            if not series:
                return 0
            return int(sum(week.get("count", 0) for week in series) / max(len(series), 1))

        actual_mqls = _avg_weekly("mqls_weekly")
        actual_s0 = _avg_weekly("s0_weekly")
        actual_s1 = _avg_weekly("s1_weekly")
        actual_s2 = _avg_weekly("s2_weekly")
        snapshot_actual_bookings = self._quarter_actual_bookings_from_snapshot(
            quarter,
            runtime_snapshot,
        )
        actual_bookings = (
            float(snapshot_actual_bookings)
            if snapshot_actual_bookings is not None
            else float(self.try_cdw_bookings(quarter) or 0.0)
        )

        resolved_rates = funnel_result.get("rates", {})
        conv_rates = {}
        for stage_key in ("mql_to_s0", "s0_to_s1", "s1_to_s2"):
            stage_rates = {}
            for stream in ("marketing_sdr", "ae_selfgen", "plg"):
                stream_data = resolved_rates.get(stream, {}).get(stage_key, {})
                if stream_data:
                    stage_rates[stream] = {
                        "rate": stream_data.get("rate", 0),
                        "n": stream_data.get("n", 0),
                        "source": stream_data.get("source", "plan"),
                    }
            conv_rates[stage_key] = stage_rates

        funnel_tieout = {
            "mqls_weekly": {
                "plan": td["mqls_weekly"],
                "actual": actual_mqls,
                "delta": actual_mqls - td["mqls_weekly"],
            },
            "s0_weekly": {
                "plan": td["s0_weekly"],
                "actual": actual_s0,
                "delta": actual_s0 - td["s0_weekly"],
            },
            "s1_weekly": {
                "plan": td["s1_weekly"],
                "actual": actual_s1,
                "delta": actual_s1 - td["s1_weekly"],
            },
            "s2_weekly": {
                "plan": td["s2_weekly"],
                "actual": actual_s2,
                "delta": actual_s2 - td["s2_weekly"],
            },
        }

        mkt_rates = resolved_rates.get("marketing_sdr", {})
        mql_to_s0_rate = mkt_rates.get("mql_to_s0", {}).get("rate", funnel_defaults["mql_to_s0"])
        s0_to_s1_rate = mkt_rates.get("s0_to_s1", {}).get("rate", funnel_defaults["s0_to_s1"])
        s1_to_s2_rate = mkt_rates.get("s1_to_s2", {}).get("rate", funnel_defaults["s1_to_s2"])

        # Prefer actual MQLs, then projection-derived MQL rate, then plan target.
        proj_mql = (projections.get("marketing_sdr") or {}).get("weekly_input")
        if actual_mqls > 0:
            mql_weekly = actual_mqls
        elif proj_mql and proj_mql > 0:
            mql_weekly = int(proj_mql)
        else:
            mql_weekly = td["mqls_weekly"]
        bu_s0 = int(projections.get("total_weekly_s0_count", mql_weekly * mql_to_s0_rate))
        bu_s1 = int(projections.get("total_weekly_s1_count", bu_s0 * s0_to_s1_rate))
        bu_s2 = int(projections.get("total_weekly_s2_count", bu_s1 * s1_to_s2_rate))

        source_breakdown = self.summarize_source_breakdown(
            projections,
            mode="cdw",
            actual_streams=funnel_result.get("streams", {}),
        )
        actual_pipeline_total = sum(
            float(stream.get("actual_pipeline", 0.0) or 0.0)
            for stream in (source_breakdown.get("streams") or {}).values()
        )

        return {
            "sales_led": sales_led,
            "plg": quarterly_plg,
            "expansion": 0.0,
            "total": sales_led + quarterly_plg,
            "ramped_aes": ramped_aes,
            "total_aes": total_aes_count,
            "blended_ramp": blended,
            "mqls_projected": mql_weekly,
            "s0_projected": bu_s0,
            "s1_projected": bu_s1,
            "s2_projected": bu_s2,
            "conversion_rates": conv_rates,
            "funnel_tieout": funnel_tieout,
            "source_breakdown": source_breakdown,
            "actual_bookings": actual_bookings,
            "actual_pipeline": actual_pipeline_total,
            "actual_mqls": actual_mqls,
            "actual_s0": actual_s0,
            "actual_s1": actual_s1,
            "actual_s2": actual_s2,
            "monthly_creation": monthly_creation,
            "overflow_amounts": bookings_result.get("overflow_amounts", []),
        }

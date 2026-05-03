"""Weekly target derivation helpers for Planning Tie-Out."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class TieoutWeeklyTargetDeriver:
    """Resolve configured and runtime-derived weekly targets."""

    quarters: list[str]
    get_targets: Callable[[], dict]
    get_assumptions: Callable[[], dict]
    get_runtime_funnel_rates: Callable[[], dict[str, float]]
    get_td_quarter_cb: Callable[[str], dict]
    get_source_mix_shares_cb: Callable[[str], dict]
    allocate_integer_mix_cb: Callable[[int, list[tuple[str, float]]], dict]
    resolve_s0_source_mix_cb: Callable[[str, dict], dict]
    get_config_conversion_rates_cb: Callable[[str, dict], dict]

    def default_target_provenance(self, quarter: str, wt: dict) -> dict:
        """Return a default provenance payload for a configured weekly target set."""
        if not wt:
            return {
                "status": "missing_weekly_targets",
                "label": f"{quarter} weekly targets missing",
                "method": "runtime_derivation_required",
                "source": "targets.yaml",
                "approved": False,
            }

        return {
            "status": "explicit_configured_targets",
            "label": f"{quarter} configured weekly targets",
            "method": "configured_weekly_plan",
            "source": "targets.yaml",
            "approved": True,
        }

    def annotate_target_coherence(self, td: dict, provenance: dict) -> dict:
        """Attach reviewer-facing target-coherence diagnostics to weekly-target provenance."""
        annotated = copy.deepcopy(provenance or {})
        weeks = float(td.get("weeks_in_quarter", 13) or 13)
        s2_weekly = float(td.get("s2_weekly", 0.0) or 0.0)
        pipeline_target = float(td.get("pipeline_target", 0.0) or 0.0)
        configured_pipeline_total = float(td.get("s1_pipeline_total", 0.0) or 0.0)
        avg_acv = float((self.get_assumptions().get("funnel", {}) or {}).get("avg_acv", 0.0) or 0.0)

        if weeks <= 0 or s2_weekly <= 0 or avg_acv <= 0:
            return annotated

        implied_raw_s2_pipeline = s2_weekly * weeks * avg_acv
        comparison_total = configured_pipeline_total if configured_pipeline_total > 0 else pipeline_target
        if comparison_total <= 0:
            return annotated

        ratio = implied_raw_s2_pipeline / comparison_total if comparison_total > 0 else 0.0
        if ratio <= 1.25:
            coherence_status = "aligned"
        elif ratio <= 1.75:
            coherence_status = "stretched"
        else:
            coherence_status = "divergent"

        annotated["coherence_status"] = coherence_status
        annotated["implied_raw_s2_pipeline"] = implied_raw_s2_pipeline
        annotated["pipeline_target_ratio"] = (
            (configured_pipeline_total / pipeline_target)
            if configured_pipeline_total > 0 and pipeline_target > 0
            else None
        )
        annotated["activity_to_config_ratio"] = ratio
        annotated["configured_pipeline_total"] = comparison_total
        annotated["configured_pipeline_basis"] = (
            "s1_pipeline_creation" if configured_pipeline_total > 0 else "quarter_pipeline_target"
        )
        annotated["coherence_note"] = (
            f"Implied raw S2 creation is {implied_raw_s2_pipeline:,.0f} "
            f"against configured {'S1 pipeline' if configured_pipeline_total > 0 else 'pipeline target'} "
            f"{comparison_total:,.0f} ({ratio:.1f}x)."
        )
        return annotated

    @staticmethod
    def normalize_s1_pipeline_by_source(wt: dict) -> dict:
        """Normalize configured by-source S1 pipeline values to quarterly dollars."""
        s1_cfg = (wt.get("s1_pipeline_creation", {}) or {})
        by_source = dict((s1_cfg.get("by_source", {}) or {}))
        if not by_source:
            return {}

        quarter_total = float(s1_cfg.get("total_quarterly", 0.0) or 0.0)
        raw_total = sum(float(value or 0.0) for value in by_source.values())
        if raw_total <= 0 or quarter_total <= 0:
            return {key: float(value or 0.0) for key, value in by_source.items()}

        if abs(raw_total - quarter_total) <= max(quarter_total * 0.05, 1.0):
            scale = 1.0
        else:
            scale = quarter_total / raw_total

        return {
            key: float(value or 0.0) * scale
            for key, value in by_source.items()
        }

    def get_td_quarter(self, quarter: str) -> dict:
        """Extract top-down targets for a quarter."""
        targets = self.get_targets()
        qt = targets.get("quarterly_targets", {}).get(quarter, {})
        ht = targets.get("headcount_targets", {}).get(quarter, {})
        wt = targets.get(f"weekly_targets_{quarter}", {})
        activity = wt.get("activity", {})
        target_provenance = copy.deepcopy(
            wt.get("target_provenance") or self.default_target_provenance(quarter, wt)
        )
        s1_pipeline_by_source = self.normalize_s1_pipeline_by_source(wt)

        td = {
            "bookings": qt.get("bookings_target", 0),
            "plg": qt.get("plg_target", 0),
            "expansion": qt.get("expansion_target", 0),
            "total_net_new": qt.get("total_net_new", 0),
            "ending_arr": qt.get("ending_arr", 0),
            "pipeline_target": qt.get("pipeline_target", 0),
            "aes": ht.get("account_executives", 0),
            "ses": ht.get("sales_engineers", 0),
            "sdrs": ht.get("sdrs", 0),
            "total_gtm": ht.get("total_gtm", 0),
            "weeks_in_quarter": wt.get("weeks_in_quarter", 13),
            "mqls_weekly": activity.get("mqls_weekly", 0),
            "s0_weekly": activity.get("s0_booked_weekly", 0),
            "s1_weekly": activity.get("s1_held_weekly", 0),
            "s2_weekly": activity.get("s2_created_weekly", 0),
            "s0_by_source": activity.get("s0_by_source", {}),
            "conversion": wt.get("conversion", {}),
            "s1_pipeline_total": ((wt.get("s1_pipeline_creation", {}) or {}).get("total_quarterly", 0)),
            "s1_pipeline_by_source": s1_pipeline_by_source,
            "s1_pipeline_monthly": list(
                ((wt.get("s1_pipeline_creation", {}) or {}).get("monthly_breakdown", {}) or {}).values()
            ),
            "target_provenance": target_provenance,
        }
        td["s0_by_source"] = self.resolve_s0_source_mix_cb(quarter, td)
        td["target_provenance"] = self.annotate_target_coherence(td, td["target_provenance"])
        return td

    def get_source_mix_shares(self, quarter: str) -> dict:
        """Return normalized source shares for marketing, SDR, and AE motions."""
        targets = self.get_targets()
        wt = targets.get(f"weekly_targets_{quarter}", {}) or {}
        by_source = (wt.get("s1_pipeline_creation", {}) or {}).get("by_source", {}) or {}
        if by_source:
            marketing = float(by_source.get("marketing_sourced", 0.0) or 0.0)
            sdr = float(by_source.get("sdr_sourced", 0.0) or 0.0)
            ae = float(by_source.get("ae_sourced", 0.0) or 0.0)
        else:
            source_mix = targets.get("source_mix_planned", {}) or {}
            marketing = float(source_mix.get("marketing_sourced", 0.0) or 0.0)
            sdr = float(source_mix.get("sdr_sourced", 0.0) or 0.0)
            ae = float(source_mix.get("ae_sourced", 0.0) or 0.0)

        total = marketing + sdr + ae
        if total <= 0:
            marketing, sdr, ae = 0.335, 0.315, 0.350
            total = 1.0

        marketing /= total
        sdr /= total
        ae /= total
        return {
            "marketing": marketing,
            "sdr": sdr,
            "ae": ae,
            "marketing_plus_sdr": marketing + sdr,
        }

    @staticmethod
    def allocate_integer_mix(total_count: int, allocations: list[tuple[str, float]]) -> dict:
        """Convert fractional source allocations into integer counts that sum exactly."""
        if total_count <= 0:
            return {key: 0 for key, _ in allocations}

        floor_values = {}
        remainders = []
        assigned = 0
        for key, raw_value in allocations:
            floored = int(raw_value)
            floor_values[key] = floored
            assigned += floored
            remainders.append((raw_value - floored, key))

        remainder = total_count - assigned
        for _, key in sorted(remainders, reverse=True)[:max(remainder, 0)]:
            floor_values[key] += 1

        return floor_values

    def resolve_s0_source_mix(self, quarter: str, td: dict) -> dict:
        """Return explicit S0 source splits, deriving them from source mix when absent."""
        explicit = td.get("s0_by_source") or {}
        if explicit:
            return explicit

        total_s0 = int(td.get("s0_weekly", 0) or 0)
        shares = self.get_source_mix_shares(quarter)
        allocations = self.allocate_integer_mix(
            total_s0,
            [
                ("marketing", total_s0 * shares["marketing"]),
                ("sdr", total_s0 * shares["sdr"]),
                ("ae", total_s0 * shares["ae"]),
            ],
        )
        return allocations

    def estimate_ae_selfgen_s0_weekly(self, td: dict) -> int:
        """Estimate direct AE-created S0 volume for the config funnel model."""
        s0_by_source = td.get("s0_by_source") or {}
        explicit_ae_s0 = sum(
            int(s0_by_source.get(key, 0))
            for key in ("ae", "ae_sourced", "leadership", "se", "unknown")
        )
        if explicit_ae_s0 > 0:
            return explicit_ae_s0

        targets = self.get_targets()
        planned_ae_share = (targets.get("source_mix_planned", {}) or {}).get("ae_sourced")
        if planned_ae_share is not None and td.get("s0_weekly", 0) > 0:
            return max(int(td["s0_weekly"] * planned_ae_share), 1)

        source_mix = self.get_assumptions().get("funnel", {}).get("source_mix", {})
        direct_share = sum(
            float(source_mix.get(key, 0.0))
            for key in ("ae_sourced", "leadership_sourced", "se_sourced", "unknown")
        )
        if direct_share > 0 and td.get("s0_weekly", 0) > 0:
            return max(int(td["s0_weekly"] * direct_share), 1)

        if td.get("s0_weekly", 0) > 0:
            return max(int(td["s0_weekly"] * 0.35), 1)

        return 1

    def get_config_conversion_rates(self, quarter: str, td: dict) -> dict:
        """Resolve plan conversion rates for config-mode modeling."""
        rates = self.get_runtime_funnel_rates()
        conversion = td.get("conversion") or {}
        if not conversion:
            quarter_idx = self.quarters.index(quarter)
            for prior_quarter in reversed(self.quarters[:quarter_idx]):
                prior_td = self.get_td_quarter_cb(prior_quarter)
                if prior_td.get("conversion"):
                    conversion = prior_td["conversion"]
                    break

        for key in ("mql_to_s0", "s0_to_s1", "s1_to_s2"):
            if key in conversion:
                rates[key] = conversion[key]

        return rates

    def latest_explicit_weekly_target_quarter(self, quarter: str) -> Optional[str]:
        """Return the latest earlier quarter with explicit weekly targets."""
        targets = self.get_targets()
        quarter_idx = self.quarters.index(quarter)
        for prior_quarter in reversed(self.quarters[:quarter_idx]):
            prior_td = self.get_td_quarter_cb(prior_quarter)
            prior_wt = targets.get(f"weekly_targets_{prior_quarter}", {}) or {}
            s1_pipeline_total = (prior_wt.get("s1_pipeline_creation", {}) or {}).get("total_quarterly", 0)
            if prior_td.get("s1_weekly", 0) > 0 and s1_pipeline_total:
                return prior_quarter
        return None

    def derive_weekly_targets_from_pipeline_driver_tree(self, quarter: str, td: dict) -> Optional[dict]:
        """Derive future-quarter weekly targets from pipeline coverage and stage drivers."""
        ref_quarter = self.latest_explicit_weekly_target_quarter(quarter)
        if ref_quarter is None:
            return None

        ref_td = self.get_td_quarter_cb(ref_quarter)
        targets = self.get_targets()
        ref_wt = targets.get(f"weekly_targets_{ref_quarter}", {}) or {}
        ref_s1_pipeline = float((ref_wt.get("s1_pipeline_creation", {}) or {}).get("total_quarterly", 0.0) or 0.0)
        ref_pipeline_target = float(ref_td.get("pipeline_target", 0.0) or 0.0)
        ref_s1_weekly = float(ref_td.get("s1_weekly", 0.0) or 0.0)
        weeks = int(td.get("weeks_in_quarter", 13) or 13)
        pipeline_target = float(td.get("pipeline_target", 0.0) or 0.0)
        if ref_s1_pipeline <= 0 or ref_pipeline_target <= 0 or ref_s1_weekly <= 0 or pipeline_target <= 0:
            return None

        rates = self.get_config_conversion_rates_cb(quarter, td)
        s0_to_s1 = float(rates.get("s0_to_s1", 0.0) or 0.0)
        s1_to_s2 = float(rates.get("s1_to_s2", 0.0) or 0.0)
        mql_to_s0 = float(rates.get("mql_to_s0", 0.0) or 0.0)
        if s0_to_s1 <= 0 or s1_to_s2 <= 0 or mql_to_s0 <= 0:
            return None

        s1_pipeline_intensity = ref_s1_pipeline / ref_pipeline_target
        ref_s1_pipeline_weekly = ref_s1_pipeline / max(float(ref_td.get("weeks_in_quarter", 13) or 13), 1.0)
        dollars_per_s1 = ref_s1_pipeline_weekly / ref_s1_weekly
        if dollars_per_s1 <= 0:
            return None

        derived_s1_pipeline_total = pipeline_target * s1_pipeline_intensity
        derived_s1_weekly = (derived_s1_pipeline_total / weeks) / dollars_per_s1
        derived_s0_weekly = derived_s1_weekly / s0_to_s1
        derived_s2_weekly = derived_s1_weekly * s1_to_s2

        shares = self.get_source_mix_shares_cb(ref_quarter)
        total_s0_int = max(int(round(derived_s0_weekly)), 0)
        s0_by_source = self.allocate_integer_mix_cb(
            total_s0_int,
            [
                ("marketing", total_s0_int * shares["marketing"]),
                ("sdr", total_s0_int * shares["sdr"]),
                ("ae", total_s0_int * shares["ae"]),
            ],
        )
        marketing_sdr_s0 = s0_by_source["marketing"] + s0_by_source["sdr"]
        derived_mqls_weekly = marketing_sdr_s0 / mql_to_s0
        derived_s1_pipeline_by_source = {
            "marketing_sourced": derived_s1_pipeline_total * shares["marketing"],
            "sdr_sourced": derived_s1_pipeline_total * shares["sdr"],
            "ae_sourced": derived_s1_pipeline_total * shares["ae"],
        }
        ref_monthly = list(ref_td.get("s1_pipeline_monthly", []) or [])
        if ref_monthly and sum(float(value or 0.0) for value in ref_monthly) > 0:
            ref_total = sum(float(value or 0.0) for value in ref_monthly)
            derived_s1_pipeline_monthly = [
                derived_s1_pipeline_total * (float(value or 0.0) / ref_total)
                for value in ref_monthly
            ]
        else:
            derived_s1_pipeline_monthly = []

        derived = dict(td)
        derived["mqls_weekly"] = max(int(round(derived_mqls_weekly)), 0)
        derived["s0_weekly"] = total_s0_int
        derived["s1_weekly"] = max(int(round(derived_s1_weekly)), 0)
        derived["s2_weekly"] = max(int(round(derived_s2_weekly)), 0)
        derived["s0_by_source"] = s0_by_source
        derived["s1_pipeline_total"] = derived_s1_pipeline_total
        derived["s1_pipeline_by_source"] = derived_s1_pipeline_by_source
        derived["s1_pipeline_monthly"] = derived_s1_pipeline_monthly
        derived["target_provenance"] = {
            "status": "runtime_derived_targets",
            "label": f"{quarter} runtime-derived weekly targets",
            "method": "pipeline_driver_tree",
            "source": "planning_tieout.py",
            "reference_quarter": ref_quarter,
            "approved": False,
            "notes": "Derived at runtime from pipeline coverage, source mix, and recent stage relationships.",
        }
        return derived

    def derive_weekly_targets(self, quarter: str, td: dict) -> tuple[dict, bool]:
        """Derive weekly targets when later-quarter explicit targets are absent."""
        has_weekly = td["mqls_weekly"] > 0
        if has_weekly:
            return td, False

        derived_from_pipeline = self.derive_weekly_targets_from_pipeline_driver_tree(quarter, td)
        if derived_from_pipeline is not None:
            return derived_from_pipeline, True

        ref_quarter = "Q2FY26"
        ref_td = self.get_td_quarter_cb(ref_quarter)
        ref_bookings = ref_td["bookings"]
        if ref_bookings <= 0 or ref_td["mqls_weekly"] <= 0:
            return td, False

        this_bookings = td["bookings"]
        scale = this_bookings / ref_bookings if ref_bookings > 0 else 1.0

        derived = dict(td)
        derived["mqls_weekly"] = int(ref_td["mqls_weekly"] * scale)
        derived["s0_weekly"] = int(ref_td["s0_weekly"] * scale)
        derived["s1_weekly"] = int(ref_td["s1_weekly"] * scale)
        derived["s2_weekly"] = int(ref_td["s2_weekly"] * scale)
        derived["s0_by_source"] = self.resolve_s0_source_mix_cb(quarter, derived)
        ref_s1_pipeline_total = float(ref_td.get("s1_pipeline_total", 0.0) or 0.0)
        if ref_s1_pipeline_total > 0:
            scaled_s1_pipeline_total = ref_s1_pipeline_total * scale
            shares = self.get_source_mix_shares_cb(ref_quarter)
            derived["s1_pipeline_total"] = scaled_s1_pipeline_total
            derived["s1_pipeline_by_source"] = {
                "marketing_sourced": scaled_s1_pipeline_total * shares["marketing"],
                "sdr_sourced": scaled_s1_pipeline_total * shares["sdr"],
                "ae_sourced": scaled_s1_pipeline_total * shares["ae"],
            }
            ref_monthly = list(ref_td.get("s1_pipeline_monthly", []) or [])
            if ref_monthly and sum(float(value or 0.0) for value in ref_monthly) > 0:
                ref_total = sum(float(value or 0.0) for value in ref_monthly)
                derived["s1_pipeline_monthly"] = [
                    scaled_s1_pipeline_total * (float(value or 0.0) / ref_total)
                    for value in ref_monthly
                ]
        derived["target_provenance"] = {
            "status": "runtime_derived_targets",
            "label": f"{quarter} runtime-derived weekly targets",
            "method": "bookings_scale_fallback",
            "source": "planning_tieout.py",
            "reference_quarter": ref_quarter,
            "approved": False,
            "notes": "Fallback derivation scaled from the latest explicit weekly plan by bookings target.",
        }
        return derived, True

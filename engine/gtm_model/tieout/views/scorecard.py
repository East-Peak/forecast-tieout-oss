"""Semantic scorecard helpers for Planning Tie-Out review."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from gtm_model.tieout.types import ScenarioResult, TieoutResult


def _primary_scenario(result: TieoutResult) -> ScenarioResult:
    return getattr(result, "primary_scenario", None) or getattr(result, "trajectory", None) or result.base


def _archived_plan(result: TieoutResult) -> ScenarioResult:
    return getattr(result, "archived_plan", None) or result.base


def _trajectory_rollforward(result: TieoutResult) -> dict:
    """Return the active trajectory rollforward provenance payload."""
    primary = _primary_scenario(result)
    return (
        getattr(getattr(result, "trajectory", None), "monthly_rollforward_provenance", {}) or {}
    ) or (primary.monthly_rollforward_provenance or {})


def _format_money(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(float(value or 0.0))
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{sign}${value / 1_000:.0f}K"
    return f"{sign}${value:,.0f}"


def _quarter_map(scenario: ScenarioResult) -> dict[str, Any]:
    return {quarter.quarter: quarter for quarter in scenario.quarters}


def _build_ae_ramp_comparison(trajectory_rollforward: dict) -> list[dict]:
    """Return observed-versus-config AE ramp rows from trajectory provenance."""
    from gtm_model.roster import _get_ramp_curve

    observed = trajectory_rollforward.get("ae_ramp_curve", {}) or {}
    sample_sizes = trajectory_rollforward.get("ae_ramp_curve_sample_sizes", {}) or {}

    segments = sorted(set(observed) | {"enterprise"})
    rows: list[dict] = []
    for segment in segments:
        plan_curve = _get_ramp_curve(segment)
        observed_curve = observed.get(segment, {}) or {}
        segment_samples = sample_sizes.get(segment, {}) or {}
        max_bucket = max(plan_curve.keys()) if plan_curve else 0
        for bucket in range(1, max_bucket + 1):
            rows.append(
                {
                    "segment": segment,
                    "month": bucket,
                    "plan_ramp": float(plan_curve.get(bucket, 0.0) or 0.0),
                    "observed_ramp": observed_curve.get(f"month_{bucket}"),
                    "sample_ae_months": segment_samples.get(f"month_{bucket}", 0.0),
                }
            )
    return rows


def _get_operating_case_quota(segment: str, plan_quota: float, assumptions: dict) -> float:
    """Return the policy quota basis to use for the operating case."""
    calibration_cfg = (assumptions or {}).get("planning_calibration", {}) or {}
    raw = (
        (calibration_cfg.get("operating_case_quota") or {}).get(segment)
        or (calibration_cfg.get("operating_case_quota") or {}).get("default")
    )
    if raw is not None:
        return float(raw)
    return float(plan_quota)


def build_capacity_realism_benchmark_from_rollforward(tieout: Any, trajectory_rollforward: dict) -> dict:
    """Compare plan AE capacity assumptions against active trajectory reality."""
    from gtm_model.roster import _get_segment_attainment, _get_segment_quota

    observed_ae_productivity = float(trajectory_rollforward.get("observed_ae_productivity", 0.0) or 0.0)
    runtime_rates = tieout.runtime.describe_runtime_funnel_rates()
    s2_to_won = tieout._get_rolling_s2_to_won_rate()
    avg_deal_size = float(tieout.assumptions.get("funnel", {}).get("avg_acv", 300_000) or 300_000.0)

    try:
        roster = tieout._try_roster() or []
    except Exception:
        roster = []

    active_segments = [
        str(rep.get("segment") or "enterprise")
        for rep in roster
        if str(rep.get("tier") or "active").strip().lower() == "active"
    ]
    segment_counts = Counter(active_segments)
    active_total = sum(segment_counts.values())

    if active_total <= 0:
        segment_counts = Counter({"enterprise": 1})
        active_total = 1

    segment_mix = {
        segment: count / active_total
        for segment, count in sorted(segment_counts.items())
    }
    weighted_plan_quota = sum(
        mix * float(_get_segment_quota(segment))
        for segment, mix in segment_mix.items()
    )
    weighted_operating_case_quota = sum(
        mix * _get_operating_case_quota(segment, float(_get_segment_quota(segment)), tieout.assumptions)
        for segment, mix in segment_mix.items()
    )
    weighted_plan_attainment = sum(
        mix * float(_get_segment_attainment(segment))
        for segment, mix in segment_mix.items()
    )
    plan_capacity_per_ae = weighted_plan_quota * weighted_plan_attainment

    s0_to_s1 = float(runtime_rates.get("s0_to_s1", {}).get("value", 0.0) or 0.0)
    s1_to_s2 = float(runtime_rates.get("s1_to_s2", {}).get("value", 0.0) or 0.0)
    s2_to_won_rate = float(s2_to_won.get("rate", 0.0) or 0.0)

    observed_s2_pipeline_per_ae = observed_ae_productivity * s0_to_s1 * s1_to_s2 * avg_deal_size * 12.0
    observed_bookings_per_ae = observed_s2_pipeline_per_ae * s2_to_won_rate
    observed_s1_deals_per_ae_month = observed_ae_productivity * s0_to_s1
    observed_s2_deals_per_ae_month = observed_s1_deals_per_ae_month * s1_to_s2
    observed_won_deals_per_ae_month = observed_s2_deals_per_ae_month * s2_to_won_rate
    implied_attainment = (
        observed_bookings_per_ae / weighted_plan_quota
        if weighted_plan_quota > 0
        else None
    )
    operating_case_attainment = (
        observed_bookings_per_ae / weighted_operating_case_quota
        if weighted_operating_case_quota > 0
        else None
    )
    plan_vs_observed_capacity_ratio = (
        plan_capacity_per_ae / observed_bookings_per_ae
        if observed_bookings_per_ae > 0
        else None
    )
    capacity_risk = "healthy"
    warning = None
    calibration: dict[str, Any] = {
        "operating_case_capacity_per_ae": observed_bookings_per_ae,
        "capacity_multiplier": (
            observed_bookings_per_ae / plan_capacity_per_ae
            if plan_capacity_per_ae > 0 and observed_bookings_per_ae > 0
            else None
        ),
        "operating_case_quota_per_ae": weighted_operating_case_quota,
        "operating_case_attainment": operating_case_attainment,
        "plan_quota_per_ae": weighted_plan_quota,
        "plan_attainment_current_observed": implied_attainment,
        "bridge_to_operating_case_quota_per_ae": (
            weighted_operating_case_quota - observed_bookings_per_ae
            if weighted_operating_case_quota > 0
            else None
        ),
        "bridge_to_operating_case_quota_pct": (
            (weighted_operating_case_quota / observed_bookings_per_ae) - 1.0
            if weighted_operating_case_quota > 0 and observed_bookings_per_ae > 0
            else None
        ),
        "bridge_to_plan_quota_per_ae": (
            weighted_plan_quota - observed_bookings_per_ae
            if weighted_plan_quota > 0
            else None
        ),
        "bridge_to_plan_quota_pct": (
            (weighted_plan_quota / observed_bookings_per_ae) - 1.0
            if weighted_plan_quota > 0 and observed_bookings_per_ae > 0
            else None
        ),
        "recommended_attainment_if_quota_fixed": implied_attainment,
        "recommended_quota_if_attainment_fixed": (
            observed_bookings_per_ae / weighted_plan_attainment
            if weighted_plan_attainment > 0 and observed_bookings_per_ae > 0
            else None
        ),
        "plan_team_capacity": plan_capacity_per_ae * active_total,
        "operating_case_team_capacity": observed_bookings_per_ae * active_total,
        "team_capacity_gap": (observed_bookings_per_ae - plan_capacity_per_ae) * active_total,
    }
    if plan_vs_observed_capacity_ratio is not None and implied_attainment is not None:
        ratio_value = float(plan_vs_observed_capacity_ratio)
        attainment_value = float(implied_attainment)
        if ratio_value >= 3.0 or attainment_value < 0.35:
            capacity_risk = "high"
        elif ratio_value >= 2.0 or attainment_value < 0.50:
            capacity_risk = "material"

        if capacity_risk != "healthy":
            operating_case_attainment_value = (
                float(operating_case_attainment)
                if operating_case_attainment is not None
                else None
            )
            warning = (
                "Operating-case AE capacity remains materially below the selected top-down plan: "
                f"{ratio_value:.2f}x gap between top-down capacity and current output, "
                f"with {attainment_value:.0%} attainment against the top-down quota"
            )
            if operating_case_attainment_value is not None:
                warning += f" and {operating_case_attainment_value:.0%} against the policy quota."
            else:
                warning += "."

    return {
        "segment_mix": segment_mix,
        "active_ae_count": active_total,
        "weighted_plan_quota_per_ae": weighted_plan_quota,
        "weighted_operating_case_quota_per_ae": weighted_operating_case_quota,
        "weighted_plan_attainment": weighted_plan_attainment,
        "plan_steady_state_arr_per_ae": plan_capacity_per_ae,
        "observed_annual_s2_pipeline_per_ae": observed_s2_pipeline_per_ae,
        "observed_annual_bookings_arr_per_ae": observed_bookings_per_ae,
        "implied_observed_attainment": implied_attainment,
        "operating_case_attainment": operating_case_attainment,
        "plan_vs_observed_capacity_ratio": plan_vs_observed_capacity_ratio,
        "capacity_risk": capacity_risk,
        "warning": warning,
        "calibration": calibration,
        "ae_productivity_source": trajectory_rollforward.get("ae_productivity_source", "unavailable"),
        "ae_ramp_curve_source": trajectory_rollforward.get("ae_ramp_curve_source", "config"),
        "s2_to_won_source": s2_to_won.get("source", "config"),
        "avg_deal_size": avg_deal_size,
        "decomposition": {
            "observed_s0_per_ae_month": observed_ae_productivity,
            "s0_to_s1_rate": s0_to_s1,
            "s1_to_s2_rate": s1_to_s2,
            "s2_to_won_rate": s2_to_won_rate,
            "observed_s1_deals_per_ae_month": observed_s1_deals_per_ae_month,
            "observed_s2_deals_per_ae_month": observed_s2_deals_per_ae_month,
            "observed_won_deals_per_ae_month": observed_won_deals_per_ae_month,
            "observed_s2_pipeline_arr_per_ae_month": observed_s2_pipeline_per_ae / 12.0,
            "observed_bookings_arr_per_ae_month": observed_bookings_per_ae / 12.0,
        },
        "ramp_rows": _build_ae_ramp_comparison(trajectory_rollforward),
    }


def build_capacity_realism_benchmark(tieout: Any, result: TieoutResult) -> dict:
    """Compare plan AE capacity assumptions against observed trajectory reality."""
    return build_capacity_realism_benchmark_from_rollforward(
        tieout,
        _trajectory_rollforward(result),
    )


def build_runtime_source_contract(tieout: Any, result: TieoutResult) -> list[dict]:
    """Return the active runtime signal contract with source precedence."""
    primary = _primary_scenario(result)
    rollforward = primary.monthly_rollforward_provenance or {}
    trajectory_rollforward = (
        getattr(getattr(result, "trajectory", None), "monthly_rollforward_provenance", {}) or {}
    )
    beginning = result.beginning_arr_provenance or {}
    finance = result.bookings_summary_provenance or {}
    arr_movements = getattr(result, "arr_movements", {}) or {}
    stage_velocity = tieout._get_observed_stage_velocity()

    ae_productivity_source = trajectory_rollforward.get("ae_productivity_source", "archived_plan_only")
    ae_stream_source = trajectory_rollforward.get("ae_stream_source")
    if ae_stream_source == "config_fallback":
        ae_productivity_source = "config_fallback"

    return [
        {
            "input": "ae_roster",
            "priority": ["warehouse + roster.yaml", "roster.yaml", "unavailable"],
            "active_source": trajectory_rollforward.get("roster_source", "roster.yaml"),
            "active_method": "merged_live_roster",
            "notes": None,
        },
        {
            "input": "beginning_arr",
            "priority": ["warehouse", "Salesforce", "targets.yaml"],
            "active_source": beginning.get("source", "unavailable"),
            "active_method": beginning.get("method", "unknown"),
            "notes": beginning.get("warning"),
        },
        {
            "input": "closed_won_finance_summary",
            "priority": ["warehouse", "Salesforce", "unavailable"],
            "active_source": finance.get("source", "unavailable"),
            "active_method": finance.get("method", "unknown"),
            "fallback_from": finance.get("fallback_from"),
            "fallback_reason": finance.get("fallback_reason"),
            "notes": finance.get("warning"),
        },
        {
            "input": "open_inventory",
            "priority": ["warehouse", "Salesforce", "unavailable"],
            "active_source": rollforward.get("inventory_source", "unavailable"),
            "active_method": rollforward.get("inventory_metric_selection", "unknown"),
            "fallback_from": rollforward.get("fallback_from"),
            "fallback_reason": rollforward.get("fallback_reason"),
            "notes": None,
        },
        {
            "input": "ae_productivity",
            "priority": ["warehouse", "Salesforce", "config_fallback", "unavailable"],
            "active_source": ae_productivity_source,
            "active_method": trajectory_rollforward.get("pipeline_source", "archived_plan"),
            "notes": trajectory_rollforward.get("trajectory_fallback_reason"),
        },
        {
            "input": "ae_ramp_curve",
            "priority": ["warehouse", "config"],
            "active_source": trajectory_rollforward.get("ae_ramp_curve_source", "config"),
            "active_method": (
                "cohort_s0s_per_ae_month_since_start"
                if trajectory_rollforward.get("ae_ramp_curve_source") == "warehouse"
                else "assumptions.segment_productivity.ramp_curve"
            ),
            "sample_sizes": trajectory_rollforward.get("ae_ramp_curve_sample_sizes", {}),
            "notes": trajectory_rollforward.get("ae_ramp_curve_reason"),
        },
        {
            "input": "mql_signal",
            "priority": ["warehouse", "Salesforce", "unavailable"],
            "active_source": trajectory_rollforward.get("mql_signal_source", "archived_plan_only"),
            "active_method": trajectory_rollforward.get("pipeline_source", "archived_plan"),
            "notes": None,
        },
        {
            "input": "arr_movements",
            "priority": ["Salesforce", "unavailable"],
            "active_source": arr_movements.get("source", "unavailable"),
            "active_method": "trailing_12_month_arr_waterfall",
            "notes": "Still Salesforce-only; warehouse equivalent is not implemented yet.",
        },
        {
            "input": "stage_velocity",
            "priority": ["warehouse", "Salesforce", "config"],
            "active_source": stage_velocity.get("source", "config"),
            "active_method": "per_deal_stage_duration",
            "sample_sizes": stage_velocity.get("sample_sizes", {}),
            "notes": None,
        },
    ]


def build_rate_contract(tieout: Any) -> list[dict]:
    """Return runtime rate provenance used by trajectory and roll-forward math."""
    runtime_rates = tieout.runtime.describe_runtime_funnel_rates()
    rolling_s2 = tieout._get_rolling_s2_to_won_rate()
    decay = tieout._get_observed_decay_curve()

    entries = []
    for rate_key in ("mql_to_s0", "s0_to_s1", "s1_to_s2"):
        rate_info = runtime_rates.get(rate_key, {})
        entries.append(
            {
                "rate": rate_key,
                "value": float(rate_info.get("value", 0.0) or 0.0),
                "source": rate_info.get("source", "config"),
                "notes": None,
            }
        )

    entries.append(
        {
            "rate": "s2_to_won",
            "value": float(rolling_s2.get("rate", 0.0) or 0.0),
            "source": rolling_s2.get("source", "config"),
            "sample": int(rolling_s2.get("sample", 0) or 0),
            "method": rolling_s2.get("method"),
            "min_age_days": int(rolling_s2.get("min_age_days", 0) or 0),
            "notes": (
                "Quarter-bounded warehouse aggregates measure same-quarter "
                "velocity, not lifetime conversion — lifetime S2→Won "
                "comes from per-deal stage history or config."
            ),
        }
    )
    entries.append(
        {
            "rate": "close_timing_curve",
            "value": list(decay.get("curve", []) or []),
            "source": decay.get("source", "config"),
            "sample": int(decay.get("sample", 0) or 0),
            "notes": None,
        }
    )
    return entries


def build_semantic_scorecard(tieout: Any, result: TieoutResult) -> dict:
    """Build a compact semantic review payload for plan vs trajectory."""
    primary = _primary_scenario(result)
    archived = _archived_plan(result)
    archived_by_quarter = _quarter_map(archived)
    finance_totals = (result.bookings_summary or {}).get("totals", {}) or {}
    trajectory_rollforward = (
        getattr(getattr(result, "trajectory", None), "monthly_rollforward_provenance", {}) or {}
    )

    quarters = []
    stream_rows = []
    for quarter in primary.quarters:
        archived_quarter = archived_by_quarter.get(quarter.quarter, quarter)
        quarters.append(
            {
                "quarter": quarter.quarter,
                "top_down_sales_led_arr": float(quarter.td_bookings or 0.0),
                "trajectory_sales_led_arr": float(quarter.bu_sales_led_arr or 0.0),
                "archived_plan_sales_led_arr": float(archived_quarter.bu_sales_led_arr or 0.0),
                "gap_vs_target": float(quarter.bookings_gap or 0.0),
                "gap_vs_target_pct": float(quarter.bookings_gap_pct or 0.0),
                "top_down_total_net_new_arr": float(quarter.td_total_net_new or 0.0),
                "trajectory_total_net_new_arr": float(quarter.bu_total_arr or 0.0),
                "archived_plan_total_net_new_arr": float(archived_quarter.bu_total_arr or 0.0),
                "actual_bookings": float(archived_quarter.actual_bookings or 0.0),
                "actual_pipeline": float(archived_quarter.actual_pipeline or 0.0),
                "executive_context_gap_vs_target": float(quarter.total_gap or 0.0),
                "executive_context_gap_vs_target_pct": float(quarter.total_gap_pct or 0.0),
                "confidence_tier": quarter.confidence_tier,
                "target_status": (quarter.target_provenance or {}).get("status"),
                "target_approved": (quarter.target_provenance or {}).get("approved"),
            }
        )

        primary_streams = (quarter.source_breakdown or {}).get("streams", {}) or {}
        archived_streams = (archived_quarter.source_breakdown or {}).get("streams", {}) or {}
        for stream_key in sorted(set(primary_streams) | set(archived_streams)):
            modeled = primary_streams.get(stream_key, {}) or {}
            actual = archived_streams.get(stream_key, {}) or {}
            stream_rows.append(
                {
                    "quarter": quarter.quarter,
                    "stream_key": stream_key,
                    "display_name": modeled.get("display_name")
                    or actual.get("display_name")
                    or stream_key.replace("_", " ").title(),
                    "trajectory_pipeline_created": float(modeled.get("quarter_pipeline_created", 0.0) or 0.0),
                    "actual_pipeline": float(actual.get("actual_pipeline", 0.0) or 0.0),
                    "actual_opp_count": int(actual.get("actual_opp_count", 0) or 0),
                    "trajectory_weekly_s2": float(modeled.get("weekly_s2_count", 0.0) or 0.0),
                    "actual_mode": (archived_quarter.source_breakdown or {}).get("mode", "unknown"),
                }
            )

    return {
        "plan_case": result.top_down_plan or {},
        "comparison_contract": {
            "operator_comparable_metric": "sales_led_arr",
            "operator_comparable_role": "primary_comparison",
            "executive_context_metric": "total_net_new_arr",
            "executive_context_role": "secondary_reference_only",
        },
        "fy_summary": {
            "beginning_arr": float(result.beginning_arr or 0.0),
            "gap": float(primary.fy_sales_led_gap or 0.0),
            "gap_pct": float(primary.fy_sales_led_gap_pct or 0.0),
            "top_down_total_net_new_arr": float(primary.fy_total_td or 0.0),
            "trajectory_total_net_new_arr": float(primary.fy_total_bu or 0.0),
            "archived_plan_total_net_new_arr": float(archived.fy_total_bu or 0.0),
            "top_down_sales_led_arr": float(primary.fy_bookings_td or 0.0),
            "trajectory_sales_led_arr": float(sum(q.bu_sales_led_arr for q in primary.quarters)),
            "archived_plan_sales_led_arr": float(archived.fy_bookings_bu or 0.0),
            "executive_context_gap": float(primary.fy_gap or 0.0),
            "executive_context_gap_pct": float(primary.fy_gap_pct or 0.0),
            "actual_closed_won_amount": float(finance_totals.get("amount", 0.0) or 0.0),
            "actual_closed_won_year1_arr": float(finance_totals.get("year1_arr", 0.0) or 0.0),
        },
        "runtime_contract": build_runtime_source_contract(tieout, result),
        "rate_contract": build_rate_contract(tieout),
        "capacity_benchmark": build_capacity_realism_benchmark(tieout, result),
        "ae_ramp_comparison": _build_ae_ramp_comparison(trajectory_rollforward),
        "quarters": quarters,
        "streams": stream_rows,
    }


def format_semantic_scorecard(scorecard: dict) -> str:
    """Render a scorecard dict as a compact plain-text report."""
    lines: list[str] = []
    plan = scorecard.get("plan_case", {}) or {}
    comparison_contract = scorecard.get("comparison_contract", {}) or {}
    fy = scorecard.get("fy_summary", {}) or {}

    lines.append("Planning Tie-Out Semantic Scorecard")
    lines.append("=" * 40)
    lines.append(f"Plan Case: {plan.get('label', plan.get('plan_id', 'Unknown'))}")
    if comparison_contract:
        lines.append(
            "Comparison Contract: "
            f"{comparison_contract.get('operator_comparable_metric', 'unknown')} primary, "
            f"{comparison_contract.get('executive_context_metric', 'unknown')} secondary"
        )
    lines.append(f"Beginning ARR: {_format_money(fy.get('beginning_arr', 0.0))}")
    lines.append(
        "FY Sales-Led Target / Trajectory / Archived: "
        f"{_format_money(fy.get('top_down_sales_led_arr', 0.0))} / "
        f"{_format_money(fy.get('trajectory_sales_led_arr', 0.0))} / "
        f"{_format_money(fy.get('archived_plan_sales_led_arr', 0.0))}"
    )
    lines.append(
        "FY Executive Context Total Net New / Trajectory / Archived: "
        f"{_format_money(fy.get('top_down_total_net_new_arr', 0.0))} / "
        f"{_format_money(fy.get('trajectory_total_net_new_arr', 0.0))} / "
        f"{_format_money(fy.get('archived_plan_total_net_new_arr', 0.0))}"
    )
    lines.append(
        "Closed Won Amount / Year1 ARR: "
        f"{_format_money(fy.get('actual_closed_won_amount', 0.0))} / "
        f"{_format_money(fy.get('actual_closed_won_year1_arr', 0.0))}"
    )
    lines.append("")
    lines.append("Runtime Contract")
    lines.append("-" * 40)
    for entry in scorecard.get("runtime_contract", []):
        priority = " > ".join(entry.get("priority", []))
        suffix = []
        if entry.get("fallback_from"):
            suffix.append(f"fallback {entry['fallback_from']} ({entry.get('fallback_reason', 'unknown')})")
        if entry.get("notes"):
            suffix.append(str(entry["notes"]))
        if entry.get("sample_sizes"):
            suffix.append(f"samples={json.dumps(entry['sample_sizes'], sort_keys=True)}")
        detail = f" | {'; '.join(suffix)}" if suffix else ""
        lines.append(
            f"{entry['input']}: {entry.get('active_source', 'unknown')} "
            f"[{priority}] via {entry.get('active_method', 'unknown')}{detail}"
        )

    lines.append("")
    lines.append("Rate Contract")
    lines.append("-" * 40)
    for entry in scorecard.get("rate_contract", []):
        value = entry.get("value")
        if isinstance(value, list):
            value_text = json.dumps([round(float(v), 4) for v in value])
        else:
            value_text = f"{float(value or 0.0):.4f}"
        suffix = []
        if entry.get("sample"):
            suffix.append(f"sample={entry['sample']}")
        if entry.get("method"):
            method = str(entry["method"])
            min_age_days = int(entry.get("min_age_days", 0) or 0)
            if min_age_days > 0:
                method = f"{method}, min_age_days={min_age_days}"
            suffix.append(method)
        if entry.get("notes"):
            suffix.append(str(entry["notes"]))
        detail = f" | {'; '.join(suffix)}" if suffix else ""
        lines.append(f"{entry['rate']}: {value_text} ({entry.get('source', 'unknown')}){detail}")

    benchmark = scorecard.get("capacity_benchmark", {}) or {}
    if benchmark:
        lines.append("")
        lines.append("Capacity Benchmark")
        lines.append("-" * 40)
        lines.append(
            "Plan steady-state / Observed steady-state per AE: "
            f"{_format_money(benchmark.get('plan_steady_state_arr_per_ae', 0.0))} / "
            f"{_format_money(benchmark.get('observed_annual_bookings_arr_per_ae', 0.0))}"
        )
        implied_attainment = benchmark.get("implied_observed_attainment")
        implied_text = "--" if implied_attainment is None else f"{float(implied_attainment):.0%}"
        ratio = benchmark.get("plan_vs_observed_capacity_ratio")
        ratio_text = "--" if ratio is None else f"{float(ratio):.2f}x"
        lines.append(
            "Weighted plan quota / plan attainment / implied observed attainment: "
            f"{_format_money(benchmark.get('weighted_plan_quota_per_ae', 0.0))} / "
            f"{float(benchmark.get('weighted_plan_attainment', 0.0)):.0%} / "
            f"{implied_text}"
        )
        lines.append(
            "Plan-vs-observed capacity ratio: "
            f"{ratio_text}; AE productivity source={benchmark.get('ae_productivity_source', 'unknown')}; "
            f"AE ramp source={benchmark.get('ae_ramp_curve_source', 'unknown')}"
        )
        if benchmark.get("warning"):
            lines.append(f"Warning: {benchmark['warning']}")
        calibration = benchmark.get("calibration", {}) or {}
        if calibration:
            operating_case_attainment_text = (
                "--"
                if calibration.get("operating_case_attainment") is None
                else f"{float(calibration.get('operating_case_attainment')):.0%}"
            )
            bridge_to_policy = calibration.get("bridge_to_operating_case_quota_per_ae")
            bridge_to_policy_pct = calibration.get("bridge_to_operating_case_quota_pct")
            bridge_to_plan = calibration.get("bridge_to_plan_quota_per_ae")
            bridge_to_plan_pct = calibration.get("bridge_to_plan_quota_pct")
            bridge_to_policy_text = (
                _format_money(bridge_to_policy or 0.0) if bridge_to_policy is not None else "--"
            )
            bridge_to_policy_pct_text = (
                "--" if bridge_to_policy_pct is None else f"{float(bridge_to_policy_pct):.0%}"
            )
            bridge_to_plan_text = (
                _format_money(bridge_to_plan or 0.0) if bridge_to_plan is not None else "--"
            )
            bridge_to_plan_pct_text = (
                "--" if bridge_to_plan_pct is None else f"{float(bridge_to_plan_pct):.0%}"
            )
            lines.append(
                "Calibration recommendation: "
                f"use {_format_money(calibration.get('operating_case_capacity_per_ae', 0.0))} per AE "
                f"({float(calibration.get('capacity_multiplier', 0.0) or 0.0):.2f}x current plan capacity)."
            )
            lines.append(
                "Operating-case quota / attainment: "
                f"{_format_money(calibration.get('operating_case_quota_per_ae', 0.0))} / "
                f"{operating_case_attainment_text}"
            )
            lines.append(
                "Bridge to operating-case quota / plan quota: "
                f"{bridge_to_policy_text} "
                f"({bridge_to_policy_pct_text}) / "
                f"{bridge_to_plan_text} "
                f"({bridge_to_plan_pct_text})"
            )
        decomposition = benchmark.get("decomposition", {}) or {}
        if decomposition:
            lines.append(
                "Observed per-AE chain: "
                f"S0/mo={float(decomposition.get('observed_s0_per_ae_month', 0.0) or 0.0):.2f}, "
                f"S0→S1={float(decomposition.get('s0_to_s1_rate', 0.0) or 0.0):.2f}, "
                f"S1→S2={float(decomposition.get('s1_to_s2_rate', 0.0) or 0.0):.2f}, "
                f"S2→Won={float(decomposition.get('s2_to_won_rate', 0.0) or 0.0):.2f}, "
                f"ACV={_format_money(benchmark.get('avg_deal_size', 0.0))}"
            )
            lines.append(
                "Observed per-AE monthly output: "
                f"S2 deals={float(decomposition.get('observed_s2_deals_per_ae_month', 0.0) or 0.0):.2f}, "
                f"Won deals={float(decomposition.get('observed_won_deals_per_ae_month', 0.0) or 0.0):.2f}, "
                f"S2 ARR={_format_money(decomposition.get('observed_s2_pipeline_arr_per_ae_month', 0.0))}, "
                f"Bookings ARR={_format_money(decomposition.get('observed_bookings_arr_per_ae_month', 0.0))}"
            )

    ramp_rows = scorecard.get("ae_ramp_comparison", []) or []
    if ramp_rows:
        lines.append("")
        lines.append("AE Ramp Comparison")
        lines.append("-" * 40)
        for row in ramp_rows:
            observed = row.get("observed_ramp")
            observed_text = "--" if observed is None else f"{float(observed):.2f}"
            lines.append(
                f"{row['segment']} month_{row['month']}: "
                f"plan={float(row['plan_ramp'] or 0.0):.2f} "
                f"observed={observed_text} "
                f"sample_ae_months={float(row.get('sample_ae_months', 0.0) or 0.0):.2f}"
            )

    lines.append("")
    lines.append("Quarter View")
    lines.append("-" * 40)
    for quarter in scorecard.get("quarters", []):
        lines.append(
            f"{quarter['quarter']}: sales-led target { _format_money(quarter['top_down_sales_led_arr']) }, "
            f"trajectory { _format_money(quarter['trajectory_sales_led_arr']) }, "
            f"archived { _format_money(quarter['archived_plan_sales_led_arr']) }, "
            f"executive context { _format_money(quarter['top_down_total_net_new_arr']) }, "
            f"actual bookings { _format_money(quarter['actual_bookings']) }, "
            f"conf {quarter.get('confidence_tier', 'unknown')}, "
            f"target status {quarter.get('target_status', 'unknown')}"
        )

    lines.append("")
    lines.append("Source Streams")
    lines.append("-" * 40)
    for row in scorecard.get("streams", []):
        lines.append(
            f"{row['quarter']} / {row['display_name']}: "
            f"trajectory { _format_money(row['trajectory_pipeline_created']) }, "
            f"actual pipeline { _format_money(row['actual_pipeline']) }, "
            f"actual opps {row['actual_opp_count']}"
        )
    return "\n".join(lines)

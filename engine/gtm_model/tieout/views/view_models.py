from __future__ import annotations

from datetime import date

from gtm_model.tieout.runtime.env import load_yaml_resource
from gtm_model.tieout.types import TieoutResult


def _primary_scenario(result: TieoutResult):
    return getattr(result, "primary_scenario", None) or getattr(result, "trajectory", None) or result.base


def _archived_plan(result: TieoutResult):
    return getattr(result, "archived_plan", None) or result.base


def _plan_is_board_reference(plan_meta: dict | None) -> bool:
    plan_meta = plan_meta or {}
    plan_id = str(plan_meta.get("plan_id") or "")
    preset_id = str(plan_meta.get("preset_id") or "")
    status = str(plan_meta.get("status") or "")
    return status == "baseline_reference" or preset_id == "board_baseline"


def _supports_monthly_sales_led_targets(result: TieoutResult) -> bool:
    return not _plan_is_board_reference(getattr(result, "top_down_plan", {}) or {})


def _distribute_quarterly_to_monthly(quarters, field: str, months: list) -> list[float]:
    month_values = [0.0] * len(months)
    for quarter in quarters:
        q_start = quarter.period_start
        q_end = quarter.period_end
        q_val = getattr(quarter, field, 0.0) or 0.0
        q_months = [
            idx
            for idx, month in enumerate(months)
            if q_start <= month <= q_end
            or (q_start.year == month.year and q_start.month == month.month)
        ]
        if not q_months:
            q_months = [
                idx
                for idx, month in enumerate(months)
                if q_start <= month.replace(day=15) <= q_end
            ]
        if q_months:
            per_month = q_val / len(q_months)
            for idx in q_months:
                month_values[idx] = per_month
    return month_values


def _resolve_monthly_sales_led_targets(result: TieoutResult, scenario) -> tuple[list[float | None], bool]:
    months = list(getattr(scenario, "monthly_months", []) or [])
    if not _supports_monthly_sales_led_targets(result):
        return [None] * len(months), False
    return _distribute_quarterly_to_monthly(scenario.quarters, "td_bookings", months), True


def build_bookings_bridge_view_model(result: TieoutResult) -> dict:
    scenario = _primary_scenario(result)
    months = list(getattr(scenario, "monthly_months", []) or [])
    month_labels = [m.strftime("%b %Y") if hasattr(m, "strftime") else str(m) for m in months]
    count = len(months)

    existing_wins = (list(getattr(scenario, "monthly_existing_inventory_wins", []) or []) + [0.0] * count)[:count]
    future_wins = (list(getattr(scenario, "monthly_future_generation_wins", []) or []) + [0.0] * count)[:count]
    total_wins_uncapped = [
        (list(getattr(scenario, "monthly_total_expected_wins", []) or []) + [0.0] * count)[idx]
        if idx < len(list(getattr(scenario, "monthly_total_expected_wins", []) or []))
        else existing_wins[idx] + future_wins[idx]
        for idx in range(count)
    ]
    capped_wins = (list(getattr(scenario, "monthly_bookings_capped", []) or []) + [0.0] * count)[:count]
    monthly_targets, monthly_targets_supported = _resolve_monthly_sales_led_targets(result, scenario)
    monthly_capacity = list(getattr(scenario, "monthly_capacity", []) or [])

    monthly_rows = []
    cum_existing = []
    cum_total_uncapped = []
    cum_target = []
    running_existing = 0.0
    running_total = 0.0
    running_target = 0.0
    for idx, month in enumerate(months):
        total_uncapped = total_wins_uncapped[idx] if idx < len(total_wins_uncapped) else existing_wins[idx] + future_wins[idx]
        target = monthly_targets[idx] if idx < len(monthly_targets) else (
            monthly_capacity[idx].monthly_target if idx < len(monthly_capacity) else None
        )
        running_existing += existing_wins[idx]
        running_total += total_uncapped
        cum_existing.append(running_existing)
        cum_total_uncapped.append(running_total)
        if target is None:
            cum_target.append(None)
        else:
            running_target += target
            cum_target.append(running_target)
        monthly_rows.append(
            {
                "month": month,
                "label": month_labels[idx],
                "existing_wins": existing_wins[idx],
                "future_wins": future_wins[idx],
                "total_uncapped": total_uncapped,
                "total_capped": capped_wins[idx],
                "target": target,
                "gap": (total_uncapped - target) if target is not None else None,
            }
        )

    total_existing = sum(existing_wins)
    total_future = sum(future_wins)
    total_trajectory_uncapped = total_existing + total_future
    total_trajectory_capped = sum(capped_wins)
    total_trajectory = total_trajectory_uncapped
    fy_target = sum((quarter.td_bookings or 0.0) for quarter in scenario.quarters)
    fy_gap = total_trajectory - fy_target

    quarterly_rows = []
    for quarter in scenario.quarters:
        q_existing = 0.0
        q_future = 0.0
        for idx, month in enumerate(months):
            if hasattr(month, "month") and (
                quarter.period_start <= month <= quarter.period_end
                or (
                    quarter.period_start.year == month.year
                    and quarter.period_start.month == month.month
                )
            ):
                q_existing += existing_wins[idx]
                q_future += future_wins[idx]
        q_total = quarter.bu_sales_led_arr or 0.0
        q_gap = q_total - (quarter.td_bookings or 0.0)
        quarterly_rows.append(
            {
                "quarter": quarter.quarter,
                "target": quarter.td_bookings or 0.0,
                "trajectory": q_total,
                "gap": q_gap,
                "gap_pct": q_gap / (quarter.td_bookings or 1),
                "from_existing": q_existing,
                "from_future": q_future,
                "data_basis": getattr(quarter, "confidence_tier", ""),
            }
        )

    return {
        "scenario": scenario,
        "monthly_targets_supported": monthly_targets_supported,
        "months": months,
        "month_labels": month_labels,
        "monthly": monthly_rows,
        "series": {
            "existing_wins": existing_wins,
            "future_wins": future_wins,
            "total_uncapped": total_wins_uncapped,
            "total_capped": capped_wins,
            "targets": monthly_targets,
            "cum_existing": cum_existing,
            "cum_total_uncapped": cum_total_uncapped,
            "cum_target": cum_target,
            "capacity": ([
                mc.ae_capacity if hasattr(mc, "ae_capacity") else 0.0
                for mc in monthly_capacity
            ] + [0.0] * count)[:count],
        },
        "totals": {
            "existing": total_existing,
            "future": total_future,
            "trajectory_uncapped": total_trajectory_uncapped,
            "trajectory_capped": total_trajectory_capped,
            "trajectory": total_trajectory,
            "target": fy_target,
            "gap": fy_gap,
            "existing_pct": total_existing / total_trajectory_uncapped if total_trajectory_uncapped > 0 else 0.0,
            "future_pct": total_future / total_trajectory_uncapped if total_trajectory_uncapped > 0 else 0.0,
        },
        "quarterly": quarterly_rows,
    }


def build_funnel_pacing_view_model(quarter, as_of: date | None = None) -> dict:
    as_of = as_of or date.today()
    quarter_state = quarter.quarter_state(as_of)
    if quarter_state == "not_started":
        return {
            "quarter": quarter.quarter,
            "quarter_state": quarter_state,
            "elapsed_fraction": 0.0,
            "elapsed_weeks": 0.0,
            "total_weeks": 0.0,
            "rows": [],
        }

    elapsed_fraction = quarter.elapsed_fraction()
    quarter_days = (quarter.period_end - quarter.period_start).days + 1
    elapsed_days = max((as_of - quarter.period_start).days, 0) if as_of >= quarter.period_start else 0
    total_weeks = quarter_days / 7
    elapsed_weeks = min(elapsed_days / 7, total_weeks)

    rows = []
    for stage_name, weekly_target, actual_weekly_avg in [
        ("MQLs", quarter.td_mqls_weekly, quarter.actual_mqls if hasattr(quarter, "actual_mqls") else 0),
        ("S0 (Opps Created)", quarter.td_s0_weekly, quarter.actual_s0 if hasattr(quarter, "actual_s0") else 0),
        ("S1 (Meetings Held)", quarter.td_s1_weekly, quarter.actual_s1 if hasattr(quarter, "actual_s1") else 0),
        ("S2 (Qualified Pipeline)", quarter.td_s2_weekly, quarter.actual_s2 if hasattr(quarter, "actual_s2") else 0),
    ]:
        weekly_actual = actual_weekly_avg or 0
        qtd_target = int(weekly_target * elapsed_weeks) if weekly_target else 0
        qtd_actual = int(weekly_actual * elapsed_weeks) if elapsed_weeks > 0 else 0
        rows.append(
            {
                "stage": stage_name,
                "weekly_target": weekly_target or 0,
                "weekly_actual": weekly_actual,
                "qtd_target": qtd_target,
                "qtd_actual": qtd_actual,
                "pacing_pct": qtd_actual / qtd_target if qtd_target > 0 else 0.0,
                "quarter_target": int(weekly_target * total_weeks) if weekly_target else 0,
            }
        )

    return {
        "quarter": quarter.quarter,
        "quarter_state": quarter_state,
        "elapsed_fraction": elapsed_fraction,
        "elapsed_weeks": elapsed_weeks,
        "total_weeks": total_weeks,
        "rows": rows,
    }


def build_se_capacity_view_model(result: TieoutResult) -> dict:
    scenario = _primary_scenario(result)
    roster_data = load_yaml_resource("roster.yaml")
    roster_se_active = (roster_data.get("se_active", []) or []) if roster_data else []
    roster_se_incoming = (roster_data.get("se_incoming", []) or []) if roster_data else []

    def roster_se_count_at(month_start: date) -> int:
        count = 0
        for entry in roster_se_active:
            try:
                start_date = date.fromisoformat(str(entry.get("start_date", "")))
            except (TypeError, ValueError):
                start_date = date(2020, 1, 1)
            if start_date <= month_start and entry.get("role") in ("se", "se_manager", "gtm_pm"):
                count += 1
        for entry in roster_se_incoming:
            try:
                start_date = date.fromisoformat(str(entry.get("start_date", "")))
            except (TypeError, ValueError):
                continue
            if start_date <= month_start:
                count += 1
        return count

    prov = getattr(scenario, "monthly_rollforward_provenance", None) or {}
    count_by_stage = prov.get("inventory_count_by_stage", {})
    inv_by_stage = prov.get("inventory_by_stage", {})
    s2_plus_stages = ["S2", "S3", "S4", "S5"]
    if count_by_stage:
        active_s2_plus_deals = sum(count_by_stage.get(stage, 0) for stage in s2_plus_stages)
    else:
        total_inv = sum(inv_by_stage.values()) if inv_by_stage else 0
        s2_plus_inv = sum(inv_by_stage.get(stage, 0) for stage in s2_plus_stages) if inv_by_stage else 0
        total_count = prov.get("inventory_opportunity_count", 0)
        active_s2_plus_deals = round(total_count * (s2_plus_inv / total_inv)) if total_inv > 0 and total_count > 0 else 0

    current_ses = sum(1 for entry in roster_se_active if entry.get("role") in ("se", "se_manager", "gtm_pm"))
    incoming_ses = len(roster_se_incoming)

    plan_se_target = None
    targets = load_yaml_resource("targets.yaml")
    if targets:
        headcount_targets = targets.get("headcount_targets", {}) or {}
        today = date.today()
        fiscal_month = (today.month - 2) % 12
        quarter_idx = fiscal_month // 3
        quarter_labels = ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"]
        if quarter_idx < len(quarter_labels) and quarter_labels[quarter_idx] in headcount_targets:
            plan_se_target = headcount_targets[quarter_labels[quarter_idx]].get("sales_engineers")

    monthly_rows = []
    for monthly_capacity in getattr(scenario, "monthly_capacity", []) or []:
        se_count = roster_se_count_at(monthly_capacity.month)
        ae_count = monthly_capacity.ae_total or 0
        monthly_rows.append(
            {
                "month": monthly_capacity.month,
                "label": monthly_capacity.label,
                "ae_count": ae_count,
                "se_count": se_count,
                "ae_se_ratio": f"{ae_count / se_count:.1f}:1" if se_count > 0 else "--",
                "deals_per_se": round(active_s2_plus_deals / se_count, 1) if se_count > 0 else 0.0,
            }
        )

    return {
        "scenario": scenario,
        "current_ses": current_ses,
        "incoming_ses": incoming_ses,
        "plan_se_target": plan_se_target,
        "se_gap": (current_ses - plan_se_target) if plan_se_target is not None else None,
        "active_s2_plus_deals": active_s2_plus_deals,
        "deals_per_se": (active_s2_plus_deals / current_ses) if current_ses > 0 else float("inf"),
        "monthly": monthly_rows,
    }


def build_scenario_overlay_view_model(result: TieoutResult, flexed_scenario=None) -> dict:
    baseline = _primary_scenario(result)
    effective = flexed_scenario if flexed_scenario is not None else baseline
    has_scenario = flexed_scenario is not None

    months = list(baseline.monthly_months or [])
    month_labels = [m.strftime("%b %Y") if hasattr(m, "strftime") else str(m) for m in months]
    count = len(months)
    monthly_targets, monthly_targets_supported = _resolve_monthly_sales_led_targets(result, baseline)

    baseline_existing = list(baseline.monthly_existing_inventory_wins or [])
    baseline_future = list(baseline.monthly_future_generation_wins or [])
    effective_existing = list(effective.monthly_existing_inventory_wins or [])
    effective_future = list(effective.monthly_future_generation_wins or [])

    baseline_total_line = [
        (baseline_existing[idx] if idx < len(baseline_existing) else 0)
        + (baseline_future[idx] if idx < len(baseline_future) else 0)
        for idx in range(count)
    ]
    scenario_existing_line = [(effective_existing[idx] if idx < len(effective_existing) else 0) for idx in range(count)]
    scenario_total_line = [
        scenario_existing_line[idx] + (effective_future[idx] if idx < len(effective_future) else 0)
        for idx in range(count)
    ]

    cum_baseline_total = []
    cum_scenario_existing = []
    cum_scenario_total = []
    cum_target = []
    running_baseline = running_scenario_existing = running_scenario_total = running_target = 0.0
    for idx in range(count):
        running_baseline += baseline_total_line[idx]
        running_scenario_existing += scenario_existing_line[idx]
        running_scenario_total += scenario_total_line[idx]
        cum_baseline_total.append(running_baseline)
        cum_scenario_existing.append(running_scenario_existing)
        cum_scenario_total.append(running_scenario_total)
        target = monthly_targets[idx] if idx < len(monthly_targets) else None
        if target is None:
            cum_target.append(None)
        else:
            running_target += target
            cum_target.append(running_target)

    quarterly_rows = []
    for baseline_quarter, effective_quarter in zip(baseline.quarters, effective.quarters):
        baseline_arr = baseline_quarter.bu_sales_led_arr
        scenario_arr = effective_quarter.bu_sales_led_arr
        target = baseline_quarter.td_bookings
        delta = scenario_arr - baseline_arr
        quarterly_rows.append(
            {
                "quarter": baseline_quarter.quarter,
                "sales_led_target": target,
                "baseline": baseline_arr,
                "scenario": scenario_arr,
                "delta": delta,
                "delta_pct": (delta / baseline_arr) if baseline_arr else None,
                "gap_to_target": (scenario_arr if has_scenario else baseline_arr) - target,
            }
        )

    baseline_total = sum(q.bu_sales_led_arr for q in baseline.quarters)
    scenario_total = sum(q.bu_sales_led_arr for q in effective.quarters)
    fy_target = sum(q.td_bookings for q in baseline.quarters)
    fy_gap = fy_target - scenario_total
    fy_gap_pct = (fy_gap / fy_target) if fy_target else 0.0

    return {
        "has_scenario": has_scenario,
        "baseline": baseline,
        "effective": effective,
        "months": months,
        "month_labels": month_labels,
        "monthly_targets_supported": monthly_targets_supported,
        "monthly_targets": monthly_targets,
        "baseline_total_capped": baseline_total,
        "scenario_total_capped": scenario_total,
        "delta_capped": scenario_total - baseline_total,
        "fy_target": fy_target,
        "baseline_total_line": baseline_total_line,
        "scenario_existing_line": scenario_existing_line,
        "scenario_total_line": scenario_total_line,
        "cum_baseline_total": cum_baseline_total,
        "cum_scenario_existing": cum_scenario_existing,
        "cum_scenario_total": cum_scenario_total,
        "cum_target": cum_target,
        "quarterly": quarterly_rows,
        "fy_summary": {
            "target": fy_target,
            "baseline": baseline_total,
            "scenario": scenario_total,
            "gap": fy_gap,
            "gap_pct": fy_gap_pct,
        },
    }


def build_scenario_override_rows(scenario_overrides: dict | None) -> list[dict]:
    if not scenario_overrides:
        return []
    all_keys = set()
    for quarter_overrides in scenario_overrides.values():
        if isinstance(quarter_overrides, dict):
            all_keys.update(quarter_overrides.keys())
    rows = []
    for key in sorted(all_keys):
        row = {"parameter": key}
        for quarter_label, quarter_overrides in scenario_overrides.items():
            row[quarter_label] = quarter_overrides.get(key, "") if isinstance(quarter_overrides, dict) else ""
        rows.append(row)
    return rows

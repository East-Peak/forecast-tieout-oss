"""Narrative invariants for the three public demo personas.

These tests generate fresh persona data into a temp directory, build canonical
snapshots from that data, and assert only snapshot fields consumed by the
existing frontend pages.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
AS_OF = "2026-04-06"

PERSONA_GENERATORS = {
    "sprout-labs": "engine.scripts.generate_sprout_data",
    "sapling-industries": "engine.scripts.generate_sapling_data",
    "mighty-oak-holdings": "engine.scripts.generate_mighty_oak_data",
}

H2_QUARTERS = ("Q3FY26", "Q4FY26")
FY_QUARTERS = ("Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26")
EPSILON = 1e-6


@pytest.fixture(scope="module")
def persona_snapshots(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    """Generate data and snapshots from temp-local CSVs/config."""

    root = tmp_path_factory.mktemp("persona-narratives")
    temp_config = root / "config"
    shutil.copytree(REPO_ROOT / "engine" / "config", temp_config)

    env = os.environ.copy()
    env["GTM_TIEOUT_CONFIG_DIR"] = str(temp_config)
    env.setdefault("GTM_TIEOUT_GIT_SHA", "persona-narrative-test")

    snapshots: dict[str, dict[str, Any]] = {}
    for profile_id, module_name in PERSONA_GENERATORS.items():
        data_dir = root / "data" / profile_id
        subprocess.run(
            [sys.executable, "-m", module_name, "--output-dir", str(data_dir)],
            cwd=REPO_ROOT,
            env=env,
            check=True,
        )

        profile_path = temp_config / "profiles" / profile_id / "profile.yaml"
        profile = yaml.safe_load(profile_path.read_text()) or {}
        profile.setdefault("data_access", {}).setdefault("params", {})["path"] = str(data_dir)
        profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")

        output = root / "snapshots" / profile_id / "snapshot.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "engine.scripts.generate_snapshot",
                "--profile-id",
                profile_id,
                "--as-of",
                AS_OF,
                "--output",
                str(output),
                "--profiles-output-dir",
                str(root / "frontend-profiles"),
            ],
            cwd=REPO_ROOT,
            env=env,
            check=True,
        )
        snapshots[profile_id] = json.loads(output.read_text())

    return snapshots


@pytest.fixture(scope="module")
def acme_snapshot(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Generate Acme through the canonical CSV-backed snapshot path."""

    root = tmp_path_factory.mktemp("acme-canonical-snapshot")
    output = root / "snapshot.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "engine.scripts.generate_snapshot",
            "--profile-id",
            "acme-saas",
            "--as-of",
            AS_OF,
            "--output",
            str(output),
            "--profiles-output-dir",
            str(root / "profiles"),
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    return json.loads(output.read_text())


def _trajectory_quarters(snapshot: dict[str, Any], section: str = "bookings_bridge") -> dict[str, dict[str, Any]]:
    return {
        row["quarter"]: row
        for row in snapshot["model_output"][section]["trajectory_quarters"]
    }


def _quarter_bounds(snapshot: dict[str, Any]) -> dict[str, tuple[date, date]]:
    return {
        row["quarter"]: (
            date.fromisoformat(row["period_start"]),
            date.fromisoformat(row["period_end"]),
        )
        for row in snapshot["model_output"]["bookings_bridge"]["trajectory_quarters"]
    }


def _quarter_for_month(snapshot: dict[str, Any], month: str) -> str | None:
    month_date = date.fromisoformat(month[:10])
    for quarter, (start, end) in _quarter_bounds(snapshot).items():
        if start <= month_date <= end:
            return quarter
    return None


def _quarter_for_deal(snapshot: dict[str, Any], deal: dict[str, Any]) -> str | None:
    close_date = deal.get("close_date")
    if not close_date:
        return None
    close = date.fromisoformat(close_date[:10])
    for quarter, (start, end) in _quarter_bounds(snapshot).items():
        if start <= close <= end:
            return quarter
    return None


def _bookings_target(snapshot: dict[str, Any], quarter: str) -> float:
    return float(_trajectory_quarters(snapshot)[quarter]["top_down"]["bookings"] or 0)


def _pipeline_target_coverage(snapshot: dict[str, Any], quarter: str) -> float:
    row = _trajectory_quarters(snapshot)[quarter]
    bookings = float(row["top_down"]["bookings"] or 0)
    pipeline_target = float(row["top_down"].get("pipeline_target") or 0)
    return pipeline_target / bookings if bookings > 0 else 0.0


def _actual_totals_by_quarter(snapshot: dict[str, Any], key: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in snapshot["actuals"].get(key, []):
        quarter = _quarter_for_month(snapshot, row["month"])
        if quarter:
            totals[quarter] += float(row.get("total", row.get("value", 0)) or 0)
    return totals


def _dollar_win_rates(snapshot: dict[str, Any]) -> dict[str, float]:
    bookings = _actual_totals_by_quarter(snapshot, "bookings_by_month")
    losses = _actual_totals_by_quarter(snapshot, "losses_by_month")
    rates: dict[str, float] = {}
    for quarter in sorted(set(bookings) | set(losses)):
        won = bookings.get(quarter, 0.0)
        lost = losses.get(quarter, 0.0)
        denom = won + lost
        if denom > 0:
            rates[quarter] = won / denom
    return rates


def _monthly_dollar_win_rates(snapshot: dict[str, Any]) -> dict[str, float]:
    bookings = {
        row["month"]: float(row.get("total", 0) or 0)
        for row in snapshot["actuals"].get("bookings_by_month", [])
    }
    losses = {
        row["month"]: float(row.get("total", 0) or 0)
        for row in snapshot["actuals"].get("losses_by_month", [])
    }
    rates: dict[str, float] = {}
    for month in sorted(set(bookings) | set(losses)):
        won = bookings.get(month, 0.0)
        lost = losses.get(month, 0.0)
        denom = won + lost
        if denom > 0:
            rates[month] = won / denom
    return rates


def _mql_totals_by_quarter(snapshot: dict[str, Any]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in snapshot["actuals"].get("mql_by_month", []):
        if "month" in row:
            quarter = _quarter_for_month(snapshot, row["month"])
        else:
            month_index = int(row["month_index"])
            quarter = snapshot["scenario_building_blocks"]["quarter_by_month"][month_index]
        if quarter:
            totals[quarter] += float(row.get("total", row.get("value", row.get("count", 0))) or 0)
    return totals


def _open_pipeline_by_quarter(snapshot: dict[str, Any]) -> dict[str, list[float]]:
    by_quarter: dict[str, list[float]] = defaultdict(list)
    for deal in snapshot["pipeline"]["deals"]:
        quarter = _quarter_for_deal(snapshot, deal)
        amount = float(deal.get("metric_value") or deal.get("amount") or 0)
        if quarter and amount > 0:
            by_quarter[quarter].append(amount)
    return by_quarter


def _target_setter_required_mqls_by_quarter(snapshot: dict[str, Any]) -> dict[str, float]:
    scenario = snapshot["target_setter"]["observed_scenario"]
    quarters = list(snapshot["scenario_building_blocks"].get("overridable_quarters") or [])
    if not quarters:
        quarters = list(_trajectory_quarters(snapshot))

    inventory_value = sum(
        float(row.get("total_value") or 0)
        for row in snapshot["pipeline"].get("inventory_by_stage", [])
        if row.get("stage") in {"S2", "S3", "S4", "S5"}
    )
    current_pipe = inventory_value
    required: dict[str, float] = {}

    for quarter in quarters:
        target = _bookings_target(snapshot, quarter)
        won_from_starting = current_pipe * float(scenario["win_rate_starting"])
        won_from_created = target - won_from_starting
        if won_from_created <= 0 or float(scenario["win_rate_created"]) <= 0:
            created_pipe = 0.0
        else:
            created_pipe = won_from_created / float(scenario["win_rate_created"])

        marketing_pipe = created_pipe * (1 - float(scenario["ae_self_gen_pct"]))
        marketing_s2_count = 0.0
        for segment, share in scenario["segment_share"].items():
            acv = float(scenario["acv"][segment])
            if acv > 0:
                marketing_s2_count += (marketing_pipe * float(share)) / acv

        denominator = (
            float(scenario["mql_to_s0"])
            * float(scenario["s0_to_s1"])
            * float(scenario["s1_to_s2"])
        )
        required[quarter] = marketing_s2_count / denominator if denominator > 0 else math.inf

        remaining_coeff = 1 - float(scenario["win_rate_created"]) - float(scenario["loss_rate"]) * 0.5
        current_pipe = current_pipe * float(scenario["push_rate"]) + created_pipe * max(remaining_coeff, 0)

    return required


def _funnel_rate(snapshot: dict[str, Any], key: str) -> float:
    rate_row = snapshot["model_output"]["funnel_health"]["funnel_rates"][key]
    if isinstance(rate_row, dict):
        if "blended" in rate_row:
            return float(rate_row["blended"]["rate"])
        if "rate" in rate_row:
            return float(rate_row["rate"])
    return float(rate_row)


def _plan_values_from_quarter_blocks(snapshot: dict[str, Any]) -> list[float]:
    """Mirror the frontend's current monthly reference for the v2 public plans.

    The committed v2 plan assets use explicit monthly values that are even
    splits of the quarter targets. The engine fixture generates snapshots into
    a temp output tree, so this keeps the pytest layer anchored to the freshly
    generated quarter targets without reading committed plan JSON.
    """

    quarter_targets = {
        row["quarter"]: float(row["top_down"]["bookings"] or 0)
        for row in snapshot["model_output"]["bookings_bridge"]["trajectory_quarters"]
    }
    quarter_month_counts: dict[str, int] = defaultdict(int)
    quarter_by_month = snapshot["scenario_building_blocks"].get("quarter_by_month") or []
    for quarter in quarter_by_month:
        if quarter in quarter_targets:
            quarter_month_counts[quarter] += 1

    values: list[float] = []
    for quarter in quarter_by_month:
        if quarter not in quarter_targets:
            values.append(0.0)
            continue
        values.append(quarter_targets[quarter] / quarter_month_counts[quarter])
    return values


def _capacity_by_month(snapshot: dict[str, Any]) -> dict[str, float]:
    return {
        row["month"][:10]: float(row.get("ae_capacity") or 0)
        for row in snapshot["roster"]["effective_capacity"]
    }


def _quarter_metrics(snapshot: dict[str, Any]) -> dict[str, dict[str, float]]:
    bridge = snapshot["model_output"]["bookings_bridge"]
    plan_values = _plan_values_from_quarter_blocks(snapshot)
    capacity_by_month = _capacity_by_month(snapshot)
    quarter_by_month = snapshot["scenario_building_blocks"].get("quarter_by_month") or []
    metrics = {
        quarter: {"expected": 0.0, "existing": 0.0, "plan": 0.0, "capacity": 0.0}
        for quarter in FY_QUARTERS
    }

    for idx, month in enumerate(bridge["months"]):
        quarter = quarter_by_month[idx] if idx < len(quarter_by_month) else _quarter_for_month(snapshot, month)
        if quarter not in metrics:
            continue
        metrics[quarter]["expected"] += float(bridge["total_expected"][idx] or 0)
        metrics[quarter]["existing"] += float(bridge["existing_wins"][idx] or 0)
        metrics[quarter]["plan"] += plan_values[idx] if idx < len(plan_values) else 0.0
        metrics[quarter]["capacity"] += capacity_by_month.get(month[:10], 0.0)
    return metrics


def _actual_month_keys(snapshot: dict[str, Any]) -> set[str]:
    months = snapshot["scenario_building_blocks"].get("months") or []
    flags = snapshot["scenario_building_blocks"].get("monthly_is_actual") or []
    return {
        str(month)[:7]
        for month, is_actual in zip(months, flags)
        if bool(is_actual)
    }


def _bookings_actuals_in_actual_window(snapshot: dict[str, Any]) -> float:
    actual_month_keys = _actual_month_keys(snapshot)
    return sum(
        float(row.get("total") or 0)
        for row in snapshot["actuals"].get("bookings_by_month", [])
        if str(row.get("month") or "")[:7] in actual_month_keys
    )


def _snapshot_cases(
    persona_snapshots: dict[str, dict[str, Any]],
    acme_snapshot: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {**persona_snapshots, "acme-saas": acme_snapshot}


def _rendered_totals(snapshot: dict[str, Any]) -> dict[str, Any]:
    bridge = snapshot["model_output"]["bookings_bridge"]
    plan_values = _plan_values_from_quarter_blocks(snapshot)
    capacity_by_month = _capacity_by_month(snapshot)
    expected_values = [float(value or 0) for value in bridge["total_expected"]]
    capacity_values = [capacity_by_month.get(month[:10], 0.0) for month in bridge["months"]]
    monthly_expected_to_plan = [
        expected / plan if plan > 0 else 0.0
        for expected, plan in zip(expected_values, plan_values)
    ]
    monthly_expected_to_capacity = [
        expected / capacity if capacity > 0 else 0.0
        for expected, capacity in zip(expected_values, capacity_values)
    ]
    monthly_capacity_to_plan = [
        capacity / plan if plan > 0 else 0.0
        for capacity, plan in zip(capacity_values, plan_values)
    ]
    quarter_metrics = _quarter_metrics(snapshot)
    return {
        "expected": sum(expected_values),
        "plan": sum(plan_values),
        "capacity": sum(capacity_values),
        "monthly_expected_to_plan": monthly_expected_to_plan,
        "monthly_expected_to_capacity": monthly_expected_to_capacity,
        "monthly_capacity_to_plan": monthly_capacity_to_plan,
        "quarters": quarter_metrics,
    }


def _quarter_gap(metrics: dict[str, Any], quarter: str) -> float:
    quarter_metrics = metrics["quarters"][quarter]
    return quarter_metrics["plan"] - quarter_metrics["expected"]


def test_sprout_plan_assumes_repeatability_the_funnel_does_not_show(
    persona_snapshots: dict[str, dict[str, Any]],
) -> None:
    sprout = persona_snapshots["sprout-labs"]
    sapling = persona_snapshots["sapling-industries"]

    h1_coverage = statistics.mean(
        _pipeline_target_coverage(sprout, quarter) for quarter in ("Q1FY26", "Q2FY26")
    )
    h2_coverage = statistics.mean(
        _pipeline_target_coverage(sprout, quarter) for quarter in H2_QUARTERS
    )
    assert h1_coverage >= 2.5
    assert h2_coverage < 2.0

    by_quarter = _open_pipeline_by_quarter(sprout)
    concentrated_quarters = []
    for quarter, amounts in by_quarter.items():
        total = sum(amounts)
        if total > 0 and len(amounts) >= 3:
            concentrated_quarters.append(sum(sorted(amounts, reverse=True)[:3]) / total)
    assert max(concentrated_quarters) > 0.35

    sprout_rates = list(_monthly_dollar_win_rates(sprout).values())
    sapling_rates = list(_monthly_dollar_win_rates(sapling).values())
    assert len(sprout_rates) >= 2
    assert len(sapling_rates) >= 2
    assert statistics.stdev(sprout_rates) > 0.15
    assert statistics.stdev(sprout_rates) > statistics.stdev(sapling_rates) * 1.5

    required_mqls = _target_setter_required_mqls_by_quarter(sprout)
    observed_mqls = _mql_totals_by_quarter(sprout)
    assert sum(observed_mqls.values()) > 0
    assert max(required_mqls[q] for q in H2_QUARTERS) > 2.0 * max(observed_mqls.values())


def test_sapling_headcount_is_on_plan_but_capacity_is_not(
    persona_snapshots: dict[str, dict[str, Any]],
) -> None:
    sapling = persona_snapshots["sapling-industries"]
    capacity_rows = sapling["model_output"]["capacity_headcount"]["trajectory_capacity"]
    h2_capacity_rows = [
        row
        for row in capacity_rows
        if _quarter_for_month(sapling, row["month"]) in H2_QUARTERS
    ]
    assert h2_capacity_rows
    assert statistics.mean(float(row["blended_ramp_pct"]) for row in h2_capacity_rows) < 0.75

    quarters = _trajectory_quarters(sapling, "capacity_headcount")
    for quarter in H2_QUARTERS:
        plan_aes = float(quarters[quarter]["top_down"]["aes"])
        actual_aes = float(quarters[quarter]["bottoms_up"]["total_aes"])
        assert actual_aes / plan_aes >= 0.95

    assert 0.10 <= _funnel_rate(sapling, "mql_to_s0") <= 0.16
    assert 0.50 <= _funnel_rate(sapling, "s0_to_s1") <= 0.65
    assert 0.40 <= _funnel_rate(sapling, "s1_to_s2") <= 0.55
    assert 0.28 <= sapling["scenario_building_blocks"]["observed_values"]["win_rate"] <= 0.40

    for quarter in ("Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"):
        assert _pipeline_target_coverage(sapling, quarter) >= 2.5

    bookings_quarters = _trajectory_quarters(sapling)
    capacity_gaps = [
        float(bookings_quarters[quarter]["top_down"]["bookings"])
        - float(bookings_quarters[quarter]["bottoms_up"]["sales_led_arr"])
        for quarter in ("Q2FY26", "Q3FY26", "Q4FY26")
    ]
    assert capacity_gaps == sorted(capacity_gaps)
    assert capacity_gaps[0] > 0


def test_mighty_oak_bridge_depends_on_unsupported_expansion_assumptions(
    persona_snapshots: dict[str, dict[str, Any]],
) -> None:
    mighty = persona_snapshots["mighty-oak-holdings"]
    quarters = _trajectory_quarters(mighty)

    plan_expansion = sum(float(row["top_down"]["expansion"] or 0) for row in quarters.values())
    plan_net_new = sum(float(row["top_down"]["total_net_new"] or 0) for row in quarters.values())
    assert plan_net_new > 0
    assert plan_expansion / plan_net_new > 0.45

    expansion_attainment = []
    for quarter, row in quarters.items():
        planned = float(row["top_down"]["expansion"] or 0)
        actual = float(row["expansion_breakdown"]["total_expansion_arr"] or 0)
        assert planned > 0, quarter
        expansion_attainment.append(actual / planned)
    assert max(expansion_attainment) < 0.75

    observed = mighty["scenario_building_blocks"]["observed_values"]
    assert 120 <= float(observed["avg_cycle_days"]) <= 180

    scenario = mighty["target_setter"]["observed_scenario"]
    assert float(scenario["win_rate_created"]) <= 0.22
    assert float(scenario["win_rate_created"]) <= float(scenario["win_rate_starting"]) - 0.10

    aged_open_counts: dict[str, int] = defaultdict(int)
    for deal in mighty["pipeline"]["deals"]:
        quarter = _quarter_for_deal(mighty, deal)
        if quarter not in {"Q2FY26", "Q3FY26", "Q4FY26"}:
            continue
        created_date = deal.get("created_date")
        close_date = deal.get("close_date")
        if not created_date or not close_date:
            continue
        age_days = (
            date.fromisoformat(close_date[:10])
            - date.fromisoformat(created_date[:10])
        ).days
        if age_days >= 150:
            aged_open_counts[quarter] += 1
    assert aged_open_counts["Q2FY26"] < aged_open_counts["Q3FY26"] < aged_open_counts["Q4FY26"]

    assert len(mighty.get("provenance", {})) >= 10
    assert mighty["health_status"]["overall_status"] in {"yellow", "red"}


def test_sprout_rendered_bridge_is_a_visible_coverage_cliff(
    persona_snapshots: dict[str, dict[str, Any]],
) -> None:
    metrics = _rendered_totals(persona_snapshots["sprout-labs"])

    assert 0.85 <= metrics["capacity"] / metrics["plan"] <= 1.15
    assert 0.55 <= metrics["expected"] / metrics["plan"] <= 0.70
    assert statistics.mean(metrics["monthly_expected_to_plan"][:6]) >= 0.80
    assert statistics.mean(metrics["monthly_expected_to_plan"][9:12]) <= 0.65


def test_sapling_rendered_bridge_has_headline_capacity_and_growing_gap(
    persona_snapshots: dict[str, dict[str, Any]],
) -> None:
    metrics = _rendered_totals(persona_snapshots["sapling-industries"])

    assert max(metrics["monthly_expected_to_capacity"]) <= 1 + EPSILON
    assert min(metrics["monthly_capacity_to_plan"]) >= 1
    assert 0.82 <= metrics["expected"] / metrics["plan"] <= 0.92

    gaps = [_quarter_gap(metrics, quarter) for quarter in ("Q2FY26", "Q3FY26", "Q4FY26")]
    assert gaps[0] > 0
    assert gaps[0] < gaps[1] < gaps[2]


def test_mighty_oak_rendered_bridge_stays_below_capacity_and_plan(
    persona_snapshots: dict[str, dict[str, Any]],
) -> None:
    metrics = _rendered_totals(persona_snapshots["mighty-oak-holdings"])
    fy_shortfall = metrics["plan"] - metrics["expected"]
    h2_shortfall = _quarter_gap(metrics, "Q3FY26") + _quarter_gap(metrics, "Q4FY26")
    h1_existing = (
        metrics["quarters"]["Q1FY26"]["existing"]
        + metrics["quarters"]["Q2FY26"]["existing"]
    )
    h1_expected = (
        metrics["quarters"]["Q1FY26"]["expected"]
        + metrics["quarters"]["Q2FY26"]["expected"]
    )

    assert max(metrics["monthly_expected_to_capacity"]) <= 1 + EPSILON
    assert max(metrics["monthly_expected_to_plan"]) <= 1 + EPSILON
    assert 0.80 <= metrics["expected"] / metrics["plan"] <= 0.90
    assert fy_shortfall > 0
    assert h2_shortfall / fy_shortfall >= 0.60
    assert h1_existing / h1_expected >= 0.60


def test_trajectory_quarter_blocks_reconcile_to_rendered_series(
    persona_snapshots: dict[str, dict[str, Any]],
) -> None:
    for profile_id, snapshot in persona_snapshots.items():
        metrics = _rendered_totals(snapshot)
        for quarter_block in snapshot["model_output"]["bookings_bridge"]["trajectory_quarters"]:
            quarter = quarter_block["quarter"]
            if quarter not in FY_QUARTERS:
                continue
            rendered_quarter = metrics["quarters"][quarter]
            top_down = float(quarter_block["top_down"]["bookings"] or 0)
            bottoms_up = float(quarter_block["bottoms_up"]["sales_led_arr"] or 0)

            assert math.isclose(
                top_down,
                rendered_quarter["plan"],
                rel_tol=0.15,
            ), f"{profile_id} {quarter} top_down does not match rendered plan"
            assert math.isclose(
                bottoms_up,
                rendered_quarter["expected"],
                rel_tol=0.15,
            ), f"{profile_id} {quarter} bottoms_up does not match rendered expected"


def test_actual_bookings_reconcile_to_trajectory_quarters(
    persona_snapshots: dict[str, dict[str, Any]],
    acme_snapshot: dict[str, Any],
) -> None:
    """Actual bookings are carried in actuals and every page's quarter blocks."""

    for profile_id, snapshot in _snapshot_cases(persona_snapshots, acme_snapshot).items():
        actuals_total = _bookings_actuals_in_actual_window(snapshot)
        assert actuals_total > 0, f"{profile_id} fixture should carry booking actuals"

        for section in ("bookings_bridge", "capacity_headcount", "funnel_health"):
            quarter_rows = snapshot["model_output"][section]["trajectory_quarters"]
            quarter_total = sum(float(row.get("actual_bookings") or 0) for row in quarter_rows)
            nested_total = sum(
                float((row.get("actuals") or {}).get("bookings") or 0)
                for row in quarter_rows
            )

            assert math.isclose(
                quarter_total,
                actuals_total,
                abs_tol=1.0,
            ), f"{profile_id} {section} flat actual_bookings do not reconcile"
            assert math.isclose(
                nested_total,
                actuals_total,
                abs_tol=1.0,
            ), f"{profile_id} {section} nested actuals.bookings do not reconcile"


def test_quarter_blocks_match_across_page_payloads(
    persona_snapshots: dict[str, dict[str, Any]],
    acme_snapshot: dict[str, Any],
) -> None:
    """The three page payloads carry the same quarter-level core facts."""

    fields = ("td_bookings", "bu_sales_led_arr", "actual_bookings")
    for profile_id, snapshot in _snapshot_cases(persona_snapshots, acme_snapshot).items():
        bridge_rows = _trajectory_quarters(snapshot, "bookings_bridge")
        for section in ("capacity_headcount", "funnel_health"):
            section_rows = _trajectory_quarters(snapshot, section)
            assert set(section_rows) == set(bridge_rows), f"{profile_id} {section} quarter set drifted"
            for quarter, bridge_row in bridge_rows.items():
                section_row = section_rows[quarter]
                for field in fields:
                    assert math.isclose(
                        float(section_row.get(field) or 0),
                        float(bridge_row.get(field) or 0),
                        abs_tol=1.0,
                    ), f"{profile_id} {section} {quarter} {field} drifted from bookings_bridge"


def test_roster_effective_capacity_reconciles_to_capacity_payloads(
    persona_snapshots: dict[str, dict[str, Any]],
    acme_snapshot: dict[str, Any],
) -> None:
    """Capacity is duplicated in roster, Capacity page payload, and scenario blocks."""

    fields = (
        "ae_total",
        "ae_ramped",
        "ae_ramping",
        "se_total",
        "sdr_total",
        "ae_capacity",
        "ae_capacity_ramped",
        "ae_capacity_ramping",
        "blended_ramp_pct",
    )

    for profile_id, snapshot in _snapshot_cases(persona_snapshots, acme_snapshot).items():
        roster_rows = {
            row["month"][:10]: row for row in snapshot["roster"]["effective_capacity"]
        }
        capacity_rows = {
            row["month"][:10]: row
            for row in snapshot["model_output"]["capacity_headcount"]["trajectory_capacity"]
        }
        assert capacity_rows.keys() == roster_rows.keys(), f"{profile_id} capacity month set drifted"

        for month, roster_row in roster_rows.items():
            capacity_row = capacity_rows[month]
            for field in fields:
                assert math.isclose(
                    float(capacity_row.get(field) or 0),
                    float(roster_row.get(field) or 0),
                    abs_tol=1e-6,
                ), f"{profile_id} {month} {field} drifted between roster and capacity page"

        building_blocks = snapshot["scenario_building_blocks"]
        for idx, month in enumerate(building_blocks["months"]):
            month_key = month[:10]
            if month_key not in roster_rows:
                continue
            roster_row = roster_rows[month_key]
            assert math.isclose(
                float(building_blocks["monthly_ae_capacity"][idx] or 0),
                float(roster_row.get("ae_capacity") or 0),
                abs_tol=1e-6,
            ), f"{profile_id} {month_key} scenario capacity drifted"
            assert math.isclose(
                float(building_blocks["monthly_ae_count"][idx] or 0),
                float(roster_row.get("ae_total") or 0),
                abs_tol=1e-6,
            ), f"{profile_id} {month_key} scenario AE count drifted"

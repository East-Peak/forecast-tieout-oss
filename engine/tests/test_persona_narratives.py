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

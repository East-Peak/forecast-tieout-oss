"""Regenerate shared scenario golden vectors.

Regeneration is legitimate when docs/scenario-formulas.md changes, when a
public persona snapshot intentionally changes its scenario_building_blocks, or
when a vector category is added to cover a newly specified edge case. Run with
--verify in CI; without it, review the resulting git diff before committing.

This script is the independent contract implementation for the vectors. It does
not import the Python runtime scenario service or the TypeScript planner.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
VECTOR_PATH = ROOT / "tests/parity/fixtures/scenario-golden-vectors.json"
PUBLIC_PROFILE_ROOT = ROOT / "frontend/public/data/profiles"
PUBLIC_PROFILE_IDS = ("sprout-labs", "sapling-industries", "mighty-oak-holdings")


def number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return fallback


def integer(value: Any, fallback: int = 0) -> int:
    return int(round(number(value, float(fallback))))


def cumulative(values: list[float]) -> list[float]:
    result: list[float] = []
    running = 0.0
    for value in values:
        running += value
        result.append(running)
    return result


def stack_cohorts(monthly_creation: list[float], decay_curve: list[float]) -> list[float]:
    result = [0.0] * (len(monthly_creation) + len(decay_curve) - 1)
    for month_index, creation in enumerate(monthly_creation):
        for bucket_index, rate in enumerate(decay_curve):
            result[month_index + bucket_index] += creation * rate
    return result


def apply_capacity_ceiling(expected: list[float], capacity: list[float]) -> list[float]:
    result = [0.0] * len(expected)
    carry = 0.0
    for index, value in enumerate(expected):
        available = value + carry
        month_capacity = capacity[index] if index < len(capacity) else 0.0
        if available <= month_capacity:
            result[index] = available
            carry = 0.0
        else:
            result[index] = month_capacity
            carry = available - month_capacity
    return result


def compute_overflow(expected: list[float], capacity: list[float]) -> list[float]:
    result = [0.0] * len(expected)
    carry = 0.0
    for index, value in enumerate(expected):
        available = value + carry
        month_capacity = capacity[index] if index < len(capacity) else 0.0
        if available <= month_capacity:
            result[index] = 0.0
            carry = 0.0
        else:
            carry = available - month_capacity
            result[index] = carry
    return result


def first_projected_month_index(snapshot: Mapping[str, Any]) -> int:
    flags = list(snapshot["scenario_building_blocks"]["monthly_is_actual"])
    for index, is_actual in enumerate(flags):
        if not is_actual:
            return index
    return len(flags)


def quarter_by_month(snapshot: Mapping[str, Any]) -> list[str | None]:
    bb = snapshot["scenario_building_blocks"]
    months = list(bb["months"])
    raw = bb.get("quarter_by_month")
    if isinstance(raw, list) and len(raw) == len(months):
        return [str(value) if isinstance(value, str) else None for value in raw]
    return [None] * len(months)


def overridable_quarters(snapshot: Mapping[str, Any]) -> list[str]:
    raw = snapshot["scenario_building_blocks"].get("overridable_quarters")
    if not isinstance(raw, list):
        return []
    return [value for value in raw if isinstance(value, str)]


def quarter_indexes(snapshot: Mapping[str, Any], quarter: str) -> list[int]:
    return [index for index, value in enumerate(quarter_by_month(snapshot)) if value == quarter]


def observed_ramp_curve(snapshot: Mapping[str, Any]) -> dict[int, float]:
    curve_source = (
        ((snapshot.get("roster") or {}).get("observed_ramp_curve") or {}).get("curve_by_segment_serialized")
        or ((snapshot.get("roster") or {}).get("observed_ramp_curve") or {}).get("curve_by_segment")
        or {}
    )
    enterprise = curve_source.get("enterprise") if isinstance(curve_source, Mapping) else None
    if not isinstance(enterprise, Mapping):
        return {}
    parsed: dict[int, float] = {}
    for raw_key, raw_value in enterprise.items():
        key = str(raw_key)
        month = int(key[6:] if key.startswith("month_") else key)
        parsed[month] = number(raw_value)
    return parsed


def ramp_factor(curve: Mapping[int, float], months_since_start: int) -> float:
    key = months_since_start + 1
    if key in curve:
        return number(curve[key])
    max_key = max([0, *curve.keys()])
    if max_key == 0:
        return 1.0 if months_since_start >= 5 else 0.0
    if key > max_key:
        return number(curve[max_key], 1.0)
    return 0.0


def future_generation_win_rates(snapshot: Mapping[str, Any], length: int) -> list[float]:
    provenance = (((snapshot.get("model_output") or {}).get("bookings_bridge") or {}).get("provenance") or {})
    raw = provenance.get("future_generation_win_rates") if isinstance(provenance, Mapping) else None
    rates = [number(value) for value in raw] if isinstance(raw, list) else []
    fallback = number((snapshot.get("rates") or {}).get("overall_win_rate"), 0.0)
    return [rates[index] if index < len(rates) else fallback for index in range(length)]


def capacity_per_ae(snapshot: Mapping[str, Any]) -> list[float]:
    bb = snapshot["scenario_building_blocks"]
    raw: list[float] = []
    for index, capacity in enumerate(bb["monthly_ae_capacity"]):
        ae_count = number(bb["monthly_ae_count"][index], 0.0)
        raw.append(0.0 if ae_count <= 0 else number(capacity) / ae_count)
    non_zero = [value for value in raw if value > 0]
    fallback = non_zero[-1] if non_zero else 0.0
    return [value if value > 0 else fallback for value in raw]


def default_overrides(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    bb = snapshot["scenario_building_blocks"]
    base_rates = (snapshot.get("rates") or {}).get("funnel_rates") or {}
    ae_counts = [number(value) for value in bb["monthly_ae_count"]]
    avg_deal_size = number((bb.get("observed_values") or {}).get("avg_deal_size"), 300_000.0)

    result: dict[str, dict[str, Any]] = {}
    for quarter in overridable_quarters(snapshot):
        values = [ae_counts[index] if index < len(ae_counts) else 0.0 for index in quarter_indexes(snapshot, quarter)]
        fallback = values[-1] if values else 0.0
        result[quarter] = {
            "addAes": 0,
            "aeMonthTargets": [
                values[0] if len(values) > 0 else fallback,
                values[1] if len(values) > 1 else fallback,
                values[2] if len(values) > 2 else fallback,
            ],
            "mqlChangePct": 0.0,
            "mqlToS0": number(base_rates.get("mql_to_s0"), 0.0),
            "s0ToS1": number(base_rates.get("s0_to_s1"), 0.0),
            "s1ToS2": number(base_rates.get("s1_to_s2"), 0.0),
            "avgDealSize": avg_deal_size,
        }
    return result


def normalized_overrides(
    snapshot: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    defaults = default_overrides(snapshot)
    if not overrides:
        return defaults
    normalized: dict[str, dict[str, Any]] = {}
    for quarter in overridable_quarters(snapshot):
        baseline = defaults[quarter]
        raw = overrides.get(quarter)
        if not isinstance(raw, Mapping):
            normalized[quarter] = copy.deepcopy(baseline)
            continue
        normalized[quarter] = {
            "addAes": integer(raw.get("addAes"), integer(baseline["addAes"])),
            "aeMonthTargets": [
                integer(raw["aeMonthTargets"][index], integer(baseline["aeMonthTargets"][index]))
                if isinstance(raw.get("aeMonthTargets"), list) and len(raw["aeMonthTargets"]) == 3
                else integer(baseline["aeMonthTargets"][index])
                for index in range(3)
            ],
            "mqlChangePct": number(raw.get("mqlChangePct"), number(baseline["mqlChangePct"])),
            "mqlToS0": number(raw.get("mqlToS0"), number(baseline["mqlToS0"])),
            "s0ToS1": number(raw.get("s0ToS1"), number(baseline["s0ToS1"])),
            "s1ToS2": number(raw.get("s1ToS2"), number(baseline["s1ToS2"])),
            "avgDealSize": number(raw.get("avgDealSize"), number(baseline["avgDealSize"])),
        }
    return normalized


def reference_compute(
    snapshot: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized = normalized_overrides(snapshot, overrides)
    bb = snapshot["scenario_building_blocks"]
    months = list(bb["months"])
    month_count = len(months)
    first_projected = first_projected_month_index(snapshot)

    inventory_wins = [number(value) for value in bb["monthly_inventory_wins"]]
    baseline_future_wins = [number(value) for value in bb["monthly_future_wins"]]
    ae_creation = [number(value) for value in bb["monthly_ae_creation"]]
    mql_creation = [number(value) for value in bb["monthly_mql_creation"]]
    monthly_capacity = [number(value) for value in bb["monthly_ae_capacity"]]
    monthly_ae_count = [number(value) for value in bb["monthly_ae_count"]]
    baseline_ae_count = list(monthly_ae_count)

    observed_values = bb.get("observed_values") or {}
    base_avg_deal_size = number(observed_values.get("avg_deal_size"), 300_000.0)
    observed_ae_productivity = number(observed_values.get("productivity_per_ae_per_month"), 0.0)
    funnel_rates = bb.get("funnel_rates") or {}
    base_mql_to_s0 = number(funnel_rates.get("mql_to_s0"), 0.0)
    base_s0_to_s1 = number(funnel_rates.get("s0_to_s1"), 0.0)
    base_s1_to_s2 = number(funnel_rates.get("s1_to_s2"), 0.0)
    base_ae_factor = base_avg_deal_size * base_s0_to_s1 * base_s1_to_s2
    base_mql_factor = base_mql_to_s0 * base_ae_factor
    baseline_pipeline_created = [
        ae_value + (mql_creation[index] if index < len(mql_creation) else 0.0)
        for index, ae_value in enumerate(ae_creation)
    ]

    ae_cohorts: list[dict[str, int]] = []
    carried_monthly_extra_aes = 0
    for quarter in overridable_quarters(snapshot):
        for month_offset, month_index in enumerate(quarter_indexes(snapshot, quarter)):
            if month_index < first_projected:
                continue
            desired_total = max(
                number(normalized[quarter]["aeMonthTargets"][month_offset], monthly_ae_count[month_index]),
                monthly_ae_count[month_index],
            )
            raw_extra_aes = max(0, int(round(desired_total - baseline_ae_count[month_index])))
            effective_extra_aes = max(raw_extra_aes, carried_monthly_extra_aes)
            month_cohort_count = effective_extra_aes - carried_monthly_extra_aes
            if month_cohort_count > 0:
                ae_cohorts.append({"startIndex": month_index, "count": month_cohort_count})
            carried_monthly_extra_aes = effective_extra_aes

    qbm = quarter_by_month(snapshot)
    for quarter in overridable_quarters(snapshot):
        start_index = next((index for index, value in enumerate(qbm) if value == quarter), -1)
        if start_index == -1:
            continue
        count = max(0, integer(normalized[quarter]["addAes"], 0))
        if count > 0:
            ae_cohorts.append({"startIndex": start_index, "count": count})

    ramp = observed_ramp_curve(snapshot)
    per_ae_capacity = capacity_per_ae(snapshot)
    for index in range(first_projected, month_count):
        extra_ae_creation = 0.0
        extra_capacity = 0.0
        extra_headcount = 0.0
        for cohort in ae_cohorts:
            if index < cohort["startIndex"]:
                continue
            factor = ramp_factor(ramp, index - cohort["startIndex"])
            extra_headcount += cohort["count"]
            extra_ae_creation += (
                observed_ae_productivity
                * cohort["count"]
                * factor
                * base_s0_to_s1
                * base_s1_to_s2
                * base_avg_deal_size
            )
            extra_capacity += (per_ae_capacity[index] if index < len(per_ae_capacity) else 0.0) * cohort["count"] * factor
        ae_creation[index] += extra_ae_creation
        monthly_capacity[index] += extra_capacity
        monthly_ae_count[index] += extra_headcount

    for index in range(first_projected, month_count):
        quarter = qbm[index] if index < len(qbm) else None
        if quarter not in overridable_quarters(snapshot):
            continue
        override = normalized[quarter]
        effective_ae_factor = (
            number(override["avgDealSize"], base_avg_deal_size)
            * number(override["s0ToS1"], base_s0_to_s1)
            * number(override["s1ToS2"], base_s1_to_s2)
        )
        effective_mql_factor = number(override["mqlToS0"], base_mql_to_s0) * effective_ae_factor
        ae_scale = effective_ae_factor / base_ae_factor if base_ae_factor > 0 else 1.0
        mql_scale = effective_mql_factor / base_mql_factor if base_mql_factor > 0 else 1.0
        mql_volume_scale = max(0.0, 1.0 + number(override["mqlChangePct"], 0.0))
        ae_creation[index] *= ae_scale
        mql_creation[index] *= mql_scale * mql_volume_scale

    monthly_pipeline_created = [
        ae_value + (mql_creation[index] if index < len(mql_creation) else 0.0)
        for index, ae_value in enumerate(ae_creation)
    ]
    win_rates = future_generation_win_rates(snapshot, month_count)
    win_adjusted_creation_delta = [
        (value - (baseline_pipeline_created[index] if index < len(baseline_pipeline_created) else 0.0))
        * (win_rates[index] if index < len(win_rates) else 0.0)
        for index, value in enumerate(monthly_pipeline_created)
    ]
    future_wins_delta = stack_cohorts(win_adjusted_creation_delta, [number(value) for value in bb["decay_curve"]])[
        :month_count
    ]
    future_wins = [
        baseline_value + (future_wins_delta[index] if index < len(future_wins_delta) else 0.0)
        for index, baseline_value in enumerate(baseline_future_wins)
    ]

    for index in range(first_projected):
        ae_creation[index] = number(bb["monthly_ae_creation"][index])
        mql_creation[index] = number(bb["monthly_mql_creation"][index])
        monthly_pipeline_created[index] = ae_creation[index] + mql_creation[index]
        future_wins[index] = baseline_future_wins[index]
        monthly_capacity[index] = number(bb["monthly_ae_capacity"][index])
        monthly_ae_count[index] = number(bb["monthly_ae_count"][index])

    monthly_expected = [
        inventory_value + (future_wins[index] if index < len(future_wins) else 0.0)
        for index, inventory_value in enumerate(inventory_wins)
    ]
    for index in range(first_projected):
        monthly_expected[index] = number(bb["monthly_total_expected"][index], monthly_expected[index])

    monthly_capped = apply_capacity_ceiling(monthly_expected, monthly_capacity)
    monthly_overflow = compute_overflow(monthly_expected, monthly_capacity)
    for index in range(first_projected):
        monthly_capped[index] = number(bb["monthly_capped"][index], monthly_expected[index])
        monthly_overflow[index] = 0.0

    return {
        "months": months,
        "monthly_inventory_wins": inventory_wins,
        "monthly_future_wins": future_wins,
        "monthly_pipeline_created": monthly_pipeline_created,
        "monthly_ae_creation": ae_creation,
        "monthly_mql_creation": mql_creation,
        "monthly_expected": monthly_expected,
        "monthly_capped": monthly_capped,
        "monthly_capacity": monthly_capacity,
        "monthly_ae_count": monthly_ae_count,
        "monthly_overflow": monthly_overflow,
        "cumulative_expected": cumulative(monthly_expected),
        "cumulative_capped": cumulative(monthly_capped),
        "fy_expected": sum(monthly_expected),
        "fy_capped": sum(monthly_capped),
    }


def minimal_snapshot(
    profile_id: str,
    building_blocks: dict[str, Any],
    *,
    overall_win_rate: float = 0.25,
    future_generation_rates: list[float] | None = None,
    ramp_curve: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "golden-vector-v1",
        "engine_version": "contract-reference",
        "profile_id": profile_id,
        "rates": {
            "overall_win_rate": overall_win_rate,
            "funnel_rates": copy.deepcopy(building_blocks.get("funnel_rates") or {}),
        },
        "roster": {
            "observed_ramp_curve": {
                "curve_by_segment_serialized": {
                    "enterprise": ramp_curve if ramp_curve is not None else {}
                }
            }
        },
        "model_output": {
            "bookings_bridge": {
                "provenance": (
                    {"future_generation_win_rates": future_generation_rates}
                    if future_generation_rates is not None
                    else {}
                )
            }
        },
        "scenario_building_blocks": copy.deepcopy(building_blocks),
    }


def base_blocks() -> dict[str, Any]:
    return {
        "months": [
            "2026-01-01",
            "2026-02-01",
            "2026-03-01",
            "2026-04-01",
            "2026-05-01",
            "2026-06-01",
        ],
        "quarter_by_month": ["Q4FY25", "Q1FY26", "Q1FY26", "Q1FY26", "Q2FY26", "Q2FY26"],
        "overridable_quarters": ["Q1FY26", "Q2FY26"],
        "monthly_is_actual": [True, True, False, False, False, False],
        "monthly_inventory_wins": [40_000, 55_000, 90_000, 110_000, 70_000, 60_000],
        "monthly_future_wins": [0, 10_000, 20_000, 30_000, 40_000, 50_000],
        "monthly_ae_creation": [0, 30_000, 60_000, 65_000, 75_000, 80_000],
        "monthly_mql_creation": [0, 10_000, 20_000, 22_000, 24_000, 26_000],
        "monthly_total_expected": [40_000, 65_000, 110_000, 140_000, 110_000, 110_000],
        "monthly_capped": [40_000, 65_000, 100_000, 120_000, 110_000, 110_000],
        "monthly_ae_capacity": [80_000, 100_000, 100_000, 120_000, 150_000, 160_000],
        "monthly_ae_count": [2, 2, 3, 3, 4, 4],
        "decay_curve": [0.5, 0.3, 0.2],
        "observed_values": {
            "avg_deal_size": 100_000,
            "productivity_per_ae_per_month": 2.0,
        },
        "funnel_rates": {
            "mql_to_s0": 0.5,
            "s0_to_s1": 0.4,
            "s1_to_s2": 0.25,
        },
    }


def make_case(
    case_id: str,
    category: str,
    snapshot: dict[str, Any],
    overrides: dict[str, Any] | None,
    rationale: str,
) -> dict[str, Any]:
    actual_overrides = normalized_overrides(snapshot, overrides)
    return {
        "id": case_id,
        "category": category,
        "rationale": rationale,
        "input": {
            "snapshot": snapshot,
            "overrides": actual_overrides,
        },
        "expected": {
            "result": reference_compute(snapshot, actual_overrides),
        },
    }


def synthetic_cases() -> list[dict[str, Any]]:
    blocks = base_blocks()
    default_snapshot = minimal_snapshot(
        "synthetic-default",
        blocks,
        future_generation_rates=[0.2, 0.22, 0.24, 0.26, 0.28, 0.3],
        ramp_curve={"month_1": 0.2, "month_2": 0.5, "month_3": 0.8, "month_4": 1.0},
    )

    extreme_overrides = default_overrides(default_snapshot)
    extreme_overrides["Q1FY26"]["addAes"] = 3
    extreme_overrides["Q1FY26"]["aeMonthTargets"] = [2, 3, 6]
    extreme_overrides["Q1FY26"]["mqlChangePct"] = 1.75
    extreme_overrides["Q1FY26"]["mqlToS0"] = 0.8
    extreme_overrides["Q1FY26"]["s0ToS1"] = 0.65
    extreme_overrides["Q1FY26"]["s1ToS2"] = 0.5
    extreme_overrides["Q1FY26"]["avgDealSize"] = 250_000
    extreme_overrides["Q2FY26"]["mqlChangePct"] = -1.0
    extreme_overrides["Q2FY26"]["mqlToS0"] = 0.0

    zero_blocks = base_blocks()
    for key in (
        "monthly_inventory_wins",
        "monthly_future_wins",
        "monthly_ae_creation",
        "monthly_mql_creation",
        "monthly_total_expected",
        "monthly_capped",
        "monthly_ae_capacity",
        "monthly_ae_count",
    ):
        zero_blocks[key] = [0, 0, 0, 0, 0, 0]
    zero_blocks["monthly_is_actual"] = [False, False, False, False, False, False]
    zero_snapshot = minimal_snapshot(
        "synthetic-zero-pipeline",
        zero_blocks,
        overall_win_rate=0.0,
        future_generation_rates=[0, 0, 0, 0, 0, 0],
    )

    missing_optional_blocks = base_blocks()
    missing_optional_blocks.pop("overridable_quarters")
    missing_optional_blocks.pop("quarter_by_month")
    missing_optional_snapshot = minimal_snapshot("synthetic-missing-optional", missing_optional_blocks)

    boundary_blocks = base_blocks()
    boundary_blocks["monthly_is_actual"] = [True, True, True, False, False, False]
    boundary_blocks["quarter_by_month"] = ["Q1FY26", "Q1FY26", "Q1FY26", "Q2FY26", "Q2FY26", "Q2FY26"]
    boundary_blocks["overridable_quarters"] = ["Q1FY26", "Q2FY26"]
    boundary_snapshot = minimal_snapshot(
        "synthetic-boundary-months",
        boundary_blocks,
        future_generation_rates=[0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
        ramp_curve={"month_1": 1.0},
    )
    boundary_overrides = default_overrides(boundary_snapshot)
    boundary_overrides["Q1FY26"]["addAes"] = 10
    boundary_overrides["Q1FY26"]["avgDealSize"] = 1_000_000
    boundary_overrides["Q2FY26"]["aeMonthTargets"] = [7, 8, 9]

    return [
        make_case(
            "synthetic-default-noop",
            "contract baseline",
            default_snapshot,
            default_overrides(default_snapshot),
            "No-op override must preserve saved actual months while recomputing projected months.",
        ),
        make_case(
            "synthetic-extreme-overrides",
            "edge: extreme overrides",
            default_snapshot,
            extreme_overrides,
            "High upside, MQL shutoff, added AE cohorts, and capacity overflow in one case.",
        ),
        make_case(
            "synthetic-zero-pipeline-zero-win-rate",
            "edge: zero pipeline and zero win rate",
            zero_snapshot,
            default_overrides(zero_snapshot),
            "All-zero pipeline, capacity, AE count, and future win rates must remain zero.",
        ),
        make_case(
            "synthetic-boundary-actual-to-projected-quarter",
            "edge: boundary months and quarters",
            boundary_snapshot,
            boundary_overrides,
            "A Q1 override cannot mutate actual Q1 months; Q2 overrides begin at the first projected quarter month.",
        ),
        make_case(
            "synthetic-missing-optional-quarter-blocks",
            "edge: empty/missing optional blocks",
            missing_optional_snapshot,
            default_overrides(missing_optional_snapshot),
            "Missing overridable_quarters and quarter_by_month means no quarter edits are applied.",
        ),
    ]


def load_persona_snapshot(profile_id: str) -> dict[str, Any]:
    raw = json.loads((PUBLIC_PROFILE_ROOT / profile_id / "snapshot.json").read_text(encoding="utf-8"))
    return {
        "schema_version": raw.get("schema_version", "golden-vector-v1"),
        "engine_version": raw.get("engine_version", "committed-snapshot"),
        "profile_id": profile_id,
        "rates": copy.deepcopy(raw["rates"]),
        "roster": {
            "observed_ramp_curve": copy.deepcopy((raw.get("roster") or {}).get("observed_ramp_curve") or {})
        },
        "model_output": {
            "bookings_bridge": {
                "provenance": copy.deepcopy(
                    (((raw.get("model_output") or {}).get("bookings_bridge") or {}).get("provenance") or {})
                )
            }
        },
        "scenario_building_blocks": copy.deepcopy(raw["scenario_building_blocks"]),
    }


def persona_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for profile_id in PUBLIC_PROFILE_IDS:
        snapshot = load_persona_snapshot(profile_id)
        overrides = default_overrides(snapshot)
        for quarter in list(overrides)[:1]:
            overrides[quarter]["mqlChangePct"] = 0.15
        for quarter in list(overrides)[1:2]:
            overrides[quarter]["s0ToS1"] *= 0.9
            overrides[quarter]["s1ToS2"] *= 0.9
        cases.append(
            make_case(
                f"persona-{profile_id}-committed-snapshot",
                "public persona committed scenario_building_blocks",
                snapshot,
                overrides,
                f"{profile_id} real committed scenario_building_blocks with representative override.",
            )
        )
    return cases


def build_vectors() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "contract": {
            "doc": "docs/scenario-formulas.md",
            "summary": "Shared golden vectors for Python and TypeScript snapshot scenario engines.",
        },
        "tolerancePolicy": {
            "integers": "exact",
            "countFields": ["monthly_ae_count"],
            "floats": {
                "mode": "max(absoluteEpsilon, relativeEpsilon * max(1, abs(expected)))",
                "absoluteEpsilon": 1e-6,
                "relativeEpsilon": 1e-9,
            },
        },
        "cases": synthetic_cases() + persona_cases(),
    }


def render_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Regenerate vectors in memory and fail if the committed fixture differs.",
    )
    args = parser.parse_args()

    rendered = render_json(build_vectors())
    if args.verify:
        current = VECTOR_PATH.read_text(encoding="utf-8")
        if current != rendered:
            print(
                "scenario-golden-vectors.json is stale; run "
                "`python -m tests.parity.generate_scenario_golden_vectors` and review the diff."
            )
            return 1
        print("scenario-golden-vectors.json is current")
        return 0

    VECTOR_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {VECTOR_PATH.relative_to(ROOT)}")
    print("Review the git diff before committing regenerated vectors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

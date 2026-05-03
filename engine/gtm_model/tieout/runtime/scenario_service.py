"""Profile-scoped scenario planner service built on exported snapshot bundles.

This service mirrors the current planner semantics against a saved snapshot so
the what-if contract lives in Python as well as the frontend. It is the first
step toward a canonical backend/API boundary for scenario recompute.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from gtm_model.tieout.runtime.bundle_store import (
    default_frontend_profile_data_root,
    resolve_profile_bundle_store,
)
from gtm_model.tieout.runtime.profile import (
    load_org_profile,
)

def _overridable_quarters(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    """Read the overridable-quarter list from the snapshot. Returns an empty
    tuple if the snapshot does not declare it — callers should treat that as
    'no quarters editable' rather than substituting a default."""
    bb = snapshot.get("scenario_building_blocks") or {}
    raw = bb.get("overridable_quarters")
    if isinstance(raw, list):
        return tuple(str(q) for q in raw if isinstance(q, str))
    return ()


def _quarter_by_month(snapshot: Mapping[str, Any]) -> tuple[str | None, ...]:
    """Parallel array to `months`, mapping each month to its quarter label."""
    bb = snapshot.get("scenario_building_blocks") or {}
    months = list(bb.get("months") or [])
    raw = bb.get("quarter_by_month")
    if isinstance(raw, list) and len(raw) == len(months):
        return tuple((str(q) if isinstance(q, str) else None) for q in raw)
    return tuple(None for _ in months)


@dataclass(frozen=True)
class SnapshotScenarioQuarterOverride:
    add_aes: int
    ae_month_targets: tuple[int, int, int]
    mql_change_pct: float
    mql_to_s0: float
    s0_to_s1: float
    s1_to_s2: float
    avg_deal_size: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "addAes": self.add_aes,
            "aeMonthTargets": list(self.ae_month_targets),
            "mqlChangePct": self.mql_change_pct,
            "mqlToS0": self.mql_to_s0,
            "s0ToS1": self.s0_to_s1,
            "s1ToS2": self.s1_to_s2,
            "avgDealSize": self.avg_deal_size,
        }


@dataclass(frozen=True)
class SnapshotScenarioResult:
    months: list[str]
    monthly_inventory_wins: list[float]
    monthly_future_wins: list[float]
    monthly_pipeline_created: list[float]
    monthly_ae_creation: list[float]
    monthly_mql_creation: list[float]
    monthly_expected: list[float]
    monthly_capped: list[float]
    monthly_capacity: list[float]
    monthly_ae_count: list[float]
    monthly_overflow: list[float]
    cumulative_expected: list[float]
    cumulative_capped: list[float]
    fy_expected: float
    fy_capped: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "months": list(self.months),
            "monthly_inventory_wins": list(self.monthly_inventory_wins),
            "monthly_future_wins": list(self.monthly_future_wins),
            "monthly_pipeline_created": list(self.monthly_pipeline_created),
            "monthly_ae_creation": list(self.monthly_ae_creation),
            "monthly_mql_creation": list(self.monthly_mql_creation),
            "monthly_expected": list(self.monthly_expected),
            "monthly_capped": list(self.monthly_capped),
            "monthly_capacity": list(self.monthly_capacity),
            "monthly_ae_count": list(self.monthly_ae_count),
            "monthly_overflow": list(self.monthly_overflow),
            "cumulative_expected": list(self.cumulative_expected),
            "cumulative_capped": list(self.cumulative_capped),
            "fy_expected": self.fy_expected,
            "fy_capped": self.fy_capped,
        }


def _sum(values: list[float]) -> float:
    return sum(values)


def _to_number(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value_float = float(value)
        if value_float == value_float and value_float not in (float("inf"), float("-inf")):
            return value_float
    return fallback


def _to_int(value: Any, fallback: int = 0) -> int:
    return int(round(_to_number(value, float(fallback))))


def get_quarter_month_indexes_from_snapshot(
    snapshot: Mapping[str, Any], quarter: str
) -> list[int]:
    """Return indexes of months in the snapshot that belong to `quarter`,
    using the snapshot's `quarter_by_month` parallel array."""
    qbm = _quarter_by_month(snapshot)
    return [index for index, q in enumerate(qbm) if q == quarter]


def _first_projected_month_index(snapshot: Mapping[str, Any]) -> int:
    flags = list(snapshot["scenario_building_blocks"]["monthly_is_actual"])
    for index, flag in enumerate(flags):
        if not flag:
            return index
    return len(flags)


def _stack_cohorts(monthly_creation: list[float], decay_curve: list[float]) -> list[float]:
    result = [0.0] * (len(monthly_creation) + len(decay_curve) - 1)
    for month_index, creation in enumerate(monthly_creation):
        for bucket_index, rate in enumerate(decay_curve):
            result[month_index + bucket_index] += creation * rate
    return result


def _apply_capacity_ceiling(expected: list[float], capacity: list[float]) -> list[float]:
    result = [0.0] * len(expected)
    carry = 0.0

    for index, value in enumerate(expected):
        available = value + carry
        month_capacity = capacity[index] if index < len(capacity) else 0.0
        if available <= month_capacity:
            result[index] = available
            carry = 0.0
            continue
        result[index] = month_capacity
        carry = available - month_capacity

    return result


def _compute_overflow(expected: list[float], capacity: list[float]) -> list[float]:
    overflow = [0.0] * len(expected)
    carry = 0.0

    for index, value in enumerate(expected):
        available = value + carry
        month_capacity = capacity[index] if index < len(capacity) else 0.0
        if available <= month_capacity:
            overflow[index] = 0.0
            carry = 0.0
            continue
        overflow[index] = available - month_capacity
        carry = overflow[index]

    return overflow


def _get_observed_ramp_curve(snapshot: Mapping[str, Any]) -> dict[int, float]:
    roster = snapshot.get("roster") or {}
    observed_ramp_curve = roster.get("observed_ramp_curve") or {}
    curve_source = (
        observed_ramp_curve.get("curve_by_segment_serialized")
        or observed_ramp_curve.get("curve_by_segment")
        or {}
    )
    enterprise_curve = curve_source.get("enterprise") or {}
    parsed: dict[int, float] = {}
    for key, value in enterprise_curve.items():
        key_str = str(key)
        if key_str.startswith("month_"):
            month = int(key_str[6:])
        else:
            month = int(key_str)
        parsed[month] = _to_number(value)
    return parsed


def _get_ramp_factor(curve: dict[int, float], months_since_start: int) -> float:
    key = months_since_start + 1
    if key in curve:
        return _to_number(curve[key], 0.0)
    max_key = max([0, *curve.keys()])
    if max_key == 0:
        return 1.0 if months_since_start >= 5 else 0.0
    if key > max_key:
        return _to_number(curve[max_key], 1.0)
    return 0.0


def _get_future_generation_win_rates(snapshot: Mapping[str, Any], length: int) -> list[float]:
    provenance = (((snapshot.get("model_output") or {}).get("bookings_bridge") or {}).get("provenance") or {})
    raw_rates = provenance.get("future_generation_win_rates")
    if isinstance(raw_rates, list):
        win_rates = [_to_number(value) for value in raw_rates]
    else:
        win_rates = []
    fallback = _to_number(((snapshot.get("rates") or {}).get("overall_win_rate")), 0.0)
    return [win_rates[index] if index < len(win_rates) else fallback for index in range(length)]


def _estimate_capacity_per_ae(snapshot: Mapping[str, Any]) -> list[float]:
    building_blocks = snapshot["scenario_building_blocks"]
    raw = []
    for index, capacity in enumerate(building_blocks["monthly_ae_capacity"]):
        ae_count = _to_number(building_blocks["monthly_ae_count"][index], 0.0)
        raw.append(0.0 if ae_count <= 0 else _to_number(capacity) / ae_count)
    non_zero = [value for value in raw if value > 0]
    fallback = non_zero[-1] if non_zero else 0.0
    return [value if value > 0 else fallback for value in raw]


def _cumulative(values: list[float]) -> list[float]:
    result: list[float] = []
    running = 0.0
    for value in values:
        running += value
        result.append(running)
    return result


def _coerce_ae_month_targets(raw_value: Any, baseline: tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(raw_value, list) and len(raw_value) == 3:
        return tuple(_to_int(value, baseline[index]) for index, value in enumerate(raw_value))  # type: ignore[return-value]
    if isinstance(raw_value, tuple) and len(raw_value) == 3:
        return tuple(_to_int(value, baseline[index]) for index, value in enumerate(raw_value))  # type: ignore[return-value]
    return baseline


def build_default_snapshot_scenario_overrides(
    snapshot: Mapping[str, Any],
) -> dict[str, SnapshotScenarioQuarterOverride]:
    base_rates = ((snapshot.get("rates") or {}).get("funnel_rates") or {})
    months = list(snapshot["scenario_building_blocks"]["months"])
    ae_counts = [_to_int(value, 0) for value in snapshot["scenario_building_blocks"]["monthly_ae_count"]]
    avg_deal_size = _to_number(
        ((snapshot["scenario_building_blocks"].get("observed_values") or {}).get("avg_deal_size")),
        300_000.0,
    )

    def build_ae_targets(quarter: str) -> tuple[int, int, int]:
        indexes = get_quarter_month_indexes_from_snapshot(snapshot, quarter)
        values = [ae_counts[index] if index < len(ae_counts) else 0 for index in indexes]
        fallback = values[-1] if values else 0
        padded = [
            values[0] if len(values) > 0 else fallback,
            values[1] if len(values) > 1 else fallback,
            values[2] if len(values) > 2 else fallback,
        ]
        return tuple(padded)  # type: ignore[return-value]

    defaults: dict[str, SnapshotScenarioQuarterOverride] = {}
    for quarter in _overridable_quarters(snapshot):
        defaults[quarter] = SnapshotScenarioQuarterOverride(
            add_aes=0,
            ae_month_targets=build_ae_targets(quarter),
            mql_change_pct=0.0,
            mql_to_s0=_to_number(base_rates.get("mql_to_s0"), 0.0),
            s0_to_s1=_to_number(base_rates.get("s0_to_s1"), 0.0),
            s1_to_s2=_to_number(base_rates.get("s1_to_s2"), 0.0),
            avg_deal_size=avg_deal_size,
        )
    return defaults


def normalize_snapshot_scenario_overrides(
    snapshot: Mapping[str, Any],
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, SnapshotScenarioQuarterOverride]:
    defaults = build_default_snapshot_scenario_overrides(snapshot)
    if not overrides:
        return defaults

    raw_quarters = overrides.get("quarters") if isinstance(overrides, Mapping) else None
    if not isinstance(raw_quarters, Mapping):
        raw_quarters = overrides

    normalized: dict[str, SnapshotScenarioQuarterOverride] = {}
    for quarter in _overridable_quarters(snapshot):
        baseline = defaults[quarter]
        raw_quarter = raw_quarters.get(quarter) if isinstance(raw_quarters, Mapping) else None
        if not isinstance(raw_quarter, Mapping):
            normalized[quarter] = baseline
            continue
        normalized[quarter] = SnapshotScenarioQuarterOverride(
            add_aes=_to_int(raw_quarter.get("add_aes", raw_quarter.get("addAes")), baseline.add_aes),
            ae_month_targets=_coerce_ae_month_targets(
                raw_quarter.get("ae_month_targets", raw_quarter.get("aeMonthTargets")),
                baseline.ae_month_targets,
            ),
            mql_change_pct=_to_number(
                raw_quarter.get("mql_change_pct", raw_quarter.get("mqlChangePct")),
                baseline.mql_change_pct,
            ),
            mql_to_s0=_to_number(raw_quarter.get("mql_to_s0", raw_quarter.get("mqlToS0")), baseline.mql_to_s0),
            s0_to_s1=_to_number(raw_quarter.get("s0_to_s1", raw_quarter.get("s0ToS1")), baseline.s0_to_s1),
            s1_to_s2=_to_number(raw_quarter.get("s1_to_s2", raw_quarter.get("s1ToS2")), baseline.s1_to_s2),
            avg_deal_size=_to_number(
                raw_quarter.get("avg_deal_size", raw_quarter.get("avgDealSize")),
                baseline.avg_deal_size,
            ),
        )

    return normalized


def compute_snapshot_scenario(
    snapshot: Mapping[str, Any],
    overrides: Mapping[str, Any] | None = None,
) -> SnapshotScenarioResult:
    normalized_overrides = normalize_snapshot_scenario_overrides(snapshot, overrides)
    building_blocks = snapshot["scenario_building_blocks"]
    months = list(building_blocks["months"])
    month_count = len(months)
    first_projected = _first_projected_month_index(snapshot)

    inventory_wins = [_to_number(value) for value in building_blocks["monthly_inventory_wins"]]
    baseline_future_wins = [_to_number(value) for value in building_blocks["monthly_future_wins"]]
    ae_creation = [_to_number(value) for value in building_blocks["monthly_ae_creation"]]
    mql_creation = [_to_number(value) for value in building_blocks["monthly_mql_creation"]]
    monthly_capacity = [_to_number(value) for value in building_blocks["monthly_ae_capacity"]]
    monthly_ae_count = [_to_number(value) for value in building_blocks["monthly_ae_count"]]
    baseline_ae_count = list(monthly_ae_count)

    observed_values = building_blocks.get("observed_values") or {}
    base_avg_deal_size = _to_number(observed_values.get("avg_deal_size"), 300_000.0)
    observed_ae_productivity = _to_number(observed_values.get("productivity_per_ae_per_month"), 0.0)
    funnel_rates = building_blocks.get("funnel_rates") or {}
    base_mql_to_s0 = _to_number(funnel_rates.get("mql_to_s0"), 0.0)
    base_s0_to_s1 = _to_number(funnel_rates.get("s0_to_s1"), 0.0)
    base_s1_to_s2 = _to_number(funnel_rates.get("s1_to_s2"), 0.0)
    base_ae_factor = base_avg_deal_size * base_s0_to_s1 * base_s1_to_s2
    base_mql_factor = base_mql_to_s0 * base_ae_factor

    ramp_curve = _get_observed_ramp_curve(snapshot)
    capacity_per_ae = _estimate_capacity_per_ae(snapshot)
    baseline_pipeline_created = [
        ae_value + (mql_creation[index] if index < len(mql_creation) else 0.0)
        for index, ae_value in enumerate(ae_creation)
    ]

    ae_cohorts: list[dict[str, int]] = []
    carried_monthly_extra_aes = 0

    for quarter in _overridable_quarters(snapshot):
        month_indexes = get_quarter_month_indexes_from_snapshot(snapshot, quarter)
        for month_offset, month_index in enumerate(month_indexes):
            if month_index < first_projected:
                continue
            desired_total = max(
                _to_number(normalized_overrides[quarter].ae_month_targets[month_offset], monthly_ae_count[month_index]),
                monthly_ae_count[month_index],
            )
            raw_extra_aes = max(0, int(round(desired_total - baseline_ae_count[month_index])))
            effective_extra_aes = max(raw_extra_aes, carried_monthly_extra_aes)
            month_cohort_count = effective_extra_aes - carried_monthly_extra_aes
            if month_cohort_count > 0:
                ae_cohorts.append({"startIndex": month_index, "count": month_cohort_count})
            carried_monthly_extra_aes = effective_extra_aes

    for quarter in _overridable_quarters(snapshot):
        start_index = next((index for index, q in enumerate(_quarter_by_month(snapshot)) if q == quarter), -1)
        if start_index == -1:
            continue
        count = max(0, _to_int(normalized_overrides[quarter].add_aes, 0))
        if count > 0:
            ae_cohorts.append({"startIndex": start_index, "count": count})

    for index in range(first_projected, month_count):
        extra_ae_creation = 0.0
        extra_capacity = 0.0
        extra_headcount = 0.0

        for cohort in ae_cohorts:
            if index < cohort["startIndex"]:
                continue
            ramp = _get_ramp_factor(ramp_curve, index - cohort["startIndex"])
            extra_headcount += cohort["count"]
            extra_ae_creation += (
                observed_ae_productivity
                * cohort["count"]
                * ramp
                * base_s0_to_s1
                * base_s1_to_s2
                * base_avg_deal_size
            )
            extra_capacity += (capacity_per_ae[index] if index < len(capacity_per_ae) else 0.0) * cohort["count"] * ramp

        ae_creation[index] += extra_ae_creation
        monthly_capacity[index] += extra_capacity
        monthly_ae_count[index] += extra_headcount

    qbm = _quarter_by_month(snapshot)
    for index in range(first_projected, month_count):
        quarter = qbm[index] if index < len(qbm) else None
        if quarter not in _overridable_quarters(snapshot):
            continue

        override = normalized_overrides[quarter]
        effective_mql_to_s0 = _to_number(override.mql_to_s0, base_mql_to_s0)
        effective_s0_to_s1 = _to_number(override.s0_to_s1, base_s0_to_s1)
        effective_s1_to_s2 = _to_number(override.s1_to_s2, base_s1_to_s2)
        effective_deal_size = _to_number(override.avg_deal_size, base_avg_deal_size)
        effective_ae_factor = effective_deal_size * effective_s0_to_s1 * effective_s1_to_s2
        effective_mql_factor = effective_mql_to_s0 * effective_ae_factor
        ae_scale = effective_ae_factor / base_ae_factor if base_ae_factor > 0 else 1.0
        mql_scale = effective_mql_factor / base_mql_factor if base_mql_factor > 0 else 1.0
        mql_volume_scale = max(0.0, 1.0 + _to_number(override.mql_change_pct, 0.0))

        ae_creation[index] *= ae_scale
        mql_creation[index] *= mql_scale * mql_volume_scale

    monthly_pipeline_created = [
        ae_value + (mql_creation[index] if index < len(mql_creation) else 0.0)
        for index, ae_value in enumerate(ae_creation)
    ]
    future_win_rates = _get_future_generation_win_rates(snapshot, month_count)
    win_adjusted_creation_delta = [
        (value - (baseline_pipeline_created[index] if index < len(baseline_pipeline_created) else 0.0))
        * (future_win_rates[index] if index < len(future_win_rates) else 0.0)
        for index, value in enumerate(monthly_pipeline_created)
    ]
    future_wins_delta = _stack_cohorts(
        win_adjusted_creation_delta,
        [_to_number(value) for value in building_blocks["decay_curve"]],
    )[:month_count]
    future_wins = [
        baseline_value + (future_wins_delta[index] if index < len(future_wins_delta) else 0.0)
        for index, baseline_value in enumerate(baseline_future_wins)
    ]

    for index in range(first_projected):
        ae_creation[index] = _to_number(building_blocks["monthly_ae_creation"][index], 0.0)
        mql_creation[index] = _to_number(building_blocks["monthly_mql_creation"][index], 0.0)
        monthly_pipeline_created[index] = ae_creation[index] + mql_creation[index]
        future_wins[index] = baseline_future_wins[index]
        monthly_capacity[index] = _to_number(building_blocks["monthly_ae_capacity"][index], 0.0)
        monthly_ae_count[index] = _to_number(building_blocks["monthly_ae_count"][index], 0.0)

    monthly_expected = [
        inventory_value + (future_wins[index] if index < len(future_wins) else 0.0)
        for index, inventory_value in enumerate(inventory_wins)
    ]

    for index in range(first_projected):
        monthly_expected[index] = _to_number(building_blocks["monthly_total_expected"][index], monthly_expected[index])

    monthly_capped = _apply_capacity_ceiling(monthly_expected, monthly_capacity)
    monthly_overflow = _compute_overflow(monthly_expected, monthly_capacity)

    for index in range(first_projected):
        monthly_capped[index] = _to_number(building_blocks["monthly_capped"][index], monthly_expected[index])
        monthly_overflow[index] = 0.0

    return SnapshotScenarioResult(
        months=months,
        monthly_inventory_wins=inventory_wins,
        monthly_future_wins=future_wins,
        monthly_pipeline_created=monthly_pipeline_created,
        monthly_ae_creation=ae_creation,
        monthly_mql_creation=mql_creation,
        monthly_expected=monthly_expected,
        monthly_capped=monthly_capped,
        monthly_capacity=monthly_capacity,
        monthly_ae_count=monthly_ae_count,
        monthly_overflow=monthly_overflow,
        cumulative_expected=_cumulative(monthly_expected),
        cumulative_capped=_cumulative(monthly_capped),
        fy_expected=_sum(monthly_expected),
        fy_capped=_sum(monthly_capped),
    )


def get_frontend_profile_data_root() -> Path:
    return default_frontend_profile_data_root()


def resolve_profile_snapshot_path(
    profile_id: str = "default",
    frontend_data_root: Path | None = None,
    frontend_data_base_url: str | None = None,
    config_dir: Path | None = None,
) -> Path | str:
    profile = load_org_profile(config_dir=config_dir, profile_id=profile_id)
    store = resolve_profile_bundle_store(
        profile,
        frontend_data_root=frontend_data_root,
        frontend_data_base_url=frontend_data_base_url,
    )
    return store.resolve(profile.data.snapshot)


def load_profile_frontend_snapshot(
    profile_id: str = "default",
    frontend_data_root: Path | None = None,
    frontend_data_base_url: str | None = None,
    config_dir: Path | None = None,
) -> tuple[dict[str, Any], Path | str]:
    profile = load_org_profile(config_dir=config_dir, profile_id=profile_id)
    store = resolve_profile_bundle_store(
        profile,
        frontend_data_root=frontend_data_root,
        frontend_data_base_url=frontend_data_base_url,
    )
    payload_text, snapshot_location = store.read_text(profile.data.snapshot, encoding="utf-8")
    payload = json.loads(payload_text)
    return payload, snapshot_location

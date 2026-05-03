"""Plan-case loading and frontend v2 plan asset serialization helpers."""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional

from gtm_model.tieout.runtime.env import get_default_config_dir, load_yaml_resource

logger = logging.getLogger(__name__)

_PLAN_CASE_ALIASES: dict[str, str] = {
    # Legacy aliases — populated from profile config at runtime
}

_PACING_FIELD_SOURCES = {
    "mqls_weekly": ("activity", "mqls_weekly"),
    "s0_weekly": ("activity", "s0_booked_weekly"),
    "s1_weekly": ("activity", "s1_held_weekly"),
    "s2_weekly": ("activity", "s2_created_weekly"),
    "mql_to_s0": ("conversion", "mql_to_s0"),
    "s0_to_s1": ("conversion", "s0_to_s1"),
    "s1_to_s2": ("conversion", "s1_to_s2"),
}

_FORWARD_CONTEXT_REFERENCE_IDS = {
    "sales_led_monthly",
    "sales_led_ae_targets",
}


class PlanConfigValidationError(ValueError):
    """Raised when the source config cannot be serialized into the v2 contract."""


def _to_iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")


def _slugify(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _round_half_up(value: Any) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _require_integer(value: Any, label: str) -> int:
    decimal_value = Decimal(str(value))
    if decimal_value != decimal_value.to_integral_value():
        raise PlanConfigValidationError(f"{label} must already be an integer in v2: {value!r}")
    return int(decimal_value)


def _parse_iso_or_month_key(value: Any) -> str:
    text = str(value)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        parsed = datetime.strptime(text, "%b-%y")
    except ValueError as exc:
        raise PlanConfigValidationError(f"Unsupported month key: {value!r}") from exc
    return date(parsed.year, parsed.month, 1).isoformat()


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def _fiscal_months(resolved_targets: dict) -> list[str]:
    start_raw = resolved_targets.get("fiscal_year_start")
    if not start_raw:
        raise PlanConfigValidationError("Missing fiscal_year_start in targets config.")
    start_text = str(start_raw).split()[0]
    start = date.fromisoformat(start_text)
    return [_add_months(start, offset).isoformat() for offset in range(12)]


def _quarter_order(resolved_targets: dict) -> list[str]:
    quarterly_targets = resolved_targets.get("quarterly_targets") or {}
    if not isinstance(quarterly_targets, dict) or not quarterly_targets:
        raise PlanConfigValidationError("Missing quarterly_targets in targets config.")
    return list(quarterly_targets.keys())


def _quarter_month_map(resolved_targets: dict) -> dict[str, list[str]]:
    months = _fiscal_months(resolved_targets)
    quarters = _quarter_order(resolved_targets)
    return {
        quarter: months[index * 3 : index * 3 + 3]
        for index, quarter in enumerate(quarters)
    }


def _normalize_monthly_series(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    return {
        _parse_iso_or_month_key(key): _round_half_up(value)
        for key, value in raw.items()
        if value is not None
    }


def _extract_quarter_metric(
    resolved_targets: dict,
    field_name: str,
) -> dict[str, int]:
    """Extract a per-quarter metric from `quarterly_targets`.

    Accepts two config shapes for backward compatibility:
    1. v2 (rich): `{ Q1: { bookings_target: 7000000, plg_target: 100000 } }`
       — pulls `details[field_name]` for each quarter.
    2. legacy (scalar): `{ Q1: 7000000 }` — treats the scalar as the
       bookings_target value (the most common per-quarter metric).
       Other field_names return empty for legacy configs.
    """
    quarterly_targets = resolved_targets.get("quarterly_targets") or {}
    result: dict[str, int] = {}
    for quarter, details in quarterly_targets.items():
        if isinstance(details, dict):
            if details.get(field_name) is None:
                continue
            result[str(quarter)] = _round_half_up(details[field_name])
        elif isinstance(details, (int, float)) and field_name == "bookings_target":
            # Legacy scalar form maps to bookings_target.
            result[str(quarter)] = _round_half_up(details)
    return result


def _extract_quarter_end_ae_targets(resolved_targets: dict) -> dict[str, int]:
    headcount_targets = resolved_targets.get("headcount_targets") or {}
    result: dict[str, int] = {}
    for quarter, details in headcount_targets.items():
        if not isinstance(details, dict) or details.get("account_executives") is None:
            continue
        result[str(quarter)] = _require_integer(
            details["account_executives"],
            f"{quarter} account_executives",
        )
    return result


def _build_monthly_arr_targets(
    monthly_targets: dict[str, int],
    quarterly_targets: dict[str, int],
    annual_target: Any,
    quarter_months: dict[str, list[str]],
    label: str,
) -> dict[str, Any]:
    # If the config provides only quarterly targets (no monthly_bookings),
    # we treat the quarterly values as authoritative and synthesize an even
    # 3-month split for output. This keeps the canonical generator usable
    # with minimal target configs (the demo/Acme case) while still
    # enforcing rollup consistency when monthly entries ARE provided.
    has_any_monthly = any(value for value in monthly_targets.values())
    quarterly_rollup: dict[str, int] = {}
    for quarter, months in quarter_months.items():
        declared = quarterly_targets.get(quarter)
        if declared is None:
            raise PlanConfigValidationError(f"{label}: missing declared quarterly target for {quarter}.")
        if has_any_monthly:
            calculated = sum(monthly_targets.get(month, 0) for month in months)
            if calculated != declared:
                raise PlanConfigValidationError(
                    f"{label}: monthly rollup mismatch for {quarter}: {calculated} != {declared}."
                )
        else:
            # Even split across the 3 months of the quarter.
            per_month = declared // len(months) if months else 0
            for i, month in enumerate(months):
                # Put any rounding residue on the last month so the sum equals declared.
                monthly_targets[month] = declared - per_month * (len(months) - 1) if i == len(months) - 1 else per_month
        quarterly_rollup[quarter] = declared

    annual_rollup = sum(quarterly_rollup.values())
    declared_annual = _round_half_up(annual_target)
    if annual_rollup != declared_annual:
        raise PlanConfigValidationError(
            f"{label}: annual rollup mismatch: {annual_rollup} != {declared_annual}."
        )

    return {
        "canonical_grain": "monthly",
        "monthly": monthly_targets,
        "quarterly_rollup": quarterly_rollup,
        "annual_rollup": annual_rollup,
    }


def _build_quarterly_arr_targets(
    quarterly_targets: dict[str, int],
    annual_target: Any,
    label: str,
) -> dict[str, Any]:
    annual_rollup = sum(quarterly_targets.values())
    declared_annual = _round_half_up(annual_target)
    if annual_rollup != declared_annual:
        raise PlanConfigValidationError(
            f"{label}: annual rollup mismatch: {annual_rollup} != {declared_annual}."
        )
    return {
        "canonical_grain": "quarterly",
        "quarterly": quarterly_targets,
        "annual_rollup": annual_rollup,
    }


def _build_monthly_seat_targets(
    monthly_targets: dict[str, int],
    quarter_end_targets: dict[str, int],
    quarter_months: dict[str, list[str]],
    label: str,
) -> dict[str, Any]:
    # If the config doesn't declare headcount_targets (canonical generator
    # used against a minimal demo profile), emit an empty seat-targets
    # block. The frontend renders empty seat-targets as "no plan" which
    # is the right behavior — better than crashing.
    # Field shape mirrors the populated case: `quarterly_rollup` (not
    # `quarterly`) is the field the plans.ts loader expects.
    if not quarter_end_targets and not monthly_targets:
        return {
            "canonical_grain": "monthly",
            "monthly": {},
            "quarterly_rollup": {},
            "annual_rollup": 0,
        }
    quarterly_rollup: dict[str, int] = {}
    for quarter, months in quarter_months.items():
        declared = quarter_end_targets.get(quarter)
        if declared is None:
            raise PlanConfigValidationError(f"{label}: missing declared AE milestone for {quarter}.")
        final_month = months[-1]
        actual = monthly_targets.get(final_month)
        if actual is None:
            raise PlanConfigValidationError(
                f"{label}: missing canonical month {final_month} for {quarter} seat rollup."
            )
        if actual != declared:
            raise PlanConfigValidationError(
                f"{label}: quarter-end seat mismatch for {quarter}: {actual} != {declared}."
            )
        quarterly_rollup[quarter] = declared

    annual_rollup = monthly_targets.get(next(reversed(monthly_targets)))
    if annual_rollup is None:
        raise PlanConfigValidationError(f"{label}: missing annual seat milestone.")

    return {
        "canonical_grain": "monthly",
        "monthly": monthly_targets,
        "quarterly_rollup": quarterly_rollup,
        "annual_rollup": annual_rollup,
    }


def _build_quarterly_seat_targets(
    quarter_end_targets: dict[str, int],
) -> dict[str, Any]:
    annual_rollup = quarter_end_targets.get(next(reversed(quarter_end_targets)))
    if annual_rollup is None:
        raise PlanConfigValidationError("Missing annual seat milestone for quarterly seat targets.")
    return {
        "canonical_grain": "quarterly",
        "quarterly_rollup": quarter_end_targets,
        "annual_rollup": annual_rollup,
    }


def _build_package_provenance(resolved_targets: dict, quarter: str) -> dict[str, Any] | None:
    package = resolved_targets.get(f"weekly_targets_{quarter}") or {}
    target_provenance = package.get("target_provenance") or {}
    if not isinstance(target_provenance, dict):
        return None

    freshness_as_of = _to_iso_date(
        resolved_targets.get("top_down_plan", {}).get("created_date")
        or resolved_targets.get("top_down_plan", {}).get("reconciled_on")
    )
    result: dict[str, Any] = {
        "source": _slugify(
            str(target_provenance.get("method") or target_provenance.get("source") or "unknown")
        ),
        "derivation": _slugify(str(target_provenance.get("status") or "configured_plan")),
        "approval_status": "approved" if target_provenance.get("approved") else "not_approved",
    }
    if freshness_as_of:
        result["freshness_as_of"] = freshness_as_of
        result["freshness_status"] = "present"
    if target_provenance.get("label"):
        result["label"] = str(target_provenance["label"])
    if target_provenance.get("notes"):
        result["notes"] = str(target_provenance["notes"])
    return result


def _build_pacing_payload(resolved_targets: dict) -> dict[str, Any] | None:
    quarter_ids = _quarter_order(resolved_targets)
    pacing: dict[str, Any] = {}

    for quarter in quarter_ids:
        package = resolved_targets.get(f"weekly_targets_{quarter}") or {}
        if not isinstance(package, dict):
            continue

        fields: dict[str, Any] = {}
        for field_id, (section_name, source_key) in _PACING_FIELD_SOURCES.items():
            section = package.get(section_name) or {}
            if not isinstance(section, dict) or section.get(source_key) is None:
                continue
            value = section[source_key]
            fields[field_id] = {
                "value": float(value) if field_id.endswith("_to_s0") or field_id.endswith("_to_s1") or field_id.endswith("_to_s2") else _round_half_up(value)
            }

        if not fields:
            continue

        package_provenance = _build_package_provenance(resolved_targets, quarter)
        quarter_payload: dict[str, Any] = {"fields": fields}
        if package_provenance:
            quarter_payload["package_provenance"] = package_provenance
        else:
            quarter_payload["package_provenance"] = {
                "source": "unknown",
                "derivation": "unknown",
                "approval_status": "unknown",
            }
        pacing[quarter] = quarter_payload

    return pacing or None


def _build_forward_context(resolved_targets: dict) -> dict[str, Any] | None:
    raw = resolved_targets.get("forward_context") or {}
    if not isinstance(raw, dict):
        return None

    reference_series_raw = raw.get("reference_series") or {}
    reference_series: dict[str, dict[str, int]] = {}
    if isinstance(reference_series_raw, dict):
        for series_id, values in reference_series_raw.items():
            if series_id not in _FORWARD_CONTEXT_REFERENCE_IDS:
                raise PlanConfigValidationError(f"Unknown forward_context.reference_series id: {series_id}")
            if not isinstance(values, dict):
                raise PlanConfigValidationError(f"forward_context {series_id} must be a mapping.")
            if series_id == "sales_led_ae_targets":
                reference_series[series_id] = {
                    _parse_iso_or_month_key(month): _require_integer(value, f"{series_id} {month}")
                    for month, value in values.items()
                    if value is not None
                }
            else:
                reference_series[series_id] = {
                    _parse_iso_or_month_key(month): _round_half_up(value)
                    for month, value in values.items()
                    if value is not None
                }

    notes = raw.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]

    payload: dict[str, Any] = {
        "mode": "note_only",
        "promotion_strategy": "requires_new_plan_version",
    }
    if raw.get("effective_after"):
        payload["effective_after"] = str(raw["effective_after"])
    if reference_series:
        payload["reference_series"] = reference_series
    if isinstance(notes, list) and notes:
        payload["notes"] = [str(note) for note in notes]
    return payload if len(payload) > 2 or payload.get("notes") else None


def _is_board_plan(plan_meta: dict, resolved_plan_case_id: str) -> bool:
    preset_id = str(plan_meta.get("preset_id") or "")
    status = str(plan_meta.get("status") or "")
    return status == "baseline_reference" or preset_id == "board_baseline"


def _build_sales_led_component(
    resolved_targets: dict,
    resolved_plan_case_id: str,
) -> tuple[dict[str, Any], bool]:
    plan_meta = resolved_targets.get("top_down_plan", {}) or {}
    annual_targets = resolved_targets.get("annual_targets", {}) or {}
    quarter_months = _quarter_month_map(resolved_targets)
    board_plan = _is_board_plan(plan_meta, resolved_plan_case_id)

    sales_led_quarterly = _extract_quarter_metric(resolved_targets, "bookings_target")
    sales_led_monthly_all = _normalize_monthly_series(resolved_targets.get("monthly_bookings") or {})
    fiscal_months = _fiscal_months(resolved_targets)
    sales_led_monthly = {
        month: value
        for month, value in sales_led_monthly_all.items()
        if month in set(fiscal_months)
    }

    if board_plan:
        arr_targets = _build_quarterly_arr_targets(
            sales_led_quarterly,
            annual_targets.get("new_business_arr"),
            "sales_led arr_targets",
        )
    else:
        arr_targets = _build_monthly_arr_targets(
            sales_led_monthly,
            sales_led_quarterly,
            annual_targets.get("new_business_arr"),
            quarter_months,
            "sales_led arr_targets",
        )

    quarter_end_ae_targets = _extract_quarter_end_ae_targets(resolved_targets)
    monthly_ae_targets_all = _normalize_monthly_series(resolved_targets.get("monthly_ae_targets") or {})
    monthly_ae_targets = {
        month: _require_integer(value, f"monthly_ae_targets {month}")
        for month, value in monthly_ae_targets_all.items()
        if month in set(fiscal_months)
    }

    seat_targets = (
        _build_quarterly_seat_targets(quarter_end_ae_targets)
        if board_plan
        else _build_monthly_seat_targets(
            monthly_ae_targets,
            quarter_end_ae_targets,
            quarter_months,
            "sales_led seat_targets",
        )
    )

    component = {
        "label": "Sales-Led",
        "category": "new_logo_sales_led",
        "modeled_status": "scenario_modeled",
        "approval_status": str(plan_meta.get("status") or "working_draft"),
        "basis": "board_plan" if board_plan else "consultant_capacity_recut",
        "as_of": _to_iso_date(plan_meta.get("created_date") or plan_meta.get("reconciled_on")),
        "arr_targets": arr_targets,
        "seat_targets": seat_targets,
    }
    return component, not board_plan


def _build_held_assumption_component(
    resolved_targets: dict,
    field_name: str,
    annual_field: str,
    label: str,
    category: str,
) -> dict[str, Any] | None:
    """Build a held-assumption (PLG / Expansion / Renewal) plan component.

    Returns None when the active profile doesn't declare this revenue stream
    (no annual_targets[annual_field]). Callers must handle the None and skip
    inserting the component into the plan preset, rather than emitting a
    decimal-error-inducing empty bundle.
    """
    plan_meta = resolved_targets.get("top_down_plan", {}) or {}
    annual_targets = resolved_targets.get("annual_targets", {}) or {}
    annual_value = annual_targets.get(annual_field)
    if annual_value is None:
        return None
    quarterly_targets = _extract_quarter_metric(resolved_targets, field_name)

    return {
        "label": label,
        "category": category,
        "modeled_status": "held_assumption",
        "approval_status": "held_from_board_plan",
        "basis": "board_hold",
        "as_of": _to_iso_date(plan_meta.get("created_date") or plan_meta.get("reconciled_on")),
        "arr_targets": _build_quarterly_arr_targets(
            quarterly_targets,
            annual_value,
            f"{label} arr_targets",
        ),
    }


def build_frontend_plan_preset_payload(resolved_targets: dict, resolved_plan_case_id: str) -> dict[str, Any]:
    """Serialize a resolved backend plan case into the frontend v2 preset contract."""
    plan_meta = copy.deepcopy(resolved_targets.get("top_down_plan", {}) or {})
    preset_id = str(plan_meta.get("preset_id") or _slugify(plan_meta.get("label") or resolved_plan_case_id))
    label = str(plan_meta.get("label") or resolved_plan_case_id)
    created_date = _to_iso_date(plan_meta.get("created_date") or plan_meta.get("reconciled_on"))
    version = str(plan_meta.get("version") or "1.0")
    board_plan = _is_board_plan(plan_meta, resolved_plan_case_id)

    sales_led_component, sales_led_monthly_supported = _build_sales_led_component(
        resolved_targets,
        resolved_plan_case_id,
    )

    components: dict[str, Any] = {
        "sales_led": sales_led_component,
    }
    views: dict[str, Any] = {
        "sales_led_operating": {
            "label": "Sales-Led Plan",
            "treatment_class": "operator_comparable",
            "supported_grains": ["quarterly", "annual"]
            if board_plan
            else ["monthly", "quarterly", "annual"],
            "component_ids": ["sales_led"],
            "seat_target_owner_component_id": "sales_led",
            "derived": True,
        }
    }

    default_executive_context_view_id: str | None = None
    if not board_plan:
        plg_component = _build_held_assumption_component(
            resolved_targets,
            "plg_target",
            "plg_arr",
            "PLG",
            "self_serve",
        )
        if plg_component is not None:
            components["plg"] = plg_component
        expansion_component = _build_held_assumption_component(
            resolved_targets,
            "expansion_target",
            "expansion_arr",
            "Expansion",
            "expansion",
        )
        if expansion_component is not None:
            components["expansion"] = expansion_component
        # Only emit the executive total-net-new view when ALL streams are
        # declared. Otherwise the view would reference missing components,
        # and the default_executive_context_view_id must not point at a
        # view that wasn't emitted (frontend plan validator rejects that).
        if plg_component is not None and expansion_component is not None:
            views["executive_total_net_new"] = {
                "label": "Executive Total Net New",
                "treatment_class": "executive_reference",
                "context_kind": "total_net_new",
                "supported_grains": ["quarterly", "annual"],
                "component_ids": ["sales_led", "plg", "expansion"],
                "derived": True,
            }
            default_executive_context_view_id = "executive_total_net_new"

    payload: dict[str, Any] = {
        "schema_version": 2,
        "id": preset_id,
        "name": label,
        "version": version,
        "created_date": created_date,
        "default_comparison_view_id": "sales_led_operating",
        "components": components,
        "views": views,
    }
    if default_executive_context_view_id:
        payload["default_executive_context_view_id"] = default_executive_context_view_id

    pacing = _build_pacing_payload(resolved_targets)
    if pacing:
        payload["pacing"] = pacing

    forward_context = _build_forward_context(resolved_targets)
    if forward_context and sales_led_monthly_supported:
        payload["forward_context"] = forward_context

    return payload


@dataclass
class TieoutPlanConfigResolver:
    """Load config files and resolve active plan cases."""

    config_dir: Path
    config_stage: Optional[str] = None
    profile_id: Optional[str] = None

    def load_yaml(self, filename: str) -> dict:
        """Load a YAML file from the tieout config directory."""
        return load_yaml_resource(
            filename,
            config_dir=self.config_dir or get_default_config_dir(),
            config_stage=self.config_stage,
            profile_id=self.profile_id,
        )

    def deep_merge_dicts(self, base: dict, overlay: dict) -> dict:
        """Recursively merge a config overlay into the base dictionary."""
        merged = copy.deepcopy(base)
        for key, value in (overlay or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self.deep_merge_dicts(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    @staticmethod
    def base_plan_case_id(targets_raw: dict) -> str:
        """Return the plan-case id represented by the top-level YAML block."""
        plan = targets_raw.get("top_down_plan", {}) or {}
        return plan.get("plan_id") or "baseline"

    @staticmethod
    def default_plan_case_id(targets_raw: dict) -> str:
        """Return the default selectable plan-case id from raw targets config."""
        return targets_raw.get("default_plan_case") or TieoutPlanConfigResolver.base_plan_case_id(targets_raw)

    @staticmethod
    def canonical_plan_case_id(plan_case_id: Optional[str]) -> Optional[str]:
        """Resolve any backwards-compatible aliases for a requested plan-case id."""
        if not plan_case_id:
            return plan_case_id
        return _PLAN_CASE_ALIASES.get(plan_case_id, plan_case_id)

    def _resolve_known_targets(self, targets_raw: dict, selected_plan_case: str) -> tuple[dict, str]:
        """Resolve a known plan case without falling back."""
        base = copy.deepcopy(targets_raw)
        base_plan_case = self.base_plan_case_id(targets_raw)
        base_canonical_case = self.canonical_plan_case_id(base_plan_case) or "baseline"
        base.setdefault("top_down_plan", {})
        base["top_down_plan"].setdefault("plan_id", base_canonical_case)

        if selected_plan_case == base_canonical_case:
            return base, base_canonical_case

        overlay = (base.get("plan_cases") or {}).get(selected_plan_case)
        if not overlay:
            for case_id, candidate in (base.get("plan_cases") or {}).items():
                if self.canonical_plan_case_id(case_id) == selected_plan_case:
                    overlay = candidate
                    break
        if not overlay:
            raise KeyError(selected_plan_case)

        merged = self.deep_merge_dicts(base, overlay)
        merged.setdefault("top_down_plan", {})
        current_case_id = self.canonical_plan_case_id(merged["top_down_plan"].get("plan_id"))
        if not current_case_id or current_case_id == base_canonical_case:
            merged["top_down_plan"]["plan_id"] = selected_plan_case
        else:
            merged["top_down_plan"]["plan_id"] = current_case_id
        return merged, str(merged["top_down_plan"]["plan_id"])

    def resolve_targets(self, targets_raw: dict, plan_case_id: Optional[str]) -> tuple[dict, str]:
        """Resolve the active top-down plan case from `targets.yaml`."""
        default_plan_case = self.default_plan_case_id(targets_raw)
        selected_plan_case = self.canonical_plan_case_id(plan_case_id or default_plan_case) or default_plan_case

        try:
            return self._resolve_known_targets(targets_raw, selected_plan_case)
        except KeyError:
            logger.warning(
                "Unknown top-down plan case '%s'; using default '%s'.",
                selected_plan_case,
                default_plan_case,
            )
        default_canonical_case = self.canonical_plan_case_id(default_plan_case) or self.base_plan_case_id(targets_raw)
        try:
            return self._resolve_known_targets(targets_raw, default_canonical_case)
        except KeyError:
            base_plan_case = self.base_plan_case_id(targets_raw)
            base_canonical_case = self.canonical_plan_case_id(base_plan_case) or "baseline"
            if default_canonical_case != base_canonical_case:
                logger.warning(
                    "Unknown default top-down plan case '%s'; using base '%s'.",
                    default_canonical_case,
                    base_canonical_case,
                )
            return self._resolve_known_targets(targets_raw, base_canonical_case)

    def available_plan_cases(self, targets_raw: dict) -> list[dict]:
        """Return selectable top-down plan cases with the default case first."""
        candidates = [
            self.default_plan_case_id(targets_raw),
            self.base_plan_case_id(targets_raw),
            *((targets_raw.get("plan_cases") or {}).keys()),
        ]

        cases = []
        seen_case_ids: set[str] = set()
        for case_id in candidates:
            resolved_targets, resolved_case_id = self.resolve_targets(targets_raw, case_id)
            if resolved_case_id in seen_case_ids:
                continue
            plan_meta = copy.deepcopy(resolved_targets.get("top_down_plan", {}) or {})
            plan_meta["plan_id"] = resolved_case_id
            cases.append(plan_meta)
            seen_case_ids.add(resolved_case_id)
        return cases


def list_frontend_plan_presets(
    config_dir: Optional[Path] = None,
    profile_id: Optional[str] = None,
    config_stage: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Resolve backend plan cases into frontend v2 preset payloads."""
    resolver = TieoutPlanConfigResolver(
        config_dir=Path(config_dir or get_default_config_dir()).expanduser().resolve(),
        config_stage=config_stage,
        profile_id=profile_id,
    )
    targets_raw = resolver.load_yaml("targets.yaml")
    case_ids = [case.get("plan_id") for case in resolver.available_plan_cases(targets_raw) if case.get("plan_id")]

    presets: list[dict[str, Any]] = []
    for case_id in case_ids:
        resolved_targets, resolved_case_id = resolver.resolve_targets(targets_raw, case_id)
        presets.append(build_frontend_plan_preset_payload(resolved_targets, resolved_case_id))
    return presets


def write_frontend_plan_assets(
    output_dir: Path,
    config_dir: Optional[Path] = None,
    profile_id: Optional[str] = None,
    config_stage: Optional[str] = None,
    indent: int = 2,
) -> list[Path]:
    """Write frontend plan preset assets from canonical backend plan cases."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    indent_value = indent if indent > 0 else None

    presets = list_frontend_plan_presets(
        config_dir=config_dir,
        profile_id=profile_id,
        config_stage=config_stage,
    )

    manifest = {
        "plans": [
            {
                "id": str(preset["id"]),
                "path": f"./{preset['id']}.json",
            }
            for preset in presets
        ]
    }

    kept_files = {"index.json"}
    written_paths: list[Path] = []
    manifest_path = output_dir / "index.json"
    manifest_path.write_text(json.dumps(manifest, indent=indent_value) + "\n", encoding="utf-8")
    written_paths.append(manifest_path)

    for preset in presets:
        filename = f"{preset['id']}.json"
        kept_files.add(filename)
        payload_path = output_dir / filename
        payload_path.write_text(json.dumps(preset, indent=indent_value) + "\n", encoding="utf-8")
        written_paths.append(payload_path)

    for existing in output_dir.glob("*.json"):
        if existing.name not in kept_files:
            existing.unlink()

    return written_paths

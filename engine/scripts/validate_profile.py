#!/usr/bin/env python3
"""
Validate a profile's YAML configuration for internal consistency.

This is a config-only validator — no runtime environment checks
(Salesforce connectivity, warehouse availability, etc.). It runs offline
against config files alone and is intended to gate snapshot generation.

Usage:
    python -m engine.scripts.validate_profile --profile acme-saas --config-dir engine/config/profiles
    python -m engine.scripts.validate_profile --profile-dir engine/config/profiles/acme-saas
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    "profile.yaml",
    "stages.yaml",
    "roster.yaml",
    "targets.yaml",
    "assumptions.yaml",
    "field_mappings.yaml",
    "slip_rates.yaml",
]

VALID_REVENUE_METRICS = {"bookings", "acv"}

REQUIRED_DEAL_FIELDS = {"amount", "stage", "close_date", "owner_id"}


@dataclass
class ValidationResult:
    """Outcome of a profile configuration validation run."""

    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.passed = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


# ---------------------------------------------------------------------------
# YAML loading helper
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load and parse a YAML file. Returns (data, error_message)."""
    try:
        text = path.read_text()
    except OSError as exc:
        return None, f"Cannot read {path.name}: {exc}"

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, f"{path.name} is not valid YAML: {exc}"

    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, f"{path.name} top-level value must be a mapping, got {type(data).__name__}"
    return data, None


# ---------------------------------------------------------------------------
# Individual validation checks
# ---------------------------------------------------------------------------


def _check_required_files(profile_dir: Path, result: ValidationResult) -> dict[str, dict]:
    """Ensure all 7 required files exist and are parseable YAML.

    Returns a dict of filename -> parsed data for files that loaded
    successfully.
    """
    loaded: dict[str, dict] = {}
    for filename in REQUIRED_FILES:
        filepath = profile_dir / filename
        if not filepath.exists():
            result.add_error(f"Missing required file: {filename}")
            continue
        data, error = _load_yaml(filepath)
        if error:
            result.add_error(error)
        elif data is not None:
            loaded[filename] = data
    return loaded


def _check_profile_yaml(data: dict, result: ValidationResult) -> None:
    """Validate profile.yaml: revenue_metric must be 'bookings' or 'acv',
    and data_access (if present) must declare a known type.
    """
    metric = data.get("revenue_metric")
    if metric is None:
        result.add_error(
            "profile.yaml: missing 'revenue_metric' (must be one of: "
            + ", ".join(sorted(VALID_REVENUE_METRICS))
            + ")"
        )
    elif metric not in VALID_REVENUE_METRICS:
        result.add_error(
            f"profile.yaml: invalid revenue_metric '{metric}' "
            f"(must be one of: {', '.join(sorted(VALID_REVENUE_METRICS))})"
        )

    _check_data_access_block(data, result)


def _check_data_access_block(data: dict, result: ValidationResult) -> None:
    """Per ARCHITECTURE.md, profile.yaml may declare a data_access block.

    During the deprecation window (legacy connector + data_dir fields),
    data_access is optional. Once present, it's validated.
    """
    block = data.get("data_access")
    if block is None:
        # Falls back to legacy `connector` + `data_dir` fields. Issue a
        # deprecation warning to nudge profiles toward the new shape.
        if data.get("connector") and data.get("data_dir"):
            result.add_warning(
                "profile.yaml: legacy 'connector' + 'data_dir' fields are "
                "deprecated; migrate to the 'data_access' block (see ARCHITECTURE.md)"
            )
        return

    if not isinstance(block, dict):
        result.add_error(
            "profile.yaml: 'data_access' must be a dict with 'type' "
            "and 'params' fields"
        )
        return

    type_name = block.get("type")
    if not type_name:
        result.add_error(
            "profile.yaml: 'data_access.type' is required (e.g. 'csv', "
            "'snowflake', 'salesforce', or a forker-defined type)"
        )
        return

    # Don't enforce a closed list of types — forkers register custom ones.
    # We do require params to be a dict (or absent).
    params = block.get("params")
    if params is not None and not isinstance(params, dict):
        result.add_error(
            "profile.yaml: 'data_access.params' must be a dict (or omitted)"
        )


def _check_field_mappings(data: dict, result: ValidationResult) -> None:
    """Validate field_mappings.yaml.

    Per ARCHITECTURE.md, the supported shape is:

        opportunity:
          <model_field>:
            sf_field: <source-system field name>
          stage:
            stage_mapping:
              <source stage>: <model stage>

    The legacy flat `deal:` shape (just `model_field: source_field` strings)
    is accepted with a deprecation warning for one release.
    """
    opportunity_section = data.get("opportunity")
    deal_section = data.get("deal")  # legacy shape

    if isinstance(opportunity_section, dict):
        _check_field_mappings_new_shape(opportunity_section, result)
    elif isinstance(deal_section, dict):
        result.add_warning(
            "field_mappings.yaml: legacy 'deal:' shape is deprecated; "
            "migrate to the 'opportunity:' shape with stage_mapping. "
            "See ARCHITECTURE.md."
        )
        _check_field_mappings_legacy_shape(deal_section, result)
    else:
        result.add_error(
            "field_mappings.yaml: missing 'opportunity' section. "
            "Expected shape: opportunity.<model_field>.sf_field plus "
            "opportunity.stage.stage_mapping. See ARCHITECTURE.md."
        )


def _check_field_mappings_new_shape(
    opportunity_section: dict, result: ValidationResult
) -> None:
    """Validate the ARCHITECTURE.md opportunity-block shape."""
    for required_field in sorted(REQUIRED_DEAL_FIELDS):
        field_block = opportunity_section.get(required_field)
        if not isinstance(field_block, dict):
            result.add_error(
                f"field_mappings.yaml: missing required mapping "
                f"'opportunity.{required_field}'"
            )
            continue
        if "sf_field" not in field_block:
            result.add_error(
                f"field_mappings.yaml: 'opportunity.{required_field}' is "
                f"missing 'sf_field'"
            )

    # Architectural decision: opportunity.stage.stage_mapping is required and non-empty.
    # Without it, the connector boundary can't normalize source stages
    # to model vocabulary, and the engine sees inconsistent stages.
    stage_block = opportunity_section.get("stage")
    if not isinstance(stage_block, dict):
        result.add_error(
            "field_mappings.yaml: 'opportunity.stage' is required and "
            "must declare 'stage_mapping' (see ARCHITECTURE.md)"
        )
        return
    stage_mapping = stage_block.get("stage_mapping")
    if stage_mapping is None:
        result.add_error(
            "field_mappings.yaml: 'opportunity.stage.stage_mapping' is "
            "required (see ARCHITECTURE.md — connectors normalize source stages "
            "to model vocabulary at the boundary)"
        )
    elif not isinstance(stage_mapping, dict):
        result.add_error(
            "field_mappings.yaml: 'opportunity.stage.stage_mapping' "
            "must be a dict mapping source stages to model stages"
        )
    elif not stage_mapping:
        result.add_error(
            "field_mappings.yaml: 'opportunity.stage.stage_mapping' "
            "must declare at least one source-stage → model-stage mapping"
        )


def _check_field_mappings_legacy_shape(
    deal_section: dict, result: ValidationResult
) -> None:
    """Validate the pre-ARCHITECTURE.md 'deal:' flat shape."""
    for required_field in sorted(REQUIRED_DEAL_FIELDS):
        if required_field not in deal_section:
            result.add_error(
                f"field_mappings.yaml: missing required deal mapping "
                f"'{required_field}'"
            )


def _check_targets(data: dict, result: ValidationResult) -> None:
    """Validate targets.yaml: quarterly targets sum must equal annual_target."""
    annual_target = data.get("annual_target")
    quarterly_targets = data.get("quarterly_targets")

    if annual_target is None:
        result.add_error("targets.yaml: missing 'annual_target'")
    if not isinstance(quarterly_targets, dict) or not quarterly_targets:
        result.add_error("targets.yaml: missing or empty 'quarterly_targets'")
        return

    if annual_target is None:
        return  # already reported

    try:
        annual_val = float(annual_target)
        quarterly_sum = sum(float(v) for v in quarterly_targets.values())
    except (TypeError, ValueError) as exc:
        result.add_error(f"targets.yaml: non-numeric target value: {exc}")
        return

    if abs(quarterly_sum - annual_val) > 1.0:
        result.add_error(
            f"targets.yaml: quarterly targets sum ({quarterly_sum:,.0f}) "
            f"does not equal annual_target ({annual_val:,.0f}) "
            f"(difference: {abs(quarterly_sum - annual_val):,.2f}, tolerance: $1)"
        )


def _check_stages_cross_reference(
    stages_data: dict,
    assumptions_data: dict,
    result: ValidationResult,
) -> None:
    """Validate that stage names in assumptions.yaml exist in stages.yaml."""
    # Extract defined stage names from stages.yaml
    raw_stages = stages_data.get("stages")
    if not isinstance(raw_stages, list):
        result.add_warning("stages.yaml: no 'stages' list found; skipping cross-reference check")
        return

    defined_names: set[str] = set()
    for entry in raw_stages:
        if isinstance(entry, dict) and "name" in entry:
            defined_names.add(str(entry["name"]))
        elif isinstance(entry, str):
            defined_names.add(entry)

    # Check assumptions.yaml stage_rates keys
    stage_rates = assumptions_data.get("stage_rates")
    if not isinstance(stage_rates, dict):
        return  # no stage_rates to check

    for stage_name in stage_rates:
        if stage_name not in defined_names:
            result.add_error(
                f"assumptions.yaml: stage_rates references stage '{stage_name}' "
                f"which is not defined in stages.yaml "
                f"(defined: {', '.join(sorted(defined_names))})"
            )


def _check_roster(data: dict, result: ValidationResult) -> None:
    """Validate roster.yaml: no duplicate team member IDs."""
    team_members = data.get("team_members")
    if not isinstance(team_members, list):
        result.add_warning("roster.yaml: no 'team_members' list found")
        return

    seen_ids: dict[str, int] = {}
    for member in team_members:
        if not isinstance(member, dict):
            continue
        member_id = member.get("id")
        if member_id is None:
            continue
        member_id_str = str(member_id)
        seen_ids[member_id_str] = seen_ids.get(member_id_str, 0) + 1

    for member_id, count in seen_ids.items():
        if count > 1:
            result.add_error(
                f"roster.yaml: duplicate team member id '{member_id}' "
                f"(appears {count} times)"
            )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def validate_profile(profile_dir: Path) -> ValidationResult:
    """Validate a profile directory for internal configuration consistency.

    Args:
        profile_dir: Path to the profile directory containing YAML config files.

    Returns:
        ValidationResult with passed/errors/warnings.
    """
    result = ValidationResult()
    profile_dir = Path(profile_dir)

    if not profile_dir.exists():
        result.add_error(f"Profile directory does not exist: {profile_dir}")
        return result

    if not profile_dir.is_dir():
        result.add_error(f"Profile path is not a directory: {profile_dir}")
        return result

    # Step 1: Check all required files exist and parse
    loaded = _check_required_files(profile_dir, result)

    # Step 2: Validate profile.yaml contents
    if "profile.yaml" in loaded:
        _check_profile_yaml(loaded["profile.yaml"], result)

    # Step 3: Validate field_mappings.yaml contents
    if "field_mappings.yaml" in loaded:
        _check_field_mappings(loaded["field_mappings.yaml"], result)

    # Step 4: Validate targets.yaml contents
    if "targets.yaml" in loaded:
        _check_targets(loaded["targets.yaml"], result)

    # Step 5: Cross-reference stages.yaml and assumptions.yaml
    if "stages.yaml" in loaded and "assumptions.yaml" in loaded:
        _check_stages_cross_reference(
            loaded["stages.yaml"],
            loaded["assumptions.yaml"],
            result,
        )

    # Step 6: Validate roster.yaml for duplicate IDs
    if "roster.yaml" in loaded:
        _check_roster(loaded["roster.yaml"], result)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a profile's YAML configuration for internal consistency.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--profile-dir",
        type=Path,
        help="Direct path to the profile directory.",
    )
    group.add_argument(
        "--profile",
        type=str,
        help="Profile name (resolved under --config-dir).",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("engine/config/profiles"),
        help="Root directory containing profile subdirectories.",
    )

    args = parser.parse_args(argv)

    if args.profile_dir:
        profile_dir = args.profile_dir
    else:
        profile_dir = args.config_dir / args.profile

    result = validate_profile(profile_dir)

    if result.errors:
        print(f"FAIL  {profile_dir.name}: {len(result.errors)} error(s)")
        for err in result.errors:
            print(f"  ERROR: {err}")
    if result.warnings:
        for warn in result.warnings:
            print(f"  WARN:  {warn}")
    if result.passed:
        print(f"OK    {profile_dir.name}: profile configuration is valid")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())

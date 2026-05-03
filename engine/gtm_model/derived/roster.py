"""Pure-function port of `TieoutDataAccess.try_roster()`.

Builds a roster of seller records from connector-provided team members,
augmented with profile-yaml overrides. The legacy try_roster() routed
through Salesforce + roster.yaml; this pure function operates on
already-fetched team_members.

Roster augmentation semantics (preserved from data_access.py:189-192):
- Each connector-provided TeamMember is a baseline.
- The profile's roster.yaml may add records that don't exist in the
  source system (phantom AEs, contractors), or override fields on
  existing records (segment, manager_id).
- AE overrides from a runtime caller (e.g. scenario inputs) take
  precedence over both baseline and yaml overrides.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import date
from typing import Any, Iterable, Optional

from engine.connectors.interface import TeamMember


def _team_member_to_dict(tm: TeamMember) -> dict[str, Any]:
    """Convert a TeamMember dataclass to the legacy dict shape used by
    the rest of the engine (`gtm_model.roster.load_roster_data` etc.).
    """
    d = asdict(tm)
    # Legacy roster format uses ISO strings for dates
    if d.get("start_date") is not None and isinstance(d["start_date"], date):
        d["start_date"] = d["start_date"].isoformat()
    return d


def _apply_overrides(
    base: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    """Shallow-merge override fields onto a base record. None values in
    the override are skipped (don't blank out base fields).
    """
    merged = dict(base)
    for key, value in overrides.items():
        if value is None:
            continue
        merged[key] = value
    return merged


def compute_roster(
    team_members: Iterable[TeamMember],
    yaml_overrides: Optional[dict[str, dict]] = None,
    yaml_phantoms: Optional[list[dict]] = None,
    ae_overrides: Optional[dict[str, dict]] = None,
) -> list[dict[str, Any]]:
    """Build the engine's roster by composing connector data + yaml augmentations.

    Args:
        team_members: Iterable of TeamMember from a connector.
        yaml_overrides: {team_member_id: {field: value}} from roster.yaml's
            override block. Fields with None values are ignored.
        yaml_phantoms: List of full team-member dicts from roster.yaml's
            phantoms block — added on top of the connector's records.
        ae_overrides: Runtime AE overrides keyed by member id. Take
            precedence over both connector data and yaml_overrides.

    Returns:
        List of roster dicts in the legacy shape (same as
        `gtm_model.roster.load_roster_data` returns), with merged data.
    """
    yaml_overrides = yaml_overrides or {}
    yaml_phantoms = yaml_phantoms or []
    ae_overrides = ae_overrides or {}

    roster: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for tm in team_members:
        record = _team_member_to_dict(tm)
        if tm.id in yaml_overrides:
            record = _apply_overrides(record, yaml_overrides[tm.id])
        if tm.id in ae_overrides:
            record = _apply_overrides(record, ae_overrides[tm.id])
        roster.append(record)
        seen_ids.add(tm.id)

    for phantom in yaml_phantoms:
        phantom_id = phantom.get("id")
        if not phantom_id or phantom_id in seen_ids:
            continue
        record = deepcopy(phantom)
        if phantom_id in ae_overrides:
            record = _apply_overrides(record, ae_overrides[phantom_id])
        roster.append(record)
        seen_ids.add(phantom_id)

    return roster

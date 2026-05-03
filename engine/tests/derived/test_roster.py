"""Tests for engine.gtm_model.derived.roster."""
from __future__ import annotations

from datetime import date

from engine.connectors.interface import TeamMember
from engine.gtm_model.derived.roster import compute_roster


def _tm(**overrides) -> TeamMember:
    base = dict(
        id="U1",
        name="Alice",
        role="AE",
        segment="Enterprise",
        start_date=date(2025, 1, 1),
        is_active=True,
    )
    base.update(overrides)
    return TeamMember(**base)


def test_baseline_roster_from_connector():
    members = [_tm(id="U1"), _tm(id="U2", name="Bob")]
    roster = compute_roster(members)
    assert len(roster) == 2
    assert roster[0]["id"] == "U1"
    assert roster[0]["start_date"] == "2025-01-01"  # ISO string


def test_yaml_overrides_replace_fields():
    members = [_tm(id="U1", segment="Enterprise")]
    overrides = {"U1": {"segment": "Mid-Market", "manager_id": "M1"}}
    roster = compute_roster(members, yaml_overrides=overrides)
    assert roster[0]["segment"] == "Mid-Market"
    assert roster[0]["manager_id"] == "M1"


def test_yaml_overrides_skip_none_values():
    """None in override doesn't blank out a base field."""
    members = [_tm(id="U1", segment="Enterprise")]
    overrides = {"U1": {"segment": None, "manager_id": "M1"}}
    roster = compute_roster(members, yaml_overrides=overrides)
    assert roster[0]["segment"] == "Enterprise"  # untouched
    assert roster[0]["manager_id"] == "M1"


def test_yaml_phantoms_added_to_roster():
    members = [_tm(id="U1")]
    phantoms = [
        {"id": "PHANTOM1", "name": "Future AE", "role": "AE", "segment": "SMB"},
    ]
    roster = compute_roster(members, yaml_phantoms=phantoms)
    ids = [r["id"] for r in roster]
    assert ids == ["U1", "PHANTOM1"]


def test_phantom_with_existing_id_skipped():
    """Phantoms can't duplicate connector-provided IDs."""
    members = [_tm(id="U1", segment="Enterprise")]
    phantoms = [{"id": "U1", "name": "Imposter", "segment": "SMB"}]
    roster = compute_roster(members, yaml_phantoms=phantoms)
    assert len(roster) == 1
    assert roster[0]["segment"] == "Enterprise"  # phantom didn't override


def test_ae_overrides_take_precedence_over_yaml():
    members = [_tm(id="U1", segment="Enterprise")]
    yaml_overrides = {"U1": {"segment": "Mid-Market"}}
    ae_overrides = {"U1": {"segment": "SMB"}}
    roster = compute_roster(
        members,
        yaml_overrides=yaml_overrides,
        ae_overrides=ae_overrides,
    )
    assert roster[0]["segment"] == "SMB"


def test_ae_overrides_apply_to_phantoms_too():
    phantoms = [{"id": "P1", "name": "X", "segment": "SMB"}]
    ae_overrides = {"P1": {"segment": "Enterprise"}}
    roster = compute_roster(
        [], yaml_phantoms=phantoms, ae_overrides=ae_overrides
    )
    assert roster[0]["segment"] == "Enterprise"


def test_empty_inputs_return_empty_roster():
    assert compute_roster([]) == []
    assert compute_roster([], yaml_overrides={}, yaml_phantoms=[]) == []

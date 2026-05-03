"""Tests for engine.profile_backend.* """
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.connectors.csv_connector import CSVConnector
from engine.connectors.interface import (
    ConnectorCapabilities,
    ConnectorInterface,
    Deal,
    StageTransition,
    TeamMember,
)
from engine.profile_backend import (
    NoOpHealth,
    ProfileBackend,
    ProfileBackendBase,
    build_backend,
    register_backend,
)
from engine.profile_backend.csv_backend import CSVBackend
from engine.profile_backend.factory import _REGISTRY


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def acme_data_dir():
    return Path(__file__).resolve().parents[2] / "engine" / "data" / "acme-saas"


@pytest.fixture
def acme_field_mappings(tmp_path):
    """A field_mappings.yaml with a complete stage mapping."""
    path = tmp_path / "field_mappings.yaml"
    path.write_text(
        "opportunity:\n"
        "  amount:\n"
        "    sf_field: Amount\n"
        "  stage:\n"
        "    sf_field: StageName\n"
        "    stage_mapping:\n"
        "      Discovery: S1\n"
        "      Qualification: S2\n"
        "      Technical Evaluation: S3\n"
        "      Business Case: S4\n"
        "      Negotiation: S5\n"
        "      Closed Won: Won\n"
        "      Closed Lost: Lost\n"
        "  close_date:\n"
        "    sf_field: CloseDate\n"
        "  owner_id:\n"
        "    sf_field: OwnerId\n"
    )
    return path


# ── ProfileBackend Protocol conformance ──────────────────────────


def test_profile_backend_base_implements_protocol():
    """ProfileBackendBase satisfies the runtime-checkable Protocol."""
    connector = MagicMock(spec=ConnectorInterface)
    backend = ProfileBackendBase(connector)
    assert isinstance(backend, ProfileBackend)


def test_no_op_health_returns_empty():
    health = NoOpHealth()
    assert health.mart_freshness() == {}
    assert health.reconciliation_check(quarter="Q1 FY26") is None


# ── ProfileBackendBase default behavior ──────────────────────────


def test_base_concern_b_prime_returns_none():
    """Architectural decision: Concern B′ default is None for non-Snowflake backends."""
    connector = MagicMock(spec=ConnectorInterface)
    connector.fetch_deals.return_value = []
    backend = ProfileBackendBase(connector)
    assert backend.compute_funnel_from_source("Q1 FY26") is None
    assert backend.compute_weekly_targets("Q1 FY26") is None
    assert backend.compute_quarter_conversion_overrides("Q1 FY26") is None
    assert backend.compute_closed_won_timing(lookback_months=12) is None


def test_base_compute_finance_summary_uses_derived():
    """Default compute_closed_won_finance_summary delegates to derived module."""
    connector = MagicMock(spec=ConnectorInterface)
    connector.fetch_deals.return_value = [
        Deal(
            id="W1", name="X", amount=100, stage="Won",
            close_date=date(2026, 6, 1), owner_id="U1",
            is_closed=True, is_won=True, year_1_arr=80, type="New Business",
        ),
    ]
    backend = ProfileBackendBase(connector)
    summary = backend.compute_closed_won_finance_summary(
        date(2026, 1, 1), date(2026, 12, 31)
    )
    assert summary.totals.won_count == 1
    assert summary.totals.year1_arr == 80


# ── CSVBackend integration with real Acme data ────────────────────


def test_csv_backend_constructed_with_field_mapping(
    acme_data_dir, acme_field_mappings
):
    if not acme_data_dir.exists():
        pytest.skip("Acme data dir not present in this environment")
    backend = CSVBackend(
        data_dir=acme_data_dir,
        field_mapping_path=acme_field_mappings,
    )
    assert isinstance(backend, ProfileBackend)
    deals = backend.fetch_deals()
    assert len(deals) > 0
    # All deals should have model-stage values from the mapping
    assert all(d.stage in {"S1", "S2", "S3", "S4", "S5", "Won", "Lost"} for d in deals)


def test_csv_backend_capabilities_propagate(acme_data_dir, acme_field_mappings):
    if not acme_data_dir.exists():
        pytest.skip("Acme data dir not present")
    backend = CSVBackend(acme_data_dir, field_mapping_path=acme_field_mappings)
    caps = backend.capabilities()
    # Acme CSV has stage_history.csv but no companies/contacts CSVs
    assert caps.has_stage_history is True


# ── Factory ──────────────────────────────────────────────────────


def test_factory_builds_csv_backend(acme_field_mappings):
    config = {"type": "csv", "params": {"path": "engine/data/acme-saas"}}
    backend = build_backend(config, field_mapping_path=acme_field_mappings)
    assert isinstance(backend, CSVBackend)


def test_factory_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown data_access.type"):
        build_backend({"type": "made-up-backend"})


def test_factory_missing_type_raises():
    with pytest.raises(ValueError, match="data_access.type is required"):
        build_backend({"params": {}})


def test_factory_non_dict_raises():
    with pytest.raises(ValueError, match="data_access must be a dict"):
        build_backend("not a dict")


def test_factory_csv_requires_path_param():
    with pytest.raises(KeyError, match="path"):
        build_backend({"type": "csv", "params": {}})


def test_factory_resolves_relative_paths_against_repo_root(acme_field_mappings, tmp_path):
    """Per ARCHITECTURE.md, relative CSV paths resolve relative to repo root."""
    config = {
        "type": "csv",
        "params": {"path": "engine/data/acme-saas"},
    }
    backend = build_backend(config, field_mapping_path=acme_field_mappings)
    # Resolved path should be under the repo root, not cwd
    csv_path = backend.connector._data_dir
    assert csv_path.is_absolute()
    assert "engine/data/acme-saas" in str(csv_path)


def test_register_backend_extends_factory():
    """Forkers can register custom backend types."""
    sentinel = object()

    def builder(params, fm):
        return sentinel

    register_backend("test-custom-backend", builder)
    try:
        result = build_backend({"type": "test-custom-backend"})
        assert result is sentinel
    finally:
        # Clean up so other tests aren't polluted
        del _REGISTRY["test-custom-backend"]

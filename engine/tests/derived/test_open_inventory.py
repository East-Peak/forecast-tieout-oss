"""Tests for engine.gtm_model.derived.open_inventory."""
from __future__ import annotations

from datetime import date

from engine.connectors.interface import Deal
from engine.gtm_model.derived.open_inventory import (
    INVENTORY_STAGES,
    compute_open_inventory_snapshot,
)


def _deal(**overrides) -> Deal:
    base = dict(
        id="D",
        name="Test Deal",
        amount=100.0,
        stage="S2",
        close_date=None,
        owner_id="U1",
        is_closed=False,
        is_won=False,
    )
    base.update(overrides)
    return Deal(**base)


def test_empty_returns_empty_snapshot():
    snap = compute_open_inventory_snapshot([], date(2026, 4, 6))
    assert snap.opportunities == []
    assert snap.as_of == date(2026, 4, 6)
    assert snap.provenance["opp_count"] == 0


def test_includes_open_s2_through_s5():
    deals = [
        _deal(id="A", stage="S2", amount=100),
        _deal(id="B", stage="S3", amount=200),
        _deal(id="C", stage="S4", amount=300),
        _deal(id="D", stage="S5", amount=400),
    ]
    snap = compute_open_inventory_snapshot(deals, date(2026, 4, 6))
    ids = {o.opp_id for o in snap.opportunities}
    assert ids == {"A", "B", "C", "D"}


def test_excludes_pre_s2_stages():
    deals = [
        _deal(id="S0", stage="S0"),
        _deal(id="S1", stage="S1"),
        _deal(id="S2", stage="S2"),
    ]
    snap = compute_open_inventory_snapshot(deals, date(2026, 4, 6))
    assert {o.opp_id for o in snap.opportunities} == {"S2"}


def test_excludes_closed_deals():
    deals = [
        _deal(id="A", stage="S3", is_closed=False),
        _deal(id="B", stage="Won", is_closed=True, is_won=True),
        _deal(id="C", stage="Lost", is_closed=True, is_won=False),
    ]
    snap = compute_open_inventory_snapshot(deals, date(2026, 4, 6))
    assert {o.opp_id for o in snap.opportunities} == {"A"}


def test_sorts_by_amount_desc():
    deals = [
        _deal(id="SMALL", stage="S2", amount=100),
        _deal(id="LARGE", stage="S3", amount=500),
        _deal(id="MED", stage="S4", amount=300),
    ]
    snap = compute_open_inventory_snapshot(deals, date(2026, 4, 6))
    assert [o.opp_id for o in snap.opportunities] == ["LARGE", "MED", "SMALL"]


def test_populates_owner_forecast_source_fields():
    deals = [
        _deal(
            id="A", stage="S2", amount=100,
            owner_name="Alice", forecast_category="Commit",
            source_stream="Outbound", first_s2_entry_date=date(2026, 2, 1),
        ),
    ]
    snap = compute_open_inventory_snapshot(deals, date(2026, 4, 6))
    o = snap.opportunities[0]
    assert o.owner_name == "Alice"
    assert o.forecast_category == "Commit"
    assert o.source_stream == "Outbound"
    assert o.s2_date == "2026-02-01"


def test_to_dict_serializes_correctly():
    deals = [_deal(id="A", stage="S2", amount=100)]
    snap = compute_open_inventory_snapshot(deals, date(2026, 4, 6))
    d = snap.to_dict()
    assert d["as_of"] == "2026-04-06"
    assert len(d["opportunities"]) == 1
    assert d["opportunities"][0]["opp_id"] == "A"

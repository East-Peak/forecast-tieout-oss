"""Tests for engine.gtm_model.derived.arr_snapshot."""
from __future__ import annotations

from datetime import date

import pytest

from engine.connectors.interface import Deal
from engine.gtm_model.derived.arr_snapshot import compute_beginning_arr


def _won_deal(
    id: str,
    year_1_arr: float = 100000,
    effective_start: date = date(2025, 1, 1),
    effective_end: date = date(2027, 12, 31),
) -> Deal:
    return Deal(
        id=id,
        name=id,
        amount=year_1_arr,
        stage="Won",
        close_date=date(2025, 12, 31),
        owner_id="U1",
        is_closed=True,
        is_won=True,
        year_1_arr=year_1_arr,
        effective_start_date=effective_start,
        effective_end_date=effective_end,
    )


def test_empty_deals_returns_fallback():
    snapshot = compute_beginning_arr(
        [], date(2026, 2, 1), fallback_arr=5_000_000
    )
    assert snapshot.value == 5_000_000.0
    assert snapshot.is_live is False
    assert snapshot.method == "config_fallback"
    assert "no qualifying" in snapshot.warning.lower()


def test_sums_year1_arr_for_active_deals():
    deals = [
        _won_deal("D1", year_1_arr=300_000),
        _won_deal("D2", year_1_arr=500_000),
    ]
    snapshot = compute_beginning_arr(deals, date(2026, 2, 1))
    assert snapshot.value == 800_000.0
    assert snapshot.opp_count == 2
    assert snapshot.is_live is True
    assert snapshot.method == "active_won_opportunity_window"


def test_excludes_deals_outside_active_window():
    deals = [
        _won_deal(
            "EXPIRED",
            effective_start=date(2024, 1, 1),
            effective_end=date(2025, 12, 31),
        ),
        _won_deal(
            "FUTURE",
            effective_start=date(2027, 1, 1),
            effective_end=date(2027, 12, 31),
        ),
        _won_deal("ACTIVE", year_1_arr=100_000),
    ]
    snapshot = compute_beginning_arr(deals, date(2026, 2, 1))
    assert snapshot.value == 100_000.0
    assert snapshot.opp_count == 1


def test_excludes_open_deals():
    deal = _won_deal("OPEN")
    deal.is_won = False
    deal.is_closed = False
    snapshot = compute_beginning_arr([deal], date(2026, 2, 1), fallback_arr=10)
    assert snapshot.value == 10.0  # falls back


def test_falls_back_to_arr_when_year1_missing():
    deal = _won_deal("D1", year_1_arr=0)
    deal.year_1_arr = None
    deal.arr = 250_000
    snapshot = compute_beginning_arr([deal], date(2026, 2, 1))
    assert snapshot.value == 250_000.0


def test_to_tuple_matches_legacy_shape():
    snapshot = compute_beginning_arr(
        [_won_deal("D1", year_1_arr=100_000)],
        date(2026, 2, 1),
    )
    value, provenance = snapshot.to_tuple()
    assert value == 100_000.0
    assert provenance["is_live"] is True
    assert provenance["opp_count"] == 1
    assert provenance["method"] == "active_won_opportunity_window"

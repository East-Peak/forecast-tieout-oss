"""Tests for engine.gtm_model.derived.arr_movements."""
from __future__ import annotations

from datetime import date

from engine.connectors.interface import Deal
from engine.gtm_model.derived.arr_movements import compute_arr_movements


def _deal(**overrides) -> Deal:
    base = dict(
        id="D",
        name="X",
        amount=100.0,
        stage="Won",
        close_date=date(2026, 6, 1),
        owner_id="U1",
        is_closed=True,
        is_won=True,
        year_1_arr=100,
    )
    base.update(overrides)
    return Deal(**base)


def test_empty_input_zero_movements():
    m = compute_arr_movements([], date(2026, 1, 1), date(2026, 12, 31))
    assert m.new_logo_arr == 0.0
    assert m.expansion_arr == 0.0
    assert m.churn_arr == 0.0


def test_new_logo_bucket():
    deals = [_deal(revenue_type="new_logo", year_1_arr=300)]
    m = compute_arr_movements(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert m.new_logo_arr == 300.0
    assert m.new_logo_count == 1


def test_expansion_bucket():
    deals = [
        _deal(id="UP1", revenue_type="expansion", year_1_arr=50),
        _deal(id="UP2", revenue_type="upsell", year_1_arr=75),
    ]
    m = compute_arr_movements(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert m.expansion_arr == 125.0
    assert m.expansion_count == 2


def test_churn_bucket_uses_absolute_value():
    deals = [_deal(revenue_type="churn", year_1_arr=-200)]
    m = compute_arr_movements(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert m.churn_arr == 200.0
    assert m.churn_count == 1


def test_renewal_skipped():
    deals = [_deal(revenue_type="renewal", year_1_arr=500)]
    m = compute_arr_movements(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert m.new_logo_arr == 0
    assert m.expansion_arr == 0
    assert m.churn_arr == 0


def test_period_filter():
    deals = [
        _deal(id="EARLY", close_date=date(2025, 12, 1), revenue_type="new_logo"),
        _deal(id="IN", close_date=date(2026, 6, 1), revenue_type="new_logo"),
        _deal(id="LATE", close_date=date(2027, 1, 1), revenue_type="new_logo"),
    ]
    m = compute_arr_movements(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert m.new_logo_count == 1

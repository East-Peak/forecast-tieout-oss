"""Tests for engine.gtm_model.derived.monthly_actuals."""
from __future__ import annotations

from datetime import date

import pytest

from engine.connectors.interface import Deal
from engine.gtm_model.derived.monthly_actuals import compute_monthly_actuals


def _deal(**overrides) -> Deal:
    base = dict(
        id="D",
        name="X",
        amount=100.0,
        stage="S2",
        close_date=None,
        owner_id="U1",
        created_date=date(2026, 3, 15),
    )
    base.update(overrides)
    return Deal(**base)


def test_bookings_bucketed_by_close_date_month():
    deals = [
        _deal(id="W1", is_won=True, is_closed=True, amount=100, close_date=date(2026, 3, 5)),
        _deal(id="W2", is_won=True, is_closed=True, amount=200, close_date=date(2026, 3, 28)),
        _deal(id="W3", is_won=True, is_closed=True, amount=50, close_date=date(2026, 4, 1)),
    ]
    actuals = compute_monthly_actuals(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert actuals.monthly_bookings[date(2026, 3, 1)] == 300.0
    assert actuals.monthly_bookings[date(2026, 4, 1)] == 50.0


def test_bookings_use_year1_arr_when_available():
    deals = [
        _deal(
            is_won=True, is_closed=True,
            amount=999, year_1_arr=100,
            close_date=date(2026, 3, 5),
        ),
    ]
    actuals = compute_monthly_actuals(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert actuals.monthly_bookings[date(2026, 3, 1)] == 100.0


def test_losses_bucketed_separately():
    deals = [
        _deal(id="L1", is_won=False, is_closed=True, amount=80, close_date=date(2026, 5, 10)),
    ]
    actuals = compute_monthly_actuals(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert actuals.monthly_closed_lost[date(2026, 5, 1)] == 80.0
    assert date(2026, 5, 1) not in actuals.monthly_bookings


def test_creation_bucketed_by_created_date():
    deals = [
        _deal(amount=200, created_date=date(2026, 2, 15)),
    ]
    actuals = compute_monthly_actuals(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert actuals.monthly_pipeline_creation[date(2026, 2, 1)] == 200.0


def test_entered_s2_uses_first_s2_entry_date_when_present():
    deals = [
        _deal(
            id="A",
            amount=100,
            created_date=date(2026, 1, 5),
            first_s2_entry_date=date(2026, 4, 10),
        ),
    ]
    actuals = compute_monthly_actuals(deals, date(2026, 1, 1), date(2026, 12, 31))
    # Bucketed in April, not January, because first_s2_entry_date is April
    assert actuals.monthly_entered_s2[date(2026, 4, 1)] == 100.0
    assert date(2026, 1, 1) not in actuals.monthly_entered_s2


def test_entered_s2_falls_back_to_created_date():
    deals = [
        _deal(amount=100, created_date=date(2026, 1, 5), first_s2_entry_date=None),
    ]
    actuals = compute_monthly_actuals(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert actuals.monthly_entered_s2[date(2026, 1, 1)] == 100.0


def test_period_bounds_filter_each_series():
    deals = [
        _deal(id="W", is_won=True, is_closed=True, amount=100, close_date=date(2025, 12, 1)),  # before
        _deal(id="WIN", is_won=True, is_closed=True, amount=200, close_date=date(2026, 6, 1)),  # in
        _deal(id="WX", is_won=True, is_closed=True, amount=300, close_date=date(2027, 1, 1)),  # after
    ]
    actuals = compute_monthly_actuals(deals, date(2026, 1, 1), date(2026, 12, 31))
    assert sum(actuals.monthly_bookings.values()) == 200.0


def test_as_rows_returns_iso_dates():
    deals = [
        _deal(id="W", is_won=True, is_closed=True, amount=100, close_date=date(2026, 3, 5)),
    ]
    actuals = compute_monthly_actuals(deals, date(2026, 1, 1), date(2026, 12, 31))
    rows = actuals.as_rows()
    assert rows["monthly_bookings"][0]["month"] == "2026-03-01"
    assert rows["monthly_bookings"][0]["total"] == 100.0

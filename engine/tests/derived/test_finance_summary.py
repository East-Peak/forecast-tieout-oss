"""Tests for engine.gtm_model.derived.finance_summary."""
from __future__ import annotations

from datetime import date

import pytest

from engine.connectors.interface import Deal
from engine.gtm_model.derived.finance_summary import (
    FinanceSummary,
    compute_closed_won_finance_summary,
)


def _deal(**overrides) -> Deal:
    """Minimal Deal fixture with overridable fields."""
    base = dict(
        id="D1",
        name="Test",
        amount=100.0,
        stage="Won",
        close_date=date(2026, 3, 1),
        owner_id="U1",
        is_closed=True,
        is_won=True,
    )
    base.update(overrides)
    return Deal(**base)


def test_empty_deal_list_returns_zero_totals():
    summary = compute_closed_won_finance_summary(
        [], date(2026, 1, 1), date(2026, 12, 31)
    )
    assert summary.totals.won_count == 0
    assert summary.totals.amount == 0.0
    assert summary.by_type == {}


def test_only_won_deals_in_period_count():
    deals = [
        _deal(id="WON1", amount=100, year_1_arr=80, type="New Business"),
        _deal(id="WON2", amount=200, year_1_arr=150, type="New Business"),
        _deal(id="OPEN", is_won=False, is_closed=False, amount=999),
        _deal(id="LOST", is_won=False, is_closed=True, amount=999),
        _deal(
            id="OUT_OF_RANGE",
            close_date=date(2025, 12, 1),
            amount=999,
        ),
    ]
    summary = compute_closed_won_finance_summary(
        deals, date(2026, 1, 1), date(2026, 12, 31)
    )
    assert summary.totals.won_count == 2
    assert summary.totals.amount == 300.0
    assert summary.totals.year1_arr == 230.0


def test_by_type_groups_correctly():
    deals = [
        _deal(id="A", amount=100, type="New Business"),
        _deal(id="B", amount=50, type="Expansion"),
        _deal(id="C", amount=200, type="New Business"),
        _deal(id="D", amount=10, type=None),  # buckets under "Unknown"
    ]
    summary = compute_closed_won_finance_summary(
        deals, date(2026, 1, 1), date(2026, 12, 31)
    )
    assert summary.by_type["New Business"].won_count == 2
    assert summary.by_type["New Business"].amount == 300.0
    assert summary.by_type["Expansion"].won_count == 1
    assert summary.by_type["Unknown"].won_count == 1


def test_handles_none_numeric_fields():
    """Deal with None for amount/arr/etc shouldn't crash; treated as 0."""
    deals = [
        _deal(amount=None, year_1_arr=None, arr=None, nacv=None, non_recurring=None),
    ]
    summary = compute_closed_won_finance_summary(
        deals, date(2026, 1, 1), date(2026, 12, 31)
    )
    assert summary.totals.won_count == 1
    assert summary.totals.amount == 0.0


def test_excludes_deals_without_close_date():
    deals = [
        _deal(close_date=None),
    ]
    summary = compute_closed_won_finance_summary(
        deals, date(2026, 1, 1), date(2026, 12, 31)
    )
    assert summary.totals.won_count == 0


def test_to_dict_matches_legacy_shape():
    """Output shape must match what api.py / snapshot.py consumers expect."""
    deals = [_deal(amount=100, type="New Business")]
    summary = compute_closed_won_finance_summary(
        deals, date(2026, 1, 1), date(2026, 12, 31)
    )
    d = summary.to_dict()
    assert "totals" in d
    assert "by_type" in d
    assert "period" in d
    assert d["totals"]["won_count"] == 1
    assert d["period"]["start"] == "2026-01-01"
    assert d["period"]["end"] == "2026-12-31"

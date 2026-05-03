"""Tests for engine.gtm_model.derived.observed_velocity."""
from __future__ import annotations

from datetime import date, datetime

from engine.connectors.interface import Deal, StageTransition
from engine.gtm_model.derived.observed_velocity import compute_observed_velocity


def _deal(**overrides) -> Deal:
    base = dict(
        id="D",
        name="Test",
        amount=100.0,
        stage="S2",
        close_date=None,
        owner_id="U1",
        is_closed=False,
        is_won=False,
    )
    base.update(overrides)
    return Deal(**base)


def _trans(deal_id, to_stage, day, from_stage=None) -> StageTransition:
    return StageTransition(
        deal_id=deal_id,
        from_stage=from_stage,
        to_stage=to_stage,
        transition_date=datetime(2026, 1, day),
    )


def test_empty_inputs_returns_empty_profile():
    profile = compute_observed_velocity([], [], date(2026, 4, 6))
    assert profile.s2_to_won_rate is None
    assert profile.rolling_s2_to_won_rate is None
    assert profile.stage_velocity_days == {}
    assert profile.stage_win_rates == {}


def test_s2_to_won_rate_computed_from_history():
    deals = [
        _deal(id="W1", is_won=True, is_closed=True),
        _deal(id="W2", is_won=True, is_closed=True),
        _deal(id="L1", is_won=False, is_closed=True),
        _deal(id="OPEN", is_won=False, is_closed=False),
    ]
    history = [
        _trans("W1", "S2", 1),
        _trans("W2", "S2", 2),
        _trans("L1", "S2", 3),
        _trans("OPEN", "S2", 4),
    ]
    profile = compute_observed_velocity(deals, history, date(2026, 6, 1))
    # Won/Closed of those that entered S2: 2 won, 3 closed → 2/3
    assert profile.s2_to_won_rate == pytest_approx(2 / 3)


def test_stage_velocity_days_computed_from_transitions():
    """Days between S1 entry and S2 entry for one deal."""
    deals = [_deal(id="D1", is_closed=True, is_won=True)]
    history = [
        StageTransition(
            deal_id="D1", from_stage=None, to_stage="S1",
            transition_date=datetime(2026, 1, 1),
        ),
        StageTransition(
            deal_id="D1", from_stage="S1", to_stage="S2",
            transition_date=datetime(2026, 1, 11),  # 10 days later
        ),
        StageTransition(
            deal_id="D1", from_stage="S2", to_stage="S3",
            transition_date=datetime(2026, 1, 16),  # 5 days later
        ),
    ]
    profile = compute_observed_velocity(deals, history, date(2026, 6, 1))
    assert profile.stage_velocity_days["S1"] == 10.0
    assert profile.stage_velocity_days["S2"] == 5.0


def test_stage_win_rates():
    """Per-stage win rate = won deals that reached stage / closed deals
    that reached stage.
    """
    deals = [
        _deal(id="W1", is_won=True, is_closed=True),
        _deal(id="W2", is_won=True, is_closed=True),
        _deal(id="L1", is_won=False, is_closed=True),
    ]
    history = [
        _trans("W1", "S1", 1),
        _trans("W1", "S2", 2),
        _trans("W2", "S1", 1),
        _trans("L1", "S1", 1),
    ]
    profile = compute_observed_velocity(deals, history, date(2026, 6, 1))
    # All 3 closed deals reached S1; 2 won → 2/3
    assert profile.stage_win_rates["S1"] == pytest_approx(2 / 3)


# Tiny pytest-approx shim so we don't have to import math.isclose everywhere
def pytest_approx(value, rel=1e-6):
    import pytest
    return pytest.approx(value, rel=rel)

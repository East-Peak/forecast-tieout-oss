"""Tests for engine.gtm_model.derived.funnel."""
from __future__ import annotations

from datetime import datetime

import pytest

from engine.connectors.interface import Deal, StageTransition
from engine.gtm_model.derived.funnel import compute_funnel_rates


def _trans(deal_id, to_stage, from_stage=None) -> StageTransition:
    return StageTransition(
        deal_id=deal_id,
        from_stage=from_stage,
        to_stage=to_stage,
        transition_date=datetime(2026, 1, 1),
    )


def test_empty_returns_no_rates():
    rates = compute_funnel_rates([], [])
    assert rates.transitions == {}


def test_simple_advance_rate():
    """100% advance rate when every deal that hit S1 also hit S2."""
    history = [
        _trans("D1", "S1"),
        _trans("D1", "S2", from_stage="S1"),
        _trans("D2", "S1"),
        _trans("D2", "S2", from_stage="S1"),
    ]
    rates = compute_funnel_rates([], history)
    assert rates.transitions[("S1", "S2")] == pytest.approx(1.0)
    assert rates.sample_sizes[("S1", "S2")] == 2


def test_partial_advance_rate():
    """Only 1 of 2 S1 deals advance to S2 → 50%."""
    history = [
        _trans("D1", "S1"),
        _trans("D1", "S2", from_stage="S1"),
        _trans("D2", "S1"),  # didn't advance
    ]
    rates = compute_funnel_rates([], history)
    assert rates.transitions[("S1", "S2")] == pytest.approx(0.5)

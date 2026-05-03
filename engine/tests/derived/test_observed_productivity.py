"""Tests for engine.gtm_model.derived.observed_productivity.

CONTRACT NOTE: per a prior architectural review, this module's output
shape doesn't yet match the legacy `_get_observed_ae_productivity()`
contract (which returns S0_count + ramped_AE_months + productivity-rate
tuples). These tests pin the CURRENT pure-function shape (won-bookings
per AE in lookback window). future work will either extend this module's
output or have ProfileBackend.compute_observed_productivity() compose
the legacy shape from this output + roster ramp data.
"""
from __future__ import annotations

from datetime import date

from engine.connectors.interface import Deal, TeamMember
from engine.gtm_model.derived.observed_productivity import (
    ProductivityProfile,
    RampCurve,
    compute_observed_productivity,
    compute_observed_ae_ramp_curve,
)


def _ae(id, name="X", segment="Enterprise", start_date=date(2025, 1, 1)) -> TeamMember:
    return TeamMember(
        id=id, name=name, role="AE", segment=segment, start_date=start_date,
    )


def _deal(**overrides) -> Deal:
    base = dict(
        id="D",
        name="X",
        amount=100.0,
        stage="Won",
        close_date=date(2026, 3, 1),
        owner_id="U1",
        is_closed=True,
        is_won=True,
        year_1_arr=100,
    )
    base.update(overrides)
    return Deal(**base)


def test_empty_inputs_returns_empty_profile():
    profile = compute_observed_productivity([], [], date(2026, 4, 6))
    assert profile.by_ae == {}
    assert profile.overall_avg is None


def test_aggregates_by_ae_within_lookback():
    aes = [_ae("U1"), _ae("U2")]
    deals = [
        _deal(id="W1", owner_id="U1", year_1_arr=100, close_date=date(2026, 3, 1)),
        _deal(id="W2", owner_id="U1", year_1_arr=200, close_date=date(2026, 3, 15)),
        _deal(id="W3", owner_id="U2", year_1_arr=300, close_date=date(2026, 3, 20)),
    ]
    profile = compute_observed_productivity(
        deals, aes, date(2026, 4, 6), lookback_days=180
    )
    assert profile.by_ae["U1"] == 300.0
    assert profile.by_ae["U2"] == 300.0
    assert profile.overall_avg == 300.0


def test_excludes_non_ae_owners():
    aes = [_ae("U1")]
    deals = [
        _deal(owner_id="U1", year_1_arr=100),
        _deal(owner_id="UNKNOWN", year_1_arr=999),
    ]
    profile = compute_observed_productivity(deals, aes, date(2026, 4, 6))
    assert profile.by_ae == {"U1": 100.0}


def test_segment_aggregation():
    aes = [
        _ae("U1", segment="Enterprise"),
        _ae("U2", segment="Mid-Market"),
    ]
    deals = [
        _deal(owner_id="U1", year_1_arr=100),
        _deal(owner_id="U2", year_1_arr=50),
    ]
    profile = compute_observed_productivity(deals, aes, date(2026, 4, 6))
    assert profile.by_segment["Enterprise"] == 100.0
    assert profile.by_segment["Mid-Market"] == 50.0


def test_ramp_curve_buckets_by_tenure_month():
    """Tenure month = days(close - start) // 30."""
    aes = [_ae("U1", start_date=date(2025, 6, 1))]
    deals = [
        _deal(owner_id="U1", close_date=date(2025, 7, 5), year_1_arr=100),  # ~1 mo
        _deal(owner_id="U1", close_date=date(2025, 8, 15), year_1_arr=200),  # ~2 mo
    ]
    curve = compute_observed_ae_ramp_curve(
        deals, aes, date(2026, 4, 6), lookback_days=400
    )
    assert curve.sample_size == 2
    # Tenure month 1 should have one bookings record; month 2 the other
    assert any(curve.monthly_productivity.values())


def test_ramp_curve_excludes_pre_start_date():
    """Deals closed before AE start date are excluded."""
    aes = [_ae("U1", start_date=date(2026, 1, 1))]
    deals = [
        _deal(owner_id="U1", close_date=date(2025, 12, 1), year_1_arr=100),
    ]
    curve = compute_observed_ae_ramp_curve(deals, aes, date(2026, 4, 6))
    assert curve.sample_size == 0

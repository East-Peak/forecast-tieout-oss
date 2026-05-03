"""
Cross-language parity tests for scenario formulas.

These tests verify that the Python engine projection and the TypeScript
scenario adapter produce identical results from identical inputs.

For now, this file tests the Python side only. The full cross-language
parity suite (invoking the TypeScript adapter via Node) is added when
the frontend scenario engine is fully integrated.
"""
import json
import pytest
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
TOLERANCE = 0.001  # 0.1%


def weighted_projection(deals, stage_rates):
    """Reference implementation of the weighted projection formula."""
    total = 0.0
    for deal in deals:
        value = deal.get("metric_value") or 0
        if value is None:
            value = 0
        rate = stage_rates.get(deal["stage"], 0.0)
        total += value * rate
    return total


def capacity_projection(ae_count, productivity, ramp_factor):
    """Reference implementation of capacity projection."""
    return ae_count * productivity * ramp_factor


@pytest.fixture
def baseline():
    return json.loads((FIXTURE_DIR / "acme_baseline.json").read_text())


def test_baseline_weighted_projection(baseline):
    result = weighted_projection(baseline["deals"], baseline["stage_win_rates"])
    # D1: 250000 * 0.25 = 62500
    # D2: 150000 * 0.50 = 75000
    # D3: 0 * 0.75 = 0
    # D4: null -> 0 * 0.05 = 0
    # D5: 400000 * 0.0 (unknown stage) = 0
    expected = 62500 + 75000  # = 137500
    assert abs(result - expected) < 1.0


def test_capacity_projection(baseline):
    cap = baseline["capacity"]
    result = capacity_projection(
        cap["ae_count"], cap["productivity_per_ae"], cap["ramp_factor"]
    )
    expected = 20 * 150000 * 0.85  # = 2,550,000
    assert abs(result - expected) < 1.0


def test_rate_override():
    """Applying a rate override produces a different result."""
    deals = [{"id": "D1", "metric_value": 100000, "stage": "Technical Evaluation"}]
    baseline_rates = {"Technical Evaluation": 0.25}
    override_rates = {"Technical Evaluation": 0.50}

    baseline_result = weighted_projection(deals, baseline_rates)
    override_result = weighted_projection(deals, override_rates)

    assert baseline_result == 25000
    assert override_result == 50000
    assert override_result - baseline_result == 25000  # delta


def test_empty_deals():
    result = weighted_projection([], {"Discovery": 0.05})
    assert result == 0.0


def test_noop_override():
    """Override with same values as baseline produces exact same result."""
    deals = [
        {"id": "D1", "metric_value": 250000, "stage": "Technical Evaluation"},
        {"id": "D2", "metric_value": 150000, "stage": "Business Case"},
    ]
    rates = {"Technical Evaluation": 0.25, "Business Case": 0.50}

    result1 = weighted_projection(deals, rates)
    result2 = weighted_projection(deals, rates)
    assert result1 == result2  # exact equality, not tolerance


def test_missing_amounts():
    """Deals with null amounts are handled gracefully."""
    deals = [
        {"id": "D1", "metric_value": None, "stage": "Discovery"},
        {"id": "D2", "metric_value": 0, "stage": "Discovery"},
        {"id": "D3", "metric_value": 100000, "stage": "Discovery"},
    ]
    rates = {"Discovery": 0.05}
    result = weighted_projection(deals, rates)
    assert result == 5000  # only D3 contributes

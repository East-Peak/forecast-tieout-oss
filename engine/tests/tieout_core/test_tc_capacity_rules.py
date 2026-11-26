"""Goal 2B: the rules declared before any capacity score is computed.

This file and ``engine/tieout_core/capacity_rules.py`` are committed before the
code that produces the adoption scores they govern, so git history shows the
order. The numbers come from the design doc; the rest are builder calls, each
with its reason in the module docstring."""

from decimal import Decimal

from engine.tieout_core import capacity_rules as r


def test_the_adoption_thresholds_are_the_specs():
    assert r.MIN_STAFFING_VARIATION == Decimal("0.20")
    assert r.MIN_IMPROVEMENT == Decimal("0.10")
    assert r.SCORED_HORIZONS == (3, 6)
    assert r.MIN_FOLDS == 6


def test_the_ramp_and_attrition_cohort_minimums_are_the_specs():
    assert r.RAMP_FITTED_MONTHS == 6
    assert r.RAMP_MIN_REPS == 8
    assert r.RAMP_MIN_TENURED == 3
    assert r.TENURED_AFTER_MONTHS == 12
    assert r.MIN_DEPARTURES == 5


def test_recovery_is_judged_on_200_seeds_with_a_point_tolerance():
    assert r.RECOVERY_SEEDS == 200
    assert r.RECOVERY_MIN_COVERAGE == 0.90
    # basis: see the module docstring (expected standard errors on the fixtures)
    assert r.RAMP_POINT_TOLERANCE == 0.06
    assert r.ATTRITION_POINT_TOLERANCE == 0.004


def test_an_ae_month_is_a_fixed_length_so_a_constant_roster_is_a_constant_rate():
    assert r.DAYS_PER_AE_MONTH == Decimal("30.4375")  # 365.25 / 12
    assert r.TRAILING_DAYS == 365


def test_the_default_ramp_is_linear_over_six_months_and_the_default_attrition_is_stated():
    assert len(r.DEFAULT_RAMP) == 6
    assert r.DEFAULT_RAMP[0] == Decimal(1) / 12
    assert r.DEFAULT_RAMP[-1] == Decimal(11) / 12
    assert r.DEFAULT_MONTHLY_ATTRITION == Decimal("0.015")

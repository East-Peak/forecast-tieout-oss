"""The worksheet's definitions and gates, written down before any company is scored."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from engine.tieout_core import worksheet_rules as rules

D = Decimal


def quarter(**kw):
    base = rules.Quarter(
        "Q1FY25", date(2025, 2, 1), date(2025, 4, 30), 30, 8, True, D(6),
        D("0.2"), D(100), D(90), D(5),
    )  # fmt: skip
    return replace(base, **kw)


def test_the_declared_gates():
    assert rules.REQUIRED_QUARTERS == 6
    assert rules.MIN_CREATED_FOR_CONVERSION == 20
    assert rules.MIN_WINS_FOR_SIZE_OR_TIMING == 5
    assert rules.MIN_CREATED_FOR_PRODUCTIVITY == 20


def test_a_conversion_quarter_needs_maturity_and_twenty_created_deals():
    assert rules.eligible(quarter(created=20), rules.WIN_RATE) == (True, None)
    assert not rules.eligible(quarter(created=19), rules.WIN_RATE)[0]
    assert not rules.eligible(quarter(mature=False), rules.WIN_RATE)[0]


def test_size_and_cycle_need_maturity_and_five_wins():
    for driver in (rules.WON_ARR, rules.CYCLE_DAYS):
        assert rules.eligible(quarter(wins=5), driver) == (True, None)
        assert not rules.eligible(quarter(wins=4), driver)[0]
        assert not rules.eligible(quarter(mature=False), driver)[0]


def test_productivity_needs_exposure_and_twenty_created_but_not_maturity():
    assert rules.eligible(quarter(mature=False), rules.PRODUCTIVITY) == (True, None)
    assert not rules.eligible(quarter(exposure=D(0)), rules.PRODUCTIVITY)[0]
    assert not rules.eligible(quarter(created=19), rules.PRODUCTIVITY)[0]


def test_every_refusal_carries_a_reason_in_words():
    ok, why = rules.eligible(quarter(mature=False), rules.WIN_RATE)
    assert not ok and why and not any(c.isdigit() for c in why)


def test_halves_of_an_even_count_split_in_the_middle():
    # lower half 1, 2, 3 mean 2; upper half 10, 20, 30 mean 20
    assert rules.halves([D(x) for x in (30, 1, 20, 2, 10, 3)]) == (D(2), D(20))


def test_halves_of_an_odd_count_leave_the_middle_value_out_of_both():
    # 1, 2 | 50 | 10, 20 would be wrong order: sorted is 1, 2, 3, 10, 20 -> (1+2)/2, (10+20)/2
    assert rules.halves([D(x) for x in (20, 1, 3, 10, 2)]) == (D("1.5"), D(15))


def test_halves_need_two_values():
    with pytest.raises(ValueError):
        rules.halves([D(1)])


def test_historical_settings_need_six_values():
    assert rules.historical_settings([D(i) for i in range(5)]) is None
    s = rules.historical_settings([D(i) for i in (1, 2, 3, 4, 5, 6)])
    assert (s.low, s.high, s.minimum, s.maximum, s.count) == (D(2), D(5), D(1), D(6), 6)


def test_scaling_rounds_each_sample_up_to_whole_days():
    assert rules.scaled_days((10, 30, 31), Fraction(1, 2)) == (5, 15, 16)
    assert rules.scaled_days((10, 30), Fraction(0)) == (0, 0)
    assert rules.scaled_days((10, 30), Fraction(1)) == (10, 30)


def test_scale_steps_are_every_scale_where_a_rounded_day_changes():
    steps = rules.scale_steps((2, 3))
    assert steps == [
        Fraction(0),
        Fraction(1, 3),
        Fraction(1, 2),
        Fraction(2, 3),
        Fraction(1),
    ]
    # between two neighbors nothing changes; at each step the faster timing holds
    assert rules.scaled_days((2, 3), Fraction(1, 2)) == (1, 2)
    assert rules.scaled_days((2, 3), Fraction(1, 2) + Fraction(1, 100)) == (2, 2)


def test_quarter_labels_follow_the_fiscal_year_named_for_its_start_year():
    fy = date(2026, 2, 1)
    assert rules.quarter_label(date(2026, 2, 1), fy) == "Q1FY26"
    assert rules.quarter_label(date(2025, 11, 1), fy) == "Q4FY25"
    assert rules.quarter_label(date(2024, 2, 1), fy) == "Q1FY24"
    assert rules.quarter_label(date(2026, 11, 1), fy) == "Q4FY26"
    assert rules.quarter_label(date(2027, 2, 1), fy) == "Q1FY27"

"""The lanes' definitions and status rules, written down before any company is scored."""

from decimal import Decimal

import pytest

from engine.tieout_core import lanes_rules as rules

D = Decimal


def status(key, compared, goal, denominator=None):
    return rules.status(rules.COLUMN[key], compared, goal, denominator)


def test_the_eight_columns_in_the_specified_order_with_their_goal_labels():
    assert [(c.key, c.goal_label) for c in rules.COLUMNS] == [
        ("open", "frozen opening basis"),
        ("created", "derived requirement"),
        ("created_arr", "derived requirement"),
        ("win_rate", "plan-start assumption"),
        ("cycle", "model-implied benchmark"),
        ("won", "target-equivalent wins"),
        ("avg_won_arr", "model-implied benchmark"),
        ("bookings", "entered target"),
    ]


def test_behind_at_or_below_ninety_five_percent_of_the_goal_and_not_above_it():
    assert status("won", D("95"), D("100")) == ("behind", None, D("0.9500"))
    assert status("won", D("95.01"), D("100"))[0] == "on_track"
    assert status("won", D("300"), D("100"))[0] == "on_track"


def test_the_boundary_is_judged_on_the_exact_ratio_not_the_rounded_one():
    assert status("won", D("95.001"), D("100")) == ("on_track", None, D("0.9500"))
    assert status("cycle", D("104.999"), D("100"), 5)[0] == "on_track"


def test_cycle_days_are_reversed_behind_at_or_above_one_hundred_five_percent():
    assert status("cycle", D("105"), D("100"), 5)[0] == "behind"
    assert status("cycle", D("104.99"), D("100"), 5)[0] == "on_track"
    assert status("cycle", D("50"), D("100"), 5)[0] == "on_track"


def test_no_status_without_a_goal_or_a_figure_and_a_zero_goal_is_no_goal():
    assert status("won", D(1), None) == ("none", "no_goal", None)
    assert status("won", D(1), D(0)) == ("none", "no_goal", None)
    assert status("won", None, D(1)) == ("none", "not_modeled", None)


def test_a_ratio_with_a_small_denominator_has_no_status_and_says_why():
    assert status("win_rate", D("0.1"), D("0.2"), 19) == ("none", "too_few", None)
    assert status("win_rate", D("0.1"), D("0.2"), 20)[0] == "behind"
    assert status("avg_won_arr", D(1), D(2), 4)[1] == "too_few"
    assert status("avg_won_arr", D(1), D(2), 5)[0] == "behind"
    assert status("cycle", D(1), D(2), 4)[1] == "too_few"


def test_the_opening_stock_has_no_status_because_the_comparison_is_vacuous():
    assert status("open", D(10), D(10)) == ("none", "vacuous", None)


def test_the_minimums_are_defined_once_and_a_rate_is_compared_on_the_actual():
    assert rules.MIN_COHORT == 20 and rules.MIN_WINS == 5
    assert rules.COLUMN["win_rate"].compared == "actual"
    assert {c.compared for c in rules.COLUMNS if c.key != "win_rate"} == {"forecast"}


def test_every_reason_code_has_words():
    assert set(rules.REASONS) == {
        "no_goal",
        "not_modeled",
        "too_few",
        "vacuous",
        "not_compared_at_owner",
        "not_allocated",
    }


@pytest.mark.parametrize("key", [c.key for c in rules.COLUMNS])
def test_places_are_declared_for_every_column(key):
    assert rules.COLUMN[key].places in (0, 2, 4)


def owner(key, compared, goal):
    return rules.owner_status(rules.COLUMN[key], compared, goal)


def test_an_owner_is_judged_on_volumes_only_and_never_on_a_pooled_rate_or_size():
    for key in rules.RATIO_COLUMNS:
        assert owner(key, D("0.1"), D("0.2")) == ("none", "not_compared_at_owner", None)
    assert owner("won", D("95"), D(100)) == ("behind", None, D("0.9500"))
    assert owner("bookings", D(300), D(100))[0] == "on_track"


def test_an_owner_with_no_allocation_has_no_status_and_a_zero_allocation_is_no_goal():
    assert owner("bookings", D(5), None) == ("none", "not_allocated", None)
    assert owner("bookings", D(5), D(0)) == ("none", "no_goal", None)
    assert owner("open", D(5), None) == ("none", "vacuous", None)

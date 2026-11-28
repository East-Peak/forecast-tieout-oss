"""What an action on won ARR per win adds in expectation, on the small company the win-rate
tests calculate by hand (``test_tc_driver_actions``): two segments, a flat creation rate shared
0.75 to 0.25, a win rate of 0.2, a pooled won size of 1,000, and prices of two thirds of it for
``a`` and twice it for ``b``.

A target of ``T`` dollars on the pooled size of 1,000 is a change of ``T / 1000 - 1`` in the size
of every win of the deals the slice creates from the start, ramping in by creation date."""

from datetime import date
from decimal import Decimal

import pytest

from engine.tieout_core import driver_actions as da
from engine.tieout_core.plan import PlanAction

from .test_tc_driver_actions import AS_OF, BASELINE, at, frame, run
from .test_tc_driver_actions import act as win_rate_action

D = Decimal


def size(id="s", segment="b", start="2026-05-01", ramp=0, target="1100"):
    y, m, d = map(int, start.split("-"))
    return PlanAction(id, id, "won_arr", segment, date(y, m, d), ramp, D(target))


def test_a_size_target_is_a_change_in_the_size_of_a_win_from_the_start():
    e = run(size())  # b: +10% from May 1, the eleventh day
    assert e.sizes["b"][:10] == (D(0),) * 10
    assert e.sizes["b"][10] == D("0.1") == e.sizes["b"][364]
    assert e.sizes["a"] == (D(0),) * 365
    # 0.5 deals a day, won at 0.2, each 10% bigger than b's price of 2 (in units of 1,000)
    assert at(e, 10) == 0
    assert at(e, 11) == D("0.5") * D("0.2") * D("0.1") * 2


def test_the_wins_the_action_changes_are_not_more_or_fewer_only_bigger():
    e = run(size())
    assert e.changes["b"] == (D(0),) * 365  # no change in the win rate
    assert not any(e.lift.extra_wins("b"))  # nor more or fewer wins


def test_a_ramp_rises_by_creation_date_as_a_win_rate_does():
    e = run(size(ramp=2))  # May and June: 61 days
    assert e.sizes["b"][9] == 0
    assert e.sizes["b"][10] == D("0.1") / 61
    assert e.sizes["b"][70] == D("0.1")
    assert at(e, 11) == D("0.5") * D("0.2") * (D("0.1") / 61) * 2


def test_a_target_equal_to_the_baseline_or_no_actions_change_nothing():
    for none in (run(), run(size(target="1000"))):
        assert not none.lift
    assert run(size(target="1000")).lift == run().lift


def test_a_zero_size_removes_the_bookings_of_the_wins_it_changes_and_no_more():
    e = run(size(target="0"))
    # b's deals from the start book nothing: minus the whole of what they were to book
    assert at(e, 11) == -(D("0.5") * D("0.2") * 2)
    assert at(e, 10) == 0


def test_a_larger_size_adds_in_proportion():
    assert at(run(size(target="2000")), 11) == 10 * at(run(size(target="1100")), 11)


def test_the_company_is_the_same_action_in_every_segment_exactly():
    company = run(size(id="c", segment=None))
    each = run(size(id="x", segment="a"), size(id="y", segment="b"))
    assert company.sizes == each.sizes and company.lift == each.lift
    # the segments' prices add back to the pooled price, so the company books what changing
    # the pooled size would: 2 deals a day won at 0.2, each worth 1,000, 10% more
    assert at(company, 11) == D(2) * D("0.2") * D("0.1")


def test_a_size_and_a_win_rate_together_multiply_in_one_defined_way():
    both = run(size(), win_rate_action())  # b: +10% in size and +0.1 in win rate
    # 0.5 deals * (0.3 * 1.1 - 0.2) * price 2 = 0.5 * 0.13 * 2
    assert at(both, 11) == D("0.5") * (D("0.3") * D("1.1") - D("0.2")) * 2


def test_listing_actions_in_another_order_changes_nothing_to_the_last_digit():
    a, b = size(id="x", segment="a", ramp=3), win_rate_action(id="y", segment="b")
    assert run(a, b).lift == run(b, a).lift


def test_dropping_a_size_action_is_the_effect_of_the_others():
    a, b = size(id="x", segment="a"), size(id="y", segment="b")
    both = run(a, b)
    assert both.dropping(a).lift == run(b).lift
    assert both.dropping(a).dropping(b).lift == run().lift


def test_the_baseline_a_size_target_is_read_against_is_the_pooled_mean_won_arr():
    assert frame().size == D(1000)
    assert run(size(target="1100")).baseline == BASELINE  # the win rate's is untouched


def test_a_driver_with_no_rule_is_still_an_error():
    odd = PlanAction("x", "x", "cycle_days", None, date(2026, 5, 1), 0, D("1"))
    with pytest.raises(ValueError, match="no rule for the driver"):
        run(odd)


def test_the_effect_reads_the_frame_it_was_made_over():
    assert da.build_frame.__name__ == "build_frame" and AS_OF.year == 2026

"""What an action on cycle length does in expectation, on the small company the other action tests
calculate by hand (``test_tc_driver_actions``): two wins per deal's worth of timing, ten and twenty
days after creation, so the pooled cycle is 15 days; a win rate of 0.2; prices of two thirds and twice
the pooled one for ``a`` and ``b``. The as-of date is April 20: May 1 is day 11, April ends on day 10,
May on day 41.

A target of ``T`` days against the pooled 15 multiplies the lags of the slice's deals created from the
start by ``T / 15`` (ramping in by creation date) and rounds each up to a whole day. How many are won
and how big do not change; only the month they land in does, and each keeps the price of the month it
was to land in."""

import itertools
from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from engine.tieout_core import driver_actions as da
from engine.tieout_core.plan import PlanAction

from .test_tc_driver_actions import AS_OF, BASELINE, frame, run
from .test_tc_driver_actions import act as win_rate_action
from .test_tc_driver_actions_productivity import prod
from .test_tc_driver_actions_size import size

D = Decimal


def cyc(id="c", segment="b", start="2026-05-01", ramp=0, target="30"):
    y, m, d = map(int, start.split("-"))
    return PlanAction(id, id, "cycle_days", segment, date(y, m, d), ramp, D(target))


def test_the_baseline_is_the_pooled_mean_days_to_win_unrounded():
    assert frame().cycle == D(15)


def test_a_cycle_target_is_a_relative_change_in_the_lag_from_the_start_and_nothing_else():
    e = run(cyc())  # b: 30 days against 15, from the eleventh day
    assert e.cycles["b"][:10] == (D(0),) * 10
    assert e.cycles["b"][10] == D(1) == e.cycles["b"][364]
    assert e.cycles["a"] == (D(0),) * 365
    assert e.changes["b"] == e.sizes["b"] == e.creation["b"] == (D(0),) * 365
    assert e.lift.moved_days("b")[0] == 10 and e.lift.moved_days("a") == []
    assert not any(
        e.lift.priced(i) != [0] * 365 and any(e.lift.priced(i)) for i in range(13)
    )


def test_a_ramp_rises_by_creation_date_and_each_lag_is_rounded_up_to_a_whole_day():
    e = run(cyc(ramp=2))  # May and June: 61 days
    assert e.cycles["b"][10] == Fraction(1, 61)  # the start day is the first of 61
    f = Fraction(1) + Fraction(e.cycles["b"][10])
    assert f == Fraction(62, 61)
    assert e.lift.transport.scaled(f)[0] == (
        11,
        21,
    )  # 10 * 62/61 = 10.16 and 20 * 62/61 = 20.33


def test_a_target_equal_to_the_unrounded_baseline_or_no_actions_change_nothing():
    assert not run(cyc(target="15")).lift
    assert run(cyc(target="15")).lift == run().lift


def test_one_cohort_moves_by_hand_and_keeps_the_price_of_the_month_it_was_to_land_in():
    """Deals b creates on day 11 (0.5 of them, won at 0.2: 0.1 wins), lags 10 and 20, were to land
    on days 21 and 31, both May. At 30 days against 15 the lags are 20 and 40: days 31 (May) and
    51 (June). Half a win, 0.05, moves from May to June, at the price of May's atom."""
    f = frame()
    e = run(cyc())
    lift = replace(
        e.lift,
        cycle={
            "a": e.cycles["a"],
            "b": tuple(D(1) if t == 10 else D(0) for t in range(365)),
        },
    )
    price = f.price["b"][(1, f.origin[10])]
    assert (
        lift.moved(1) == -D("0.1") * price
    )  # May: the two wins were there, one now is
    assert lift.moved(2) == D("0.1") * price  # June: it lands there
    assert sum(lift.cycle_units("b")) == 0  # the same dollars, tail included


def test_a_cohort_never_loses_dollars_to_the_tail_it_only_moves_them():
    e = run(cyc(target="30"))
    for segment in ("a", "b"):
        assert abs(sum(e.lift.cycle_units(segment))) < D("1e-20")
    longer = run(cyc(target="30", segment=None))
    assert abs(
        sum(longer.lift.cycle_units("a")) + sum(longer.lift.cycle_units("b"))
    ) < D("1e-20")
    shorter = run(
        cyc(target="8", segment=None)
    )  # the pooled mean's half is the floor of the guardrail
    assert abs(sum(shorter.lift.cycle_units("b"))) < D("1e-20")


def test_a_longer_cycle_pushes_dollars_out_of_the_months_shown_and_a_shorter_one_pulls_them_in():
    longer, shorter = (
        run(cyc(target="30", segment=None)),
        run(cyc(target="8", segment=None)),
    )
    # what leaves the months shown is what the tail gains, to the last digit
    assert sum(longer.lift.cycle_units("b")[:-1]) == -longer.lift.cycle_units("b")[-1]
    assert (
        sum(longer.lift.cycle_units("b")[:-1])
        < 0
        < sum(shorter.lift.cycle_units("b")[:-1])
    )


def test_the_company_is_the_same_action_in_every_segment_and_untouched_segments_do_not_move():
    company = run(cyc(id="c", segment=None))
    each = run(cyc(id="x", segment="a"), cyc(id="y", segment="b"))
    assert company.cycles == each.cycles and company.lift == each.lift
    only_b = run(cyc())
    assert not any(only_b.lift.cycle_units("a"))
    assert only_b.lift.cycle_units("b") == company.lift.cycle_units("b")


def test_every_listing_order_of_four_actions_is_one_effect():
    acts = [
        win_rate_action(id="w", segment="b"),
        size(id="s", segment=None),
        prod(id="p", segment="a"),
        cyc(id="c", segment="b", ramp=2),
    ]
    base = run(*acts)
    for perm in itertools.permutations(acts):
        other = run(*perm)
        assert other.lift == base.lift
        assert [other.lift.moved(i) for i in range(13)] == [
            base.lift.moved(i) for i in range(13)
        ]


def test_dropping_one_of_four_actions_is_the_effect_of_the_other_three():
    acts = [win_rate_action(id="w"), size(id="s"), prod(id="p"), cyc(id="c")]
    whole = run(*acts)
    for i, dropped in enumerate(acts):
        rest = [a for k, a in enumerate(acts) if k != i]
        assert whole.dropping(dropped).lift == run(*rest).lift


def test_a_cycle_action_moves_the_dollars_the_other_drivers_set_not_the_ones_it_started_with():
    """Win rate up and size up on b, and a longer cycle: the cohort's dollars are the new ones, placed later."""
    e = run(win_rate_action(), size(), cyc())
    plain = run(win_rate_action(), size())
    # the same dollars together, whatever the timing
    made, was = e.lift.day_units("b", 10)
    assert made == D("0.5") * D("0.3") * D("1.1") and was == D("0.5") * D("0.2")
    assert plain.lift.moved(1) == 0


def test_a_negative_or_missing_baseline_is_an_error_not_a_division():
    f = frame()
    with pytest.raises(ValueError, match="has no baseline"):
        da.effect(replace(f, cycle=None), D("0.2"), AS_OF, (cyc(),))
    with pytest.raises(ValueError, match="has no baseline"):
        da.effect(replace(f, cycle=D(0)), BASELINE, AS_OF, (cyc(),))


# ----------------------------------------------------- the ratio stays rational down to the whole day


def exact_frame(lags=(15, 30)):
    from engine.tieout_core.fit import Timing

    from .test_tc_driver_actions import CAL, SEGMENTS, SHARES, SIZES, ground

    g = ground()
    g.model.new_pipeline.timing = Timing(lags, "t")
    return da.build_frame(g, SHARES, SIZES, CAL, (), (), SEGMENTS)


def test_a_ratio_that_does_not_end_in_decimal_digits_still_rounds_up_at_the_exact_whole_day():
    """Lags of 15 and 30 days, a pooled cycle of 22.5 and a target of 15: the lags are exactly two
    thirds of what they were, 10 and 20. A ratio rounded to 28 digits would give 10.0000...01 and
    round up to 11 and 21, and a deal created on May 21 would land on June 1, not May 31."""
    f = exact_frame()
    assert f.cycle == D("22.5")
    e = da.effect(
        f, BASELINE, AS_OF, (cyc(target="15", segment=None, start="2026-05-01"),)
    )
    scale = Fraction(1) + e.cycles["b"][40]
    assert scale == Fraction(2, 3) and isinstance(e.cycles["b"][40], Fraction)
    assert e.lift.transport.scaled(scale)[0] == (10, 20)
    # created May 21 (day 31): wins at 10 and 20 days land on May 31 (day 41) and June 10
    pieces = e.lift.transport.pieces(31, scale)
    assert [(p.original, p.moved) for p in pieces] == [
        (2, 1),
        (2, 2),
    ]  # the first stays in May


def test_a_ramp_over_a_repeating_fraction_of_a_month_is_exact_too():
    f = exact_frame(
        (21, 42)
    )  # a pooled cycle of 31.5; a target of 10.5 is a third of it
    e = da.effect(
        f,
        BASELINE,
        AS_OF,
        (cyc(target="10.5", segment="b", start="2026-06-01", ramp=3),),
    )
    for t in (
        40,
        41,
        71,
        200,
    ):  # June 1 is the 42nd day (index 41); June to August is 92 days
        share = min(Fraction(1), Fraction(max(t - 41 + 1, 0), 92))
        assert e.cycles["b"][t] == Fraction(-2, 3) * share and isinstance(
            e.cycles["b"][t], Fraction
        )
    third = (
        Fraction(1) + e.cycles["b"][71]
    )  # the thirty-first day in: 1 - 2/3 * 31/92 = 107/138
    assert third == Fraction(107, 138)
    assert e.lift.transport.scaled(third)[0] == (
        17,
        33,
    )  # 21 * 107/138 = 16.28, 42 * 107/138 = 32.6


def test_a_target_equal_to_an_exact_mean_that_is_not_a_decimal_changes_nothing():
    from engine.tieout_core.fit import Timing

    from .test_tc_driver_actions import CAL, SEGMENTS, SHARES, SIZES, ground

    g = ground()
    g.model.new_pipeline.timing = Timing((10, 20, 40), "t")  # a mean of 70/3
    f = da.build_frame(g, SHARES, SIZES, CAL, (), (), SEGMENTS)
    target = f.cycle  # the displayed 28-digit mean
    e = da.effect(f, BASELINE, AS_OF, (cyc(target=str(target)),))
    # the displayed figure is not the exact mean: a sliver of change, which no whole day sees
    assert all(abs(c) < Fraction(1, 10**20) for c in e.cycles["b"])
    assert e.lift.transport.scaled(Fraction(1) + e.cycles["b"][200])[0] == (10, 20, 40)

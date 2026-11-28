"""What an action on creation productivity adds in expectation, on the small company the other
action tests calculate by hand (``test_tc_driver_actions``): the flat creation rate is 2 deals a
day (the target is read against it), shared 0.75 to 0.25 into 1.5 and 0.5 organic deals a day
for ``a`` and ``b``; the win rate is 0.2 and the prices are two thirds and twice the pooled one.

A target of ``T`` on the pooled 2 a day multiplies the organic deals of the slice by ``T / 2``
from the start, ramping in by creation date. Programs' deals are not organic and do not move."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from engine.tieout_core import driver_actions as da
from engine.tieout_core.forecast import Inflow
from engine.tieout_core.plan import PlanAction

from .test_tc_driver_actions import (
    AS_OF,
    BASELINE,
    CAL,
    SEGMENTS,
    SHARES,
    SIZES,
    at,
    frame,
    ground,
    run,
)
from .test_tc_driver_actions import (
    act as win_rate_action,
)
from .test_tc_driver_actions_size import size

D = Decimal


def prod(id="p", segment="b", start="2026-05-01", ramp=0, target="3"):
    y, m, d = map(int, start.split("-"))
    return PlanAction(id, id, "productivity", segment, date(y, m, d), ramp, D(target))


def test_a_productivity_target_is_a_relative_change_in_the_slices_organic_creation():
    e = run(
        prod()
    )  # b: 3 deals a day against the pooled 2, from May 1, the eleventh day
    assert e.creation["b"][:10] == (D(0),) * 10
    assert e.creation["b"][10] == D("0.5") == e.creation["b"][364]
    assert e.creation["a"] == (D(0),) * 365
    # a quarter more deals: 0.5 more organic deals a day in b, won at 0.2, at b's price of 2
    assert at(e, 10) == 0
    assert at(e, 11) == D("0.25") * D("0.2") * 2


def test_it_changes_how_many_deals_are_created_not_how_likely_each_is_won_or_how_big():
    e = run(prod())
    assert e.changes["b"] == (D(0),) * 365 and e.sizes["b"] == (D(0),) * 365
    assert e.lift.created("b")[10] == D("0.75") and e.lift.created("b")[9] == D("0.5")
    assert e.lift.created("a") == tuple(frame().series["a"])  # untouched
    assert e.lift.extra_wins("b")[10] == D("0.25") * D("0.2")


def test_a_ramp_rises_by_creation_date_as_the_other_drivers_do():
    e = run(prod(ramp=2))  # May and June: 61 days
    assert e.creation["b"][9] == 0
    assert e.creation["b"][10] == D("0.5") / 61
    assert e.creation["b"][70] == D("0.5")
    assert at(e, 11) == D("0.5") * (D("0.5") / 61) * D("0.2") * 2


def test_a_target_equal_to_the_baseline_or_no_actions_change_nothing():
    for none in (run(), run(prod(target="2"))):
        assert not none.lift
    assert run(prod(target="2")).lift == run().lift


def test_a_zero_target_removes_the_organic_deals_wins_and_bookings_and_no_more():
    e = run(prod(target="0", segment=None))
    # every organic deal from the start: 2 a day, won at 0.2, at the prices of 2/3 and 2
    assert e.lift.extra_wins("a")[10] == -(D("1.5") * D("0.2"))
    assert e.lift.extra_wins("b")[10] == -(D("0.5") * D("0.2"))
    assert at(e, 11) == -(D("1.5") * D("0.2") * D(2) / 3 + D("0.5") * D("0.2") * 2)
    assert at(e, 10) == 0


def test_a_zero_target_leaves_the_programs_pipeline_exactly_as_it_was():
    flow = Inflow(10, 20, D(1000))  # 0.2 deals a day from day 11 to day 20, shared 3:1
    alone, with_program = (
        run(prod(target="0", segment=None)),
        run(prod(target="0", segment=None), inflows=(flow,)),
    )
    for s in ("a", "b"):
        assert with_program.lift.created(s)[10] == SHARES[s] * D(
            "0.2"
        )  # only the program's
        assert alone.lift.created(s)[10] == 0
    assert at(with_program, 11) == at(
        alone, 11
    )  # the removal does not touch what programs book
    assert with_program.lift.extra_wins("a")[10:15] == alone.lift.extra_wins("a")[10:15]


def test_a_programs_deals_are_not_made_more_by_more_productivity():
    flow = Inflow(10, 20, D(1000))
    plain = run(prod(target="4", segment=None), inflows=(flow,))
    assert plain.lift.created("b")[10] == 2 * D("0.5") + SHARES["b"] * D("0.2")
    assert plain.lift.extra_wins("b")[10] == D("0.5") * D("0.2")  # organic times 1 more


def test_the_company_is_the_same_action_in_every_segment_exactly():
    company = run(prod(id="c", segment=None))
    each = run(prod(id="x", segment="a"), prod(id="y", segment="b"))
    assert company.creation == each.creation and company.lift == each.lift
    # half again as many organic deals, won at 0.2, at each segment's price
    assert at(company, 11) == D("0.5") * D("0.2") * (D("1.5") * 2 / 3 + D("0.5") * 2)


def test_three_drivers_on_one_slice_multiply_in_one_defined_way():
    """b: win rate 0.2 to 0.3 (+0.1), size +10%, organic creation +50%: the wins are 0.75 deals
    at 0.3 where there were 0.5 at 0.2, each worth 1.1 times as much."""
    e = run(size(), win_rate_action(), prod())
    assert at(e, 11) == (D("0.75") * D("0.3") * D("1.1") - D("0.5") * D("0.2")) * 2
    assert e.lift.extra_wins("b")[10] == D("0.75") * D("0.3") - D("0.5") * D("0.2")


def test_listing_actions_in_another_order_changes_nothing_to_the_last_digit():
    a, b, c = (
        prod(id="x", segment="a", ramp=3),
        size(id="y", segment="b"),
        win_rate_action(id="z", segment="b"),
    )
    base = run(a, b, c)
    for other in ((c, b, a), (b, a, c), (c, a, b)):
        assert run(*other).lift == base.lift and run(*other).creation == base.creation


def test_dropping_one_of_three_actions_is_the_effect_of_the_other_two():
    a, b, c = prod(id="x", segment="a"), size(id="y"), win_rate_action(id="z")
    assert run(a, b, c).dropping(b).lift == run(a, c).lift
    assert run(a, b, c).dropping(a).dropping(b).dropping(c).lift == run().lift


def test_the_baseline_a_productivity_target_is_read_against_is_the_organic_rate_where_flat():
    assert frame().productivity == D(2)


def test_where_the_capacity_term_is_adopted_it_is_the_fitted_rate_per_ramped_ae_month():
    g = ground()
    g.cap = SimpleNamespace(adopted=True, fit=SimpleNamespace(rate=D("0.8")))
    assert da.wd.current_value(g, "productivity") == D("0.8")


def test_a_productivity_action_with_no_baseline_is_an_error():
    f = frame()
    from dataclasses import replace

    with pytest.raises(ValueError, match="has no baseline"):
        da.effect(replace(f, productivity=D(0)), D("0.2"), date(2026, 4, 20), (prod(),))


def mixed_frame():
    """The same company with programs whose deals are shared 0.2 to 0.8 rather than 0.75 to 0.25,
    so that organic creation and the programs' do not have the same mix of segments."""
    g = ground()
    organic = {"a": [D("1.5")] * 365, "b": [D("0.5")] * 365}
    program = {"a": [D("0.2")] * 365, "b": [D("0.8")] * 365}
    series = {s: [o + p for o, p in zip(organic[s], program[s])] for s in organic}
    landing, origin = da.day_cells(g, CAL.year.start, 365)
    return da.Frame(
        SEGMENTS,
        organic,
        program,
        series,
        da.price_index(g, series, SIZES, origin),
        landing,
        origin,
        D(1000),
        D(2),
    )


def cell_of(e, f, day):
    """The (window, quarter) cell the wins of ``day`` land in, ten days on."""
    return e.lift.landing[day + 9], f.origin[day - 1]


def test_a_zero_target_in_a_segment_leaves_exactly_its_program_wins_at_their_frozen_price():
    """One price per win in a segment, whoever created it: with a mix of organic and program
    deals that differs between segments, taking a segment's organic creation away leaves what it
    books from the programs' deals and never a residual below zero."""
    f = mixed_frame()
    e = da.effect(f, BASELINE, AS_OF, (prod(segment="a", target="0"),))
    land, origin = cell_of(e, f, 11)
    idx = f.price["a"][(land, origin)]
    extra = e.lift.extra("a", land)[10]
    assert (
        extra == -D("1.5") * D("0.2") * idx
    )  # the organic deals' wins, at the one price
    still = D("0.2") * D("0.2") * idx  # the programs' 0.2 deals a day, won at 0.2
    assert abs(D("1.7") * D("0.2") * idx + extra - still) < D("1e-20") and still > 0
    assert not any(e.lift.extra("b", land))  # nothing moves in the other segment


def test_a_segment_never_books_below_zero_whatever_the_three_drivers_do_to_it():
    f = mixed_frame()
    for u in ("0", "0.5", "3"):
        for z in ("0", "1000", "9000"):
            for p in ("0", "0.2", "0.9"):
                acts = (
                    prod(segment="a", target=u),
                    size(segment="a", target=z),
                    win_rate_action(segment="a", target=p),
                )
                e = da.effect(f, BASELINE, AS_OF, acts)
                land, origin = cell_of(e, f, 11)
                base = D("1.7") * BASELINE * f.price["a"][(land, origin)]
                assert base + e.lift.extra("a", land)[10] >= 0, (u, z, p)


def test_a_larger_size_after_a_zero_creation_never_lowers_what_the_company_books():
    f = mixed_frame()
    zero = da.effect(f, BASELINE, AS_OF, (prod(segment="a", target="0"),))
    both = da.effect(
        f,
        BASELINE,
        AS_OF,
        (prod(segment="a", target="0"), size(segment="a", target="2000")),
    )
    land, _ = cell_of(zero, f, 11)
    assert sum(both.lift.extra(s, land)[10] for s in "ab") >= sum(
        zero.lift.extra(s, land)[10] for s in "ab"
    )


def test_a_company_zero_target_removes_the_organic_wins_at_the_prices_the_plan_gives_them():
    f = mixed_frame()
    e = da.effect(f, BASELINE, AS_OF, (prod(segment=None, target="0"),))
    land, origin = cell_of(e, f, 11)
    want = -sum(
        o * BASELINE * f.price[s][(land, origin)]
        for s, o in (("a", D("1.5")), ("b", D("0.5")))
    )
    assert abs(at(e, 11) - want) < D("1e-20")

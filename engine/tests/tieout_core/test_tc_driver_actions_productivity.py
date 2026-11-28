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
        da.price_index(g, organic, SIZES, origin),
    )


def test_the_organic_deals_are_priced_so_that_a_company_change_books_what_the_pooled_rate_does():
    """Over all the wins the segments' prices add back to the pooled one; over the organic wins
    alone they do not unless the mix is the same. Organic creation is changed at its own index, so
    taking all of it away (company-wide, a zero target) takes the pooled bookings of 2 deals a
    day at 0.2 and 1,000 each, and leaves the programs' exactly."""
    f = mixed_frame()
    assert f.price["a"] != f.organic_price["a"]  # the mixes differ
    e = da.effect(f, BASELINE, AS_OF, (prod(segment=None, target="0"),))
    assert abs(at(e, 11) + D("0.4")) < D("1e-20")
    # the programs' own deals, priced in the plan: 1.0 a day at the pooled 0.2 and 1,000
    assert not da.effect(f, BASELINE, AS_OF, ()).lift


def test_a_company_change_is_the_pooled_change_whatever_the_mix_and_a_segments_is_its_own():
    f = mixed_frame()
    company = da.effect(f, BASELINE, AS_OF, (prod(segment=None, target="3"),))
    assert abs(at(company, 11) - D("0.5") * D(2) * D("0.2")) < D("1e-20")
    only_b = da.effect(f, BASELINE, AS_OF, (prod(segment="b", target="3"),))
    cell = (
        only_b.lift.landing[20],
        f.origin[10],
    )  # where the wins of day 11 land, ten days on
    assert at(only_b, 11) == D("0.5") * D("0.5") * D("0.2") * f.organic_price["b"][cell]

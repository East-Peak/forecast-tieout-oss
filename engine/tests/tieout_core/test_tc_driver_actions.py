"""What a win-rate action adds in expectation, on a company small enough to calculate by hand:
two segments, the flat creation rate shared by frozen shares, a pooled won size of 1,000, and a
segment size of 1,000 for ``a`` and 3,000 for ``b``, so ``a`` wins at two thirds of the pooled
price and ``b`` at twice it."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from engine.tieout_core import driver_actions as da
from engine.tieout_core import lanes_flows as flows
from engine.tieout_core.fiscal import FiscalYear
from engine.tieout_core.fit import Timing
from engine.tieout_core.forecast import Inflow
from engine.tieout_core.lanes_basis import Sizes
from engine.tieout_core.plan import PlanAction

D = Decimal
AS_OF = date(2026, 4, 20)  # day 1 is April 21; May 1 is day 11
CAL = flows.Calendar(FiscalYear(date(2026, 2, 1)))
SHARES = {"a": D("0.75"), "b": D("0.25")}
SEGMENTS = ("a", "b")
SIZES = {
    "a": Sizes(D(1000), "", D(500), ""),
    "b": Sizes(D(3000), "", D(500), ""),
}
BASELINE = D("0.2")


def ground():
    new = SimpleNamespace(
        win_rate=BASELINE,
        timing=Timing((10, 20), "test"),
        mean_won_arr=D(1000),
        mean_created_arr=D(500),
        created_per_day=D(2),
    )
    return SimpleNamespace(
        cap=SimpleNamespace(adopted=False),
        model=SimpleNamespace(new_pipeline=new),
        as_of=AS_OF,
        horizon_days=365,
    )


def frame(inflows=()):
    return da.build_frame(ground(), SHARES, SIZES, CAL, (), inflows, SEGMENTS)


def act(id="x", segment="b", start="2026-05-01", ramp=0, target="0.3"):
    y, m, d = map(int, start.split("-"))
    return PlanAction(id, id, "win_rate", segment, date(y, m, d), ramp, D(target))


def run(*actions, inflows=()):
    return da.effect(frame(inflows), BASELINE, AS_OF, actions)


def test_the_flat_creation_rate_is_shared_by_the_frozen_shares_and_a_segment_is_priced_by_its_size():
    f = frame()
    assert f.series["a"][0] == D("1.5") and f.series["b"][364] == D("0.5")
    assert len(f.series["a"]) == 365
    # in every cell a wins three times as much as b, so the pooled price is shared by 3:3000
    assert f.price["a"] == D(2) / D(3) and f.price["b"] == D(2)
    assert (
        sum(f.series[s][0] * f.price[s] for s in SEGMENTS)
        == D(2) * D("0.75") * D(2) / D(3) + D("0.5") * 2
    )  # wins weighted by price, for one day


def test_nothing_changes_before_the_start_and_all_of_it_after_with_no_ramp():
    e = run(act())  # b: +0.1 from May 1, the eleventh day
    assert e.changes["b"][:10] == (D(0),) * 10
    assert e.changes["b"][10] == D("0.1") == e.changes["b"][364]
    assert e.changes["a"] == (D(0),) * 365
    # 0.5 deals a day times 0.1 more wins each, at twice the pooled price
    assert e.lift[9] == 0 and e.lift[10] == D("0.1") == e.lift[364]


def test_a_ramp_rises_by_creation_date_from_the_start_to_the_months_end_and_holds():
    e = run(act(ramp=2))  # May and June: 61 days
    one_day = D("0.1") / 61
    assert e.changes["b"][9] == 0
    assert e.changes["b"][10] == one_day  # the start day is the first of 61
    assert e.changes["b"][11] == 2 * one_day
    assert e.changes["b"][70] == D("0.1")  # day 71 = July 1 - 1: the 61st day
    assert e.changes["b"][71] == D("0.1") == e.changes["b"][200]
    assert e.lift[10] == D("0.1") / 61  # 0.5 * (0.1 / 61) * 2


def test_the_start_day_of_a_ramp_is_the_first_day_of_its_first_month():
    e = run(act(start="2026-06-01", ramp=1))  # June has 30 days; June 1 is day 42
    assert e.changes["b"][40] == 0
    assert e.changes["b"][41] == D("0.1") / 30
    assert e.changes["b"][70] == D("0.1")  # June 30 is the 30th day
    assert e.changes["b"][71] == D("0.1")


def test_a_target_equal_to_the_baseline_or_no_actions_change_nothing():
    for none in (run(), run(act(target="0.2"))):
        assert not any(none.lift)
        assert all(not any(v) for v in none.changes.values())


def test_a_target_below_the_baseline_is_a_negative_change():
    e = run(act(target="0.15"))
    assert e.lift[10] == D("-0.05")


def test_the_company_is_the_same_action_in_every_segment_exactly():
    company = run(act(id="c", segment=None))
    each = run(act(id="x", segment="a"), act(id="y", segment="b"))
    assert company.changes == each.changes
    assert company.lift == each.lift
    # 1.5 * 0.1 * 2/3 + 0.5 * 0.1 * 2 on any day after the start
    assert company.lift[10] == D("0.1") + D("0.1")


def test_listing_actions_in_another_order_changes_nothing_to_the_last_digit():
    a, b = act(id="x", segment="a", ramp=3), act(id="y", segment="b", target="0.31")
    assert run(a, b).lift == run(b, a).lift
    assert run(a, b).changes == run(b, a).changes


def test_a_segment_action_leaves_every_other_segment_exactly_as_it_was():
    only_b = run(act(segment="b"))
    both = run(act(segment="b"), act(id="y", segment="a", target="0.4"))
    assert both.changes["b"] == only_b.changes["b"]
    assert only_b.changes["a"] == (D(0),) * 365


def test_dropping_an_action_is_the_effect_of_the_others():
    a, b = act(id="x", segment="a"), act(id="y", segment="b")
    both = run(a, b)
    assert both.dropping(a).lift == run(b).lift
    assert both.dropping(b).changes == run(a).changes
    assert both.dropping(a).dropping(b).lift == run().lift


def test_program_pipeline_is_created_in_segments_by_share_and_is_changed_once():
    # 1,000 of pipeline over days 11 to 20: 100 a day, 0.2 deals a day of 500
    flow = Inflow(10, 20, D(1000))
    plain, with_program = (
        run(act(segment=None)),
        run(act(segment=None), inflows=(flow,)),
    )
    f = frame((flow,))
    assert f.series["a"][10] == D("1.5") + D("0.75") * D("0.2")
    assert f.series["b"][10] == D("0.5") + D("0.25") * D("0.2")
    # the extra lift is the program's deals times the change times each segment's price
    extra = D("0.2") * D("0.1") * (D("0.75") * D(2) / D(3) + D("0.25") * 2)
    assert with_program.lift[10] - plain.lift[10] == extra
    assert with_program.lift[20] == plain.lift[20]  # the program is over


def test_an_action_for_a_segment_with_no_lane_is_an_error():
    with pytest.raises(ValueError, match="no lane"):
        run(act(segment="zzz"))


def test_a_driver_with_no_rule_is_an_error_not_a_win_rate():
    odd = PlanAction("x", "x", "won_arr", None, date(2026, 5, 1), 0, D("1"))
    with pytest.raises(ValueError, match="no rule for the driver"):
        run(odd)


def test_the_section_says_plainly_that_a_segments_target_is_not_a_measured_rate():
    assert "an entered change on the pooled baseline win rate" in da.DEFINITION
    assert "not a win rate that was measured for the segment" in da.DEFINITION

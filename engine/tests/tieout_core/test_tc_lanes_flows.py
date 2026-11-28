"""Expected wins, bookings and win days by segment, by the quarter they land in and the quarter
their deal was created in, on a model small enough to calculate by hand."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from engine.tieout_core import lanes_flows as flows
from engine.tieout_core.fiscal import FiscalYear
from engine.tieout_core.fit import Timing
from engine.tieout_core.forecast import Inflow
from engine.tieout_core.records import Deal

D = Decimal
AS_OF = date(2026, 4, 20)
CAL = flows.Calendar(FiscalYear(date(2026, 2, 1)))


def timing(days=(10, 20), weights=None):
    return Timing(days, "test", weights)


def model(p=None, win_rate=None, t=None):
    p, win_rate, t = p or D("0.5"), win_rate or D("0.2"), t or timing()
    return SimpleNamespace(
        win_rate=lambda stage, age: p,
        timing=lambda stage, age: t,
        new_pipeline=SimpleNamespace(win_rate=win_rate, timing=t, mean_won_arr=D(1000)),
    )


def open_deal(created, arr="1000", segment="a"):
    return Deal(
        1, "d", "new_business", segment, "S1", D(arr), created, None, False, False
    )


def test_mass_is_the_timing_curve_and_its_day_weighted_moment():
    m = flows.Mass(timing())
    assert m.through(-1) == (0, 0)
    assert m.through(10) == (D("0.5"), D(5))
    assert m.through(25) == (D(1), D(15))
    w = flows.Mass(timing((5, 9), (D(3), D(1))))
    assert w.through(5) == (D("0.75"), D("3.75"))
    assert w.through(9)[0] == timing((5, 9), (D(3), D(1))).cdf(9)


def test_the_calendar_names_the_quarter_a_date_falls_in_with_zero_before_the_year():
    assert CAL.bucket(date(2026, 1, 5)) == 0
    assert CAL.bucket(date(2026, 1, 31)) == 0 and CAL.bucket(date(2026, 2, 1)) == 1
    assert CAL.bucket(date(2026, 4, 30)) == 1 and CAL.bucket(date(2026, 5, 1)) == 2
    assert CAL.bucket(date(2027, 1, 31)) == 4 and CAL.bucket(date(2027, 2, 1)) == 5


def test_apportion_gives_each_piece_its_share_and_the_pieces_add_to_the_total_exactly():
    assert flows.apportion(D("10.00"), [D(1), D(1), D(1)]) == [
        D("3.34"),
        D("3.33"),
        D("3.33"),
    ]
    assert flows.apportion(D("0.01"), [D(1), D(1)]) == [D("0.01"), D("0.00")]
    assert flows.apportion(D(0), [D(0), D(0)]) == [D(0), D(0)]
    assert sum(flows.apportion(D("1234.57"), [D(7), D(11), D(13)])) == D("1234.57")
    with pytest.raises(ValueError):
        flows.apportion(D(5), [D(0)])


def test_an_open_deal_wins_in_the_quarter_its_timing_lands_in_and_keeps_its_origin():
    got = flows.existing_flows(model(), [open_deal(date(2026, 3, 1))], AS_OF, CAL)
    # age 50 days; Q1 ends 10 days on, Q2 runs from day 10 to day 102
    assert got[("a", 0, 1)] == flows.Flow(D("0.25"), D(250), D("15"))
    assert got[("a", 1, 1)] == flows.Flow(D("0.25"), D(250), D("17.5"))
    assert set(got) == {("a", 0, 1), ("a", 1, 1)}


def test_a_deal_created_before_the_year_has_origin_zero():
    got = flows.existing_flows(model(), [open_deal(date(2026, 1, 5))], AS_OF, CAL)
    assert {origin for _, _, origin in got} == {0}


def test_a_deal_with_no_stage_or_no_amount_is_left_out_as_the_forecast_leaves_it_out():
    unknown = Deal(
        2,
        "u",
        "new_business",
        "a",
        "Unknown",
        D(5),
        date(2026, 3, 1),
        None,
        False,
        False,
    )
    assert flows.existing_flows(model(), [unknown], AS_OF, CAL) == {}


def test_new_pipeline_wins_at_the_pooled_size_in_the_quarter_after_its_creation_day():
    won, created = flows.new_flows(model(), {"a": [D(1)] + [D(0)] * 9}, AS_OF, CAL)
    # created on 21 April (Q1); both its wins (day 11, 21) land after Q1 ends on day 10
    assert won == {("a", 1, 1): flows.Flow(D("0.2"), D(200), D(3))}
    assert created == {("a", 1): D(1)}


def test_creation_after_the_fiscal_year_ends_is_not_counted():
    days = (date(2027, 1, 31) - AS_OF).days
    _, created = flows.new_flows(model(), {"a": [D(1)] * (days + 5)}, AS_OF, CAL)
    assert sum(created.values()) == days


def test_the_pieces_of_a_series_split_between_segments_add_up_to_the_whole():
    whole, _ = flows.new_flows(model(), {"x": [D(3)] * 200}, AS_OF, CAL)
    split, _ = flows.new_flows(
        model(), {"a": [D(1)] * 200, "b": [D(2)] * 200}, AS_OF, CAL
    )
    for q in range(4):
        for origin in range(5):
            parts = [split.get((s, q, origin), flows.ZERO_FLOW) for s in "ab"]
            total = whole.get(("x", q, origin), flows.ZERO_FLOW)
            assert sum((p.wins for p in parts), D(0)) == total.wins


def test_program_dollars_become_deals_per_day_over_the_days_they_are_created():
    got = flows.inflow_series([Inflow(2, 4, D(600))], D(100), 6)
    assert got == [D(0), D(0), D(3), D(3), D(0), D(0)]  # 600 over two days at 100 each
    assert flows.inflow_series([Inflow(2, 4, D(600))], D(100), 3) == [D(0), D(0), D(3)]
    assert flows.inflow_series([Inflow(2, 4, D(600))], D(0), 3) == [D(0)] * 3


def test_a_creation_series_is_split_by_share_and_programs_follow_the_same_shares():
    got = flows.segment_series(
        {"a": [D(1), D(1)], "b": [D(3), D(3)]},
        [D(0), D(4)],
        {"a": D("0.25"), "b": D("0.75")},
    )
    assert got == {"a": [D(1), D(2)], "b": [D(3), D(6)]}


def test_a_deal_with_a_blank_segment_belongs_to_the_unassigned_lane():
    got = flows.existing_flows(model(), [open_deal(date(2026, 3, 1), segment="")], AS_OF, CAL)  # fmt: skip
    assert {segment for segment, _, _ in got} == {"unassigned"}

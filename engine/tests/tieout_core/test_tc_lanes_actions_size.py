"""The swimlane grid with won-ARR actions: a segment's average won ARR forecast follows the
size its actions leave, its bookings with it, and no count, goal or actual moves."""

from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import driver_actions as da
from engine.tieout_core import lanes, lanes_basis
from engine.tieout_core.report import prepare

from .test_tc_lanes_actions import (
    COMPANY,
    FY,
    HIRES,
    PROGRAMS,
    Q3,
    REST,
    SEGMENTS,
    build,
    problems,
    row,
)

D = Decimal


@pytest.fixture(scope="module")
def world():
    with gen.in_repo():
        state = prepare(gen.PROFILES / COMPANY, gen.DATA / COMPANY, gen.AS_OF, 200, 0)
        basis = lanes_basis.plan_basis(state)
    return state, basis


def size(id="s", slice="company", start="2026-09", ramp=0, target=None):
    return {
        "id": id, "name": id, "driver": "won_arr", "slice": slice, "start": start,
        "ramp_months": ramp, "target": str(target),
    }  # fmt: skip


def bigger(world, percent):
    return (world[0].ground.model.new_pipeline.mean_won_arr * (100 + D(percent)) / 100).quantize(D("0.0001"))  # fmt: skip


def cell(doc, period, column, *path):
    return row(doc, period, *path)["cells"][column]


def test_a_size_action_moves_the_bookings_and_the_average_not_the_counts(world):
    _, plain, _ = build(world, hires=HIRES, programs=PROGRAMS)
    report, doc, _ = build(
        world,
        size(slice="enterprise", target=bigger(world, 20)),
        hires=HIRES,
        programs=PROGRAMS,
    )
    for column in ("won", "created", "created_arr"):
        for period in plain["periods"]:
            for r0, r1 in zip(period["rows"], next(p for p in doc["periods"] if p["key"] == period["key"])["rows"]):  # fmt: skip
                assert r0["cells"][column]["forecast"] == r1["cells"][column]["forecast"], (
                    period["key"], r0["path"], column,
                )  # fmt: skip
    mine, theirs = cell(doc, FY, "avg_won_arr", "segment", "enterprise"), cell(plain, FY, "avg_won_arr", "segment", "enterprise")  # fmt: skip
    assert D(mine["forecast"]) > D(theirs["forecast"])
    assert D(cell(doc, FY, "bookings", "segment", "enterprise")["forecast"]) > D(
        cell(plain, FY, "bookings", "segment", "enterprise")["forecast"]
    )
    for seg in (
        "mid_market",
        "commercial",
    ):  # no other segment moves, but for a cent in the rounding
        got, was = cell(doc, FY, "bookings", "segment", seg), cell(plain, FY, "bookings", "segment", seg)  # fmt: skip
        assert abs(D(got["forecast"]) - D(was["forecast"])) <= D("0.02")
    assert problems(world, report, doc) == []


def test_goals_actuals_and_the_basis_digest_never_move(world):
    _, plain, _ = build(world)
    report, doc, _ = build(world, size(target=bigger(world, 30)))
    for period in plain["periods"]:
        for r0, r1 in zip(period["rows"], next(p for p in doc["periods"] if p["key"] == period["key"])["rows"]):  # fmt: skip
            for column, c0 in r0["cells"].items():
                assert r1["cells"][column]["actual"] == c0["actual"]
                assert r1["cells"][column]["goal"] == c0["goal"]
    assert doc["plan_basis"] == plain["plan_basis"]
    assert problems(world, report, doc) == []


def test_a_company_size_action_is_the_same_action_in_every_segment(world):
    target = bigger(world, 10)
    _, one, _ = build(world, size("c", "company", ramp=2, target=target))
    _, many, _ = build(world, *(size(s, s, ramp=2, target=target) for s in SEGMENTS))
    assert one["periods"] == many["periods"]


def test_a_target_equal_to_the_pooled_mean_changes_no_period_of_the_grid(world):
    _, plain, _ = build(world, hires=HIRES, programs=PROGRAMS)
    pooled = world[0].ground.model.new_pipeline.mean_won_arr
    _, same, _ = build(world, size(target=pooled), hires=HIRES, programs=PROGRAMS)
    assert (
        same["periods"] == plain["periods"]
        and same["plan_basis"] == plain["plan_basis"]
    )


def test_the_grid_the_report_and_the_removal_values_agree_after_a_size_and_a_rate(
    world,
):
    report, doc, _ = build(
        world,
        size("s", "enterprise", target=bigger(world, 15)),
        {
            "id": "r", "name": "r", "driver": "win_rate", "slice": "enterprise",
            "start": "2026-09", "ramp_months": 0, "target": "0.30",
        },
        hires=HIRES,
        programs=PROGRAMS,
    )  # fmt: skip
    _, bare, _ = build(world, hires=HIRES, programs=PROGRAMS)
    d = report["driver_actions"]
    with_ = D(cell(doc, FY, "bookings", "total")["forecast"])
    without = D(cell(bare, FY, "bookings", "total")["forecast"])
    assert with_ - without == D(d["joint_gain"][REST])
    assert D(row(doc, Q3, "total")["cells"]["bookings"]["forecast"]) == D(d["with_actions"]["quarters"][2]["expected"])  # fmt: skip
    assert report["driver_actions"]["reconciliation"]["material"][REST] is True
    check = next(c for c in doc["checks"] if c["name"] == "lane action bookings reproduce the report's joint gain")  # fmt: skip
    assert check["passed"] and da.REINFORCE == d["reconciliation"]["sentences"][REST]
    assert problems(world, report, doc) == []


def test_the_caveat_names_what_the_plan_acts_on(world):
    _, win_only, _ = build(world, {
        "id": "r", "name": "r", "driver": "win_rate", "slice": "company",
        "start": "2026-09", "ramp_months": 0, "target": "0.30",
    })  # fmt: skip
    _, sized, _ = build(world, size(target=bigger(world, 10)))
    assert lanes.ACTIONS_CAVEAT in win_only["caveats"]
    assert lanes.ACTIONS_CAVEAT not in sized["caveats"]
    assert lanes.ACTIONS_CAVEAT_ANY in sized["caveats"]


def test_a_zero_size_from_the_first_day_leaves_no_new_booking_in_any_lane_and_none_below_zero(
    world,
):
    """Baseline lane bookings and an action's change are priced on the same atoms (each month a
    win lands in, by the quarter its deal was created in), so taking all the size away leaves each
    lane exactly no new booking: nothing negative where segments' mixes change
    month by month within a quarter."""
    from engine.tieout_core import actions, lanes_basis
    from engine.tieout_core import lanes_flows as flows
    from engine.tieout_core.plan import parse_plan

    state, basis = world
    seg = ["enterprise", "mid_market", "commercial"]
    h, i = actions.plan_inputs(
        state.ground, parse_plan({"hires": HIRES, "programs": PROGRAMS}, state.as_of, state.cap.members, "p")
    )  # fmt: skip
    plan = parse_plan(
        {"actions": [size(target="0")], "hires": HIRES, "programs": PROGRAMS},
        state.as_of, state.cap.members, "p",
    )  # fmt: skip
    cal = flows.Calendar(state.profile.fiscal_year)
    sizes = lanes_basis.sizes_now(state.ground, state.params.trailing_days, seg)
    scen = actions.Scenario(state.ground)
    effect = da.effect_for(state, plan, h, i)
    priced = lanes._remainder(state, basis, cal, h, i, seg, sizes, scen, effect)[4]
    for (
        key,
        flow,
    ) in priced.items():  # the new pipeline's wins, priced, with the action's change
        assert abs(flow.bookings) < D("1e-9"), (key, flow.bookings)

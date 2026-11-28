"""The swimlane grid with cycle actions: won deals and bookings move between the quarters the wins
land in, a lane's cycle is the mean lag of the wins landing in the period (not the target), created
deals and ARR do not move, and nothing a plan does not touch does."""

from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, lanes, lanes_basis
from engine.tieout_core import driver_actions as da
from engine.tieout_core import lanes_flows as flows
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import prepare
from engine.tieout_core.worksheet_drivers import current_value
from engine.tieout_core.worksheet_rules import CYCLE_DAYS

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


def cyc(world, ratio, id="c", slice="company", start="2026-09", ramp=0):
    target = (current_value(world[0].ground, CYCLE_DAYS) * D(ratio)).quantize(
        D("0.0001")
    )
    return {
        "id": id, "name": id, "driver": "cycle_days", "slice": slice, "start": start,
        "ramp_months": ramp, "target": str(target),
    }  # fmt: skip


def cell(doc, period, column, *path):
    return row(doc, period, *path)["cells"][column]


def test_a_shorter_cycle_moves_wins_into_the_year_and_the_lane_shows_the_lag_of_the_wins_that_land(
    world,
):
    report, doc, _ = build(world, cyc(world, "0.7"), hires=HIRES, programs=PROGRAMS)
    _, plain, _ = build(world, hires=HIRES, programs=PROGRAMS)
    assert D(cell(doc, FY, "won", "total")["forecast"]) > D(
        cell(plain, FY, "won", "total")["forecast"]
    )
    assert D(cell(doc, FY, "bookings", "total")["forecast"]) > D(cell(plain, FY, "bookings", "total")["forecast"])  # fmt: skip
    mine, was = cell(doc, FY, "cycle", "total"), cell(plain, FY, "cycle", "total")
    assert D(mine["forecast"]) < D(was["forecast"])
    # the cell is the day-weighted numerator over the wins, as the file says, not the target
    parts = mine["parts"]["forecast"]
    assert abs(
        D(parts["numerator"]) / D(parts["denominator"]) - D(mine["forecast"])
    ) < D("0.0051")
    assert D(mine["forecast"]) != D(cyc(world, "0.7")["target"])
    for column in (
        "created",
        "created_arr",
    ):  # how many deals are created does not change
        assert cell(doc, FY, column, "total") == cell(plain, FY, column, "total")
    assert problems(world, report, doc) == []


def test_goals_actuals_and_the_basis_digest_never_move(world):
    _, plain, _ = build(world, hires=HIRES)
    report, doc, _ = build(world, cyc(world, "1.4"), hires=HIRES)
    for period in plain["periods"]:
        mine = next(p for p in doc["periods"] if p["key"] == period["key"])
        for r0, r1 in zip(period["rows"], mine["rows"]):
            for column, c0 in r0["cells"].items():
                assert r1["cells"][column]["actual"] == c0["actual"]
                assert r1["cells"][column]["goal"] == c0["goal"]
    assert doc["plan_basis"] == plain["plan_basis"]
    assert problems(world, report, doc) == []


def test_the_grid_the_report_and_the_removal_values_agree_with_four_drivers(world):
    g = world[0].ground
    acts = [
        cyc(world, "0.8", id="c", slice="enterprise"),
        {"id": "s", "name": "s", "driver": "won_arr", "slice": "enterprise", "start": "2026-09",
         "ramp_months": 0, "target": str(g.model.new_pipeline.mean_won_arr * D("1.1"))},
        {"id": "r", "name": "r", "driver": "win_rate", "slice": "enterprise", "start": "2026-09",
         "ramp_months": 0, "target": str(g.model.new_pipeline.win_rate * D("1.2"))},
        {"id": "p", "name": "p", "driver": "productivity", "slice": "mid_market", "start": "2026-09",
         "ramp_months": 0, "target": str(current_value(g, "productivity") * D("1.3"))},
    ]  # fmt: skip
    report, doc, _ = build(world, *acts, hires=HIRES, programs=PROGRAMS)
    _, bare, _ = build(world, hires=HIRES, programs=PROGRAMS)
    d = report["driver_actions"]
    with_ = D(cell(doc, FY, "bookings", "total")["forecast"])
    without = D(cell(bare, FY, "bookings", "total")["forecast"])
    assert with_ - without == D(d["joint_gain"][REST])
    assert D(cell(doc, Q3, "bookings", "total")["forecast"]) == D(d["with_actions"]["quarters"][2]["expected"])  # fmt: skip
    check = next(c for c in doc["checks"] if c["name"] == "lane action bookings reproduce the report's joint gain")  # fmt: skip
    assert check["passed"]
    assert (
        sum(D(cell(doc, FY, "bookings", "segment", s)["forecast"]) for s in SEGMENTS)
        == with_
    )
    assert (
        problems(world, report, doc) == []
    )  # owners add to segments, segments to the company


def test_a_company_action_is_the_same_action_in_every_segment(world):
    _, one, _ = build(world, cyc(world, "0.8", id="c", ramp=2), hires=HIRES)
    _, many, _ = build(world, *(cyc(world, "0.8", id=s, slice=s, ramp=2) for s in SEGMENTS), hires=HIRES)  # fmt: skip
    assert one["periods"] == many["periods"]


def test_a_target_equal_to_the_unrounded_baseline_changes_no_period_of_the_grid(world):
    _, plain, _ = build(world, hires=HIRES, programs=PROGRAMS)
    base = current_value(world[0].ground, CYCLE_DAYS)
    act = {**cyc(world, "1"), "target": str(base)}
    _, same, _ = build(world, act, hires=HIRES, programs=PROGRAMS)
    assert (
        same["periods"] == plain["periods"]
        and same["plan_basis"] == plain["plan_basis"]
    )


def test_other_segments_unrounded_forecasts_do_not_move_and_no_lane_goes_negative(
    world,
):
    state, basis = world
    seg = ["enterprise", "mid_market", "commercial"]
    plan = parse_plan({"actions": [cyc(world, "2", slice="enterprise")], "hires": HIRES, "programs": PROGRAMS}, state.as_of, state.cap.members, "p")  # fmt: skip
    h, i = actions.plan_inputs(state.ground, plan)
    cal = flows.Calendar(state.profile.fiscal_year)
    sizes = lanes_basis.sizes_now(state.ground, state.params.trailing_days, seg)
    scen = actions.Scenario(state.ground)
    plain = lanes._remainder(state, basis, cal, h, i, seg, sizes, scen)[4]
    moved = lanes._remainder(state, basis, cal, h, i, seg, sizes, scen, da.effect_for(state, plan, h, i))[4]  # fmt: skip
    for key, flow in plain.items():
        if key[0] != "enterprise":
            assert moved[key] == flow, key
    assert any(moved[k] != plain[k] for k in plain if k[0] == "enterprise")
    for flow in moved.values():
        assert flow.bookings >= 0 and flow.wins >= 0


def test_owners_follow_their_own_creation_and_add_to_the_segment(world):
    report, doc, _ = build(
        world,
        cyc(world, "0.7", slice="mid_market", start="2026-10"),
        hires=[{"segment": "mid_market", "start": "2026-10", "count": 2}],
    )
    rows = {tuple(r["path"]): r for r in doc["periods"][0]["rows"]}
    owners = [r for p, r in rows.items() if len(p) == 4 and p[1] == "mid_market"]
    assert any(r["kind"] == "planned_hires" for r in owners)
    total = sum(D(r["cells"]["bookings"]["forecast"]) for r in owners)
    assert total == D(rows[("segment", "mid_market")]["cells"]["bookings"]["forecast"])
    won = sum(D(r["cells"]["won"]["forecast"]) for r in owners)
    assert abs(
        won - D(rows[("segment", "mid_market")]["cells"]["won"]["forecast"])
    ) < D("0.0005")
    assert problems(world, report, doc) == []

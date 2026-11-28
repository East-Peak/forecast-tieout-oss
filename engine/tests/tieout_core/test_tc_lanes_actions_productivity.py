"""The swimlane grid with creation-productivity actions: a segment's and an owner's created
deals and created ARR forecasts follow the creation the action leaves, the wins and bookings
with them, programs' deals stay as they were, and no goal or actual moves."""

from datetime import date
from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import lanes_basis
from engine.tieout_core.capacity import project
from engine.tieout_core.report import prepare
from engine.tieout_core.worksheet_drivers import current_value
from engine.tieout_core.worksheet_rules import PRODUCTIVITY

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


def prod(id="p", slice="company", start="2026-09", ramp=0, target=None):
    return {
        "id": id, "name": id, "driver": "productivity", "slice": slice, "start": start,
        "ramp_months": ramp, "target": str(target),
    }  # fmt: skip


def more(world, percent):
    rate = current_value(world[0].ground, PRODUCTIVITY)
    return (rate * (100 + D(percent)) / 100).quantize(D("0.0000001"))


def cell(doc, period, column, *path):
    return row(doc, period, *path)["cells"][column]


def test_a_segments_created_deals_and_created_arr_follow_its_peoples_creation(world):
    _, plain, _ = build(world, hires=HIRES, programs=PROGRAMS)
    report, doc, _ = build(
        world,
        prod(slice="enterprise", target=more(world, 50)),
        hires=HIRES,
        programs=PROGRAMS,
    )
    for column in ("created", "created_arr", "won", "bookings"):
        assert D(cell(doc, FY, column, "segment", "enterprise")["forecast"]) > D(
            cell(plain, FY, column, "segment", "enterprise")["forecast"]
        ), column
    for seg in (
        "mid_market",
        "commercial",
    ):  # the others' creation does not move at all
        for column in ("created", "created_arr", "won"):
            assert cell(doc, FY, column, "segment", seg) == cell(plain, FY, column, "segment", seg)  # fmt: skip
    assert problems(world, report, doc) == []


def test_the_created_deals_are_what_the_peoples_projection_gives_by_hand(world):
    """Enterprise's own people create, from October 1 (day 31 after the as-of date), half again
    as many deals as the fitted rate says: the created forecast in the year is the plain one plus
    half of what they are expected to create from then on, by the capacity term's own projection."""
    state, _ = world
    g = state.ground
    _, plain, _ = build(world)
    _, doc, _ = build(
        world, prod(slice="enterprise", start="2026-10", target=more(world, 50))
    )
    people = [m for m in g.cap.members if m.segment == "enterprise"]
    per_day = project(g.cap.fit, people, g.as_of, g.horizon_days).per_day
    first = (date(2026, 10, 1) - g.as_of).days  # day 31
    last = (state.profile.fiscal_year.end - g.as_of).days
    extra = sum(per_day[first - 1 : last], D(0)) * D("0.5")
    got = D(cell(doc, FY, "created", "segment", "enterprise")["forecast"]) - D(
        cell(plain, FY, "created", "segment", "enterprise")["forecast"]
    )
    assert abs(got - extra) <= D("0.0002"), (
        got,
        extra,
    )  # the cell is written to four places


def test_created_arr_is_the_created_deals_at_the_created_size(world):
    _, plain, _ = build(world)
    _, doc, _ = build(world, prod(target=more(world, 30)))
    new = world[0].ground.model.new_pipeline
    more_deals = D(cell(doc, FY, "created", "total")["forecast"]) - D(cell(plain, FY, "created", "total")["forecast"])  # fmt: skip
    more_arr = D(cell(doc, FY, "created_arr", "total")["forecast"]) - D(cell(plain, FY, "created_arr", "total")["forecast"])  # fmt: skip
    # each cell is written to four places, a hundredth of a deal in the segments' sum
    assert abs(more_arr - more_deals * new.mean_created_arr) <= D("0.0005") * new.mean_created_arr  # fmt: skip


def test_goals_actuals_and_the_basis_digest_never_move(world):
    _, plain, _ = build(world, hires=HIRES)
    report, doc, _ = build(world, prod(target=more(world, 40)), hires=HIRES)
    for period in plain["periods"]:
        mine = next(p for p in doc["periods"] if p["key"] == period["key"])
        for r0, r1 in zip(period["rows"], mine["rows"]):
            for column, c0 in r0["cells"].items():
                assert r1["cells"][column]["actual"] == c0["actual"]
                assert r1["cells"][column]["goal"] == c0["goal"]
    assert doc["plan_basis"] == plain["plan_basis"]
    assert problems(world, report, doc) == []


def test_owners_follow_their_own_creation_and_add_up_to_their_segment_exactly(world):
    """The enterprise lane's people each create more; its planned-hires bucket does too (a hire is
    organic); the programs' bucket is not a person's creation and creates what it did. Every cell
    of owners adds to the segment's, which the lanes contract checks."""
    _, plain, _ = build(world, hires=[{"segment": "enterprise", "start": "2026-10", "count": 1}], programs=PROGRAMS)  # fmt: skip
    report, doc, _ = build(
        world,
        prod(slice="enterprise", target=more(world, 50)),
        hires=[{"segment": "enterprise", "start": "2026-10", "count": 1}],
        programs=PROGRAMS,
    )
    year = {tuple(r["path"]): r for r in doc["periods"][0]["rows"]}
    was = {tuple(r["path"]): r for r in plain["periods"][0]["rows"]}
    mine = {p: r for p, r in year.items() if p[:2] == ("segment", "enterprise") and len(p) == 4}  # fmt: skip
    kinds = {r["kind"] for r in mine.values()}
    assert {"programs", "planned_hires", "owner"} <= kinds
    made = lambda r: D(r["cells"]["created"]["forecast"])
    for path, r1 in mine.items():
        r0 = was[path]
        if r1["kind"] == "programs":
            assert made(r1) == made(r0)  # not a person's creation
        elif r1["kind"] == "planned_hires":
            assert made(r1) > made(r0)  # a hire is organic
    grew = [p for p, r1 in mine.items() if r1["kind"] == "owner" and made(r1) > made(was[p])]  # fmt: skip
    assert grew and all(made(r1) >= made(was[p]) for p, r1 in mine.items())
    assert problems(world, report, doc) == []


def test_a_zero_target_leaves_the_programs_deals_alone_and_no_lane_below_zero(world):
    _, plain, _ = build(world, hires=HIRES, programs=PROGRAMS)
    report, doc, _ = build(world, prod(target="0"), hires=HIRES, programs=PROGRAMS)
    for period in doc["periods"]:
        for r in period["rows"]:
            for column in ("created", "created_arr", "won", "bookings"):
                value = r["cells"][column]["forecast"]
                assert value is None or D(value) >= 0, (period["key"], r["path"], column, value)  # fmt: skip
    # the programs' lanes create what they did in the year; only organic creation is gone
    was = {tuple(r["path"]): r for r in plain["periods"][0]["rows"]}
    for r1 in doc["periods"][0]["rows"]:
        if r1["kind"] == "programs":
            assert r1["cells"]["created"] == was[tuple(r1["path"])]["cells"]["created"]
    assert problems(world, report, doc) == []


def test_a_company_action_is_the_same_action_in_every_segment(world):
    target = more(world, 20)
    _, one, _ = build(world, prod("c", "company", ramp=2, target=target), hires=HIRES)
    _, many, _ = build(world, *(prod(s, s, ramp=2, target=target) for s in SEGMENTS), hires=HIRES)  # fmt: skip
    assert one["periods"] == many["periods"]


def test_a_target_equal_to_the_pooled_rate_changes_no_period_of_the_grid(world):
    _, plain, _ = build(world, hires=HIRES, programs=PROGRAMS)
    _, same, _ = build(world, prod(target=current_value(world[0].ground, PRODUCTIVITY)), hires=HIRES, programs=PROGRAMS)  # fmt: skip
    assert (
        same["periods"] == plain["periods"]
        and same["plan_basis"] == plain["plan_basis"]
    )


def test_the_grid_the_report_the_bridge_and_the_removal_values_agree_with_three_drivers(
    world,
):
    g = world[0].ground
    acts = [
        prod("p", "enterprise", target=more(world, 30)),
        {"id": "s", "name": "s", "driver": "won_arr", "slice": "enterprise", "start": "2026-09",
         "ramp_months": 0, "target": str(g.model.new_pipeline.mean_won_arr * D("1.1"))},
        {"id": "r", "name": "r", "driver": "win_rate", "slice": "enterprise", "start": "2026-09",
         "ramp_months": 0, "target": str(g.model.new_pipeline.win_rate * D("1.2"))},
    ]  # fmt: skip
    report, doc, _ = build(world, *acts, hires=HIRES, programs=PROGRAMS)
    _, bare, _ = build(world, hires=HIRES, programs=PROGRAMS)
    d = report["driver_actions"]
    with_ = D(cell(doc, FY, "bookings", "total")["forecast"])
    without = D(cell(bare, FY, "bookings", "total")["forecast"])
    assert with_ - without == D(d["joint_gain"][REST])
    assert D(cell(doc, Q3, "bookings", "total")["forecast"]) == D(d["with_actions"]["quarters"][2]["expected"])  # fmt: skip
    check = next(c for c in doc["checks"] if c["name"] == "lane action bookings reproduce the report's joint gain")  # fmt: skip
    assert check["passed"] and d["reconciliation"]["material"][REST] is True
    seg = sum(D(cell(doc, FY, "bookings", "segment", s)["forecast"]) for s in SEGMENTS)
    assert seg == with_
    assert problems(world, report, doc) == []


def test_the_win_rate_a_lane_shows_is_weighted_by_the_deals_it_is_expected_to_create(
    world,
):
    """Where a win-rate action and a productivity action share a segment, the period's rate is
    weighted by the creation the productivity action leaves, not the plain one."""
    g = world[0].ground
    p = g.model.new_pipeline.win_rate
    rate_act = {"id": "r", "name": "r", "driver": "win_rate", "slice": "enterprise",
                "start": "2026-10", "ramp_months": 0, "target": "0.40"}  # fmt: skip
    _, a, _ = build(world, rate_act)
    _, b, _ = build(world, rate_act, prod(slice="enterprise", start="2026-10", target=more(world, 100)))  # fmt: skip
    # September has no change in rate and October all of it; twice the deals in October (and
    # none more in September) give October more of the weight, so the period's rate is higher
    ra = D(cell(a, Q3, "win_rate", "segment", "enterprise")["forecast"])
    rb = D(cell(b, Q3, "win_rate", "segment", "enterprise")["forecast"])
    assert p < ra < rb < D("0.40")

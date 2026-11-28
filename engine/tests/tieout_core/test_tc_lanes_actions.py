"""The swimlane grid with win-rate actions: each lane shows the rate it is left with, its wins and
bookings follow, and nothing a plan does not touch moves."""

import copy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import (
    actions,
    contract,
    lanes,
    lanes_basis,
    lanes_contract,
    lanes_files,
)
from engine.tieout_core import driver_actions as da
from engine.tieout_core import lanes_flows as flows
from engine.tieout_core.capacity import project
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import finish, prepare

D = Decimal
COMPANY = "sapling-industries"
REST, NEXT = "rest of fiscal year", "next twelve months"
SEGMENTS = ("enterprise", "mid_market", "commercial")


@pytest.fixture(scope="module")
def world():
    with gen.in_repo():
        state = prepare(gen.PROFILES / COMPANY, gen.DATA / COMPANY, gen.AS_OF, 200, 0)
        basis = lanes_basis.plan_basis(state)
    return state, basis


def act(id="x", slice="company", start="2026-09", ramp=0, target="0.30"):
    return {
        "id": id, "name": id, "driver": "win_rate", "slice": slice, "start": start,
        "ramp_months": ramp, "target": str(target),
    }  # fmt: skip


HIRES = [{"segment": "mid_market", "start": "2026-10", "count": 2}]
PROGRAMS = [{"name": "P", "pipeline": 3_000_000, "start": "2026-10"}]


def build(world, *acts, hires=(), programs=()):
    """(report, lanes document, effect) for a plan of ``acts`` over the given hires and programs."""
    state, basis = world
    doc = {"actions": list(acts), "hires": list(hires), "programs": list(programs)}
    plan = parse_plan(doc, state.as_of, state.cap.members, "plan.yaml")
    with gen.in_repo():
        report = finish(state, plan, "plan.yaml", COMPANY, "x")
    h, i = actions.plan_inputs(state.ground, plan)
    effect = da.effect_for(state, plan, h, i)
    digest = lanes_contract.digest(lanes_basis.document(basis, COMPANY))
    return (
        report,
        lanes.lanes_document(state, basis, report, h, i, COMPANY, "x", digest, effect),
        effect,
    )


def problems(world, report, doc):
    _, basis = world
    return lanes_contract.validate(doc, lanes_basis.document(basis, COMPANY), report)


def row(doc, period, *path):
    p = next(p for p in doc["periods"] if p["key"] == period)
    return next(r for r in p["rows"] if r["path"] == list(path))


def rate(doc, period, *path):
    return D(row(doc, period, *path)["cells"]["win_rate"]["forecast"])


FY, Q1, Q2, Q3, Q4 = "FY26", "Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"


# ---------------------------------------------------------------- the rate each lane shows


def test_with_no_action_every_lane_shows_the_pooled_rate_as_it_always_did(world):
    _, doc, effect = build(world, hires=HIRES)
    assert effect is None
    pooled = world[0].ground.model.new_pipeline.win_rate.quantize(D("0.0001"))
    for p in doc["periods"]:
        for r in p["rows"]:
            if r["kind"] in ("company", "segment"):
                assert D(r["cells"]["win_rate"]["forecast"]) == pooled
    assert all(c["name"] != "lane action bookings reproduce the report's joint gain" for c in doc["checks"])  # fmt: skip


def test_an_action_from_the_first_day_leaves_every_lane_it_touches_at_its_target(world):
    """Starting September 1, the day after the as-of date, and at once: every deal still to be
    created in the year is created at 30%, so each period with deals to create shows it."""
    report, doc, _ = build(world, act(target="0.30"))
    for seg in ("total",):
        for period in (FY, Q3, Q4):
            assert rate(doc, period, seg) == D("0.3000"), period
    for seg in SEGMENTS:
        for period in (FY, Q3, Q4):
            assert rate(doc, period, "segment", seg) == D("0.3000"), (seg, period)
    pooled = D("0.2193")  # the quarters already closed have no pipeline left to create
    for period in (Q1, Q2):
        assert rate(doc, period, "total") == pooled
        assert rate(doc, period, "segment", "enterprise") == pooled
    assert problems(world, report, doc) == []


def test_a_segment_action_changes_only_its_segments_rate_and_the_companys_is_between(
    world,
):
    report, doc, _ = build(world, act(slice="enterprise", target="0.30"))
    assert rate(doc, FY, "segment", "enterprise") == D("0.3000")
    for seg in ("mid_market", "commercial"):
        assert rate(doc, FY, "segment", seg) == D("0.2193")
    assert D("0.2193") < rate(doc, FY, "total") < D("0.3000")
    assert problems(world, report, doc) == []


def test_a_ramp_leaves_a_rate_between_the_pooled_one_and_the_target(world):
    report, doc, _ = build(world, act(slice="mid_market", ramp=3, target="0.30"))
    got = rate(doc, Q3, "segment", "mid_market")
    assert D("0.2193") < got < D("0.3000")
    assert (
        rate(doc, Q4, "segment", "mid_market") > got
    )  # the ramp is done sooner than the year
    assert problems(world, report, doc) == []


def test_a_start_after_a_period_leaves_that_period_with_the_pooled_rate(world):
    _, doc, _ = build(
        world, act(start="2027-01", target="0.30")
    )  # the last month of the year
    assert rate(doc, Q3, "total") == D("0.2193")
    assert D("0.2193") < rate(doc, Q4, "total") < D("0.3000")


def test_the_rate_is_the_creation_weighted_mean_of_the_days_it_applies_to(world):
    """An independent recomputation: Enterprise's rate in the quarter ending October 31, from
    the deals its own people are expected to create each day (the capacity term's projection,
    not the frame) and a ramp counted by hand: October 1 is the first of the 61 days of
    October and November."""
    state, _ = world
    g = state.ground
    _, doc, _ = build(
        world, act(slice="enterprise", start="2026-10", ramp=2, target="0.30")
    )
    people = [m for m in g.cap.members if m.segment == "enterprise"]
    per_day = project(g.cap.fit, people, g.as_of, g.horizon_days).per_day
    start, span = date(2026, 10, 1), 61
    moved = made = D(0)
    for t in range(1, 62):  # September 1 to October 31
        since = (g.as_of + timedelta(days=t) - start).days
        share = D(0) if since < 0 else min(D(1), D(since + 1) / D(span))
        moved += per_day[t - 1] * share
        made += per_day[t - 1]
    pooled = g.model.new_pipeline.win_rate
    want = (pooled + moved / made * (D("0.30") - pooled)).quantize(D("0.0001"))
    assert rate(doc, Q3, "segment", "enterprise") == want


# ---------------------------------------------------------------- wins and bookings follow


def test_a_segments_wins_and_bookings_rise_where_its_rate_does_and_nothing_else_moves(
    world,
):
    _, none_doc, _ = build(world, hires=HIRES, programs=PROGRAMS)
    report, doc, _ = build(
        world, act(slice="enterprise"), hires=HIRES, programs=PROGRAMS
    )
    mine, theirs = row(doc, FY, "segment", "enterprise")["cells"], row(none_doc, FY, "segment", "enterprise")["cells"]  # fmt: skip
    assert D(mine["won"]["forecast"]) > D(theirs["won"]["forecast"])
    assert D(mine["bookings"]["forecast"]) > D(theirs["bookings"]["forecast"])
    for period in none_doc["periods"]:
        for r0, r1 in zip(period["rows"], next(p for p in doc["periods"] if p["key"] == period["key"])["rows"]):  # fmt: skip
            for col, cell0 in r0["cells"].items():
                cell1 = r1["cells"][col]
                assert cell1["actual"] == cell0["actual"], (
                    period["key"],
                    r0["path"],
                    col,
                )
                assert cell1["goal"] == cell0["goal"], (period["key"], r0["path"], col)
                if col in (
                    "created",
                    "created_arr",
                    "open",
                ):  # creation does not change
                    assert cell1["forecast"] == cell0["forecast"], (period["key"], r0["path"], col)  # fmt: skip
    assert doc["plan_basis"] == none_doc["plan_basis"]  # the goals' digest is the same
    assert problems(world, report, doc) == []


def test_other_segments_unrounded_forecasts_do_not_move_to_the_last_digit(world):
    state, basis = world
    seg = ["enterprise", "mid_market", "commercial"]
    h, i = actions.plan_inputs(state.ground, parse_plan({"hires": HIRES, "programs": PROGRAMS}, state.as_of, state.cap.members, "p"))  # fmt: skip
    plan = parse_plan({"actions": [act(slice="enterprise")], "hires": HIRES, "programs": PROGRAMS}, state.as_of, state.cap.members, "p")  # fmt: skip
    effect = da.effect_for(state, plan, h, i)
    cal = flows.Calendar(state.profile.fiscal_year)
    sizes = lanes_basis.sizes_now(state.ground, state.params.trailing_days, seg)
    scen = actions.Scenario(state.ground)
    plain = lanes._remainder(state, basis, cal, h, i, seg, sizes, scen)[4]
    moved = lanes._remainder(state, basis, cal, h, i, seg, sizes, scen, effect)[4]
    for key, flow in plain.items():
        if key[0] != "enterprise":
            assert moved[key] == flow, key  # exact decimals, no rounding anywhere
    assert any(moved[k].wins > plain[k].wins for k in plain if k[0] == "enterprise")


def test_a_company_action_is_the_same_action_in_every_segment_to_the_last_digit(world):
    state, basis = world
    seg = ["enterprise", "mid_market", "commercial"]
    h, i = actions.plan_inputs(state.ground, parse_plan({"hires": HIRES}, state.as_of, state.cap.members, "p"))  # fmt: skip
    cal = flows.Calendar(state.profile.fiscal_year)
    sizes = lanes_basis.sizes_now(state.ground, state.params.trailing_days, seg)
    scen = actions.Scenario(state.ground)

    def priced(*acts):
        plan = parse_plan({"actions": list(acts), "hires": HIRES}, state.as_of, state.cap.members, "p")  # fmt: skip
        return lanes._remainder(
            state, basis, cal, h, i, seg, sizes, scen, da.effect_for(state, plan, h, i)
        )[4]

    once = priced(act("c", "company", ramp=2))
    each = priced(*(act(s, s, ramp=2) for s in seg))
    assert once == each


def test_a_company_action_gives_the_lanes_what_the_same_action_in_each_segment_does(
    world,
):
    _, one, _ = build(world, act("c", "company", ramp=2))
    _, many, _ = build(world, *(act(s, s, ramp=2) for s in SEGMENTS))
    assert one["periods"] == many["periods"]


def test_an_action_that_leaves_the_rate_where_it_was_changes_no_period_of_the_grid(
    world,
):
    _, plain, _ = build(world, hires=HIRES, programs=PROGRAMS)
    pooled = world[0].ground.model.new_pipeline.win_rate
    _, same, _ = build(world, act(target=pooled), hires=HIRES, programs=PROGRAMS)
    assert (
        same["periods"] == plain["periods"]
    )  # byte for byte, row by row, owners included
    assert same["plan_basis"] == plain["plan_basis"]


# ---------------------------------------------------------------- the grid agrees with the report


def test_the_grid_the_report_the_bridge_and_the_removal_values_agree(world):
    report, doc, _ = build(
        world,
        act("e", "enterprise"),
        act("m", "mid_market", ramp=2, target="0.28"),
        hires=HIRES,
        programs=PROGRAMS,
    )
    _, bare, _ = build(world, hires=HIRES, programs=PROGRAMS)
    da_ = report["driver_actions"]
    # the company's year forecast, with the actions and without, differ by the joint gain exactly
    with_ = D(row(doc, FY, "total")["cells"]["bookings"]["forecast"])
    without = D(row(bare, FY, "total")["cells"]["bookings"]["forecast"])
    assert with_ - without == D(da_["joint_gain"][REST])
    assert with_ == D(da_["with_actions"]["expected_fiscal_year"])
    assert without == D(da_["without_actions"]["expected_fiscal_year"])
    # each quarter likewise
    for q in da_["with_actions"]["quarters"]:
        assert D(row(doc, q["quarter"], "total")["cells"]["bookings"]["forecast"]) == D(q["expected"])  # fmt: skip
    # the bridge's step is the same gain, and the lanes' own check says the grid reproduces it
    steps = {s["kind"]: s for s in report["worksheet"]["bridge"]["steps"]}
    assert D(steps["actions"]["change"]) == D(da_["joint_gain"][REST])
    check = next(c for c in doc["checks"] if c["name"] == "lane action bookings reproduce the report's joint gain")  # fmt: skip
    assert check["passed"]
    # segments add to the company in every cell, owners to their segment
    assert problems(world, report, doc) == []
    segments = [
        row(doc, FY, "segment", s)["cells"]["bookings"]["forecast"] for s in SEGMENTS
    ]
    assert sum(D(x) for x in segments) == with_


def test_a_negative_action_is_a_valid_grid_with_a_lower_forecast(world):
    report, doc, _ = build(world, act(slice="enterprise", target="0.15"))
    _, plain, _ = build(world)
    assert D(row(doc, FY, "total")["cells"]["bookings"]["forecast"]) < D(row(plain, FY, "total")["cells"]["bookings"]["forecast"])  # fmt: skip
    assert rate(doc, FY, "segment", "enterprise") == D("0.1500")
    assert problems(world, report, doc) == []


def test_the_files_split_and_join_with_actions_in_the_plan(world):
    report, doc, _ = build(world, act(slice="commercial"), hires=HIRES)
    mine, owners = lanes_files.split(doc)
    assert lanes_files.merge(mine, list(owners.values())) == doc
    assert problems(world, report, doc) == []


# ---------------------------------------------------------------- the contract refuses what is not so


@pytest.fixture(scope="module")
def good(world):
    return build(world, act("e", "enterprise", ramp=1), hires=HIRES, programs=PROGRAMS)[
        :2
    ]


def found(world, good, edit):
    """Every problem either contract finds in ``good`` once ``edit`` has changed it."""
    report, doc = copy.deepcopy(good)
    edit(report, doc)
    return problems(world, report, doc) + contract.validate(report)


def cells(doc, period, *path):
    return row(doc, period, *path)["cells"]


def set_cell(period, column, field, value, *path):
    return lambda r, d: cells(d, period, *path)[column].update({field: value})


EDITS = {
    "a segment's rate above its target": set_cell(FY, "win_rate", "forecast", "0.5000", "segment", "enterprise"),
    "a segment's rate below the pooled one": set_cell(FY, "win_rate", "forecast", "0.0100", "segment", "enterprise"),
    "an untouched segment moved": set_cell(FY, "win_rate", "forecast", "0.2500", "segment", "commercial"),
    "the company's rate above every target": set_cell(Q4, "win_rate", "forecast", "0.9000", "total"),
    "a quarter's forecast bookings": set_cell(Q4, "bookings", "forecast", "1.00", "total"),
    "an action's bookings in a segment": set_cell(FY, "bookings", "forecast", "1.00", "segment", "enterprise"),
    "the report's joint gain": lambda r, d: r["driver_actions"]["joint_gain"].update({REST: "1.00"}),
    "the report's expected year": lambda r, d: r["plan"].update({"expected_fiscal_year": "1.00"}),
    "a failed check": lambda r, d: d["checks"][-1].update({"passed": False}),
}  # fmt: skip


@pytest.mark.parametrize("what", list(EDITS))
def test_a_grid_that_does_not_follow_its_actions_is_refused(world, good, what):
    assert found(world, good, EDITS[what]), what


def test_the_grid_with_actions_is_valid_and_every_check_passes(world, good):
    report, doc = good
    assert problems(world, report, doc) == []
    assert all(c["passed"] for c in doc["checks"])
    names = {c["name"] for c in doc["checks"]}
    assert "segment creation is the creation the actions were valued over" in names
    assert contract.validate(report) == []
    assert any("win-rate action" in c for c in doc["caveats"])

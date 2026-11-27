"""Every number a worksheet serializes, replayed through the whole forward function: the
sensitivity at each historical setting, and every needed-alone setting fed back in as written."""

import copy
import json
from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core.figures import money
from engine.tieout_core.plan import load_plan
from engine.tieout_core.report import prepare
from engine.tieout_core.worksheet_replay import replay


@pytest.fixture(scope="module", params=gen.COMPANIES)
def company(request):
    name = request.param
    with gen.in_repo():
        yield (
            name,
            prepare(
                gen.PROFILES / name, gen.DATA / name, gen.AS_OF, gen.DRAWS, gen.SEED
            ),
        )


def committed(name, scenario):
    path = gen.REPO / gen.REPORTS / name / f"{scenario.id}.json"
    return json.loads(path.read_text())


def plan_of(name, state, scenario):
    if scenario.plan is None:
        return None
    return load_plan(gen.PROFILES / name / scenario.plan, gen.AS_OF, state.cap.members)


@pytest.mark.parametrize("scenario", gen.SCENARIOS, ids=lambda s: s.id)
def test_every_committed_worksheet_replays_exactly(company, scenario):
    name, state = company
    with gen.in_repo():
        report = committed(name, scenario)
        assert replay(state, report, plan_of(name, state, scenario)) == []


@pytest.mark.parametrize("scenario", gen.SCENARIOS, ids=lambda s: s.id)
def test_every_solved_setting_reaches_the_target_when_entered_as_written(
    company, scenario
):
    name, state = company
    report = committed(name, scenario)
    solved = [
        d["needed_alone"]
        for d in report["worksheet"]["drivers"]
        if d["needed_alone"] and d["needed_alone"]["outcome"] == "solves"
    ]
    assert solved
    for n in solved:
        assert Decimal(n["achieved_fiscal_year_bookings"]) >= Decimal(n["target"])
        assert Decimal(n["overshoot"]) >= 0
    assert money(state.ground.fy_target) == solved[0]["target"]


def test_a_tampered_sensitivity_or_solve_is_found_by_the_replay(company):
    name, state = company
    scenario = next(s for s in gen.SCENARIOS if s.id == "demo-plan")
    with gen.in_repo():
        report = committed(name, scenario)
        plan = plan_of(name, state, scenario)
        win = copy.deepcopy(report)
        d = next(x for x in win["worksheet"]["drivers"] if x["driver"] == "win_rate")
        d["historical"]["high"]["change"]["next twelve months"] = "1.00"
        assert replay(state, win, plan)
        solve = copy.deepcopy(report)
        d = next(x for x in solve["worksheet"]["drivers"] if x["driver"] == "won_arr")
        d["needed_alone"]["value"] = money(Decimal(d["needed_alone"]["value"]) - 1)
        assert replay(state, solve, plan)
        wrong_plan = copy.deepcopy(report)
        assert replay(state, wrong_plan, None)  # measured around the wrong scenario

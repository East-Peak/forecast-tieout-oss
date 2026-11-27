"""Goal 3D: ``build_report`` is ``prepare`` (everything the plan does not touch) then
``finish`` (the plan section, the self-checks, the assembly). Finishing a prepared company
with a plan gives the very report the committed files hold, for every company and scenario,
and preparing once serves any number of plans without one changing the next."""

import copy
import json

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core.plan import load_plan
from engine.tieout_core.report import Prepared, finish, prepare

COMPANY_IDS = gen.COMPANIES


@pytest.fixture(scope="module", params=COMPANY_IDS)
def prepared(request):
    company = request.param
    with gen.in_repo():
        state = prepare(
            gen.PROFILES / company, gen.DATA / company, gen.AS_OF, gen.DRAWS, gen.SEED
        )
        yield company, state


def _finish(company, state, scenario):
    plan = None
    plan_file = None
    if scenario.plan is not None:
        plan_file = gen.PROFILES / company / scenario.plan
        plan = load_plan(plan_file, gen.AS_OF, state.cap.members)
    return finish(state, plan, plan_file, company=company, scenario=scenario.id)


@pytest.mark.parametrize("scenario", gen.SCENARIOS, ids=lambda s: s.id)
def test_finish_of_prepare_is_the_committed_report_byte_for_byte(prepared, scenario):
    company, state = prepared
    with gen.in_repo():
        report = _finish(company, state, scenario)
        committed = (
            gen.REPO / gen.REPORTS / company / f"{scenario.id}.json"
        ).read_text()
    assert gen.canonical(report) == committed


def test_the_state_is_a_typed_record_not_a_bag_of_locals(prepared):
    _, state = prepared
    assert isinstance(state, Prepared)
    assert not isinstance(state, dict)


def test_finishing_does_not_change_what_the_next_finish_sees(prepared):
    company, state = prepared
    by_id = {s.id: s for s in gen.SCENARIOS}
    with gen.in_repo():
        first = copy.deepcopy(_finish(company, state, by_id["demo-plan"]))
        _finish(company, state, by_id["hires-only"])
        _finish(company, state, by_id["as-signed"])
        again = _finish(company, state, by_id["demo-plan"])
    assert json.dumps(again, sort_keys=True) == json.dumps(first, sort_keys=True)

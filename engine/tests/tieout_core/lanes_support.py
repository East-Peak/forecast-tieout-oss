"""What the lanes tests share: every demo company prepared once, with its plan basis and the
report and lanes of every scenario."""

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, lanes, lanes_basis, lanes_contract
from engine.tieout_core.plan import load_plan
from engine.tieout_core.report import finish, prepare


def build(company, state, basis, scenario):
    plan = None
    if scenario.plan is not None:
        plan = load_plan(
            gen.PROFILES / company / scenario.plan, gen.AS_OF, state.cap.members
        )
    report = finish(state, plan, scenario.plan, company, scenario.id)
    hires, inflows = actions.plan_inputs(state.ground, plan) if plan else ((), ())
    digest = lanes_contract.digest(lanes_basis.document(basis, company))
    doc = lanes.lanes_document(
        state, basis, report, hires, inflows, company, scenario.id, digest
    )
    return report, doc


@pytest.fixture(scope="session", params=gen.COMPANIES)
def built(request):
    """(company, prepared state, plan basis, {scenario: (report, lanes)}); built inside the repo,
    and handed over outside it so no other test sees the directory change."""
    company = request.param
    with gen.in_repo():
        state = prepare(gen.PROFILES / company, gen.DATA / company, gen.AS_OF, 200, 0)
        basis = lanes_basis.plan_basis(state)
        docs = {s.id: build(company, state, basis, s) for s in gen.SCENARIOS}
    return company, state, basis, docs

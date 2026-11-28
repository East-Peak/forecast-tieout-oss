"""What the lanes tests share: every demo company prepared once, with its plan basis and the
report and lanes of every scenario."""

import csv
import shutil

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import (
    actions,
    driver_actions,
    lanes,
    lanes_basis,
    lanes_contract,
    lanes_records,
    lanes_records_contract,
    lanes_replay,
)
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
        state, basis, report, hires, inflows, company, scenario.id, digest,
        driver_actions.effect_for(state, plan, hires, inflows),
    )  # fmt: skip
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


def mutated(company, tmp_path, scenario="as-signed", deals=None, team=None):
    """The whole path, run on a copy of ``company``'s files after ``deals`` and ``team`` have each
    edited their rows (lists of dicts): prepared, the basis, the report, the lanes, and every
    problem the contract finds in them. Returns (doc, basis document, problems)."""
    here = gen.REPO / gen.DATA / company
    there = tmp_path / company
    shutil.copytree(here, there)
    for name, edit in (("deals.csv", deals), ("team_members.csv", team)):
        if edit is None:
            continue
        with open(there / name, newline="") as fh:
            reader = csv.DictReader(fh)
            columns, rows = reader.fieldnames, list(reader)
        rows = edit(rows) or rows
        with open(there / name, "w", newline="") as fh:
            writer = csv.DictWriter(fh, columns)
            writer.writeheader()
            writer.writerows(rows)
    sc = next(s for s in gen.SCENARIOS if s.id == scenario)
    with gen.in_repo():
        state = prepare(gen.PROFILES / company, there, gen.AS_OF, 200, 0)
        basis = lanes_basis.plan_basis(state)
        report, doc = build(company, state, basis, sc)
    basis_doc = lanes_basis.document(basis, company)
    problems = lanes_contract.validate_basis(basis_doc)
    problems += lanes_contract.validate(doc, basis_doc, report)
    shard = lanes_records.document(state, company)
    problems += lanes_records_contract.validate(shard, doc)
    problems += lanes_replay.records(state, shard)
    return doc, basis_doc, problems

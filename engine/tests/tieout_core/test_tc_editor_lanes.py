"""The swimlane grid for the visitor's own plan: the editor's session computes the lanes of what
was just applied, from the same prepared state and the same Apply revision as the report, and
the goals are the committed ones (applying a plan cannot move them)."""

import copy
import hashlib
import json

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import lanes_basis, lanes_contract, lanes_files, lanes_replay
from engine.tieout_core.editor import YOUR_PLAN, EditorSession
from engine.tieout_core.lanes import unavailable_document
from engine.tieout_core.report import Prepared

EDITED = {
    "hires": [{"segment": "enterprise", "start": "2026-11", "count": 3}],
    "programs": [{"name": "Events", "pipeline": 900000, "start": "2026-12"}],
}


def committed(company, name):
    return (gen.REPO / gen.REPORTS / company / name).read_text()


def run(session, company, plan):
    session.open(company)
    text, meta = session.apply(json.dumps(plan))
    return text, json.loads(meta)


def lanes_of(session, revision):
    return json.loads(session.lanes(revision))


@pytest.fixture(scope="module", params=gen.COMPANIES)
def demo(request):
    """(company, the lanes the editor computes for the company's own demo plan)."""
    company = request.param
    with gen.in_repo():
        session = EditorSession()
        facts = json.loads(session.open(company))
        text, meta = session.apply(json.dumps(facts["demo_plan"]))
        revision = json.loads(meta)["revision"]
        yield company, text, lanes_of(session, revision)


def as_your_plan(doc):
    doc = copy.deepcopy(doc)
    doc["scenario"] = YOUR_PLAN
    if "lanes" in doc:  # an owners file names the lanes file it belongs to
        doc["lanes"] = f"lanes-{YOUR_PLAN}.json"
    return doc


def test_the_demo_plan_through_the_editor_is_the_committed_lanes_of_the_demo_plan(demo):
    company, _, got = demo
    assert got["problems"] == [] and got["stale"] is False
    want = json.loads(committed(company, "lanes-demo-plan.json"))
    assert got["lanes"] == as_your_plan(want)
    owners = got["owners"]
    for segment, doc in owners.items():
        name = lanes_files.name("demo-plan", segment)
        assert doc == as_your_plan(json.loads(committed(company, name)))
    assert sorted(owners) == sorted(
        r["path"][1] for r in want["periods"][0]["rows"] if r["kind"] == "segment"
    )


def test_goals_cannot_move_the_basis_is_the_committed_one_for_every_company(demo):
    company, _, got = demo
    committed_text = committed(company, "lanes-basis.json")
    digest = hashlib.sha256(committed_text.encode()).hexdigest()
    assert got["lanes"]["plan_basis"]["digest"] == digest
    assert got["lanes"]["plan_basis"]["file"] == "lanes-basis.json"
    signed = json.loads(committed(company, "lanes-as-signed.json"))
    assert got["lanes"]["plan_basis"]["digest"] == signed["plan_basis"]["digest"]


def figures(doc, mode):
    """Every cell's ``mode`` figure of a lanes or owners file, by period, row and column."""
    return sorted(
        (p["key"], tuple(r["path"]), c, r["cells"][c][mode])
        for p in doc["periods"]
        for r in p["rows"]
        for c in r["cells"]
    )


def test_an_edit_changes_forecasts_and_no_goal_and_no_actual():
    with gen.in_repo():
        session = EditorSession()
        _, meta = run(session, "sapling-industries", EDITED)
        got = lanes_of(session, meta["revision"])
    signed = json.loads(committed("sapling-industries", "lanes-as-signed.json"))
    assert got["problems"] == []
    for mode in ("goal", "actual"):
        assert figures(got["lanes"], mode) == figures(signed, mode)
    for segment, owners in got["owners"].items():
        name = lanes_files.name("as-signed", segment)
        before = json.loads(committed("sapling-industries", name))
        # the edit adds rows (the planned hires' bucket); every row the signed file has keeps both
        for mode in ("goal", "actual"):
            kept = {k[:3] for k in figures(before, mode)}
            now = [f for f in figures(owners, mode) if f[:3] in kept]
            assert now == figures(before, mode)
    enterprise = got["owners"]["enterprise"]["periods"][0]["rows"]
    assert any(r["path"][-1] == "planned-hires" for r in enterprise)
    year = lambda d: d["periods"][0]["rows"][0]["cells"]["bookings"]["forecast"]
    assert year(got["lanes"]) != year(signed)


def test_the_company_row_is_the_edited_reports_expected_bookings_and_the_contract_holds():
    with gen.in_repo():
        session = EditorSession()
        text, meta = run(session, "sapling-industries", EDITED)
        got = lanes_of(session, meta["revision"])
    report = json.loads(text)
    assert (
        got["lanes"]["periods"][0]["reported_bookings"]
        == (got["lanes"]["periods"][0]["rows"][0]["cells"]["bookings"]["forecast"])
    )
    basis = json.loads(committed("sapling-industries", "lanes-basis.json"))
    assert lanes_contract.validate(got["lanes"], basis, report) == []
    for owners in got["owners"].values():
        assert lanes_contract.validate_owners(owners, got["lanes"], basis, report) == []  # fmt: skip
    assert lanes_contract.validate_owner_set(list(got["owners"].values()), got["lanes"]) == []  # fmt: skip


def test_the_lanes_replay_against_the_deals_and_the_forward_function():
    from engine.tieout_core import actions

    with gen.in_repo():
        session = EditorSession()
        _, meta = run(session, "sapling-industries", EDITED)
        got = lanes_of(session, meta["revision"])
        state: Prepared = session._opened.state
        parsed = session._edited.plan
        hires, inflows = actions.plan_inputs(state.ground, parsed)
        assert lanes_replay.replay(state, got["lanes"], hires, inflows) == []


def test_a_revision_that_is_not_the_latest_is_stale_and_carries_no_lanes():
    with gen.in_repo():
        session = EditorSession()
        _, first = run(session, "sprout-labs", EDITED)
        second = json.loads(session.apply(json.dumps({"hires": [], "programs": []}))[1])
        assert second["revision"] > first["revision"]
        old = lanes_of(session, first["revision"])
        assert old["stale"] is True and "lanes" not in old
        assert lanes_of(session, second["revision"])["stale"] is False


def test_a_revision_of_another_company_is_stale_after_opening_another():
    with gen.in_repo():
        session = EditorSession()
        _, meta = run(session, "sprout-labs", EDITED)
        session.open("sapling-industries")
        assert lanes_of(session, meta["revision"])["stale"] is True
        _, again = run(session, "sapling-industries", EDITED)
        assert again["revision"] > meta["revision"]


def test_a_refused_plan_has_no_revision_to_ask_lanes_of():
    with gen.in_repo():
        session = EditorSession()
        _, meta = run(session, "sprout-labs", {"hires": [{"segment": "x", "start": "2026-11", "count": 0}]})  # fmt: skip
        assert meta["errors"] and meta["revision"] is None
        assert lanes_of(session, 1)["stale"] is True


def test_goals_that_moved_are_refused_not_shown(monkeypatch):
    real = lanes_basis.document

    def moved(basis, company):
        doc = real(basis, company)
        doc["fit"]["win_rate"] = "0.9999"
        return doc

    with gen.in_repo():
        session = EditorSession()
        _, meta = run(session, "sprout-labs", EDITED)
        monkeypatch.setattr(lanes_basis, "document", moved)
        got = lanes_of(session, meta["revision"])
    assert "lanes" not in got and got["stale"] is False
    assert any("committed" in p for p in got["problems"])


def test_a_company_with_no_plan_basis_gets_the_unavailable_document(monkeypatch):
    def none(state):
        raise lanes_basis.BasisUnavailable("no basis for this test")

    with gen.in_repo():
        session = EditorSession()
        _, meta = run(session, "sprout-labs", EDITED)
        monkeypatch.setattr(lanes_basis, "plan_basis", none)
        got = lanes_of(session, meta["revision"])
    assert got["lanes"] == unavailable_document("sprout-labs", YOUR_PLAN, "no basis for this test")  # fmt: skip
    assert got["owners"] == {} and got["problems"] == []


def test_the_editor_reads_the_basis_where_the_generator_writes_it():
    from engine.tieout_core import editor_lanes

    assert editor_lanes.REPORTS == gen.REPORTS


def test_a_crlf_copy_of_the_committed_basis_is_refused_the_check_is_byte_for_byte(
    tmp_path, monkeypatch
):
    from engine.tieout_core import editor_lanes

    with gen.in_repo():
        text = committed("sprout-labs", "lanes-basis.json")
        folder = tmp_path / "reports" / "sprout-labs"
        folder.mkdir(parents=True)
        (folder / "lanes-basis.json").write_bytes(text.replace("\n", "\r\n").encode())
        monkeypatch.setattr(editor_lanes, "REPORTS", tmp_path / "reports")
        session = EditorSession()
        _, meta = run(session, "sprout-labs", EDITED)
        got = lanes_of(session, meta["revision"])
    assert "lanes" not in got
    assert any("committed" in p for p in got["problems"])

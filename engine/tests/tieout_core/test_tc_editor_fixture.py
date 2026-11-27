"""The edited plan the browser tests compare against: a native run of the core, committed under the app's
test fixtures. ``generate_editor_fixture --verify`` fails when the committed files are not what a native run
of that plan writes today."""

import json

import yaml

from engine.scripts import generate_editor_fixture as fixture
from engine.tieout_core import contract


def test_the_committed_expected_files_are_what_a_native_run_writes_today():
    assert fixture.main(["--verify"]) == 0


def test_the_expected_report_is_a_complete_valid_report_for_the_plan_named():
    report = json.loads((fixture.OUT / "report.json").read_text())
    assert contract.validate(report) == []
    assert report["inputs"]["identity"] == {
        "company": fixture.COMPANY,
        "scenario": "your-plan",
    }
    plan = json.loads((fixture.OUT / "plan.json").read_text())
    demo = yaml.safe_load(
        (fixture.REPO / fixture.PROFILES / fixture.COMPANY / "plan.yaml").read_text()
    )
    assert plan != demo, "the fixture is an edit of the demo plan, not the demo plan"


def test_the_editors_own_entry_writes_the_same_report_and_row_as_the_native_run():
    from engine.tieout_core.editor import apply_plan, open_company

    with fixture.in_repo():
        applied = apply_plan(open_company(fixture.COMPANY), fixture.PLAN)
    assert applied.report_text == (fixture.OUT / "report.json").read_text()
    assert applied.comparison == json.loads(
        (fixture.OUT / "comparison-row.json").read_text()
    )

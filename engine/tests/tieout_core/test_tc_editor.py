"""Goal 3D: the entry the browser worker calls. A plan arrives as data, never as a path; the
report comes back as the text the generator would write, with the contract's verdict and the
comparison row against as-signed."""

import copy
import json

import pytest
import yaml

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import contract
from engine.tieout_core.comparison import comparison_rows
from engine.tieout_core.editor import YOUR_PLAN, apply_plan, open_company
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import build_report

COMPANY = "sprout-labs"
EDITED = {
    "hires": [{"segment": "mid_market", "start": "2026-11", "count": 3}],
    "programs": [
        {"name": "Events", "pipeline": 900000, "start": "2026-12", "cost": 120000}
    ],
}


@pytest.fixture(scope="module")
def opened():
    with gen.in_repo():
        yield open_company(COMPANY)


def _demo_doc():
    return yaml.safe_load((gen.REPO / gen.PROFILES / COMPANY / "plan.yaml").read_text())


def test_a_plan_document_is_judged_by_the_same_loader_as_a_plan_file(tmp_path):
    from datetime import date

    doc = {"hires": [{"segment": "x", "start": "2026-10", "count": 0}]}
    with pytest.raises(ValueError, match=r"hires\[1\]: count must be a whole number"):
        parse_plan(doc, date(2026, 8, 31), (), "your plan")


def test_the_demo_plan_entered_as_data_is_the_committed_report_but_for_its_name(opened):
    with gen.in_repo():
        applied = apply_plan(opened, _demo_doc())
        committed = json.loads(
            (gen.REPO / gen.REPORTS / COMPANY / "demo-plan.json").read_text()
        )
    assert applied.errors == [] and applied.problems == []
    committed["inputs"]["identity"]["scenario"] = YOUR_PLAN
    committed["plan"]["file"] = YOUR_PLAN
    assert applied.report_text == gen.canonical(committed)


def test_an_edited_plan_equals_a_native_run_of_the_same_plan(opened, tmp_path):
    plan_file = tmp_path / "your-plan.yaml"
    plan_file.write_text(yaml.safe_dump(EDITED))
    with gen.in_repo():
        applied = apply_plan(opened, copy.deepcopy(EDITED))
        native = build_report(
            gen.PROFILES / COMPANY,
            gen.DATA / COMPANY,
            gen.AS_OF,
            draws=gen.DRAWS,
            seed=gen.SEED,
            plan_path=plan_file,
            company=COMPANY,
            scenario=YOUR_PLAN,
        )
    native["plan"]["file"] = YOUR_PLAN
    assert applied.report_text == gen.canonical(native)
    assert contract.validate(json.loads(applied.report_text)) == []


def test_the_comparison_row_is_the_cores_own_against_as_signed(opened):
    with gen.in_repo():
        applied = apply_plan(opened, copy.deepcopy(EDITED))
    signed = json.loads(
        (gen.REPO / gen.REPORTS / COMPANY / "as-signed.json").read_text()
    )
    yours = json.loads(applied.report_text)
    expected = comparison_rows(
        {"as-signed": signed, YOUR_PLAN: yours}, {YOUR_PLAN: "Your plan"}
    )[1]
    assert applied.comparison == expected
    assert expected["scenario"] == YOUR_PLAN and expected["label"] == "Your plan"


@pytest.mark.parametrize(
    "doc, section, index, text",
    [
        (
            {"hires": [{"segment": "mid_market", "start": "2026-11", "count": 0}]},
            "hires",
            1,
            "count must be a whole number of at least 1",
        ),
        (
            {"programs": [{"name": "a", "pipeline": 0, "start": "2026-11"}]},
            "programs",
            1,
            "pipeline must be more than 0",
        ),
        (
            {"programs": [{"name": "a", "pipeline": 5, "start": "2026-08"}]},
            "programs",
            1,
            "not after the as-of date",
        ),
    ],
)
def test_an_invalid_plan_is_explained_in_the_cores_words_beside_its_item(
    opened, doc, section, index, text
):
    with gen.in_repo():
        applied = apply_plan(opened, doc)
    assert applied.report_text is None and applied.comparison is None
    [error] = applied.errors
    assert (error["section"], error["index"]) == (section, index)
    assert error["position"] == index - 1
    assert text in error["message"]
    assert error["message"].startswith(f"{section}[{index}]")


def test_a_plan_of_the_wrong_shape_is_an_error_not_a_crash(opened):
    with gen.in_repo():
        applied = apply_plan(opened, {"hires": "all of them"})
    assert applied.report_text is None
    assert applied.errors and applied.errors[0]["section"] is None


def test_the_form_facts_come_from_the_core(opened):
    facts = opened.facts
    assert facts["company"] == COMPANY
    assert [s["value"] for s in facts["segments"]] == ["commercial", "mid_market"]
    assert [s["label"] for s in facts["segments"]] == ["Commercial", "Mid Market"]
    assert facts["months"][0] == "2026-09" and len(facts["months"]) == 12
    assert facts["demo_plan"] == _demo_doc()
    targets = yaml.safe_load(
        (gen.REPO / gen.PROFILES / COMPANY / "targets.yaml").read_text()
    )
    assert facts["max_dollars"] == str(10 * targets["annual_target"])


def test_the_session_the_worker_drives_speaks_json_text_both_ways():
    from engine.tieout_core.editor import EditorSession

    with gen.in_repo():
        session = EditorSession()
        facts = json.loads(session.open(COMPANY))
        assert facts["company"] == COMPANY
        report_text, meta_text = session.apply(json.dumps(EDITED))
        bad_text, bad_meta = session.apply(
            json.dumps({"hires": [{"segment": "x", "start": "2026-11", "count": 0}]})
        )
    meta = json.loads(meta_text)
    assert json.loads(report_text)["inputs"]["identity"] == {
        "company": COMPANY,
        "scenario": YOUR_PLAN,
    }
    assert meta["problems"] == [] and meta["errors"] == []
    assert meta["comparison"]["scenario"] == YOUR_PLAN
    assert bad_text == "" and json.loads(bad_meta)["errors"][0]["section"] == "hires"


def test_applying_before_opening_a_company_is_an_error_not_a_crash():
    from engine.tieout_core.editor import EditorSession

    with pytest.raises(RuntimeError, match="open a company first"):
        EditorSession().apply("{}")

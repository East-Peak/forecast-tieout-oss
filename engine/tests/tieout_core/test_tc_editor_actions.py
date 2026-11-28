"""The editor's entry with actions: a plan arrives as data with its actions, is judged by the same
loader, gives the report a native run gives, and its lanes belong to its own Apply."""

import copy
import json

import pytest
import yaml

from engine.scripts import generate_app_reports as gen
from engine.scripts import generate_editor_fixture as fixture
from engine.tieout_core import contract, lanes_basis
from engine.tieout_core import driver_actions as da
from engine.tieout_core.editor import YOUR_PLAN, EditorSession, apply_plan, open_company
from engine.tieout_core.report import build_report

COMPANY = fixture.COMPANY
ACTION = fixture.PLAN_WITH_ACTION["actions"][0]


@pytest.fixture(scope="module")
def opened():
    with gen.in_repo():
        yield open_company(COMPANY)


def plan_with(*actions, **rest):
    return {"hires": [], "programs": [], **rest, "actions": list(actions)}


def action(**over):
    return {**ACTION, **over}


def test_a_plan_with_an_action_entered_as_data_is_a_native_run_of_the_same_plan(
    opened, tmp_path
):
    doc = plan_with(action(), hires=fixture.PLAN["hires"])
    path = tmp_path / "your-plan.yaml"
    path.write_text(yaml.safe_dump(doc))
    with gen.in_repo():
        applied = apply_plan(opened, copy.deepcopy(doc))
        native = build_report(
            gen.PROFILES / COMPANY, gen.DATA / COMPANY, gen.AS_OF, draws=gen.DRAWS,
            seed=gen.SEED, plan_path=path, company=COMPANY, scenario=YOUR_PLAN,
        )  # fmt: skip
    native["plan"]["file"] = YOUR_PLAN
    assert applied.report_text == gen.canonical(native)
    assert contract.validate(json.loads(applied.report_text)) == []
    assert applied.comparison["bookings_change"] == native["plan"]["difference"]


def test_an_action_the_core_refuses_comes_back_beside_its_item(opened):
    cases = [
        (action(slice="strategic"), "'strategic' is not the company or a segment"),
        (
            action(target="1.5"),
            "The target win rate must be between 0% and 100%, not 150%",
        ),
        (
            action(start="2026-08"),
            "Starts in August 2026, which is not after the as-of date",
        ),
        (action(driver="won_arr"), "Only the win rate can be changed by an action"),
    ]
    for bad, why in cases:
        with gen.in_repo():
            applied = apply_plan(
                opened, plan_with(action(id="ok", slice="mid_market"), bad)
            )
        assert applied.report_text is None and applied.problems == []
        (error,) = applied.errors
        assert (error["section"], error["index"], error["position"]) == (
            "actions",
            2,
            1,
        )
        # in a person's words: where it is goes in the structured error, not in the text
        assert why in error["message"] and "actions[" not in error["message"]
        assert not any(
            w in error["message"]
            for w in ("win_rate", "slice", "driver", "ramp_months")
        )


def test_overlapping_actions_are_refused_with_the_item_that_repeats_the_slice(opened):
    with gen.in_repo():
        applied = apply_plan(
            opened, plan_with(action(), action(id="again", target="0.3"))
        )
    (error,) = applied.errors
    assert error["section"] == "actions" and error["position"] == 1
    assert error["message"].startswith("Overlaps 'Enterprise win-rate push'")
    assert "actions[" not in error["message"] and "win_rate" not in error["message"]
    assert error["code"] == "overlap"


@pytest.mark.parametrize(
    "doc", [{"actions": "none"}, {"actions": ["x"]}, {"actions": [[1]]}]
)
def test_actions_that_are_not_a_list_of_mappings_are_refused_as_a_shape(opened, doc):
    with gen.in_repo():
        applied = apply_plan(opened, doc)
    assert applied.report_text is None
    (error,) = applied.errors
    assert error["section"] is None and "actions" in error["message"]


def test_a_company_without_a_plan_basis_refuses_a_plan_with_actions_beside_the_message(
    opened, monkeypatch
):
    def none(_):
        raise lanes_basis.BasisUnavailable("no bookings before the plan start")

    monkeypatch.setattr(lanes_basis, "plan_basis", none)
    opened.state.memo.clear()
    with gen.in_repo():
        applied = apply_plan(opened, plan_with(action()))
    opened.state.memo.clear()
    assert applied.report_text is None and applied.problems == []
    assert "plan basis" in applied.errors[0]["message"]


def test_changing_only_an_actions_target_does_not_build_the_frame_again(
    opened, monkeypatch
):
    calls = []
    real = da.build_frame
    monkeypatch.setattr(
        da, "build_frame", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    opened.state.memo.clear()
    with gen.in_repo():
        first = apply_plan(opened, plan_with(action(target="0.24")))
        second = apply_plan(opened, plan_with(action(target="0.27", ramp_months=0)))
    assert first.report_text != second.report_text
    assert len(calls) == 1


# ----------------------------------------------------------------------- the lanes of an Apply


def apply_and_lanes(session, plan):
    _, meta = session.apply(json.dumps(plan))
    return json.loads(meta)["revision"]


def test_the_grid_of_an_old_apply_is_stale_and_the_new_one_carries_its_own_actions():
    with gen.in_repo():
        session = EditorSession()
        session.open(COMPANY)
        old = apply_and_lanes(session, plan_with(action(target="0.26")))
        new = apply_and_lanes(session, plan_with(action(target="0.30")))
        stale, fresh = json.loads(session.lanes(old)), json.loads(session.lanes(new))
    assert stale["stale"] is True and "lanes" not in stale
    assert fresh["stale"] is False and fresh["problems"] == []
    rate = fresh["lanes"]["periods"][0]["rows"]
    enterprise = next(r for r in rate if r["path"] == ["segment", "enterprise"])
    assert enterprise["cells"]["win_rate"]["forecast"] != "0.2193"
    assert float(enterprise["cells"]["win_rate"]["forecast"]) <= 0.30


def test_the_editors_own_entry_writes_what_a_native_run_writes_for_a_plan_with_an_action(
    opened,
):
    out = fixture.OUT_ACTIONS
    with gen.in_repo():
        session = EditorSession()
        session.open(COMPANY)
        text, meta = session.apply(json.dumps(fixture.PLAN_WITH_ACTION))
        got = json.loads(session.lanes(json.loads(meta)["revision"]))
    assert text == (out / "report.json").read_text()
    assert json.loads(meta)["comparison"] == json.loads(
        (out / "comparison-row.json").read_text()
    )
    assert got["lanes"] == json.loads((out / "lanes.json").read_text())
    for segment in fixture.OWNER_SEGMENTS:
        assert got["owners"][segment] == json.loads(
            (out / f"owners-{segment}.json").read_text()
        )

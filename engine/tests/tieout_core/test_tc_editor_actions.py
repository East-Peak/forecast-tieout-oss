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
        (
            action(driver="mood"),
            "Only the win rate, won ARR per win, creation productivity and cycle length can be changed by an action",
        ),
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


# ----------------------------------------------------------------------- an action on each driver

DRIVERS = fixture.PLAN_WITH_DRIVERS["actions"]


def test_a_plan_with_an_action_on_each_driver_is_a_native_run_of_the_same_plan(
    opened, tmp_path
):
    doc = copy.deepcopy(fixture.PLAN_WITH_DRIVERS)
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
    r = json.loads(applied.report_text)
    assert [i["driver"] for i in r["driver_actions"]["items"]] == ["win_rate", "won_arr", "productivity"]  # fmt: skip
    assert (
        r["driver_actions"]["reconciliation"]["material"]["rest of fiscal year"] is True
    )


def test_the_core_refuses_a_size_and_a_creation_target_in_a_persons_words(opened):
    size, creation = DRIVERS[1], DRIVERS[2]
    cases = [
        (dict(size, target="-5"), "The target won ARR per win must be zero or more dollars, not -$5"),
        (dict(size, target="lots"), "The target won ARR per win must be a number of dollars"),
        (dict(creation, target="-1"), "The target creation productivity must be zero or more deals, not -1"),
        (dict(creation, slice="strategic"), "'strategic' is not the company or a segment"),
    ]  # fmt: skip
    for bad, why in cases:
        with gen.in_repo():
            applied = apply_plan(
                opened, plan_with(action(id="ok", slice="mid_market"), bad)
            )
        (error,) = applied.errors
        assert (error["section"], error["position"]) == ("actions", 1)
        assert why in error["message"] and "actions[" not in error["message"]
        assert not any(
            w in error["message"] for w in ("won_arr", "slice", "driver", "ramp_months")
        )


def test_the_same_driver_twice_on_one_slice_is_refused_but_two_drivers_are_not(opened):
    with gen.in_repo():
        applied = apply_plan(
            opened, plan_with(DRIVERS[1], dict(DRIVERS[1], id="again", target="460000"))
        )
    (error,) = applied.errors
    assert error["code"] == "overlap" and error["position"] == 1
    assert (
        "both change the size of a won deal for the whole company"
        not in error["message"]
    )
    assert "Overlaps 'Company deal size'" in error["message"]
    with gen.in_repo():
        ok = apply_plan(
            opened, plan_with(action(slice="company"), DRIVERS[1], DRIVERS[2])
        )
    assert ok.errors == [] and ok.report_text is not None


def test_changing_only_a_size_or_a_creation_target_does_not_build_the_frame_again(
    opened, monkeypatch
):
    calls = []
    real = da.build_frame
    monkeypatch.setattr(
        da, "build_frame", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    opened.state.memo.clear()
    with gen.in_repo():
        apply_plan(opened, plan_with(DRIVERS[1], DRIVERS[2]))
        apply_plan(
            opened,
            plan_with(
                dict(DRIVERS[1], target="440000"), dict(DRIVERS[2], target="2.7")
            ),
        )
    assert len(calls) == 1


def test_the_grid_of_the_apply_carries_the_created_deals_the_creation_action_leaves():
    with gen.in_repo():
        session = EditorSession()
        session.open(COMPANY)
        plain = apply_and_lanes(session, plan_with(DRIVERS[0]))
        before = json.loads(session.lanes(plain))
        more = apply_and_lanes(session, plan_with(DRIVERS[0], DRIVERS[2]))
        after = json.loads(session.lanes(more))
    assert before["problems"] == [] == after["problems"]
    segment = lambda d: next(
        r
        for r in d["lanes"]["periods"][0]["rows"]
        if r["path"] == ["segment", "mid_market"]
    )
    assert float(segment(after)["cells"]["created"]["forecast"]) > float(segment(before)["cells"]["created"]["forecast"])  # fmt: skip


def test_the_editors_own_entry_writes_what_a_native_run_writes_for_a_plan_with_each_driver():
    out = fixture.OUT_DRIVERS
    with gen.in_repo():
        session = EditorSession()
        session.open(COMPANY)
        text, meta = session.apply(json.dumps(fixture.PLAN_WITH_DRIVERS))
        got = json.loads(session.lanes(json.loads(meta)["revision"]))
    assert text == (out / "report.json").read_text()
    assert json.loads(meta)["comparison"] == json.loads(
        (out / "comparison-row.json").read_text()
    )
    assert got["lanes"] == json.loads((out / "lanes.json").read_text())
    for segment in fixture.DRIVERS_OWNER_SEGMENTS:
        assert got["owners"][segment] == json.loads(
            (out / f"owners-{segment}.json").read_text()
        )


# ----------------------------------------------------------------------- a target no simulation could carry


def test_a_creation_target_above_ten_times_the_pooled_rate_is_refused_beside_its_item_before_any_simulation(
    opened, monkeypatch
):
    from engine.tieout_core import forecast

    def never(*a, **k):
        raise AssertionError("the simulation must not start for a refused plan")

    monkeypatch.setattr(forecast, "simulate", never)
    creation = dict(DRIVERS[2], target="1000000000")
    with gen.in_repo():
        applied = apply_plan(
            opened, plan_with(action(id="ok", slice="mid_market"), creation)
        )
    assert applied.report_text is None and applied.problems == []
    (error,) = applied.errors
    assert (error["section"], error["position"], error["code"]) == (
        "actions",
        1,
        "target",
    )
    assert "more than ten times the pooled creation rate" in error["message"]
    assert "deals per ramped AE-month" in error["message"]
    assert "actions[" not in error["message"] and "productivity" not in error["message"]


def test_ten_times_the_pooled_rate_itself_is_allowed(opened):
    base = opened.signed["worksheet"]["drivers"]
    rate = next(d for d in base if d["driver"] == "productivity")["current"]["value"]
    with gen.in_repo():
        ok = apply_plan(
            opened, plan_with(dict(DRIVERS[2], target=str(float(rate) * 9.99)))
        )
    assert ok.errors == [] and ok.report_text is not None


def test_a_size_target_no_decimal_could_carry_is_refused_beside_its_item_not_crashed(
    opened,
):
    size = dict(DRIVERS[1], target="1e300")
    with gen.in_repo():
        applied = apply_plan(
            opened, plan_with(action(id="ok", slice="mid_market"), size)
        )
    assert applied.report_text is None
    (error,) = applied.errors
    assert (error["section"], error["position"], error["code"]) == (
        "actions",
        1,
        "target",
    )
    assert "more than a thousand times the pooled size" in error["message"]
    with gen.in_repo():
        big = apply_plan(opened, plan_with(dict(DRIVERS[1], target="4000000")))
    assert (
        big.errors == [] and big.report_text is not None
    )  # ten times the mean is allowed


# ----------------------------------------------------------------------- cycle length

CYCLE = {
    "id": "enterprise-cycle", "name": "Enterprise cycle", "driver": "cycle_days",
    "slice": "enterprise", "start": "2026-10", "ramp_months": 1, "target": "130",
}  # fmt: skip


def _baseline_cycle(opened):
    row = next(
        d for d in opened.signed["worksheet"]["drivers"] if d["driver"] == "cycle_days"
    )
    return float(row["current"]["value"])


def test_a_cycle_target_outside_half_to_twice_the_pooled_cycle_is_refused_as_a_guardrail(
    opened, monkeypatch
):
    from engine.tieout_core import forecast

    monkeypatch.setattr(
        forecast,
        "simulate",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("simulated")),
    )
    base = _baseline_cycle(opened)
    for target, word in (
        (base * 0.4, "less than half"),
        (base * 2.5, "more than twice"),
    ):
        with gen.in_repo():
            applied = apply_plan(opened, plan_with(dict(CYCLE, target=str(target))))
        (error,) = applied.errors
        assert (error["section"], error["position"], error["code"]) == (
            "actions",
            0,
            "target",
        )
        assert word in error["message"] and "guardrail" in error["message"]
        assert (
            "actions[" not in error["message"] and "cycle_days" not in error["message"]
        )


def test_the_edges_of_the_guardrail_are_allowed(opened):
    base = _baseline_cycle(opened)
    for target in (base * 0.5001, base * 1.9999):
        with gen.in_repo():
            ok = apply_plan(opened, plan_with(dict(CYCLE, target=str(target))))
        assert ok.errors == [] and ok.report_text is not None


def test_a_plan_with_a_cycle_action_is_a_native_run_and_its_grid_belongs_to_its_own_apply(
    opened, tmp_path
):
    doc = plan_with(CYCLE, hires=fixture.PLAN["hires"])
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
    with gen.in_repo():
        session = EditorSession()
        session.open(COMPANY)
        old = apply_and_lanes(session, plan_with(CYCLE))
        new = apply_and_lanes(
            session, plan_with(dict(CYCLE, target=str(_baseline_cycle(opened) * 0.8)))
        )
        stale, fresh = json.loads(session.lanes(old)), json.loads(session.lanes(new))
    assert stale["stale"] is True and "lanes" not in stale
    assert fresh["stale"] is False and fresh["problems"] == []

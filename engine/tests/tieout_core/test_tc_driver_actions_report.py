"""Win-rate actions in the report, on Sapling's demo data: what they are worth, how each figure is
reached by more than one route, and what the contract refuses."""

import copy
import json
from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import contract, lanes_basis
from engine.tieout_core import driver_actions as da
from engine.tieout_core.forecast import ACTIONS
from engine.tieout_core.markdown import render
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import finish, prepare

D = Decimal
REST, NEXT = "rest of fiscal year", "next twelve months"
COMPANY = "sapling-industries"


@pytest.fixture(scope="module")
def state():
    with gen.in_repo():
        yield prepare(gen.PROFILES / COMPANY, gen.DATA / COMPANY, gen.AS_OF, 400, 0)


def plan_of(state, *actions, hires=(), programs=()):
    doc = {"actions": list(actions), "hires": list(hires), "programs": list(programs)}
    return parse_plan(doc, state.as_of, state.cap.members, "plan.yaml")


def act(
    id="x", slice="company", start="2026-09", ramp=0, target=None, state=None, **kw
):
    out = {
        "id": id, "name": id, "driver": "win_rate", "slice": slice, "start": start,
        "ramp_months": ramp, "target": str(target), **kw,
    }  # fmt: skip
    return out


def points(state, p):
    """The pooled win rate plus ``p`` points, to ten places (an entered target)."""
    return (state.ground.model.new_pipeline.win_rate + D(p) / 100).quantize(D("1e-10"))


def report(state, *actions, **kw):
    with gen.in_repo():
        return finish(state, plan_of(state, *actions, **kw), "plan.yaml", COMPANY, "x")


def figures(r):
    d = r["driver_actions"]
    return {i["id"]: i["removal_value"] for i in d["items"]}, d["joint_gain"]


# ----------------------------------------------------- the outside estimate


@pytest.mark.parametrize(
    "ramp, fiscal_year, twelve",
    [(0, 731_000, 4_770_000), (1, 555_000, 4_480_000), (3, 295_000, 3_910_000)],
)
def test_two_points_from_september_agree_with_the_outside_estimate_within_three_percent(
    state, ramp, fiscal_year, twelve
):
    """+2 points company-wide from September 1 (21.93% to 23.93%), estimated outside this code."""
    r = report(state, act(ramp=ramp, target=points(state, 2)))
    gain = r["driver_actions"]["joint_gain"]
    for got, want in ((gain[REST], fiscal_year), (gain[NEXT], twelve)):
        assert abs(D(got) - want) / want < D("0.03"), (got, want)


# ----------------------------------------------------- nothing, or nothing changed


def test_no_actions_is_an_empty_section_and_the_plan_as_it_was(state):
    with gen.in_repo():
        plain = finish(state, plan_of(state), "plan.yaml", COMPANY, "x")
    assert plain["driver_actions"] == {"items": []}
    assert all(i["kind"] != "actions" for i in plain["plan"]["items"])


def test_a_target_equal_to_the_pooled_rate_changes_no_figure_anywhere(state):
    hold = dict(  # noqa: C408
        hires=[{"segment": "mid_market", "start": "2026-10", "count": 2}],
        programs=[{"name": "P", "pipeline": 3_000_000, "start": "2026-10"}],
    )
    base = report(state, **hold)
    same = report(state, act(target=state.ground.model.new_pipeline.win_rate), **hold)
    for key in ("gap", "forecasts", "actions", "required_pipeline", "history"):
        assert same[key] == base[key], key
    # the plan is the same but for the step that says there is an action, and the words about it
    a, b = copy.deepcopy(base["plan"]), copy.deepcopy(same["plan"])
    step = b["items"].pop()
    assert step["kind"] == "actions"
    assert step["contribution"] == {REST: "0.00", NEXT: "0.00"}
    for doc in (a, b):
        for k in ("order", "cost_note"):
            doc.pop(k)
        doc["ranges"].pop("what_is_drawn")
    assert a == b  # the figures, the quarters, the gaps and the very same draws
    assert same["driver_actions"]["joint_gain"] == {REST: "0.00", NEXT: "0.00"}
    assert same["worksheet"]["drivers"] == base["worksheet"]["drivers"]


# ----------------------------------------------------- values reached two ways


def test_one_action_is_worth_its_joint_gain_and_the_bridge_step_is_that_gain(state):
    r = report(state, act(slice="enterprise", target=points(state, 4)))
    removal, joint = figures(r)
    assert removal["x"] == joint
    assert D(joint[REST]) > 0 < D(joint[NEXT]) and D(joint[NEXT]) > D(joint[REST])
    steps = {s["kind"]: s for s in r["worksheet"]["bridge"]["steps"]}
    assert steps["actions"]["change"] == joint[REST]
    assert r["plan"]["items"][-1]["contribution"] == joint


def test_the_working_plan_is_as_signed_plus_each_step_and_the_actions_step_is_last(
    state,
):
    r = report(
        state,
        act(slice="enterprise", target=points(state, 3)),
        hires=[{"segment": "mid_market", "start": "2026-10", "count": 2}],
        programs=[{"name": "P", "pipeline": 3_000_000, "start": "2026-10"}],
    )
    kinds = [s["kind"] for s in r["worksheet"]["bridge"]["steps"]]
    assert kinds == [
        "as_signed",
        "hires",
        "program",
        "actions",
        "working_plan",
        "remaining_gap",
    ]
    steps = r["worksheet"]["bridge"]["steps"]
    start = D(steps[0]["to"])
    assert start + sum(D(s["change"]) for s in steps[1:4]) == D(steps[4]["to"])
    for h in (REST, NEXT):
        parts = [D(i["contribution"][h]) for i in r["plan"]["items"]]
        assert sum(parts) == D(r["plan"]["difference"][h])


def test_two_actions_in_different_segments_are_worth_what_removing_each_loses_in_all(
    state,
):
    r = report(
        state,
        act("e", "enterprise", target=points(state, 3)),
        act("m", "mid_market", start="2026-10", ramp=2, target=points(state, 2)),
    )
    removal, joint = figures(r)
    rec = r["driver_actions"]["reconciliation"]
    for h in (REST, NEXT):
        assert abs(D(rec["values"][h])) <= D(rec["tolerance"][h])
        assert abs(D(joint[h]) - D(removal["e"][h]) - D(removal["m"][h])) <= D(
            rec["tolerance"][h]
        )
    assert rec["sentences"][REST] == da.NO_INTERACTION


def test_each_action_alone_is_its_own_removal_value_in_a_plan_of_two(state):
    both = report(
        state,
        act("e", "enterprise", target=points(state, 3)),
        act("m", "mid_market", ramp=2, target=points(state, 2)),
    )
    only_e = report(state, act("e", "enterprise", target=points(state, 3)))
    removal, _ = figures(both)
    _, alone = figures(only_e)
    for h in (REST, NEXT):
        assert abs(D(removal["e"][h]) - D(alone[h])) <= D("0.05")


def test_reordering_actions_changes_no_figure(state):
    e = act("e", "enterprise", target=points(state, 3))
    m = act("m", "mid_market", ramp=2, target=points(state, 2))
    a, b = report(state, e, m), report(state, m, e)
    assert figures(a) == figures(b)
    for key in ("with_plan", "difference", "expected_fiscal_year", "ranges", "gap"):
        assert a["plan"][key] == b["plan"][key], key
    assert a["driver_actions"]["with_actions"] == b["driver_actions"]["with_actions"]
    assert (
        a["driver_actions"]["reconciliation"] == b["driver_actions"]["reconciliation"]
    )


def test_the_company_is_every_segment_and_the_same_report_figures_follow(state):
    target = points(state, 2)
    company = report(state, act("c", "company", target=target))
    each = report(
        state,
        *(act(s, s, target=target) for s in ("commercial", "enterprise", "mid_market")),
    )
    assert figures(company)[1] == figures(each)[1]
    assert company["plan"]["with_plan"] == each["plan"]["with_plan"]
    assert company["plan"]["ranges"] == each["plan"]["ranges"]  # the same draws
    removals, joint = figures(each)
    for h in (REST, NEXT):
        assert abs(sum(D(v[h]) for v in removals.values()) - D(joint[h])) <= D("0.2")


def test_a_late_start_is_worth_nothing_in_the_year_and_something_after_it(state):
    r = report(
        state, act(start="2027-02", target=points(state, 3))
    )  # the year ends 2027-01-31
    gain = r["driver_actions"]["joint_gain"]
    assert gain[REST] == "0.00" and D(gain[NEXT]) > 0


def test_an_action_for_a_segment_with_no_creation_adds_no_wins(state):
    plan = plan_of(state, act("e", "enterprise", target=points(state, 3)))
    e = da.effect_for(state, plan, (), ())
    assert any(e.lift)
    quiet = da.Frame(
        e.frame.segments, {s: (D(0),) * 365 for s in e.frame.segments}, e.frame.price
    )
    assert not any(da.effect(quiet, e.baseline, e.as_of, e.actions).lift)


def test_the_rest_of_the_year_figure_and_the_twelve_month_one_come_from_the_same_series(
    state,
):
    r = report(state, act(target=points(state, 2)))
    gain = r["driver_actions"]["joint_gain"]
    assert D(gain[NEXT]) > D(gain[REST]) > 0


# ----------------------------------------------------- ranges


def test_the_range_is_drawn_with_the_action_and_says_once_what_it_leaves_out(state):
    base = report(state)
    r = report(state, act(slice="enterprise", target=points(state, 5)))
    assert D(r["plan"]["ranges"]["bookings_in_window"][NEXT]["median"]) > D(
        base["plan"]["ranges"]["bookings_in_window"][NEXT]["median"]
    )
    assert "driver actions' win rates" in r["plan"]["ranges"]["what_is_drawn"]
    text = json.dumps(r)
    assert text.count("exclude uncertainty about whether an action is achieved") == 1
    checks = {c["name"]: c for c in r["verdicts"]["software_correct"]["checks"]}
    assert checks["plan simulation centered on its expectation"]["passed"]


def test_the_simulation_is_centered_on_the_expectation_with_actions_in_every_segment(
    state,
):
    r = report(state, act(target=points(state, 6)))
    names = {
        c["name"]: c["passed"] for c in r["verdicts"]["software_correct"]["checks"]
    }
    assert names["plan simulation centered on its expectation"] is True
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"


# ----------------------------------------------------- evidence


def test_a_target_above_the_worksheets_high_is_outside_its_historical_settings(state):
    r = report(state, act(target=points(state, 5)))
    e = r["driver_actions"]["items"][0]["evidence"]
    assert (
        e["position"] == "above"
        and e["label"] == "outside the worksheet's historical settings"
    )
    row = r["worksheet"]["drivers"][0]
    assert e["historical_low"] == row["historical"]["low"]["setting"]
    assert e["historical_high"] == row["historical"]["high"]["setting"]
    assert e["baseline_rate"] == row["current"]["value"] == "0.2193"
    assert (
        e["change_points"] == "5.00"
        and e["resulting_rate"] == f"{points(state, 5):.4f}"
    )


@pytest.mark.parametrize("target, position", [("0.15", "below"), ("0.2000", "inside")])
def test_a_target_below_or_between_the_worksheets_settings_is_placed_there(
    state, target, position
):
    e = report(state, act(target=target))["driver_actions"]["items"][0]["evidence"]
    assert e["position"] == position
    assert (e["label"] == da.OUTSIDE) == (position != "inside")
    assert e["label"] != "beyond what this team has done"


def test_a_worksheet_with_no_historical_settings_says_so():
    row = {"historical": None}
    state_less = type(
        "G",
        (),
        {
            "model": type(
                "M", (), {"new_pipeline": type("N", (), {"win_rate": D("0.2")})}
            )
        },
    )
    from datetime import date

    from engine.tieout_core.plan import PlanAction

    a = PlanAction("x", "x", "win_rate", None, date(2026, 9, 1), 0, D("0.3"))
    e = da._evidence(state_less, a, row)
    assert (e["position"], e["label"]) == ("none", da.NOT_OFFERED)
    assert e["historical_low"] is None and e["historical_high"] is None


# ----------------------------------------------------- the contract refuses what is not so


@pytest.fixture(scope="module")
def good(state):
    return report(
        state,
        act("e", "enterprise", target=points(state, 3)),
        act("m", "mid_market", start="2026-10", ramp=2, target=points(state, 2)),
    )


def broken(good, edit):
    r = copy.deepcopy(good)
    edit(r)
    return contract.validate(r)


def test_the_good_report_is_valid_and_all_its_checks_pass(good):
    assert contract.validate(good) == []
    assert good["verdicts"]["software_correct"]["verdict"] == "yes"
    names = {c["name"] for c in good["verdicts"]["software_correct"]["checks"]}
    assert "driver actions' joint gain is the plan's actions step" in names


EDITS = {
    "the joint gain": lambda r: r["driver_actions"]["joint_gain"].update({REST: "1.00"}),
    "a removal value": lambda r: r["driver_actions"]["items"][0]["removal_value"].update({NEXT: "9.99"}),
    "the reconciliation": lambda r: r["driver_actions"]["reconciliation"]["values"].update({REST: "5.00"}),
    "the rounding allowance": lambda r: r["driver_actions"]["reconciliation"]["tolerance"].update({NEXT: "9.00"}),
    "the sentence": lambda r: r["driver_actions"]["reconciliation"]["sentences"].update({REST: da.REINFORCE}),
    "the plan's step": lambda r: r["plan"]["items"][-1]["contribution"].update({REST: "1.00"}),
    "with actions": lambda r: r["driver_actions"]["with_actions"]["bookings"].update({NEXT: "1.00"}),
    "without actions": lambda r: r["driver_actions"]["without_actions"]["bookings"].update({REST: "1.00"}),
    "the year with actions": lambda r: r["driver_actions"]["with_actions"].update({"expected_fiscal_year": "1.00"}),
    "the year without actions": lambda r: r["driver_actions"]["without_actions"].update({"expected_fiscal_year": "1.00"}),
    "a quarter with actions": lambda r: r["driver_actions"]["with_actions"]["quarters"][2].update({"forecast": "1.00"}),
    "a quarter's order": lambda r: r["driver_actions"]["without_actions"]["quarters"].reverse(),
    "the baseline": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"baseline_rate": "0.5000"}),
    "the worksheet's high": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"historical_high": "0.9000"}),
    "the position": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"position": "inside"}),
    "the label": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"label": "beyond what this team has done"}),
    "the change in points": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"change_points": "9.00"}),
    "the resulting rate": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"resulting_rate": "0.9000"}),
    "the sentence on what it affects": lambda r: r["driver_actions"]["items"][0].update({"affects": "It adds 99."}),
    "a target above one": lambda r: r["driver_actions"]["items"][0].update({"target": "1.5000"}),
    "a start in the past": lambda r: r["driver_actions"]["items"][0].update({"start": "2026-08"}),
    "the slice": lambda r: r["driver_actions"]["items"][0]["slice"].update({"key": None}),
    "a repeated id": lambda r: r["driver_actions"]["items"][1].update({"id": "e"}),
    "the definition": lambda r: r["driver_actions"].update({"definition": "Whatever."}),
    "the range note": lambda r: r["driver_actions"].update({"range_note": ""}),
    "an empty section beside a step": lambda r: r.update({"driver_actions": {"items": []}}),
    "a step with no actions": lambda r: r["plan"]["items"].pop(),
    "the removal label": lambda r: r["driver_actions"].update({"removal_label": "Share of the gain"}),
}  # fmt: skip


@pytest.mark.parametrize("what", list(EDITS))
def test_a_report_with_a_wrong_figure_or_sentence_is_refused(good, what):
    assert broken(good, EDITS[what]) != [], what


def test_a_check_that_fails_fails_the_software_correct_verdict(state, monkeypatch):
    """A joint gain the plan does not agree with is found by the section's own check."""
    real = da.Probe.with_lift

    def off(self, lift):
        f = real(self, lift)
        if any(lift):  # the probe, but for a thousand dollars the plan does not have
            comp = f.components[ACTIONS]
            comp["2026-10"] = comp["2026-10"] + D(1000)
        return f

    monkeypatch.setattr(da.Probe, "with_lift", off)
    r = report(state, act(target=points(state, 3)))
    names = {
        c["name"]: c["passed"] for c in r["verdicts"]["software_correct"]["checks"]
    }
    assert r["verdicts"]["software_correct"]["verdict"] == "no"
    assert not all(names[n] for n in names if n.startswith("driver actions"))


# ----------------------------------------------------- markdown


def test_the_markdown_has_a_section_for_actions_only_when_there_are_some(state, good):
    text = render(good)
    assert "## 13. Driver actions" in text and da.REMOVAL_LABEL in text
    assert "outside the worksheet's historical settings" in text
    assert "Driver actions, together" in text
    assert "## 13." not in render(report(state))


# ----------------------------------------------------- what the frame costs, and when it is unavailable


def test_the_frame_is_built_once_for_a_plans_hires_and_programs_whatever_its_actions(
    state, monkeypatch
):
    calls = []
    real = da.build_frame
    monkeypatch.setattr(
        da, "build_frame", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    state.memo.clear()
    report(state, act("a", target=points(state, 1)))
    report(state, act("b", slice="enterprise", ramp=3, target=points(state, 4)))
    assert len(calls) == 1
    report(
        state,
        act("a", target=points(state, 1)),
        hires=[{"segment": "mid_market", "start": "2026-10", "count": 1}],
    )
    assert len(calls) == 2


def test_a_plan_with_actions_is_refused_where_the_plan_basis_is_unavailable(
    state, monkeypatch
):
    def none(_):
        raise lanes_basis.BasisUnavailable("no bookings before the plan start")

    monkeypatch.setattr(lanes_basis, "plan_basis", none)
    state.memo.clear()
    with pytest.raises(da.Unavailable, match="plan basis, which is unavailable"):
        report(state, act(target=points(state, 2)))
    state.memo.clear()

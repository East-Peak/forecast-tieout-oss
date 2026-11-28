"""Win-rate actions in the report, on Sapling's demo data: what they are worth, how each figure is
reached by more than one route, and what the contract refuses."""

import copy
import json
from dataclasses import replace
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
    # no items, but what an action is: the form says it before the first Apply
    assert plain["driver_actions"] == {
        "items": [],
        "definition": da.DEFINITION,
        "line": da.LINE,
    }
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
    # the worksheet's drivers are the same but for what is said of the win rate with an action on it
    for a, b in zip(base["worksheet"]["drivers"], same["worksheet"]["drivers"]):
        if a["driver"] != "win_rate":
            assert a == b
            continue
        assert b["needed_alone"] is None and b["action_limitation"].endswith(
            "not on one line."
        )
        assert a["action_limitation"] is None and b["limitation"] == a["limitation"]
        for key in a:
            if key not in ("needed_alone", "action_limitation"):
                assert a[key] == b[key], key


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
    windows = range(len(state.ground.windows))
    assert any(any(e.lift.priced(i)) for i in windows)
    zeros = {s: (D(0),) * 365 for s in e.frame.segments}
    quiet = replace(e.frame, organic=zeros, program=zeros, series=zeros)
    none = da.effect(quiet, e.baseline, e.as_of, e.actions)
    assert not any(any(none.lift.priced(i)) for i in windows)


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
    "an empty section beside a step": lambda r: r.update({"driver_actions": {"items": [], "definition": da.DEFINITION, "line": da.LINE}}),
    "the plain line": lambda r: r["driver_actions"].update({"line": "Whatever."}),
    "a material flag that is not the figure's": lambda r: r["driver_actions"]["reconciliation"]["material"].update({REST: True}),
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
        if lift:  # the probe, but for a thousand dollars the plan does not have
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
    with pytest.raises(da.Unavailable, match="plan basis is unavailable"):
        report(state, act(target=points(state, 2)))
    state.memo.clear()


# ----------------------------------------------------- each source of creation gets the change once


def test_organic_hire_and_program_creation_each_get_the_change_exactly_once(state):
    """A mid-market action from the first day, at once: the deals its change acts on each day are
    the segment's own people's, its hires' and its share of the programs', each recomputed here
    from the capacity projection and the program's own dollars, and counted once."""
    from engine.tieout_core.capacity import project
    from engine.tieout_core.plan import program_inflows

    g = state.ground
    target = points(state, 4)
    hires = [{"segment": "mid_market", "start": "2026-10", "count": 2}]
    programs = [{"name": "P", "pipeline": 3_000_000, "start": "2026-10"}]
    mm = [m for m in g.cap.members if m.segment == "mid_market"]
    days = g.horizon_days

    def effect_of(**plan):
        p = plan_of(
            state, act("m", "mid_market", start="2026-09", target=target), **plan
        )
        people = tuple(m for i in range(len(p.hires)) for m in p.members_for(i))
        flows = tuple(
            f
            for item in p.programs
            for f in program_inflows(item, g.windows, g.as_of, g.fy_end, 3)
        )
        return da.effect_for(state, p, people, flows), people, flows

    e, _, _ = effect_of()
    want = project(g.cap.fit, mm, g.as_of, days).per_day
    assert list(e.lift.organic["mid_market"]) == list(want)  # the signed roster's, once
    assert not any(e.lift.program["mid_market"])
    assert all(
        c == target - g.model.new_pipeline.win_rate for c in e.changes["mid_market"]
    )

    e, people, _ = effect_of(hires=hires)
    both = project(g.cap.fit, [*mm, *people], g.as_of, days).per_day
    assert list(e.lift.organic["mid_market"]) == list(both)  # and the hires', once
    assert e.lift.organic["mid_market"][200] > want[200]

    e, _, flows = effect_of(programs=programs)
    shares = {s.key: s.creation_share for s in da.basis_of(state).segments}
    per_day = [D(0)] * days
    for f in flows:
        for t in range(f.start, min(f.end, days)):
            per_day[t] += (
                f.dollars / D(f.end - f.start) / g.model.new_pipeline.mean_created_arr
            )
    for t in range(days):  # and the programs' share, once
        assert e.lift.program["mid_market"][t] == shares["mid_market"] * per_day[t]
        assert (
            e.lift.counts("mid_market")[t]
            == want[t] + shares["mid_market"] * per_day[t]
        )


# ----------------------------------------------------- prices frozen by landing month and creation quarter


def probes(state, *acts, **plan):
    """(the forecast with no actions, the forecast with them) for the plan's own hires and programs."""
    from engine.tieout_core.actions import Scenario

    p = plan_of(state, *acts, **plan)
    h, i = actions_inputs(state, p)
    e = da.effect_for(state, p, h, i)
    scen = Scenario(state.ground)
    return scen.forecast(h, i), scen.forecast(h, i, e.lift), scen


def actions_inputs(state, plan):
    from engine.tieout_core import actions

    return actions.plan_inputs(state.ground, plan)


def new_pipeline_bookings(f):
    """Each month's bookings from pipeline not yet created: everything but the open deals'."""
    from engine.tieout_core.forecast import EXISTING

    parts = [c for k, c in f.components.items() if k != EXISTING]
    return {m: sum((c[m] for c in parts), D(0)) for m in f.components[EXISTING]}


@pytest.mark.parametrize("slice", ["company", "enterprise", "mid_market", "commercial"])
@pytest.mark.parametrize(
    "extra",
    [
        {},
        {
            "hires": [{"segment": "mid_market", "start": "2026-10", "count": 3}],
            "programs": [{"name": "P", "pipeline": 4_000_000, "start": "2026-10"}],
        },
    ],
)
def test_a_zero_target_removes_the_wins_it_changes_and_leaves_no_month_below_zero(
    state, slice, extra
):
    plain, zero, _ = probes(state, act(slice=slice, target="0"), **extra)
    before, after = new_pipeline_bookings(plain), new_pipeline_bookings(zero)
    for month in after:
        assert after[month] >= -D("1e-9"), (month, after[month])
        assert after[month] <= before[month] + D("1e-9")
    if slice == "company":
        assert abs(sum(after.values())) < D("1e-9")  # nothing new is won at all
    else:
        assert 0 < sum(after.values()) < sum(before.values())


def test_a_company_action_books_what_changing_the_pooled_probability_directly_books(
    state,
):
    from engine.tieout_core import worksheet_drivers as wd

    g = state.ground
    base = g.model.new_pipeline.win_rate
    plain, acted, scen = probes(state, act(target=base + D("0.02")))
    probe = wd.Probe(g)
    direct = probe.forecast(wd.with_win_rate(g, base + D("0.02")))
    for window in (g.rest_labels, g.twelve_labels):
        gain = scen.exact(acted, window) - scen.exact(plain, window)
        want = scen.exact(direct, window) - scen.exact(plain, window)
        assert abs(gain - want) < D("0.005"), (
            gain,
            want,
        )  # to the cent, windows unrounded
    for month in plain.components["future pipeline"]:  # and month by month
        moved = acted.window_total(month) - plain.window_total(month)
        assert abs(
            moved - (direct.window_total(month) - plain.window_total(month))
        ) < D("0.005")


def test_segments_are_priced_by_their_size_in_every_cell_they_share(state):
    """Enterprise's deals are the largest and commercial's the smallest."""
    e = da.effect_for(state, plan_of(state, act(target=points(state, 2))), (), ())
    price = e.frame.price
    shared = (
        set(price["enterprise"]) & set(price["mid_market"]) & set(price["commercial"])
    )
    assert len(shared) > 20
    for cell in shared:
        assert (
            price["enterprise"][cell]
            > price["mid_market"][cell]
            > price["commercial"][cell]
        )


# ----------------------------------------------------- ranges follow each path, for either kind of company


@pytest.fixture(scope="module")
def flat_state():
    """Mighty Oak: the capacity term is not adopted, so creation is the flat trailing rate."""
    with gen.in_repo():
        yield prepare(
            gen.PROFILES / "mighty-oak-holdings",
            gen.DATA / "mighty-oak-holdings",
            gen.AS_OF,
            4000,
            0,
        )


@pytest.fixture(scope="module")
def adopted_state():
    with gen.in_repo():
        yield prepare(gen.PROFILES / COMPANY, gen.DATA / COMPANY, gen.AS_OF, 4000, 0)


@pytest.mark.parametrize("points_up", ["+3", "-1.5", "zero"])
@pytest.mark.parametrize("which", ["adopted_state", "flat_state"])
def test_the_simulation_is_centered_on_the_expectation_for_a_positive_negative_and_zero_action(
    request, which, points_up
):
    st = request.getfixturevalue(which)
    base = st.ground.model.new_pipeline.win_rate
    target = D(0) if points_up == "zero" else base + D(points_up) / 100
    segment = next(iter(sorted({m.segment for m in st.cap.members})))
    plan = parse_plan(
        {"actions": [act("x", "company", target=target) | {"slice": "company"}]},
        st.as_of, st.cap.members, "plan.yaml",
    )  # fmt: skip
    with gen.in_repo():
        r = finish(st, plan, "plan.yaml", st.profile_dir.name, "x")
    checks = {c["name"]: c for c in r["verdicts"]["software_correct"]["checks"]}
    centered = checks["plan simulation centered on its expectation"]
    assert centered["passed"], centered["detail"]
    assert segment  # the company has segments to share the action over
    one = parse_plan(
        {"actions": [act("y", segment, target=target)]},
        st.as_of,
        st.cap.members,
        "plan.yaml",
    )
    with gen.in_repo():
        r = finish(st, one, "plan.yaml", st.profile_dir.name, "x")
    assert {c["name"]: c for c in r["verdicts"]["software_correct"]["checks"]}[
        "plan simulation centered on its expectation"
    ]["passed"]


# ----------------------------------------------------- the worksheet over a plan with actions


def under(state, *acts, **plan):
    """(the ground, a probe over the plan's own hires and programs and its actions' lift)."""
    from engine.tieout_core import actions
    from engine.tieout_core import worksheet_drivers as wd

    p = plan_of(state, *acts, **plan)
    h, i = actions.plan_inputs(state.ground, p)
    e = da.effect_for(state, p, h, i)
    return state.ground, wd.Probe(state.ground, h, i, e.lift), e


def new_wins(f):
    from engine.tieout_core.forecast import ACTIONS

    return sum(f.components[ACTIONS].values(), D(0))


def test_an_override_over_an_action_holds_each_days_probability_at_one(state):
    """Sapling's pooled rate set to 95% under an action of fifteen points: a probability of 110%
    is held at 100%, so it books what an action of five points does, and what the pooled rate set
    to 100% does when the action starts on the first day."""
    from engine.tieout_core import worksheet_drivers as wd

    base = state.ground.model.new_pipeline.win_rate
    g, big, _ = under(state, act(target=base + D("0.15")))
    _, small, _ = under(state, act(target=base + D("0.05")))
    adjusted = wd.with_win_rate(g, D("0.95"))
    stacked, five = big.forecast(adjusted), small.forecast(adjusted)
    assert stacked.total() == five.total()
    direct = wd.Probe(g).forecast(wd.with_win_rate(g, D(1)))
    for month in direct.components["future pipeline"]:
        assert abs(stacked.window_total(month) - direct.window_total(month)) < D("1e-6")
    change = big.change(stacked)
    assert all(
        D(0) < v < D("1e9") for v in change.values()
    )  # not the $174M of an unbounded 110%


def test_an_override_under_an_action_that_lowers_the_rate_holds_it_at_zero(state):
    from engine.tieout_core import worksheet_drivers as wd

    base = state.ground.model.new_pipeline.win_rate
    g, down, _ = under(state, act(target=base - D("0.15")))
    adjusted = wd.with_win_rate(g, D("0.05"))
    got = down.forecast(adjusted)
    direct = wd.Probe(g).forecast(wd.with_win_rate(g, D(0)))
    for month in direct.components["future pipeline"]:
        assert abs(got.window_total(month) - direct.window_total(month)) < D("1e-6")


def test_an_override_that_does_not_reach_a_bound_adds_its_points_to_the_actions(state):
    from engine.tieout_core import worksheet_drivers as wd

    base = state.ground.model.new_pipeline.win_rate
    g, probe, _ = under(state, act(target=base + D("0.02")))
    got = probe.forecast(wd.with_win_rate(g, base + D("0.03")))
    direct = wd.Probe(g).forecast(wd.with_win_rate(g, base + D("0.05")))
    for month in direct.components["future pipeline"]:
        assert abs(got.window_total(month) - direct.window_total(month)) < D("1e-6")


def test_a_worksheet_over_an_action_solves_nothing_for_the_win_rate_and_says_why(state):
    r = report(state, act(slice="enterprise", target=points(state, 3)))
    row = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "win_rate")
    assert row["needed_alone"] is None
    assert "no setting is solved for" in row["action_limitation"]
    assert row["historical"] is not None  # the changes at its settings are still shown
    others = [d for d in r["worksheet"]["drivers"] if d["driver"] != "win_rate"]
    assert all(d["needed_alone"] is not None for d in others)
    assert contract.validate(r) == []


@pytest.mark.parametrize("mutate", ["needed_alone", "action_limitation"])
def test_the_contract_holds_a_win_rate_with_an_action_to_saying_so(state, mutate):
    r = report(state, act(target=points(state, 3)))
    row = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "win_rate")
    other = next(
        d for d in report(state)["worksheet"]["drivers"] if d["driver"] == "win_rate"
    )
    row[mutate] = other[mutate]  # what a plan with no action says
    assert contract.validate(r) != []


def test_productivity_changes_the_organic_creation_an_action_acts_on_and_not_the_programs(
    state,
):
    """At zero productivity nothing organic is created, so the action has nothing to lift but the
    programs' deals; at twice it, the organic part doubles and the programs' does not."""
    from engine.tieout_core import worksheet_drivers as wd

    base = state.ground.model.new_pipeline.win_rate
    target = base + D("0.03")
    prog = [{"name": "P", "pipeline": 3_000_000, "start": "2026-10"}]
    g, none, _ = under(state, act(target=target))
    at = lambda probe, v: new_wins(probe.forecast(wd.with_productivity(g, v)))
    rate = wd.current_value(g, "productivity")
    assert at(none, D(0)) == 0  # nothing is created, so there is nothing to lift
    assert at(none, rate) == new_wins(none.base) > 0
    assert abs(at(none, 2 * rate) - 2 * at(none, rate)) < D("1e-6")
    g, with_programs, _ = under(state, act(target=target), programs=prog)
    zero, one, two = (at(with_programs, v) for v in (D(0), rate, 2 * rate))
    assert zero > 0  # the programs' deals are still created
    assert abs((two - zero) - 2 * (one - zero)) < D(
        "1e-6"
    )  # and only the organic part scales


# ------------------------------------------------ what a person reads: dates, the plain line, the reconciliation


def test_the_empty_section_says_what_an_action_is_in_the_sentence_the_form_shows(state):
    with gen.in_repo():
        plain = finish(state, plan_of(state), "plan.yaml", COMPANY, "x")
    line = plain["driver_actions"]["line"]
    assert "pipeline created from its start month on" in line
    assert "Deals already open keep their odds" in line
    assert "entered change on the pooled baseline, not a measured segment rate" in line
    assert contract.validate(plain) == []
    wrong = copy.deepcopy(plain)
    wrong["driver_actions"]["line"] = "An action does something."
    assert contract.validate(wrong) != []


def test_a_month_is_written_as_the_app_writes_it_in_the_sentence_on_what_an_action_affects(
    state,
):
    r = report(
        state, act("e", "enterprise", start="2026-10", ramp=2, target=points(state, 3))
    )
    text = r["driver_actions"]["items"][0]["affects"]
    assert text.startswith(
        "Pipeline created from October 2026 in Enterprise, ramping up over 2 months"
    )
    assert "2026-10" not in text


def test_the_reconciliation_says_per_window_whether_it_is_material_and_the_rule_is_one(
    state,
):
    """Material: it does not round to zero in whole dollars, the finest figure the screen writes."""
    r = report(
        state,
        act("e", "enterprise", target=points(state, 3)),
        act("m", "mid_market", ramp=2, target=points(state, 2)),
    )
    rec = r["driver_actions"]["reconciliation"]
    for w in (REST, NEXT):
        assert rec["material"][w] == (abs(D(rec["values"][w])) >= da.MATERIAL_FROM)
    assert da.MATERIAL_FROM == D("0.5")
    assert (
        da.is_material(D("0.49")) is False
        and da.is_material(D("-0.5")) is True
        and da.is_material(D("0")) is False
    )

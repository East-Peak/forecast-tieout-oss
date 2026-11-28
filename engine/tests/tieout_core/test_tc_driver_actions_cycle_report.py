"""Cycle-length actions in the report, on Sapling's demo data (the capacity term in use) and Mighty
Oak's (a flat creation rate): what they are worth, what they leave alone, how they sit with the other
three drivers, and what the contract refuses."""

import copy
import itertools
from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, contract
from engine.tieout_core import driver_actions as da
from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core.markdown import render
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import finish, prepare
from engine.tieout_core.worksheet_rules import CYCLE_DAYS

D = Decimal
REST, NEXT = "rest of fiscal year", "next twelve months"
COMPANY = "sapling-industries"
HIRES = [{"segment": "mid_market", "start": "2026-10", "count": 2}]
PROGRAMS = [{"name": "P", "pipeline": 3_000_000, "start": "2026-10"}]


@pytest.fixture(scope="module")
def state():
    with gen.in_repo():
        yield prepare(gen.PROFILES / COMPANY, gen.DATA / COMPANY, gen.AS_OF, 400, 0)


def plan_of(state, *acts, hires=(), programs=()):
    doc = {"actions": list(acts), "hires": list(hires), "programs": list(programs)}
    return parse_plan(doc, state.as_of, state.cap.members, "plan.yaml")


def act(
    id="x", slice="company", start="2026-09", ramp=0, target=None, driver="cycle_days"
):
    return {
        "id": id, "name": id, "driver": driver, "slice": slice, "start": start,
        "ramp_months": ramp, "target": str(target),
    }  # fmt: skip


def report(state, *acts, **kw):
    with gen.in_repo():
        return finish(state, plan_of(state, *acts, **kw), "plan.yaml", COMPANY, "x")


def base(state):
    return wd.current_value(state.ground, CYCLE_DAYS)


def days(state, percent):
    """The pooled cycle and ``percent`` more of it, as an entered target in days."""
    return (base(state) * (100 + D(percent)) / 100).quantize(D("0.0001"))


def drivers_row(r, name):
    return next(d for d in r["worksheet"]["drivers"] if d["driver"] == name)


# ----------------------------------------------------- nothing, or nothing changed


def test_a_target_equal_to_the_unrounded_baseline_changes_no_figure_anywhere(state):
    hold = {"hires": HIRES, "programs": PROGRAMS}
    plain = report(state, **hold)
    same = report(state, act(target=base(state)), **hold)
    for key in ("gap", "forecasts", "actions", "required_pipeline", "history"):
        assert same[key] == plain[key], key
    a, b = copy.deepcopy(plain["plan"]), copy.deepcopy(same["plan"])
    step = b["items"].pop()
    assert step["kind"] == "actions" and step["contribution"] == {
        REST: "0.00",
        NEXT: "0.00",
    }
    for doc in (a, b):
        for k in ("order", "cost_note"):
            doc.pop(k)
        doc["ranges"].pop("what_is_drawn")
    assert a == b  # the figures, the quarters, the gaps and the very same draws
    assert same["driver_actions"]["joint_gain"] == {REST: "0.00", NEXT: "0.00"}


def test_a_start_after_the_year_gains_nothing_in_it_and_pipeline_before_the_start_does_not_move(
    state,
):
    r = report(state, act(start="2027-02", target=days(state, -20)))
    assert r["driver_actions"]["joint_gain"][REST] == "0.00"
    assert D(r["driver_actions"]["joint_gain"][NEXT]) != 0


# ----------------------------------------------------- what it is worth


def test_a_shorter_cycle_brings_bookings_forward_and_a_longer_one_pushes_them_out(
    state,
):
    shorter = report(state, act(target=days(state, -15)))["driver_actions"][
        "joint_gain"
    ]
    longer = report(state, act(target=days(state, 15)))["driver_actions"]["joint_gain"]
    assert D(shorter[REST]) > 0 > D(longer[REST])
    assert D(shorter[NEXT]) > 0 > D(longer[NEXT])


def test_one_action_is_worth_its_joint_gain_the_bridge_step_is_that_gain_and_the_evidence_is_a_timing_assumption(
    state,
):
    r = report(state, act(slice="enterprise", target=days(state, -20)))
    d = r["driver_actions"]
    (item,) = d["items"]
    assert item["removal_value"] == d["joint_gain"]
    steps = {s["kind"]: s for s in r["worksheet"]["bridge"]["steps"]}
    assert steps["actions"]["change"] == d["joint_gain"][REST]
    e, row = item["evidence"], drivers_row(r, "cycle_days")
    assert e["baseline"] == row["current"]["value"] and e["change_percent"] == "-20.00"
    assert (e["historical_low"], e["historical_high"]) == (
        row["historical"]["low"]["setting"], row["historical"]["high"]["setting"],
    )  # fmt: skip
    assert (
        "when wins land" in d["definition"] and "lifetime bookings" in d["definition"]
    )
    assert (
        "timing assumption" in item["affects"]
        and "none more or fewer" in item["affects"]
    )
    assert "guardrail" in d["definition"]
    assert contract.validate(r) == []


def test_the_company_is_every_segment_and_the_same_report_figures_follow(state):
    target = days(state, -10)
    company = report(state, act("c", target=target))
    each = report(
        state,
        *(act(s, s, target=target) for s in ("commercial", "enterprise", "mid_market")),
    )
    assert (
        company["driver_actions"]["joint_gain"] == each["driver_actions"]["joint_gain"]
    )
    assert company["plan"]["with_plan"] == each["plan"]["with_plan"]
    assert company["plan"]["ranges"] == each["plan"]["ranges"]


def test_a_segment_leaves_every_other_segments_figures_exactly_as_they_were(state):
    plan = plan_of(state, act(slice="enterprise", target=days(state, -20)))
    e = da.effect_for(state, plan, (), ())
    assert any(e.lift.cycle_units("enterprise"))
    assert not any(e.lift.cycle_units("mid_market")) and not any(
        e.lift.cycle_units("commercial")
    )


def test_for_fixed_cohorts_the_dollars_are_the_same_with_the_tail_counted(state):
    for percent in (-30, 25, 90):
        plan = plan_of(
            state, act(target=days(state, percent)), hires=HIRES, programs=PROGRAMS
        )
        h, i = actions.plan_inputs(state.ground, plan)
        e = da.effect_for(state, plan, h, i)
        total = sum((sum(e.lift.cycle_units(s)) for s in e.frame.segments), D(0))
        assert abs(total) < D("1e-15"), (percent, total)


# ----------------------------------------------------- with the other three drivers


def four(state, **over):
    g = state.ground
    wr, sz, pr = (
        g.model.new_pipeline.win_rate * D("1.15"),
        g.model.new_pipeline.mean_won_arr * D("1.1"),
        wd.current_value(g, "productivity") * D("1.2"),
    )
    return [
        act("w", "enterprise", target=wr, driver="win_rate", **over),
        act("s", "company", target=sz, driver="won_arr", **over),
        act("p", "mid_market", target=pr, driver="productivity", **over),
        act("c", "company", target=days(state, -15), **over),
    ]


def test_every_listing_order_of_four_actions_is_one_plan_at_the_lift(state):
    plan = plan_of(state, *four(state))
    base_lift = da.effect_for(state, plan, (), ()).lift
    for perm in itertools.permutations(four(state)):
        other = da.effect_for(state, plan_of(state, *perm), (), ()).lift
        assert other == base_lift
        assert [other.moved(i) for i in range(13)] == [
            base_lift.moved(i) for i in range(13)
        ]


def test_reordering_four_actions_changes_no_figure_of_the_report(state):
    acts = four(state)
    one, two = report(state, *acts), report(state, *reversed(acts))
    for key in ("with_plan", "difference", "expected_fiscal_year", "ranges", "gap"):
        assert one["plan"][key] == two["plan"][key], key
    a, b = one["driver_actions"], two["driver_actions"]
    assert (
        a["joint_gain"] == b["joint_gain"]
        and a["reconciliation"] == b["reconciliation"]
    )
    removals = lambda r: {
        i["id"]: i["removal_value"] for i in r["driver_actions"]["items"]
    }
    assert removals(one) == removals(two)


def test_four_drivers_reconcile_the_line_is_neutral_about_timing_and_the_report_is_valid(
    state,
):
    r = report(state, *four(state), hires=HIRES, programs=PROGRAMS)
    d = r["driver_actions"]
    removals = {i["id"]: i["removal_value"] for i in d["items"]}
    for w in (REST, NEXT):
        want = D(d["joint_gain"][w]) - sum(D(v[w]) for v in removals.values())
        assert D(d["reconciliation"]["values"][w]) == want
    assert d["reconciliation"]["material"][REST] is True
    sentence = d["reconciliation"]["sentences"][REST]
    assert sentence == da.TIMING_INTERACTION
    assert "reinforce" not in sentence and "overlap" not in sentence
    assert contract.validate(r) == []
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"
    assert "Cycle length" in render(r) or "cycle" in render(r).lower()


# ----------------------------------------------------- the worksheet


def test_the_cycle_row_is_not_solved_for_while_the_plan_has_a_cycle_action_and_says_so(
    state,
):
    plain = drivers_row(report(state), "cycle_days")
    r = report(state, act(target=days(state, -10)))
    row = drivers_row(r, "cycle_days")
    assert plain["needed_alone"] is not None and row["needed_alone"] is None
    assert "no setting is solved for" in row["limitation"]
    for other in ("win_rate", "won_arr", "productivity"):
        assert drivers_row(r, other)["needed_alone"] is not None or drivers_row(r, other)["current"]["value"] is None  # fmt: skip
    assert contract.validate(r) == []


# ----------------------------------------------------- bounds


@pytest.mark.parametrize("percent", [-60, 150])
def test_a_target_below_half_or_above_twice_the_pooled_cycle_is_refused_in_words_before_any_simulation(
    state, percent, monkeypatch
):
    from engine.tieout_core import forecast

    monkeypatch.setattr(
        forecast,
        "simulate",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("simulated")),
    )
    with pytest.raises(da.ActionRefused) as why:
        report(state, act(target=days(state, percent)))
    assert why.value.code == "target" and "guardrail" in str(why.value)


def test_a_company_with_no_recorded_win_times_cannot_have_a_cycle_action(
    state, monkeypatch
):
    monkeypatch.setattr(
        wd, "current_value", lambda g, driver: None if driver == CYCLE_DAYS else D(1)
    )
    with pytest.raises(da.ActionRefused, match="no recorded win times"):
        da.refuse_unbounded(state.ground, plan_of(state, act(target=100)))

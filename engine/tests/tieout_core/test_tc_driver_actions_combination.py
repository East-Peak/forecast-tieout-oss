"""Actions on different drivers in overlapping slices: the changes multiply through each win, so
the reconciliation line (the joint gain less the sum of the removal values) is not zero, and it
is what the algebra says it is.

With no program pipeline and every action company-wide from the first day, the plan's new
bookings are the future-pipeline component ``F`` of the plan without actions. A win-rate change
of ``a``, a size change of ``b`` and a creation change of ``c`` (each a fraction of the baseline)
gain ``F * ((1+a)(1+b)(1+c) - 1)`` together, and removing one loses what it adds to the other
two, ``F * a(1+b)(1+c)`` and so on; the line is the first less the sum of the others."""

from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, contract
from engine.tieout_core import driver_actions as da
from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import finish, prepare
from engine.tieout_core.worksheet_rules import PRODUCTIVITY

D = Decimal
REST, NEXT = "rest of fiscal year", "next twelve months"
COMPANY = "sapling-industries"
HIRES = [{"segment": "mid_market", "start": "2026-10", "count": 2}]


@pytest.fixture(scope="module")
def state():
    with gen.in_repo():
        yield prepare(gen.PROFILES / COMPANY, gen.DATA / COMPANY, gen.AS_OF, 400, 0)


def base_of(state, driver):
    g = state.ground
    return {
        "win_rate": g.model.new_pipeline.win_rate,
        "won_arr": g.model.new_pipeline.mean_won_arr,
        "productivity": wd.current_value(g, PRODUCTIVITY),
    }[driver]


def act(state, driver, change, slice="company", start="2026-09", ramp=0, id=None):
    """An action that changes ``driver`` by the fraction ``change`` of its baseline."""
    return {
        "id": id or driver, "name": id or driver, "driver": driver, "slice": slice,
        "start": start, "ramp_months": ramp,
        "target": str(base_of(state, driver) * (1 + D(change))),
    }  # fmt: skip


def report(state, *acts, hires=()):
    doc = {"actions": list(acts), "hires": list(hires)}
    plan = parse_plan(doc, state.as_of, state.cap.members, "plan.yaml")
    with gen.in_repo():
        return finish(state, plan, "plan.yaml", COMPANY, "x")


def future(state, w, hires=()):
    """What the plan without actions books from the deals its own people create after the as-of
    date, in window ``w``: the base the changes multiply."""
    plan = parse_plan(
        {"hires": list(hires)}, state.as_of, state.cap.members, "plan.yaml"
    )
    h, i = actions.plan_inputs(state.ground, plan)
    probe = wd.Probe(state.ground, h, i)
    months = {REST: state.ground.rest_labels, NEXT: state.ground.twelve_labels}[w]
    return sum((probe.base.components["future pipeline"][m] for m in months), D(0))


def removal(r):
    return {i["id"]: i["removal_value"] for i in r["driver_actions"]["items"]}


@pytest.mark.parametrize("hires", [(), HIRES])
def test_three_drivers_company_wide_reconcile_to_the_algebra_to_the_cent(state, hires):
    a, b, c = D("0.10"), D("0.10"), D("0.10")
    r = report(
        state,
        act(state, "win_rate", a),
        act(state, "won_arr", b),
        act(state, "productivity", c),
        hires=hires,
    )
    d = r["driver_actions"]
    for w in (REST, NEXT):
        f = future(state, w, hires)
        joint = f * ((1 + a) * (1 + b) * (1 + c) - 1)
        parts = {
            "win_rate": f * a * (1 + b) * (1 + c),
            "won_arr": f * b * (1 + a) * (1 + c),
            "productivity": f * c * (1 + a) * (1 + b),
        }
        assert abs(D(d["joint_gain"][w]) - joint) <= D("0.05"), w
        for k, v in parts.items():
            assert abs(D(removal(r)[k][w]) - v) <= D("0.05"), (w, k)
        line = joint - sum(parts.values())  # -0.032 of F
        assert abs(D(d["reconciliation"]["values"][w]) - line) <= D("0.10"), w
        assert d["reconciliation"]["material"][w] is True
    assert d["reconciliation"]["sentences"][REST] == da.REINFORCE
    assert contract.validate(r) == []


def test_two_actions_that_take_bookings_away_cover_part_of_each_other(state):
    """Win rate down a tenth and size down a tenth: the actions together lose 0.19 of F, removing
    each one adds back 0.09 (not the 0.10 each took alone), so the others cover part of each."""
    r = report(
        state, act(state, "win_rate", D("-0.10")), act(state, "won_arr", D("-0.10"))
    )
    d = r["driver_actions"]
    f = future(state, REST)
    assert abs(D(d["joint_gain"][REST]) + D("0.19") * f) <= D("0.05")
    assert abs(D(d["reconciliation"]["values"][REST]) + D("0.01") * f) <= D("0.05")
    assert d["reconciliation"]["sentences"][REST] == da.OVERLAP
    assert d["reconciliation"]["material"][REST] is True
    assert contract.validate(r) == []


def test_one_that_adds_and_one_that_takes_away_are_read_by_size(state):
    """Win rate up a fifth, size down a tenth: 1.2 * 0.9 - 1 = +0.08 together; removing the rate
    loses 0.1 * 1.2 - ... the line is -0.2 * -0.1 = +0.02 of F, and the sizes of the parts add to less."""
    r = report(
        state, act(state, "win_rate", D("0.20")), act(state, "won_arr", D("-0.10"))
    )
    d = r["driver_actions"]
    f = future(state, REST)
    assert abs(D(d["joint_gain"][REST]) - D("0.08") * f) <= D("0.05")
    assert abs(D(d["reconciliation"]["values"][REST]) - D("0.02") * f) <= D("0.05")
    assert d["reconciliation"]["sentences"][REST] == da.OVERLAP


def test_actions_that_do_not_share_a_driver_or_a_slice_do_not_interact(state):
    r = report(
        state,
        act(state, "win_rate", D("0.20"), slice="enterprise"),
        act(state, "won_arr", D("0.10"), slice="mid_market"),
        act(state, "productivity", D("0.30"), slice="commercial"),
    )
    d = r["driver_actions"]
    rec = d["reconciliation"]
    for w in (REST, NEXT):
        assert abs(D(rec["values"][w])) <= D(rec["tolerance"][w])
        assert rec["material"][w] is False
    assert rec["sentences"][REST] == da.NO_INTERACTION
    assert contract.validate(r) == []


def test_the_joint_gain_is_the_direct_forecast_difference_to_the_cent(state):
    from engine.tieout_core.worksheet_rules import WIN_RATE, WON_ARR

    g = state.ground
    r = report(
        state,
        act(state, "win_rate", D("0.10")),
        act(state, "won_arr", D("0.10")),
        act(state, "productivity", D("0.10")),
    )
    plan = parse_plan({}, state.as_of, state.cap.members, "plan.yaml")
    h, i = actions.plan_inputs(g, plan)
    probe = wd.Probe(g, h, i)
    direct = wd.with_setting(g, WIN_RATE, base_of(state, "win_rate") * D("1.1"))
    direct = wd.with_setting(direct, WON_ARR, base_of(state, "won_arr") * D("1.1"))
    direct = wd.with_setting(
        direct, PRODUCTIVITY, base_of(state, "productivity") * D("1.1")
    )
    flex = probe.change(probe.forecast(direct))
    for w in (REST, NEXT):
        assert D(r["driver_actions"]["joint_gain"][w]) == D(flex[w]), w


def test_every_listing_order_of_three_actions_is_one_report(state):
    import itertools

    acts = [
        act(state, "win_rate", D("0.15"), slice="enterprise"),
        act(state, "won_arr", D("0.08"), start="2026-10", ramp=2),
        act(state, "productivity", D("0.25"), slice="mid_market", start="2026-11"),
    ]
    reports = [report(state, *p) for p in itertools.permutations(acts)]
    first = reports[0]
    for other in reports[1:]:
        assert (
            other["driver_actions"]["joint_gain"]
            == first["driver_actions"]["joint_gain"]
        )
        assert (
            other["driver_actions"]["reconciliation"]
            == first["driver_actions"]["reconciliation"]
        )
        assert removal(other) == removal(first)
        assert other["plan"]["with_plan"] == first["plan"]["with_plan"]
        assert other["plan"]["ranges"] == first["plan"]["ranges"]


def test_the_report_the_bridge_and_the_removal_values_agree_after_rounding(state):
    r = report(
        state,
        act(state, "win_rate", D("0.10")),
        act(state, "won_arr", D("0.10")),
        act(state, "productivity", D("0.10")),
        hires=HIRES,
    )
    d = r["driver_actions"]
    steps = {s["kind"]: s for s in r["worksheet"]["bridge"]["steps"]}
    assert steps["actions"]["change"] == d["joint_gain"][REST]
    assert r["plan"]["items"][-1]["contribution"] == d["joint_gain"]
    for w in (REST, NEXT):
        want = D(d["joint_gain"][w]) - sum(D(v[w]) for v in removal(r).values())
        assert D(d["reconciliation"]["values"][w]) == want
        assert D(d["with_actions"]["bookings"][w]) - D(d["without_actions"]["bookings"][w]) == D(d["joint_gain"][w])  # fmt: skip
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"
    names = {c["name"] for c in r["verdicts"]["software_correct"]["checks"]}
    assert "driver actions on different drivers interact: the reconciliation is the joint gain less the removal values" in names  # fmt: skip


def test_the_sentence_reads_by_size_not_by_sign():
    joint, ten = D(100), D(10)
    assert da.reconciliation_sentence(joint, D("95"), ten) == da.NO_INTERACTION
    assert da.reconciliation_sentence(joint, D(130), ten) == da.REINFORCE
    assert da.reconciliation_sentence(joint, D(70), ten) == da.OVERLAP
    assert da.reconciliation_sentence(-joint, D(-130), ten) == da.REINFORCE
    assert da.reconciliation_sentence(-joint, D(-70), ten) == da.OVERLAP
    assert "gain" not in da.REINFORCE and "loses" not in da.OVERLAP

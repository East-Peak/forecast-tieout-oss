"""Won-ARR actions in the report, on Sapling's demo data: what they are worth, the figure the
worksheet's own flex gives for the same change, and what the contract refuses."""

import copy
from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, contract
from engine.tieout_core import driver_actions as da
from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core.markdown import render
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import finish, prepare
from engine.tieout_core.worksheet_rules import WON_ARR

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
    id="x", slice="company", start="2026-09", ramp=0, target=None, driver="won_arr"
):
    return {
        "id": id, "name": id, "driver": driver, "slice": slice, "start": start,
        "ramp_months": ramp, "target": str(target),
    }  # fmt: skip


def report(state, *acts, **kw):
    with gen.in_repo():
        return finish(state, plan_of(state, *acts, **kw), "plan.yaml", COMPANY, "x")


def pooled(state):
    return state.ground.model.new_pipeline.mean_won_arr


def bigger(state, percent):
    """The pooled mean won size and ``percent`` more of it, as an entered dollar target."""
    return (pooled(state) * (100 + D(percent)) / 100).quantize(D("0.0001"))


def worksheet_flex(state, target, **kw):
    """What the worksheet's own flex says moving the pooled mean won ARR to ``target`` does to
    the plan's bookings, the plan's hires and programs held."""
    plan = plan_of(state, **kw)
    hires, inflows = actions.plan_inputs(state.ground, plan)
    probe = wd.Probe(state.ground, hires, inflows)
    return probe.change(probe.forecast(wd.with_setting(state.ground, WON_ARR, target)))


# ----------------------------------------------------- the worksheet's own flex, to the cent


@pytest.mark.parametrize("kw", [{}, {"hires": HIRES, "programs": PROGRAMS}])
def test_ten_percent_more_per_win_company_wide_from_the_first_day_is_the_worksheets_flex(
    state, kw
):
    target = pooled(state) * D("1.1")  # an entered target, to full precision
    r = report(state, act(target=target), **kw)
    gain = r["driver_actions"]["joint_gain"]
    flex = worksheet_flex(state, target, **kw)
    for w in (REST, NEXT):
        assert D(gain[w]) == D(flex[w]), w


def test_that_gain_is_a_tenth_of_what_the_plan_books_from_pipeline_created_after_the_as_of_date(
    state,
):
    """The by-hand route: a tenth of the future and added bookings the plan has without actions."""
    kw = {"hires": HIRES, "programs": PROGRAMS}
    r = report(state, act(target=pooled(state) * D("1.1")), **kw)
    plan = plan_of(state, **kw)
    h, i = actions.plan_inputs(state.ground, plan)
    probe = wd.Probe(state.ground, h, i)
    for w, months in (
        (REST, state.ground.rest_labels),
        (NEXT, state.ground.twelve_labels),
    ):
        tenth = sum(
            (
                sum(
                    v[m]
                    for k, v in probe.base.components.items()
                    if k != "existing pipeline"
                )
                / 10
                for m in months
            ),
            D(0),
        )
        assert abs(D(r["driver_actions"]["joint_gain"][w]) - tenth) <= D("0.02"), w


def test_a_zero_size_books_no_new_win_in_the_window_and_leaves_the_existing_pipeline(
    state,
):
    r = report(state, act(target="0"))
    plan = plan_of(state)
    h, i = actions.plan_inputs(state.ground, plan)
    probe = wd.Probe(state.ground, h, i)
    for w, months in (
        (REST, state.ground.rest_labels),
        (NEXT, state.ground.twelve_labels),
    ):
        new = sum(
            (
                sum(
                    v[m]
                    for k, v in probe.base.components.items()
                    if k != "existing pipeline"
                )
                for m in months
            ),
            D(0),
        )
        assert abs(D(r["driver_actions"]["joint_gain"][w]) + new) <= D("0.02"), w


# ----------------------------------------------------- nothing, or nothing changed


def test_a_size_target_equal_to_the_pooled_mean_changes_no_figure_anywhere(state):
    hold = {"hires": HIRES, "programs": PROGRAMS}
    base = report(state, **hold)
    same = report(state, act(target=pooled(state)), **hold)
    for key in ("gap", "forecasts", "actions", "required_pipeline", "history"):
        assert same[key] == base[key], key
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
    # the worksheet is the same but for what is said of the size with an action on it
    for a, b in zip(base["worksheet"]["drivers"], same["worksheet"]["drivers"]):
        if a["driver"] != "won_arr":
            assert a == b, a["driver"]
            continue
        for key in a:
            if key != "action_limitation":
                assert a[key] == b[key], key
        assert b["action_limitation"].endswith("at that setting.")


# ----------------------------------------------------- values reached two ways


def test_one_size_action_is_worth_its_joint_gain_and_the_bridge_step_is_that_gain(
    state,
):
    r = report(state, act(slice="enterprise", target=bigger(state, 15)))
    items = {i["id"]: i["removal_value"] for i in r["driver_actions"]["items"]}
    joint = r["driver_actions"]["joint_gain"]
    assert (
        items["x"] == joint and D(joint[REST]) > 0 and D(joint[NEXT]) > D(joint[REST])
    )
    steps = {s["kind"]: s for s in r["worksheet"]["bridge"]["steps"]}
    assert steps["actions"]["change"] == joint[REST]


def test_size_actions_in_different_segments_do_not_interact(state):
    r = report(
        state,
        act("e", "enterprise", target=bigger(state, 15)),
        act("m", "mid_market", start="2026-10", ramp=2, target=bigger(state, 8)),
    )
    rec = r["driver_actions"]["reconciliation"]
    for w in (REST, NEXT):
        assert abs(D(rec["values"][w])) <= D(rec["tolerance"][w])
    assert rec["sentences"][REST] == da.NO_INTERACTION
    names = {c["name"] for c in r["verdicts"]["software_correct"]["checks"]}
    assert (
        "driver actions on won ARR per win do not interact: removal values add to the joint gain"
        in names
    )


def test_the_company_is_every_segment_and_the_same_report_figures_follow(state):
    target = bigger(state, 10)
    company = report(state, act("c", "company", target=target))
    each = report(
        state,
        *(act(s, s, target=target) for s in ("commercial", "enterprise", "mid_market")),
    )
    assert (
        company["driver_actions"]["joint_gain"] == each["driver_actions"]["joint_gain"]
    )
    assert company["plan"]["with_plan"] == each["plan"]["with_plan"]
    assert company["plan"]["ranges"] == each["plan"]["ranges"]  # the same draws


def test_reordering_actions_changes_no_figure(state):
    e = act("e", "enterprise", target=bigger(state, 15))
    m = act("m", "mid_market", ramp=2, target=bigger(state, 8))
    a, b = report(state, e, m), report(state, m, e)
    for key in ("with_plan", "difference", "expected_fiscal_year", "ranges", "gap"):
        assert a["plan"][key] == b["plan"][key], key
    assert a["driver_actions"]["with_actions"] == b["driver_actions"]["with_actions"]
    assert (
        a["driver_actions"]["reconciliation"] == b["driver_actions"]["reconciliation"]
    )


def test_a_size_action_and_a_win_rate_action_on_the_same_slice_interact_and_the_line_says_so(
    state,
):
    """Wins that are more likely and bigger: the gain together is more than the two removal
    values add up to is not so, each is worth more with the other in place."""
    rate = state.ground.model.new_pipeline.win_rate
    r = report(
        state,
        act("size", target=bigger(state, 10)),
        act("rate", target=(rate * D("1.1")).quantize(D("1e-10")), driver="win_rate"),
    )
    d = r["driver_actions"]
    joint, items = d["joint_gain"], {i["id"]: i["removal_value"] for i in d["items"]}
    rec = d["reconciliation"]
    for w in (REST, NEXT):
        want = D(joint[w]) - D(items["size"][w]) - D(items["rate"][w])
        assert D(rec["values"][w]) == want
        # 10% on each: the interaction is the product, a hundredth of the new pipeline's bookings
        assert want < 0 and rec["material"][w] is True
    assert rec["sentences"][REST] == da.REINFORCE
    assert contract.validate(r) == []
    assert d["line"] == da.LINE_ANY and d["definition"] == da.DEFINITION_ANY


def test_the_interaction_is_the_product_of_the_two_changes_to_the_cent(state):
    """Size up s and win rate up r (both company-wide from the first day, no ramp): the gain
    together is (1 + s)(1 + r) - 1 of the new pipeline's bookings, each alone s or r, so what
    removing each loses adds up to s + r + 2sr and the line is -sr of them."""
    rate = state.ground.model.new_pipeline.win_rate
    s, rr = D("0.10"), D("0.05")
    r = report(
        state,
        act("size", target=pooled(state) * (1 + s)),
        act("rate", target=rate * (1 + rr), driver="win_rate"),
    )
    plan = plan_of(state)
    h, i = actions.plan_inputs(state.ground, plan)
    probe = wd.Probe(state.ground, h, i)
    for w, months in (
        (REST, state.ground.rest_labels),
        (NEXT, state.ground.twelve_labels),
    ):
        new = sum(
            (
                sum(
                    v[m]
                    for k, v in probe.base.components.items()
                    if k != "existing pipeline"
                )
                for m in months
            ),
            D(0),
        )
        got = D(r["driver_actions"]["reconciliation"]["values"][w])
        assert abs(got + s * rr * new) <= D("0.1"), w


# ----------------------------------------------------- ranges


def test_the_simulation_is_centered_on_the_expectation_for_a_larger_a_smaller_and_an_extreme_size(
    state,
):
    for percent in (30, -30, 900, -100):
        r = report(state, act(target=bigger(state, percent)))
        names = {
            c["name"]: c["passed"] for c in r["verdicts"]["software_correct"]["checks"]
        }
        assert names["plan simulation centered on its expectation"] is True, percent
        assert r["verdicts"]["software_correct"]["verdict"] == "yes", percent


def test_a_size_action_moves_the_range_not_only_the_mean(state):
    base = report(state)
    r = report(state, act(slice="enterprise", target=bigger(state, 40)))
    a = base["plan"]["ranges"]["bookings_in_window"][NEXT]
    b = r["plan"]["ranges"]["bookings_in_window"][NEXT]
    assert D(b["median"]) > D(a["median"])
    assert D(b["range80"][1]) - D(b["range80"][0]) > D(a["range80"][1]) - D(
        a["range80"][0]
    )
    assert "driver actions' win rates" not in r["plan"]["ranges"]["what_is_drawn"]
    assert "driver actions' changes" in r["plan"]["ranges"]["what_is_drawn"]


# ----------------------------------------------------- evidence


def test_the_evidence_reads_the_target_against_the_pooled_size_and_the_worksheets_settings(
    state,
):
    target = bigger(state, 10)
    r = report(state, act(slice="enterprise", target=target))
    item = r["driver_actions"]["items"][0]
    e, row = (
        item["evidence"],
        next(d for d in r["worksheet"]["drivers"] if d["driver"] == "won_arr"),
    )
    assert item["driver"] == "won_arr" and item["target"] == f"{target:.2f}"
    assert e["baseline"] == row["current"]["value"]
    assert e["change_percent"] == "10.00" and e["resulting"] == item["target"]
    assert (e["historical_low"], e["historical_high"]) == (
        row["historical"]["low"]["setting"], row["historical"]["high"]["setting"],
    )  # fmt: skip
    assert e["label"] in (da.INSIDE, da.OUTSIDE)
    assert "Enterprise" in item["affects"] and "target size" in item["affects"]
    assert r["driver_actions"]["line"] == da.LINE_ANY


def test_a_size_far_above_the_worksheets_high_is_outside_its_historical_settings(state):
    e = report(state, act(target=bigger(state, 400)))["driver_actions"]["items"][0][
        "evidence"
    ]
    assert (e["position"], e["label"]) == ("above", da.OUTSIDE)


def test_the_win_rates_needed_alone_still_solves_where_only_size_is_acted_on(state):
    r = report(state, act(target=bigger(state, 10)))
    rate = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "win_rate")
    assert rate["needed_alone"] is not None and rate["action_limitation"] is None  # fmt: skip


def test_the_size_row_still_solves_with_a_size_action_on_the_plan(state):
    r = report(state, act(target=bigger(state, 10)))
    row = next(d for d in r["worksheet"]["drivers"] if d["driver"] == "won_arr")
    assert row["needed_alone"] is not None
    # the setting it names, entered back, reaches the target the worksheet set
    n = row["needed_alone"]
    if n["outcome"] == "solves":
        assert D(n["achieved_fiscal_year_bookings"]) >= D(n["target"])


# ----------------------------------------------------- the contract refuses what is not so


@pytest.fixture(scope="module")
def good(state):
    return report(
        state,
        act("e", "enterprise", target=bigger(state, 15)),
        act("m", "mid_market", start="2026-10", ramp=2, target=bigger(state, 8)),
    )


def broken(good, edit):
    r = copy.deepcopy(good)
    edit(r)
    return contract.validate(r)


def test_the_good_report_is_valid_and_all_its_checks_pass(good):
    assert contract.validate(good) == []
    assert good["verdicts"]["software_correct"]["verdict"] == "yes"


EDITS = {
    "the baseline": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"baseline": "1.00"}),
    "the change in percent": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"change_percent": "99.00"}),
    "the resulting value": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"resulting": "1.00"}),
    "the position": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"position": "none"}),
    "the label": lambda r: r["driver_actions"]["items"][0]["evidence"].update({"label": "beyond what this team has done"}),
    "a negative target": lambda r: r["driver_actions"]["items"][0].update({"target": "-5.00"}),
    "the sentence on what it affects": lambda r: r["driver_actions"]["items"][0].update({"affects": "It adds 99."}),
    "the line": lambda r: r["driver_actions"].update({"line": da.LINE}),
    "the definition": lambda r: r["driver_actions"].update({"definition": da.DEFINITION}),
    "a win-rate evidence on a size": lambda r: r["driver_actions"]["items"][0].update({"evidence": {
        "baseline_rate": "0.2", "change_points": "1.00", "resulting_rate": "0.3",
        "historical_low": None, "historical_high": None, "position": "none", "label": "x"}}),
}  # fmt: skip


@pytest.mark.parametrize("what", list(EDITS))
def test_a_report_with_a_wrong_figure_or_sentence_is_refused(good, what):
    assert broken(good, EDITS[what]) != [], what


def test_the_markdown_says_the_size_in_dollars(good):
    text = render(good)
    assert "Pooled baseline $" in text and "%, resulting $" in text


# ----------------------------------------------------- a company whose creation is a flat rate


@pytest.fixture(scope="module")
def flat():
    with gen.in_repo():
        yield prepare(
            gen.PROFILES / "mighty-oak-holdings",
            gen.DATA / "mighty-oak-holdings",
            gen.AS_OF,
            400,
            0,
        )


@pytest.mark.parametrize("percent", [30, -30, 900, -100])
def test_the_simulation_is_centered_for_a_size_action_where_creation_is_flat(
    flat, percent
):
    assert not flat.ground.cap.adopted
    target = (pooled(flat) * (100 + D(percent)) / 100).quantize(D("0.0001"))
    with gen.in_repo():
        r = finish(
            flat,
            plan_of(flat, act(target=target)),
            "plan.yaml",
            "mighty-oak-holdings",
            "x",
        )
    names = {
        c["name"]: c["passed"] for c in r["verdicts"]["software_correct"]["checks"]
    }
    assert names["plan simulation centered on its expectation"] is True
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"
    assert (
        r["driver_actions"]["items"][0]["evidence"]["baseline"] == f"{pooled(flat):.2f}"
    )


# ----------------------------------------------------- the worksheet says how an action on the driver stacks


def test_the_worksheet_says_that_a_size_action_scales_the_setting_and_only_for_that_driver(
    state,
):
    plain = report(state)
    acted = report(state, act(target=bigger(state, 10)))
    size = {d["driver"]: d for d in acted["worksheet"]["drivers"]}
    was = {d["driver"]: d for d in plain["worksheet"]["drivers"]}
    assert "size actions change the size this sets by the same relative amount" in size["won_arr"]["action_limitation"]  # fmt: skip
    assert was["won_arr"]["action_limitation"] is None
    for other in ("win_rate", "productivity", "cycle_days"):
        assert size[other]["action_limitation"] is None, other
        assert size[other]["limitation"] == was[other]["limitation"], other


def test_the_contract_refuses_a_worksheet_that_forgets_or_invents_that_sentence(state):
    acted = report(state, act(target=bigger(state, 10)))
    gone = copy.deepcopy(acted)
    row = next(d for d in gone["worksheet"]["drivers"] if d["driver"] == "won_arr")
    row["action_limitation"] = None
    assert contract.validate(gone) != []
    plain = report(state)
    invented = copy.deepcopy(plain)
    row = next(d for d in invented["worksheet"]["drivers"] if d["driver"] == "won_arr")
    row["action_limitation"] = (
        "The plan's size actions change the size this sets by the same relative amount."
    )
    assert contract.validate(invented) != []

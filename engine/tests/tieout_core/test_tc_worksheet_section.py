"""The worksheet section for the three demo companies: pinned to the known answers of a
separately written reference script where the conventions agree, and the places they differ
written down; the bridge, the restated figures and the repeatability of the whole."""

import copy
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, worksheet
from engine.tieout_core import worksheet_rules as rules
from engine.tieout_core.plan import NEXT_12, REST_OF_FY, load_plan
from engine.tieout_core.report import prepare
from engine.tieout_core.worksheet_drivers import Probe

KNOWN = json.loads(
    (Path(__file__).with_name("worksheet_known_answers.json")).read_text()
)["companies"]
D = Decimal
CENT = D("0.01")


@pytest.fixture(scope="module", params=gen.COMPANIES)
def prepared(request):
    company = request.param
    with gen.in_repo():
        yield (
            company,
            prepare(
                gen.PROFILES / company,
                gen.DATA / company,
                gen.AS_OF,
                gen.DRAWS,
                gen.SEED,
            ),
        )


def section_for(company, state, scenario_id):
    """The section as ``finish`` builds it, from the pieces ``prepare`` leaves."""
    g = state.ground
    scenario = next(s for s in gen.SCENARIOS if s.id == scenario_id)
    plan_section, hires, inflows, plan = None, (), (), None
    if scenario.plan is not None:
        path = gen.PROFILES / company / scenario.plan
        plan = load_plan(path, gen.AS_OF, state.cap.members)
        plan_section, _ = actions.plan_section(g, state.scenario, plan, path)
        hires, inflows = actions.plan_inputs(g, plan)
    section, checks = worksheet.worksheet_section(
        g, worksheet.company_quarters(g), state.params, plan_section, hires, inflows,
        state.actions_section, state.gap, state.required,
    )  # fmt: skip
    return section, checks, plan_section


def driver(section, name):
    return next(d for d in section["drivers"] if d["driver"] == name)


def near(got, want, places=CENT):
    return abs(D(got) - D(want)) <= places


# ----------------------------------------------------------- pinned to the reference answers


def test_the_baseline_and_every_check_hold(prepared):
    company, state = prepared
    with gen.in_repo():
        _, checks, _ = section_for(company, state, "as-signed")
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]
    k = KNOWN[company]["baseline"]
    year = state.gap["fiscal_year"]
    assert D(year["expected"]) == D(k["expected"]).quantize(CENT)
    assert D(year["gap"]) == D(k["gap"]).quantize(CENT)


def test_the_observations_are_the_reference_quarters(prepared):
    company, state = prepared
    with gen.in_repo():
        section, _, _ = section_for(company, state, "as-signed")
    known = KNOWN[company]["observations"]
    got = driver(section, rules.WIN_RATE)["evidence"]["quarters"]
    assert [q["quarter"] for q in got] == [o["quarter"] for o in known]
    for q, o in zip(got, known):
        assert (q["created"], q["wins"], q["mature"]) == (
            o["created"],
            o["wins"],
            o["mature"],
        )
    for name in rules.DRIVERS:
        for q, o in zip(driver(section, name)["evidence"]["quarters"], known):
            want = o["values"][name]
            if want is None:
                assert q["value"] is None
            else:
                assert near(q["value"], want, D("0.01"))
            # the same gate, quarter by quarter
            assert q["eligible"] == o["gates"][name]


def test_current_settings_and_changes_match_the_reference_to_the_cent(prepared):
    company, state = prepared
    with gen.in_repo():
        section, _, _ = section_for(company, state, "as-signed")
    for name, k in KNOWN[company]["drivers"].items():
        d = driver(section, name)
        assert near(d["current"]["value"], k["current"], D("0.01"))
        h = d["historical"]
        assert d["evidence"]["eligible_quarters"] == k["eligible_quarters"]
        for side, delta in (("low", "low_delta"), ("high", "high_delta")):
            assert near(h[side]["setting"], k[side], D("0.01"))
            assert D(h[side]["change"][REST_OF_FY]) == D(k[delta]["fy"])
            assert D(h[side]["change"][NEXT_12]) == D(k[delta]["ntm"])
        assert near(h["minimum"], k["min"], D("0.01")) and near(
            h["maximum"], k["max"], D("0.01")
        )


def test_needed_alone_matches_the_reference_where_the_conventions_agree(prepared):
    company, state = prepared
    with gen.in_repo():
        section, _, _ = section_for(company, state, "as-signed")
    for name, k in KNOWN[company]["drivers"].items():
        n = driver(section, name)["needed_alone"]
        want = k["needed"]
        if name != rules.CYCLE_DAYS:
            assert n["outcome"] == "solves"
            assert near(
                n["value"],
                want["value"],
                D("0.0001") if name != rules.WON_ARR else CENT,
            )
            assert near(n["achieved_fiscal_year_bookings"], want["achieved"])
            # the reference calls it extrapolation when outside min/max; so does the core
            assert (n["inside_observed_range"] is False) == want["extrapolation"]
        elif want["scale"] == "0":
            # a company that cannot close on cycle even at zero days
            assert (
                n["outcome"] == "cannot_close_alone"
                and n["reason"] == "short_even_at_zero_days"
            )
            assert near(n["achieved_fiscal_year_bookings"], want["achieved"])
        else:
            assert n["scale"] == want["scale"]
            assert near(n["achieved_fiscal_year_bookings"], want["achieved"])
            assert near(n["overshoot"], want["overshoot"])
            # DIFFERENCE: the reference prints current x scale; the core prints the mean win time
            # the rounded samples really have (the reference also saved it).
            assert near(n["value"], want["realized_mean_days"], D("0.01"))


def test_where_the_core_differs_from_the_reference_is_on_purpose(prepared):
    """Two conventions. (1) The core never calls a value that cannot close the gap 'beyond' or
    'inside' history: the reference marked zero days as extrapolation, the core shows no
    comparison for an outcome that is not a solve. (2) The reference refits outside
    ``prepare``; the core reads the fit in use, which is why the numbers agree to the cent."""
    company, state = prepared
    with gen.in_repo():
        section, _, _ = section_for(company, state, "as-signed")
    for d in section["drivers"]:
        n = d["needed_alone"]
        if n["outcome"] != "solves":
            assert n["inside_observed_range"] is None and n["history_label"] is None


# ----------------------------------------------------------- the plan in force


def test_plan_inputs_are_what_the_plan_section_forecasts(prepared):
    company, state = prepared
    with gen.in_repo():
        _, _, plan_section = section_for(company, state, "demo-plan")
        path = gen.PROFILES / company / "plan.yaml"
        plan = load_plan(path, gen.AS_OF, state.cap.members)
        hires, inflows = actions.plan_inputs(state.ground, plan)
        probe = Probe(state.ground, hires, inflows)
    shown = probe.shown(probe.base)
    assert {k: str(v.quantize(CENT)) for k, v in shown.items()} == plan_section[
        "with_plan"
    ]


def test_a_plan_moves_the_baseline_the_drivers_are_measured_around(prepared):
    company, state = prepared
    with gen.in_repo():
        signed, _, _ = section_for(company, state, "as-signed")
        planned, checks, _ = section_for(company, state, "demo-plan")
    assert all(c.passed for c in checks)
    assert signed["plan_in_force"] is False and planned["plan_in_force"] is True
    # measured around the plan, a win-rate change is worth more when the plan adds pipeline
    a = D(driver(signed, rules.WIN_RATE)["historical"]["high"]["change"][NEXT_12])
    b = D(driver(planned, rules.WIN_RATE)["historical"]["high"]["change"][NEXT_12])
    assert b > a


def test_the_bridge_sums_exactly_in_the_declared_order(prepared):
    company, state = prepared
    with gen.in_repo():
        planned, _, plan_section = section_for(company, state, "demo-plan")
    steps = planned["bridge"]["steps"]
    assert steps[0]["kind"] == "as_signed"
    assert [s["kind"] for s in steps][-2:] == ["working_plan", "remaining_gap"]
    items = [s for s in steps if s["kind"] in ("hires", "program")]
    assert [s["label"] for s in items] == [i["label"] for i in plan_section["items"]]
    total = D(steps[0]["to"]) + sum((D(s["change"]) for s in items), D(0))
    assert total == D(steps[-2]["to"]) == D(plan_section["expected_fiscal_year"])
    assert D(planned["bridge"]["target"]["value"]) - total == D(steps[-1]["to"])


def test_without_a_plan_the_bridge_is_as_signed_and_the_gap(prepared):
    company, state = prepared
    with gen.in_repo():
        signed, _, _ = section_for(company, state, "as-signed")
    assert [s["kind"] for s in signed["bridge"]["steps"]] == [
        "as_signed",
        "working_plan",
        "remaining_gap",
    ]
    s = signed["summary"]
    assert s["working_plan"]["value"] == s["as_signed"]["value"]
    assert s["twelve_month_gain"] is None and s["no_plan_note"]


def test_the_chain_is_as_signed_in_both_scenarios_and_holds_the_remaining_quarters(
    prepared,
):
    company, state = prepared
    with gen.in_repo():
        signed, _, _ = section_for(company, state, "as-signed")
        planned, _, _ = section_for(company, state, "demo-plan")
    assert signed["chain"] == planned["chain"]
    assert signed["chain"]["basis"] == "as signed"
    remaining = [
        q["quarter"] for q in state.required["quarters"] if q["status"] != "closed"
    ]
    assert [q["quarter"] for q in signed["chain"]["quarters"]] == remaining


# ----------------------------------------------------------- repeatability


def test_running_the_worksheet_twice_and_between_other_plans_gives_identical_bytes(
    prepared,
):
    company, state = prepared
    with gen.in_repo():
        first = json.dumps(section_for(company, state, "demo-plan")[0], sort_keys=True)
        for other in ("hires-only", "as-signed", "program-only"):
            section_for(company, state, other)
        again = json.dumps(section_for(company, state, "demo-plan")[0], sort_keys=True)
    assert again == first


def test_the_worksheet_changes_nothing_it_reads(prepared):
    company, state = prepared
    before = (state.ground.model, state.ground.cap, state.ground.pop)
    snapshot = copy.deepcopy(state.ground.model.new_pipeline)
    with gen.in_repo():
        section_for(company, state, "demo-plan")
    assert (state.ground.model, state.ground.cap, state.ground.pop) == before
    assert state.ground.model.new_pipeline == snapshot


# ----------------------------------------------------------- words


def test_every_sentence_is_written_without_a_digit_the_fields_do_not_carry(prepared):
    company, state = prepared
    with gen.in_repo():
        section, _, _ = section_for(company, state, "demo-plan")
    sentences = [
        section[k]
        for k in (
            "definition",
            "measured_around",
            "expectation_note",
            "sensitivity_note",
            "history_note",
        )
    ]
    sentences += [
        section["bridge"]["order"],
        section["actions"]["note"],
        section["chain"]["note"],
    ]
    for d in section["drivers"]:
        n = d["needed_alone"]
        sentences += [d["applies_to"], d["evidence"]["gate"], n["outcome_label"], n["reason_label"],
                      n["history_label"], d["limitation"], d["historical_unavailable_because"]]  # fmt: skip
        sentences += [q["not_eligible_because"] for q in d["evidence"]["quarters"]]
        sentences += [d["historical"]["rule"]] if d["historical"] else []
    sentences += [r["closes_alone_label"] for r in section["actions"]["rows"]]
    assert all(not re.search(r"\d", s) for s in sentences if s)
    assert sum(1 for s in sentences if s) > 20


def test_a_recency_fit_names_the_limitation_and_a_matured_fit_does_not(prepared):
    company, state = prepared
    with gen.in_repo():
        section, _, _ = section_for(company, state, "as-signed")
    recency = state.params.estimator == "cumulative incidence"
    for name in (rules.WIN_RATE, rules.WON_ARR):
        text = driver(section, name)["limitation"]
        assert (text is not None and "older than that fit" in text) == recency

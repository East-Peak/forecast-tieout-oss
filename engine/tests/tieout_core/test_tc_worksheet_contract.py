"""The worksheet's contract: the schema is closed, every figure carried from elsewhere in the
report is what its source holds, the historical settings are recomputed from the observations,
the bridge adds up, and a sentence carries no digit its fields do not."""

import copy
import json
from pathlib import Path

import pytest

from engine.tieout_core import contract

REPORTS = Path("frontend/public/data/reports")


def load(company, scenario):
    return json.loads((REPORTS / company / f"{scenario}.json").read_text())


@pytest.fixture(scope="module")
def planned():
    return load("sapling-industries", "demo-plan")


@pytest.fixture(scope="module")
def signed():
    return load("sprout-labs", "as-signed")


def broken(report, edit):
    r = copy.deepcopy(report)
    edit(r)
    return contract.validate(r)


def driver(r, name):
    return next(d for d in r["worksheet"]["drivers"] if d["driver"] == name)


@pytest.mark.parametrize(
    "scenario", ["as-signed", "demo-plan", "hires-only", "program-only"]
)
@pytest.mark.parametrize(
    "company", ["sprout-labs", "sapling-industries", "mighty-oak-holdings"]
)
def test_every_committed_report_satisfies_the_contract(company, scenario):
    assert contract.validate(load(company, scenario)) == []


def test_the_section_is_required_and_closed(planned):
    assert broken(planned, lambda r: r.pop("worksheet"))
    assert broken(planned, lambda r: r["worksheet"].update(extra=1))
    assert broken(planned, lambda r: driver(r, "win_rate").update(extra=1))


def test_a_restated_figure_must_be_what_its_source_holds(planned):
    def edit(r):
        r["worksheet"]["summary"]["remaining_gap"]["value"] = "1.00"

    assert any("is not what" in p for p in broken(planned, edit))

    def edit(r):
        r["worksheet"]["actions"]["rows"][0]["bookings_gained"]["value"] = None

    assert broken(planned, edit)

    def edit(r):
        q = r["worksheet"]["chain"]["quarters"][0]
        q["bookings"]["expected"]["value"] = "1.00"

    assert broken(planned, edit)


def test_a_source_that_is_not_in_the_report_is_refused(planned):
    def edit(r):
        r["worksheet"]["summary"]["as_signed"]["source"] = "/gap/nowhere"

    assert any("is not in the report" in p for p in broken(planned, edit))


def test_the_bridge_must_add_up(planned):
    def edit(r):
        step = next(
            s for s in r["worksheet"]["bridge"]["steps"] if s["kind"] == "hires"
        )
        step["change"] = "1.00"

    assert broken(planned, edit)

    def edit(r):
        r["worksheet"]["bridge"]["steps"][-1]["to"] = "5.00"

    assert broken(planned, edit)


def test_historical_settings_are_recomputed_from_the_observations(planned):
    def edit(r):
        driver(r, "win_rate")["historical"]["low"]["setting"] = "0.0001"

    assert any("lower half" in p for p in broken(planned, edit))

    def edit(r):
        driver(r, "win_rate")["historical"]["maximum"] = "0.9999"

    assert broken(planned, edit)


def test_the_gate_and_the_settings_travel_together(planned):
    def edit(r):
        d = driver(r, "win_rate")
        d["evidence"]["gate_passed"] = False

    assert broken(planned, edit)

    def edit(r):
        d = driver(r, "win_rate")
        d["historical"] = None
        d["evidence"]["gate_passed"] = False

    assert broken(planned, edit)  # a missing range must say why


def test_inside_or_beyond_history_must_agree_with_the_value_and_the_range(planned):
    def edit(r):
        n = driver(r, "win_rate")["needed_alone"]
        n["inside_observed_range"] = not n["inside_observed_range"]

    assert broken(planned, edit)


def test_a_sentence_may_not_carry_a_digit(planned):
    def edit(r):
        driver(r, "win_rate")["limitation"] = "Only 6 quarters count."

    assert any("digit" in p for p in broken(planned, edit))

    def edit(r):
        r["worksheet"]["history_note"] += " 100%"

    assert any("digit" in p for p in broken(planned, edit))


def test_a_failed_self_check_of_the_section_is_a_contract_problem(planned):
    def edit(r):
        r["worksheet"]["checks"][0]["passed"] = False

    assert any("self-check" in p for p in broken(planned, edit))


def test_the_chain_names_each_remaining_quarter_once(planned):
    assert broken(planned, lambda r: r["worksheet"]["chain"]["quarters"].pop())


def test_the_plan_flag_follows_the_report(planned, signed):
    assert broken(planned, lambda r: r["worksheet"].update(plan_in_force=False))
    assert broken(signed, lambda r: r["worksheet"].update(plan_in_force=True))


def test_a_report_with_a_plan_has_the_gain_and_cost_and_one_without_has_none(
    planned, signed
):
    assert planned["worksheet"]["summary"]["twelve_month_gain"] is not None
    assert signed["worksheet"]["summary"]["twelve_month_gain"] is None

    def edit(r):
        r["worksheet"]["summary"]["twelve_month_gain"] = None

    assert broken(planned, edit)


def test_the_schema_is_versioned():
    assert contract.SCHEMA_VERSION == "2.5.0"

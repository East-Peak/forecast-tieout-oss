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

    assert any("pointers" in p for p in broken(planned, edit))

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

    assert any("pointers" in p for p in broken(planned, edit))


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
    assert contract.SCHEMA_VERSION == "2.8.0"


# ---------------------------------------------------------------- the fix round


from engine.tieout_core import worksheet as ws


def never_raises(report, edit):
    """The validator returns problems for a malformed payload; it never raises."""
    return broken(report, edit)


def test_a_sub_cent_shortfall_is_valid_only_with_its_explanation(planned):
    def cannot(r, note):
        d = driver(r, "win_rate")
        n = d["needed_alone"]
        n.update(
            outcome="cannot_close_alone", outcome_label=ws.OUTCOME_LABELS["cannot_close_alone"],
            reaches_target=False, reason="bounded_at_one", reason_label=ws.REASON_LABELS["bounded_at_one"],
            value="1.0000", achieved_fiscal_year_bookings=n["target"], overshoot=None,
            precision_note=note, inside_observed_range=None, history_label=None,
        )  # fmt: skip

    assert broken(planned, lambda r: cannot(r, ws.SUB_CENT_NOTE)) == []
    assert broken(planned, lambda r: cannot(r, None))


def test_a_figure_that_reaches_the_target_may_not_say_it_cannot(planned):
    def edit(r):
        n = driver(r, "win_rate")["needed_alone"]
        n.update(
            outcome="cannot_close_alone", reaches_target=False, reason="bounded_at_one"
        )

    assert broken(planned, edit)


def test_an_absurd_sensitivity_is_refused(planned):
    def edit(r):
        driver(r, "win_rate")["historical"]["high"]["change"]["next twelve months"] = (
            "999999999.00"
        )

    assert any("one line" in p for p in broken(planned, edit))


def test_a_sensitivity_on_the_wrong_side_or_a_zero_move_with_a_change_is_refused(
    planned,
):
    def flip(r):
        c = driver(r, "won_arr")["historical"]["high"]["change"]
        c["rest of fiscal year"] = "-" + c["rest of fiscal year"]

    assert any("wrong side" in p for p in broken(planned, flip))

    def cycle(r):  # a longer cycle cannot add bookings
        c = driver(r, "cycle_days")["historical"]["high"]["change"]
        c["next twelve months"] = "100.00"

    assert any("wrong side" in p for p in broken(planned, cycle))


def test_outcome_wording_must_be_the_reports_not_a_promise(planned):
    def edit(r):
        driver(r, "win_rate")["needed_alone"]["outcome_label"] = (
            "Guaranteed achievable."
        )

    assert broken(planned, edit)

    def edit(r):
        driver(r, "cycle_days")["needed_alone"]["reason_label"] = "Easy."

    assert broken(planned, edit)


def test_eligibility_follows_the_quarters_own_fields(planned):
    def edit(r):
        q = driver(r, "win_rate")["evidence"]["quarters"][0]
        q["mature"], q["created"] = False, 0  # still marked eligible

    assert broken(planned, edit)

    def edit(r):
        driver(r, "win_rate")["evidence"]["quarters"][1]["eligible"] = False

    assert broken(planned, edit)

    def edit(r):
        driver(r, "win_rate")["evidence"]["quarters"][0]["wins"] += 3

    assert any("follow from its own counts" in p for p in broken(planned, edit))


def test_a_solved_value_cannot_be_nulled_along_with_its_history_fields(planned):
    def edit(r):
        n = driver(r, "won_arr")["needed_alone"]
        n.update(value=None, inside_observed_range=None, history_label=None)

    assert broken(planned, edit)


def test_each_outcome_carries_only_its_own_payload(planned):
    def solve_with_reason(r):
        driver(r, "won_arr")["needed_alone"]["reason"] = "no_effect_in_the_year"

    def solve_without_overshoot(r):
        driver(r, "won_arr")["needed_alone"]["overshoot"] = None

    def covered_with_scale(r):
        n = driver(r, "won_arr")["needed_alone"]
        n.update(outcome="already_at_or_ahead", scale="1/1")

    def wrong_places(r):
        driver(r, "win_rate")["needed_alone"]["value"] = "0.2"

    for edit in (
        solve_with_reason,
        solve_without_overshoot,
        covered_with_scale,
        wrong_places,
    ):
        assert broken(planned, edit), edit.__name__


def test_settings_must_be_the_half_means_and_the_extremes(planned):
    def edit(r):
        driver(r, "won_arr")["historical"]["high"]["setting"] = "1.00"

    assert broken(planned, edit)

    def edit(r):
        driver(r, "won_arr")["historical"]["minimum"] = "1.00"

    assert broken(planned, edit)


def test_text_must_equal_what_the_fields_produce(planned):
    for key in ("limitation", "applies_to", "unit_label"):

        def edit(r, key=key):
            driver(r, "cycle_days")[key] = "Whatever."

        assert broken(planned, edit), key

    def edit(r):
        r["worksheet"]["sensitivity_note"] = "Trust these."

    assert broken(planned, edit)


def test_a_valid_number_from_the_wrong_path_is_refused(signed):
    # /gap/lever/target holds the same text as /gap/fiscal_year/target: the number is right, the
    # path is not the canonical one for this field
    assert signed["gap"]["lever"]["target"] == signed["gap"]["fiscal_year"]["target"]

    def edit(r):
        r["worksheet"]["summary"]["fiscal_year_target"]["source"] = "/gap/lever/target"

    assert any("pointers" in p for p in broken(signed, edit))

    def edit(r):
        q = r["worksheet"]["chain"]["quarters"][0]["bookings"]["target"]
        q["source"] = q["source"].replace("/2/", "/3/")

    assert broken(signed, edit)


def test_an_action_row_swapped_for_the_other_kind_is_refused(planned):
    def edit(r):
        rows = r["worksheet"]["actions"]["rows"]
        rows[0], rows[1] = rows[1], rows[0]

    assert broken(planned, edit)


def test_malformed_payloads_the_schema_permits_give_problems_not_exceptions(planned):
    def null_value(r):
        driver(r, "win_rate")["evidence"]["quarters"][0]["value"] = None

    def empty_bridge(r):
        r["worksheet"]["bridge"]["steps"] = []

    def wrong_bridge_kinds(r):
        for s in r["worksheet"]["bridge"]["steps"]:
            s["kind"] = "as_signed"

    def no_quarters(r):
        driver(r, "win_rate")["evidence"]["quarters"] = []

    def three_drivers(r):
        r["worksheet"]["drivers"].pop()

    def odd_pointer(r):
        r["worksheet"]["summary"]["as_signed"]["source"] = "/gap/quarters/99/nope"

    for edit in (
        null_value,
        empty_bridge,
        wrong_bridge_kinds,
        no_quarters,
        three_drivers,
        odd_pointer,
    ):
        assert never_raises(planned, edit), edit.__name__


def test_ranks_are_the_order_of_the_largest_absolute_change_and_nothing_else(planned):
    ranks = [d["rank"] for d in planned["worksheet"]["drivers"]]
    for window in ("rest of fiscal year", "next twelve months"):
        assert sorted(r[window] for r in ranks) == [1, 2, 3, 4]
    assert all(r["rank"] for r in planned["worksheet"]["actions"]["rows"])

    def edit(r):
        a, b = (
            r["worksheet"]["drivers"][0]["rank"],
            r["worksheet"]["drivers"][1]["rank"],
        )
        a["rest of fiscal year"], b["rest of fiscal year"] = (
            b["rest of fiscal year"],
            a["rest of fiscal year"],
        )

    assert broken(planned, edit)

    def edit(r):
        r["worksheet"]["actions"]["rows"][0]["rank"]["next twelve months"] = 2

    assert broken(planned, edit)


def test_ties_keep_the_listed_order_and_nothing_is_ranked_without_a_change():
    from decimal import Decimal as D

    same = {"rest of fiscal year": D(5), "next twelve months": D(5)}
    ranks = ws.rank_by_window(
        [same, None, same, {"rest of fiscal year": D(9), "next twelve months": D(1)}]
    )
    assert [r["rest of fiscal year"] for r in ranks] == [2, None, 3, 1]
    assert [r["next twelve months"] for r in ranks] == [1, None, 2, 3]


def test_the_verdict_counts_the_worksheets_checks(planned):
    names = {c["name"] for c in planned["verdicts"]["software_correct"]["checks"]}
    assert {c["name"] for c in planned["worksheet"]["checks"]} <= names

    def edit(r):
        r["verdicts"]["software_correct"]["checks"] = [
            c
            for c in r["verdicts"]["software_correct"]["checks"]
            if not c["name"].startswith("worksheet")
        ]

    assert broken(planned, edit)

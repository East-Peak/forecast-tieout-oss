"""Goal 3B fix round: the fields and wordings the screens need so that a missing figure says why,
a report knows which company and scenario it is, and a comparison does not show a zero for what
could not be valued."""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import contract
from engine.tieout_core.actions import closing_cost_note
from engine.tieout_core.comparison import BASELINE, comparison_rows
from engine.tieout_core.pipeline_report import quarter_notes
from engine.tieout_core.report import build_report

AS_OF = gen.AS_OF
REST, TWELVE = "rest of fiscal year", "next twelve months"


@pytest.fixture(scope="module")
def reports():
    out = {}
    for company in gen.COMPANIES:
        profile = Path(f"engine/config/profiles/{company}")
        data = Path(f"engine/data-v2/{company}")
        out[company] = {
            "as-signed": build_report(profile, data, AS_OF, draws=100),
            "demo-plan": build_report(
                profile, data, AS_OF, draws=100, plan_path=profile / "plan.yaml"
            ),
        }
    return out


def _copy(x):
    return json.loads(json.dumps(x))


# ---------------------------------------------------------------- a report knows which company and scenario it is


def test_a_report_carries_its_company_and_scenario(reports):
    assert reports["sprout-labs"]["as-signed"]["inputs"]["identity"] == {
        "company": "sprout-labs",
        "scenario": "as-signed",
    }
    assert reports["sprout-labs"]["demo-plan"]["inputs"]["identity"] == {
        "company": "sprout-labs",
        "scenario": "plan",
    }  # the core's own name for a run: the plan file's stem


def test_the_generator_names_each_report_by_the_scenario_it_is_filed_under():
    built = gen.build(["mighty-oak-holdings"], draws=100)
    for scenario in ("as-signed", "demo-plan", "hires-only", "programme-only"):
        report = json.loads(built[f"mighty-oak-holdings/{scenario}.json"])
        assert report["inputs"]["identity"] == {
            "company": "mighty-oak-holdings",
            "scenario": scenario,
        }


def test_the_contract_requires_the_identity(reports):
    report = _copy(reports["sprout-labs"]["as-signed"])
    del report["inputs"]["identity"]
    assert contract.validate(report)


# ---------------------------------------------------------------- a missing cost says why


@pytest.mark.parametrize(
    "kind,outcome,status,cost,says",
    [
        ("hires", "feasible", "entered", "1000.00", None),
        ("hires", "unreachable", "entered", None, "no number of hires closes the gap"),
        ("hires", "already covered", "entered", None, "already covered"),
        ("hires", "feasible", "cost not entered", None, "cost not entered"),
        ("programme", "feasible", "entered", "1000.00", None),
        (
            "programme",
            "unreachable",
            "entered",
            None,
            "no amount of pipeline closes the gap",
        ),
        ("programme", "already covered", "entered", None, "already covered"),
        ("programme", "feasible", "cost not entered", None, "cost not entered"),
    ],
)
def test_the_cost_of_a_closing_action_says_why_it_is_missing(
    kind, outcome, status, cost, says
):
    note = closing_cost_note(kind, outcome, status, cost)
    if says is None:
        assert note is None
    else:
        assert note is not None and says in note


def test_every_closing_action_with_no_cost_carries_a_note_and_every_cost_has_none(
    reports,
):
    for scenarios in reports.values():
        close = scenarios["as-signed"]["actions"]["close_the_fiscal_year_gap"]
        rows = [close["programme"]] + (
            [close["hires"]] if "bound" in close["hires"] else []
        )
        for row in rows:
            assert (row["cash_cost_in_twelve_months"] is None) == (
                row["cash_cost_note"] is not None
            )
    # an unreachable hire whose cost was entered does not say the cost was missing
    sprout = reports["sprout-labs"]["as-signed"]["actions"][
        "close_the_fiscal_year_gap"
    ]["hires"]
    assert sprout["outcome"] == "unreachable" and sprout["cost_status"] == "entered"
    assert "not entered" not in sprout["cash_cost_note"]


# ---------------------------------------------------------------- a missing requirement figure says why


class _Q:  # the few fields the notes read
    def __init__(self, outcome, total, months, days, per_day_ratio, per_ae_ratio):
        self.outcome, self.total, self.months, self.days = outcome, total, months, days
        self.per_day_ratio, self.per_ae_ratio = per_day_ratio, per_ae_ratio


def test_notes_separate_nothing_required_from_unavailable():
    covered = quarter_notes(
        "already covered", None, Decimal(5), 90, best_day=Decimal(1), best_ae=Decimal(1)
    )
    assert covered["total"].startswith("no extra pipeline is required")
    assert covered["per_day"].startswith("no extra pipeline is required")
    assert covered["per_ae"].startswith("no extra pipeline is required")
    full = quarter_notes(
        "feasible", Decimal(10), Decimal(5), 90, best_day=Decimal(1), best_ae=Decimal(1)
    )
    assert full == {"total": None, "per_day": None, "per_ae": None}
    no_history = quarter_notes(
        "feasible", Decimal(10), Decimal(5), 90, best_day=None, best_ae=None
    )
    assert (
        no_history["per_day"].startswith("unavailable")
        and "four complete quarters" in no_history["per_day"]
    )
    assert "four complete quarters" in no_history["per_ae"]
    no_ramp = quarter_notes(
        "feasible", Decimal(10), None, 90, best_day=Decimal(1), best_ae=Decimal(1)
    )
    assert (
        no_ramp["per_ae"].startswith("unavailable") and "no ramp" in no_ramp["per_ae"]
    )
    assert no_ramp["per_day"] is None


def test_each_quarter_row_carries_a_note_exactly_where_a_figure_is_missing(reports):
    sapling = reports["sapling-industries"]["as-signed"]["required_pipeline"][
        "quarters"
    ]
    covered = next(q for q in sapling if q["outcome"] == "already covered")
    assert covered["total_created_in_span"] is None
    assert covered["total_created_note"].startswith("no extra pipeline is required")
    assert covered["per_day"]["note"].startswith("no extra pipeline is required")
    for scenarios in reports.values():
        for q in scenarios["as-signed"]["required_pipeline"]["quarters"]:
            assert (q["total_created_in_span"] is None) == (
                q["total_created_note"] is not None
            )
            for part in ("per_day", "per_ramped_ae_month"):
                p = q[part]
                missing = (
                    p["required_total"] is None
                    or p["required_against_team_best"] is None
                )
                assert missing == (p["note"] is not None), (q["quarter"], part)


def test_the_contract_refuses_a_note_that_disagrees_with_its_figure(reports):
    report = _copy(reports["sapling-industries"]["as-signed"])
    q = next(
        x
        for x in report["required_pipeline"]["quarters"]
        if x["outcome"] == "already covered"
    )
    q["total_created_note"] = None
    assert any("note" in p for p in contract.validate(report))


# ---------------------------------------------------------------- headline figures, not sentences


def test_an_unreachable_quarter_carries_what_it_would_take_as_a_figure(reports):
    for scenarios in reports.values():
        for q in scenarios["as-signed"]["required_pipeline"]["quarters"]:
            if (
                q["outcome"] == "unreachable within bounds"
                and q["would_take"] is not None
            ):
                assert f"${Decimal(q['would_take']):,.2f}" in q["headline"]
            else:
                assert q["would_take"] is None


def test_the_year_total_spread_evenly_carries_its_outcome_and_figure(reports):
    for scenarios in reports.values():
        r = scenarios["as-signed"]
        spread = r["required_pipeline"]["fiscal_year"]["single_spread"]
        assert spread["outcome"] == r["gap"]["lever"]["outcome"]
        assert spread["required"] == r["gap"]["lever"]["required"]


# ---------------------------------------------------------------- a short name for a stage's win rate


def test_a_stage_win_rate_carries_the_stage_name_as_its_label(reports):
    rates = reports["sapling-industries"]["as-signed"]["rates"]
    stage = [
        x
        for x in rates
        if x["name"].count(":") == 1 and x["name"].startswith("win_within_horizon")
    ]
    assert stage and all(x["label"] for x in stage)
    assert f" {stage[0]['label']} " in stage[0]["definition"]
    assert next(x for x in rates if x["name"] == "new_pipeline_win_rate")["label"]
    assert all(x["label"] is None for x in rates if x["name"] == "mean_won_arr")


# ---------------------------------------------------------------- the sentence and the figure agree


def test_the_adoption_sentence_rounds_the_reported_improvement_as_the_screen_does(
    reports,
):
    for scenarios in reports.values():
        decision = scenarios["as-signed"]["roster_capacity"]["decision"]
        for h in decision["horizons"]:
            shown = (Decimal(h["improvement"]) * 100).quantize(
                Decimal("0.1"), ROUND_HALF_UP
            )
            if decision["outcome"] == "adopted":
                assert f"{shown}% lower" in decision["reason"], (
                    shown,
                    decision["reason"],
                )


# ---------------------------------------------------------------- segment names read as words


def test_a_plan_item_names_its_segment_as_words(reports):
    for scenarios in reports.values():
        for item in scenarios["demo-plan"]["plan"]["items"]:
            if item["kind"] == "hires":
                assert "_" not in item["label"] and "_" not in item["detail"]


# ---------------------------------------------------------------- a comparison does not show a zero for what could not be valued


def _report(plan=None):
    return {
        "gap": {
            "fiscal_year": {
                "expected": "5000.00",
                "gap": "3000.00",
                "forecast_rest_of_year": "4000.00",
            }
        },
        **({"plan": plan} if plan else {}),
    }


def _plan(items):
    return {
        "baseline": {REST: "4000.00", TWELVE: "9000.00"},
        "with_plan": {REST: "4000.00", TWELVE: "9000.00"},
        "difference": {REST: "0.00", TWELVE: "0.00"},
        "expected_fiscal_year": "5000.00",
        "gap": {"fiscal_year": {"baseline_gap": "3000.00", "gap_with_plan": "3000.00"}},
        "cash_cost_in_twelve_months": "966.00",
        "items": items,
    }


UNVALUED = {
    "label": "2 hires",
    "valued": False,
    "note": "hiring is unsupported by this history: not valued",
}
VALUED = {"label": "A programme", "valued": True, "note": None}


def test_a_plan_with_no_valued_item_has_no_change_figures_and_says_why():
    reports = {BASELINE: _report(), "hires-only": _report(_plan([UNVALUED]))}
    row = {r["scenario"]: r for r in comparison_rows(reports, {})}["hires-only"]
    assert row["bookings_change"] is None and row["fiscal_year_gap_change"] is None
    assert row["note"].startswith("no item in this plan is valued: ")
    assert "unsupported by this history" in row["note"]
    assert row["cash_cost_in_twelve_months"] == "966.00"  # the cost stays as it is


def test_a_plan_with_some_valued_items_keeps_its_figures_and_names_what_is_left_out():
    reports = {BASELINE: _report(), "demo-plan": _report(_plan([UNVALUED, VALUED]))}
    row = {r["scenario"]: r for r in comparison_rows(reports, {})}["demo-plan"]
    assert row["bookings_change"] == {REST: "0.00", TWELVE: "0.00"}
    assert row["fiscal_year_gap_change"] == "0.00"
    assert "2 hires" in row["note"] and "leave out" in row["note"]


def test_a_fully_valued_plan_and_the_baseline_have_no_note():
    reports = {BASELINE: _report(), "demo-plan": _report(_plan([VALUED]))}
    rows = {r["scenario"]: r for r in comparison_rows(reports, {})}
    assert rows[BASELINE]["note"] is None and rows["demo-plan"]["note"] is None


def test_mighty_oaks_hires_only_scenario_is_not_a_zero():
    built = gen.build(["mighty-oak-holdings"], draws=100)
    comparison = json.loads(built["mighty-oak-holdings/comparison.json"])
    row = next(r for r in comparison["rows"] if r["scenario"] == "hires-only")
    assert row["bookings_change"] is None and row["fiscal_year_gap_change"] is None
    assert "unsupported by this history" in row["note"]
    demo = next(r for r in comparison["rows"] if r["scenario"] == "demo-plan")
    assert demo["bookings_change"] is not None and "leave out" in demo["note"]

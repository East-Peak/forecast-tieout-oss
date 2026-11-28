"""The lanes for the three demo companies and every scenario: the figures Astra's separately
written reference expects for Sapling's total row, and the reconciliations that must hold."""

from dataclasses import replace
from decimal import Decimal

import pytest

from engine.tieout_core import lanes, lanes_basis, lanes_rules

D = Decimal
ADDITIVE = ("created", "created_arr", "won", "bookings")


def cell(doc, period, path, column):
    p = next(p for p in doc["periods"] if p["key"] == period)
    row = next(r for r in p["rows"] if r["path"] == path)
    return row["cells"][column]


def test_sapling_total_row_for_the_fiscal_year_against_the_reference_figures(built):
    company, _, _, docs = built
    if company != "sapling-industries":
        pytest.skip("the reference figures are Sapling's")
    report, doc = docs["as-signed"]

    def at(col):
        return cell(doc, "FY26", ["total"], col)

    assert (at("created")["actual"], at("created")["goal"][:3]) == ("401.0000", "855")
    assert at("win_rate")["actual"] == "0.2215" and at("win_rate")["goal"] == "0.2035"
    assert at("win_rate")["forecast"] == "0.2193"
    assert at("won")["actual"] == "81.0000"
    assert at("bookings")["actual"] == "29699760.00"
    assert at("bookings")["goal"] == "60000000.00"
    assert at("bookings")["forecast"] == report["gap"]["fiscal_year"]["expected"]
    assert D("765.5") <= D(at("created")["forecast"]) <= D("766.5")
    assert D("151.65") <= D(at("won")["forecast"]) <= D("151.75")
    assert D("366.5e3") <= D(at("avg_won_arr")["actual"]) <= D("367.5e3")
    assert D("382.5e3") <= D(at("avg_won_arr")["forecast"]) <= D("383.5e3")


def test_every_scenario_ties_its_company_bookings_to_the_report_to_the_cent(built):
    _, _, _, docs = built
    for report, doc in docs.values():
        plan = report.get("plan")
        year = (
            plan["expected_fiscal_year"]
            if plan
            else report["gap"]["fiscal_year"]["expected"]
        )
        quarters = (
            [q["expected"] for q in plan["with_plan_quarters"]]
            if plan
            else [q["expected"] for q in report["gap"]["quarters"]]
        )
        assert cell(doc, "FY26", ["total"], "bookings")["forecast"] == year
        for key, expected in zip(("Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"), quarters):
            assert cell(doc, key, ["total"], "bookings")["forecast"] == expected


def test_a_parent_is_the_sum_of_its_children_and_the_year_the_sum_of_its_quarters(
    built,
):
    _, _, _, docs = built
    for _, doc in docs.values():
        for period in doc["periods"]:
            segments = [r for r in period["rows"] if r["path"][0] == "segment"]
            for col in ADDITIVE:
                for mode in ("actual", "forecast", "goal"):
                    parent = cell(doc, period["key"], ["total"], col)[mode]
                    kids = [r["cells"][col][mode] for r in segments]
                    assert D(parent) == sum(D(k) for k in kids), (
                        period["key"],
                        col,
                        mode,
                    )
        for row in doc["periods"][0]["rows"]:
            for col in ADDITIVE:
                for mode in ("actual", "forecast", "goal"):
                    year = D(row["cells"][col][mode])
                    quarters = [
                        D(
                            next(r for r in p["rows"] if r["path"] == row["path"])[
                                "cells"
                            ][col][mode]
                        )
                        for p in doc["periods"][1:]
                    ]
                    assert year == sum(quarters), (row["path"], col, mode)


def test_the_parent_goal_for_a_rate_or_a_size_is_its_summed_numerator_over_its_denominator(
    built,
):
    _, _, _, docs = built
    _, doc = docs["as-signed"]
    for period in doc["periods"]:
        for column in ("avg_won_arr", "cycle"):
            parts = [
                r["cells"][column]["parts"]["goal"]
                for r in period["rows"]
                if r["path"][0] == "segment"
            ]
            total = cell(doc, period["key"], ["total"], column)["parts"]["goal"]
            assert D(total["numerator"]) == sum(D(p["numerator"]) for p in parts)
            assert D(total["denominator"]) == sum(D(p["denominator"]) for p in parts)
            assert D(cell(doc, period["key"], ["total"], column)["goal"]) == (
                D(total["numerator"]) / D(total["denominator"])
            ).quantize(D(1).scaleb(-lanes_rules.COLUMN[column].places))


def test_won_and_bookings_split_into_carried_in_and_created_in_the_period(built):
    _, _, _, docs = built
    for _, doc in docs.values():
        for period in doc["periods"]:
            for row in period["rows"]:
                for col in ("won", "bookings"):
                    c = row["cells"][col]
                    for mode in ("actual", "forecast"):
                        s = c["split"][mode]
                        assert D(s["carried_in"]) + D(s["created_in_period"]) == D(
                            c[mode]
                        )


def test_goals_are_the_same_in_every_scenario_so_a_plan_cannot_move_them(built):
    _, _, _, docs = built

    def goals(doc):
        return [
            (p["key"], r["path"], col, c["goal"], c["parts"] and c["parts"]["goal"])
            for p in doc["periods"]
            for r in p["rows"]
            for col, c in r["cells"].items()
        ]

    reference = goals(docs["as-signed"][1])
    for _, doc in docs.values():
        assert goals(doc) == reference


def test_the_opening_stock_has_no_status_and_says_why(built):
    _, _, _, docs = built
    _, doc = docs["as-signed"]
    c = cell(doc, "FY26", ["total"], "open")
    assert (c["status"], c["none_because"]) == ("none", "vacuous")
    assert c["actual"] == c["forecast"] and c["goal"] is not None
    assert cell(doc, "Q4FY26", ["total"], "open")["forecast"] is None
    assert cell(doc, "Q4FY26", ["total"], "open")["none_because"] == "vacuous"


def test_a_ratio_on_too_few_observations_has_no_status_and_exposes_its_denominator(
    built,
):
    _, _, _, docs = built
    _, doc = docs["as-signed"]
    for period in doc["periods"]:
        for row in period["rows"]:
            for col in ("win_rate", "cycle", "avg_won_arr"):
                c = row["cells"][col]
                if (
                    c["denominator"] is not None
                    and D(c["denominator"]) < lanes_rules.COLUMN[col].minimum
                ):
                    assert c["none_because"] == "too_few", (
                        period["key"],
                        row["path"],
                        col,
                    )


def test_the_marker_is_on_total_bookings_only_and_only_for_a_period_with_a_range(built):
    _, _, _, docs = built
    report, doc = docs["as-signed"]
    fy = cell(doc, "FY26", ["total"], "bookings")
    assert fy["range80"] == report["gap"]["fiscal_year"]["expected_range80"]
    lo, hi = (D(x) for x in fy["range80"])
    assert fy["goal_inside_range80"] == (lo <= D(fy["goal"]) <= hi)
    assert cell(doc, "Q1FY26", ["total"], "bookings")["range80"] is None
    assert all(
        r["cells"]["bookings"]["range80"] is None
        for p in doc["periods"]
        for r in p["rows"]
        if r["path"] != ["total"]
    )


def test_the_builders_own_reconciliations_all_pass(built):
    _, _, _, docs = built
    for _, doc in docs.values():
        assert doc["checks"] and all(c["passed"] for c in doc["checks"]), [
            c for c in doc["checks"] if not c["passed"]
        ]


def test_a_blank_segment_is_a_lane_of_its_own_and_the_company_row_still_adds_up(built):
    company, state, _, docs = built
    if company != "sprout-labs":
        pytest.skip("one company is enough")
    pop = replace(
        state.pop,
        deals=tuple(
            replace(d, segment="") if i % 7 == 0 else d
            for i, d in enumerate(state.pop.deals)
        ),
    )
    blank = replace(state, pop=pop, ground=replace(state.ground, pop=pop))
    changed = lanes_basis.plan_basis(blank)
    report, _ = docs["as-signed"]
    doc = lanes.lanes_document(
        blank, changed, report, (), (), company, "as-signed", "x"
    )
    paths = [r["path"] for r in doc["periods"][0]["rows"]]
    assert ["segment", "unassigned"] in paths
    assert paths[0] == ["total"]
    total = D(cell(doc, "FY26", ["total"], "won")["actual"])
    assert total == sum(
        D(cell(doc, "FY26", p, "won")["actual"]) for p in paths if p[0] == "segment"
    )

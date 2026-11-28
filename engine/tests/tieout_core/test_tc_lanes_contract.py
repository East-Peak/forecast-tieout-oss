"""The lanes contract: every generated file satisfies it, and each rule a schema cannot say
catches the tampering it exists for."""

import copy
import json

import pytest

from engine.tieout_core import lanes, lanes_basis, lanes_contract
from engine.tieout_core.editor import canonical


@pytest.fixture
def parts(built):
    company, _, basis, docs = built
    report, doc = docs["demo-plan"]
    basis_doc = lanes_basis.document(basis, company)
    doc = copy.deepcopy(doc)
    doc["plan_basis"]["digest"] = lanes_contract.digest(basis_doc)
    return doc, basis_doc, report


def test_every_generated_file_satisfies_the_contract(built):
    company, _, basis, docs = built
    basis_doc = lanes_basis.document(basis, company)
    assert lanes_contract.validate_basis(basis_doc) == []
    for report, doc in docs.values():
        doc = copy.deepcopy(doc)
        doc["plan_basis"]["digest"] = lanes_contract.digest(basis_doc)
        assert lanes_contract.validate(doc, basis_doc, report) == []


def test_the_schemas_are_json_and_versioned():
    for schema in (lanes_contract.schema(), lanes_contract.basis_schema()):
        assert lanes_contract.SCHEMA_VERSION in schema["$id"]
        json.dumps(schema)
    assert lanes_contract.schema_text(lanes_contract.schema()).endswith("}\n")


def problems(parts, edit):
    doc, basis_doc, report = copy.deepcopy(parts)
    edit(doc, basis_doc, report)
    return lanes_contract.validate(doc, basis_doc, report)


def total(doc, period, column):
    return doc["periods"][period]["rows"][0]["cells"][column]


def test_an_unknown_key_or_a_malformed_figure_fails_the_schema(parts):
    def stray(doc, *_):
        total(doc, 0, "won")["extra"] = 1

    def malformed(doc, *_):
        total(doc, 0, "won")["actual"] = "81 deals"

    assert problems(parts, stray) and problems(parts, malformed)


def test_a_parent_that_is_not_the_sum_of_its_children_is_found(parts):
    def edit(doc, *_):
        total(doc, 1, "created")["forecast"] = "9999.0000"

    assert any("created" in p for p in problems(parts, edit))


def test_a_year_that_is_not_the_sum_of_its_quarters_is_found(parts):
    def edit(doc, *_):
        for row in doc["periods"][0]["rows"]:
            row["cells"]["created_arr"]["goal"] = "1.00"

    assert any("quarters" in p for p in problems(parts, edit))


def test_a_status_that_the_figures_do_not_give_is_found(parts):
    def edit(doc, *_):
        c = total(doc, 0, "bookings")
        c["status"] = "behind" if c["status"] == "on_track" else "on_track"

    assert any("status" in p for p in problems(parts, edit))


def test_a_ratio_that_is_not_its_numerator_over_its_denominator_is_found(parts):
    def edit(doc, *_):
        total(doc, 0, "avg_won_arr")["actual"] = "1.00"

    assert any("avg_won_arr" in p for p in problems(parts, edit))


def test_a_goal_that_is_not_the_frozen_basis_is_found(parts):
    def edit(doc, *_):
        for p in doc["periods"]:
            for row in p["rows"]:
                row["cells"]["bookings"]["goal"] = "1.00"

    assert any("basis" in p for p in problems(parts, edit))


def test_a_basis_that_is_not_the_one_the_lanes_name_is_found(parts):
    def edit(doc, basis_doc, _):
        basis_doc["label"] = "something else"

    assert any("digest" in p for p in problems(parts, edit))


def test_company_bookings_that_differ_from_the_report_by_a_cent_are_found(parts):
    def edit(doc, basis_doc, report):
        report["plan"]["expected_fiscal_year"] = "1.00"

    assert any("report" in p for p in problems(parts, edit))


def test_a_won_split_that_does_not_add_up_is_found(parts):
    def edit(doc, *_):
        total(doc, 0, "won")["split"]["actual"]["carried_in"] = "0.5000"

    assert any("split" in p for p in problems(parts, edit))


def test_the_basis_must_share_each_target_exactly_and_pass_its_checks(built):
    company, _, basis, _ = built
    doc = lanes_basis.document(basis, company)
    doc["goals"]["Q1FY26"][doc["segments"][0]["key"]]["bookings"] = "1.00"
    assert any("target" in p for p in lanes_contract.validate_basis(doc))
    doc = lanes_basis.document(basis, company)
    doc["checks"][0]["passed"] = False
    assert any("check" in p for p in lanes_contract.validate_basis(doc))


def test_the_unavailable_shape_is_a_shape_of_its_own():
    doc = {
        "schema_version": lanes_contract.SCHEMA_VERSION,
        "company": "x",
        "scenario": "as-signed",
        "unavailable": "the plan-start forecast is unavailable: no timing",
    }
    assert lanes_contract.validate(doc, None, {}) == []
    assert lanes_contract.validate({**doc, "unavailable": 3}, None, {})
    assert canonical(doc)
    made = lanes.unavailable_document("x", "as-signed", doc["unavailable"])
    assert made == doc and lanes_contract.validate(made, None, {}) == []


def test_owner_goals_that_do_not_add_to_the_segments_goal_or_an_opening_that_does_not_are_found(
    built,
):
    company, _, basis, _ = built
    doc = lanes_basis.document(basis, company)
    seg = doc["segments"][0]["key"]
    doc["owner_goals"]["Q1FY26"][seg]["unassigned"]["bookings"] = "1.00"
    assert any("owner goals" in p for p in lanes_contract.validate_basis(doc))
    doc = lanes_basis.document(basis, company)
    next(o for o in doc["owners"] if o["segment"] == seg)["opening"] += 1
    assert any("opening" in p for p in lanes_contract.validate_basis(doc))
    doc = lanes_basis.document(basis, company)
    next(o for o in doc["owners"] if o["segment"] == seg)["share"] = "0.999999"
    assert any("share" in p for p in lanes_contract.validate_basis(doc))

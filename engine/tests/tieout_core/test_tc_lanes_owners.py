"""Owner rows: beneath each segment, adding to it in every figure and mode, volumes only."""

from decimal import Decimal

import pytest

from engine.tests.tieout_core.lanes_support import mutated
from engine.tieout_core import lanes, lanes_basis, lanes_rules

D = Decimal
ADDITIVE = ("created", "created_arr", "won", "bookings")
MODES = ("actual", "forecast", "goal")


def segments(period):
    return [r for r in period["rows"] if len(r["path"]) == 2 and r["path"][0] == "segment"]  # fmt: skip


def owners(period, seg):
    return [r for r in period["rows"] if r["path"][:2] == ["segment", seg] and len(r["path"]) == 4]  # fmt: skip


def figure(row, col, mode):
    v = row["cells"][col][mode]
    return None if v is None else D(v)


def total(rows, col, mode):
    return sum((figure(r, col, mode) or 0 for r in rows), D(0))


def assert_owners_reconcile(doc):
    """Every additive cell, in every mode and every period, and each part of a split."""
    for p in doc["periods"]:
        for seg in segments(p):
            kids = owners(p, seg["path"][1])
            assert kids, (p["key"], seg["path"])
            for col in ("open", *ADDITIVE):
                for mode in MODES:
                    if figure(seg, col, mode) is None:
                        assert all(figure(k, col, mode) is None for k in kids)
                    else:
                        assert total(kids, col, mode) == figure(seg, col, mode), (
                            p["key"],
                            seg["path"],
                            col,
                            mode,
                        )
            for col in ("won", "bookings"):
                for mode in ("actual", "forecast"):
                    for part in ("carried_in", "created_in_period"):
                        assert sum(
                            (D(k["cells"][col]["split"][mode][part]) for k in kids),
                            D(0),
                        ) == D(seg["cells"][col]["split"][mode][part])
            for col in lanes_rules.RATIO_COLUMNS:
                for key in ("numerator", "denominator"):
                    assert sum(
                        (D(k["cells"][col]["parts"]["actual"][key]) for k in kids),
                        D(0),
                    ) == D(seg["cells"][col]["parts"]["actual"][key])


def test_every_segment_has_owner_rows_beneath_it_and_the_rows_are_in_one_order(built):
    _, _, _, docs = built
    for _, doc in docs.values():
        first = [r["path"] for r in doc["periods"][0]["rows"]]
        assert first[0] == ["total"]
        for p in doc["periods"]:
            assert [r["path"] for r in p["rows"]] == first
        for r in doc["periods"][0]["rows"]:
            if len(r["path"]) == 4:
                assert r["parent"] == r["path"][:2]
                assert r["path"][2] == "owner"
        assert any(len(p) == 4 for p in first)


def test_owners_add_to_their_segment_in_every_figure_and_every_mode(built):
    _, _, _, docs = built
    for _, doc in docs.values():
        assert_owners_reconcile(doc)


def test_an_owner_is_shown_in_volumes_only_with_the_actual_of_a_rate_and_no_comparison(
    built,
):
    _, _, _, docs = built
    _, doc = docs["as-signed"]
    for p in doc["periods"]:
        for seg in segments(p):
            for row in owners(p, seg["path"][1]):
                for col in lanes_rules.RATIO_COLUMNS:
                    c = row["cells"][col]
                    assert c["status"] == "none"
                    assert c["none_because"] == "not_compared_at_owner"
                    assert c["goal"] is None and c["forecast"] is None
                    assert c["parts"]["actual"] is not None
                    assert c["parts"]["forecast"] is None and c["parts"]["goal"] is None
                for col in ("created", "created_arr", "won", "bookings"):
                    c = row["cells"][col]
                    if c["goal"] is None:
                        assert (c["status"], c["none_because"]) == ("none", "not_allocated")  # fmt: skip


def test_owner_goals_are_the_bases_and_the_same_in_every_scenario(built):
    company, _, b, docs = built
    basis_doc = lanes_basis.document(b, company)
    for _, doc in docs.values():
        for p in doc["periods"][1:]:
            for seg in segments(p):
                for row in owners(p, seg["path"][1]):
                    mine = (
                        basis_doc["owner_goals"][p["key"]]
                        .get(seg["path"][1], {})
                        .get(row["path"][3])
                    )
                    got = row["cells"]["bookings"]["goal"]
                    assert got == (mine["bookings"] if mine else None)


def test_sapling_largest_segment_orders_owners_by_goal_without_arithmetic(built):
    company, _, _, docs = built
    if company != "sapling-industries":
        pytest.skip("Sapling's figures")
    _, doc = docs["as-signed"]
    year = doc["periods"][0]
    seg = segments(year)[0]  # the largest bookings goal first
    rows = owners(year, seg["path"][1])
    ranks = [r["rank"] for r in rows]
    assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)
    goals = [figure(r, "bookings", "goal") for r in rows if r["kind"] == "owner"]
    known = [g for g in goals if g is not None]
    assert known == sorted(known, reverse=True)
    kinds = [("owner", "unassigned", "programs", "planned_hires").index(r["kind"]) for r in rows]  # fmt: skip
    assert kinds == sorted(kinds)


def test_guardrail_wording_says_allocated_production_is_not_measured_performance(built):
    _, _, _, docs = built
    _, doc = docs["demo-plan"]
    assert lanes.OWNER_CAVEAT in doc["caveats"]
    assert "never a measure of a person" in lanes.OWNER_CAVEAT
    for p in doc["periods"][:1]:
        for r in p["rows"]:
            if len(r["path"]) == 4 and r["kind"] == "owner":
                assert "allocat" in r["allocation"].lower()


def test_the_builders_checks_include_the_owner_ones_and_all_pass(built):
    _, _, _, docs = built
    for _, doc in docs.values():
        names = [c["name"] for c in doc["checks"]]
        assert "owner creation adds to the segment's" in names
        assert all(c["passed"] for c in doc["checks"])


# ---- inputs that change what a lane holds: reconciled in the forecast, and the contract passes


def ids_in(rows, segment):
    return [r["id"] for r in rows if r["segment"] == segment]


def check_mutation(doc, problems):
    assert problems == []
    assert all(c["passed"] for c in doc["checks"]), doc["checks"]
    assert_owners_reconcile(doc)


def test_a_blank_owner_becomes_an_unassigned_row_that_reconciles_in_every_mode(
    tmp_path,
):
    def blank(rows):
        for i, r in enumerate(rows):
            if i % 5 == 0:
                r["owner_id"] = r["owner"] = ""

    doc, _, problems = mutated("sprout-labs", tmp_path, deals=blank)
    check_mutation(doc, problems)
    paths = [r["path"] for r in doc["periods"][0]["rows"]]
    assert any(p[3] == "unassigned" for p in paths if len(p) == 4)


def test_someone_hired_after_the_plan_date_has_no_goal_and_says_why(tmp_path):
    def hire(rows):
        new = dict(rows[0], id="AE-900", name="Late Hire", start_date="2026-05-01", end_date="", is_active="true", annual_quota="1000000")  # fmt: skip
        return [*rows, new]

    def reassign(rows):
        n = 0
        for r in rows:
            if r["created_date"] > "2026-03-01" and n < 6:
                r["owner_id"], r["owner"] = "AE-900", "Late Hire"
                n += 1

    doc, basis_doc, problems = mutated(
        "sprout-labs", tmp_path, deals=reassign, team=hire
    )
    check_mutation(doc, problems)
    rows = [r for r in doc["periods"][0]["rows"] if r["path"][-1:] == ["AE-900"]]
    assert rows
    for r in rows:
        c = r["cells"]["bookings"]
        assert c["goal"] is None and c["status"] == "none"
        assert c["none_because"] == "not_allocated"
    assert not any(o["id"] == "AE-900" for o in basis_doc["owners"])


def test_an_owner_with_zero_quota_has_a_zero_goal_and_no_status(tmp_path):
    def zero(rows):
        for r in rows:
            if r["id"] == "AE-001":
                r["annual_quota"] = "0"

    doc, _, problems = mutated("sprout-labs", tmp_path, team=zero)
    check_mutation(doc, problems)
    row = next(r for r in doc["periods"][0]["rows"] if r["path"][-1:] == ["AE-001"])
    c = row["cells"]["bookings"]
    assert (c["goal"], c["status"], c["none_because"]) == ("0.00", "none", "no_goal")


def test_a_segment_with_a_single_owner_gives_that_owner_the_whole_goal(tmp_path):
    def only(rows):
        mine = [r for r in rows if r["segment"] == "mid_market" and r["role"] == "ae"]
        return [r for r in rows if r not in mine[1:]]

    doc, _, problems = mutated("sprout-labs", tmp_path, team=only)
    check_mutation(doc, problems)
    year = doc["periods"][0]
    seg = next(s for s in segments(year) if s["path"][1] == "mid_market")
    kids = owners(year, "mid_market")
    holders = [r for r in kids if figure(r, "bookings", "goal")]
    assert len(holders) == 1 and holders[0]["kind"] == "owner"
    assert figure(holders[0], "bookings", "goal") == figure(seg, "bookings", "goal")


def test_an_adopted_roster_forecast_reconciles_owner_by_owner_with_a_planned_hire(
    built,
):
    company, _, _, docs = built
    if company != "sapling-industries":
        pytest.skip("Sapling adopts the capacity term")
    _, doc = docs["hires-only"]
    kinds = {r["kind"] for p in doc["periods"] for r in p["rows"]}
    assert "planned_hires" in kinds
    assert_owners_reconcile(doc)

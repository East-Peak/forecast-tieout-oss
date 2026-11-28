"""The reconstructed plan basis: what a refit on the day before the year started freezes."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import fit, lanes, lanes_contract
from engine.tieout_core import lanes_basis as basis
from engine.tieout_core.editor import canonical
from engine.tieout_core.records import Deal
from engine.tieout_core.report import prepare

D = Decimal
DAY = date(2026, 1, 31)


def won(i, segment, arr, closed=date(2025, 9, 1)):
    return Deal(
        i,
        f"w{i}",
        "new_business",
        segment,
        "Won",
        D(arr),
        date(2025, 3, 1),
        closed,
        True,
        True,
    )


def test_a_segment_with_enough_wins_is_priced_at_its_own_mean_and_a_thin_one_at_the_pooled():
    deals = [won(i, "a", 100 + i) for i in range(10)] + [
        won(20 + i, "b", 999) for i in range(9)
    ]
    got = basis.segment_sizes(deals, {d.id: d.arr for d in deals}, DAY, D(7), D(70))
    assert got["a"] == basis.Sizes(
        D("104.5"), "segment mean", D("104.5"), "segment mean"
    )
    assert got["b"].won == D(7) and got["b"].won_basis == "pooled, thin sample"
    assert got["b"].created == D(70) and got["b"].created_basis == "pooled, thin sample"


def test_only_wins_in_the_trailing_year_count_and_a_missing_first_amount_is_not_a_zero():
    old = [won(i, "a", 5000, date(2024, 1, 1)) for i in range(10)]
    got = basis.segment_sizes(old, {}, DAY, D(7), D(70))
    assert got["a"].won == D(7)
    recent = [won(i, "a", 10) for i in range(10)]
    amounts = {d.id: (None if d.row < 5 else D(30)) for d in recent}
    assert basis.segment_sizes(recent, amounts, DAY, D(7), D(70))["a"].created == D(70)


def test_goals_share_the_target_by_trailing_bookings_and_each_figure_adds_to_its_total():
    sizes = {
        "a": basis.Sizes(D(100), "", D(10), ""),
        "b": basis.Sizes(D(200), "", D(20), ""),
    }
    got = basis.split_goals(D(1000), {"a": D(60), "b": D(40)}, sizes, D(8), D(100))
    assert got["a"] == basis.Goal(
        D("600.00"), D("6.0000"), D("6.0000"), D("60.00"), D("600.00")
    )
    assert got["b"] == basis.Goal(
        D("400.00"), D("2.0000"), D("2.0000"), D("40.00"), D("200.00")
    )
    odd = basis.split_goals(
        D("10.00"),
        {"a": D(1), "b": D(1), "c": D(1)},
        {k: sizes["a"] for k in "abc"},
        D("10"),
        D(30),
    )
    assert sum(g.bookings for g in odd.values()) == D("10.00")
    assert sum(g.created for g in odd.values()) == D("10.0000")


@pytest.fixture(scope="module", params=gen.COMPANIES)
def frozen(request):
    company = request.param
    with gen.in_repo():
        state = prepare(gen.PROFILES / company, gen.DATA / company, gen.AS_OF, 200, 0)
        yield company, state, basis.plan_basis(state)


def test_the_basis_is_dated_the_day_before_the_year_and_labeled_a_reconstruction(
    frozen,
):
    _, _, b = frozen
    assert b.cutoff == date(2026, 1, 31)
    assert b.label == "Reconstructed FY plan basis, 2026-01-31"
    assert b.capacity_decision == "not shown"


def test_segment_goals_add_to_the_entered_targets_exactly(frozen):
    _, state, b = frozen
    for q, target in state.profile.quarterly_targets.items():
        assert sum(g.bookings for (qq, _), g in b.goals.items() if qq == q) == target


def test_the_schedule_is_shown_beside_the_targets(frozen):
    company, state, b = frozen
    assert [s.quarter for s in b.schedule] == list(
        state.profile.fiscal_year.quarter_keys
    )
    assert all(s.bookings > 0 for s in b.schedule)
    if company == "sapling-industries":
        total = sum(s.bookings for s in b.schedule)
        assert D("69.5e6") < total < D("70.1e6")  # the report's "about $69.8M"


def test_every_check_of_the_basis_passes(frozen):
    _, _, b = frozen
    assert b.checks and all(c.passed for c in b.checks), [
        c for c in b.checks if not c.passed
    ]


def test_the_basis_uses_nothing_that_was_not_known_on_the_plan_date(built):
    """Drop what was created after the plan date, change what closed after it, and hand the
    basis the other estimator than the report chose: the file must not move by a byte."""
    company, state, basis, _ = built
    after = [d for d in state.pop.deals if d.created > basis.cutoff]
    assert after, "the demo companies have deals created after the plan date"
    kept = {d.id for d in state.pop.deals if d.created <= basis.cutoff}
    deals = tuple(
        replace(d, arr=d.arr * 3, close=d.close + timedelta(days=30))
        if d.is_closed and d.close > basis.cutoff
        else d
        for d in state.pop.deals
        if d.id in kept
    )
    pop = replace(
        state.pop,
        deals=deals,
        transitions=tuple(t for t in state.pop.transitions if t.deal_id in kept),
    )
    other = fit.MATURED if state.params.estimator == fit.RECENCY else fit.RECENCY
    changed = replace(
        state,
        pop=pop,
        params=replace(state.params, estimator=other),
        ground=replace(state.ground, pop=pop),
    )
    assert canonical(basis_doc(changed, company)) == canonical(
        basis_doc(state, company)
    )


def basis_doc(state, company):
    return basis.document(basis.plan_basis(state), company)


def test_a_quarter_with_no_target_shares_its_created_deals_by_trailing_bookings():
    sizes = {"a": basis.Sizes(D(100), "", D(10), ""), "b": basis.Sizes(D(200), "", D(20), "")}  # fmt: skip
    got = basis.split_goals(D(0), {"a": D(60), "b": D(40)}, sizes, D(10), D(100))
    assert [g.created for g in got.values()] == [D("6.0000"), D("4.0000")]
    assert all(g.bookings == 0 and g.won == 0 for g in got.values())


def test_full_generation_survives_a_zero_quarterly_target(built):
    company, state, _, docs = built
    if company != "sprout-labs":
        pytest.skip("one company is enough")
    targets = {**state.profile.quarterly_targets, "Q2FY26": D(0)}
    zero = replace(state, profile=replace(state.profile, quarterly_targets=targets))
    b = basis.plan_basis(zero)
    assert lanes_contract.validate_basis(basis.document(b, company)) == []
    assert sum(g.created for (q, _), g in b.goals.items() if q == "Q2FY26") == (
        next(s for s in b.schedule if s.quarter == "Q2FY26").created.quantize(
            D("0.0001")
        )
    )
    report, _ = docs["as-signed"]
    doc = lanes.lanes_document(zero, b, report, (), (), company, "as-signed", "x")
    assert all(c["passed"] for c in doc["checks"])
    cell = doc["periods"][2]["rows"][0]["cells"]["bookings"]
    assert (cell["goal"], cell["none_because"]) == ("0.00", "no_goal")

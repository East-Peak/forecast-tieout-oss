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


FIGURES = ("bookings", "won", "created", "created_arr", "days")


def test_owner_goals_add_to_their_segments_goal_to_the_last_unit_and_openings_add_too(
    frozen,
):
    _, _, b = frozen
    for (q, seg), goal in b.goals.items():
        mine = [g for (qq, s, _), g in b.owner_goals.items() if (qq, s) == (q, seg)]
        for figure in FIGURES:
            assert sum(getattr(g, figure) for g in mine) == getattr(goal, figure)
    for s in b.segments:
        assert sum(o.opening for o in b.owners if o.segment == s.key) == s.opening


def test_every_segment_has_an_unassigned_owner_and_only_roster_people_have_a_share(
    frozen,
):
    _, state, b = frozen
    on_roster = {m.id for m in state.cap.members if m.start <= b.cutoff}
    for s in b.segments:
        mine = {o.id: o for o in b.owners if o.segment == s.key}
        assert "unassigned" in mine and mine["unassigned"].allocated
        assert abs(sum(o.share for o in mine.values()) - 1) <= D("0.000001")
    for o in b.owners:
        if o.id not in on_roster and o.id != "unassigned":
            assert not o.allocated and o.share == 0


def test_nobody_hired_after_the_plan_date_has_an_allocation(frozen):
    _, state, b = frozen
    later = {m.id for m in state.cap.members if m.start > b.cutoff}
    assert later or state.cap.members
    assert not any(o.allocated and o.id in later for o in b.owners)
    assert not any(o in later for _, _, o in b.owner_goals)


def test_a_hire_a_departure_or_a_deal_dated_after_the_plan_date_cannot_move_an_owner_goal(
    built,
):
    """Hire someone after the plan date, move a departure to after it, give deals created after it
    to the new hire: the basis file must not move by a byte. This is all it proves: quota,
    roster segment and a deal's owner have no history in the files, so they are today's values
    (see the test below), and only employment dates and deal data are cut at the plan date."""
    company, state, b, _ = built
    doc = basis.document(b, company)
    assert doc["owners"] and doc["owner_goals"]
    cap = state.cap
    people = list(cap.members)
    extra = replace(people[0], id="LATE-1", start=b.cutoff + timedelta(days=30))
    left = next((m for m in people if m.end is None), people[0])
    people = [replace(m, end=date(2026, 12, 1)) if m is left else m for m in people]
    pop = replace(
        state.pop,
        deals=tuple(
            replace(d, owner_id="LATE-1") if d.created > b.cutoff else d
            for d in state.pop.deals
        ),
    )
    roster = replace(cap.roster, members=(*people, extra))
    changed = replace(
        state,
        pop=pop,
        cap=replace(cap, roster=roster),
        ground=replace(state.ground, pop=pop),
    )
    assert canonical(basis_doc(changed, company)) == canonical(doc)


def test_a_quota_edit_in_todays_roster_does_move_the_goal_and_the_file_says_so(built):
    """The known limit, pinned: quota is today's value standing in for the plan date, so doubling
    a rep's quota in the roster file changes their allocated goal."""
    company, state, b, _ = built
    doc = basis.document(b, company)
    rep = next(o for o in b.owners if o.allocated and o.quota)
    people = tuple(
        replace(m, annual_quota=m.annual_quota * 2) if m.id == rep.id else m
        for m in state.cap.members
    )
    edited = replace(state, cap=replace(state.cap, roster=replace(state.cap.roster, members=people)))  # fmt: skip
    moved = basis_doc(edited, company)
    assert canonical(moved) != canonical(doc)
    assert "today's" in doc["owner_caveat"] and "quota" in doc["owner_caveat"]
    assert "roster segment" in doc["owner_caveat"]


def test_the_basis_records_each_owners_inputs_so_a_goal_can_be_traced(frozen):
    _, _, b = frozen
    for o in b.owners:
        if o.allocated and o.id != "unassigned":
            assert o.weight == (o.quota or D(0)) * o.days
    doc = basis.document(b, "x")
    row = next(o for o in doc["owners"] if o["quota"])
    assert set(row) >= {"segment", "quota", "days", "weight", "share"}

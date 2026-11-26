import math
from collections import defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from engine.scripts.synth_history import Company, Staffing, generate, true_win_rates

BASE = Company(
    slug="test-co", prefix="T", start=date(2023, 12, 1), as_of=date(2026, 6, 30), seed=11,
    deals_per_month=30, advance=(0.6, 0.7, 0.75, 0.8, 0.9), dwell_days=(15, 20, 20, 15, 10),
)  # fmt: skip


@pytest.fixture(scope="module")
def company():
    return generate(BASE)


def test_same_seed_same_data():
    assert generate(BASE) == generate(BASE)
    assert generate(replace(BASE, seed=12)) != generate(BASE)


def test_nothing_is_dated_after_the_as_of(company):
    d = company.dataset
    assert max(x.created for x in d.deals) <= BASE.as_of
    assert max(x.close for x in d.deals if x.is_closed) <= BASE.as_of
    assert max(t.on for t in d.transitions) <= BASE.as_of
    assert max(o.on for o in d.observations) <= BASE.as_of


def test_close_date_is_the_final_stage_transition(company):
    last = {}
    for t in company.dataset.transitions:
        last[t.deal_id] = t
    for x in company.dataset.deals:
        if x.is_closed:
            assert (last[x.id].on, last[x.id].stage) == (x.close, x.stage)
        else:
            assert last[x.id].stage not in ("Won", "Lost")


def test_open_deals_carry_their_latest_observation(company):
    latest = {}
    for o in company.dataset.observations:
        latest[o.deal_id] = o
    for x in company.dataset.deals:
        if not x.is_closed:
            assert (x.arr, x.close) == (
                latest[x.id].amount,
                latest[x.id].expected_close,
            )


def test_closed_deals_book_their_last_observed_amount(company):
    latest = {}
    for o in company.dataset.observations:
        latest[o.deal_id] = o
    assert all(
        x.arr == latest[x.id].amount for x in company.dataset.deals if x.is_closed
    )


def test_history_spans_at_least_thirty_months(company):
    first = min(x.created for x in company.dataset.deals)
    months = (BASE.as_of.year - first.year) * 12 + BASE.as_of.month - first.month
    assert months >= 30


def test_money_is_whole_dollars(company):
    assert all(x.arr == x.arr.to_integral_value() for x in company.dataset.deals)


def test_true_win_rates_are_products_of_advance_probabilities():
    rates = true_win_rates(BASE)
    assert rates["S5"] == pytest.approx(0.9)
    assert rates["S1"] == pytest.approx(0.6 * 0.7 * 0.75 * 0.8 * 0.9)


def test_awkward_knobs_show_up_in_the_data():
    awkward = generate(
        replace(
            BASE,
            big_deal_share=0.03,
            slip_share=0.5,
            missing_history_share=0.1,
            conversion_change=(date(2025, 8, 1), 0.6),
        )
    )
    with_history = {t.deal_id for t in awkward.dataset.transitions}
    assert sum(1 for x in awkward.dataset.deals if x.id not in with_history) > 0
    arrs = sorted(x.arr for x in awkward.dataset.deals)
    assert arrs[-1] > 5 * arrs[len(arrs) // 2]
    expected = defaultdict(set)
    for o in awkward.dataset.observations:
        expected[o.deal_id].add(o.expected_close)
    assert sum(1 for v in expected.values() if len(v) > 2) > 0  # close dates that moved


def test_other_motions_are_won_rows_of_their_type():
    other = generate(replace(BASE, other_motions=(("expansion", 4, 50_000),)))
    exp = [x for x in other.dataset.deals if x.type == "expansion"]
    assert exp and all(x.is_won for x in exp)
    assert all(x.type == "new_business" for x in generate(BASE).dataset.deals)


def test_amounts_are_decimals(company):
    assert all(isinstance(x.arr, Decimal) for x in company.dataset.deals)


# ---------------------------------------------------------------- staffing
# Goal 2A step 1: pipeline creation depends on people. Created deals come
# partly from ramped AEs and partly from demand that ignores headcount.

STAFFED = replace(
    BASE,
    staffing=Staffing(
        headcount=((date(2023, 12, 1), 4), (date(2025, 1, 1), 8), (date(2026, 1, 1), 12)),
        monthly_attrition=0.03,
        deals_per_ramped_ae_month=3.0,
        ramp_months=4,
        demand_deals_per_month=10.0,
        annual_quota=(("mid_market", 900_000),),
        other_roles=(("manager", 1), ("sdr", 2)),
    ),
)  # fmt: skip


@pytest.fixture(scope="module")
def staffed():
    return generate(STAFFED)


def _employed(rep, on):
    return rep.start <= on and (rep.end is None or on <= rep.end)


def test_every_deal_is_owned_by_an_ae_employed_on_its_creation_date(staffed):
    reps = {r.id: r for r in staffed.roster}
    assert len(staffed.owners) == len(staffed.dataset.deals)
    for d in staffed.dataset.deals:
        rep = reps[staffed.owners[d.id]]
        assert rep.role == "ae"
        assert _employed(rep, d.created), (d.id, d.created, rep)


def test_reps_start_and_leave_across_the_history(staffed):
    aes = [r for r in staffed.roster if r.role == "ae"]
    assert sum(1 for r in aes if STAFFED.start <= r.start <= STAFFED.as_of) >= 8
    assert any(r.end is not None for r in aes)
    assert all(r.end is None or r.start <= r.end <= STAFFED.as_of for r in aes)
    assert all(r.start <= STAFFED.as_of for r in staffed.roster)
    roles = {r.role for r in staffed.roster}
    assert roles == {"ae", "manager", "sdr"}


def test_heads_track_the_headcount_plan(staffed):
    aes = [r for r in staffed.roster if r.role == "ae"]
    for on, planned in ((date(2024, 6, 15), 4), (date(2025, 6, 15), 8), (date(2026, 6, 15), 12)):  # fmt: skip
        heads = sum(_employed(r, on) for r in aes)
        assert planned - 2 <= heads <= planned, (on, heads)


def test_creation_is_split_between_reps_and_demand(staffed):
    origins = staffed.origins
    assert set(origins.values()) == {"rep", "demand"}
    rep_made = [d for d in staffed.dataset.deals if origins[d.id] == "rep"]
    # A rep-made deal belongs to the rep who made it, in that rep's segment.
    reps = {r.id: r for r in staffed.roster}
    assert all(d.segment == reps[staffed.owners[d.id]].segment for d in rep_made)


def test_more_ramped_reps_create_more_deals_and_demand_alone_does_not_respond():
    def created(staffing):
        g = generate(replace(BASE, staffing=staffing))
        return sum(1 for d in g.dataset.deals if d.created >= date(2026, 1, 1))

    s = STAFFED.staffing
    bigger = replace(s, headcount=s.headcount[:-1] + ((date(2026, 1, 1), 24),))
    assert created(bigger) > 1.3 * created(s)
    demand_only = replace(s, deals_per_ramped_ae_month=0.0)
    demand_bigger = replace(bigger, deals_per_ramped_ae_month=0.0)
    a, b = created(demand_only), created(demand_bigger)
    assert abs(a - b) <= 4 * math.sqrt(a)  # same demand process, headcount ignored


def test_ramp_lowers_a_new_hire_s_output():
    s = replace(STAFFED.staffing, demand_deals_per_month=0.0, monthly_attrition=0.0)
    g = generate(replace(BASE, staffing=s, seed=5))
    reps = {r.id: r for r in g.roster}
    first, later = 0, 0
    for d in g.dataset.deals:
        tenure = (d.created - reps[g.owners[d.id]].start).days
        if 0 <= tenure < 30:
            first += 1
        elif 180 <= tenure < 210:
            later += 1
    assert first < 0.5 * later


def test_quotas_are_full_ramp_figures_for_aes_only(staffed):
    for r in staffed.roster:
        if r.role == "ae":
            assert r.annual_quota == Decimal(900_000)
        else:
            assert r.annual_quota is None


def test_staffed_generation_is_deterministic_and_dated_by_the_as_of(staffed):
    assert generate(STAFFED) == staffed
    assert max(x.created for x in staffed.dataset.deals) <= STAFFED.as_of
    assert max(t.on for t in staffed.dataset.transitions) <= STAFFED.as_of

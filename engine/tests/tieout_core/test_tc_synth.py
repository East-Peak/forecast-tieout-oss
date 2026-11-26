from collections import defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from engine.scripts.synth_history import Company, generate, true_win_rates

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

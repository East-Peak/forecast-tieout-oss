"""The spike's checks, as tests: totals reconcile to raw records, no future leakage at the query level,
slices sum to parents for every dimension and pair of dimensions, non-additive metrics refuse to be summed."""

import itertools
import json
from collections import Counter
from datetime import date

import pytest

from engine.harness.evidence import load
from engine.harness.query import NonAdditiveError, query, reaggregate, total
from engine.harness.tests.test_evidence_leakage import PAIRS, mutate
from engine.harness.tests.test_evidence_support import ROOT, estate_dirs
from engine.harness.tests.test_query_support import D

W = (D("2025-01-01"), D("2025-06-30"))
T = D("2025-06-30")


def rows(extract: str, system: str, name: str) -> list[dict]:
    path = ROOT / extract / system / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def by_month(pairs) -> dict:
    return {f"2025-{m:02d}": n for m, n in sorted(Counter(pairs).items())}


def monthly(estate, cat, metric):
    return {
        c.key[0]: c.value for c in query(estate, cat, metric, ["month"], None, W, T)
    }


# ---- totals reconcile to the raw records, computed independently ----------------------------------------------


def test_bookings_reconcile_to_the_raw_opportunity_records(estate, cat):
    latest = rows("extract_2025-06-30", "salesforce", "Opportunity")
    expected = Counter()
    for r in latest:
        if r["Type"] == "New Business" and r["StageName"] == "Closed Won":
            expected[r["CloseDate"][:7]] += round(r["Amount"] * 100)
    got = monthly(estate, cat, "bookings")
    assert {m: v for m, v in got.items() if v} == dict(expected)
    assert sum(got.values()) == sum(expected.values()) == 5_900_000


def test_counts_reconcile_to_the_raw_records(estate, cat):
    ever = {
        r["Id"]: r
        for ex in ("extract_2025-04-30", "extract_2025-06-30")
        for r in rows(ex, "salesforce", "Opportunity")
    }
    created = by_month(
        (
            int(r["CreatedDate"][5:7])
            for r in ever.values()
            if r["Type"] == "New Business"
        )
    )
    assert {
        m: v for m, v in monthly(estate, cat, "opportunities_created").items() if v
    } == created
    leads = rows("extract_2025-06-30", "salesforce", "Lead")
    mqls = by_month(int(r["MQL_Date__c"][5:7]) for r in leads if r["MQL_Date__c"])
    assert {m: v for m, v in monthly(estate, cat, "mqls").items() if v} == mqls
    offers = [
        h["NewValue"]
        for h in rows("extract_2025-06-30", "salesforce", "LeadHistory")
        if h["Field"] == "Sales_Offered_Date__c" and h["NewValue"]
    ]
    assert {
        m: v for m, v in monthly(estate, cat, "demand_offered").items() if v
    } == by_month(int(o[5:7]) for o in offers)


# ---- no future leakage, at the query level ---------------------------------------------------------------------

SUITE = [
    ("bookings", ["month"]), ("bookings", ["segment"]), ("bookings", ["source"]), ("bookings", ["booking_owner"]),
    ("won_deals", []), ("opportunities_created", ["region"]), ("win_rate", ["month"]), ("average_deal", []),
    ("sales_cycle_median", []), ("mqls", ["month"]), ("mql_to_opportunity", []), ("demand_offered", ["month"]),
    ("demand_admitted", ["month"]), ("bookings_monthly_average", []), ("open_pipeline_cents", ["segment"]),
    ("open_pipeline_deals", ["source"]),
]  # fmt: skip


def answers(estate, cat, t, k) -> list:
    out = []
    for metric, group_by in SUITE:
        window = (D("2025-01-01"), max(t, D("2025-01-31")))
        for c in query(estate, cat, metric, group_by, None, window, t, known_at=k):
            out.append(
                (
                    metric,
                    c.key,
                    c.value,
                    c.numerator,
                    c.denominator,
                    c.applicability,
                    c.availability,
                    c.availability_reason,
                )
            )
    return out


@pytest.fixture(scope="module")
def original(estate):
    return estate


@pytest.mark.parametrize(
    "variant", ["scramble_history", "delete_history", "scramble_snapshots"]
)
@pytest.mark.parametrize("t, k", PAIRS[:5], ids=lambda v: v.isoformat())
def test_answers_at_k_do_not_change_when_everything_recorded_after_k_is_destroyed(
    original, cat, tmp_path, t, k, variant
):
    world = load(mutate(tmp_path / "w", k, variant))
    assert answers(world, cat, t, k) == answers(original, cat, t, k)


def test_the_check_has_teeth(original, cat, tmp_path):
    t, k = date(2025, 6, 30), PAIRS[-1][1]
    world = load(
        mutate(tmp_path / "w", k, "scramble_before")
    )  # corrupt what was recorded before K
    assert answers(world, cat, t, k) != answers(original, cat, t, k)


# ---- slices sum to parents -----------------------------------------------------------------------------------

LEVELS = {"source": ["source", "source.group"], "month": ["month", "quarter"]}


def axes_of(metric) -> list[str]:
    return [a for d in metric.dimensions for a in LEVELS.get(d, [d])]


@pytest.mark.parametrize(
    "metric_id",
    [
        "bookings",
        "won_deals",
        "opportunities_created",
        "mqls",
        "demand_offered",
        "open_pipeline_cents",
    ],
)
def test_additive_slices_sum_to_the_parent_for_every_dimension_and_pair(
    estate, cat, metric_id
):
    metric = cat.metric(metric_id)
    window, t = (None, D("2025-05-31")) if metric.basis == "snapshot" else (W, T)
    (parent,) = query(estate, cat, metric_id, [], None, window, t)
    axes = axes_of(metric)
    combos = [(a,) for a in axes] + [
        c
        for c in itertools.combinations(axes, 2)
        if c[0].split(".")[0]
        != c[1].split(".")[0]  # a dimension and its own level are one dimension
    ]
    for group_by in combos:
        cells = query(estate, cat, metric_id, list(group_by), None, window, t)
        assert sum(c.value for c in cells if c.value is not None) == parent.value, (
            group_by
        )
        assert not [
            c for c in cells if "inapplicable_member_has_rows" in c.contract.flags
        ], group_by
        assert total([c for c in cells if c.value is not None]) == parent.value


def test_non_additive_cells_never_sum_but_reaggregate_from_numerator_and_denominator(
    estate, cat
):
    for metric_id in ("win_rate", "average_deal", "mql_to_opportunity"):
        cells = query(estate, cat, metric_id, ["segment"], None, W, T)
        with pytest.raises(NonAdditiveError):
            total(cells)
        (whole,) = query(estate, cat, metric_id, [], None, W, T)
        assert reaggregate(cells) == pytest.approx(whole.value)
    for metric_id in ("sales_cycle_median", "bookings_monthly_average"):
        with pytest.raises(NonAdditiveError):
            total(query(estate, cat, metric_id, ["segment"], None, W, T))

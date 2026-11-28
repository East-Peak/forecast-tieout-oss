"""The six metric kinds, snapshots, providers and the refusal to sum non-additive cells."""

import pytest

from engine.harness.catalog import load_catalog
from engine.harness.query import (
    Estimate,
    NonAdditiveError,
    query,
    reaggregate,
    register_estimator,
    register_provider,
    total,
)
from engine.harness.tests.test_query_support import (
    D,
    by_key,
    catalog_text,
    values,
)

W = (D("2025-01-01"), D("2025-06-30"))
T = D("2025-06-30")


def run(estate, cat, metric, group_by=(), window=W, as_of=T, **kw):
    return query(
        estate, cat, metric, group_by, kw.pop("filters", None), window, as_of, **kw
    )


def test_ratio_returns_numerator_and_denominator_and_excludes_immature_cohorts(
    estate, cat
):
    # deals created Jan-Mar are mature at 06-30 (cohort month end + 90 days); April and May are not
    (cell,) = run(estate, cat, "win_rate")
    assert (cell.numerator, cell.denominator) == (2, 3) and cell.value == pytest.approx(
        2 / 3
    )
    assert cell.contract.excluded == {"immature": 2}
    assert cell.contract.cohort_maturity == {
        "days": 90,
        "mature_through": D("2025-03-31"),
    }
    months = by_key(run(estate, cat, "win_rate", ["month"]))
    assert months[("2025-01",)].value == 1.0 and months[("2025-03",)].value == 0.0
    april = months[("2025-04",)]
    assert (april.value, april.availability, april.availability_reason) == (
        None,
        "insufficient",
        "immature_cohort",
    )
    assert (april.numerator, april.denominator) == (0, 0)
    assert months[("2025-06",)].availability_reason == "no_denominator"


def test_average_deal_counts_large_deals_instead_of_dropping_them(estate, cat):
    (cell,) = run(estate, cat, "average_deal")
    assert (cell.numerator, cell.denominator, cell.value) == (5_900_000, 4, 1_475_000)
    small = load_catalog(
        catalog_text().replace("amount_cents > 20000000", "amount_cents > 1500000")
    )  # O1 is large
    (cell,) = run(estate, small, "average_deal")
    assert (cell.numerator, cell.denominator) == (
        3_500_000,
        3,
    ) and cell.contract.excluded == {"large_deal": 1}


def test_quantile_of_cycle_days(estate, cat):
    # won deals took 53 (O1), 81 (O2), 53 (O4) and 23 (O7) days from creation to the effective close date
    (cell,) = run(estate, cat, "sales_cycle_median")
    assert cell.value == 53 and cell.denominator == 4 and cell.numerator is None
    cells = by_key(run(estate, cat, "sales_cycle_median", ["month"]))
    assert (
        cells[("2025-04",)].value == 81
        and cells[("2025-02",)].availability_reason == "no_rows"
    )
    assert cells[("2025-02",)].value is None


def test_conversion_rate_and_lag_with_maturity(estate, cat):
    # MQLs of Jan and Mar are mature; L1 converted after 9 days, L3 after 4, L4 and L5 never; Apr is immature
    (rate,) = run(estate, cat, "mql_to_opportunity")
    assert (rate.numerator, rate.denominator, rate.value) == (
        2,
        4,
        0.5,
    ) and rate.contract.excluded == {"immature": 3}
    (lag,) = run(estate, cat, "mql_to_opportunity_lag")
    assert lag.value == 6.5 and lag.denominator == 2
    by_month = by_key(run(estate, cat, "mql_to_opportunity", ["month"]))
    assert (
        by_month[("2025-03",)].value == pytest.approx(1 / 3)
        and by_month[("2025-04",)].availability == "insufficient"
    )


def test_rollup_is_a_statistic_over_closed_periods(estate, cat):
    (cell,) = run(estate, cat, "bookings_monthly_average")
    assert cell.value == pytest.approx(5_900_000 / 6) and (
        cell.numerator,
        cell.denominator,
    ) == (5_900_000, 6)
    (partial,) = run(estate, cat, "bookings_monthly_average", as_of=D("2025-05-15"))
    assert (
        partial.contract.excluded == {"open_period": 1} and partial.denominator == 4
    )  # Jan-Apr closed, May open


def test_snapshot_metrics_ignore_the_window_and_report_the_stock_at_t(estate, cat):
    t = D("2025-05-31")
    by_segment = values(
        query(estate, cat, "open_pipeline_cents", ["segment"], None, None, t)
    )
    assert by_segment == {
        ("Enterprise",): 7_000_000,
        ("Mid-Market",): 500_000,
        ("SMB",): 800_000,
        ("Unknown",): 0,
    }
    (deals,) = query(estate, cat, "open_pipeline_deals", [], None, None, t)
    assert deals.value == 4 and deals.contract.window is None
    contemporaneous = query(
        estate, cat, "open_pipeline_deals", [], None, None, t, mode="contemporaneous"
    )
    assert (
        contemporaneous[0].value == 4
    )  # O5, O6, O7, O8 then; same count, different deals (expected.yaml)


def test_demand_episodes_match_the_evidence_outcomes(estate, cat):
    march = (D("2025-03-01"), D("2025-03-31"))
    got = {
        m: run(estate, cat, m, window=march)[0].value
        for m in (
            "demand_offered",
            "demand_admitted",
            "demand_rejected",
            "demand_expired",
        )
    }
    assert got == {
        "demand_offered": 3,
        "demand_admitted": 1,
        "demand_rejected": 1,
        "demand_expired": 1,
    }
    may = (D("2025-05-01"), D("2025-05-31"))
    assert run(estate, cat, "demand_offered", window=may)[0].value == 1
    assert (
        run(estate, cat, "demand_admitted", window=may)[0].value == 0
    )  # the re-offer is still open


def test_non_additive_cells_refuse_to_be_summed_and_can_be_reaggregated(estate, cat):
    cells = run(estate, cat, "win_rate", ["segment"])
    with pytest.raises(NonAdditiveError):
        total(cells)
    (whole,) = run(estate, cat, "win_rate")
    assert reaggregate([c for c in cells if c.denominator]) == pytest.approx(
        whole.value
    )
    assert total(run(estate, cat, "bookings", ["segment"])) == 5_900_000


def test_a_registered_estimator_pools_across_cells(estate, cat):
    text = catalog_text().replace(
        "  - id: win_rate\n",
        """  - id: pooled_win_rate
    version: "1"
    label: Pooled win rate
    unit: ratio
    population: decided deals
    basis: cohort
    kind: estimator
    estimator: pooled_rate
    inputs: {successes: cohort_won, trials: cohort_decided}
    maturity_days: 90
    aggregation: non_additive
    dimensions: [segment, month]
    favorable: up
    owner: Sales Operations
    definition: Every segment shares the pooled rate.
  - id: win_rate\n""",
    )
    cat = load_catalog(text)

    def pooled(inputs, params):
        won = sum(f["successes"].total for f in inputs.values())
        trials = sum(f["trials"].total for f in inputs.values())
        return {k: Estimate(won / trials, won, trials, "pooled") for k in inputs}

    (unregistered,) = query(estate, cat, "pooled_win_rate", [], None, W, T)
    assert (unregistered.availability, unregistered.availability_reason) == (
        "unavailable",
        "estimator_not_registered",
    )
    register_estimator("pooled_rate", pooled)
    cells = run(estate, cat, "pooled_win_rate", ["segment"])
    assert {c.derivation for c in cells} == {"pooled"}
    assert {round(c.value, 6) for c in cells} == {round(2 / 3, 6)}


def test_kinds_other_than_actual_without_a_provider_never_raise(estate, cat):
    plan = run(estate, cat, "bookings", ["segment"], kind="plan", plan_version="FY25")
    assert {(c.availability, c.availability_reason, c.value) for c in plan} == {
        ("not_planned", "no_provider", None)
    }
    forecast = run(estate, cat, "bookings", ["month"], kind="forecast", run_id="r1")
    assert {(c.availability, c.availability_reason) for c in forecast} == {
        ("unavailable", "no_provider")
    }
    assert len(forecast) == 6


def test_a_registered_provider_answers_its_kind(estate, cat):
    def provider(request):
        return [
            run(estate, cat, "bookings", window=request.window, as_of=request.t)[
                0
            ].__class__(
                key,
                1,
                None,
                None,
                "applicable",
                "measured",
                None,
                "modeled",
                run(estate, cat, "bookings")[0].contract,
            )
            for key in request.keys
        ]

    register_provider("required", provider)
    cells = run(estate, cat, "bookings", ["segment"], kind="required")
    assert {c.derivation for c in cells} == {"modeled"} and len(cells) == 4

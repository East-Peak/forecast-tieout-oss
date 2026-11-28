"""records(): a cell resolves to the source rows it counted, and they sum or count to the cell exactly."""

import statistics

import pytest

from engine.harness.catalog import load_catalog
from engine.harness.query import Lineage, query, records
from engine.harness.tests.test_query_support import D, catalog_text

W = (D("2025-01-01"), D("2025-06-30"))
T = D("2025-06-30")


def cells(estate, cat, metric, group_by=(), as_of=T, window=W, **kw):
    return query(
        estate, cat, metric, group_by, kw.pop("filters", None), window, as_of, **kw
    )


def test_additive_rows_sum_to_the_cell_exactly_for_every_slice(estate, cat):
    for metric, expected_rows in (
        ("bookings", None),
        ("opportunities_created", None),
    ):
        for group_by in (
            [],
            ["segment"],
            ["source"],
            ["month"],
            ["segment", "source"],
            ["booking_owner"],
        ):
            for cell in cells(estate, cat, metric, group_by):
                if (
                    cell.availability != "measured"
                    or cell.applicability != "applicable"
                    or not cell.contract.eligible  # an empty cell has no rows to resolve
                ):
                    continue
                rows = records(estate, cat, cell)
                got = sum(r.value for r in rows)
                assert got == cell.value, (metric, group_by, cell.key)
                assert len(rows) == (cell.contract.eligible or 0)
                assert all(r.source_record_ids for r in rows)
    assert expected_rows is None


def test_rows_carry_record_ids_and_lineage(estate, cat):
    (cell,) = cells(estate, cat, "bookings", filters={"source": ["BDR Outbound"]})
    (row,) = records(estate, cat, cell)
    assert row.id == "006FX0000000001" and row.value == 2_400_000
    assert (
        "salesforce/OpportunityHistory/008FX0000000005" in row.source_record_ids
    )  # the amended amount


def test_ratio_sides_and_the_excluded_side(estate, cat):
    (rate,) = cells(estate, cat, "win_rate")
    assert len(records(estate, cat, rate, "numerator")) == rate.numerator == 2
    assert len(records(estate, cat, rate, "denominator")) == rate.denominator == 3
    assert {r.id for r in records(estate, cat, rate, "excluded:immature")} == {
        "006FX0000000004",
        "006FX0000000007",
    }
    small = load_catalog(
        catalog_text().replace("amount_cents > 20000000", "amount_cents > 1500000")
    )
    (avg,) = cells(estate, small, "average_deal")
    assert [r.id for r in records(estate, small, avg, "excluded:large_deal")] == [
        "006FX0000000001"
    ]
    assert (
        sum(r.value for r in records(estate, small, avg, "numerator")) == avg.numerator
    )


def test_quantile_and_conversion_rows(estate, cat):
    (cycle,) = cells(estate, cat, "sales_cycle_median")
    rows = records(estate, cat, cycle)
    assert (
        statistics.median(r.value for r in rows) == cycle.value
        and len(rows) == cycle.denominator
    )
    (rate,) = cells(estate, cat, "mql_to_opportunity")
    assert len(records(estate, cat, rate, "numerator")) == rate.numerator
    assert len(records(estate, cat, rate, "denominator")) == rate.denominator
    (lag,) = cells(estate, cat, "mql_to_opportunity_lag")
    assert sorted(r.value for r in records(estate, cat, lag)) == [4, 9]


def test_rollup_and_snapshot_rows(estate, cat):
    (avg,) = cells(estate, cat, "bookings_monthly_average")
    assert sum(r.value for r in records(estate, cat, avg)) == avg.numerator
    (stock,) = query(
        estate, cat, "open_pipeline_cents", [], None, None, D("2025-05-31")
    )
    assert sum(r.value for r in records(estate, cat, stock)) == stock.value == 8_300_000


def test_rows_respect_the_knowledge_cutoff_of_the_cell(estate, cat):
    march = (D("2025-03-01"), D("2025-03-31"))
    (recon,) = cells(
        estate,
        cat,
        "bookings",
        window=march,
        as_of=D("2025-03-31"),
        mode="reconstructed",
    )
    (contemp,) = cells(
        estate,
        cat,
        "bookings",
        window=march,
        as_of=D("2025-03-31"),
        mode="contemporaneous",
    )
    assert sum(r.value for r in records(estate, cat, recon)) == 2_400_000
    assert sum(r.value for r in records(estate, cat, contemp)) == 2_000_000


def test_only_measured_cells_resolve(estate, cat):
    with pytest.raises(ValueError):
        records(estate, cat, Lineage("modeled", run_id="r1", lanes=("a",)))
    with pytest.raises(ValueError):
        records(estate, cat, (cells(estate, cat, "win_rate")[0]), "nope")

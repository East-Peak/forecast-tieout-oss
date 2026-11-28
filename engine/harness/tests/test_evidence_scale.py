"""Tranche 1, part G: a generated-estate smoke path.

Estate A replicated with distinct ids to 5,000 opportunities and extracted 13 times per system.
The loader is set-based, so this loads in seconds and answers a bookings-by-month question in
milliseconds. Timings are printed (run with -s) and bounded.
"""

import time
from datetime import date

import pytest

from engine.harness.evidence import (
    AsOf,
    bookings_by_month,
    demand_outcomes,
    load,
    mql_count,
)
from engine.harness.tests.test_evidence_reconcile import reconcile
from engine.harness.tests.test_evidence_support import scaled_estate

COPIES = 625  # 8 opportunities each: 5,000


@pytest.fixture(scope="module")
def scaled(tmp_path_factory):
    dirs = scaled_estate(tmp_path_factory.mktemp("scaled"), COPIES)
    started = time.perf_counter()
    store = load(dirs)
    return dirs, store, time.perf_counter() - started


def test_the_scaled_estate_has_the_stated_size(scaled):
    dirs, store, _ = scaled
    salesforce = [d for d in dirs if d.name == "salesforce"]
    assert len(salesforce) == 13
    assert store.con.execute("SELECT count(*) FROM extract").fetchall()[0][0] == len(
        dirs
    )
    assert (
        store.con.execute(
            "SELECT count(DISTINCT id) FROM record WHERE entity = 'Opportunity'"
        ).fetchall()[0][0]
        == 8 * COPIES
    )


def test_it_loads_in_under_ten_seconds(scaled):
    _, _, seconds = scaled
    print(
        f"\nload of {8 * COPIES} opportunities, 13 salesforce extracts: {seconds:.2f}s"
    )
    assert seconds < 10


def test_reloading_the_same_extracts_is_instant_and_changes_nothing(scaled):
    dirs, store, _ = scaled
    before = store.con.execute("SELECT count(*) FROM assertion").fetchall()[0][0]
    started = time.perf_counter()
    load(dirs, store=store)
    assert time.perf_counter() - started < 1
    assert (
        store.con.execute("SELECT count(*) FROM assertion").fetchall()[0][0] == before
    )


def test_bookings_by_month_answers_in_under_a_second(scaled):
    _, store, _ = scaled
    asof = AsOf.reconstructed(store, date(2099, 1, 1))
    started = time.perf_counter()
    got = {
        m: bookings_by_month(asof, m)
        for m in ("2025-03", "2025-04", "2025-05", "2025-06")
    }
    elapsed = time.perf_counter() - started
    print(
        f"\nbookings by month over {8 * COPIES} opportunities: {elapsed * 1000:.0f} ms for four months"
    )
    assert got == {
        m: COPIES * c
        for m, c in {
            "2025-03": 2400000,
            "2025-04": 1500000,
            "2025-05": 1200000,
            "2025-06": 800000,
        }.items()
    }
    assert elapsed < 1


def test_the_other_questions_stay_fast_too(scaled):
    _, store, _ = scaled
    asof = AsOf.reconstructed(store, date(2025, 5, 31))
    started = time.perf_counter()
    assert len(asof.open_ids()) == 4 * COPIES
    assert mql_count(asof, "2025-04") == 3 * COPIES
    assert demand_outcomes(asof, "2025-03").counts == {
        "admitted": COPIES,
        "rejected": COPIES,
        "expired": COPIES,
    }
    assert asof.relation("opportunity_spell").aggregate("count(*)").fetchall()[0][0] > 0
    assert time.perf_counter() - started < 3


def test_the_scaled_measures_reconcile_to_the_raw_records(scaled):
    dirs, store, _ = scaled
    last = {}
    for folder in dirs:
        if "extra" in folder.parent.name or folder.name not in last:
            last[folder.name] = folder
    reconcile(
        store,
        [d for d in last.values() if d.name == "salesforce"]
        + [d for d in last.values() if d.name == "spend_sheet"],
    )

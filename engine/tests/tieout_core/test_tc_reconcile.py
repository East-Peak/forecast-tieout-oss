from datetime import date
from decimal import Decimal

import pytest

from engine.tests.tieout_core.builders import deal, write_company, write_profile
from engine.tieout_core.load import load_company, load_profile
from engine.tieout_core.reconcile import reconcile

AS_OF = date(2026, 4, 15)


@pytest.fixture
def profile(tmp_path):
    return load_profile(write_profile(tmp_path / "profile"))


def _run(tmp_path, profile, rows):
    path = write_company(tmp_path / "c", rows)
    return reconcile(path, load_company(path, profile), profile, AS_OF)


ROWS = [
    deal("PRIOR", "Closed Won", "1000.00", "2025-06-01", "2026-01-31"),  # before FY26
    deal("FEB", "Closed Won", "200.10", "2025-12-01", "2026-02-01"),  # first day of FY
    deal(
        "APR", "Closed Won", "300.25", "2026-02-10", "2026-04-15"
    ),  # on the as-of date
    deal("LOST", "Closed Lost", "50", "2026-01-05", "2026-03-03"),
    deal("OPEN", "Negotiation", "75", "2026-03-01", "2026-06-30"),
    deal("EXP", "Closed Won", "999", "2026-01-01", "2026-03-01", type="expansion"),
    deal("TOMORROW", "Closed Won", "40", "2026-01-01", "2026-04-16"),
    deal("UNBORN", "Discovery", "60", "2026-04-16"),
    deal("BROKEN", "Closed Won", "nope", "2026-01-01", "2026-03-01"),
]


def test_fytd_bookings_by_month_to_the_cent(tmp_path, profile):
    r = _run(tmp_path, profile, ROWS)
    assert r.bookings_by_month == {
        "2026-02": Decimal("200.10"),
        "2026-03": Decimal("0"),
        "2026-04": Decimal("300.25"),
    }
    assert r.bookings_fytd == Decimal("500.35")


def test_every_excluded_row_has_a_reason(tmp_path, profile):
    r = _run(tmp_path, profile, ROWS)
    assert {e.deal_id: e.reason for e in r.exclusions} == {
        "EXP": "excluded motion: expansion",
        "TOMORROW": "closed after the as-of date",
        "UNBORN": "created after the as-of date",
        "BROKEN": "arr is missing or not a number",
    }


def test_excluded_motions_are_reconciled_separately(tmp_path, profile):
    r = _run(tmp_path, profile, ROWS)
    exp = r.excluded_motions["expansion"]
    assert (exp.rows, exp.arr, exp.won_fytd_arr) == (1, Decimal("999"), Decimal("999"))


def test_source_ties_out(tmp_path, profile):
    r = _run(tmp_path, profile, ROWS)
    assert all(c.passed for c in r.checks), [c for c in r.checks if not c.passed]
    names = {c.name for c in r.checks}
    assert {
        "rows partition",
        "arr partition",
        "bookings tie to source",
        "pipeline flow",
    } <= names


def test_bookings_tie_counts_won_rows_that_were_excluded(tmp_path, profile):
    # The flag-mismatch row is new-business won FYTD in the raw file; the tie
    # must account for it rather than silently differ.
    bad = {
        **deal("FLAG", "Closed Won", "7", "2026-01-01", "2026-03-01"),
        "is_closed": "false",
    }
    r = _run(tmp_path, profile, ROWS + [bad])
    tie = next(c for c in r.checks if c.name == "bookings tie to source")
    assert tie.passed
    assert "7" in tie.detail


def test_pipeline_flow_conserves_count_and_dollars(tmp_path, profile):
    flow = _run(tmp_path, profile, ROWS).flow
    # Open at FY start: FEB (created Dec) and LOST (created Jan).  Created in FY: APR, OPEN.
    assert (flow.open_at_start.count, flow.open_at_start.arr) == (2, Decimal("250.10"))
    assert (flow.created.count, flow.created.arr) == (2, Decimal("375.25"))
    assert (flow.won.count, flow.won.arr) == (2, Decimal("500.35"))
    assert (flow.lost.count, flow.lost.arr) == (1, Decimal("50"))
    assert (flow.open_at_end.count, flow.open_at_end.arr) == (1, Decimal("75"))


def test_as_of_outside_the_fiscal_year_is_refused(tmp_path, profile):
    path = write_company(tmp_path / "c", ROWS)
    with pytest.raises(ValueError, match="outside"):
        reconcile(path, load_company(path, profile), profile, date(2027, 2, 1))


def test_stage_history_after_the_as_of_is_refused(tmp_path, profile):
    path = write_company(
        tmp_path / "c", [deal("OPEN", "Negotiation", "75", "2026-03-01", "2026-06-30")],
        history=[("OPEN", "Discovery", "2026-03-01"), ("OPEN", "Negotiation", "2026-04-20")],
    )  # fmt: skip
    with pytest.raises(ValueError, match="after the as-of date"):
        reconcile(path, load_company(path, profile), profile, AS_OF)

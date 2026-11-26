from datetime import date

import pytest

from engine.tieout_core.fiscal import FiscalYear, Window, add_months, month_windows


def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert add_months(date(2024, 8, 15), 12) == date(2025, 8, 15)


def test_fiscal_year_quarters_follow_start_month():
    fy = FiscalYear(date(2026, 2, 1))
    assert fy.end == date(2027, 1, 31)
    assert fy.quarter_key(date(2026, 2, 1)) == "Q1FY26"
    assert fy.quarter_key(date(2026, 4, 30)) == "Q1FY26"
    assert fy.quarter_key(date(2026, 5, 1)) == "Q2FY26"
    assert fy.quarter_key(date(2027, 1, 31)) == "Q4FY26"
    assert fy.quarter_keys == ("Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26")


def test_fiscal_year_rejects_dates_outside_it():
    fy = FiscalYear(date(2026, 2, 1))
    assert fy.contains(date(2027, 1, 31))
    assert not fy.contains(date(2027, 2, 1))
    with pytest.raises(ValueError):
        fy.quarter_key(date(2026, 1, 31))


def test_month_windows_split_the_as_of_month():
    # As-of mid-month: the first window is the rest of that month only.
    windows = month_windows(date(2026, 11, 14), date(2027, 1, 31))
    assert windows == [
        Window("2026-11", date(2026, 11, 14), date(2026, 11, 30)),
        Window("2026-12", date(2026, 11, 30), date(2026, 12, 31)),
        Window("2027-01", date(2026, 12, 31), date(2027, 1, 31)),
    ]


def test_month_windows_at_month_end_skip_the_empty_remainder():
    windows = month_windows(date(2026, 11, 30), date(2027, 1, 31))
    assert [w.label for w in windows] == ["2026-12", "2027-01"]


def test_window_contains_is_open_at_start_closed_at_end():
    w = Window("x", date(2026, 1, 1), date(2026, 1, 31))
    assert not w.contains(date(2026, 1, 1))
    assert w.contains(date(2026, 1, 2))
    assert w.contains(date(2026, 1, 31))
    assert w.days == 30

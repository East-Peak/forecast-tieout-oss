"""Tests for engine.gtm_model.derived.mql_signals.

CONTRACT NOTE: legacy `_get_trailing_mql_weekly_signal()` returns more
than these basic aggregates (e.g. EWMA-smoothed signal); legacy
`_get_monthly_mql_actuals()` returns ([12 months], partial_idx) tuple.
future work will either extend these data classes or compose at the backend
level. These tests pin the current shape.
"""
from __future__ import annotations

from datetime import date

from engine.gtm_model.derived.mql_signals import (
    MonthlyMQLSeries,
    MQLSignals,
    compute_mql_signals_from_buckets,
    compute_monthly_mql_from_buckets,
)


def test_mql_signals_from_empty_buckets():
    signals = compute_mql_signals_from_buckets([], lookback_days=180)
    assert signals.total == 0
    assert signals.avg_per_week is None


def test_mql_signals_aggregates_total_and_average():
    buckets = [
        {"week_start": "2026-01-05", "count": 10},
        {"week_start": "2026-01-12", "count": 20},
        {"week_start": "2026-01-19", "count": 30},
    ]
    signals = compute_mql_signals_from_buckets(buckets, lookback_days=21)
    assert signals.total == 60
    assert signals.avg_per_week == 20.0
    assert signals.lookback_days == 21


def test_mql_signals_handles_missing_count():
    buckets = [{"week_start": "2026-01-05"}]  # no count
    signals = compute_mql_signals_from_buckets(buckets, lookback_days=7)
    assert signals.total == 0


def test_monthly_mql_from_iso_string_keys():
    series = compute_monthly_mql_from_buckets(
        {"2026-01-01": 100, "2026-02-01": 150}
    )
    assert series.monthly_counts[date(2026, 1, 1)] == 100
    assert series.monthly_counts[date(2026, 2, 1)] == 150


def test_monthly_mql_from_date_keys():
    series = compute_monthly_mql_from_buckets(
        {date(2026, 1, 1): 50, date(2026, 2, 1): 75}
    )
    assert series.monthly_counts[date(2026, 1, 1)] == 50


def test_monthly_mql_drops_invalid_keys():
    series = compute_monthly_mql_from_buckets(
        {"not a date": 50, "2026-01-01": 100}
    )
    assert series.monthly_counts == {date(2026, 1, 1): 100}

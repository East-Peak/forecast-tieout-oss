from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from engine.tests.tieout_core.builders import write_profile
from engine.tieout_core.fiscal import month_windows
from engine.tieout_core.fit import FitParams, Model, NewPipeline, Timing
from engine.tieout_core.forecast import (
    existing_pipeline_conservation,
    model_forecast,
    run_rate,
    simulate,
    stage_weighted,
)
from engine.tieout_core.load import load_profile
from engine.tieout_core.rates import RateBook
from engine.tieout_core.records import Dataset, Deal

CUT = date(2026, 1, 15)
WINDOWS = month_windows(CUT, date(2026, 3, 31))  # 16, 28 and 31 days; ends at day 16, 44, 75


def _deal(id, created, stage, arr, close=None, won=False):
    closed = stage in ("Won", "Lost")
    return Deal(0, id, "new_business", "mm", stage, Decimal(arr), created, close, closed, won)


DATA = Dataset(
    deals=(
        _deal("X", date(2026, 1, 1), "S1", "100", date(2026, 2, 10)),
        _deal("Y", date(2025, 12, 1), "S2", "50", date(2026, 1, 5)),  # past due
        _deal("Z", date(2025, 11, 1), "S1", "180", date(2026, 5, 1)),  # beyond the windows
        _deal("W", date(2025, 10, 1), "Won", "400", date(2025, 12, 1), True),  # 61-day cycle
    ),
    transitions=(),
    observations=None,
)

MODEL = Model(
    cutoff=CUT,
    params=FitParams(),
    rates=RateBook(),
    cells={},
    stage_rates={"S1": Decimal("0.5"), "S2": Decimal("0.5")},
    timings={"S1": Timing((10, 40), "t"), "S2": Timing((10, 40), "t")},
    new_pipeline=NewPipeline(
        win_rate=Decimal("0.5"),
        timing=Timing((30,), "t"),
        mean_won_arr=Decimal(1000),
        mean_created_arr=Decimal(2000),
        created_per_day=Decimal("0.1"),
        won_arr_samples=(Decimal(1000),),
    ),
    unknown_stage_observations=0,
)

ONLY_X = Dataset(DATA.deals[:1], (), None)


@pytest.fixture(scope="module")
def profile(tmp_path_factory):
    return load_profile(write_profile(tmp_path_factory.mktemp("p")))


def test_run_rate_spreads_trailing_bookings_per_day():
    f = run_rate(DATA, CUT, WINDOWS)
    assert f.components["run-rate"] == {
        "2026-01": Decimal(400) * 16 / 365,
        "2026-02": Decimal(400) * 28 / 365,
        "2026-03": Decimal(400) * 31 / 365,
    }


def test_stage_weighted_uses_profile_probabilities_and_expected_close(profile):
    f = stage_weighted(DATA, CUT, profile, WINDOWS)
    # Y is past due, so it lands in the first window; Z closes after the last.
    assert f.components["existing pipeline"] == {
        "2026-01": Decimal("10.0"), "2026-02": Decimal("10.0"), "2026-03": Decimal(0)}  # fmt: skip
    # $730 created in the trailing year = $2/day, x Discovery 0.1, closing 61 days later.
    assert f.components["future pipeline"]["2026-03"] == Decimal("2.8")
    assert f.components["future pipeline"]["2026-02"] == 0


def test_stage_weighted_is_unavailable_without_amounts(profile):
    unknown = Dataset((replace(_deal("X", date(2026, 1, 1), "S1", "1"), arr=None),), (), None)
    f = stage_weighted(unknown, CUT, profile, WINDOWS)
    assert f.available is False
    assert "amount" in f.unavailable_reason


def test_model_existing_pipeline_by_window():
    f = model_forecast(MODEL, ONLY_X, CUT, WINDOWS)
    assert f.components["existing pipeline"] == {
        "2026-01": Decimal(25), "2026-02": Decimal(25), "2026-03": Decimal(0)}  # fmt: skip


def test_model_future_pipeline_by_window():
    f = model_forecast(MODEL, ONLY_X, CUT, WINDOWS)
    assert f.components["future pipeline"] == {
        "2026-01": Decimal(0), "2026-02": Decimal(700), "2026-03": Decimal(1550)}  # fmt: skip


def test_added_pipeline_is_spread_evenly_across_windows():
    f = model_forecast(MODEL, ONLY_X, CUT, WINDOWS, added_pipeline=Decimal(3000))
    added = f.components["added pipeline"]
    assert added["2026-01"] == 0
    assert added["2026-02"] == Decimal("0.25") * Decimal(1000) / 16 * 14
    expected_march = Decimal("0.25") * (Decimal(1000) / 16 * 2 + Decimal(1000) + Decimal(1000) / 31)
    assert abs(added["2026-03"] - expected_march) < Decimal("1e-20")


def test_existing_pipeline_dollars_are_conserved():
    check = existing_pipeline_conservation(MODEL, DATA, CUT, WINDOWS)
    assert check.passed, check.detail


def test_simulation_is_seeded_and_centred_on_the_expectation():
    a = simulate(MODEL, ONLY_X, CUT, WINDOWS, draws=20000, seed=7)
    b = simulate(MODEL, ONLY_X, CUT, WINDOWS, draws=20000, seed=7)
    assert a == b
    expected_total = 50 + 2250  # existing 25 + 25, future 700 + 1550
    assert a.total.mean == pytest.approx(expected_total, rel=0.03)
    assert a.total.p2_5 <= a.total.p10 <= a.total.p50 <= a.total.p90 <= a.total.p97_5


def test_simulation_reports_spreads_for_groups_of_windows():
    groups = {"Q": ["2026-02", "2026-03"], "all": [w.label for w in WINDOWS]}
    s = simulate(MODEL, ONLY_X, CUT, WINDOWS, draws=5000, seed=3, groups=groups)
    assert s.by_group["all"] == s.total
    assert s.by_group["Q"].mean == pytest.approx(25 + 700 + 1550, rel=0.04)


def test_baselines_declare_their_rates(profile):
    (rr,) = run_rate(DATA, CUT, WINDOWS).rates
    assert (rr.name, rr.value, rr.sample_size) == ("trailing_bookings_per_day", Decimal(400) / 365, 1)
    sw = {r.name: r for r in stage_weighted(DATA, CUT, profile, WINDOWS).rates}
    assert sw["stage_probability:S1"].value == Decimal("0.1")
    assert sw["stage_probability:S1"].source == "entered"
    assert sw["created_arr_per_day"].value == Decimal(2)
    assert sw["median_won_cycle_days"].value == Decimal(61)


def test_no_windows_means_nothing_to_forecast(profile):
    for f in (run_rate(DATA, CUT, []), stage_weighted(DATA, CUT, profile, []), model_forecast(MODEL, DATA, CUT, [])):
        assert f.available and f.total() == 0
    assert simulate(MODEL, ONLY_X, CUT, [], draws=10).total.mean == 0

from dataclasses import replace
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from engine.tests.tieout_core.builders import write_profile
from engine.tieout_core import forecast as forecast_module
from engine.tieout_core.fiscal import month_windows
from engine.tieout_core.fit import FitParams, Model, NewPipeline, Timing
from engine.tieout_core.forecast import (
    Inflow,
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
WINDOWS = month_windows(
    CUT, date(2026, 3, 31)
)  # 16, 28 and 31 days; ends at day 16, 44, 75


def _deal(id, created, stage, arr, close=None, won=False):
    closed = stage in ("Won", "Lost")
    return Deal(
        0, id, "new_business", "mm", stage, Decimal(arr), created, close, closed, won
    )


DATA = Dataset(
    deals=(
        _deal("X", date(2026, 1, 1), "S1", "100", date(2026, 2, 10)),
        _deal("Y", date(2025, 12, 1), "S2", "50", date(2026, 1, 5)),  # past due
        _deal(
            "Z", date(2025, 11, 1), "S1", "180", date(2026, 5, 1)
        ),  # beyond the windows
        _deal(
            "W", date(2025, 10, 1), "Won", "400", date(2025, 12, 1), True
        ),  # 61-day cycle
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
        cohort_size=10,
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
    unknown = Dataset(
        (replace(_deal("X", date(2026, 1, 1), "S1", "1"), arr=None),), (), None
    )
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
    expected_march = Decimal("0.25") * (
        Decimal(1000) / 16 * 2 + Decimal(1000) + Decimal(1000) / 31
    )
    assert abs(added["2026-03"] - expected_march) < Decimal("1e-20")


def test_existing_pipeline_dollars_are_conserved():
    check = existing_pipeline_conservation(MODEL, DATA, CUT, WINDOWS)
    assert check.passed, check.detail


def test_simulation_is_seeded_and_centered_on_the_expectation():
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
    assert (rr.name, rr.value, rr.sample_size) == (
        "trailing_bookings_per_day",
        Decimal(400) / 365,
        1,
    )
    sw = {r.name: r for r in stage_weighted(DATA, CUT, profile, WINDOWS).rates}
    assert sw["stage_probability:S1"].value == Decimal("0.1")
    assert sw["stage_probability:S1"].source == "entered"
    assert sw["created_arr_per_day"].value == Decimal(2)
    assert sw["median_won_cycle_days"].value == Decimal(61)


def test_no_windows_means_nothing_to_forecast(profile):
    for f in (
        run_rate(DATA, CUT, []),
        stage_weighted(DATA, CUT, profile, []),
        model_forecast(MODEL, DATA, CUT, []),
    ):
        assert f.available and f.total() == 0
    assert simulate(MODEL, ONLY_X, CUT, [], draws=10).total.mean == 0


def test_an_unknown_amount_makes_the_model_unavailable_even_for_unknown_stages():
    from engine.tieout_core.history import UNKNOWN_STAGE

    lost = replace(
        _deal("Q", date(2026, 1, 1), "S1", "1"), stage=UNKNOWN_STAGE, arr=None
    )
    f = model_forecast(MODEL, Dataset((lost,), (), None), CUT, WINDOWS)
    assert f.available is False


def test_created_pipeline_has_one_amount_rule_everywhere(profile):
    from engine.tieout_core.fit import fit
    from engine.tieout_core.history import creation_amounts
    from engine.tieout_core.records import Observation

    # X was recorded at $40 when created; it is $100 now. Y, Z, W never changed.
    obs = tuple(
        Observation(
            d.id, d.created, Decimal(40) if d.id == "X" else d.arr, date(2026, 6, 1)
        )
        for d in DATA.deals
    )
    data = Dataset(DATA.deals, (), obs)
    assert creation_amounts(data)["X"] == Decimal(40)
    sw = {r.name: r for r in stage_weighted(data, CUT, profile, WINDOWS).rates}
    assert sw["created_arr_per_day"].value == Decimal(40 + 50 + 180 + 400) / 365
    model = fit(data, CUT, profile)
    assert "(first recorded amount)" in model.rates["mean_created_arr"].definition
    # With an observation missing, the baseline says so rather than undercount.
    partial = Dataset(DATA.deals, (), obs[:1])
    assert stage_weighted(partial, CUT, profile, WINDOWS).available is False


def test_missing_close_timing_is_unavailable_not_zero():
    no_timing = replace(MODEL, timings={"S1": Timing((), "t"), "S2": Timing((), "t")})
    f = model_forecast(no_timing, ONLY_X, CUT, WINDOWS)
    assert f.available is False and "close-timing" in f.unavailable_reason


def test_no_matured_creation_cohort_is_unavailable_not_zero():
    empty = replace(MODEL, new_pipeline=replace(MODEL.new_pipeline, cohort_size=0))
    f = model_forecast(empty, ONLY_X, CUT, WINDOWS)
    assert f.available is False and "creation cohort" in f.unavailable_reason


class _Wasm32Numpy:
    """numpy as a 32-bit WebAssembly build has it: the platform integer is 32 bits and
    ``repeat`` refuses a count array that cannot be cast to it without loss."""

    intp = np.int32

    def __getattr__(self, name):
        return getattr(np, name)

    @staticmethod
    def repeat(a, repeats, axis=None):
        counts = np.asarray(repeats)
        if not np.can_cast(counts.dtype, np.int32, "safe"):
            raise TypeError(
                f"Cannot cast array data from {counts.dtype} to dtype('int32') according to the rule 'safe'"
            )
        return np.repeat(a, counts, axis)


@pytest.mark.parametrize(
    "inflows",
    [(), (Inflow(0, 30, Decimal(100000)),)],
    ids=["flat creation rate", "created pipeline added"],
)
def test_the_simulation_runs_where_the_platform_integer_is_32_bits(
    monkeypatch, inflows
):
    native = simulate(MODEL, ONLY_X, CUT, WINDOWS, draws=500, seed=7, inflows=inflows)
    monkeypatch.setattr(forecast_module, "np", _Wasm32Numpy())
    wasm = simulate(MODEL, ONLY_X, CUT, WINDOWS, draws=500, seed=7, inflows=inflows)
    assert wasm == native


# ------------------------------------------------------------------ win-rate lift


def _lifted(lift, **kw):
    return model_forecast(MODEL, DATA, CUT, WINDOWS, lift=lift, **kw)


def test_a_lift_is_wins_expected_on_each_days_creation_at_the_mean_won_size():
    """Wins land 30 days after creation; the windows end on days 16, 44 and 75, so the deals
    created on days 1 to 14 win in the second window and on days 15 to 45 in the third."""
    f = _lifted((Decimal("0.01"),) * 75)
    assert f.components[forecast_module.ACTIONS] == {
        "2026-01": Decimal(0),
        "2026-02": Decimal("0.01") * 14 * 1000,
        "2026-03": Decimal("0.01") * 31 * 1000,
    }
    assert (
        f.components[forecast_module.EXISTING]
        == model_forecast(MODEL, DATA, CUT, WINDOWS).components[
            forecast_module.EXISTING
        ]
    )


def test_a_lift_on_later_days_only_moves_the_windows_those_days_win_in():
    lift = (Decimal(0),) * 20 + (Decimal(2),) * 55  # days 21 to 75
    got = _lifted(lift).components[forecast_module.ACTIONS]
    assert got["2026-02"] == 0  # the deals created on days 1 to 14 are not lifted
    assert got["2026-03"] == Decimal(2) * 25 * 1000  # days 21 to 45


def test_no_lift_or_a_lift_of_zeros_is_the_forecast_as_it_was():
    plain = model_forecast(MODEL, DATA, CUT, WINDOWS)
    assert _lifted(()) == plain
    assert _lifted((Decimal(0),) * 75) == plain


def test_a_lift_adds_to_creation_whatever_its_source_and_changes_no_other_part():
    flows = (Inflow(0, 30, Decimal(6000)),)
    own = _lifted((Decimal("0.01"),) * 75, inflows=flows)
    plain = model_forecast(MODEL, DATA, CUT, WINDOWS, inflows=flows)
    for part in (
        forecast_module.EXISTING,
        forecast_module.FUTURE,
        forecast_module.ADDED,
    ):
        assert own.components[part] == plain.components[part]
    assert own.window_total("2026-03") - plain.window_total("2026-03") == Decimal(310)


def _within_four_standard_errors(sim, expected):
    sd = (
        sum((x - sim.total.mean) ** 2 for x in sim.samples_total) / (sim.draws - 1)
    ) ** 0.5 / sim.draws**0.5
    return abs(sim.total.mean - expected) <= 4 * sd


def test_a_simulation_under_a_lift_is_centered_on_the_forecast_under_it():
    lift = (Decimal("0.2"),) * 75
    expected = float(_lifted(lift).total())
    plain = float(model_forecast(MODEL, DATA, CUT, WINDOWS).total())
    sim = simulate(MODEL, DATA, CUT, WINDOWS, draws=6000, seed=3, lift=lift)
    assert _within_four_standard_errors(sim, expected)
    assert expected - plain > 1000  # and the lift is a real one


def test_a_simulation_with_no_lift_or_a_lift_of_zeros_is_the_one_there_was():
    plain = simulate(MODEL, DATA, CUT, WINDOWS, draws=500, seed=5)
    assert simulate(MODEL, DATA, CUT, WINDOWS, draws=500, seed=5, lift=()) == plain
    zeros = (Decimal(0),) * 75
    assert simulate(MODEL, DATA, CUT, WINDOWS, draws=500, seed=5, lift=zeros) == plain


def test_a_lift_that_never_wins_inside_the_windows_adds_nothing_to_them():
    late = (Decimal(0),) * 60 + (
        Decimal(5),
    ) * 15  # created on days 61 to 75: wins on 91+
    plain = model_forecast(MODEL, DATA, CUT, WINDOWS)
    assert _lifted(late).window_total("2026-03") == plain.window_total("2026-03")
    sim = simulate(MODEL, DATA, CUT, WINDOWS, draws=6000, seed=5, lift=late)
    assert _within_four_standard_errors(sim, float(plain.total()))

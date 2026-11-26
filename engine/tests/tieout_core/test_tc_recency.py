"""Goal 2A, lesson 1 (recency). The declared candidate: the same quantity as
Goal 1 (won within 365 days of a snapshot, by stage and age group) estimated
as a cumulative incidence over days since the snapshot, with loss as a
competing outcome and still-open deals counted only for the days they were
observed, from snapshots in the trailing 24 months including ones younger than
365 days. Close timing comes from the same curve. The creation cohort that
prices pipeline not yet created is estimated the same way (a deal's creation
is its snapshot)."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest

from engine.scripts.synth_history import Company, generate
from engine.tests.tieout_core.builders import write_profile
from engine.tests.tieout_core.test_tc_backtest import regular_history
from engine.tieout_core.backtest import (
    MODEL,
    Backtest,
    Fold,
    HorizonScore,
    compare_estimators,
    fold,
)
from engine.tieout_core.fiscal import Window
from engine.tieout_core.fit import (
    LOSS,
    MATURED,
    OPEN,
    RECENCY,
    WIN,
    FitParams,
    Timing,
    cumulative_incidence,
    fit,
)
from engine.tieout_core.forecast import model_forecast, simulate
from engine.tieout_core.history import as_known_at
from engine.tieout_core.load import load_profile
from engine.tieout_core.records import Dataset, Deal

RECENT = FitParams(estimator=RECENCY)


@pytest.fixture(scope="module")
def profile(tmp_path_factory):
    return load_profile(write_profile(tmp_path_factory.mktemp("p")))


# ---------------------------------------------------------------- the estimator


def test_cumulative_incidence_by_hand():
    # day 3: 5 at risk, 1 win          F = 1/5 = 0.2,           S = 0.8
    # day 5: 4 at risk, 1 loss         F = 0.2,                 S = 0.6
    #        (the deal censored on day 5 is at risk that day, then leaves)
    # day 8: 2 at risk, 1 win          F = 0.2 + 0.6 * 1/2 = 0.5
    obs = [(3, WIN), (5, LOSS), (5, OPEN), (8, WIN), (10, OPEN)]
    ci = cumulative_incidence(obs, horizon=365)
    assert ci.value == Decimal("0.5")
    assert (ci.n, ci.wins, ci.still_open) == (5, 2, 2)
    assert ci.timing.samples == (3, 8)
    assert ci.timing.weights == (Decimal("0.2"), Decimal("0.3"))
    assert cumulative_incidence(obs, horizon=7).value == Decimal("0.2")


def test_without_censoring_it_is_the_share_won_with_binomial_variance():
    obs = [(3, WIN), (5, LOSS), (5, WIN), (8, WIN), (10, LOSS), (12, WIN), (400, WIN)]
    ci = cumulative_incidence(obs, horizon=365)
    assert ci.value == Decimal(4) / Decimal(7)  # the day-400 win is outside the horizon
    p = 4 / 7
    assert ci.variance == pytest.approx(p * (1 - p) / 7)


def test_no_wins_has_no_timing_and_a_zero_rate():
    ci = cumulative_incidence([(4, LOSS), (9, OPEN)], horizon=365)
    assert ci.value == 0 and ci.timing.samples == () and ci.wins == 0


# ---------------------------------------------------------------- weighted timing


def test_weighted_timing_cdf_and_forward_function():
    t = Timing((3, 8), "t", weights=(Decimal("0.2"), Decimal("0.3")))
    assert t.cdf(2) == 0 and t.cdf(5) == Decimal("0.4") and t.cdf(8) == 1
    assert t.total == Decimal("0.5") and t.count_through(5) == Decimal("0.2")
    cut = date(2026, 1, 15)
    deal = Deal(0, "X", "new_business", "mm", "S1", Decimal(100), date(2026, 1, 1), None, False, False)  # fmt: skip
    from engine.tests.tieout_core.test_tc_forecast import MODEL as BASE

    model = replace(BASE, timings={"S1": t, "S2": t})
    windows = [Window("a", cut, cut + timedelta(days=5)), Window("b", cut + timedelta(days=5), cut + timedelta(days=30))]  # fmt: skip
    f = model_forecast(model, Dataset((deal,), (), None), cut, windows)
    # 100 x 0.5 win rate x (0.4 by day 5, then 0.6 by day 30)
    assert f.components["existing pipeline"] == {
        "a": Decimal("20.0"),
        "b": Decimal("30.0"),
    }
    sim = simulate(model, Dataset((deal,), (), None), cut, windows, draws=20000, seed=3)
    assert sim.by_window["a"].mean == pytest.approx(20, abs=1.5)
    assert sim.by_window["b"].mean == pytest.approx(30, abs=1.5)


# ---------------------------------------------------------------- the fit


def test_recency_learns_from_snapshots_younger_than_a_year(profile):
    young = regular_history(start=date(2025, 10, 1), end=date(2026, 6, 30))
    old = fit(young, date(2026, 6, 30), profile)
    new = fit(young, date(2026, 6, 30), profile, RECENT)
    assert old.rates["win_within_horizon:S1"].source == "default"
    rate = new.rates["win_within_horizon:S1"]
    assert (
        rate.source == "fitted" and rate.value == 1
    )  # every deal is won after 45 days
    assert "cumulative incidence" in rate.definition
    created_to_win = new.new_pipeline.timing  # every deal wins 45 days after creation
    assert created_to_win.cdf(44) == 0 and created_to_win.cdf(45) == 1
    assert new.new_pipeline.cohort_size > 0 and new.new_pipeline.win_rate == 1


def test_snapshots_older_than_the_window_are_not_used(profile):
    data = regular_history()
    m = fit(data, date(2026, 6, 30), profile, RECENT)
    assert m.snapshot_count == 24
    assert "2024-06-30 to 2026-05-30" in m.rates["win_within_horizon:S1"].cohort


SHIFT = Company(
    slug="shift", prefix="H", start=date(2023, 7, 1), as_of=date(2026, 6, 30), seed=0,
    deals_per_month=40, advance=(0.6, 0.7, 0.75, 0.8, 0.9), dwell_days=(15, 20, 20, 15, 10),
    conversion_change=(date(2025, 6, 30), 0.6),
)  # fmt: skip


def test_recency_moves_toward_a_conversion_change_sooner(profile):
    after = float(np.prod([a * 0.6 for a in SHIFT.advance]))
    closer = 0
    for seed in range(10):
        data = generate(replace(SHIFT, seed=seed)).dataset
        old = fit(data, SHIFT.as_of, profile).rates["new_pipeline_win_rate"].value
        new = (
            fit(data, SHIFT.as_of, profile, RECENT).rates["new_pipeline_win_rate"].value
        )
        closer += abs(float(new) - after) < abs(float(old) - after)
    assert closer >= 9


def test_a_recency_fold_cannot_see_data_after_its_cutoff(profile):
    cutoff = date(2025, 3, 31)
    clean = regular_history()
    rewritten = [
        replace(d, arr=Decimal(1000), stage="Lost", is_won=False, is_closed=True)
        if d.close > cutoff or d.created > cutoff
        else d
        for d in clean.deals
    ]
    poisoned = Dataset(tuple(rewritten), clean.transitions, clean.observations)
    a = fold(clean, cutoff, (1, 3), profile, RECENT, draws=100)
    b = fold(poisoned, cutoff, (1, 3), profile, RECENT, draws=100)
    assert [(x.horizon, x.forecasts, x.range80) for x in a] == [
        (x.horizon, x.forecasts, x.range80) for x in b
    ]
    fa = fit(as_known_at(clean, cutoff), cutoff, profile, RECENT)
    fb = fit(as_known_at(poisoned, cutoff), cutoff, profile, RECENT)
    assert list(fa.rates) == list(fb.rates)


# ---------------------------------------------------------------- the paired comparison


def _bt(mae1, mae3, folds=6):
    def score(h, mae):
        return HorizonScore(
            h, folds, {MODEL: None if mae is None else Decimal(mae)}, {}, None, None
        )

    fold_list = tuple(
        Fold(date(2025, 1, 1) + timedelta(days=31 * i), h, Decimal(0), {}, None, None)
        for h in (1, 3)
        for i in range(folds)
    )
    return Backtest(
        fold_list, (score(1, mae1), score(3, mae3), score(6, None)), "no", "", ()
    )


def test_adopted_only_if_lower_at_both_one_and_three_months():
    assert compare_estimators(_bt(10, 10), _bt(9, 9)).adopted
    assert not compare_estimators(_bt(10, 10), _bt(9, 10)).adopted
    assert not compare_estimators(_bt(10, 10), _bt(11, 5)).adopted
    assert not compare_estimators(_bt(10, 10, folds=5), _bt(1, 1, folds=5)).adopted
    assert not compare_estimators(_bt(None, 10), _bt(9, 9)).adopted


def test_comparison_refuses_different_folds():
    with pytest.raises(ValueError, match="same folds"):
        compare_estimators(_bt(10, 10), _bt(9, 9, folds=7))


def test_matured_is_the_default_estimator():
    assert FitParams().estimator == MATURED and FitParams().recency_months == 24


# ---------------------------------------------------------------- in the report


@pytest.fixture(scope="module")
def sprout_report():
    from pathlib import Path

    from engine.tieout_core.report import build_report

    return build_report(
        Path("engine/config/profiles/sprout-labs"),
        Path("engine/data-v2/sprout-labs"),
        date(2026, 8, 31),
        draws=200,
    )


def test_report_scores_both_fits_on_the_same_folds_and_applies_the_rule(sprout_report):
    c = sprout_report["backtest"]["candidates"]["recency"]
    assert c["incumbent"] == MATURED and c["candidate"] == RECENCY
    lower = all(
        Decimal(c["mean_absolute_error"][h][RECENCY])
        < Decimal(c["mean_absolute_error"][h][MATURED])
        for h in ("1m", "3m")
    )
    assert c["adopted"] is lower
    in_use = RECENCY if lower else MATURED
    assert sprout_report["inputs"]["fit"] == in_use
    assert c["fit_in_use"] == in_use


def test_the_fit_in_use_drives_rates_backtest_and_verdict(sprout_report):
    c = sprout_report["backtest"]["candidates"]["recency"]
    in_use = sprout_report["inputs"]["fit"]
    rate = next(
        r for r in sprout_report["rates"] if r["name"] == "win_within_horizon:S1"
    )
    assert ("cumulative incidence" in rate["definition"]) is (in_use == RECENCY)
    scored = {f"{h['horizon_months']}m": h["mean_absolute_error"]["fitted model"]
              for h in sprout_report["backtest"]["horizons"]}  # fmt: skip
    for h in ("1m", "3m"):
        assert scored[h] == c["mean_absolute_error"][h][in_use]
    assert (
        sprout_report["verdicts"]["forecast_better_than_baselines"]["verdict"]
        == (sprout_report["backtest"]["verdict"])
    )

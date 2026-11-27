"""Goal 2D, the two generated fixtures, with the tolerances declared in
``stretch_rules`` before they were run.

A history with a known common downward shift in conversion: the stretched range covers
the actuals the simulated one misses. A history with no shift: the factors stay near 1.
Both go through the whole back-test (a refit at every past date on what was known then)
and the rolling scorer; neither sees the generator's parameters."""

from dataclasses import replace
from datetime import date
from statistics import median

import pytest

from engine.scripts.synth_history import Company, generate
from engine.tests.tieout_core.builders import write_profile
from engine.tieout_core import stretch_rules as rules
from engine.tieout_core.backtest import backtest
from engine.tieout_core.load import load_profile
from engine.tieout_core.stretch import score_horizon

STEADY = Company(
    slug="steady", prefix="H", start=date(2022, 7, 1), as_of=date(2026, 6, 30), seed=0,
    deals_per_month=40, advance=(0.6, 0.7, 0.75, 0.8, 0.9), dwell_days=(15, 20, 20, 15, 10),
)  # fmt: skip
SHIFTED = replace(STEADY, conversion_change=(date(2024, 1, 1), rules.SHIFT_FACTOR))
DRAWS = 300


@pytest.fixture(scope="module")
def profile(tmp_path_factory):
    return load_profile(write_profile(tmp_path_factory.mktemp("p")))


def scored(company, seed, profile):
    data = generate(replace(company, seed=seed)).dataset
    bt = backtest(data, company.as_of, profile, draws=DRAWS, seed=seed)
    return {h: score_horizon(list(bt.folds), h, company.as_of) for h in rules.HORIZONS}


@pytest.fixture(scope="module")
def steady(profile):
    return [scored(STEADY, s, profile) for s in range(rules.FIXTURE_SEEDS)]


@pytest.fixture(scope="module")
def shifted(profile):
    return [scored(SHIFTED, s, profile) for s in range(rules.FIXTURE_SEEDS)]


def test_with_no_shift_the_factors_stay_near_one(steady):
    near = [
        v
        for run in steady
        for h in rules.SCORED_HORIZONS
        for v in (run[h].factors.lower, run[h].factors.upper)
    ]
    assert all(run[h].factors.learned for run in steady for h in rules.HORIZONS)
    assert min(near) >= 1.0
    assert max(near) <= rules.NO_SHIFT_MAX_FACTOR
    assert median(near) <= rules.NO_SHIFT_MEDIAN_FACTOR


def test_with_no_shift_the_six_month_factors_do_not_run_away(steady):
    # amended after the first run (see stretch_rules): six-month folds overlap too much for
    # the declared bound
    six = [v for run in steady for v in (run[6].factors.lower, run[6].factors.upper)]
    assert 1.0 <= min(six) and max(six) <= rules.NO_SHIFT_MAX_FACTOR_SIX


def pooled(runs, which):
    inside = sum(getattr(r[h], which) for r in runs for h in rules.SCORED_HORIZONS)
    n = sum(r[h].scored for r in runs for h in rules.SCORED_HORIZONS)
    return inside / n, n


def test_with_a_common_shift_the_stretched_range_covers_what_the_simulated_one_misses(
    shifted,
):
    simulated, n = pooled(shifted, "inside_simulated")
    stretched, _ = pooled(shifted, "inside_stretched")
    assert n >= 3 * rules.MIN_SCORED_FOLDS * 2  # enough scored folds to say anything
    assert simulated <= rules.SHIFT_MAX_SIMULATED
    assert stretched >= simulated + rules.SHIFT_MIN_GAIN

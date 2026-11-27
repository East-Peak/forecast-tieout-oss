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


def test_the_declared_bound_does_not_hold_at_six_months_on_the_first_three_seeds(
    steady,
):
    """A recorded fact, not a pass: the criterion declared before the fixtures were run (every
    factor at most 1.35, the median of all at most 1.10) fails once six months is included.
    Observed on seeds 0, 1 and 2: largest six-month factor 1.594, median of all eighteen 1.1145."""
    every = [
        v
        for run in steady
        for h in rules.HORIZONS
        for v in (run[h].factors.lower, run[h].factors.upper)
    ]
    six = [v for run in steady for v in (run[6].factors.lower, run[6].factors.upper)]
    assert max(six) == pytest.approx(1.594, abs=0.001)
    assert median(every) == pytest.approx(1.1145, abs=0.001)
    assert max(six) > rules.NO_SHIFT_MAX_FACTOR
    assert median(every) > rules.NO_SHIFT_MEDIAN_FACTOR


def test_with_no_shift_the_six_month_factors_stay_under_the_exploratory_bound(steady):
    # EXPLORATORY: this bound was chosen after seeing the run above; it only says the factor
    # does not run away, and is not the criterion the stretch was declared against
    six = [v for run in steady for v in (run[6].factors.lower, run[6].factors.upper)]
    assert 1.0 <= min(six) and max(six) <= rules.EXPLORATORY_SIX_MONTH_MAX_FACTOR


@pytest.fixture(scope="module")
def fresh(profile):
    return [scored(STEADY, seed, profile) for seed in rules.FRESH_SEEDS]


def test_on_fresh_seeds_the_original_six_month_criterion_holds(fresh):
    """Seeds 101 to 103, declared in 8a43da2 before they were run, with the original criterion
    unamended. Observed: six-month factors 1.267, 1.0, 1.0, 1.338, 1.014, 1.0 (largest 1.338,
    median 1.007), so it holds, narrowly. The one-month factor on seed 101 (1.358) is over 1.35;
    that bound was not declared for fresh seeds at one month and is not asserted here."""
    six = [v for run in fresh for v in (run[6].factors.lower, run[6].factors.upper)]
    assert all(v is not None for v in six)
    assert max(six) == pytest.approx(1.338, abs=0.001)
    assert max(six) <= rules.FRESH_SIX_MONTH_MAX_FACTOR
    assert median(six) <= rules.FRESH_SIX_MONTH_MEDIAN_FACTOR


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

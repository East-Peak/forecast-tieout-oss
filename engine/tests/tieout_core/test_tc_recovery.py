"""Fixture recovery (design doc, builder check 8): the true rate lies inside the
fitted 95% range in at least 90% of 200 fixed-seed replicates.

Goal 2A adds a point check so a wide range cannot pass alone: across the 200
seeds the median absolute error of the point estimate is at most
POINT_TOLERANCE. It was stated before the recency fit was written, from the
sampling error of these fixtures (largest standard error 0.049, at S3 with
about 100 deals; an unbiased estimator's median absolute error is then about
0.033). Both estimators are held to it: the report uses whichever one the
back-test adopts for a company.
"""

import math
import statistics
from dataclasses import replace
from datetime import date

import pytest

from engine.scripts.synth_history import Company, generate, true_win_rates
from engine.tests.tieout_core.builders import write_profile
from engine.tieout_core.fit import MATURED, RECENCY, FitParams, fit
from engine.tieout_core.load import load_profile

POINT_TOLERANCE = 0.04
ESTIMATORS = (MATURED, RECENCY)

REPLICATES = 200
SEEDS = range(1000, 1000 + REPLICATES)
TRUTH_CO = Company(
    slug="recovery", prefix="R", start=date(2024, 1, 1), as_of=date(2026, 7, 31), seed=0,
    deals_per_month=25, advance=(0.6, 0.7, 0.75, 0.8, 0.9), dwell_days=(15, 20, 20, 15, 10),
)  # fmt: skip


def _recovered(fits, name, truth):
    """(replicates whose 95% range holds the truth, median absolute error)."""
    rates = [m.rates[name] for m in fits]
    inside = sum(r.low95 <= truth <= r.high95 for r in rates)
    error = statistics.median(abs(float(r.value) - truth) for r in rates)
    return inside, error


def _assert_recovered(fits, name, truth):
    inside, error = _recovered(fits, name, truth)
    assert inside >= 0.9 * REPLICATES, (
        f"{name}: true {truth:.3f} inside {inside}/{REPLICATES}"
    )
    assert error <= POINT_TOLERANCE, f"{name}: median absolute error {error:.4f}"


@pytest.fixture(scope="module", params=ESTIMATORS)
def fits(request, tmp_path_factory):
    profile = load_profile(write_profile(tmp_path_factory.mktemp("p")))
    params = FitParams(estimator=request.param)
    return [
        fit(
            generate(replace(TRUTH_CO, seed=s)).dataset, TRUTH_CO.as_of, profile, params
        )
        for s in SEEDS
    ]


@pytest.mark.parametrize("stage", ["S1", "S2", "S3", "S4", "S5"])
def test_stage_win_rates_are_recovered(fits, stage):
    _assert_recovered(
        fits, f"win_within_horizon:{stage}", true_win_rates(TRUTH_CO)[stage]
    )


def test_new_pipeline_win_rate_is_recovered(fits):
    _assert_recovered(fits, "new_pipeline_win_rate", math.prod(TRUTH_CO.advance))


def test_every_replicate_had_evidence(fits):
    assert all(
        m.rates[f"win_within_horizon:{s}"].source == "fitted"
        for m in fits
        for s in ("S1", "S5")
    )


def test_the_point_check_rejects_a_biased_estimate_with_a_wide_range(fits):
    """Mutation check: shift every estimate by 0.06 and widen its range to
    [0, 1]. Coverage still passes; the point check must not."""
    from dataclasses import replace as swap

    name, truth = "win_within_horizon:S3", true_win_rates(TRUTH_CO)["S3"]

    class Biased:
        def __init__(self, m):
            r = m.rates[name]
            self.rates = {
                name: swap(
                    r, value=r.value + type(r.value)("0.06"), low95=0.0, high95=1.0
                )
            }

    inside, error = _recovered([Biased(m) for m in fits], name, truth)
    assert inside == REPLICATES and error > POINT_TOLERANCE


# Slow stages: many wins land beyond the 365-day horizon, so the finite-horizon
# truth differs from the eventual win probability and a fit that ignored the
# horizon would miss it.
SLOW_CO = replace(
    TRUTH_CO, prefix="S", start=date(2022, 7, 1), deals_per_month=20,
    dwell_days=(60, 90, 90, 80, 60),
)  # fmt: skip


def finite_horizon_truth(company, stage_index, horizon=365, walks=200_000, seed=99):
    """P(win within ``horizon`` days | open in this stage at a snapshot), by
    simulating the generator's stage walk directly, independently of the fit.
    Dwell is exponential, so the time left in the current stage is too."""
    import random

    rng = random.Random(seed)
    wins = 0
    for _ in range(walks):
        t = rng.expovariate(1 / company.dwell_days[stage_index])
        won = rng.random() < company.advance[stage_index]
        for j in range(stage_index + 1, len(company.advance)):
            if not won:
                break
            t += max(1, math.ceil(rng.expovariate(1 / company.dwell_days[j])))
            won = rng.random() < company.advance[j]
        wins += won and math.ceil(t) <= horizon
    return wins / walks


@pytest.fixture(scope="module", params=ESTIMATORS)
def slow_fits(request, tmp_path_factory):
    profile = load_profile(write_profile(tmp_path_factory.mktemp("p")))
    params = FitParams(estimator=request.param)
    return [
        fit(generate(replace(SLOW_CO, seed=s)).dataset, SLOW_CO.as_of, profile, params)
        for s in SEEDS
    ]


@pytest.mark.parametrize("index", range(5))
def test_finite_horizon_win_rates_are_recovered(slow_fits, index):
    truth = finite_horizon_truth(SLOW_CO, index)
    if index == 0:
        assert truth < 0.8 * math.prod(SLOW_CO.advance)  # the case discriminates
    _assert_recovered(slow_fits, f"win_within_horizon:S{index + 1}", truth)

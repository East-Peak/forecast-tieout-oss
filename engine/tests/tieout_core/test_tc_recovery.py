"""Fixture recovery (design doc, builder check 8): the true rate lies inside the
fitted 95% range in at least 90% of 200 fixed-seed replicates."""

import math
from dataclasses import replace
from datetime import date

import pytest

from engine.scripts.synth_history import Company, generate, true_win_rates
from engine.tests.tieout_core.builders import write_profile
from engine.tieout_core.fit import fit
from engine.tieout_core.load import load_profile

REPLICATES = 200
SEEDS = range(1000, 1000 + REPLICATES)
TRUTH_CO = Company(
    slug="recovery", prefix="R", start=date(2024, 1, 1), as_of=date(2026, 7, 31), seed=0,
    deals_per_month=25, advance=(0.6, 0.7, 0.75, 0.8, 0.9), dwell_days=(15, 20, 20, 15, 10),
)  # fmt: skip


@pytest.fixture(scope="module")
def fits(tmp_path_factory):
    profile = load_profile(write_profile(tmp_path_factory.mktemp("p")))
    return [
        fit(generate(replace(TRUTH_CO, seed=s)).dataset, TRUTH_CO.as_of, profile)
        for s in SEEDS
    ]


@pytest.mark.parametrize("stage", ["S1", "S2", "S3", "S4", "S5"])
def test_stage_win_rates_are_recovered(fits, stage):
    truth = true_win_rates(TRUTH_CO)[stage]
    inside = sum(
        m.rates[f"win_within_horizon:{stage}"].low95
        <= truth
        <= m.rates[f"win_within_horizon:{stage}"].high95
        for m in fits
    )
    assert inside >= 0.9 * REPLICATES, (
        f"{stage}: true {truth:.3f} inside the range {inside}/{REPLICATES}"
    )


def test_new_pipeline_win_rate_is_recovered(fits):
    truth = math.prod(TRUTH_CO.advance)
    inside = sum(
        m.rates["new_pipeline_win_rate"].low95
        <= truth
        <= m.rates["new_pipeline_win_rate"].high95
        for m in fits
    )
    assert inside >= 0.9 * REPLICATES, (
        f"true {truth:.3f} inside the range {inside}/{REPLICATES}"
    )


def test_every_replicate_had_evidence(fits):
    assert all(
        m.rates[f"win_within_horizon:{s}"].source == "fitted"
        for m in fits
        for s in ("S1", "S5")
    )


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


@pytest.fixture(scope="module")
def slow_fits(tmp_path_factory):
    profile = load_profile(write_profile(tmp_path_factory.mktemp("p")))
    return [
        fit(generate(replace(SLOW_CO, seed=s)).dataset, SLOW_CO.as_of, profile)
        for s in SEEDS
    ]


@pytest.mark.parametrize("index", range(5))
def test_finite_horizon_win_rates_are_recovered(slow_fits, index):
    stage = f"S{index + 1}"
    truth = finite_horizon_truth(SLOW_CO, index)
    if index == 0:
        assert truth < 0.8 * math.prod(SLOW_CO.advance)  # the case discriminates
    inside = sum(
        m.rates[f"win_within_horizon:{stage}"].low95
        <= truth
        <= m.rates[f"win_within_horizon:{stage}"].high95
        for m in slow_fits
    )
    assert inside >= 0.9 * REPLICATES, (
        f"{stage}: truth {truth:.3f} inside {inside}/{REPLICATES}"
    )

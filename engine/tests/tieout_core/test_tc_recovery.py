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

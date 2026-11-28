"""The simulated company and its ground truth (the stock-and-flow truth as a Snapshot)."""

from datetime import date
from functools import cache

import numpy as np

from engine.harness.contract.snapshot import Snapshot, flow_check
from engine.harness.synth.params import CompanyParams
from engine.harness.synth.run import run_company
from engine.harness.synth.truth import load_truth, save_truth

SMALL_START, SMALL_END = date(2024, 2, 1), date(2025, 7, 31)


def small_params(variant: str) -> CompanyParams:
    """A short window (18 months, warm-up included) with the full-size company."""
    return CompanyParams.for_variant(variant, start=SMALL_START, end=SMALL_END)


@cache
def small_company(variant: str, seed: int = 1):
    return run_company(small_params(variant), seed)


def test_truth_passes_flow_check_with_nothing_unavailable():
    for variant in ("demand_limited", "capacity_constrained"):
        truth = small_company(variant).truth
        report = flow_check(truth)
        assert report.violations == [], report.violations[:3]
        assert report.unavailable == []
        assert report.checked > 1000


def test_truth_has_real_activity_in_every_measure():
    truth = small_company("capacity_constrained").truth
    for name in (
        "leads",
        "mqls",
        "arrivals",
        "admissions",
        "wins",
        "losses",
        "bookings_cents",
        "spend_cents",
    ):
        assert getattr(truth, name).values.sum() > 0, name
    assert truth.exits.values.sum() > 0
    assert truth.reopened.values.sum() > 0 and truth.deleted.values.sum() > 0
    assert truth.months[0] == "2024-02" and truth.months[-1] == "2025-07"
    assert any(lane.endswith("source=Partner") for lane in truth.lanes)


def test_every_lane_belongs_to_a_team_and_directly_created_lanes_have_no_queue():
    truth = small_company("demand_limited").truth
    assert set(truth.lane_team) <= set(truth.teams)
    for i, lane in enumerate(truth.lanes):
        if lane.endswith(("source=Partner", "source=SelfSourced")):
            assert truth.queue_end.values[i].sum() == 0
            assert (truth.arrivals.values[i] == truth.admissions.values[i]).all()


def test_truth_round_trips_through_its_file(tmp_path):
    truth = small_company("capacity_constrained").truth
    path = tmp_path / "snapshot.json"
    save_truth(truth, path)
    loaded = load_truth(path)
    assert isinstance(loaded, Snapshot) and loaded.lanes == truth.lanes
    for name in (
        "wins",
        "bookings_cents",
        "queue_end",
        "exits",
        "carrying_capacity",
        "ramp_exposure",
    ):
        assert np.array_equal(
            getattr(loaded, name).values, getattr(truth, name).values
        ), name
    assert loaded.outstanding_episodes == truth.outstanding_episodes
    assert loaded.roster == truth.roster
    assert flow_check(loaded).violations == []

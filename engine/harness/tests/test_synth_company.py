"""The simulated company and its ground truth (the stock-and-flow truth as a Snapshot)."""

import sys
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
    return CompanyParams.for_variant(
        variant,
        start=SMALL_START,
        end=SMALL_END,
        p_delete=0.03,
        attrition_annual={
            "AE": 0.5,
            "BDR": 0.2,
        },  # departures happen, so inheritance is exercised
    )


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
    assert truth.reopened.values.sum() > 0
    assert any(o.dead for o in small_company("capacity_constrained").sim.opps)
    assert truth.months[0] == "2024-02" and truth.months[-1] == "2025-07"
    assert any(lane.endswith("source=Partner") for lane in truth.lanes)


def test_every_lane_belongs_to_a_team_and_only_self_sourcing_bypasses_the_queue():
    truth = small_company("capacity_constrained").truth
    assert set(truth.lane_team) <= set(truth.teams)
    for i, lane in enumerate(truth.lanes):
        if lane.endswith("source=SelfSourced"):
            assert truth.queue_end.values[i].sum() == 0
            assert (truth.arrivals.values[i] == truth.admissions.values[i]).all()
    partner = [
        i for i, lane in enumerate(truth.lanes) if lane.endswith("source=Partner")
    ]
    arrivals = truth.arrivals.values[partner].sum()
    # partner referrals are demand episodes: some are rejected for fit, and they can queue
    assert truth.exits.values[partner].sum() > 0
    assert arrivals > truth.admissions.values[partner].sum()


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


def test_synth_depends_only_on_the_standard_library_numpy_and_the_contract():
    from engine.harness.tests.test_import_rules import imported_modules, touches

    modules = imported_modules("synth")
    assert touches(modules, "planning") == [] and touches(modules, "tieout_core") == []
    absolute = {m.split(".")[0] for m in modules if not m.startswith(".")}
    assert absolute <= set(sys.stdlib_module_names) | {"numpy"}, absolute
    assert not any(m.startswith("engine") for m in modules)


def capacity_expiry_share(variant: str, seed: int) -> float:
    """Share of FY25 team-months in which some demand expired for lack of capacity."""
    truth = run_company(CompanyParams.for_variant(variant), seed).truth
    first, last = truth.months.index("2025-02"), truth.months.index("2026-01") + 1
    expired = truth.exits.values[
        :, first:last, truth.exit_reasons.index("expired_no_capacity")
    ]
    shares = [
        float(
            (
                expired[[i for i, t in enumerate(truth.lane_team) if t == team]].sum(
                    axis=0
                )
                > 0
            ).mean()
        )
        for team in truth.teams
    ]
    return sum(shares) / len(shares)


def test_capacity_binds_for_sustained_stretches_only_in_the_constrained_company():
    # Stated before running: constrained, at least a third of FY25 team-months expire demand for
    # capacity in every seed 1 to 5; demand-limited, at most a tenth on average and most seeds none.
    constrained = [
        capacity_expiry_share("capacity_constrained", s) for s in range(1, 6)
    ]
    limited = [capacity_expiry_share("demand_limited", s) for s in range(1, 6)]
    print(
        "capacity expiry share by seed",
        {"constrained": constrained, "limited": limited},
    )
    assert min(constrained) >= 1 / 3
    assert sum(limited) / 5 <= 0.10 and sum(share == 0 for share in limited) >= 3

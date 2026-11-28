"""Paired counterfactuals: common random numbers, no-op identity, and the hiring effect."""

import json
from datetime import date
from functools import cache

from engine.harness.synth.cases import named_cases
from engine.harness.synth.cli import generate, tree_hash
from engine.harness.synth.counterfactual import (
    change_spend,
    fiscal_year_total,
    paired_counterfactual,
    slip_hire,
)
from engine.harness.synth.params import CompanyParams, Intervention
from engine.harness.synth.run import run_company
from engine.harness.tests.test_synth_company import SMALL_END, small_params


def keyed(company):
    return {lead.key: lead for lead in company.sim.leads}


def named_hire(params, seed):
    base = run_company(params, seed)
    return named_cases(base)["counterfactual_hire"]["req_id"]


def test_a_no_op_intervention_reproduces_the_base_run_byte_for_byte(tmp_path):
    params = small_params("capacity_constrained")
    dates = [date(2025, 1, 24), SMALL_END]
    generate(params, 3, tmp_path / "base", dates)
    no_ops = {
        "zero_slip": slip_hire(named_hire(params, 3), 0),
        "flat_spend": change_spend("Paid Social", date(2025, 1, 1), 1.0),
        "empty": Intervention(),
    }
    for name, iv in no_ops.items():
        generate(params, 3, tmp_path / name, dates, iv)
        assert tree_hash(tmp_path / name) == tree_hash(tmp_path / "base"), name
    generate(params, 3, tmp_path / "real", dates, slip_hire(named_hire(params, 3), 120))
    assert tree_hash(tmp_path / "real") != tree_hash(tmp_path / "base")


def test_a_slipped_hire_changes_only_what_depends_on_it():
    pair = paired_counterfactual(
        small_params("capacity_constrained"),
        4,
        slip_hire(named_hire(small_params("capacity_constrained"), 4), 120),
    )
    base, alt = pair.truths
    assert (
        base.carrying_capacity.values.tolist() != alt.carrying_capacity.values.tolist()
    )
    # demand and spend are untouched: the same leads, with the same latent fates
    for name in ("leads", "mqls", "spend_cents"):
        assert (
            getattr(base, name).values.tolist() == getattr(alt, name).values.tolist()
        ), name
    a, b = keyed(pair.base), keyed(pair.alt)
    assert a.keys() == b.keys()
    same_deal = [
        (x, y)
        for x, y in zip(
            sorted(pair.base.sim.opps, key=lambda o: o.lead.key if o.lead else ()),
            sorted(pair.alt.sim.opps, key=lambda o: o.lead.key if o.lead else ()),
            strict=False,
        )
        if x.lead and y.lead and x.lead.key == y.lead.key
    ]
    assert same_deal and all(
        x.list_cents == y.list_cents and x.base_days == y.base_days
        for x, y in same_deal
    )


def test_more_spend_only_adds_leads_and_leaves_earlier_months_alone():
    params = small_params("demand_limited")
    pair = paired_counterfactual(
        params, 2, change_spend("Paid Search SMB", date(2024, 10, 1), 1.5)
    )
    base, alt = pair.truths
    assert keyed(pair.base).keys() <= keyed(pair.alt).keys()
    cut = base.months.index("2024-10")
    assert base.mqls.values[:, :cut].tolist() == alt.mqls.values[:, :cut].tolist()
    assert alt.mqls.values.sum() > base.mqls.values.sum()
    assert alt.spend_cents.values.sum() > base.spend_cents.values.sum()


@cache
def hiring_effect(seed: int) -> tuple[int, int]:
    """FY25 bookings in cents without and with a 120-day slip of the named hire (constrained company)."""
    params = CompanyParams.for_variant("capacity_constrained")
    base = run_company(params, seed)
    hire = named_cases(base)["counterfactual_hire"]
    alt = run_company(
        params, seed, slip_hire(hire["req_id"], hire["default_slip_days"])
    )
    return tuple(
        fiscal_year_total(c.truth, "bookings_cents", 2025) for c in (base, alt)
    )


def test_slipping_one_hire_120_days_costs_bookings_in_the_constrained_company():
    deltas = {
        seed: hiring_effect(seed)[1] - hiring_effect(seed)[0] for seed in range(1, 6)
    }
    print(
        "FY25 bookings change (cents) by seed:",
        deltas,
        "base:",
        {s: hiring_effect(s)[0] for s in deltas},
    )
    mean = sum(deltas.values()) / len(deltas)
    base_mean = sum(hiring_effect(s)[0] for s in deltas) / len(deltas)
    assert mean < -0.005 * base_mean, (
        mean,
        base_mean,
    )  # a clearly nonzero cost: at least half a percent of the year
    assert json.dumps(sorted(deltas))  # seeds 1 to 5 only

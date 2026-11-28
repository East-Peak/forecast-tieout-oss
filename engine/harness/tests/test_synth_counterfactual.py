"""Paired counterfactuals (one realization) and the expected-effect benchmark."""

from datetime import date

from engine.harness.synth import counterfactual
from engine.harness.synth.cases import named_cases
from engine.harness.synth.cli import generate, tree_hash
from engine.harness.synth.counterfactual import (
    change_spend,
    expected_effect,
    paired_counterfactual,
    slip_hire,
)
from engine.harness.synth.params import CompanyParams, Intervention
from engine.harness.synth.people import day_of
from engine.harness.synth.run import run_company
from engine.harness.tests.test_synth_company import SMALL_END, small_params


def keyed(company):
    return {lead.key: lead for lead in company.sim.leads}


def benchmark_hire(params, seed, team="AE-SMB"):
    return named_cases(run_company(params, seed))["benchmark_hires"][team]["req_id"]


def test_the_paired_counterfactual_says_it_is_one_realization():
    assert "one realization" in counterfactual.paired_counterfactual.__doc__.lower()
    assert (
        "not an expected value" in counterfactual.paired_counterfactual.__doc__.lower()
    )


def test_a_no_op_intervention_reproduces_the_base_run_byte_for_byte(tmp_path):
    params = small_params("capacity_constrained")
    dates = [date(2025, 1, 24), SMALL_END]
    generate(params, 3, tmp_path / "base", dates)
    no_ops = {
        "zero_slip": slip_hire(benchmark_hire(params, 3), 0),
        "flat_spend": change_spend("Paid Social", date(2025, 1, 1), 1.0),
        "empty": Intervention(),
    }
    for name, iv in no_ops.items():
        generate(params, 3, tmp_path / name, dates, iv)
        assert tree_hash(tmp_path / name) == tree_hash(tmp_path / "base"), name
    generate(
        params, 3, tmp_path / "real", dates, slip_hire(benchmark_hire(params, 3), 120)
    )
    assert tree_hash(tmp_path / "real") != tree_hash(tmp_path / "base")


def test_a_slipped_hire_changes_only_what_depends_on_it():
    params = small_params("capacity_constrained")
    pair = paired_counterfactual(params, 4, slip_hire(benchmark_hire(params, 4), 120))
    base, alt = pair.truths
    assert (
        base.carrying_capacity.values.tolist() != alt.carrying_capacity.values.tolist()
    )
    for name in ("leads", "mqls", "spend_cents"):
        assert (
            getattr(base, name).values.tolist() == getattr(alt, name).values.tolist()
        ), name
    assert keyed(pair.base).keys() == keyed(pair.alt).keys()
    deals_a = {o.key: o for o in pair.base.sim.opps}
    deals_b = {o.key: o for o in pair.alt.sim.opps}
    common = deals_a.keys() & deals_b.keys()
    assert len(common) > 50
    # a deal's size and base cycle never depend on who took it or when
    assert all(
        deals_a[k].list_cents == deals_b[k].list_cents
        and deals_a[k].base_days == deals_b[k].base_days
        for k in common
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


def test_a_fork_keeps_the_past_and_redraws_the_future_per_replicate():
    params = CompanyParams.for_variant(
        "capacity_constrained", start=date(2024, 2, 1), end=date(2025, 7, 31)
    )
    fork = day_of(date(2025, 1, 24))
    runs = [run_company(params, 2, None, r, fork) for r in (0, 1)]
    past = [{k.key for k in c.sim.leads if k.key[2] < fork} for c in runs]
    future = [{k.key for k in c.sim.leads if k.key[2] >= fork} for c in runs]
    assert past[0] == past[1] and len(past[0]) > 500
    assert future[0] != future[1]
    assert (
        run_company(params, 2, None, 0, fork).sim.fingerprint()
        == runs[0].sim.fingerprint()
    )


def test_the_expected_effect_of_a_slip_is_a_replicated_mean_with_a_standard_error():
    params = CompanyParams.for_variant("capacity_constrained")
    hire = benchmark_hire(params, 1)
    effect = expected_effect(params, 1, slip_hire(hire, 120), replicates=12, workers=6)
    assert len(effect.diffs) == 12 and effect.replicates == 12
    assert effect.fork_date == params.plan_date and effect.measure == "bookings_cents"
    assert abs(effect.mean - sum(effect.diffs) / 12) < 1e-6 and effect.se > 0
    assert (
        effect.mean < -2 * effect.se
    )  # a slipped SMB hire clearly costs bookings when capacity binds
    again = expected_effect(params, 1, slip_hire(hire, 120), replicates=12, workers=1)
    assert again.diffs == effect.diffs  # deterministic, whatever the worker count

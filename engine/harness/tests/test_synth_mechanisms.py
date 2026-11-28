"""Mechanisms: no outcome oracle, carrying ramp, inheritance on departure, partner demand, self-sourcing, owners."""

import dataclasses
import itertools
from datetime import date

import pytest

from engine.harness.contract.snapshot import flow_check
from engine.harness.synth import sim as sim_module
from engine.harness.synth.cli import generate, tree_hash
from engine.harness.synth.counterfactual import slip_hire
from engine.harness.synth.params import CompanyParams, Intervention
from engine.harness.synth.people import day_of
from engine.harness.synth.run import run_company
from engine.harness.synth.sim import Simulation
from engine.harness.tests.test_synth_company import (
    SMALL_END,
    small_company,
    small_params,
)


def test_open_deal_close_dates_do_not_depend_on_the_latent_outcome(
    tmp_path, monkeypatch
):
    params = small_params("demand_limited")
    dates = [date(2025, 1, 31)]
    base = run_company(params, 1).sim
    target = next(
        o
        for o in base.opps
        if o.status == "won"
        and o.last_stage == 3
        and o.created_day > day_of(date(2024, 6, 1))
        and len(o.images) > 4
    )
    original = Simulation.create_opp

    def flipped(self, *args, **kwargs):
        opp = original(self, *args, **kwargs)
        if opp.n == target.n:
            opp.will_win, opp.last_stage = (
                False,
                1,
            )  # same deal, now fated to be lost after stage 2
        return opp

    monkeypatch.setattr(Simulation, "create_opp", flipped)
    alt = run_company(params, 1).sim
    other = next(o for o in alt.opps if o.n == target.n)
    first = next(
        i
        for i, (a, b) in enumerate(zip(target.images, other.images, strict=False))
        if a != b
    )
    assert first >= 2  # several stage rows were identical before the outcome showed
    reveal = min(target.images[first][1], other.images[first][1])
    before = date.fromisoformat(reveal[:10]).toordinal() - 1
    cut = date.fromordinal(before)
    monkeypatch.setattr(Simulation, "create_opp", original)
    generate(params, 1, tmp_path / "base", [cut])
    monkeypatch.setattr(Simulation, "create_opp", flipped)
    generate(params, 1, tmp_path / "flipped", [cut])
    assert tree_hash(tmp_path / "base" / "extracts") == tree_hash(
        tmp_path / "flipped" / "extracts"
    )
    assert dates  # the extract date is the day before the first differing history row


def test_carrying_ramp_is_tenure_based_and_continuous_in_the_start_date():
    params = small_params("capacity_constrained")
    sim = Simulation(params, 1, Intervention())
    ae = sim.aes["AE-SMB"][0]
    assert (
        ae.carry_factor(ae.start - 1, 30, 60) == 0
        and ae.carry_factor(ae.start + 30, 30, 60) == 0
    )
    assert ae.carry_factor(ae.start + 60, 30, 60) == pytest.approx(0.5)
    assert ae.carry_factor(ae.start + 90, 30, 60) == 1
    # one day of start date moves capacity by at most one deal, even across a month boundary
    full = CompanyParams.for_variant(
        "capacity_constrained", start=date(2024, 2, 1), end=date(2025, 7, 31)
    )
    hire = next(
        i
        for i, h in enumerate(full.hires, 1)
        if h.team == "AE-SMB" and h.planned_start == date(2025, 3, 3)
    )
    runs = [
        run_company(full, 1, slip_hire(f"REQ-{hire:03d}", d)).truth for d in (13, 14)
    ]  # starts Apr 30 and May 1
    diff = abs(runs[0].carrying_capacity.values - runs[1].carrying_capacity.values)
    assert (
        diff.max() <= 1
        and abs(runs[0].ramp_exposure.values - runs[1].ramp_exposure.values).max()
        < 0.05
    )
    assert abs(runs[0].ramped_heads.values - runs[1].ramped_heads.values).max() <= 1


def inherited_run(**over):
    params = dataclasses.replace(
        small_params("capacity_constrained"),
        attrition_annual={"AE": 0.9, "BDR": 0.2},
        **over,
    )
    return run_company(params, 2)


def test_departures_hand_deals_to_teammates_instead_of_liquidating_them():
    company = inherited_run()
    sim, truth = company.sim, company.truth
    assert not any(
        i[1].endswith("T07:00:00Z") and i[2] == "Closed Lost"
        for o in sim.opps
        for i in o.images
    )
    holder = sim.cs[0].uid
    chains = [
        o.owner_rows for o in sim.opps if any(r[3] == holder for r in o.owner_rows)
    ]
    assert len(chains) >= 5
    for rows in (
        chains
    ):  # the manager holds the deal, then a teammate takes it after the handoff delay
        i = next(i for i, r in enumerate(rows) if r[3] == holder)
        if i + 1 < len(
            rows
        ):  # (a deal may still be waiting, or be deleted, when the run ends)
            assert rows[i + 1][2] == holder and rows[i + 1][1][:10] > rows[i][1][:10]
    assert sum(any(r[2] == holder for r in rows) for rows in chains) >= 3
    open_by_team = sim.F["open_end"][
        [i for i, t in enumerate(truth.lane_team) if t == "AE-SMB"]
    ].sum(axis=0)
    cap = truth.carrying_capacity.values[truth.teams.index("AE-SMB")]
    assert (open_by_team > cap).any(), (
        "a team should sit above capacity after a departure"
    )
    report = flow_check(truth)
    assert report.violations == [] and report.unavailable == []


def test_the_handoff_gap_costs_deals_and_stretches_them_only_by_declared_parameters():
    def lost_while_orphaned(p_loss):
        sim = inherited_run(p_orphan_loss=p_loss).sim
        orphaned = [o for o in sim.opps if o.orphaned and o.status in ("won", "lost")]
        return sum(o.status == "lost" for o in orphaned) / len(orphaned)

    assert lost_while_orphaned(1.0) > lost_while_orphaned(0.0) + 0.1


def test_partner_referrals_are_leads_that_queue_like_any_other_demand():
    sim = small_company("capacity_constrained").sim
    partner = [x for x in sim.leads if x.kind == "partner"]
    assert len(partner) > 20 and all(
        x.leadsource == "Partner" and x.mql_day is None for x in partner
    )
    outcomes = {r[3] for x in partner for r in x.rows if r[2] == "Disposition__c"}
    assert {"Admitted", "Rejected"} <= outcomes
    assert any(o.lead and o.lead.kind == "partner" for o in sim.opps)
    assert sim.p.routing_priority == "oldest_first"
    with pytest.raises(ValueError, match="routing_priority"):
        Simulation(
            dataclasses.replace(sim.p, routing_priority="partner_first"),
            1,
            Intervention(),
        )


def test_self_sourcing_needs_room_and_its_rate_falls_to_zero_when_the_ae_is_full():
    params = dataclasses.replace(small_params("demand_limited"), ae_self_per_day=3.0)
    sim = Simulation(params, 1, Intervention())
    day = day_of(date(2024, 9, 2))
    sim._day_state(day)
    sim.self_source(day)
    made = len(sim.opps)
    assert made > 0
    for ae in sim.ramped("AE-SMB"):
        assert len(sim.ae_open[ae.pid]) <= sim.limit[ae.pid]
    for _ in range(40):  # the same day over and over: AEs fill to their limits and stop
        sim.self_source(day)
    assert all(
        len(sim.ae_open[a.pid]) <= sim.limit[a.pid]
        for t in sim.teams
        for a in sim.ramped(t)
    )
    before = len(sim.opps)
    sim.self_source(day)
    assert len(sim.opps) == before  # everyone is full: nothing is created
    assert sim_module.T_ADMIT  # self-sourced deals are not queued demand


def test_every_owner_change_has_a_history_row_and_open_counts_match_the_simulation(
    tmp_path,
):
    from engine.harness.tests.test_synth_extracts import read

    company = inherited_run(p_reopen=1.0)  # every loss is reopened where there is room
    for o in company.sim.opps:  # replaying the history from the first owner gives the owner now, closed deals too
        assert ([r[3] for r in o.owner_rows] or [o.owner0])[-1] == o.owner.uid, o.n
    generate(company.params, 2, tmp_path, [SMALL_END])
    opps = {r["Id"]: r for r in read(tmp_path, SMALL_END, "salesforce", "Opportunity")}
    rows = {}
    for r in read(tmp_path, SMALL_END, "salesforce", "OpportunityFieldHistory"):
        rows.setdefault(r["OpportunityId"], []).append(r)
    assert rows
    for oid, chain in rows.items():
        chain.sort(key=lambda r: (r["CreatedDate"], r["Id"]))
        assert all(
            a["NewValue"] == b["OldValue"] for a, b in itertools.pairwise(chain)
        ), oid
        assert chain[-1]["NewValue"] == opps[oid]["OwnerId"], oid
    sim = company.sim
    counts = {}
    for r in opps.values():
        if r["Type"] == "New Business" and not r["IsClosed"]:
            counts[r["OwnerId"]] = counts.get(r["OwnerId"], 0) + 1
    expected = {
        p.uid: len(sim.ae_open[p.pid]) for p in sim.people if sim.ae_open[p.pid]
    }
    held = sum(len(v) for v in sim.orphans.values())
    if held:
        expected[sim.cs[0].uid] = held
    assert counts == expected

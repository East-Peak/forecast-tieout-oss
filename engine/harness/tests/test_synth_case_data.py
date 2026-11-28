"""Named cases hold in the observable data (extracts and observable truth), on seeds 1 to 3."""

import json
import tempfile
from collections import defaultdict
from functools import cache
from pathlib import Path

import numpy as np
import pytest

from engine.harness.synth.cli import generate
from engine.harness.synth.params import CompanyParams
from engine.harness.synth.records import extract_folder
from engine.harness.synth.truth import load_truth

PARAMS = CompanyParams.for_variant("demand_limited")
PLAN, FINAL = PARAMS.plan_date, __import__("datetime").date(2026, 1, 31)
SEEDS = (1, 2, 3)


@cache
def estate(seed):
    out = Path(tempfile.mkdtemp(prefix="synth_cases_"))
    generate(PARAMS, seed, out, [PLAN, FINAL])
    return out, json.loads((out / "truth" / "manifest.json").read_text())


def read(out, when, system, name):
    path = extract_folder(out, when) / system / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def observable(seed):
    return load_truth(estate(seed)[0] / "truth" / "observable_snapshot.json")


def lane_series(truth, lane, name):
    return getattr(truth, name).values[truth.lanes.index(lane)]


def test_the_plateaued_lane_stops_growing_across_the_whole_named_lane():
    before, after = [], []
    for seed in SEEDS:
        out, manifest = estate(seed)
        case = manifest["named_cases"]["plateaued_lane"]
        truth = observable(seed)
        series = lane_series(truth, case["lane"], "mqls").astype(float)
        cut = truth.months.index(case["plateau_from"][:7])
        before.append(series[cut - 9 : cut].sum() / series[cut - 24 : cut - 15].sum())
        after.append(series[-9:].sum() / series[cut : cut + 9].sum())
        # nothing else feeds the lane: every inbound lead for it comes from the plateaued program
        campaigns = {
            r["Id"]: r["Name"] for r in read(out, FINAL, "salesforce", "Campaign")
        }
        members = {
            c["CampaignId"] for c in read(out, FINAL, "salesforce", "CampaignMember")
        }
        inbound_smb = [m for m in members if campaigns[m] == case["campaign"]]
        assert inbound_smb
    assert np.mean(before) > 1.25, before  # it grew into the plateau
    assert np.mean(after) < 1.12, after  # and stopped


def people_by_email(out):
    return {p["email"]: p for p in read(out, FINAL, "people_system", "people")}


def smb_outbound_deals(out, when):
    people = people_by_email(out)
    segment = {
        u["Id"]: people[u["Email"]]["segment"]
        for u in read(out, when, "salesforce", "User")
        if u["Email"] in people and people[u["Email"]]["role"] == "BDR"
    }
    history = defaultdict(list)
    for h in read(out, when, "salesforce", "OpportunityHistory"):
        history[h["OpportunityId"]].append(h)
    deals = []
    for o in read(out, when, "salesforce", "Opportunity"):
        if o["Type"] == "New Business" and segment.get(o["Sourcing_User__c"]) == "SMB":
            rows = sorted(history[o["Id"]], key=lambda h: (h["CreatedDate"], h["Id"]))
            deals.append(
                (
                    o["CreatedDate"][:10],
                    o["StageName"],
                    next(
                        (
                            h["CreatedDate"][:10]
                            for h in rows
                            if h["StageName"].startswith("Closed")
                        ),
                        None,
                    ),
                )
            )
    return deals


def rate(deals):
    done = [d for d in deals if d[1].startswith("Closed")]
    return sum(d[1] == "Closed Won" for d in done) / len(done)


def test_the_step_change_shows_in_outcomes_and_a_trailing_rate_at_the_plan_date_understates_it():
    gains, understated = [], []
    for seed in SEEDS:
        out, manifest = estate(seed)
        step = manifest["named_cases"]["improvement_understated"]["step_on"]
        final = smb_outbound_deals(out, FINAL)
        old = [d for d in final if "2023-08-01" <= d[0] < step]
        new = [d for d in final if d[0] >= step]
        # the trailing rate as the plan extract knew it: closings in the 12 months to the plan date
        known = smb_outbound_deals(out, PLAN)
        trailing = [
            d
            for d in known
            if d[1].startswith("Closed")
            and d[2]
            and "2024-01-24" < d[2] <= PLAN.isoformat()
        ]
        gains.append(rate(new) - rate(old))
        understated.append(rate(new) - rate(trailing))
        assert manifest["named_cases"]["improvement_understated"][
            "trailing_12m_win_rate_at_plan_date"
        ] == pytest.approx(rate(trailing), abs=0.08)
    assert np.mean(gains) > 0.05, gains
    assert np.mean(understated) > 0.02, understated


@pytest.mark.parametrize("seed", SEEDS)
def test_the_thin_slice_is_thin_in_the_observable_truth(seed):
    truth = observable(seed)
    created = lane_series(
        truth, "segment=Enterprise;source=Partner", "opportunities_created"
    )
    fy24 = [i for i, m in enumerate(truth.months) if "2024-02" <= m <= "2025-01"]
    assert 1 <= created[fy24].sum() <= 12
    others = [
        truth.opportunities_created.values[i, fy24].sum()
        for i in range(len(truth.lanes))
        if truth.lanes[i].startswith("segment=SMB")
    ]
    assert created[fy24].sum() < min(x for x in others if x > 50)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_recent_cohort_is_immature_in_the_plan_extract(seed):
    out, _manifest = estate(seed)
    young = [
        o
        for o in read(out, PLAN, "salesforce", "Opportunity")
        if o["Type"] == "New Business"
        and "2024-11-26" <= o["CreatedDate"][:10] <= PLAN.isoformat()
    ]
    older = [
        o
        for o in read(out, PLAN, "salesforce", "Opportunity")
        if o["Type"] == "New Business"
        and "2024-02-01" <= o["CreatedDate"][:10] < "2024-06-01"
    ]
    assert len(young) > 50
    share = sum(o["IsClosed"] for o in young) / len(young)
    assert share < 0.6 and share < sum(o["IsClosed"] for o in older) / len(older) - 0.3


@pytest.mark.parametrize("seed", SEEDS)
def test_missing_attribution_is_in_the_records_and_in_its_own_lane(seed):
    out, manifest = estate(seed)
    leads = read(out, FINAL, "salesforce", "Lead")
    members = {m["LeadId"] for m in read(out, FINAL, "salesforce", "CampaignMember")}
    mql = [x for x in leads if x["MQL_Date__c"]]
    share = sum(x["Id"] not in members for x in mql) / len(mql)
    assert 0.02 < share < 0.09
    bare = [
        o
        for o in read(out, FINAL, "salesforce", "Opportunity")
        if o["Type"] == "New Business"
        and not o["CampaignId"]
        and not o["LeadSource"]
        and not o["Sourcing_User__c"]
    ]
    truth = observable(seed)
    in_lane = sum(
        truth.opportunities_created.values[i].sum()
        for i, lane in enumerate(truth.lanes)
        if lane.endswith("source=Unknown")
    )
    ghosts = manifest["observable"]["ghost_lead_derived_opportunities"]
    assert len(bare) > 30 and abs(in_lane - len(bare)) <= ghosts


@pytest.mark.parametrize("seed", SEEDS)
def test_one_very_large_deal_stands_alone_in_the_extract(seed):
    out, manifest = estate(seed)
    whale = manifest["named_cases"]["very_large_deal"]
    big = [
        o
        for o in read(out, FINAL, "salesforce", "Opportunity")
        if o["Type"] == "New Business" and o["Amount"] >= 2_500_000
    ]
    assert [o["Id"] for o in big] == [whale["opportunity_id"]]
    assert big[0]["Amount"] == whale["amount_cents"] / 100 and big[0]["IsWon"]
    rest = sorted(
        o["Amount"]
        for o in read(out, FINAL, "salesforce", "Opportunity")
        if o["Type"] == "New Business"
    )[-2]
    assert big[0]["Amount"] > 2 * rest


@pytest.mark.parametrize("seed", SEEDS)
def test_hires_slip_between_the_requisition_and_the_start_date(seed):
    out, _ = estate(seed)
    people = {p["person_id"]: p for p in read(out, FINAL, "people_system", "people")}
    slips = [
        (date_diff(people[r["person_id"]]["start_date"], r["planned_start"]))
        for r in read(out, FINAL, "people_system", "requisitions")
        if r["status"] == "filled"
    ]
    assert sum(s >= 14 for s in slips) >= 5 and max(slips) >= 75


def date_diff(later, earlier):
    from datetime import date

    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days

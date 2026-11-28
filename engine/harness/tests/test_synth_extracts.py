"""The extract writer: each extract is a complete, valid snapshot of what the systems held that day."""

import itertools
import json
from collections import defaultdict
from datetime import date

import pytest

from engine.harness.contract.manifest import validate_extract
from engine.harness.contract.schemas import SCHEMAS, SYSTEMS
from engine.harness.synth.records import extract_folder, write_extracts
from engine.harness.tests.test_synth_company import small_company

DATES = (date(2024, 12, 18), date(2025, 1, 31), date(2025, 4, 30), date(2025, 7, 31))
SYSTEMS_WRITTEN = ("salesforce", "hubspot", "people_system", "spend_sheet")


@pytest.fixture(scope="module")
def estate(tmp_path_factory):
    company = small_company("capacity_constrained")
    out = tmp_path_factory.mktemp("estate")
    write_extracts(company, out, DATES)
    return company, out


def read(out, when, system, name):
    path = extract_folder(out, when) / system / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_every_extract_of_every_system_validates(estate):
    _, out = estate
    for when in DATES:
        for system in SYSTEMS_WRITTEN:
            folder = extract_folder(out, when) / system
            assert validate_extract(folder) == [], (when, system)
            listed = json.loads((folder / "manifest.json").read_text())["objects"]
            assert set(listed) == set(SYSTEMS[system]) - {"plan_lines"}


def test_nothing_is_dated_after_its_extract(estate):
    _, out = estate
    for when in DATES:
        cutoff = f"{when.isoformat()}T23:00:00Z"
        for system in SYSTEMS_WRITTEN:
            for name in SYSTEMS[system]:
                if name == "plan_lines":
                    continue
                datetimes = [
                    f.name for f in SCHEMAS[name].fields if f.type == "datetime"
                ]
                for rec in read(out, when, system, name):
                    for f in datetimes:
                        assert rec[f] is None or rec[f] <= cutoff, (
                            when,
                            name,
                            f,
                            rec[f],
                        )
                    for f in (
                        "Sales_Offered_Date__c",
                        "MQL_Date__c",
                        "ConvertedDate",
                        "start_date",
                        "end_date",
                        "FirstRespondedDate",
                    ):
                        assert rec.get(f) is None or rec[f] <= when.isoformat(), (
                            when,
                            name,
                            f,
                        )


def test_history_is_append_only_except_for_deleted_records(estate):
    _, out = estate
    deleted_any = False
    for earlier, later in itertools.pairwise(DATES):
        alive = {r["Id"] for r in read(out, later, "salesforce", "Opportunity")}
        gone = {
            r["Id"] for r in read(out, earlier, "salesforce", "Opportunity")
        } - alive
        deleted_any |= bool(gone)
        for name, key in (
            ("OpportunityHistory", "OpportunityId"),
            ("OpportunityFieldHistory", "OpportunityId"),
            ("LeadHistory", "LeadId"),
        ):
            before = read(out, earlier, "salesforce", name)
            after = {json.dumps(r) for r in read(out, later, "salesforce", name)}
            missing = [r for r in before if json.dumps(r) not in after]
            assert all(r[key] in gone for r in missing), (earlier, name)
        for name in ("Lead", "Account", "User"):
            assert {r["Id"] for r in read(out, earlier, "salesforce", name)} <= {
                r["Id"] for r in read(out, later, "salesforce", name)
            }
    assert deleted_any, "no record was deleted between extracts"


def test_final_extract_bookings_equal_the_truth_in_cents(estate):
    company, out = estate
    by_month = defaultdict(int)
    for r in read(out, DATES[-1], "salesforce", "Opportunity"):
        if r["Type"] == "New Business" and r["IsWon"]:
            by_month[r["CloseDate"][:7]] += round(r["Amount"] * 100)
    truth = company.truth
    expected = {
        m: int(v)
        for m, v in zip(
            truth.months, truth.bookings_cents.values.sum(axis=0), strict=True
        )
        if v
    }
    assert dict(by_month) == expected


def test_the_estate_has_the_data_quality_problems_the_contract_rules_exist_for(estate):
    _, out = estate
    final = DATES[-1]
    opps = {r["Id"]: r for r in read(out, final, "salesforce", "Opportunity")}
    history = defaultdict(list)
    for r in read(out, final, "salesforce", "OpportunityHistory"):
        history[r["OpportunityId"]].append(r)
    assert {r["Type"] for r in opps.values()} >= {"New Business", "Renewal"}
    amended = arrears = corrected = 0
    for rows in history.values():
        rows.sort(key=lambda r: r["CreatedDate"])
        closed = [r for r in rows if r["StageName"].startswith("Closed")]
        if len(closed) > 1:
            amended += closed[-1]["Amount"] != closed[0]["Amount"]
            corrected += closed[-1]["CloseDate"] != closed[0]["CloseDate"]
        arrears += (
            bool(closed) and closed[0]["CloseDate"] < closed[0]["CreatedDate"][:10]
        )
    assert amended and arrears and corrected
    assert read(out, final, "salesforce", "OpportunityFieldHistory"), "no owner changes"
    leads = read(out, final, "salesforce", "LeadHistory")
    mql_late = [
        r
        for r in leads
        if r["Field"] == "MQL_Date__c" and r["NewValue"] < r["CreatedDate"][:10]
    ]
    assert mql_late
    offers = defaultdict(int)
    for r in leads:
        offers[r["LeadId"]] += r["Field"] == "Sales_Offered_Date__c"
    assert max(offers.values()) >= 2, "no re-offered lead"
    assert {r["Disposition__c"] for r in read(out, final, "salesforce", "Lead")} >= {
        "Admitted",
        "Rejected",
        "Expired",
    }
    tiers = {}
    for when in DATES:
        for r in read(out, when, "salesforce", "Account"):
            tiers.setdefault(r["Id"], set()).add(r["Tier__c"])
    assert any(len(v) > 1 for v in tiers.values()), "no account changed tier"
    countries = {r["BillingCountry"] for r in read(out, final, "salesforce", "Account")}
    assert {"United States", "US"} <= countries


def test_hubspot_deals_mirror_salesforce_and_contacts_carry_lifecycle(estate):
    _, out = estate
    opp_ids = {r["Id"] for r in read(out, DATES[-1], "salesforce", "Opportunity")}
    deals = read(out, DATES[-1], "hubspot", "deals")
    assert deals and all(d["salesforce_opportunity_id"] in opp_ids for d in deals)
    stages = {c["lifecyclestage"] for c in read(out, DATES[-1], "hubspot", "contacts")}
    assert stages >= {"lead", "marketingqualifiedlead", "opportunity"}


def test_people_requisitions_and_spend_are_consistent(estate):
    company, out = estate
    users = {r["Email"] for r in read(out, DATES[-1], "salesforce", "User")}
    people = read(out, DATES[-1], "people_system", "people")
    assert {p["email"] for p in people} <= users
    reqs = read(out, DATES[-1], "people_system", "requisitions")
    slipped = [r for r in reqs if r["status"] == "filled"]
    assert slipped and {r["status"] for r in reqs} >= {"filled"}
    early = read(out, DATES[0], "spend_sheet", "spend")
    late = read(out, DATES[-1], "spend_sheet", "spend")
    assert (
        early
        and len(late) > len(early)
        and max(r["month"] for r in early) < "2024-12-02"
    )
    assert company.truth.spend_cents.values.sum() == sum(
        r["amount_cents"] for r in late
    )

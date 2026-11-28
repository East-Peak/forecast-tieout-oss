"""The catalog against a small generated company (synth seed 1, demand-limited): the mapping guesses hold
and measured totals equal independent plain-Python totals over the final extract's raw records."""

import json
from collections import Counter
from datetime import date

import pytest

from engine.harness.evidence import load
from engine.harness.query import query
from engine.harness.synth.cli import generate, small_params
from engine.harness.tests.test_query_support import D, catalog_text

FY24 = (
    D("2024-02-01"),
    D("2025-01-31"),
)  # the fiscal year starts February 1: FY24 is 2024-02-01 to 2025-01-31
EXTRACTS = [date(2025, 1, 24), date(2025, 2, 28), date(2025, 3, 31)]
PARAMS = small_params("demand_limited")


@pytest.fixture(scope="module")
def company(tmp_path_factory):
    out = tmp_path_factory.mktemp("generated")
    generate(PARAMS, 1, out, EXTRACTS)
    folders = sorted(p for p in (out / "extracts").glob("extract_*/*") if p.is_dir())
    return load(folders), out / "extracts" / f"extract_{EXTRACTS[-1]}"


def raw(extracts, system: str, name: str) -> list[dict]:
    path = extracts / system / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def fy(cat, estate, metric, group_by=()):
    return query(estate, cat, metric, group_by, None, FY24, FY24[1])


def in_fy(text: str | None) -> bool:
    return bool(text) and FY24[0].isoformat() <= text[:10] <= FY24[1].isoformat()


def test_totals_over_a_fiscal_year_equal_independent_totals_over_the_raw_records(
    company, cat
):
    estate, final = company
    opps = raw(final, "salesforce", "Opportunity")
    new = [r for r in opps if r["Type"] == "New Business"]
    won = [r for r in new if r["StageName"] == "Closed Won" and in_fy(r["CloseDate"])]
    leads = raw(final, "salesforce", "Lead")
    assert won and any(r["MQL_Date__c"] and in_fy(r["MQL_Date__c"]) for r in leads)
    expected = {
        "bookings": sum(round(r["Amount"] * 100) for r in won),
        "won_deals": len(won),
        "opportunities_created": sum(in_fy(r["CreatedDate"]) for r in new),
        "mqls": sum(in_fy(r["MQL_Date__c"]) for r in leads),
        "lost_deals": sum(
            r["StageName"] == "Closed Lost" and in_fy(r["CloseDate"]) for r in new
        ),
        "leads_created": sum(in_fy(r["CreatedDate"]) for r in leads),
    }
    got = {m: fy(cat, estate, m)[0].value for m in expected}
    assert got == expected
    by_year = {
        c.key: c.value
        for c in query(estate, cat, "bookings", ["fiscal_year"], None, FY24, FY24[1])
    }
    assert by_year == {("FY24",): expected["bookings"]}


def test_every_raw_tier_country_and_campaign_type_is_mapped(company, cat):
    estate, final = company
    for metric in ("opportunities_created", "bookings"):
        for dimension in ("segment", "region"):
            cells = fy(cat, estate, metric, [dimension])
            assert {c.contract.counts.get("unmapped", 0) for c in cells} == {0}, (
                metric,
                dimension,
            )
            assert {c.key: c.value for c in cells}[("Unknown",)] == 0
    text = catalog_text().lower()
    for campaign in raw(final, "salesforce", "Campaign"):
        assert f"'{campaign['Type'].lower()}'" in text, campaign["Type"]
    for r in raw(final, "salesforce", "Opportunity"):
        if r["LeadSource"]:
            assert f"'{r['LeadSource'].lower()}'" in text, r["LeadSource"]


def test_only_genuinely_unattributed_deals_are_unknown(company, cat):
    estate, final = company
    cells = {
        c.key[0]: c.value for c in fy(cat, estate, "opportunities_created", ["source"])
    }
    total = sum(cells.values())
    assert total and all(
        cells[leaf] > 0
        for leaf in (
            "Paid",
            "Events",
            "Inbound",
            "ABM",
            "BDR Outbound",
            "AE Self-Sourced",
            "Partner",
        )
    )
    declared = PARAMS.p_unattributed
    assert abs(cells["Unknown"] / total - declared) < 0.04, (
        cells["Unknown"],
        total,
        declared,
    )
    raw_opps = [
        r
        for r in raw(final, "salesforce", "Opportunity")
        if r["Type"] == "New Business" and in_fy(r["CreatedDate"])
    ]
    blank = Counter(
        r["CampaignId"] is None
        and r["Sourcing_User__c"] is None
        and r["LeadSource"] is None
        for r in raw_opps
    )
    assert (
        cells["Unknown"] <= blank[True] + 1
    )  # nothing with a campaign, a sourcing person or a lead source is Unknown

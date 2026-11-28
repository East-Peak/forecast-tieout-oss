"""Dimension semantics on small estates built in code: attribute time, its flagged fallback, unmapped values."""

from engine.harness.evidence import load
from engine.harness.query import query, records
from engine.harness.tests.test_evidence_support import (
    ofh,
    ohist,
    opp,
    write_extract,
)
from engine.harness.tests.test_query_support import D, by_key, values

W = (D("2025-01-01"), D("2025-06-30"))
T = D("2025-06-30")


def account(
    aid: str, tier: str | None, created: str, country="United States", code=None
) -> dict:
    return {
        "Id": aid, "Name": f"{aid} Co", "Tier__c": tier, "BillingCountry": country, "BillingCountryCode": code,
        "CreatedDate": created, "SystemModstamp": created,
    }  # fmt: skip


def estate_x(root):
    """Account X1 is Tier 1 until a re-tiering shows in the second extract; deal O2 predates its account."""
    o1 = opp("006X1", AccountId="001X1", CreatedDate="2025-01-05T09:00:00Z", StageName="Closed Won", Amount=1000.0, CloseDate="2025-02-10", IsClosed=True, IsWon=True)  # fmt: skip
    o2 = opp("006X2", AccountId="001X2", CreatedDate="2025-02-15T09:00:00Z", StageName="Closed Won", Amount=2000.0, CloseDate="2025-03-10", IsClosed=True, IsWon=True)  # fmt: skip
    o3 = opp("006X3", AccountId="001X3", CreatedDate="2025-02-20T09:00:00Z", StageName="Closed Won", Amount=3000.0, CloseDate="2025-04-10", IsClosed=True, IsWon=True)  # fmt: skip
    history = [
        ohist("008X1", "006X1", "Discovery", 1000.0, "2025-02-28", "2025-01-05T09:00:00Z"),
        ohist("008X2", "006X1", "Closed Won", 1000.0, "2025-02-10", "2025-02-10T09:00:00Z"),
        ohist("008X3", "006X2", "Discovery", 2000.0, "2025-03-31", "2025-02-15T09:00:00Z"),
        ohist("008X4", "006X2", "Closed Won", 2000.0, "2025-03-10", "2025-03-10T09:00:00Z"),
        ohist("008X5", "006X3", "Discovery", 3000.0, "2025-04-30", "2025-02-20T09:00:00Z"),
        ohist("008X6", "006X3", "Closed Won", 3000.0, "2025-04-10", "2025-04-10T09:00:00Z"),
    ]  # fmt: skip
    owner_change = [
        ofh("017X1", "006X1", "005X1", "005X2", "2025-03-01T09:00:00Z")
    ]  # after O1 closed

    def folder(when, accounts, opps, ofhs):
        return write_extract(root, when, "salesforce", {
            "Opportunity": opps, "OpportunityHistory": history, "OpportunityFieldHistory": ofhs,
            "Lead": [], "LeadHistory": [], "Account": accounts,
        })  # fmt: skip

    first = folder(
        "2025-03-15T23:00:00Z",
        [account("001X1", "Tier 1", "2025-01-01T09:00:00Z")],
        [o1, o2],
        [],
    )
    second = folder(
        "2025-06-30T23:00:00Z",
        [
            account(
                "001X1", "Tier 3", "2025-01-01T09:00:00Z"
            ),  # re-tiered after the deal
            account(
                "001X2", "Tier 2", "2025-03-01T09:00:00Z", "Germany", "DE"
            ),  # created after O2
            account(
                "001X3", "Platinum", "2025-01-01T09:00:00Z", "Atlantis"
            ),  # no rule for either
        ],
        [o1, o2, o3],
        owner_change,
    )
    return [first, second]


def bookings(estate, cat, group_by, **kw):
    return query(estate, cat, "bookings", group_by, kw.pop("filters", None), W, T, **kw)


def test_a_later_retiering_does_not_move_a_closed_deal(tmp_path, cat):
    estate = load(estate_x(tmp_path))
    cells = by_key(bookings(estate, cat, ["segment"]))
    assert (
        cells[("Enterprise",)].value == 100_000
    )  # O1 stays in the Tier 1 it had when it was created
    assert cells[("SMB",)].value == 0  # although the account is Tier 3 today


def test_fallback_to_current_is_flagged_and_counted(tmp_path, cat):
    estate = load(estate_x(tmp_path))
    cells = by_key(bookings(estate, cat, ["segment"]))
    mid = cells[
        ("Mid-Market",)
    ]  # O2: its account did not exist when the deal was created
    assert mid.value == 200_000
    assert mid.contract.counts == {"attribute_fallback_current": 1}
    assert "attribute_fallback_current" in mid.contract.flags
    assert "attribute_fallback_current" not in cells[("Enterprise",)].contract.flags
    assert [r.id for r in records(estate, cat, mid)] == ["006X2"]


def test_unmapped_values_land_in_the_declared_member_and_are_counted(tmp_path, cat):
    estate = load(estate_x(tmp_path))
    cells = by_key(bookings(estate, cat, ["segment"]))
    unknown = cells[("Unknown",)]
    assert unknown.value == 300_000  # O3's tier "Platinum" has no rule
    assert (
        unknown.contract.counts["unmapped"] == 1
        and "unmapped_values" in unknown.contract.flags
    )
    regions = by_key(bookings(estate, cat, ["region"]))
    assert (
        regions[("Unknown",)].contract.counts["unmapped"] == 1
    )  # "Atlantis" with no code
    assert (
        regions[("EMEA",)].value == 200_000
        and regions[("North America",)].value == 100_000
    )


def test_attribute_time_at_close_keeps_the_owner_who_closed_the_deal(tmp_path, cat):
    estate = load(estate_x(tmp_path))
    by_owner = values(bookings(estate, cat, ["booking_owner"]))
    assert (
        by_owner[("005X1",)] == 600_000
    )  # O1 closed under 005X1; reassigned to 005X2 a month later
    assert ("005X2",) not in by_owner or by_owner[("005X2",)] == 0

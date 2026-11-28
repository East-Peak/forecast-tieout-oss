"""Tranche 1, part F: the restating measures reconcile to the raw records.

The independent total is plain Python over the JSON Lines files: for each record, the version
in the latest extract that shows it, summed with exact decimal arithmetic. No SQL, no engine.
"""

import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from engine.harness.evidence import AsOf, bookings_by_month, load, mql_count
from engine.harness.tests.test_evidence_support import estate_dirs

FAR = date(2099, 12, 31)


def latest_versions(
    dirs: list[Path], system: str, name: str, key: str
) -> dict[str, dict]:
    """Each record as the latest extract showing it has it."""
    found = {}
    for folder in sorted(d for d in dirs if d.name == system):
        manifest = json.loads((folder / "manifest.json").read_text())
        if name not in manifest["objects"]:
            continue
        for line in (folder / f"{name}.jsonl").read_text().splitlines():
            if line.strip():
                record = json.loads(line)
                found[record[key]] = record
    return found


def raw_bookings_by_month(dirs: list[Path]) -> dict[str, int]:
    out: Counter = Counter()
    for r in latest_versions(dirs, "salesforce", "Opportunity", "Id").values():
        if (
            r["Type"] == "New Business"
            and r["StageName"] == "Closed Won"
            and r["Amount"] is not None
        ):
            out[r["CloseDate"][:7]] += int(Decimal(repr(r["Amount"])) * 100)
    return dict(out)


def raw_mqls_by_month(dirs: list[Path]) -> dict[str, int]:
    out: Counter = Counter()
    for r in latest_versions(dirs, "salesforce", "Lead", "Id").values():
        if r["MQL_Date__c"]:
            out[r["MQL_Date__c"][:7]] += 1
    return dict(out)


def raw_offer_count(dirs: list[Path]) -> int:
    rows = latest_versions(dirs, "salesforce", "LeadHistory", "Id")
    return sum(
        1
        for r in rows.values()
        if r["Field"] == "Sales_Offered_Date__c" and r["NewValue"]
    )


def reconcile(store, dirs: list[Path]) -> None:
    asof = AsOf.reconstructed(store, FAR)
    bookings = raw_bookings_by_month(dirs)
    for month, cents in bookings.items():
        assert bookings_by_month(asof, month) == cents, month
    assert sum(bookings_by_month(asof, m) for m in bookings) == sum(bookings.values())
    mqls = raw_mqls_by_month(dirs)
    assert {m: mql_count(asof, m) for m in mqls} == mqls
    assert asof.relation("demand_episode").aggregate("count(*)").fetchall()[0][
        0
    ] == raw_offer_count(dirs)
    alive = (
        asof.relation("opportunity")
        .filter("deleted_at IS NULL")
        .aggregate("count(*)")
        .fetchall()[0][0]
    )
    final = max(
        (d for d in dirs if d.name == "salesforce"),
        key=lambda d: json.loads((d / "manifest.json").read_text())["extracted_at"],
    )
    assert alive == sum(
        1
        for line in (final / "Opportunity.jsonl").read_text().splitlines()
        if line.strip()
    )


def test_estate_a_restating_measures_equal_the_raw_totals():
    dirs = estate_dirs()
    store = load(dirs)
    reconcile(store, dirs)
    assert raw_bookings_by_month(dirs) == {
        "2025-03": 2400000,
        "2025-05": 1200000,
        "2025-06": 800000,
        "2025-04": 1500000,
    }
    assert raw_mqls_by_month(dirs) == {"2025-01": 1, "2025-03": 3, "2025-04": 3}
    assert raw_offer_count(dirs) == 9


def test_spend_reconciles_to_the_spend_sheet():
    dirs = estate_dirs()
    store = load(dirs)
    sheet = latest_versions(dirs, "spend_sheet", "spend", "spend_id")
    total = sum(r["amount_cents"] for r in sheet.values())
    got = (
        AsOf.reconstructed(store, FAR)
        .relation("spend")
        .aggregate("sum(amount_cents)")
        .fetchall()[0][0]
    )
    assert got == total == 970000

"""Golden fixture A: two extracts of a tiny estate with a late edit.

Part one checks the files: they validate against the schemas, the extracts
agree with each other and with their own history objects, and each planted
situation is present. Part two checks expected.yaml: it is well formed, and
every numeric answer is re-derived by a brute-force oracle over the raw
rows. The oracle is a test device for ten small questions, not an evidence engine.
"""

import json
from itertools import pairwise
from pathlib import Path

import pytest
import yaml

from engine.harness.contract.manifest import validate_extract
from engine.harness.contract.schemas import SCHEMAS

ROOT = Path(__file__).resolve().parents[1] / "contract" / "fixtures" / "estate_a"
E1, E2 = "extract_2025-04-30", "extract_2025-06-30"
T1, T2 = "2025-04-30T23:00:00Z", "2025-06-30T23:00:00Z"
ESTATE = yaml.safe_load((ROOT / "estate.yaml").read_text())
EXPECTED = yaml.safe_load((ROOT / "expected.yaml").read_text())


def rows(extract, system, name):
    path = ROOT / extract / system / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def manifest(extract, system):
    return json.loads((ROOT / extract / system / "manifest.json").read_text())


def folders():
    return sorted(p for p in ROOT.glob("extract_*/*") if p.is_dir())


# ---- the files --------------------------------------------------------


@pytest.mark.parametrize("folder", folders(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_extract_validates(folder):
    assert validate_extract(folder) == []


def test_estate_has_the_stated_size():
    assert {
        r["Id"] for e in (E1, E2) for r in rows(e, "salesforce", "Opportunity")
    } == {f"006FX000000000{i}" for i in range(1, 9)}
    assert len(rows(E2, "salesforce", "Lead")) == 8
    assert len(rows(E2, "salesforce", "Account")) == 3
    assert (
        len(rows(E2, "salesforce", "User"))
        == len(rows(E2, "people_system", "people"))
        == 4
    )
    assert len(rows(E2, "salesforce", "Campaign")) == 2


def test_two_extracts_at_different_dates_and_every_object_is_covered():
    assert manifest(E1, "salesforce")["extracted_at"] == T1
    assert manifest(E2, "salesforce")["extracted_at"] == T2
    listed = {
        n
        for e in (E1, E2)
        for f in (ROOT / e).iterdir()
        for n in json.loads((f / "manifest.json").read_text())["objects"]
    }
    assert listed == set(SCHEMAS)


def test_unextracted_and_empty_are_different():
    assert "requisitions" not in manifest(E1, "people_system")["objects"]
    assert "requisitions" in manifest(E2, "people_system")["objects"]
    assert (
        manifest(E1, "salesforce")["objects"]["OpportunityFieldHistory"]["count"] == 0
    )
    assert not (ROOT / E1 / "hubspot").exists()


def test_a_record_is_deleted_between_extracts_with_its_history():
    gone = {r["Id"] for r in rows(E1, "salesforce", "Opportunity")} - {
        r["Id"] for r in rows(E2, "salesforce", "Opportunity")
    }
    assert gone == {"006FX0000000005"}
    assert any(
        r["OpportunityId"] in gone for r in rows(E1, "salesforce", "OpportunityHistory")
    )
    assert not any(
        r["OpportunityId"] in gone for r in rows(E2, "salesforce", "OpportunityHistory")
    )


def test_history_is_append_only_across_extracts():
    for obj in ("OpportunityHistory", "LeadHistory"):
        later = {r["Id"]: r for r in rows(E2, "salesforce", obj)}
        for r in rows(E1, "salesforce", obj):
            assert r["CreatedDate"] <= T1
            if r["Id"] in later:
                assert later[r["Id"]] == r
    assert all(
        r["CreatedDate"] > T1 for r in rows(E2, "salesforce", "OpportunityFieldHistory")
    )


@pytest.mark.parametrize("extract", [E1, E2])
def test_snapshots_agree_with_their_history_objects(extract):
    cutoff = {E1: T1, E2: T2}[extract]
    latest = {}
    for r in sorted(
        rows(extract, "salesforce", "OpportunityHistory"),
        key=lambda r: r["CreatedDate"],
    ):
        assert r["CreatedDate"] <= cutoff
        latest[r["OpportunityId"]] = r
    for opp in rows(extract, "salesforce", "Opportunity"):
        h = latest[opp["Id"]]
        assert (opp["StageName"], opp["Amount"], opp["CloseDate"]) == (
            h["StageName"],
            h["Amount"],
            h["CloseDate"],
        ), opp["Id"]
        assert opp["IsClosed"] == opp["StageName"].startswith("Closed") and opp[
            "IsWon"
        ] == (opp["StageName"] == "Closed Won")
    value = {}
    for r in sorted(
        rows(extract, "salesforce", "LeadHistory"), key=lambda r: r["CreatedDate"]
    ):
        value[r["LeadId"], r["Field"]] = r["NewValue"]
    for lead in rows(extract, "salesforce", "Lead"):
        for field in (
            "Sales_Offered_Date__c",
            "MQL_Date__c",
            "Disposition__c",
            "Disposition_Reason__c",
        ):
            assert lead[field] == value.get((lead["Id"], field)), (lead["Id"], field)


def test_references_resolve_within_each_extract():
    for extract in (E1, E2):
        ids = {}
        for system in (ROOT / extract).iterdir():
            for f in system.glob("*.jsonl"):
                schema = SCHEMAS[f.stem]
                ids[f.stem] = {
                    r[schema.key[0]] for r in rows(extract, system.name, f.stem)
                }
        for system in (ROOT / extract).iterdir():
            for f in system.glob("*.jsonl"):
                for field in SCHEMAS[f.stem].fields:
                    if field.ref and field.ref in ids:
                        for r in rows(extract, system.name, f.stem):
                            assert (
                                r[field.name] is None or r[field.name] in ids[field.ref]
                            ), (extract, f.stem, field.name, r[field.name])


def test_planted_situations_are_present():
    hist = rows(E2, "salesforce", "OpportunityHistory")
    o1 = [
        r
        for r in hist
        if r["OpportunityId"] == "006FX0000000001" and r["StageName"] == "Closed Won"
    ]
    assert [r["Amount"] for r in o1] == [20000.0, 24000.0] and o1[1][
        "CreatedDate"
    ] > o1[0]["CreatedDate"]  # amended after close
    (o2,) = [
        r
        for r in hist
        if r["OpportunityId"] == "006FX0000000002" and r["StageName"] == "Closed Won"
    ]
    assert o2["CloseDate"] < o2["CreatedDate"][:10]  # close date entered in arrears
    l8 = [
        r
        for r in rows(E2, "salesforce", "LeadHistory")
        if r["LeadId"] == "00QFX0000000008" and r["Field"] == "MQL_Date__c"
    ]
    assert l8[0]["NewValue"] < l8[0]["CreatedDate"][:10]  # a lead re-dated in arrears
    tiers = [
        next(
            a["Tier__c"]
            for a in rows(e, "salesforce", "Account")
            if a["Id"] == "001FX0000000001"
        )
        for e in (E1, E2)
    ]
    assert tiers == ["Tier 3", "Tier 2"]
    assert "Account.Tier__c" in ESTATE["field_coverage"]["snapshot_only_examples"]
    assert "Account.Tier__c" not in ESTATE["field_coverage"]["history"]


def test_more_planted_situations():
    hist = rows(E2, "salesforce", "OpportunityHistory")
    # a counterexample to backdating: Negotiation observed after the CloseDate it is later given
    o7 = [r for r in hist if r["OpportunityId"] == "006FX0000000007"]
    assert [r["StageName"] for r in o7] == ["Discovery", "Negotiation", "Closed Won"]
    assert o7[1]["CreatedDate"][:10] > o7[2]["CloseDate"]
    # a CloseDate correction on an already closed deal
    o4 = [
        r
        for r in hist
        if r["OpportunityId"] == "006FX0000000004" and r["StageName"] == "Closed Won"
    ]
    assert [r["CloseDate"] for r in o4] == ["2025-05-20", "2025-06-02"]
    # a reopened deal: closed lost, then back to an open stage
    o8 = [r["StageName"] for r in hist if r["OpportunityId"] == "006FX0000000008"]
    assert o8 == ["Discovery", "Closed Lost", "Proposal"]
    # a lead offered to sales twice, and outbound demand without an MQL date
    offers = [
        r["NewValue"]
        for r in rows(E2, "salesforce", "LeadHistory")
        if r["LeadId"] == "00QFX0000000004" and r["Field"] == "Sales_Offered_Date__c"
    ]
    assert offers == ["2025-03-20", "2025-05-10"]
    l2 = next(r for r in rows(E2, "salesforce", "Lead") if r["Id"] == "00QFX0000000002")
    assert l2["MQL_Date__c"] is None and l2["Sales_Offered_Date__c"] is not None
    # one country given as a name, one as a code, one with the optional code column
    accounts = {a["Id"]: a for a in rows(E2, "salesforce", "Account")}
    assert (
        accounts["001FX0000000001"]["BillingCountry"] == "United States"
        and accounts["001FX0000000001"]["BillingCountryCode"] is None
    )
    assert accounts["001FX0000000002"]["BillingCountry"] == "US"
    assert accounts["001FX0000000003"]["BillingCountryCode"] == "DE"


def test_fabricated_people_only():
    for e in (E1, E2):
        for u in rows(e, "salesforce", "User"):
            assert u["Email"].endswith("@example.com")
        for p in rows(e, "people_system", "people"):
            assert p["email"].endswith("@example.com")


# ---- expected.yaml ----------------------------------------------------

KINDS = {
    "bookings", "stage_at", "status_at", "open_at", "owner_at", "open_count", "closing",
    "mql_count", "demand_outcomes", "episodes_of_lead", "field_at", "object_available",
}  # fmt: skip


def test_expected_cases_are_well_formed():
    ids = [c["id"] for c in EXPECTED["cases"]]
    assert len(ids) == len(set(ids))
    assert {c["kind"] for c in EXPECTED["cases"]} <= KINDS
    for c in EXPECTED["cases"]:
        assert (
            c["question"]
            and len(c["derivation"]) > 20
            and "\n" not in c["derivation"].strip()
        )
        assert set(c) >= {"t", "args", "reconstructed", "contemporaneous"}


def test_the_two_modes_differ_where_the_design_says():
    differ = {
        c["id"] for c in EXPECTED["cases"] if c["reconstructed"] != c["contemporaneous"]
    }
    assert {
        "bookings_2025_03",
        "bookings_2025_04",
        "bookings_2025_05",
        "open_o7_2025_05_31",
        "open_o4_2025_05_31",
        "open_count_2025_04_30",
        "open_count_2025_05_31",
        "mql_count_2025_04",
        "demand_outcomes_offered_2025_04",
    } <= differ


def test_stage_at_and_open_at_are_different_questions():
    cases = {c["id"]: c for c in EXPECTED["cases"]}
    stage, open_ = cases["stage_o7_2025_05_31"], cases["open_o7_2025_05_31"]
    assert stage["reconstructed"]["value"] == "Negotiation"  # operational
    assert open_["reconstructed"] == {
        "open": False
    }  # commercial, same deal, same T, same K


def test_expected_assertions_match_their_source_rows():
    sources = {}
    for extract in (E1, E2):
        for f in (ROOT / extract / "salesforce").glob("*History.jsonl"):
            for r in rows(extract, "salesforce", f.stem):
                sources.setdefault(f"salesforce/{f.stem}/{r['Id']}", r)
    tuple_fields = ["entity", "id", "field", "value", "effective_at", "recorded_at", "source", "extract_id"]  # fmt: skip
    for a in EXPECTED["assertions"]:
        assert [k for k in a if k != "flags"] == tuple_fields
        assert a["effective_at"] <= a["recorded_at"]
        row = sources.get(a["source"])
        if row:
            assert (
                str(row[a["field"]]) == a["value"]
                and row["CreatedDate"] == a["recorded_at"]
            )
    deleted = [a for a in EXPECTED["assertions"] if a["field"] == "_deleted"]
    assert [a["flags"] for a in deleted] == [["deletion_time_upper_bound"]]
    assert all(a["effective_at"] == a["recorded_at"] == T2 for a in deleted)


# The oracle: brute force over the raw rows, one small function per question kind.

END = "T23:59:59Z"


def history(name):
    seen = {}
    for e in (E1, E2):
        for r in rows(e, "salesforce", name):
            seen[r["Id"]] = r
    return sorted(seen.values(), key=lambda r: (r["CreatedDate"], r["Id"]))


def known_k(case, mode):
    return T2 if mode == "reconstructed" else case["t"] + END


def opp_rows(opp, k):
    return [
        r
        for r in history("OpportunityHistory")
        if r["OpportunityId"] == opp and r["CreatedDate"] <= k
    ]


def all_opps():
    return sorted({r["OpportunityId"] for r in history("OpportunityHistory")})


def created(opp):
    return next(
        r["CreatedDate"]
        for e in (E1, E2)
        for r in rows(e, "salesforce", "Opportunity")
        if r["Id"] == opp
    )


def deleted_by(opp, t, k):
    """R4: deletion is effective at the first extract lacking the record."""
    return opp == "006FX0000000005" and T2 <= min(k, t + END)


def stage_at(opp, t, k):
    """R1: a stage assertion per row that changes the stage, effective at the row's CreatedDate."""
    out, previous = [], None
    for r in opp_rows(opp, k):
        if r["StageName"] != previous and r["CreatedDate"] <= t + END:
            out.append((r["CreatedDate"], r["StageName"]))
        previous = r["StageName"]
    return out[-1][1] if out else None


def closed_spells(opp, k):
    """(close_date, reopened_at or None) for each selling spell closed as known by K."""
    spells, current = [], None
    for r in opp_rows(opp, k):
        if r["StageName"].startswith("Closed"):
            current = (
                {"close": r["CloseDate"], "reopened": None}
                if current is None
                else {**current, "close": r["CloseDate"]}
            )
        elif current is not None:
            spells.append({**current, "reopened": r["CreatedDate"]})
            current = None
    return spells + ([current] if current else [])


def open_at(opp, t, k):
    """R2: commercial. Known by K, created by T, not deleted by T, not closed by T."""
    if not opp_rows(opp, k) or created(opp) > t + END or deleted_by(opp, t, k):
        return False
    return not any(
        s["close"] <= t and (s["reopened"] is None or s["reopened"] > t + END)
        for s in closed_spells(opp, k)
    )


def episodes(lead, t, k):
    """R8: one per non-null Sales_Offered_Date__c row recorded by K."""
    rs = [
        r
        for r in history("LeadHistory")
        if r["LeadId"] == lead and r["CreatedDate"] <= k
    ]
    offers = [
        r
        for r in rs
        if r["Field"] == "Sales_Offered_Date__c" and r["NewValue"] is not None
    ]
    has_mql = any(r["Field"] == "MQL_Date__c" for r in rs)
    out = []
    for n, offer in enumerate(offers):
        end = offers[n + 1]["CreatedDate"] if n + 1 < len(offers) else "9999"
        window = [
            r
            for r in rs
            if offer["CreatedDate"] <= r["CreatedDate"] < end
            and r["CreatedDate"] <= t + END
        ]
        disp = [r["NewValue"] for r in window if r["Field"] == "Disposition__c"]
        why = [r["NewValue"] for r in window if r["Field"] == "Disposition_Reason__c"]
        outcome = (disp[-1] or "open").lower() if disp else "open"
        reason = (
            None
            if outcome == "open" or not why or why[-1] is None
            else ("capacity" if why[-1] == "no_capacity" else "fit")
        )
        out.append(
            {
                "offer_seq": n + 1,
                "offered_on": offer["NewValue"],
                "mql_linked": n == 0 and has_mql,
                "outcome": outcome,
                "reason": reason,
            }
        )
    return out


def oracle(case, mode):
    k, t, args = known_k(case, mode), case["t"], case["args"]
    kind = case["kind"]
    if kind == "bookings":
        total = 0
        for opp in all_opps():
            known = opp_rows(opp, k)
            if not known:
                continue
            last = known[-1]
            if (
                last["StageName"] == "Closed Won"
                and last["CloseDate"][:7] == args["month"]
            ):
                total += round(last["Amount"] * 100)
        return {"value_cents": total}
    if kind == "stage_at":
        return {"value": stage_at(args["opportunity"], t, k)}
    if kind == "status_at":
        opp = args["opportunity"]
        return (
            {"status": "deleted", "flags": ["deletion_time_upper_bound"]}
            if deleted_by(opp, t, k)
            else {"status": "present"}
        )
    if kind == "open_at":
        return {"open": open_at(args["opportunity"], t, k)}
    if kind == "owner_at":
        owner = next(
            r["OldValue"]
            for r in rows(E2, "salesforce", "OpportunityFieldHistory")
            if r["OpportunityId"] == args["opportunity"]
        )
        moves = [
            r
            for r in history("OpportunityFieldHistory")
            if r["OpportunityId"] == args["opportunity"]
            and r["CreatedDate"] <= min(k, t + END)
        ]
        return {"value": moves[-1]["NewValue"] if moves else owner}
    if kind == "open_count":
        ids = [o for o in all_opps() if open_at(o, t, k)]
        return {"count": len(ids), "ids": ids}
    if kind == "closing":
        rs = opp_rows(args["opportunity"], k)
        closed = [r for r in rs if r["StageName"].startswith("Closed")]
        return {
            "close_date": rs[-1]["CloseDate"],
            "observed_closed_recorded_at": closed[0]["CreatedDate"] if closed else None,
        }
    if kind == "mql_count":
        mql = {}
        for r in history("LeadHistory"):
            if r["Field"] == "MQL_Date__c" and r["CreatedDate"] <= k:
                mql[r["LeadId"]] = r["NewValue"]
        return {"count": sum(1 for d in mql.values() if d[:7] == args["month"])}
    if kind == "episodes_of_lead":
        return {
            "episodes": [
                {
                    key: ep[key]
                    for key in ("offer_seq", "offered_on", "mql_linked", "outcome")
                }
                for ep in episodes(args["lead"], t, k)
            ]
        }
    if kind == "demand_outcomes":
        leads = sorted({r["LeadId"] for r in history("LeadHistory")})
        eps = [
            ep
            for lead in leads
            for ep in episodes(lead, t, k)
            if ep["offered_on"][:7] == args["offered_month"]
        ]
        counts, reasons = {}, {}
        for ep in eps:
            counts[ep["outcome"]] = counts.get(ep["outcome"], 0) + 1
            if ep["reason"]:
                reasons[ep["reason"]] = reasons.get(ep["reason"], 0) + 1
        return {"counts": counts, **({"reason_classes": reasons} if reasons else {})}
    extracts = [(T1, E1), (T2, E2)]
    if kind == "field_at":
        seen = [
            (
                when,
                next(
                    r[args["field"]]
                    for r in rows(e, "salesforce", args["entity"])
                    if r["Id"] == args["id"]
                ),
            )
            for when, e in extracts
            if when <= k
        ]
        if not seen:
            return {"unavailable": "no_extract_at_or_before_known_at"}
        first = next(
            r["CreatedDate"]
            for r in rows(E1, "salesforce", args["entity"])
            if r["Id"] == args["id"]
        )
        eff = [(first, seen[0][1])] + [
            (w, v) for (_, p), (w, v) in pairwise(seen) if v != p
        ]
        live = [(i, v) for i, (e, v) in enumerate(eff) if e <= t + END]
        index, value = live[-1]
        return {
            "value": value,
            **({"flags": ["assumed_since_creation"]} if index == 0 else {}),
        }
    if kind == "object_available":
        listed = [
            (
                when,
                json.loads((ROOT / e / args["system"] / "manifest.json").read_text())[
                    "objects"
                ],
            )
            for when, e in extracts
            if (ROOT / e / args["system"]).exists() and when <= k
        ]
        if not listed:
            return {"unavailable": "no_extract_at_or_before_known_at"}
        if not any(args["object"] in objects for _, objects in listed):
            return {"unavailable": "object_not_extracted"}
        out = {"available": True}
        if args["object"] == "OpportunityFieldHistory":
            out["rows_in_first_extract"] = listed[0][1][args["object"]]["count"]
        return out
    raise AssertionError(kind)


@pytest.mark.parametrize("mode", ["reconstructed", "contemporaneous"])
@pytest.mark.parametrize("case", EXPECTED["cases"], ids=lambda c: c["id"])
def test_expected_answer_is_rederived_by_the_oracle(case, mode):
    assert oracle(case, mode) == case[mode]

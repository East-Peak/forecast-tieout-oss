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
    } == {f"006FX000000000{i}" for i in range(1, 7)}
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
        for field in ("MQL_Date__c", "Disposition__c", "Disposition_Reason__c"):
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


def test_fabricated_people_only():
    for e in (E1, E2):
        for u in rows(e, "salesforce", "User"):
            assert u["Email"].endswith("@example.com")
        for p in rows(e, "people_system", "people"):
            assert p["email"].endswith("@example.com")


# ---- expected.yaml ----------------------------------------------------

KINDS = {
    "bookings", "stage_at", "owner_at", "open_count", "closing", "mql_count",
    "demand_outcomes", "field_at", "object_available",
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
        "stage_o2_2025_04_30",
        "stage_o5_2025_05_31",
        "open_count_2025_04_30",
        "mql_count_2025_04",
    } <= differ


def test_expected_assertions_match_their_source_rows():
    sources = {}
    for system in ("salesforce",):
        for extract in (E1, E2):
            for f in (ROOT / extract / system).glob("*History.jsonl"):
                for r in rows(extract, system, f.stem):
                    sources.setdefault(f"{system}/{f.stem}/{r['Id']}", r)
    for a in EXPECTED["assertions"]:
        assert list(a) == [
            "entity",
            "id",
            "field",
            "value",
            "effective_at",
            "recorded_at",
            "source",
            "extract_id",
        ]
        assert (
            a["effective_at"] <= a["recorded_at"]
            or a["field"] == "_deleted"
            or a["source"].endswith("#snapshot")
        )
        row = sources.get(a["source"])
        if row:
            assert (
                str(row[a["field"]]) == a["value"]
                and row["CreatedDate"] == a["recorded_at"]
            )


# The oracle: brute force over the raw rows, one small function per question kind.


def history(name):
    seen = {}
    for e in (E1, E2):
        for r in rows(e, "salesforce", name):
            seen[r["Id"]] = r
    return sorted(seen.values(), key=lambda r: (r["CreatedDate"], r["Id"]))


def known_k(case, mode):
    return T2 if mode == "reconstructed" else case["t"] + "T23:59:59Z"


def opp_rows(opp, k):
    return [
        r
        for r in history("OpportunityHistory")
        if r["OpportunityId"] == opp and r["CreatedDate"] <= k
    ]


def exists(opp, k):
    deleted = opp == "006FX0000000005" and k >= T2
    return bool(opp_rows(opp, k)) and not deleted


def all_opps():
    return sorted({r["OpportunityId"] for r in history("OpportunityHistory")})


def stage_assertions(opp, k):
    """(effective_at, recorded_at, stage) for each row that changes the stage (R1, R2)."""
    out, previous = [], None
    for r in opp_rows(opp, k):
        if r["StageName"] != previous:
            eff = r["CreatedDate"]
            if r["StageName"].startswith("Closed"):
                eff = min(r["CloseDate"] + "T00:00:00Z", eff)
            out.append((eff, r["CreatedDate"], r["StageName"]))
        previous = r["StageName"]
    return out


def stage_at(opp, t, k):
    got = [a for a in stage_assertions(opp, k) if a[0] <= t + "T23:59:59Z"]
    return max(got)[2] if got else None


def oracle(case, mode):
    k, t, args = known_k(case, mode), case["t"], case["args"]
    kind = case["kind"]
    if kind == "bookings":
        total = 0
        for opp in filter(lambda o: exists(o, k), all_opps()):
            last = opp_rows(opp, k)[-1]
            if (
                last["StageName"] == "Closed Won"
                and last["CloseDate"][:7] == args["month"]
            ):
                total += round(last["Amount"] * 100)
        return {"value_cents": total}
    if kind == "stage_at":
        return (
            {"value": stage_at(args["opportunity"], t, k)}
            if exists(args["opportunity"], k)
            else {"exists": False}
        )
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
            and r["CreatedDate"] <= min(k, t + "T23:59:59Z")
        ]
        return {"value": moves[-1]["NewValue"] if moves else owner}
    if kind == "open_count":
        created = {
            r["Id"]: r["CreatedDate"]
            for e in (E1, E2)
            for r in rows(e, "salesforce", "Opportunity")
        }
        open_now = [
            o
            for o in all_opps()
            if exists(o, k)
            and created[o] <= t + "T23:59:59Z"
            and not (stage_at(o, t, k) or "").startswith("Closed")
        ]
        return {"count": len(open_now)}
    if kind == "closing":
        rs = opp_rows(args["opportunity"], k)
        closed = [r for r in rs if r["StageName"].startswith("Closed")]
        return {
            "close_date": rs[-1]["CloseDate"],
            "observed_closed_recorded_at": closed[0]["CreatedDate"] if closed else None,
        }
    if kind in ("mql_count", "demand_outcomes"):
        mql = {}
        for r in history("LeadHistory"):
            if r["Field"] == "MQL_Date__c" and r["CreatedDate"] <= k:
                mql[r["LeadId"]] = r["NewValue"]
        month = args.get("month") or args["offered_month"]
        offered = sorted(lead for lead, d in mql.items() if d[:7] == month)
        if kind == "mql_count":
            return {"count": len(offered)}
        counts, reasons = {}, {"fit": 0, "capacity": 0}
        for lead in offered:
            disp = [
                r
                for r in history("LeadHistory")
                if r["LeadId"] == lead
                and r["Field"] == "Disposition__c"
                and r["CreatedDate"] <= min(k, t + "T23:59:59Z")
            ]
            outcome = disp[-1]["NewValue"].lower() if disp else "open"
            counts[outcome] = counts.get(outcome, 0) + 1
            why = [
                r["NewValue"]
                for r in history("LeadHistory")
                if r["LeadId"] == lead
                and r["Field"] == "Disposition_Reason__c"
                and r["CreatedDate"] <= min(k, t + "T23:59:59Z")
            ]
            if why:
                reasons["capacity" if why[-1] == "no_capacity" else "fit"] += 1
        out = {"counts": counts}
        if any(reasons.values()):
            out["reason_classes"] = {c: n for c, n in reasons.items() if n}
        return out
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
        created = next(
            r["CreatedDate"]
            for r in rows(E1, "salesforce", args["entity"])
            if r["Id"] == args["id"]
        )
        eff = [(created, seen[0][1])] + [
            (w, v) for (_, p), (w, v) in pairwise(seen) if v != p
        ]
        live = [(i, v) for i, (e, v) in enumerate(eff) if e <= t + "T23:59:59Z"]
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

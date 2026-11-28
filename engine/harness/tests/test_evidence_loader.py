"""Tranche 1, part A: the loader turns extracts into append-only assertions."""

import json
import random
from datetime import UTC, datetime

import pytest

from engine.harness.contract.keys import ASSERTION_FIELDS, Assertion
from engine.harness.contract.manifest import (
    build_manifest,
    content_hash,
    write_manifest,
)
from engine.harness.evidence import Coverage, ExtractError, Store, load

from .test_evidence_support import (
    ESTATE_YAML,
    EXPECTED,
    copy_estate,
    estate_dirs,
    read_rows,
    rewrite_manifest,
    write_rows,
)


@pytest.fixture(scope="module")
def store():
    return load(estate_dirs())


def test_every_system_extract_is_registered_once(store):
    rows = store.con.execute(
        "SELECT extract_id, source_system, content_hash FROM extract ORDER BY 1"
    ).fetchall()
    assert [r[0] for r in rows] == [
        "hubspot-20250630T230000Z",
        "people_system-20250430T230000Z",
        "people_system-20250630T230000Z",
        "plan_file-20250630T230000Z",
        "salesforce-20250430T230000Z",
        "salesforce-20250630T230000Z",
        "spend_sheet-20250630T230000Z",
    ]
    folder = next(
        f
        for f in estate_dirs()
        if f.parent.name.endswith("04-30") and f.name == "salesforce"
    )
    manifest = json.loads((folder / "manifest.json").read_text())
    assert {r[0]: r[2] for r in rows}["salesforce-20250430T230000Z"] == content_hash(
        manifest
    )


def test_standard_coverage_equals_the_estate_declaration():
    assert Coverage.standard() == Coverage.from_yaml(ESTATE_YAML)
    assert Coverage.from_yaml(ESTATE_YAML).immutable["Lead"] == (
        "CreatedById",
        "LeadSource",
        "CreatedDate",
    )


def test_coverage_rejects_unknown_fields_and_partial_history(tmp_path):
    bad = {
        "field_coverage": {
            "history": {
                "Opportunity.Nope": {
                    "via": "OpportunityHistory",
                    "since": "record creation",
                }
            },
            "immutable": {},
        }
    }
    with pytest.raises(ValueError, match="Nope"):
        Coverage.from_dict(bad)
    bad["field_coverage"]["history"] = {
        "Opportunity.Amount": {"via": "OpportunityHistory", "since": "2024-01-01"}
    }
    with pytest.raises(ValueError, match="record creation"):
        Coverage.from_dict(bad)


def flagged(store):
    return {a: flags for a, flags in store.flagged_assertions()}


@pytest.mark.parametrize(
    "expected",
    EXPECTED["assertions"],
    ids=lambda a: f"{a['id']}-{a['field']}-{a['value']}",
)
def test_expected_assertion_is_produced_exactly(store, expected):
    want = Assertion(*(expected[f] for f in ASSERTION_FIELDS))
    got = flagged(store)
    assert want in got
    assert set(expected.get("flags", [])) <= set(got[want])


def test_r5_flags_a_first_seen_snapshot_value_as_assumed_since_creation(store):
    tier3, tier2 = (
        a
        for a in store.flagged_assertions()
        if a[0].id == "001FX0000000001" and a[0].field == "Tier__c"
    )
    assert tier3[1] == ("assumed_since_creation",) and tier2[1] == ()


def test_history_wins_over_snapshot_differences(store):
    sources = store.con.execute(
        "SELECT DISTINCT source FROM assertion WHERE entity='Opportunity' AND field IN ('StageName','Amount','CloseDate')"
    ).fetchall()
    assert sources and all("OpportunityHistory" in s[0] for s in sources)
    # snapshot-only fields come from snapshots; the record's history fields never do
    assert store.con.execute(
        "SELECT count(*) FROM assertion WHERE field='Tier__c' AND entity='Account' AND source NOT LIKE '%#snapshot'"
    ).fetchone() == (0,)


def test_history_row_asserts_only_the_fields_that_changed(store):
    # O1's fourth row changes stage and close date; its fifth only the amount
    rows = store.con.execute(
        "SELECT field FROM assertion WHERE source = 'salesforce/OpportunityHistory/008FX0000000005'"
    ).fetchall()
    assert rows == [("Amount",)]
    first = store.con.execute(
        "SELECT count(*) FROM assertion WHERE source = 'salesforce/OpportunityHistory/008FX0000000001'"
    ).fetchone()
    assert first == (3,)  # the first row asserts all three


def test_deletion_is_one_flagged_assertion_at_the_first_extract_lacking_the_record(
    store,
):
    rows = store.con.execute(
        "SELECT entity, id, effective_at, recorded_at, deletion_time_upper_bound FROM assertion WHERE field='_deleted' ORDER BY id"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [("Opportunity", "006FX0000000005")]
    assert rows[0][2] == rows[0][3] and rows[0][4] is True


def test_immutable_fields_are_known_from_the_record_known_time(store):
    row = store.con.execute(
        "SELECT value, effective_at, recorded_at FROM assertion WHERE entity='Opportunity' AND id='006FX0000000004' AND field='LeadSource'"
    ).fetchall()
    assert row[0][0] == "Web" and str(row[0][1]) == "2025-04-10 09:00:00" == str(
        row[0][2]
    )


def test_initial_owner_of_a_history_field_is_asserted_from_the_snapshot(store):
    rows = store.con.execute(
        "SELECT value, recorded_at, source FROM assertion WHERE entity='Opportunity' AND id='006FX0000000004' AND field='OwnerId' ORDER BY recorded_at"
    ).fetchall()
    assert [r[0] for r in rows] == ["005FX0000000001", "005FX0000000002"]
    assert str(rows[0][1]) == "2025-04-30 23:00:00"  # first extract showing the deal
    assert rows[0][2].endswith("#snapshot")


def test_every_assertion_is_effective_no_later_than_it_is_recorded(store):
    assert store.con.execute(
        "SELECT count(*) FROM assertion WHERE effective_at > recorded_at"
    ).fetchone() == (0,)


def test_loading_the_same_extracts_twice_changes_nothing(store):
    before = store.assertions()
    counts = store.con.execute(
        "SELECT (SELECT count(*) FROM extract), (SELECT count(*) FROM raw_Lead)"
    ).fetchone()
    load(estate_dirs(), store=store)
    assert store.assertions() == before
    assert (
        store.con.execute(
            "SELECT (SELECT count(*) FROM extract), (SELECT count(*) FROM raw_Lead)"
        ).fetchone()
        == counts
    )


def test_any_load_order_gives_the_same_assertions(store):
    want = store.assertions()
    dirs = estate_dirs()
    rng = random.Random(7)
    orders = [list(reversed(dirs))] + [rng.sample(dirs, len(dirs)) for _ in range(3)]
    for order in orders:
        assert load(order).assertions() == want


def test_loading_in_two_batches_equals_loading_at_once(store):
    dirs = estate_dirs()
    first = load(dirs[:3])
    load(dirs[3:], store=first)
    assert first.assertions() == store.assertions()
    assert dirs[:3] != dirs[3:]


def test_an_invalid_extract_is_rejected_and_nothing_is_loaded(tmp_path):
    dirs = copy_estate(tmp_path / "e")
    target = next(
        d for d in dirs if d.name == "salesforce" and "06-30" in d.parent.name
    )
    rows = read_rows(target, "Opportunity")
    del rows[0]["Amount"]
    write_rows(target, "Opportunity", rows)
    with pytest.raises(ExtractError, match="Amount|sha256|count"):
        load(dirs)


def test_the_same_extract_id_with_different_content_is_rejected(tmp_path):
    dirs = copy_estate(tmp_path / "e")
    store = load(dirs)
    target = next(
        d for d in dirs if d.name == "salesforce" and "06-30" in d.parent.name
    )
    rows = read_rows(target, "Account")
    rows[0]["Name"] = "Changed Name"
    write_rows(target, "Account", rows)
    rewrite_manifest(target)
    with pytest.raises(ExtractError, match="different content"):
        load([target], store=store)


def test_a_record_that_disappears_and_returns_is_refused(tmp_path):
    dirs = copy_estate(tmp_path / "e")
    # extra extract of salesforce after the second that brings the deleted deal back
    second = next(
        d for d in dirs if d.name == "salesforce" and "06-30" in d.parent.name
    )
    third = tmp_path / "e" / "extract_2025-08-31" / "salesforce"
    third.mkdir(parents=True)

    first = next(d for d in dirs if d.name == "salesforce" and "04-30" in d.parent.name)
    for name in ("Opportunity", "OpportunityHistory"):
        (third / f"{name}.jsonl").write_text((first / f"{name}.jsonl").read_text())
    write_manifest(
        third,
        build_manifest(third, "salesforce", datetime(2025, 8, 31, 23, tzinfo=UTC)),
    )
    with pytest.raises(ExtractError, match="reappears"):
        load([*dirs, third])
    assert second.exists()


def test_a_first_row_with_a_null_old_value_adds_no_base_assertion(store):
    offers = store.con.execute(
        "SELECT value FROM assertion WHERE id = '00QFX0000000004' AND field = 'Sales_Offered_Date__c' ORDER BY recorded_at"
    ).fetchall()
    assert offers == [("2025-03-20",), ("2025-05-10",)]


def test_a_record_is_known_from_the_first_extract_that_shows_it_when_its_history_came_later(
    store,
):
    (known,) = store.con.execute(
        "SELECT known_since FROM record WHERE entity = 'Lead' AND id = '00QFX0000000008'"
    ).fetchone()
    assert str(known) == "2025-04-30 23:00:00"  # its first history row is dated 05-12


def test_a_store_on_disk_survives_reopening(tmp_path):
    path = tmp_path / "evidence.duckdb"
    first = load(estate_dirs(), Coverage.from_yaml(ESTATE_YAML), store=Store(path))
    want = first.assertions()
    first.con.close()
    again = Store(path)
    assert again.assertions() == want
    assert again.coverage == Coverage.from_yaml(ESTATE_YAML)
    load(estate_dirs(), store=again)
    assert again.assertions() == want

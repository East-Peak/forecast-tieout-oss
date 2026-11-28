"""Tranche 1, part C: canonical views as of (T, K), with lineage."""

from datetime import UTC, date, datetime

import pytest

from engine.harness.contract.keys import CANONICAL_TABLES, LINEAGE_COLUMN
from engine.harness.contract.manifest import build_manifest, write_manifest
from engine.harness.evidence import AsOf, load
from engine.harness.evidence.views import VIEW_NAMES
from engine.harness.tests.test_evidence_support import estate_dirs

NOW = date(2025, 6, 30)


@pytest.fixture(scope="module")
def store():
    return load(estate_dirs())


def rows(asof, view, where="TRUE", order="1"):
    cols = [c for c in asof.relation(view).columns]
    got = asof.store.con.execute(
        f"SELECT * FROM asof_{view}(?, ?) WHERE {where} ORDER BY {order}",
        [asof.t, asof.k],
    ).fetchall()
    return [dict(zip(cols, r, strict=True)) for r in got]


def test_every_canonical_table_has_a_view_with_its_key_and_lineage(store):
    asof = AsOf.reconstructed(store, NOW)
    assert set(CANONICAL_TABLES) <= set(VIEW_NAMES)
    for name, table in CANONICAL_TABLES.items():
        relation = asof.relation(name)
        columns = relation.columns
        for key in table.key:
            assert key in columns, (name, key)
        if name not in ("extract", "lead_event", "spend"):
            assert LINEAGE_COLUMN in columns, name
        got = relation.fetchall()
        assert got, f"{name} is empty"
        keys = [tuple(r[columns.index(k)] for k in table.key) for r in got]
        assert len(keys) == len(set(keys)), f"{name} key is not unique"


def test_relation_rejects_an_unknown_view_name(store):
    with pytest.raises(ValueError, match="unknown view"):
        AsOf.reconstructed(store, NOW).relation("opportunity; DROP TABLE assertion")


def test_lineage_names_source_records_and_extracts(store):
    row = rows(
        AsOf.reconstructed(store, NOW),
        "opportunity",
        "opportunity_id = '006FX0000000001'",
    )[0]
    assert "salesforce/OpportunityHistory/008FX0000000005" in row[LINEAGE_COLUMN]
    assert set(row["extract_ids"]) == {
        "salesforce-20250430T230000Z",
        "salesforce-20250630T230000Z",
    }


def test_opportunity_measure_fields_restate_but_attributes_are_as_of_t(store):
    o4_may = rows(
        AsOf.reconstructed(store, date(2025, 5, 31)),
        "opportunity",
        "opportunity_id = '006FX0000000004'",
    )[0]
    assert o4_may["owner_id"] == "005FX0000000002"  # moved 05-05: before T
    assert (o4_may["stage"], o4_may["amount_cents"], str(o4_may["close_date"])) == (
        "Closed Won",
        800000,
        "2025-06-02",
    )
    early = rows(
        AsOf.reconstructed(store, date(2025, 5, 1)),
        "opportunity",
        "opportunity_id = '006FX0000000004'",
    )[0]
    assert early["owner_id"] == "005FX0000000001"  # before the move
    assert early["close_date"] == date(
        2025, 6, 2
    )  # measures read the latest value known by K


def test_opportunities_created_after_t_are_not_in_the_view(store):
    ids = [
        r["opportunity_id"]
        for r in rows(AsOf.reconstructed(store, date(2025, 4, 30)), "opportunity")
    ]
    assert "006FX0000000007" not in ids and "006FX0000000005" in ids


def test_a_deleted_opportunity_stays_with_its_deletion_time(store):
    o5 = rows(
        AsOf.reconstructed(store, NOW),
        "opportunity",
        "opportunity_id = '006FX0000000005'",
    )[0]
    assert o5["deleted_at"] == datetime(2025, 6, 30, 23)
    before = rows(
        AsOf.reconstructed(store, date(2025, 5, 31)),
        "opportunity",
        "opportunity_id = '006FX0000000005'",
    )[0]
    assert before["deleted_at"] is None


def test_opportunity_state_has_validity_intervals(store):
    states = rows(
        AsOf.reconstructed(store, NOW),
        "opportunity_state",
        "opportunity_id = '006FX0000000004'",
        "valid_from",
    )
    shape = [
        (
            str(s["valid_from"]),
            s["stage"],
            s["amount_cents"],
            str(s["close_date"]),
            s["owner_id"],
        )
        for s in states
    ]
    assert shape == [
        ("2025-04-10 09:00:00", "Discovery", 800000, "2025-06-30", "005FX0000000001"),
        ("2025-05-05 09:00:00", "Discovery", 800000, "2025-06-30", "005FX0000000002"),
        ("2025-05-20 11:00:00", "Closed Won", 800000, "2025-05-20", "005FX0000000002"),
        ("2025-06-20 10:00:00", "Closed Won", 800000, "2025-06-02", "005FX0000000002"),
    ]
    assert [s["valid_to"] for s in states][:-1] == [s["valid_from"] for s in states][
        1:
    ] and states[-1]["valid_to"] is None
    assert states[1]["recorded_at"] == datetime(2025, 5, 5, 9)


def test_opportunity_state_respects_knowledge_time(store):
    states = rows(
        AsOf.contemporaneous(store, date(2025, 5, 31)),
        "opportunity_state",
        "opportunity_id = '006FX0000000004'",
        "valid_from",
    )
    assert [str(s["close_date"]) for s in states] == [
        "2025-06-30",
        "2025-06-30",
        "2025-05-20",
    ]


def test_a_null_amount_is_a_value_not_a_gap(tmp_path):
    folder = tmp_path / "sf"
    folder.mkdir()
    opp = {
        "Id": "006X1", "AccountId": "001X1", "OwnerId": "005X1", "CreatedById": "005X1", "Sourcing_User__c": None,
        "CampaignId": None, "LeadSource": None, "Type": "New Business", "StageName": "Discovery", "Amount": None,
        "CloseDate": "2025-02-01", "IsClosed": False, "IsWon": False, "CreatedDate": "2025-01-01T00:00:00Z",
        "SystemModstamp": "2025-01-01T00:00:00Z",
    }  # fmt: skip
    hist = [
        {"Id": "h1", "OpportunityId": "006X1", "StageName": "Discovery", "Amount": 5.0, "CloseDate": "2025-02-01", "CreatedDate": "2025-01-01T00:00:00Z"},
        {"Id": "h2", "OpportunityId": "006X1", "StageName": "Discovery", "Amount": None, "CloseDate": "2025-02-01", "CreatedDate": "2025-01-05T00:00:00Z"},
    ]  # fmt: skip
    from engine.harness.tests.test_evidence_support import write_rows

    write_rows(folder, "Opportunity", [opp])
    write_rows(folder, "OpportunityHistory", hist)
    write_manifest(
        folder, build_manifest(folder, "salesforce", datetime(2025, 3, 1, tzinfo=UTC))
    )
    store = load([folder])
    states = rows(
        AsOf.reconstructed(store, date(2025, 3, 1)),
        "opportunity_state",
        order="valid_from",
    )
    assert [s["amount_cents"] for s in states] == [500, None]


def test_selling_spells_carry_both_clocks(store):
    spells = rows(
        AsOf.reconstructed(store, NOW),
        "opportunity_spell",
        "opportunity_id = '006FX0000000008'",
        "spell_no",
    )
    assert [(s["spell_no"], s["outcome"], str(s["close_date"])) for s in spells] == [
        (1, "lost", "2025-04-22"),
        (2, "open", "None"),
    ]
    first, second = spells
    assert first["start_at"] == datetime(2025, 3, 20, 9) and first[
        "end_at"
    ] == datetime(2025, 4, 22, 11)
    assert first["end_recorded_at"] == datetime(2025, 4, 22, 11) and first[
        "close_date_recorded_at"
    ] == datetime(2025, 4, 22, 11)
    assert (
        second["start_at"] == datetime(2025, 5, 14, 9) == first["reopened_at"]
        and second["end_at"] is None
    )


def test_spell_outcomes_cover_won_lost_deleted_and_open(store):
    spells = rows(
        AsOf.reconstructed(store, NOW),
        "opportunity_spell",
        order="opportunity_id, spell_no",
    )
    outcome = {(s["opportunity_id"][-1], s["spell_no"]): s["outcome"] for s in spells}
    assert outcome == {
        ("1", 1): "won", ("2", 1): "won", ("3", 1): "lost", ("4", 1): "won",
        ("5", 1): "deleted", ("6", 1): "open", ("7", 1): "won", ("8", 1): "lost", ("8", 2): "open",
    }  # fmt: skip
    o2 = next(s for s in spells if s["opportunity_id"].endswith("2"))
    assert str(o2["close_date"]) == "2025-04-25" and o2["end_recorded_at"] == datetime(
        2025, 5, 6, 16
    )
    o1 = next(s for s in spells if s["opportunity_id"].endswith("1"))
    assert o1["amount_cents"] == 2400000
    o5 = next(s for s in spells if s["opportunity_id"].endswith("5"))
    assert o5["end_at"] == datetime(2025, 6, 30, 23)  # the deletion, an upper bound


def test_spells_obey_knowledge_time(store):
    spells = rows(
        AsOf.contemporaneous(store, date(2025, 4, 30)),
        "opportunity_spell",
        "opportunity_id = '006FX0000000002'",
    )
    assert [(s["outcome"], s["end_at"]) for s in spells] == [("open", None)]


def test_account_attributes_are_as_of_t(store):
    march = rows(
        AsOf.reconstructed(store, date(2025, 3, 31)),
        "account",
        "account_id = '001FX0000000001'",
    )[0]
    june = rows(
        AsOf.reconstructed(store, NOW), "account", "account_id = '001FX0000000001'"
    )[0]
    assert (march["tier"], june["tier"]) == ("Tier 3", "Tier 2")
    assert (
        march["billing_country"] == "United States"
    )  # the vendor's free text, kept raw


def test_lead_mql_date_restates_and_lead_events_are_listed(store):
    leads = {
        r["lead_id"]: r
        for r in rows(AsOf.reconstructed(store, date(2025, 4, 30)), "lead")
    }
    assert str(leads["00QFX0000000008"]["mql_date"]) == "2025-04-28"
    assert leads["00QFX0000000002"]["mql_date"] is None
    early = {
        r["lead_id"]: r
        for r in rows(AsOf.contemporaneous(store, date(2025, 4, 30)), "lead")
    }
    assert early["00QFX0000000008"]["mql_date"] is None
    events = rows(
        AsOf.reconstructed(store, NOW),
        "lead_event",
        "lead_id = '00QFX0000000004'",
        "effective_at",
    )
    assert [(e["event"], str(e["effective_at"])[:10]) for e in events] == [
        ("created", str(events[0]["effective_at"])[:10]), ("mql", "2025-03-20"), ("rejected", "2025-03-25"),
    ]  # fmt: skip


def test_demand_episode_view_keys_and_reason_classes(store):
    eps = rows(
        AsOf.reconstructed(store, NOW), "demand_episode", order="lead_id, offer_seq"
    )
    by = {(e["lead_id"][-1], e["offer_seq"]): e for e in eps}
    assert (
        by[("4", 1)]["reason_class"] == "fit"
        and by[("5", 1)]["reason_class"] == "capacity"
    )
    assert by[("4", 2)]["outcome"] == "open" and by[("4", 2)]["reason_class"] is None
    assert by[("2", 1)]["mql_linked"] is False and by[("1", 1)]["mql_linked"] is True
    assert len(eps) == 9


def test_person_roster_requisition_spend_campaign_touch_extract(store):
    asof = AsOf.reconstructed(store, NOW)
    people = rows(asof, "person")
    assert [p["user_id"] for p in people] == [
        "005FX0000000001",
        "005FX0000000002",
        "005FX0000000003",
        "005FX0000000004",
    ]
    assignments = rows(asof, "assignment", order="person_id, valid_from")
    assert [(a["person_id"], str(a["valid_from"]), a["valid_to"], a["team"]) for a in assignments][:2] == [
        ("P-001", "2024-01-10", None, "AE-Enterprise"), ("P-002", "2024-01-10", None, "AE-MidMarket"),
    ]  # fmt: skip
    reqs = {r["req_id"]: r for r in rows(asof, "requisition")}
    assert (
        reqs["REQ-001"]["status_at_t"] == "open"
        and reqs["REQ-002"]["status_at_t"] == "filled"
    )
    early = {
        r["req_id"]
        for r in rows(AsOf.reconstructed(store, date(2025, 1, 31)), "requisition")
    }
    assert early == {"REQ-002"}  # REQ-001 opened 2025-05-15
    spend = rows(asof, "spend", order="month, campaign_id")
    assert [(str(s["month"]), s["campaign_id"][-1], s["amount_cents"]) for s in spend] == [
        ("2025-03-01", "1", 400000), ("2025-04-01", "1", 450000), ("2025-04-01", "2", 120000),
    ]  # fmt: skip
    assert len(rows(asof, "campaign")) == 2 and len(rows(asof, "touch")) == 7
    assert len(rows(AsOf.contemporaneous(store, date(2025, 4, 30)), "extract")) == 2
    assert len(rows(asof, "extract")) == 7


def test_money_converts_to_cents_exactly(tmp_path):
    from engine.harness.tests.test_evidence_support import write_rows

    amounts = {
        "0.29": 29,
        "1.15": 115,
        "4.35": 435,
        "19.99": 1999,
        "0.07": 7,
        "1234567.89": 123456789,
        "8000": 800000,
    }
    folder = tmp_path / "sf"
    folder.mkdir()
    opps, hist = [], []
    for i, text in enumerate(amounts):
        opps.append({
            "Id": f"006X{i}", "AccountId": "001X1", "OwnerId": "005X1", "CreatedById": "005X1", "Sourcing_User__c": None,
            "CampaignId": None, "LeadSource": None, "Type": "New Business", "StageName": "Closed Won", "Amount": float(text),
            "CloseDate": "2025-02-01", "IsClosed": True, "IsWon": True, "CreatedDate": "2025-01-01T00:00:00Z",
            "SystemModstamp": "2025-01-01T00:00:00Z",
        })  # fmt: skip
        hist.append({"Id": f"h{i}", "OpportunityId": f"006X{i}", "StageName": "Closed Won", "Amount": float(text), "CloseDate": "2025-02-01", "CreatedDate": "2025-01-01T00:00:00Z"})  # fmt: skip
    write_rows(folder, "Opportunity", opps)
    write_rows(folder, "OpportunityHistory", hist)
    write_manifest(
        folder, build_manifest(folder, "salesforce", datetime(2025, 3, 1, tzinfo=UTC))
    )
    store = load([folder])
    got = {
        r["opportunity_id"]: r["amount_cents"]
        for r in rows(AsOf.reconstructed(store, date(2025, 3, 1)), "opportunity")
    }
    assert sorted(got.values()) == sorted(amounts.values())
    from engine.harness.evidence import bookings_by_month

    assert bookings_by_month(
        AsOf.reconstructed(store, date(2025, 3, 1)), "2025-02"
    ) == sum(amounts.values())


def test_lead_events_cover_admission_and_conversion(store):
    events = rows(
        AsOf.reconstructed(store, NOW),
        "lead_event",
        "lead_id = '00QFX0000000001'",
        "effective_at",
    )
    assert {
        (e["event"], str(e["effective_at"])[:10])
        for e in events
        if e["event"] != "created"
    } == {
        ("mql", "2025-01-25"),
        ("admitted", "2025-02-03"),
        ("converted", "2025-02-03"),
    }
    assert [e["event"] for e in events].count("created") == 1
    assert all(e["source_record_ids"] for e in events)

"""Counterexample estates built in code, one per fault an adversarial review found.

Each estate is small and independent of estate A, so the fixture cannot paper over a fault.
"""

import calendar
import random
from datetime import date, datetime

import pytest

from engine.harness.evidence import (
    AsOf,
    Coverage,
    ExtractError,
    Store,
    bookings_by_month,
    load,
)
from engine.harness.tests.test_evidence_support import (
    estate_dirs,
    lead,
    lh,
    ofh,
    ohist,
    opp,
    sf,
)

D = date.fromisoformat


def view(asof, name, where="TRUE", order="1"):
    cur = asof.store.con.cursor()
    cur.execute(
        f"SELECT * FROM asof_{name}(?, ?) WHERE {where} ORDER BY {order}",
        [asof.t, asof.k],
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def known(store, t, k):
    return AsOf(store, D(t), datetime.fromisoformat(k))


# ---- 1. records that no snapshot shows -------------------------------------


def history_only_estate(tmp_path, snapshot_in_second: bool):
    """O2 and O3 have history rows but O2 appears in a snapshot only after the landmark; O3 never does."""
    o1, o2 = opp("006X1"), opp("006X2", CreatedDate="2025-04-10T09:00:00Z")
    h1 = [
        ohist("h1", "006X1", "Discovery", 1000.0, "2025-12-31", "2025-01-05T09:00:00Z")
    ]
    h2 = [
        ohist("h2", "006X2", "Discovery", 2000.0, "2025-12-31", "2025-04-10T09:00:00Z"),
        ohist("h3", "006X2", "Proposal", 2000.0, "2025-12-31", "2025-04-20T09:00:00Z"),
    ]
    h3 = [
        ohist("h4", "006X3", "Discovery", 3000.0, "2025-12-31", "2025-04-12T09:00:00Z")
    ]
    first = sf(tmp_path, "2025-03-01T23:00:00Z", [o1], h1)
    second = sf(
        tmp_path,
        "2025-06-01T23:00:00Z",
        [o1, o2] if snapshot_in_second else [o1],
        h1 + h2 + h3,
    )
    return [first, second]


def test_a_record_with_history_but_no_snapshot_is_known_and_open(tmp_path):
    store = load(history_only_estate(tmp_path, snapshot_in_second=False))
    asof = known(store, "2025-05-01", "2025-05-01T23:59:59")
    assert asof.stage_at("006X2") == "Proposal"
    assert asof.status_at("Opportunity", "006X2").status == "present"
    assert asof.open_at("006X2") is True
    assert [
        s["outcome"]
        for s in view(asof, "opportunity_spell", "opportunity_id = '006X2'")
    ] == ["open"]


def test_a_later_snapshot_does_not_change_answers_at_an_earlier_k(tmp_path):
    without = load(history_only_estate(tmp_path / "a", snapshot_in_second=False))
    with_snapshot = load(history_only_estate(tmp_path / "b", snapshot_in_second=True))
    for k in ("2025-04-15T00:00:00", "2025-05-01T23:59:59"):
        a, b = known(without, "2025-05-01", k), known(with_snapshot, "2025-05-01", k)
        for opp_id in ("006X1", "006X2"):
            assert (
                a.stage_at(opp_id),
                a.open_at(opp_id),
                a.status_at("Opportunity", opp_id),
            ) == (
                b.stage_at(opp_id),
                b.open_at(opp_id),
                b.status_at("Opportunity", opp_id),
            )
        assert view(a, "opportunity_state", "opportunity_id = '006X2'") == view(
            b, "opportunity_state", "opportunity_id = '006X2'"
        )
        assert view(a, "opportunity_spell", "opportunity_id = '006X2'") == view(
            b, "opportunity_spell", "opportunity_id = '006X2'"
        )


def test_a_history_only_record_reports_missing_attributes_as_unavailable(tmp_path):
    store = load(history_only_estate(tmp_path, snapshot_in_second=False))
    asof = known(store, "2025-05-01", "2025-05-01T23:59:59")
    got = asof.field_at("Opportunity", "006X2", "Type")
    assert (got.value, got.unavailable) == (None, "record_not_in_snapshot")
    assert asof.field_at("Opportunity", "006X2", "StageName").value == "Proposal"
    row = view(asof, "opportunity", "opportunity_id = '006X2'")[0]
    assert row["type"] is None and row["stage"] == "Proposal"


def test_a_record_created_and_deleted_between_extracts_is_present_then_deleted(
    tmp_path,
):
    store = load(history_only_estate(tmp_path, snapshot_in_second=False))
    assert known(store, "2025-05-01", "2025-05-01T23:59:59").open_at("006X3") is True
    later = known(store, "2025-06-30", "2025-06-30T23:59:59")
    assert later.status_at("Opportunity", "006X3").status == "deleted"
    assert later.open_at("006X3") is False


# ---- 2. creation evidence respects K ----------------------------------------


def two_snapshots(tmp_path, **second):
    a = opp("006X1")
    h = [
        ohist("h1", "006X1", "Discovery", 1000.0, "2025-12-31", "2025-01-05T09:00:00Z")
    ]
    return [
        sf(tmp_path, "2025-03-01T23:00:00Z", [a], h),
        sf(tmp_path, "2025-06-01T23:00:00Z", [{**a, **second}], h),
    ]


@pytest.mark.parametrize(
    "field, value", [("CreatedDate", "2025-02-01T09:00:00Z"), ("Type", "Renewal")]
)
def test_a_later_extract_contradicting_an_immutable_field_is_an_error(
    tmp_path, field, value
):
    original = "2025-01-05T09:00:00Z" if field == "CreatedDate" else "New Business"
    with pytest.raises(ExtractError) as err:
        load(two_snapshots(tmp_path, **{field: value}))
    message = str(err.value)
    assert (
        "006X1" in message
        and field in message
        and value in message
        and original in message
    )


def test_the_creation_time_is_the_value_of_the_first_extract(tmp_path):
    store = load(two_snapshots(tmp_path))
    (created,) = store.con.execute(
        "SELECT created_at FROM record WHERE id = '006X1'"
    ).fetchone()
    assert created == datetime(2025, 1, 5, 9)


# ---- 3. per-field clocks -----------------------------------------------------


def clocks_estate(tmp_path):
    o = opp("006X1", OwnerId="005X2", StageName="Proposal")
    hs = [
        ohist("h1", "006X1", "Discovery", 1000.0, "2025-12-31", "2025-01-05T09:00:00Z"),
        ohist("h2", "006X1", "Proposal", 1000.0, "2025-12-31", "2025-03-05T09:00:00Z"),
    ]
    return [
        sf(
            tmp_path,
            "2025-06-01T23:00:00Z",
            [o],
            hs,
            [ofh("f1", "006X1", "005X1", "005X2", "2025-05-10T09:00:00Z")],
        )
    ]


def test_each_carried_value_has_its_own_recorded_time(tmp_path):
    store = load(clocks_estate(tmp_path))
    rows = view(
        known(store, "2025-06-01", "2025-06-01T23:59:59"),
        "opportunity_state",
        order="valid_from",
    )
    march = rows[1]
    assert march["stage"] == "Proposal" and march["stage_recorded_at"] == datetime(
        2025, 3, 5, 9
    )
    assert march["owner_id"] == "005X1" and march["owner_recorded_at"] == datetime(
        2025, 5, 10, 9
    )
    assert march["owner_source"].endswith("OpportunityFieldHistory/f1") and march[
        "stage_source"
    ].endswith("OpportunityHistory/h2")
    assert march["amount_recorded_at"] == datetime(2025, 1, 5, 9) and march[
        "close_date_recorded_at"
    ] == datetime(2025, 1, 5, 9)


@pytest.mark.parametrize(
    "landmark", ["2025-02-01T00:00:00", "2025-04-01T00:00:00", "2025-05-20T00:00:00"]
)
def test_exported_clocks_agree_with_calling_the_view_at_that_landmark(
    tmp_path, landmark
):
    store = load(clocks_estate(tmp_path))
    now = view(
        known(store, "2025-06-01", "2025-06-01T23:59:59"),
        "opportunity_state",
        order="valid_from",
    )
    then = {
        r["valid_from"]: r
        for r in view(
            known(store, "2025-06-01", landmark),
            "opportunity_state",
            order="valid_from",
        )
    }
    stamp = datetime.fromisoformat(landmark)
    checked = 0
    for row in now:
        if row["valid_from"] not in then:
            continue
        for column, clock in (
            ("stage", "stage_recorded_at"),
            ("amount_cents", "amount_recorded_at"),
            ("close_date", "close_date_recorded_at"),
            ("owner_id", "owner_recorded_at"),
        ):
            if row[clock] is not None and row[clock] <= stamp:
                assert then[row["valid_from"]][column] == row[column]
                checked += 1
            else:
                assert (
                    then[row["valid_from"]][column] != row[column]
                    or row[column] is None
                )
    assert checked > 0


def test_spell_values_carry_their_own_clocks_and_lineage(tmp_path):
    hs = [
        ohist("h1", "006X1", "Discovery", 1000.0, "2025-12-31", "2025-01-05T09:00:00Z"),
        ohist(
            "h2", "006X1", "Closed Won", 1000.0, "2025-03-10", "2025-03-10T09:00:00Z"
        ),
        ohist(
            "h3", "006X1", "Closed Won", 1500.0, "2025-03-10", "2025-04-01T09:00:00Z"
        ),
    ]
    store = load(
        [
            sf(
                tmp_path,
                "2025-06-01T23:00:00Z",
                [opp("006X1", StageName="Closed Won", Amount=1500.0)],
                hs,
            )
        ]
    )
    (spell,) = view(
        known(store, "2025-06-01", "2025-06-01T23:59:59"), "opportunity_spell"
    )
    assert spell["amount_cents"] == 150000 and spell["amount_recorded_at"] == datetime(
        2025, 4, 1, 9
    )
    assert spell["close_date_recorded_at"] == datetime(2025, 3, 10, 9)
    assert spell["amount_source"].endswith("h3") and spell[
        "close_date_source"
    ].endswith("h2")


# ---- 4. one representation of the commercial stock ---------------------------


def flow_estate(tmp_path):
    """Normal win, normal loss, reopen, plus the contradictory shapes the review named."""
    opps = [opp(f"006X{i}", CreatedDate="2025-01-05T09:00:00Z") for i in range(1, 8)]
    hs = []

    def rows(n, steps):
        for j, (stage, amount, close, at) in enumerate(steps):
            hs.append(ohist(f"h{n}_{j}", f"006X{n}", stage, amount, close, at))

    rows(
        1,
        [
            ("Discovery", 100.0, "2025-12-31", "2025-01-05T09:00:00Z"),
            ("Closed Won", 100.0, "2025-03-10", "2025-03-10T09:00:00Z"),
        ],
    )
    rows(
        2,
        [
            ("Discovery", 200.0, "2025-12-31", "2025-01-05T09:00:00Z"),
            ("Closed Lost", 200.0, "2025-02-10", "2025-02-10T09:00:00Z"),
            ("Proposal", 200.0, "2025-12-31", "2025-04-02T09:00:00Z"),
        ],
    )
    # 3: won May 1 with CloseDate July 1; deleted (absent from the June extract)
    rows(
        3,
        [
            ("Discovery", 300.0, "2025-12-31", "2025-01-05T09:00:00Z"),
            ("Closed Won", 300.0, "2025-07-01", "2025-05-01T09:00:00Z"),
        ],
    )
    # 4: closed in March, CloseDate corrected to June, reopened April 10
    rows(
        4,
        [
            ("Discovery", 400.0, "2025-12-31", "2025-01-05T09:00:00Z"),
            ("Closed Lost", 400.0, "2025-03-10", "2025-03-10T09:00:00Z"),
            ("Closed Lost", 400.0, "2025-06-01", "2025-03-20T09:00:00Z"),
            ("Proposal", 400.0, "2025-12-31", "2025-04-10T09:00:00Z"),
        ],
    )
    rows(
        5, [("Discovery", 500.0, "2025-12-31", "2025-01-05T09:00:00Z")]
    )  # 5: absent in June, back in July
    rows(6, [("Discovery", 600.0, "2025-12-31", "2025-01-05T09:00:00Z")])
    rows(
        7,
        [
            ("Discovery", 700.0, "2025-12-31", "2025-01-05T09:00:00Z"),
            ("Closed Won", 700.0, "2025-08-01", "2025-08-02T09:00:00Z"),
        ],
    )
    e1 = sf(
        tmp_path,
        "2025-05-15T23:00:00Z",
        opps,
        [h for h in hs if h["CreatedDate"] <= "2025-05-15T23:00:00Z"],
    )
    e2 = sf(
        tmp_path,
        "2025-06-15T23:00:00Z",
        [o for o in opps if o["Id"] not in ("006X3", "006X5")],
        [
            h
            for h in hs
            if h["CreatedDate"] <= "2025-06-15T23:00:00Z"
            and h["OpportunityId"] != "006X5"
        ],
    )
    e3 = sf(
        tmp_path,
        "2025-07-15T23:00:00Z",
        [o for o in opps if o["Id"] != "006X3"],
        [h for h in hs if h["CreatedDate"] <= "2025-07-15T23:00:00Z"],
    )
    e4 = sf(
        tmp_path, "2025-09-01T23:00:00Z", [o for o in opps if o["Id"] != "006X3"], hs
    )
    return [e1, e2, e3, e4]


def test_the_contradictory_shapes_are_flagged_not_presented_as_clean(tmp_path):
    store = load(flow_estate(tmp_path))
    asof = AsOf.reconstructed(store, D("2025-12-31"))
    by_deal = {}
    for e in view(
        asof, "opportunity_flow", order="opportunity_id, business_date, event"
    ):
        by_deal.setdefault(e["opportunity_id"], []).append(
            (e["event"], str(e["business_date"]), e["delta"], tuple(sorted(e["flags"])))
        )
    assert by_deal["006X3"] == [
        ("admission", "2025-01-05", 1, ()),
        (
            "deleted",
            "2025-06-15",
            -1,
            ("contradictory_boundary", "deletion_time_upper_bound"),
        ),
        ("win", "2025-07-01", 0, ("contradictory_boundary",)),
    ]
    assert by_deal["006X4"] == [
        ("admission", "2025-01-05", 1, ()),
        ("reopened", "2025-04-10", 0, ("contradictory_boundary",)),
        ("loss", "2025-06-01", 0, ("contradictory_boundary",)),
    ]
    assert by_deal["006X5"] == [
        ("admission", "2025-01-05", 1, ()),
        ("deleted", "2025-06-15", -1, ("deletion_time_upper_bound",)),
        ("reopened", "2025-07-15", 1, ("restoration_time_upper_bound", "restored")),
    ]
    assert [e[:3] for e in by_deal["006X2"]] == [
        ("admission", "2025-01-05", 1),
        ("loss", "2025-02-10", -1),
        ("reopened", "2025-04-02", 1),
    ]


def test_spells_and_open_at_agree_with_the_flow(tmp_path):
    store = load(flow_estate(tmp_path))
    asof = AsOf.reconstructed(store, D("2025-12-31"))
    spells = {
        (s["opportunity_id"], s["spell_no"]): s for s in view(asof, "opportunity_spell")
    }
    assert (
        spells["006X3", 1]["outcome"] == "deleted"
        and "contradictory_boundary" in spells["006X3", 1]["flags"]
    )
    assert (
        spells["006X4", 1]["outcome"] == "lost"
        and "contradictory_boundary" in spells["006X4", 1]["flags"]
    )
    assert (
        spells["006X2", 1]["outcome"] == "lost"
        and spells["006X2", 2]["outcome"] == "open"
    )
    assert spells["006X5", 1]["outcome"] == "open"
    for day, expect in {
        "2025-06-14": {"006X3": True, "006X4": True, "006X5": True},
        "2025-06-15": {"006X3": False, "006X4": True, "006X5": False},
        "2025-07-16": {"006X3": False, "006X4": True, "006X5": True},
    }.items():
        now = AsOf(store, D(day), asof.k)
        assert {i: now.open_at(i) for i in expect} == expect
    march = AsOf(
        store, D("2025-03-15"), datetime(2025, 3, 15, 23, 59, 59)
    )  # before the correction was made: closed
    assert march.open_at("006X4") is False
    assert (
        AsOf(store, D("2025-03-15"), asof.k).open_at("006X4") is True
    )  # known now: never commercially closed


MONTHS = [(D(f"2025-{m:02d}-01"), D(f"2025-{m:02d}-28")) for m in range(1, 10)]


@pytest.mark.parametrize("mode", ["reconstructed", "contemporaneous"])
def test_the_open_stock_identity_holds_month_over_month(tmp_path, mode):
    store = load(flow_estate(tmp_path))
    previous_end = D("2024-12-31")
    for first, _ in MONTHS:
        month_end = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        end = AsOf.at(store, month_end, mode)
        start = AsOf(store, previous_end, end.k)
        counts = {"admission": 0, "reopened": 0, "win": 0, "loss": 0, "deleted": 0}
        for e in view(end, "opportunity_flow", "delta <> 0"):
            if previous_end < e["business_date"] <= month_end:
                counts[e["event"]] += e["delta"] and 1
        assert len(start.open_ids()) + counts["admission"] + counts[
            "reopened"
        ] - counts["win"] - counts["loss"] - counts["deleted"] == len(end.open_ids()), (
            mode,
            month_end,
        )
        previous_end = month_end


# ---- 5. close and reopen at the same instant ---------------------------------


def test_close_and_reopen_at_the_same_timestamp_keep_the_closing_values(tmp_path):
    at = "2025-03-10T09:00:00Z"
    hs = [
        ohist("h1", "006X1", "Discovery", 1000.0, "2025-12-31", "2025-01-05T09:00:00Z"),
        ohist("h2", "006X1", "Closed Won", 500.0, "2025-03-09", at),
        ohist("h3", "006X1", "Proposal", 700.0, "2025-09-01", at),
    ]
    store = load(
        [
            sf(
                tmp_path,
                "2025-06-01T23:00:00Z",
                [
                    opp(
                        "006X1",
                        StageName="Proposal",
                        Amount=700.0,
                        CloseDate="2025-09-01",
                    )
                ],
                hs,
            )
        ]
    )
    first, second = view(
        known(store, "2025-06-01", "2025-06-01T23:59:59"),
        "opportunity_spell",
        order="spell_no",
    )
    assert (first["outcome"], str(first["close_date"]), first["amount_cents"]) == (
        "won",
        "2025-03-09",
        50000,
    )
    assert (second["outcome"], second["amount_cents"]) == ("open", 70000)


# ---- 6. ties between inferred and real evidence ------------------------------


def test_a_real_change_at_the_creation_instant_beats_the_inferred_initial_value(
    tmp_path,
):
    created = "2025-01-05T09:00:00Z"
    o = opp("006X1", OwnerId="005X2")
    hs = [ohist("h1", "006X1", "Discovery", 1000.0, "2025-12-31", created)]
    folder = sf(
        tmp_path,
        "2025-06-01T23:00:00Z",
        [o],
        hs,
        [ofh("f1", "006X1", "005X1", "005X2", created)],
    )
    owners = set()
    for seed in range(6):
        order = [folder, folder]
        random.Random(seed).shuffle(order)
        store = load(order)
        asof = known(store, "2025-01-05", "2025-06-01T23:59:59")
        owners.add(asof.owner_at("006X1"))
        states = view(asof, "opportunity_state")
        assert [s["owner_id"] for s in states] == ["005X2"]
    assert owners == {"005X2"}


# ---- 7. disappearing and reappearing records ---------------------------------


def test_a_record_that_reappears_is_restored_not_an_error(tmp_path):
    store = load(flow_estate(tmp_path))
    rows = store.con.execute(
        "SELECT field, effective_at FROM assertion WHERE id = '006X5' AND field IN ('_deleted', '_restored') ORDER BY effective_at"
    ).fetchall()
    assert [r[0] for r in rows] == ["_deleted", "_restored"]
    flags = {
        a.field: f
        for a, f in store.flagged_assertions()
        if a.id == "006X5" and a.field in ("_deleted", "_restored")
    }
    assert flags == {
        "_deleted": ("deletion_time_upper_bound",),
        "_restored": ("restoration_time_upper_bound",),
    }
    gap = known(store, "2025-07-01", "2025-09-01T23:59:59")
    assert gap.status_at("Opportunity", "006X5").status == "deleted"
    assert (
        known(store, "2025-08-01", "2025-09-01T23:59:59")
        .status_at("Opportunity", "006X5")
        .status
        == "present"
    )


# ---- 8. demand episodes and business time ------------------------------------


def demand_estate(tmp_path):
    hs = [
        lh(
            "l1",
            "00QX1",
            "Sales_Offered_Date__c",
            None,
            "2025-03-05",
            "2025-01-20T09:00:00Z",
        ),  # offered on a future date
        lh(
            "l2",
            "00QX1",
            "Sales_Offered_Date__c",
            "2025-03-05",
            "2025-02-10",
            "2025-02-11T09:00:00Z",
        ),
        lh("l3", "00QX1", "Disposition__c", None, "Admitted", "2025-02-20T09:00:00Z"),
    ]
    return [
        sf(
            tmp_path,
            "2025-06-01T23:00:00Z",
            leads=[
                lead(
                    "00QX1",
                    Sales_Offered_Date__c="2025-02-10",
                    Disposition__c="Admitted",
                )
            ],
            lhists=hs,
        )
    ]


def test_offers_dated_after_t_are_not_demand_at_t_and_numbering_stays_stable(tmp_path):
    store = load(demand_estate(tmp_path))
    k = "2025-06-01T23:00:00"
    at_feb = known(store, "2025-02-15", k).episodes("00QX1")
    assert [(e.offer_seq, str(e.offered_on), e.outcome) for e in at_feb] == [
        (2, "2025-02-10", "open")
    ]
    at_apr = known(store, "2025-04-01", k).episodes("00QX1")
    assert [(e.offer_seq, str(e.offered_on), e.outcome) for e in at_apr] == [
        (1, "2025-03-05", "open"),
        (2, "2025-02-10", "admitted"),
    ]
    assert known(store, "2025-01-31", k).episodes("00QX1") == []


# ---- 9. no history fields at all ---------------------------------------------


def test_an_estate_with_no_history_fields_loads_and_answers(tmp_path):
    none = Coverage((), {})
    store = load(estate_dirs(), none)
    assert store.coverage == none
    asof = AsOf.reconstructed(store, D("2025-04-30"))
    assert asof.stage_at("006FX0000000002") == "Negotiation"
    assert (
        bookings_by_month(
            AsOf.reconstructed(store, D("2025-12-31")), "2025-03"
        ).total_cents
        == 2400000
    )
    assert len(asof.open_ids()) > 0


def test_an_empty_coverage_survives_reopening_a_store_on_disk(tmp_path):
    path = tmp_path / "e.duckdb"
    store = load(estate_dirs(), Coverage((), {}), store=Store(path))
    store.con.close()
    assert Store(path).coverage == Coverage((), {})


# ---- 10. unknown amounts ------------------------------------------------------


def test_a_won_deal_with_an_unknown_amount_makes_the_total_a_lower_bound(tmp_path):
    hs = [
        ohist(
            "h1", "006X1", "Closed Won", 1000.0, "2025-03-10", "2025-03-10T09:00:00Z"
        ),
        ohist("h2", "006X2", "Closed Won", None, "2025-03-12", "2025-03-12T09:00:00Z"),
    ]
    o = [
        opp("006X1", StageName="Closed Won"),
        opp("006X2", StageName="Closed Won", Amount=None),
    ]
    store = load([sf(tmp_path, "2025-06-01T23:00:00Z", o, hs)])
    got = bookings_by_month(AsOf.reconstructed(store, D("2025-06-01")), "2025-03")
    assert (got.total_cents, got.deals, got.unknown_amount, got.bound) == (
        100000,
        2,
        1,
        "lower_bound",
    )
    clean = bookings_by_month(AsOf.reconstructed(store, D("2025-06-01")), "2025-04")
    assert (clean.total_cents, clean.deals, clean.unknown_amount, clean.bound) == (
        0,
        0,
        0,
        "exact",
    )

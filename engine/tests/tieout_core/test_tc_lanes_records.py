"""The records shard: which deals each actual cell is made of, so the browser lists and never sums."""

import copy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from engine.tests.tieout_core.lanes_support import mutated
from engine.tieout_core import (
    lanes_records,
    lanes_replay,
)
from engine.tieout_core import (
    lanes_records_contract as contract,
)
from engine.tieout_core.fiscal import FiscalYear
from engine.tieout_core.records import Deal, Observation, Profile, StageDef

D = Decimal
FY = FiscalYear(date(2026, 2, 1))
AS_OF = date(2026, 5, 15)  # Q1 closed, Q2 in progress


def deal(id, created, close=None, won=False, arr="100", segment="a", owner="x"):
    closed = close is not None
    stage = ("Won" if won else "Lost") if closed else "S1"
    return Deal(
        1,
        id,
        "new_business",
        segment,
        stage,
        D(arr),
        date.fromisoformat(created),
        close and date.fromisoformat(close),
        closed,
        closed and won,
        owner,
        f"{id} deal",
        owner.upper(),
    )


def small():
    deals = (
        deal("carried-won", "2025-11-01", "2026-03-10", True, "300"),
        deal("carried-lost", "2025-12-01", "2026-02-20", False),
        deal("new-won", "2026-02-10", "2026-04-20", True, "200"),
        deal("open-old", "2025-10-01"),
        deal("open-new", "2026-03-01", owner="y"),
        deal("no-owner", "2026-04-10", owner=""),
        deal("after", "2026-05-20"),  # created after the as-of date: not yet a fact
    )
    stages = (StageDef("Discovery", "S1", 1, D("0.1")), StageDef("Won", "Won", 99, D(1)), StageDef("Lost", "Lost", 100, D(0)))  # fmt: skip
    return SimpleNamespace(
        pop=SimpleNamespace(
            deals=deals,
            observations=(
                Observation("new-won", date(2026, 2, 11), D(100), date(2026, 5, 1)),
            ),
        ),
        as_of=AS_OF,
        profile=Profile(stages, FY, {}, {}),
        params=SimpleNamespace(horizon_days=90),
    )


def members(doc, row, period, name):
    r = next((r for r in doc["rows"] if r["path"] == row), None)
    return [] if r is None else r["periods"][period][name]  # no row: no deal behind it


def test_a_cell_is_the_deals_that_make_it_by_hand():
    doc = lanes_records.document(small(), "c")
    t = ["total"]
    assert members(doc, t, "FY26", "created") == ["new-won", "no-owner", "open-new"]
    assert members(doc, t, "FY26", "won_carried_in") == ["carried-won"]
    assert members(doc, t, "FY26", "won_created_in_period") == ["new-won"]
    assert members(doc, t, "Q1FY26", "won_carried_in") == ["carried-won"]
    assert members(doc, t, "Q1FY26", "won_created_in_period") == ["new-won"]
    assert members(doc, t, "Q2FY26", "won_carried_in") == []
    assert members(doc, t, "Q2FY26", "won_created_in_period") == []
    assert members(doc, t, "FY26", "open") == ["carried-lost", "carried-won", "open-old"]  # fmt: skip
    assert members(doc, t, "Q2FY26", "open") == ["no-owner", "open-new", "open-old"]
    assert members(doc, t, "Q3FY26", "open") is None  # not begun
    assert members(doc, ["segment", "a", "owner", "unassigned"], "FY26", "created") == ["no-owner"]  # fmt: skip


def test_a_modeled_deal_or_a_deal_after_the_as_of_date_is_never_a_member():
    doc = lanes_records.document(small(), "c")
    assert "after" not in doc["records"]
    for row in doc["rows"]:
        for sets in row["periods"].values():
            assert "after" not in {i for v in sets.values() for i in v or ()}


def test_a_record_carries_what_a_drill_needs_and_each_deal_is_stored_once():
    doc = lanes_records.document(small(), "c")
    assert doc["records"]["new-won"] == {
        "id": "new-won",
        "name": "new-won deal",
        "segment": "a",
        "owner": "x",
        "owner_name": "X",
        "created": "2026-02-10",
        "close": "2026-04-20",
        "stage": "Won",
        "status": "won",
        "arr_first": "100.00",
        "arr": "200.00",
    }
    assert doc["records"]["no-owner"]["arr_first"] is None  # no first amount on record
    assert set(doc["records"]) == {d.id for d in small().pop.deals if d.id != "after"}


def test_the_text_keeps_a_list_of_ids_and_a_record_each_on_one_line_and_is_json():
    text = lanes_records.text(lanes_records.document(small(), "c"))
    import json

    assert json.loads(text) == lanes_records.document(small(), "c")
    assert '"won_carried_in": ["carried-won"]' in text
    assert text.endswith("\n") and text.count("\n") < 400


# ---- the real companies


def shard_of(built):
    company, state, _, docs = built
    return lanes_records.document(state, company), [d for _, d in docs.values()]


def test_every_cell_of_every_scenario_counts_and_sums_to_its_records(built):
    shard, docs = shard_of(built)
    assert shard["records"]
    for doc in docs:
        assert contract.validate(shard, doc) == []


def test_the_shard_replays_from_the_raw_deals(built):
    _, state, _, _ = built
    shard, _ = shard_of(built)
    assert lanes_replay.records(state, shard) == []


def test_the_shard_stays_under_a_megabyte_and_a_half(built):
    shard, _ = shard_of(built)
    assert len(lanes_records.text(shard).encode()) < 1_500_000


def test_sapling_largest_segment_cells_list_exactly_as_many_records_as_they_count(
    built,
):
    company, _, _, docs = built
    if company != "sapling-industries":
        pytest.skip("Sapling's figures")
    shard, _ = shard_of(built)
    _, doc = docs["as-signed"]
    for r in doc["periods"][0]["rows"]:
        if r["path"][:2] == ["segment", "enterprise"]:
            c = r["cells"]
            got = members(shard, r["path"], "FY26", "created")
            assert D(len(got)) == D(c["created"]["actual"])
            won = members(shard, r["path"], "FY26", "won_carried_in") + members(shard, r["path"], "FY26", "won_created_in_period")  # fmt: skip
            assert D(len(won)) == D(c["won"]["actual"])
            assert sum(D(shard["records"][i]["arr"]) for i in won) == D(c["bookings"]["actual"])  # fmt: skip


# ---- tampering and mutated inputs


@pytest.fixture
def parts(built):
    shard, docs = shard_of(built)
    return copy.deepcopy(shard), docs[0]


def found(parts, edit):
    shard, doc = copy.deepcopy(parts)
    edit(shard)
    return contract.validate(shard, doc)


def a_row(shard, name="created"):
    return next(
        r for r in shard["rows"] if len(r["path"]) == 4 and r["periods"]["FY26"][name]
    )


def test_a_dropped_or_a_duplicated_or_an_unknown_id_is_found(parts):
    def drop(s):
        a_row(s)["periods"]["FY26"]["created"].pop()

    def dup(s):
        got = a_row(s)["periods"]["FY26"]["created"]
        got.append(got[0])

    def ghost(s):
        a_row(s)["periods"]["FY26"]["created"][0] = "no-such-deal"

    assert any("created" in p for p in found(parts, drop))
    assert found(parts, dup)
    assert any("record" in p for p in found(parts, ghost))


def test_a_changed_amount_or_date_is_found_in_the_sums(parts):
    def money(s):
        i = a_row(s, "won_carried_in")["periods"]["FY26"]["won_carried_in"][0]
        s["records"][i]["arr"] = "1.00"

    def date_(s):
        i = a_row(s)["periods"]["FY26"]["created"][0]
        s["records"][i]["created"] = "2001-01-01"

    assert any("bookings" in p or "cycle" in p for p in found(parts, money))
    assert found(parts, date_)


def test_a_record_under_the_wrong_owner_or_a_won_deal_listed_as_open_is_found(parts):
    def owner(s):
        i = a_row(s)["periods"]["FY26"]["created"][0]
        s["records"][i]["owner"] = "somebody-else"

    assert any("owner" in p for p in found(parts, owner))


def test_the_replay_finds_a_missing_member_and_an_extra_one(built):
    _, state, _, _ = built
    shard, _ = shard_of(built)
    gone = copy.deepcopy(shard)
    a_row(gone)["periods"]["FY26"]["created"].pop()
    assert lanes_replay.records(state, gone)
    extra = copy.deepcopy(shard)
    other = next(i for i in extra["records"] if i not in a_row(extra)["periods"]["FY26"]["created"])  # fmt: skip
    a_row(extra)["periods"]["FY26"]["created"].append(other)
    assert lanes_replay.records(state, extra)


def test_inputs_that_change_the_lanes_still_give_a_shard_that_counts_and_replays(
    tmp_path,
):
    def mix(rows):
        for i, r in enumerate(rows):
            if i % 6 == 0:
                r["owner_id"] = r["owner"] = ""
            if i % 11 == 0:
                r["segment"] = ""

    doc, _, problems = mutated("sprout-labs", tmp_path, deals=mix)
    assert problems == []
    assert any(r["path"][-1] == "unassigned" for r in doc["periods"][0]["rows"])

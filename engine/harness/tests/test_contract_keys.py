import pytest

from engine.harness.contract.keys import (
    ASSERTION_FIELDS,
    CANONICAL_TABLES,
    DELETED_FIELD,
    DEMAND_OUTCOMES,
    Assertion,
    lane_key,
    parse_lane_key,
)


def test_table_list_matches_the_design():
    assert set(CANONICAL_TABLES) == {
        "account", "person", "assignment", "requisition", "lead", "lead_event",
        "opportunity", "opportunity_state", "campaign", "touch", "spend",
        "demand_episode", "extract",
    }  # fmt: skip


def test_every_table_has_a_key_and_a_grain():
    for name, table in CANONICAL_TABLES.items():
        assert table.name == name
        assert table.key and len(set(table.key)) == len(table.key)
        assert table.grain.startswith("one row per")


def test_interval_tables_are_keyed_by_validity_start():
    assert CANONICAL_TABLES["opportunity_state"].key == ("opportunity_id", "valid_from")
    assert CANONICAL_TABLES["assignment"].key == ("person_id", "valid_from")


def test_demand_episode_is_one_row_per_offer():
    table = CANONICAL_TABLES["demand_episode"]
    assert table.key == ("lead_id", "offer_seq")
    assert "offer" in table.grain and "MQL" not in table.key
    assert {"admitted", "rejected", "expired", "open"} == set(DEMAND_OUTCOMES)


def test_assertion_tuple_order_is_the_design_order():
    assert ASSERTION_FIELDS == (
        "entity", "id", "field", "value", "effective_at", "recorded_at", "source", "extract_id",
    )  # fmt: skip
    assert Assertion._fields == ASSERTION_FIELDS
    assert DELETED_FIELD == "_deleted"


def test_lane_key_is_sorted_and_round_trips():
    key = lane_key({"source": "Paid", "segment": "SMB"})
    assert key == "segment=SMB;source=Paid"
    assert parse_lane_key(key) == {"segment": "SMB", "source": "Paid"}
    assert lane_key({}) == "*" and parse_lane_key("*") == {}


@pytest.mark.parametrize("bad", ["", "a", "a=b;", "a=b;a=c", "=b", "a=;b=c"])
def test_bad_lane_keys_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_lane_key(bad)

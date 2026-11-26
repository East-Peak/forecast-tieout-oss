from dataclasses import replace
from datetime import date
from decimal import Decimal

from engine.tieout_core.history import UNKNOWN_STAGE, as_known_at, latest_known_date
from engine.tieout_core.records import Dataset, Deal, Observation, Transition


def _deal(id, created, close=None, stage="S1", won=False, arr="100"):
    closed = stage in ("Won", "Lost")
    return Deal(0, id, "new_business", "mm", stage, Decimal(arr), created, close, closed, won)


DATA = Dataset(
    deals=(
        _deal("WON_EARLY", date(2025, 1, 1), date(2025, 3, 1), "Won", True, "500"),
        _deal("WON_LATE", date(2025, 1, 1), date(2025, 9, 1), "Won", True, "700"),
        _deal("OPEN", date(2025, 2, 1), date(2026, 1, 15), "S4", arr="300"),
        _deal("FUTURE", date(2025, 8, 1), date(2025, 12, 1), "Lost"),
    ),
    transitions=(
        Transition("WON_LATE", "S1", date(2025, 1, 1)),
        Transition("WON_LATE", "S3", date(2025, 4, 1)),
        Transition("WON_LATE", "Won", date(2025, 9, 1)),
        Transition("OPEN", "S2", date(2025, 2, 1)),
        Transition("OPEN", "S4", date(2025, 7, 1)),
    ),
    observations=(
        Observation("WON_LATE", date(2025, 1, 1), Decimal("650"), date(2025, 5, 1)),
        Observation("WON_LATE", date(2025, 5, 2), Decimal("680"), date(2025, 7, 1)),
        Observation("WON_LATE", date(2025, 9, 1), Decimal("700"), date(2025, 9, 1)),
    ),
)

CUT = date(2025, 6, 1)


def _by_id(data):
    return {d.id: d for d in data.deals}


def test_deals_created_after_the_cutoff_disappear():
    assert "FUTURE" not in _by_id(as_known_at(DATA, CUT))


def test_outcomes_known_by_the_cutoff_are_kept_exactly():
    assert _by_id(as_known_at(DATA, CUT))["WON_EARLY"] == DATA.deals[0]


def test_later_outcomes_are_reopened_at_their_stage_then():
    late = _by_id(as_known_at(DATA, CUT))["WON_LATE"]
    assert (late.stage, late.is_closed, late.is_won) == ("S3", False, False)


def test_open_amount_and_expected_close_come_from_the_latest_observation():
    late = _by_id(as_known_at(DATA, CUT))["WON_LATE"]
    assert (late.arr, late.close) == (Decimal("680"), date(2025, 7, 1))


def test_without_an_observation_amount_and_expected_close_are_unknown():
    # The final values are never reused as past facts.
    open_deal = _by_id(as_known_at(DATA, CUT))["OPEN"]
    assert (open_deal.stage, open_deal.arr, open_deal.close) == ("S2", None, None)


def test_open_deal_without_any_history_has_unknown_stage():
    data = replace(DATA, transitions=())
    assert _by_id(as_known_at(data, CUT))["OPEN"].stage == UNKNOWN_STAGE


def test_nothing_after_the_cutoff_survives():
    truncated = as_known_at(DATA, CUT)
    assert latest_known_date(truncated) <= CUT
    assert latest_known_date(DATA) == date(2025, 12, 1)

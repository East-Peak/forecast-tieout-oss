"""Tranche 1, part D: estate A is the acceptance test.

Every case of expected.yaml, in both as-of modes, answered through the public API
only. A failure names the case and the mode.
"""

from datetime import date

import pytest

from engine.harness.evidence import (
    AsOf,
    bookings_by_month,
    demand_outcomes,
    load,
    mql_count,
)
from engine.harness.tests.test_evidence_support import CASES, MODES, estate_dirs


@pytest.fixture(scope="module")
def store():
    return load(estate_dirs())


def iso(moment):
    return None if moment is None else moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def answer(asof: AsOf, case: dict) -> dict:
    kind, args = case["kind"], case["args"]
    if kind == "bookings":
        return {"value_cents": bookings_by_month(asof, args["month"])}
    if kind == "stage_at":
        return {"value": asof.stage_at(args["opportunity"])}
    if kind == "status_at":
        status = asof.status_at("Opportunity", args["opportunity"])
        return {
            "status": status.status,
            **({"flags": list(status.flags)} if status.flags else {}),
        }
    if kind == "open_at":
        return {"open": asof.open_at(args["opportunity"])}
    if kind == "owner_at":
        return {"value": asof.owner_at(args["opportunity"])}
    if kind == "open_count":
        ids = asof.open_ids()
        return {"count": len(ids), "ids": ids}
    if kind == "closing":
        closing = asof.closing(args["opportunity"])
        return {
            "close_date": None
            if closing.close_date is None
            else closing.close_date.isoformat(),
            "observed_closed_recorded_at": iso(closing.observed_closed_recorded_at),
        }
    if kind == "mql_count":
        return {"count": mql_count(asof, args["month"])}
    if kind == "demand_outcomes":
        out = demand_outcomes(asof, args["offered_month"])
        return {
            "counts": out.counts,
            **({"reason_classes": out.reason_classes} if out.reason_classes else {}),
        }
    if kind == "episodes_of_lead":
        return {
            "episodes": [
                {
                    "offer_seq": e.offer_seq,
                    "offered_on": e.offered_on.isoformat(),
                    "mql_linked": e.mql_linked,
                    "outcome": e.outcome,
                }
                for e in asof.episodes(args["lead"])
            ]
        }
    if kind == "field_at":
        got = asof.field_at(args["entity"], args["id"], args["field"])
        if got.unavailable:
            return {"unavailable": got.unavailable}
        return {"value": got.value, **({"flags": list(got.flags)} if got.flags else {})}
    if kind == "object_available":
        got = asof.availability(args["system"], args["object"])
        if got.unavailable:
            return {"unavailable": got.unavailable}
        return {
            "available": True,
            **(
                {"rows_in_first_extract": got.rows_in_first_extract}
                if "rows_in_first_extract" in case[asof.mode]
                else {}
            ),
        }
    raise AssertionError(kind)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_expected_answer(store, case, mode):
    asof = AsOf.at(store, date.fromisoformat(case["t"]), mode)
    assert answer(asof, case) == case[mode]


def test_the_two_modes_use_the_documented_knowledge_instants(store):
    t = date(2025, 5, 31)
    assert AsOf.reconstructed(store, t).k == store.latest_extract_at
    assert AsOf.contemporaneous(store, t).k.isoformat() == "2025-05-31T23:59:59"
    with pytest.raises(ValueError, match="mode"):
        AsOf.at(store, t, "now")


def test_stage_at_and_open_at_are_never_mixed(store):
    asof = AsOf.reconstructed(store, date(2025, 5, 31))
    assert asof.stage_at("006FX0000000007") == "Negotiation"
    assert asof.open_at("006FX0000000007") is False


def test_an_unknown_object_is_refused(store):
    with pytest.raises(ValueError, match="unknown object"):
        AsOf.reconstructed(store, date(2025, 5, 31)).field_at("Nope", "x", "y")

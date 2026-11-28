"""The catalog's verified queries, each a question in words, the call, the answer and who checked it."""

import pytest

from engine.harness.catalog import load_catalog
from engine.harness.query import query
from engine.harness.tests.test_query_support import CATALOG_PATH

CATALOG = load_catalog(CATALOG_PATH)


def test_there_are_at_least_eight_verified_queries_with_provenance():
    assert len(CATALOG.verified_queries) >= 8
    assert all(
        q.question and q.verified_by and q.verified_at and q.fixture
        for q in CATALOG.verified_queries
    )


@pytest.mark.parametrize("vq", CATALOG.verified_queries, ids=lambda q: q.id)
def test_verified_query(vq, estate):
    assert vq.fixture == "estate_a"
    call = dict(vq.call)
    window = tuple(call["window"]) if call.get("window") else None
    cells = query(
        estate,
        CATALOG,
        call["metric"],
        call.get("group_by", []),
        call.get("filters"),
        window,
        call["as_of"],
        known_at=call.get("known_at"),
        mode=call.get("mode"),
    )
    got = {c.key: c for c in cells}
    want = {tuple(e["key"]): e for e in vq.expect["cells"]}
    assert set(got) == set(want), f"{vq.question}: cells {sorted(got)}"
    for key, expect in want.items():
        cell = got[key]
        assert (
            cell.value == pytest.approx(expect["value"])
            if expect["value"] is not None
            else cell.value is None
        ), (key, cell.value)
        assert cell.applicability == expect.get("applicability", "applicable"), key
        assert cell.availability == expect.get("availability", "measured"), key
        assert cell.availability_reason == expect.get("reason"), key
        for field in ("numerator", "denominator"):
            if field in expect:
                assert getattr(cell, field) == expect[field], (key, field)
        assert cell.contract.bound == expect.get("bound", cell.contract.bound)

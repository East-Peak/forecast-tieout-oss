"""query() on estate A: sums, dimensions, attribute time, availability and applicability."""

import pytest

from engine.harness.catalog import load_catalog
from engine.harness.query import query
from engine.harness.tests.test_query_support import (
    D,
    by_key,
    catalog_text,
    values,
)

JAN_JUN = (D("2025-01-01"), D("2025-06-30"))
T = D("2025-06-30")


def run(estate, cat, metric, group_by=(), window=JAN_JUN, as_of=T, **kw):
    return query(
        estate, cat, metric, group_by, kw.pop("filters", None), window, as_of, **kw
    )


def test_bookings_by_month_reconstructed(estate, cat):
    cells = run(estate, cat, "bookings", ["month"])
    assert values(cells) == {
        ("2025-01",): 0,
        ("2025-02",): 0,
        ("2025-03",): 2_400_000,
        ("2025-04",): 1_500_000,
        ("2025-05",): 1_200_000,
        ("2025-06",): 800_000,
    }
    assert all(
        c.applicability == "applicable"
        and c.availability == "measured"
        and c.derivation == "measured"
        for c in cells
    )


def test_bookings_total_has_the_empty_key_and_a_contract(estate, cat):
    (cell,) = run(estate, cat, "bookings")
    assert cell.key == () and cell.value == 5_900_000
    c = cell.contract
    assert (c.metric, c.metric_version, c.t, c.window) == ("bookings", "1", T, JAN_JUN)
    assert (
        c.k.isoformat() == "2025-06-30T23:00:00"
        and c.bound == "exact"
        and c.eligible == 4
    )


def test_march_bookings_differ_by_mode(estate, cat):
    march = (D("2025-03-01"), D("2025-03-31"))
    recon = run(
        estate,
        cat,
        "bookings",
        window=march,
        as_of=D("2025-03-31"),
        mode="reconstructed",
    )
    contemp = run(
        estate,
        cat,
        "bookings",
        window=march,
        as_of=D("2025-03-31"),
        mode="contemporaneous",
    )
    assert recon[0].value == 2_400_000 and contemp[0].value == 2_000_000
    assert contemp[0].contract.k.isoformat() == "2025-03-31T23:59:59"


def test_window_is_clipped_to_t_and_a_window_after_t_is_unavailable(estate, cat):
    (cell,) = run(
        estate,
        cat,
        "bookings",
        window=(D("2025-01-01"), D("2025-12-31")),
        as_of=D("2025-04-30"),
    )
    assert (
        cell.contract.window == (D("2025-01-01"), D("2025-04-30"))
        and "window_clipped_to_t" in cell.contract.flags
    )
    (late,) = run(estate, cat, "bookings", window=(D("2025-08-01"), D("2025-08-31")))
    assert (late.value, late.availability, late.availability_reason) == (
        None,
        "unavailable",
        "window_after_as_of",
    )


def test_full_member_cross_product_keeps_zero_distinct(estate, cat):
    cells = by_key(run(estate, cat, "bookings", ["segment"]))
    assert set(cells) == {("Enterprise",), ("Mid-Market",), ("SMB",), ("Unknown",)}
    assert (
        cells[("Enterprise",)].value == 0
        and cells[("Enterprise",)].availability == "measured"
    )
    assert (
        cells[("SMB",)].value == 3_200_000 and cells[("Mid-Market",)].value == 2_700_000
    )


def test_attribute_time_at_creation_does_not_move_with_a_later_retiering(estate, cat):
    # account 001FX0000000001 was Tier 3 when its deals were created and became Tier 2 on 06-30
    current = load_catalog(
        catalog_text().replace(
            "attribute_time: at_creation   # re-tiering",
            "attribute_time: current   # re-tiering",
        )
    )
    at_creation = values(run(estate, cat, "bookings", ["segment"]))
    now = values(run(estate, current, "bookings", ["segment"]))
    assert (
        at_creation[("SMB",)] == 3_200_000
        and now[("SMB",)] == 0
        and now[("Mid-Market",)] == 5_900_000
    )
    assert sum(at_creation.values()) == sum(now.values()) == 5_900_000


def test_hierarchy_rolls_up_and_conserves(estate, cat):
    leaf = values(run(estate, cat, "bookings", ["source"]))
    group = values(run(estate, cat, "bookings", ["source.group"]))
    assert leaf[("Paid",)] == 3_500_000 and leaf[("BDR Outbound",)] == 2_400_000
    assert group == {
        ("Marketing",): 3_500_000,
        ("Sales",): 2_400_000,
        ("Partner",): 0,
        ("Unknown",): 0,
    }
    assert sum(leaf.values()) == sum(group.values()) == 5_900_000


def test_unknown_not_applicable_and_total_are_never_merged(estate, cat):
    cells = by_key(
        run(
            estate,
            cat,
            "mqls",
            ["source"],
            window=(D("2025-01-01"), D("2025-04-30")),
            as_of=D("2025-04-30"),
        )
    )
    assert (
        cells[("BDR Outbound",)].applicability == "not_applicable"
        and cells[("BDR Outbound",)].value is None
    )
    assert cells[("Partner",)].applicability == "not_applicable"
    assert (
        cells[("Unknown",)].applicability == "applicable"
        and cells[("Unknown",)].value is not None
    )
    (total,) = run(
        estate,
        cat,
        "mqls",
        window=(D("2025-01-01"), D("2025-04-30")),
        as_of=D("2025-04-30"),
    )
    assert total.key == () and total.applicability == "applicable"
    assert total.value == sum(c.value for c in cells.values() if c.value is not None)


def test_missing_instrumentation_is_unavailable_never_not_applicable(estate, cat):
    march = (D("2025-03-01"), D("2025-03-31"))
    cells = run(
        estate,
        cat,
        "bookings",
        ["segment"],
        window=march,
        as_of=D("2025-03-31"),
        mode="contemporaneous",
    )
    assert {c.availability for c in cells} == {"unavailable"}
    assert {c.availability_reason for c in cells} == {
        "no_extract_at_or_before_known_at"
    }
    assert {c.applicability for c in cells} == {"applicable"} and all(
        c.value is None for c in cells
    )
    (total,) = run(
        estate,
        cat,
        "bookings",
        window=march,
        as_of=D("2025-03-31"),
        mode="contemporaneous",
    )
    assert total.availability == "measured"  # the opportunity history alone answers it


def test_filters_select_members_at_any_level(estate, cat):
    (cell,) = run(estate, cat, "bookings", filters={"source.group": ["Marketing"]})
    assert cell.value == 3_500_000
    (none,) = run(estate, cat, "bookings", filters={"segment": ["Enterprise"]})
    assert none.value == 0 and none.availability == "measured"


def test_bad_requests_raise(estate, cat):
    with pytest.raises(ValueError):
        run(estate, cat, "bookings", ["nope"])
    with pytest.raises(ValueError):
        run(estate, cat, "bookings", ["month"], window=None)
    with pytest.raises(ValueError):
        run(estate, cat, "bookings", mode="contemporaneous", known_at=D("2025-06-30"))
    with pytest.raises(KeyError):
        run(estate, cat, "ghost")

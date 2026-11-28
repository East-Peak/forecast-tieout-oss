"""Two catalogs, one evidence set: additive metrics conserve, a mapping version changes slices and never
totals, and a new dimension is YAML only."""

from pathlib import Path

import pytest

from engine.harness.catalog import load_catalog
from engine.harness.evidence import load
from engine.harness.query import query
from engine.harness.tests.test_evidence_support import ohist, opp, write_extract
from engine.harness.tests.test_query_dimensions import account
from engine.harness.tests.test_query_support import ADAPTERS, D, catalog_text, values

W = (D("2025-01-01"), D("2025-06-30"))
T = D("2025-06-30")
ADDITIVE = ["bookings", "won_deals", "opportunities_created", "mqls", "demand_offered"]


@pytest.fixture(scope="module")
def coarse():
    return load_catalog(ADAPTERS / "catalog_coarse.yaml")


def ask(estate, cat, metric, group_by=(), **kw):
    return query(estate, cat, metric, group_by, None, W, T, **kw)


@pytest.mark.parametrize("metric", ADDITIVE)
def test_additive_metrics_conserve_to_identical_totals_under_both_catalogs(
    estate, cat, coarse, metric
):
    (fine_total,) = ask(estate, cat, metric)
    (coarse_total,) = ask(estate, coarse, metric)
    assert fine_total.value == coarse_total.value
    assert (
        sum(
            c.value for c in ask(estate, cat, metric, ["source"]) if c.value is not None
        )
        == fine_total.value
    )
    assert (
        sum(
            c.value
            for c in ask(estate, coarse, metric, ["source"])
            if c.value is not None
        )
        == fine_total.value
    )


def test_the_coarse_slices_are_exactly_the_fine_hierarchy_rolled_up(
    estate, cat, coarse
):
    for metric in ("bookings", "opportunities_created", "mqls"):
        fine = values(ask(estate, cat, metric, ["source"]))
        coarse_values = values(ask(estate, coarse, metric, ["source"]))
        marketing = sum(fine[(m,)] or 0 for m in ("Paid", "Events", "Inbound", "ABM"))
        sales = sum(fine[(m,)] or 0 for m in ("BDR Outbound", "AE Self-Sourced"))
        assert coarse_values[("Marketing",)] == marketing, metric
        assert (coarse_values[("Sales",)] or 0) == sales, metric
        assert coarse_values[("Unknown",)] == fine[("Unknown",)]
        assert (
            coarse_values[("Marketing",)]
            == values(ask(estate, cat, metric, ["source.group"]))[("Marketing",)]
        )


def with_second_segment_version(text: str) -> str:
    v2 = "        - version: v2\n          adopted_on: 2025-09-01\n          rules: {rules}\n"
    first = "            - {when: \"tier = 'Tier 3'\", member: SMB}\n    - entity: lead"
    out = text.replace(
        first,
        "            - {when: \"tier = 'Tier 3'\", member: SMB}\n"
        + v2.format(
            rules="&tier_rules_v2\n            - {when: \"tier in ('Tier 1', 'Tier 2')\", member: Enterprise}\n            - {when: \"tier = 'Tier 3'\", member: SMB}"
        )
        + "    - entity: lead",
    )
    return out.replace(
        "          rules: *tier_rules\n",
        "          rules: *tier_rules\n" + v2.format(rules="*tier_rules_v2"),
    )


def test_changing_a_mapping_version_changes_slices_and_never_totals(estate):
    cat = load_catalog(with_second_segment_version(catalog_text()))
    assert (
        cat.mapping_version("segment", "opportunity", None)[0] == "v2"
    )  # the most recently adopted
    one = ask(estate, cat, "bookings", ["segment"], mapping_versions={"segment": "v1"})
    two = ask(estate, cat, "bookings", ["segment"], mapping_versions={"segment": "v2"})
    assert values(one) != values(two)
    assert (
        values(one)[("Mid-Market",)] == 2_700_000 and values(two)[("Mid-Market",)] == 0
    )
    assert sum(values(one).values()) == sum(values(two).values()) == 5_900_000
    assert one[0].contract.mapping_versions == {"segment": "v1"} and two[
        0
    ].contract.mapping_versions == {"segment": "v2"}
    assert values(ask(estate, cat, "bookings", ["segment"])) == values(
        two
    )  # the default
    with pytest.raises(KeyError):
        ask(estate, cat, "bookings", ["segment"], mapping_versions={"segment": "v9"})


REGION = """  region:
    attribute_time: at_creation
    members: [North America, EMEA, Unknown]
    unmapped: Unknown
"""


def region_mapping() -> str:
    text = catalog_text()
    start = text.index("  region:\n    - entity: opportunity")
    return text[start : text.index("  source:\n    - entity: opportunity", start)]


def add_region(text: str) -> str:
    text = text.replace(
        "  month: {kind: time, grain: month}\n",
        "  month: {kind: time, grain: month}\n" + REGION,
        1,
    )
    text = text.replace(
        "dimensions: [segment, source, month], favorable: up, owner: Revenue Operations, definition: New-business amount",
        "dimensions: [segment, source, month, region], favorable: up, owner: Revenue Operations, definition: New-business amount",
        1,
    )
    return text.replace("mappings:\n", "mappings:\n" + region_mapping(), 1)


def won_deal_estate(root: Path, accounts: list[tuple]):
    opps, history, accts = [], [], []
    for i, (country, code) in enumerate(accounts, 1):
        aid, oid = f"001R{i}", f"006R{i}"
        accts.append(account(aid, "Tier 1", "2025-01-01T09:00:00Z", country, code))
        opps.append(
            opp(
                oid,
                AccountId=aid,
                StageName="Closed Won",
                Amount=1000.0,
                CloseDate="2025-02-10",
                IsClosed=True,
                IsWon=True,
            )
        )
        history.append(
            ohist(
                f"008R{i}",
                oid,
                "Closed Won",
                1000.0,
                "2025-02-10",
                "2025-02-10T09:00:00Z",
            )
        )
    objects = {
        "Opportunity": opps,
        "OpportunityHistory": history,
        "OpportunityFieldHistory": [],
        "Lead": [],
        "LeadHistory": [],
        "Account": accts,
    }
    return [write_extract(root, "2025-06-30T23:00:00Z", "salesforce", objects)]


def test_a_dimension_is_added_to_a_catalog_in_yaml_only(estate, coarse):
    assert "region" not in coarse.dimensions
    cat = load_catalog(add_region(Path(ADAPTERS / "catalog_coarse.yaml").read_text()))
    cells = values(ask(estate, cat, "bookings", ["region"]))
    assert cells == {
        ("North America",): 5_900_000,
        ("EMEA",): 0,
        ("Unknown",): 0,
    }  # estate A's bookings are all US accounts
    assert sum(cells.values()) == ask(estate, coarse, "bookings")[0].value


def test_free_text_country_names_and_codes_are_normalized_by_the_mapping(tmp_path):
    spellings = [
        ("UNITED STATES", None),
        ("usa ", None),
        (None, "ca"),
        ("Germany ", None),
        ("Deutschland", "de"),
        ("Mars", None),
    ]
    estate = load(won_deal_estate(tmp_path, spellings))
    cat = load_catalog(add_region(Path(ADAPTERS / "catalog_coarse.yaml").read_text()))
    cells = {c.key: c for c in ask(estate, cat, "bookings", ["region"])}
    assert {k: c.value for k, c in cells.items()} == {
        ("North America",): 300_000,
        ("EMEA",): 200_000,
        ("Unknown",): 100_000,
    }
    assert cells[("Unknown",)].contract.counts["unmapped"] == 1

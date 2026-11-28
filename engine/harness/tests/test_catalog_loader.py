"""Catalog loading: a YAML file per organization, validated with errors that name the line and the key."""

import pytest

from engine.harness.catalog import ConfigError, load_catalog

MINI = """\
catalog: mini
version: "1"
entities:
  opportunity:
    view: opportunity
    requires: [salesforce.Opportunity]
    relationships:
      account: {to: account, cardinality: many_to_one, join: [account_id, account_id]}
      converted_lead:
        to: lead
        cardinality: one_to_many
        join: [opportunity_id, converted_opportunity_id]
        dedup: {order_by: [converted_date, lead_id]}
  account: {view: account, requires: [salesforce.Account]}
  lead: {view: lead}
dimensions:
  segment:
    attribute_time: at_creation
    members: [Enterprise, SMB, Unknown]
    unmapped: Unknown
  month: {kind: time, grain: month}
mappings:
  segment:
    - entity: opportunity
      inputs: {tier: account.tier}
      versions:
        - version: v1
          adopted_on: 2025-01-01
          rules:
            - {when: "tier = 'Tier 1'", member: Enterprise}
            - {when: "tier = 'Tier 3'", member: SMB}
        - version: v2
          adopted_on: 2025-06-01
          rules:
            - {when: "tier in ('Tier 1', 'Tier 2')", member: Enterprise}
            - {when: "tier = 'Tier 3'", member: SMB}
measures:
  bookings_cents: {entity: opportunity, agg: sum, column: amount_cents, time: close_date, where: "type = 'New Business' and stage = 'Closed Won'"}
  won_deals: {entity: opportunity, agg: count, time: close_date, where: "stage = 'Closed Won'"}
  decided: {entity: opportunity, agg: count, time: created_date, where: "stage in ('Closed Won', 'Closed Lost')"}
metrics:
  - id: bookings
    version: "1"
    label: Bookings
    unit: cents
    population: New-business deals closed won
    basis: period
    kind: sum
    measure: bookings_cents
    aggregation: additive
    dimensions: [segment, month]
    favorable: up
    owner: Revenue Operations
    definition: Closed-won new-business amount by close date.
  - id: bookings
    version: "2"
    label: Bookings
    unit: cents
    population: New-business deals closed won
    basis: period
    kind: sum
    measure: bookings_cents
    aggregation: additive
    dimensions: [segment, month]
    favorable: up
    owner: Revenue Operations
    definition: Closed-won new-business amount by close date, restated.
  - id: win_rate
    version: "1"
    label: Win rate
    unit: ratio
    population: Decided deals
    basis: cohort
    kind: ratio
    numerator: won_deals
    denominator: decided
    aggregation: non_additive
    dimensions: [segment]
    favorable: up
    owner: Revenue Operations
    definition: Won over decided.
"""


def line_of(text: str, marker: str) -> int:
    return next(i for i, row in enumerate(text.splitlines(), 1) if marker in row)


def broken(old: str, new: str) -> str:
    assert old in MINI, old
    return MINI.replace(old, new, 1)


def test_a_valid_catalog_loads_and_versions_coexist():
    cat = load_catalog(MINI)
    assert cat.name == "mini"
    assert cat.metric("bookings").version == "2"  # the last declared is the default
    assert cat.metric("bookings", "1").definition.endswith("by close date.")
    assert cat.metric_versions("bookings") == ["1", "2"]
    version, _ = cat.mapping_version("segment", "opportunity", None)
    assert version == "v2"  # the most recently adopted
    assert cat.mapping_version("segment", "opportunity", "v1")[0] == "v1"
    assert [h for h in cat.entities["opportunity"].relationships] == [
        "account",
        "converted_lead",
    ]


@pytest.mark.parametrize(
    "old, new, marker, key",
    [
        ("view: account, requires", "view: nope, requires", "view: nope", "view"),
        ("agg: sum, column: amount_cents", "agg: sum, column: nope", "column: nope", "column"),
        ("      account: {to: account, cardinality: many_to_one", "      account: {to: ghost, cardinality: many_to_one", "to: ghost", "to"),
        ("        dedup: {order_by: [converted_date, lead_id]}\n", "", "converted_lead:", "dedup"),
        ("member: SMB}\n        - version: v2", "member: Ghost}\n        - version: v2", "member: Ghost", "member"),
        ("{when: \"tier = 'Tier 1'\", member: Enterprise}", "{when: \"tier = 'Tier 1' or 1=1\", member: Enterprise}", "or 1=1", "when"),
        ("{when: \"tier = 'Tier 1'\", member: Enterprise}", "{when: \"nope = 'x'\", member: Enterprise}", "nope = 'x'", "when"),
        ("where: \"type = 'New Business' and stage = 'Closed Won'\"", "where: \"type = 'x'; DROP TABLE assertion\"", "DROP TABLE", "where"),
        ("measure: bookings_cents\n    aggregation: additive\n    dimensions: [segment, month]\n    favorable: up\n    owner: Revenue Operations\n    definition: Closed-won new-business amount by close date.\n", "measure: ghost\n    aggregation: additive\n    dimensions: [segment, month]\n    favorable: up\n    owner: Revenue Operations\n    definition: Closed-won new-business amount by close date.\n", "measure: ghost", "measure"),
        ("numerator: won_deals\n    denominator: decided\n    aggregation: non_additive", "numerator: won_deals\n    denominator: decided\n    aggregation: additive  # bad", "# bad", "aggregation"),
        ("dimensions: [segment]\n    favorable: up\n    owner: Revenue Operations\n    definition: Won over", "dimensions: [segment, region]\n    favorable: up\n    owner: Revenue Operations\n    definition: Won over", "region]", "dimensions"),
        ("attribute_time: at_creation", "attribute_time: whenever", "whenever", "attribute_time"),
        ("unmapped: Unknown", "unmapped: Ghost", "unmapped: Ghost", "unmapped"),
        ("favorable: up\n    owner: Revenue Operations\n    definition: Won", "favorable: sideways\n    owner: Revenue Operations\n    definition: Won", "sideways", "favorable"),
    ],
)  # fmt: skip
def test_errors_name_the_line_and_the_key(old, new, marker, key):
    text = broken(old, new)
    with pytest.raises(ConfigError) as err:
        load_catalog(text, file="mini.yaml")
    assert err.value.line == line_of(text, marker), str(err.value)
    assert err.value.key == key
    assert str(err.value).startswith(f"mini.yaml:{err.value.line}: key '{key}'")


def test_a_mapping_version_missing_for_one_entity_is_rejected():
    text = (
        MINI.replace(
            "  month: {kind: time, grain: month}", "  month: {kind: time, grain: month}"
        )
        + ""
    )
    text = text.replace(
        "mappings:\n  segment:\n",
        "mappings:\n  segment:\n    - entity: lead\n      inputs: {t: tier}\n      versions:\n        - version: v1\n          rules: [{when: \"t = 'Tier 1'\", member: SMB}]\n",
    )
    with pytest.raises(ConfigError) as err:
        load_catalog(text, file="mini.yaml")
    assert err.value.key == "versions"


def test_unknown_top_level_key_and_bad_yaml_and_duplicates():
    with pytest.raises(ConfigError) as err:
        load_catalog(MINI + "surprise: 1\n")
    assert err.value.key == "surprise" and err.value.line == line_of(
        MINI + "surprise: 1\n", "surprise"
    )
    with pytest.raises(ConfigError) as err:
        load_catalog("catalog: [unclosed\n", file="x.yaml")
    assert err.value.line >= 1
    with pytest.raises(ConfigError) as err:
        load_catalog("catalog: a\ncatalog: b\n")
    assert "duplicate" in str(err.value)


def test_injection_in_a_name_is_rejected_at_load():
    text = broken("bookings_cents: {entity", "bookings_cents; DROP: {entity")
    with pytest.raises(ConfigError):
        load_catalog(text)

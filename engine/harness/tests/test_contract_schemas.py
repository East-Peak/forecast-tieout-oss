import pytest

from engine.harness.contract.schema import (
    Field,
    ObjectSchema,
    validate_lines,
    validate_record,
)
from engine.harness.contract.schemas import SCHEMAS, SYSTEMS

DESIGN_OBJECTS = {
    "Opportunity", "OpportunityHistory", "OpportunityFieldHistory", "Lead",
    "LeadHistory", "Account", "Campaign", "CampaignMember", "User",
    "contacts", "deals", "people", "requisitions", "spend", "plan_lines",
}  # fmt: skip

CUSTOM_FIELDS = {
    "Opportunity": {"Sourcing_User__c"},
    "Lead": {"MQL_Date__c", "Disposition__c", "Disposition_Reason__c", "Tier__c"},
    "Account": {"Tier__c"},
}

TOY = ObjectSchema(
    name="Toy",
    system="salesforce",
    key=("Id",),
    doc="test object",
    fields=(
        Field("Id", "id", doc="key"),
        Field("N", "int", doc="n"),
        Field("D", "date", nullable=True, doc="d"),
        Field("T", "datetime", nullable=True, doc="t"),
        Field("Money", "dollars", nullable=True, doc="m"),
        Field("Flag", "bool", doc="f"),
        Field("Kind", "string", nullable=True, choices=("a", "b"), doc="k"),
    ),
)
GOOD = {"Id": "x1", "N": 3, "D": "2025-03-14", "T": "2025-03-14T09:30:00Z",
        "Money": 20000.5, "Flag": True, "Kind": "a"}  # fmt: skip


def test_every_design_object_has_a_schema():
    assert set(SCHEMAS) == DESIGN_OBJECTS


def test_systems_partition_the_objects():
    listed = [o for objs in SYSTEMS.values() for o in objs]
    assert sorted(listed) == sorted(DESIGN_OBJECTS)
    assert all(SCHEMAS[o].system == s for s, objs in SYSTEMS.items() for o in objs)


def test_schemas_are_well_formed():
    for schema in SCHEMAS.values():
        names = [f.name for f in schema.fields]
        assert len(names) == len(set(names)), schema.name
        assert set(schema.key) <= set(names), schema.name
        assert all(not schema.field(k).nullable for k in schema.key)
        assert all(f.doc for f in schema.fields), schema.name
        for f in schema.fields:
            if f.ref:
                assert f.ref in SCHEMAS, (schema.name, f.name)


def test_custom_fields_are_exactly_the_documented_ones():
    found = {
        s.name: {f.name for f in s.fields if f.name.endswith("__c")}
        for s in SCHEMAS.values()
    }
    assert {k: v for k, v in found.items() if v} == CUSTOM_FIELDS


def test_standard_salesforce_names_are_used():
    opp = {f.name for f in SCHEMAS["Opportunity"].fields}
    assert {"StageName", "CloseDate", "CreatedDate", "IsWon", "IsClosed", "OwnerId",
            "CreatedById", "AccountId", "LeadSource", "SystemModstamp", "Amount"} <= opp  # fmt: skip
    assert "ConvertedOpportunityId" in {f.name for f in SCHEMAS["Lead"].fields}
    hist = {f.name for f in SCHEMAS["OpportunityFieldHistory"].fields}
    assert {"OpportunityId", "Field", "OldValue", "NewValue", "CreatedDate"} <= hist


def test_valid_record_passes():
    assert validate_record(TOY, GOOD) == []
    assert (
        validate_record(
            TOY, {**GOOD, "D": None, "T": None, "Money": None, "Kind": None}
        )
        == []
    )


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"N": "3"}, "N: expected int"),
        ({"N": True}, "N: expected int"),
        ({"D": "2025-3-14"}, "D: expected date"),
        ({"D": "2025-02-30"}, "D: expected date"),
        ({"T": "2025-03-14T09:30:00"}, "T: expected datetime"),
        ({"T": "2025-03-14T09:30:00+02:00"}, "T: expected datetime"),
        ({"Money": 1.005}, "Money: expected dollars"),
        ({"Flag": 1}, "Flag: expected bool"),
        ({"Kind": "z"}, "Kind: not one of"),
        ({"Id": None}, "Id: null not allowed"),
        ({"Id": ""}, "Id: expected id"),
        ({"Extra": 1}, "unknown field Extra"),
    ],
)
def test_invalid_values_are_named(change, fragment):
    errors = validate_record(TOY, {**GOOD, **change})
    assert any(fragment in e for e in errors), errors


def test_missing_field_is_an_error_even_if_nullable():
    record = {k: v for k, v in GOOD.items() if k != "D"}
    assert validate_record(TOY, record) == ["missing field D"]


def test_lines_report_line_numbers_and_duplicate_keys():
    lines = ['{"Id": "a"', "", '{"Id": "b", "N": 1}', "[1]"]
    errors = validate_lines(TOY, lines)
    assert errors[0].startswith("line 1: not valid JSON")
    assert any(e.startswith("line 3: missing field") for e in errors)
    assert "line 4: record is not an object" in errors


def test_duplicate_key_is_reported_with_both_lines():
    row = '{"Id": "a", "N": 1, "D": null, "T": null, "Money": null, "Flag": false, "Kind": null}'
    errors = validate_lines(TOY, [row, row])
    assert errors == ["line 2: duplicate key ('a',) first seen on line 1"]

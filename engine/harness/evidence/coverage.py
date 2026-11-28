"""Field coverage: how each field's knowledge time is learned (design section 1).

history    a history object carries the field; recorded_at is the history row's CreatedDate.
immutable  never changes after creation; known as soon as the record is known.
Every other field of an object is snapshot-only: recorded_at is the extracted_at
of the first extract that shows the value.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..contract.schemas import SCHEMAS

RECORD_CREATION = "record creation"


@dataclass(frozen=True)
class Coverage:
    history: tuple[tuple[str, str, str], ...]  # (entity, field, history object)
    immutable: dict[str, tuple[str, ...]]

    @classmethod
    def from_dict(cls, estate: dict) -> "Coverage":
        declared = estate.get("field_coverage", {})
        history = []
        for dotted, spec in declared.get("history", {}).items():
            entity, field = dotted.split(".")
            _check_field(entity, field)
            if spec["via"] not in SCHEMAS:
                raise ValueError(f"{dotted}: unknown history object {spec['via']}")
            if spec.get("since") != RECORD_CREATION:
                raise ValueError(
                    f"{dotted}: only history since {RECORD_CREATION!r} is supported"
                )
            history.append((entity, field, spec["via"]))
        immutable = {}
        for entity, fields in declared.get("immutable", {}).items():
            for field in fields:
                _check_field(entity, field)
            immutable[entity] = tuple(fields)
        return cls(tuple(history), immutable)

    @classmethod
    def from_yaml(cls, path: Path | str) -> "Coverage":
        return cls.from_dict(yaml.safe_load(Path(path).read_text()))

    @classmethod
    def standard(cls) -> "Coverage":
        """The tracked fields of the standard Salesforce shapes in `contract/`."""
        via = {"Opportunity": "OpportunityHistory", "Lead": "LeadHistory"}
        history = [
            ("Opportunity", f, via["Opportunity"])
            for f in ("StageName", "Amount", "CloseDate")
        ]
        history.append(("Opportunity", "OwnerId", "OpportunityFieldHistory"))
        history += [
            ("Lead", f, via["Lead"])
            for f in (
                "Sales_Offered_Date__c",
                "MQL_Date__c",
                "Disposition__c",
                "Disposition_Reason__c",
            )
        ]
        immutable = {
            "Opportunity": (
                "AccountId",
                "CreatedById",
                "CampaignId",
                "LeadSource",
                "Type",
                "CreatedDate",
            ),
            "Lead": ("CreatedById", "LeadSource", "CreatedDate"),
        }
        return cls(tuple(history), immutable)

    def history_fields(self, entity: str) -> dict[str, str]:
        return {f: via for e, f, via in self.history if e == entity}

    def history_objects(self) -> set[str]:
        return {via for _, _, via in self.history}


def _check_field(entity: str, field: str) -> None:
    if entity not in SCHEMAS:
        raise ValueError(f"unknown object {entity}")
    try:
        SCHEMAS[entity].field(field)
    except KeyError:
        raise ValueError(f"{entity}.{field}: unknown field") from None


def is_field_style(object_name: str) -> bool:
    """History objects of one row per change (Field, OldValue, NewValue) versus full images."""
    names = {f.name for f in SCHEMAS[object_name].fields}
    return {"Field", "OldValue", "NewValue"} <= names

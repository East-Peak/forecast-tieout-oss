"""Field and object schema types, and the validator for raw JSON Lines records.

Every record carries every field of its schema. A missing key is an error even
for a nullable field; an absent value is written as an explicit null.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

# Value types. `dollars` is a JSON number with at most two decimals (the raw
# Salesforce currency shape); `cents` is an integer. Dates are YYYY-MM-DD;
# datetimes are UTC with a trailing Z.
TYPES = (
    "id",
    "string",
    "int",
    "number",
    "dollars",
    "cents",
    "bool",
    "date",
    "datetime",
)

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATETIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


@dataclass(frozen=True)
class Field:
    name: str
    type: str
    doc: str
    nullable: bool = False
    choices: tuple[str, ...] | None = None  # allowed values, when closed
    ref: str | None = None  # name of the object whose key this field holds

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"{self.name}: unknown type {self.type}")


@dataclass(frozen=True)
class ObjectSchema:
    name: str
    system: str  # the source system that serves this object
    key: tuple[str, ...]  # fields that identify a record within one snapshot
    fields: tuple[Field, ...]
    doc: str

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)


def parse_date(text: str) -> date:
    if not _DATE.fullmatch(text):
        raise ValueError(text)
    return date.fromisoformat(text)


def parse_datetime(text: str) -> datetime:
    if not _DATETIME.fullmatch(text):
        raise ValueError(text)
    return datetime.fromisoformat(text)  # 3.11+ reads the trailing Z


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v) -> bool:
    return _is_int(v) or isinstance(v, float)


def _type_error(f: Field, v) -> str | None:
    t = f.type
    if t == "id":
        return None if isinstance(v, str) and v else "expected id (non-empty string)"
    if t == "string":
        return None if isinstance(v, str) else "expected string"
    if t in ("int", "cents"):
        return None if _is_int(v) else f"expected {t}"
    if t == "number":
        return None if _is_number(v) else "expected number"
    if t == "dollars":
        if _is_number(v) and round(v * 100) / 100 == v:
            return None
        return "expected dollars (number with at most two decimals)"
    if t == "bool":
        return None if isinstance(v, bool) else "expected bool"
    if t in ("date", "datetime"):
        parse = parse_date if t == "date" else parse_datetime
        try:
            parse(v)
        except (TypeError, ValueError):
            return f"expected {t} ({'YYYY-MM-DD' if t == 'date' else 'YYYY-MM-DDTHH:MM:SSZ'})"
        return None
    raise AssertionError(t)


def validate_record(schema: ObjectSchema, record: dict) -> list[str]:
    """Problems with one record; an empty list means it conforms."""
    errors = [
        f"unknown field {k}"
        for k in record
        if not any(f.name == k for f in schema.fields)
    ]
    for f in schema.fields:
        if f.name not in record:
            errors.append(f"missing field {f.name}")
            continue
        v = record[f.name]
        if v is None:
            if not f.nullable:
                errors.append(f"{f.name}: null not allowed")
            continue
        problem = _type_error(f, v)
        if problem:
            errors.append(f"{f.name}: {problem}")
        elif f.choices and v not in f.choices:
            errors.append(f"{f.name}: not one of {list(f.choices)}")
    return errors


def validate_lines(schema: ObjectSchema, lines: list[str]) -> list[str]:
    """Problems in the lines of one object file, each prefixed with its line number.

    Blank lines are skipped. Keys must be unique within the file.
    """
    errors: list[str] = []
    seen: dict[tuple, int] = {}
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {number}: not valid JSON ({e.msg})")
            continue
        if not isinstance(record, dict):
            errors.append(f"line {number}: record is not an object")
            continue
        errors.extend(f"line {number}: {e}" for e in validate_record(schema, record))
        if all(k in record for k in schema.key):
            key = tuple(record[k] for k in schema.key)
            if key in seen:
                errors.append(
                    f"line {number}: duplicate key {key} first seen on line {seen[key]}"
                )
            else:
                seen[key] = number
    return errors

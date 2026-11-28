"""Safe SQL pieces. Identifiers and literals come only from the contract's declared names."""

from ..contract.keys import DELETED_FIELD
from ..contract.schemas import SCHEMAS, SYSTEMS

DECLARED = (
    set(SCHEMAS)
    | set(SYSTEMS)
    | {f.name for s in SCHEMAS.values() for f in s.fields}
    | {DELETED_FIELD}
)

ISO = "%Y-%m-%dT%H:%M:%SZ"
RAW_TYPES = {
    "id": "VARCHAR",
    "string": "VARCHAR",
    "int": "BIGINT",
    "cents": "BIGINT",
    "number": "DOUBLE",
    "dollars": "DOUBLE",  # read as a double, written back as its shortest text: 24000.0, 0.29
    "bool": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
}


def ident(name: str) -> str:
    if name not in DECLARED:
        raise ValueError(f"not a declared name: {name!r}")
    return f'"{name}"'


def lit(name: str) -> str:
    if name not in DECLARED:
        raise ValueError(f"not a declared name: {name!r}")
    return f"'{name}'"


def raw_table(obj: str) -> str:
    if obj not in SCHEMAS:
        raise ValueError(f"not a declared object: {obj!r}")
    return f'"raw_{obj}"'


def text(obj: str, field: str, alias: str | None = None) -> str:
    """SQL for a raw column as canonical text: ISO dates and datetimes, lowercase booleans."""
    kind = SCHEMAS[obj].field(field).type
    col = f"{alias}.{ident(field)}" if alias else ident(field)
    if kind == "datetime":
        return f"strftime({col}, '{ISO}')"
    if kind == "bool":
        return f"lower(CAST({col} AS VARCHAR))"
    return f"CAST({col} AS VARCHAR)"


def key_expr(obj: str, alias: str | None = None) -> str:
    parts = [text(obj, k, alias) for k in SCHEMAS[obj].key]
    return parts[0] if len(parts) == 1 else f"concat_ws('|', {', '.join(parts)})"


def created_field(obj: str) -> str | None:
    names = {f.name for f in SCHEMAS[obj].fields}
    return next((n for n in ("CreatedDate", "createdate") if n in names), None)

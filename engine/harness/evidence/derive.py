"""Derives the record table and the append-only assertions from the raw tables, in SQL.

Everything here is a pure function of the registered extracts and the coverage,
so loading is idempotent and independent of order: `rebuild` recomputes it all.
"""

from ..contract.keys import DELETED_FIELD
from ..contract.schemas import SCHEMAS
from .coverage import Coverage, is_field_style
from .sql import created_field, ident, key_expr, lit, raw_table, text

HISTORY_OBJECTS = ("OpportunityHistory", "OpportunityFieldHistory", "LeadHistory")
NOT_EVIDENCE = (
    "plan_lines",
)  # stated plans are the planning package's input, not evidence


class ExtractError(ValueError):
    """An extract that cannot be loaded."""


def entity_objects() -> list[str]:
    return [o for o in SCHEMAS if o not in HISTORY_OBJECTS and o not in NOT_EVIDENCE]


def _parent_column(history_object: str, entity: str) -> str:
    (column,) = [f.name for f in SCHEMAS[history_object].fields if f.ref == entity]
    return column


def _source(obj: str, key_sql: str, suffix: str = "") -> str:
    return f"{lit(SCHEMAS[obj].system)} || '/{obj}/' || {key_sql}" + (
        f" || '{suffix}'" if suffix else ""
    )


def rebuild(con, coverage: Coverage) -> None:
    con.execute("DELETE FROM assertion")
    con.execute("DELETE FROM record")
    _build_records(con, coverage)
    gap = con.execute(
        "SELECT entity, id FROM record WHERE last_ord - first_ord + 1 <> n_shown LIMIT 1"
    ).fetchone()
    if gap:
        raise ExtractError(
            f"{gap[0]} {gap[1]} reappears after it was absent from an extract"
        )
    for obj in entity_objects():
        _snapshot_assertions(con, obj, coverage)
        _immutable_assertions(con, obj, coverage)
        _deletions(con, obj)
    for entity, via in sorted({(e, v) for e, _, v in coverage.history}):
        fields = [f for e, f, v in coverage.history if (e, v) == (entity, via)]
        if is_field_style(via):
            _field_history(con, entity, via, fields)
        else:
            _image_history(con, entity, via, fields)


def _build_records(con, coverage: Coverage) -> None:
    firsts = [
        f"SELECT {lit(e)} AS entity, {ident(_parent_column(v, e))} AS id, min({ident('CreatedDate')}) AS ts FROM {raw_table(v)} GROUP BY 2"
        for e, v in sorted({(e, v) for e, _, v in coverage.history})
    ]
    history = (
        " UNION ALL ".join(firsts)
        or "SELECT NULL::VARCHAR, NULL::VARCHAR, NULL::TIMESTAMP WHERE FALSE"
    )
    parts = []
    for obj in entity_objects():
        created = created_field(obj)
        parts.append(
            f"""SELECT {lit(obj)} AS entity, {key_expr(obj, "r")} AS id, {lit(SCHEMAS[obj].system)} AS system,
                   {f"min(r.{ident(created)})" if created else "NULL::TIMESTAMP"} AS created_at,
                   arg_min(r.extract_id, l.extracted_at) AS first_extract_id,
                   min(l.extracted_at) AS first_extract_at,
                   min(l.ord) AS first_ord, max(l.ord) AS last_ord, count(*) AS n_shown
            FROM {raw_table(obj)} r JOIN listing l ON l.extract_id = r.extract_id AND l.object = {lit(obj)}
            GROUP BY 1, 2, 3"""
        )
    con.execute(
        f"""INSERT INTO record
        WITH h AS ({history}), base AS ({" UNION ALL ".join(parts)})
        SELECT b.entity, b.id, b.system, b.created_at, b.first_extract_id, b.first_extract_at,
               least(COALESCE(h.ts, b.first_extract_at), b.first_extract_at) AS known_since,
               b.first_ord, b.last_ord, b.n_shown
        FROM base b LEFT JOIN (SELECT entity, id, min(ts) AS ts FROM h GROUP BY 1, 2) h USING (entity, id)"""
    )


def _snapshot_assertions(con, obj: str, coverage: Coverage) -> None:
    skip = (
        set(SCHEMAS[obj].key)
        | set(coverage.history_fields(obj))
        | set(coverage.immutable.get(obj, ()))
    )
    fields = [f.name for f in SCHEMAS[obj].fields if f.name not in skip]
    if not fields:
        return
    columns = ", ".join(f"{text(obj, f, 'r')} AS {ident(f)}" for f in fields)
    names = ", ".join(ident(f) for f in fields)
    con.execute(
        f"""INSERT INTO assertion
        WITH s AS (
            SELECT {key_expr(obj, "r")} AS _id, r.extract_id AS _x, l.extracted_at AS _at, {columns}
            FROM {raw_table(obj)} r JOIN listing l ON l.extract_id = r.extract_id AND l.object = {lit(obj)}
        ), u AS (
            SELECT * FROM s UNPIVOT INCLUDE NULLS (_value FOR _field IN ({names}))
        ), d AS (
            SELECT _id, _field, _value, _x, _at,
                   row_number() OVER w AS _rn, lag(_value) OVER w AS _prev
            FROM u WINDOW w AS (PARTITION BY _id, _field ORDER BY _at, _x)
        )
        SELECT {lit(obj)}, d._id, d._field, d._value,
               CASE WHEN d._rn = 1 THEN COALESCE(rec.created_at, d._at) ELSE d._at END,
               d._at, {_source(obj, "d._id", "#snapshot")}, d._x,
               d._rn = 1 AND rec.created_at IS NOT NULL, FALSE
        FROM d JOIN record rec ON rec.entity = {lit(obj)} AND rec.id = d._id
        WHERE d._rn = 1 OR d._value IS DISTINCT FROM d._prev"""
    )


def _immutable_assertions(con, obj: str, coverage: Coverage) -> None:
    fields = coverage.immutable.get(obj, ())
    if not fields:
        return
    columns = ", ".join(f"{text(obj, f, 'r')} AS {ident(f)}" for f in fields)
    names = ", ".join(ident(f) for f in fields)
    con.execute(
        f"""INSERT INTO assertion
        WITH s AS (
            SELECT rec.id AS _id, rec.created_at AS _created, rec.known_since AS _known,
                   rec.first_extract_id AS _x, {columns}
            FROM record rec JOIN {raw_table(obj)} r
              ON r.extract_id = rec.first_extract_id AND {key_expr(obj, "r")} = rec.id
            WHERE rec.entity = {lit(obj)}
        ), u AS (
            SELECT * FROM s UNPIVOT INCLUDE NULLS (_value FOR _field IN ({names}))
        )
        SELECT {lit(obj)}, _id, _field, _value, COALESCE(_created, _known), _known,
               {_source(obj, "_id", "#snapshot")}, _x, FALSE, FALSE
        FROM u"""
    )


def _deletions(con, obj: str) -> None:
    con.execute(
        f"""INSERT INTO assertion
        SELECT {lit(obj)}, rec.id, {lit(DELETED_FIELD)}, 'true', nx.extracted_at, nx.extracted_at,
               {_source(obj, "rec.id", "#snapshot")}, nx.extract_id, FALSE, TRUE
        FROM record rec JOIN listing nx
          ON nx.system = rec.system AND nx.object = {lit(obj)} AND nx.ord = rec.last_ord + 1
        WHERE rec.entity = {lit(obj)}"""
    )


def _history_rows(entity: str, via: str, columns: str) -> str:
    """History rows once each, as first shown by the earliest extract that carries them."""
    parent = ident(_parent_column(via, entity))
    return f"""SELECT r.{parent} AS _id, r."Id" AS _rid, r."CreatedDate" AS _ts, r.extract_id AS _x{columns}
        FROM {raw_table(via)} r JOIN extract e ON e.extract_id = r.extract_id
        QUALIFY row_number() OVER (PARTITION BY r."Id" ORDER BY e.extracted_at, r.extract_id) = 1"""


def _image_history(con, entity: str, via: str, fields: list[str]) -> None:
    columns = "".join(f", {text(via, f, 'r')} AS {ident(f)}" for f in fields)
    names = ", ".join(ident(f) for f in fields)
    con.execute(
        f"""INSERT INTO assertion
        WITH h AS ({_history_rows(entity, via, columns)}),
        u AS (SELECT * FROM h UNPIVOT INCLUDE NULLS (_value FOR _field IN ({names}))),
        d AS (SELECT *, row_number() OVER w AS _rn, lag(_value) OVER w AS _prev
              FROM u WINDOW w AS (PARTITION BY _id, _field ORDER BY _ts, _rid))
        SELECT {lit(entity)}, _id, _field, _value, _ts, _ts, {_source(via, "_rid")}, _x, FALSE, FALSE
        FROM d WHERE _rn = 1 OR _value IS DISTINCT FROM _prev"""
    )


def _field_history(con, entity: str, via: str, fields: list[str]) -> None:
    rows = _history_rows(
        entity, via, ', r."Field" AS _fld, r."OldValue" AS _old, r."NewValue" AS _new'
    )
    listed = ", ".join(lit(f) for f in fields)
    con.execute(
        f"""INSERT INTO assertion
        WITH h AS ({rows})
        SELECT {lit(entity)}, _id, _fld, _new, _ts, _ts, {_source(via, "_rid")}, _x, FALSE, FALSE
        FROM h WHERE _fld IN ({listed})"""
    )
    for field in fields:
        # The value before the first change: the first row's old value when that row precedes the
        # first extract showing the record, otherwise what that extract shows (never a later row).
        con.execute(
            f"""INSERT INTO assertion
            WITH h AS ({rows}),
            fr AS (SELECT _id, arg_min_null(_old, (_ts, _rid)) AS _old, min(_ts) AS _ts,
                          arg_min(_rid, (_ts, _rid)) AS _rid, arg_min(_x, (_ts, _rid)) AS _x
                   FROM h WHERE _fld = {lit(field)} GROUP BY _id),
            b AS (SELECT rec.id, rec.created_at, rec.first_extract_at, rec.first_extract_id,
                         {text(entity, field, "r")} AS _snap, fr._old, fr._ts AS _fts, fr._rid, fr._x
                  FROM record rec
                  JOIN {raw_table(entity)} r
                    ON r.extract_id = rec.first_extract_id AND {key_expr(entity, "r")} = rec.id
                  LEFT JOIN fr ON fr._id = rec.id
                  WHERE rec.entity = {lit(entity)}),
            c AS (SELECT *, COALESCE(_fts <= first_extract_at, FALSE) AS _from_row FROM b)
            SELECT {lit(entity)}, id, {lit(field)}, CASE WHEN _from_row THEN _old ELSE _snap END,
                   COALESCE(created_at, first_extract_at),
                   least(first_extract_at, COALESCE(_fts, first_extract_at)),
                   CASE WHEN _from_row THEN {_source(via, "_rid")} ELSE {_source(entity, "id", "#snapshot")} END,
                   CASE WHEN _from_row THEN _x ELSE first_extract_id END, TRUE, FALSE
            FROM c WHERE CASE WHEN _from_row THEN _old ELSE _snap END IS NOT NULL"""
        )

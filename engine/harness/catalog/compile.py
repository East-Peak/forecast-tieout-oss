"""Compile a catalog's fact queries to SQL over the evidence engine's as-of macros.

A `Plan` is one entity viewed as of (T, K): its derived columns, the joins its dimensions and
conversions need, and the dimension members each row lands in. Every value is a bound parameter;
every identifier comes from the declared registry or the loaded catalog.
"""

from dataclasses import dataclass
from datetime import date, datetime

from .columns import VIEWS
from .expr import Params, compile_expr
from .loader import resolve_path
from .model import Catalog, Dimension

JOINED = {  # derived columns that need a join on the main entity: name to (join SQL, select expression)
    "is_open": (
        "LEFT JOIN asof_opportunity_open($t, $k) _op ON _op.opportunity_id = m.opportunity_id",
        "COALESCE(_op.is_open, FALSE)",
    ),
    "amount_at_t_cents": (
        (
            "LEFT JOIN (SELECT opportunity_id, arg_max(amount_cents, valid_from) AS amount"
            " FROM asof_opportunity_state($t, $k) GROUP BY 1) _st ON _st.opportunity_id = m.opportunity_id"
        ),
        "_st.amount",
    ),
}
TIME_FORMAT = {"month": "%Y-%m", "year": "%Y"}


@dataclass(frozen=True)
class Axis:
    """A dimension at one level: a grouping or a filter."""

    dim: Dimension
    level: str

    @property
    def name(self) -> str:
        return (
            self.dim.name
            if self.level == self.dim.levels[-1]
            else f"{self.dim.name}.{self.level}"
        )


def parse_axis(catalog: Catalog, text: str) -> Axis:
    name, _, level = text.partition(".")
    dim = catalog.dimensions.get(name)
    if dim is None:
        raise ValueError(f"unknown dimension {name!r}")
    level = level or dim.levels[-1]
    if level not in dim.levels:
        raise ValueError(
            f"dimension {name!r} has levels {list(dim.levels)}, not {level!r}"
        )
    return Axis(dim, level)


def time_member(day: date, grain: str) -> str:
    if grain == "quarter":
        return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
    return day.strftime(TIME_FORMAT[grain])


class Plan:
    def __init__(
        self,
        catalog: Catalog,
        entity: str,
        t: date,
        k: datetime,
        groups: list[Axis],
        filters: list[tuple[Axis, tuple[str, ...]]],
        versions: dict[str, str],
        time: str | None,
        window: tuple[date, date] | None,
    ):
        self.catalog, self.entity, self.view = (
            catalog,
            entity,
            VIEWS[catalog.entities[entity].view],
        )
        self.params = Params()
        self.params.values.update(t=t, k=k)
        self.groups, self.filters, self.time, self.window = (
            groups,
            filters,
            time,
            window,
        )
        self.versions = versions
        self.hops: dict[tuple, str] = {}  # (at, path) to alias
        self.hop_sql: list[str] = []
        self.hop_cols: dict[str, str] = {}  # projected name to alias.column
        self.joined: set[str] = set()
        self.used_entities = {entity}
        self.axis_sql: list[str] = []
        self.diagnostics: list[
            tuple[str, str]
        ] = []  # (unmapped flag column, fallback flag column)
        self.mapping_used: dict[str, str] = {}
        self._axes = [(f"d{i}", a) for i, a in enumerate(groups)] + [
            (f"x{i}", a) for i, (a, _) in enumerate(filters)
        ]
        for name, axis in self._axes:
            self._axis(name, axis)

    # -- columns ---------------------------------------------------------------------------
    def main(self, name: str) -> str:
        if name in JOINED:
            self.joined.add(name)
        return name

    def pred(self, text: str | None) -> str:
        if text is None:
            return "TRUE"
        return compile_expr(text, self.view.typed(True), self.main, self.params)

    def hop(self, path: tuple[str, ...], at: str) -> str:
        """The alias of the last relationship of `path`. A versioned relationship is read at the row's own
        date (`at`); every other is read as of T."""
        alias, here, tag = "m", self.entity, ""
        for i, name in enumerate(path):
            rel = self.catalog.entities[here].relationships[name]
            when = at if rel.versioned else "current"
            tag += "" if when == "current" else "_at"
            key = (alias, name, when)
            if key not in self.hops:
                self.hops[key] = self._join(
                    rel, alias, when, "h_" + "_".join(path[: i + 1]) + tag
                )
            alias, here = self.hops[key], rel.to
            self.used_entities.add(rel.to)
        return alias

    def _join(self, rel, parent: str, at: str, alias: str) -> str:
        view = VIEWS[self.catalog.entities[rel.to].view]
        derived = "".join(f", {sql} AS {n}" for n, (_, sql) in view.simple.items())
        order = ", ".join((*rel.dedup, view.key))
        when = {
            "current": "$t",
            "at_creation": "m._created_on",
            "at_close": "m._closed_on",
        }[at]
        rows = (
            f"SELECT * FROM (SELECT v.*{derived}, row_number() OVER (PARTITION BY v.{rel.remote} ORDER BY {order}) AS _rn"
            f" FROM asof_{view.name}({when}, $k) v{{where}}) WHERE _rn = 1"
        )
        if at == "current":
            self.hop_sql.append(
                f"LEFT JOIN ({rows.format(where='')}) {alias} ON {alias}.{rel.remote} = {parent}.{rel.local}"
            )
        else:
            where = f" WHERE v.{rel.remote} = {parent}.{rel.local}"
            self.hop_sql.append(
                f"LEFT JOIN LATERAL ({rows.format(where=where)}) {alias} ON TRUE"
            )
        return alias

    def column(self, path: tuple[str, ...], at: str = "current") -> tuple[str, str]:
        """SQL for a path from the main entity, and a flag SQL for 'fell back to current' ('FALSE' if none)."""
        if len(path) == 1:
            return self.main(path[0]), "FALSE"
        col, here, versioned = path[-1], self.entity, False
        for name in path[:-1]:
            rel = self.catalog.entities[here].relationships[name]
            versioned, here = versioned or rel.versioned, rel.to
        cur = self._project(self.hop(path[:-1], "current"), col)
        if at == "current" or not versioned:
            return cur, "FALSE"
        at_col = self._project(self.hop(path[:-1], at), col)
        return f"COALESCE({at_col}, {cur})", f"({at_col} IS NULL AND {cur} IS NOT NULL)"

    def _project(self, alias: str, col: str) -> str:
        name = f"{alias}__{col}"
        self.hop_cols[name] = f"{alias}.{col}"
        return name

    # -- dimension members -----------------------------------------------------------------
    def _axis(self, name: str, axis: Axis) -> None:
        dim = axis.dim
        if dim.kind == "time":
            if self.time is None:
                raise ValueError(
                    f"dimension {dim.name!r} needs a measure with a time column"
                )
            expr = (
                f"strftime(date_trunc('{dim.grain}', CAST({self.time} AS DATE)), '{TIME_FORMAT[dim.grain]}')"
                if dim.grain != "quarter"
                else (
                    f"strftime(CAST({self.time} AS DATE), '%Y') || '-Q' || CAST(quarter(CAST({self.time} AS DATE)) AS VARCHAR)"
                )
            )
            self.axis_sql.append(f"{expr} AS {name}")
            return
        ver, mv = self.catalog.mapping_version(
            dim.name, self.entity, self.versions.get(dim.name)
        )
        self.mapping_used[dim.name] = ver
        mapping = self.catalog.mapping(dim.name, self.entity)
        cols, fbs = {}, []
        for alias, path in mapping.inputs.items():
            cols[alias], fb = self.column(path, dim.attribute_time)
            fbs.append(fb)
        if mapping.passthrough:
            leaf = f"CAST({cols[mapping.passthrough]} AS VARCHAR)"
        else:
            types = {
                a: resolve_path(self.catalog.entities, self.entity, p)[2]
                for a, p in mapping.inputs.items()
            }
            arms = " ".join(
                f"WHEN {compile_expr(r.when, types, cols.__getitem__, self.params, mapping.normalize)} THEN {self.params.add(r.member)}"
                for r in mv.rules
            )
            leaf = f"CASE {arms} END" if arms else "CAST(NULL AS VARCHAR)"
        unmapped = self.params.add(dim.unmapped) if dim.unmapped else "NULL"
        full = f"COALESCE({leaf}, {unmapped})"
        if axis.level != dim.levels[-1]:
            arms = " ".join(
                f"WHEN {self.params.add(k)} THEN {self.params.add(v[axis.level])}"
                for k, v in dim.members.items()
            )
            full = f"CASE {full} {arms} END"
        self.axis_sql.append(
            f"{full} AS {name}, ({leaf}) IS NULL AS u_{name}, ({' OR '.join(fbs)}) AS fb_{name}"
        )
        self.diagnostics.append((f"u_{name}", f"fb_{name}"))

    # -- statement ---------------------------------------------------------------------------
    def with_sql(self) -> str:
        v = self.view
        simple = "".join(f", {sql} AS {n}" for n, (_, sql) in v.simple.items())
        created = f", {v.created} AS _created_on" if v.created else ""
        close = f", {v.close} AS _closed_on" if v.close else ""
        joins = " ".join(JOINED[n][0] for n in sorted(self.joined))
        extra = "".join(f", {JOINED[n][1]} AS {n}" for n in sorted(self.joined))
        hop_cols = "".join(f", {src} AS {name}" for name, src in self.hop_cols.items())
        axes = ", ".join(self.axis_sql)
        return (
            f"WITH b AS (SELECT m.*{extra}{hop_cols} FROM (SELECT v.*{simple}{created}{close} FROM asof_{v.name}($t, $k) v) m"
            f" {joins} {' '.join(self.hop_sql)}), f AS (SELECT b.*{', ' + axes if axes else ''} FROM b)"
        )

    def where(self) -> str:
        parts = []
        if self.window is not None and self.time:
            parts.append(
                f"{self.time} BETWEEN {self.params.add(self.window[0])} AND {self.params.add(self.window[1])}"
            )
        for i, (_, members) in enumerate(self.filters):
            parts.append(f"x{i} IN ({', '.join(self.params.add(m) for m in members)})")
        return " AND ".join(parts) or "TRUE"

    def group_cols(self) -> list[str]:
        return [f"d{i}" for i in range(len(self.groups))]

"""The governed metric query layer: query() answers a catalog metric from the evidence's as-of views,
records() resolves a cell back to the source rows it counted.

Everything is read as of (T, K) through the evidence engine's `asof_*` macros, so nothing recorded
after K can reach a value. A cell says three separate things (applicability, availability,
derivation) and carries a Contract naming exactly what it measured.
"""

import re
import statistics
from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from itertools import product

from .catalog.columns import VIEWS
from .catalog.compile import Axis, Plan, parse_axis
from .catalog.expr import compile_expr
from .catalog.model import Catalog, Measure, Metric
from .contract.keys import RECONSTRUCTED
from .evidence import AsOf

KINDS_PROVIDED = ("plan", "forecast", "required")


class NonAdditiveError(ValueError):
    """A non-additive metric was asked to be summed."""


@dataclass(frozen=True)
class Lineage:
    kind: str  # measured: a handle to source rows; modeled: a run and its lanes
    handle: dict = field(default_factory=dict)
    run_id: str | None = None
    lanes: tuple = ()


@dataclass(frozen=True)
class Contract:
    metric: str
    metric_version: str
    aggregation: str
    mapping_versions: dict
    window: tuple[date, date] | None
    t: date
    k: datetime
    mode: str
    cohort_maturity: dict | None
    eligible: int | None
    excluded: dict
    counts: dict  # diagnostics: rows landed in an unmapped member, rows that fell back to current
    bound: (
        str | None
    )  # exact | lower_bound, for additive sums and counts only; None for everything else
    completeness: str  # complete | incomplete: whether every row of unknown membership or value was resolved
    incomplete: dict  # counts of rows of unknown membership or value
    lineage: Lineage | None
    flags: tuple = ()
    provenance: str | None = None


@dataclass(frozen=True)
class Cell:
    key: tuple
    value: float | int | None
    numerator: float | int | None
    denominator: float | int | None
    applicability: str  # applicable | not_applicable
    availability: str  # measured | unavailable | insufficient | not_planned
    availability_reason: str | None
    derivation: str  # measured | pooled | allocated | modeled
    contract: Contract


@dataclass(frozen=True)
class SourceRow:
    id: str
    value: int | float | None
    source_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class Fact:
    """One input of an estimator, with the evidence's own uncertainty about it."""

    total: int | float | None
    n: int
    completeness: str = "complete"
    bound: str | None = "exact"
    excluded: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Estimate:
    """An estimator's answer. It must say how complete it is and where it came from."""

    value: float | None
    numerator: float | None = None
    denominator: float | None = None
    derivation: str = "pooled"
    reason: str | None = None
    eligible: int | None = None
    completeness: str = field(kw_only=True)
    provenance: str = field(kw_only=True)

    def __post_init__(self):
        if self.completeness not in ("complete", "incomplete"):
            raise ValueError("completeness is 'complete' or 'incomplete'")


@dataclass(frozen=True)
class ProviderRequest:
    catalog: Catalog
    metric: Metric
    group_by: tuple
    keys: list[tuple]
    filters: dict
    window: tuple[date, date] | None
    t: date
    k: datetime
    kind: str
    plan_version: str | None
    run_id: str | None
    metric_version: str | None = None
    mapping_versions: dict = field(default_factory=dict)


PROVIDERS: dict[str, Callable[[ProviderRequest], list[Cell]]] = {}
ESTIMATORS: dict[str, Callable[[dict, dict], dict]] = {}


def register_provider(kind: str, fn: Callable[[ProviderRequest], list[Cell]]) -> None:
    if kind not in KINDS_PROVIDED:
        raise ValueError(f"kind must be one of {KINDS_PROVIDED}")
    PROVIDERS[kind] = fn


def register_estimator(name: str, fn: Callable[[dict, dict], dict]) -> None:
    """fn(inputs, params) -> {key: Estimate}; inputs is {key: {role: Fact}} over every cell key."""
    ESTIMATORS[name] = fn


class _Unavailable(Exception):
    def __init__(self, reason: str):
        self.reason = reason


@dataclass
class _Row:
    n: int = 0
    total: float | None = None
    unknown: int = 0
    null: int = 0
    excluded: dict = field(default_factory=dict)
    unmapped: int = 0
    fallback: int = 0
    converted: int = 0
    quant: float | None = None


@dataclass
class _Part:
    value: float | None = None
    num: float | None = None
    den: float | None = None
    eligible: int = 0
    excluded: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    bound: str | None = "exact"
    complete: dict = field(default_factory=dict)  # rows of unknown membership or value
    provenance: str | None = None
    availability: str = "measured"
    reason: str | None = None
    derivation: str = "measured"
    flags: tuple = ()


@dataclass
class _Ctx:
    store: object
    catalog: Catalog
    asof: AsOf
    groups: list[Axis]
    filters: list[tuple[Axis, tuple[str, ...]]]
    versions: dict
    window: tuple[date, date] | None
    flags: tuple = ()
    deps: dict = field(default_factory=dict)  # pinned metric dependencies (rollup `of`)


@dataclass(frozen=True)
class _Spec:
    """One population of rows: an entity, its time, a predicate, and how it is counted."""

    entity: str
    time: str | None
    where: str | None
    column: str | None = None
    agg: str = "count"
    exclusions: tuple = ()
    maturity: int | None = None
    quantile: float | None = None
    conversion: dict | None = None


def _spec(metric: Metric, catalog: Catalog, measure: Measure) -> _Spec:
    s = metric.spec
    return _Spec(
        measure.entity,
        measure.time,
        measure.where,
        measure.column,
        measure.agg,
        s.get("exclusions", ()),
        s.get("maturity_days"),
    )


def _specs(metric: Metric, catalog: Catalog) -> dict[str, _Spec]:
    """The named row populations a metric reads: its sides."""
    s, m = metric.spec, catalog.measures
    if metric.kind == "sum":
        return {"value": _spec(metric, catalog, m[s["measure"]])}
    if metric.kind == "ratio":
        return {
            "numerator": _spec(metric, catalog, m[s["numerator"]]),
            "denominator": _spec(metric, catalog, m[s["denominator"]]),
        }
    if metric.kind == "quantile":
        base = _spec(metric, catalog, m[s["measure"]])
        return {"value": _Spec(**{**base.__dict__, "quantile": float(s["q"])})}
    if metric.kind == "conversion":
        a = s["anchor"]
        return {
            "value": _Spec(
                a["entity"],
                a["time"],
                a.get("where"),
                None,
                "count",
                (),
                s.get("maturity_days") or s["window_days"],
                float(s.get("q", 0.5)),
                s,
            )
        }
    if metric.kind == "estimator":
        return {
            role: _spec(metric, catalog, m[name]) for role, name in s["inputs"].items()
        }
    return {}


# ---- statements ------------------------------------------------------------------------------------------


def _plan(ctx: _Ctx, spec: _Spec) -> Plan:
    return Plan(
        ctx.catalog,
        spec.entity,
        ctx.asof.t,
        ctx.asof.k,
        ctx.groups,
        ctx.filters,
        ctx.versions,
        spec.time,
        ctx.window,
    )


def _gate(ctx: _Ctx, plan: Plan) -> None:
    """Every object the plan reads must be extracted by K, unless the evidence already has rows (history)."""
    for name in sorted(plan.used_entities):
        entity = ctx.catalog.entities[name]
        reasons = []
        for req in entity.requires:
            system, _, obj = req.partition(".")
            got = ctx.asof.availability(system, obj)
            if not got.available:
                reasons.append(got.unavailable)
        probe = f"SELECT 1 FROM asof_{entity.view}($t, $k) LIMIT 1"
        if (
            reasons
            and not ctx.store.con.execute(
                probe, {"t": ctx.asof.t, "k": ctx.asof.k}
            ).fetchall()
        ):
            raise _Unavailable(reasons[0])


@dataclass
class _Sql:
    """The row predicates of a spec, as SQL over the plan's rows."""

    base: str
    mature: str
    eligible: str
    converted: str
    exclusions: list[tuple[str, str]]
    series: str | None  # the quantile series


def _predicates(plan: Plan, spec: _Spec) -> _Sql:
    base = f"({plan.pred(spec.where)})"
    if spec.column:
        plan.main(spec.column)
    mature = "TRUE"
    if spec.maturity and spec.time:
        mature = f"(last_day({spec.time}) + {plan.params.add(spec.maturity)} <= $t)"
    ex = [
        (e["reason"], f"COALESCE({plan.pred(e['when'])}, FALSE)")
        for e in spec.exclusions
    ]
    eligible = f"({base} AND {mature} AND NOT {'(' + ' OR '.join(sql for _, sql in ex) + ')' if ex else 'FALSE'})"
    converted, series = "FALSE", spec.column
    if c := spec.conversion:
        link = c["link"]
        linked = plan.catalog.entities[
            plan.catalog.entities[spec.entity].relationships[link].to
        ]
        exists = f"{plan.column((link, VIEWS[linked.view].key))[0]} IS NOT NULL"  # the link resolves to a row
        event = plan.main(
            c["event"]
        )  # when the lead converted, not when the opportunity was created
        tcond = "TRUE"
        if c["target"].get("where"):
            tcond = compile_expr(
                c["target"]["where"],
                VIEWS[linked.view].typed(False),
                lambda n: plan.column((link, n))[0],
                plan.params,
            )
        series = f"date_diff('day', {spec.time}, {event})"
        window = plan.params.add(c["window_days"])
        converted = f"({eligible} AND {exists} AND {event} IS NOT NULL AND {event} <= $t AND {series} BETWEEN 0 AND {window} AND {tcond})"
    return _Sql(base, mature, eligible, converted, ex, series)


def _execute(ctx: _Ctx, plan: Plan, sql: str) -> list[tuple]:
    used = set(re.findall(r"\$(\w+)", sql))
    return ctx.store.con.execute(
        sql, {k: v for k, v in plan.params.values.items() if k in used}
    ).fetchall()


def _run(ctx: _Ctx, spec: _Spec) -> dict[tuple, _Row]:
    plan = _plan(ctx, spec)
    p = _predicates(plan, spec)
    _gate(ctx, plan)
    diag = lambda i: " OR ".join(d[i] for d in plan.diagnostics) or "FALSE"
    count = lambda cond: f"count(*) FILTER (WHERE {cond})"
    aggs = {
        "n": count(p.eligible),
        "total": f"sum({spec.column}) FILTER (WHERE {p.eligible})"
        if spec.agg == "sum"
        else count(p.eligible),
        "unknown": count(f"{p.base} IS NULL"),
        "null": count(f"{p.eligible} AND {spec.column} IS NULL")
        if spec.column
        else "0",
        "imm": count(f"{p.base} AND NOT {p.mature}"),
        "unm": count(f"{p.eligible} AND ({diag(0)})"),
        "fb": count(f"{p.eligible} AND ({diag(1)})"),
        "conv": count(p.converted),
        "quant": "NULL",
    }
    if spec.quantile is not None:
        pick = p.converted if spec.conversion else p.eligible
        aggs["quant"] = (
            f"quantile_cont({p.series}, {plan.params.add(spec.quantile)}) FILTER (WHERE {pick})"
        )
    for i, (_, sql) in enumerate(p.exclusions):
        aggs[f"ex{i}"] = count(f"{p.base} AND {p.mature} AND {sql}")
    keys = plan.group_cols()
    select = ", ".join([*keys, *[f"{v} AS {k}" for k, v in aggs.items()]])
    sql = f"{plan.with_sql()} SELECT {select} FROM f WHERE {plan.where()}" + (
        f" GROUP BY {', '.join(keys)}" if keys else ""
    )
    out = {}
    for row in _execute(ctx, plan, sql):
        v = dict(zip(aggs, row[len(keys) :], strict=True))
        excluded = {
            r: v[f"ex{i}"] for i, (r, _) in enumerate(p.exclusions) if v[f"ex{i}"]
        }
        if v["imm"]:
            excluded["immature"] = v["imm"]
        out[tuple(row[: len(keys)])] = _Row(
            v["n"],
            v["total"],
            v["unknown"],
            v["null"],
            excluded,
            v["unm"],
            v["fb"],
            v["conv"],
            v["quant"],
        )
    return out


def _rows(ctx: _Ctx, spec: _Spec, which: str, key: tuple) -> list[SourceRow]:
    """The source rows behind one side of one cell, with the evidence's source record ids."""
    plan = _plan(ctx, spec)
    p = _predicates(plan, spec)
    _gate(ctx, plan)
    cond = {"eligible": p.eligible, "converted": p.converted}.get(which)
    if cond is None:  # excluded:<reason> or immature
        reason = which.partition(":")[2] or which
        if reason == "immature":
            cond = f"({p.base} AND NOT {p.mature})"
        else:
            sql = dict(p.exclusions)[reason]
            cond = f"({p.base} AND {p.mature} AND {sql})"
    match = "".join(
        f" AND {c} = {plan.params.add(m)}"
        for c, m in zip(plan.group_cols(), key, strict=True)
    )
    value = spec.column if spec.agg == "sum" or spec.quantile is not None else "1"
    if spec.conversion:  # a rate row contributes 1; only the lag metric carries days
        value = (
            p.series
            if which == "converted" and spec.conversion["output"] == "lag"
            else "1"
        )
    ident = VIEWS[ctx.catalog.entities[spec.entity].view].key
    sql = f"{plan.with_sql()} SELECT {ident}, source_record_ids, {value} FROM f WHERE {plan.where()} AND {cond}{match} ORDER BY 1"
    return [SourceRow(r[0], r[2], tuple(r[1])) for r in _execute(ctx, plan, sql)]


# ---- metric kinds ----------------------------------------------------------------------------------------


def _incomplete(*rows: _Row) -> dict:
    """Rows of unknown membership (a predicate that is NULL) or unknown value, the largest across inputs."""
    out: dict = {}
    for r in rows:
        for name, n in (("unknown_membership", r.unknown), ("unknown_value", r.null)):
            if n:
                out[name] = max(out.get(name, 0), n)
    return out


def _bound(incomplete: dict) -> str:
    return "lower_bound" if incomplete else "exact"


def _counts(row: _Row) -> dict:
    return {
        k: v
        for k, v in (
            ("unmapped", row.unmapped),
            ("attribute_fallback_current", row.fallback),
        )
        if v
    }


def _part(
    num, den, row: _Row, inc: dict, reason_empty="no_denominator", minimum=None
) -> _Part:
    """A ratio-like part: never a mathematical bound, only complete or incomplete."""
    part = _Part(None, num, den, row.n, row.excluded, _counts(row), None, inc)
    if den and num is not None:
        part.value = num / den
    if not den:
        part.availability = "insufficient"
        part.reason = (
            "immature_cohort" if row.excluded.get("immature") else reason_empty
        )
    elif minimum and den < minimum:
        part.value, part.availability, part.reason = (
            None,
            "insufficient",
            "below_minimum_denominator",
        )
    return part


def _eval_sum(ctx, metric):
    spec = _specs(metric, ctx.catalog)["value"]
    return {
        k: _Part(
            r.total or 0,
            None,
            None,
            r.n,
            r.excluded,
            _counts(r),
            _bound(_incomplete(r)),
            _incomplete(r),
        )
        for k, r in _run(ctx, spec).items()
    }


def _eval_ratio(ctx, metric):
    specs = _specs(metric, ctx.catalog)
    num, den = _run(ctx, specs["numerator"]), _run(ctx, specs["denominator"])
    out = {}
    for key in num.keys() | den.keys():
        n, d = num.get(key, _Row()), den.get(key, _Row())
        out[key] = _part(
            n.total or 0,
            d.total or 0,
            d,
            _incomplete(n, d),
            minimum=metric.spec.get("min_denominator"),
        )
    return out


def _eval_quantile(ctx, metric):
    out = {}
    for key, r in _run(ctx, _specs(metric, ctx.catalog)["value"]).items():
        out[key] = _part(None, r.n, r, _incomplete(r), "no_rows")
        out[key].value = r.quant if r.n else None
    return out


def _eval_conversion(ctx, metric):
    out = {}
    for key, r in _run(ctx, _specs(metric, ctx.catalog)["value"]).items():
        if metric.spec["output"] == "lag":
            out[key] = _part(None, r.converted, r, _incomplete(r), "no_conversions")
            out[key].value = r.quant if r.converted else None
        else:
            out[key] = _part(r.converted, r.n, r, _incomplete(r), "no_mature_anchors")
    return out


def _eval_estimator(ctx, metric):
    fn = ESTIMATORS.get(metric.spec["estimator"])
    if fn is None:
        raise _Unavailable("estimator_not_registered")
    ran = {role: _run(ctx, spec) for role, spec in _specs(metric, ctx.catalog).items()}
    keys = set().union(*[r.keys() for r in ran.values()])
    keys |= set(
        product(
            *[_members(ctx, a, {k[i] for k in keys}) for i, a in enumerate(ctx.groups)]
        )
    )

    def fact(row: _Row | None) -> Fact:
        if row is None:
            return Fact(0, 0)
        inc = _incomplete(row)
        return Fact(
            row.total or 0,
            row.n,
            "incomplete" if inc else "complete",
            _bound(inc),
            row.excluded,
            _counts(row),
        )

    inputs = {k: {role: fact(rows.get(k)) for role, rows in ran.items()} for k in keys}
    out = {}
    for key, est in fn(inputs, dict(metric.spec.get("params", {}))).items():
        facts = inputs[key]
        inc: dict = {}
        for role, row in ((r, ran[r].get(key)) for r in ran):
            for name, n in _incomplete(row).items() if row else ():
                inc[f"{role}.{name}"] = n
        part = _Part(
            est.value,
            est.numerator,
            est.denominator,
            0,
            derivation=est.derivation,
            provenance=est.provenance,
        )
        part.eligible = (
            est.eligible
            if est.eligible is not None
            else max((f.n for f in facts.values()), default=0)
        )
        part.excluded = {
            f"{role}.{k}": n for role, f in facts.items() for k, n in f.excluded.items()
        }
        part.bound, part.complete = (
            None,
            inc if est.completeness == "incomplete" or inc else {},
        )
        if est.completeness == "incomplete" and not inc:
            part.complete = {"estimator_declared": 1}
        if est.value is None:
            part.availability, part.reason = "insufficient", est.reason or "no_estimate"
        out[key] = part
    return out


def _rollup_axis(ctx, metric) -> Axis:
    inner = _inner(ctx, metric)
    for dim in ctx.catalog.dimensions.values():
        if (
            dim.kind == "time"
            and dim.grain == metric.spec["period"]
            and dim.name in inner.dimensions
        ):
            return Axis(dim, dim.levels[-1])
    raise ValueError(
        f"no time dimension of grain {metric.spec['period']!r} on metric {inner.id!r}"
    )


def _inner(ctx, metric) -> Metric:
    return ctx.catalog.metric(
        metric.spec["of"], ctx.deps.get("of") or metric.spec.get("of_version")
    )


def _rollup_periods(ctx, axis: Axis):
    """Eligible periods: whole, inside the window, and closed by T and K. Everything else is counted, not divided."""
    cal, grain = ctx.catalog.calendar, axis.dim.grain
    limit = min(ctx.window[1], ctx.asof.k.date())
    eligible, excluded = [], {}
    for label in cal.periods(ctx.window, grain):
        start, end = cal.bounds(label, grain)
        if end > limit:
            excluded["open_period"] = excluded.get("open_period", 0) + 1
        elif start < ctx.window[0] or end > ctx.window[1]:
            excluded["partial_period"] = excluded.get("partial_period", 0) + 1
        else:
            eligible.append(label)
    span = (
        (cal.bounds(eligible[0], grain)[0], cal.bounds(eligible[-1], grain)[1])
        if eligible
        else None
    )
    return eligible, excluded, span


def _eval_rollup(ctx, metric):
    axis = _rollup_axis(ctx, metric)
    inner = _inner(ctx, metric)
    eligible, excluded, span = _rollup_periods(ctx, axis)
    parts: dict = {}
    if span is not None:
        inner_ctx = _Ctx(
            ctx.store,
            ctx.catalog,
            ctx.asof,
            [*ctx.groups, axis],
            ctx.filters,
            ctx.versions,
            span,
        )
        parts = _EVAL[inner.kind](inner_ctx, inner)
    per: dict[tuple, dict] = {}
    for key, part in parts.items():
        per.setdefault(key[:-1], {})[key[-1]] = part
    members = [_members(ctx, a, {k[i] for k in per}) for i, a in enumerate(ctx.groups)]
    out = {}
    for key in product(
        *members
    ):  # every member, every eligible period: a member with no bookings is 0, not NULL
        cells = per.get(key, {})
        series = [
            cells[p].value if p in cells else (0 if inner.kind == "sum" else None)
            for p in eligible
        ]
        series = [v for v in series if v is not None]
        part = _Part(excluded=dict(excluded), eligible=len(series), bound=None)
        part.complete = {k: n for c in cells.values() for k, n in c.complete.items()}
        if series:
            stat = metric.spec["stat"]
            part.value = {
                "mean": statistics.fmean,
                "median": statistics.median,
                "max": max,
                "min": min,
            }[stat](series)
            if stat == "mean":
                part.num, part.den = sum(series), len(series)
        else:
            part.availability, part.reason = "insufficient", "no_closed_period"
        out[key] = part
    return out


_EVAL = {
    "sum": _eval_sum,
    "ratio": _eval_ratio,
    "quantile": _eval_quantile,
    "conversion": _eval_conversion,
    "estimator": _eval_estimator,
    "rollup": _eval_rollup,
}


# ---- cells -----------------------------------------------------------------------------------------------


def _asof(store, t: date, known_at: datetime | None, mode: str | None) -> AsOf:
    if known_at is not None and mode is not None:
        raise ValueError("give known_at or mode, not both")
    if known_at is not None:
        return AsOf(store, t, known_at)
    return AsOf.at(store, t, mode or RECONSTRUCTED)


def _window(window, t: date):
    if window is None:
        return None, ()
    start, end = window
    if end > t:
        return (start, t), ("window_clipped_to_t",)
    return (start, end), ()


def _members(ctx: _Ctx, axis: Axis, observed: set[str]) -> list[str]:
    dim = axis.dim
    if dim.kind == "time":
        periods = (
            ctx.catalog.calendar.periods(ctx.window, dim.grain) if ctx.window else []
        )
        return sorted({*periods, *observed})
    declared = list(dict.fromkeys(m[axis.level] for m in dim.members.values()))
    return [*declared, *sorted(observed - set(declared))]


def _inapplicable(metric: Metric, axis: Axis, members: set[str]) -> bool:
    """True when every leaf member under `members` is one the metric declares not applicable."""
    for rule in metric.applicability:
        if axis.dim.name != rule["dimension"]:
            continue
        leaves = {k for k, v in axis.dim.members.items() if v[axis.level] in members}
        hit = {
            k
            for k, v in axis.dim.members.items()
            if set(v.values()) & set(rule["members"])
        }
        if leaves and leaves <= hit:
            return True
    return False


def _maturity(metric: Metric, t: date) -> dict | None:
    days = metric.spec.get("maturity_days")
    if not days:
        return None
    cut = t - timedelta(days=days)
    end = (
        cut
        if cut.day == monthrange(cut.year, cut.month)[1]
        else cut.replace(day=1) - timedelta(days=1)
    )
    return {"days": days, "mature_through": end}


def _dependencies(ctx: _Ctx, metric: Metric) -> dict:
    """What a metric was built from, pinned by name and version."""
    s = metric.spec
    if metric.kind == "rollup":
        inner = _inner(ctx, metric)
        return {"of": [inner.id, inner.version]}
    if metric.kind == "estimator":
        return dict(s["inputs"])
    return {r: s[r] for r in ("measure", "numerator", "denominator") if r in s}


def _handle(ctx: _Ctx, metric: Metric, key: tuple, versions: dict) -> dict:
    return {
        "metric": metric.id,
        "metric_version": metric.version,
        "group_by": [a.name for a in ctx.groups],
        "filters": {a.name: list(m) for a, m in ctx.filters},
        "window": None if ctx.window is None else [d.isoformat() for d in ctx.window],
        "t": ctx.asof.t.isoformat(),
        "k": ctx.asof.k.isoformat(),
        "mapping_versions": dict(versions),
        "dependencies": _dependencies(ctx, metric),
        "catalog_hash": ctx.catalog.content_hash,
        "key": list(key),
    }


def _contract(
    ctx: _Ctx, metric: Metric, key: tuple, part: _Part | None, versions: dict, extra=()
) -> Contract:
    part = part or _Part()
    counts = part.counts
    flags = [
        *ctx.flags,
        *(n for n, c in (("unmapped_values", counts.get("unmapped")), ("attribute_fallback_current", counts.get("attribute_fallback_current"))) if c),
        *part.flags,
        *extra,
    ]  # fmt: skip
    if part.bound == "lower_bound":
        flags.append("lower_bound")
    if part.complete:
        flags.append("incomplete")
    return Contract(
        metric.id, metric.version, metric.aggregation, versions, ctx.window, ctx.asof.t, ctx.asof.k, ctx.asof.mode,
        _maturity(metric, ctx.asof.t), part.eligible, part.excluded, counts, part.bound,
        "incomplete" if part.complete else "complete", part.complete,
        Lineage("measured", _handle(ctx, metric, key, versions)), tuple(dict.fromkeys(flags)), part.provenance,
    )  # fmt: skip


def _resolved_versions(ctx: _Ctx, metric: Metric) -> dict:
    entity = ctx.catalog.metric_entities(metric)[0]
    axes = [*ctx.groups, *(a for a, _ in ctx.filters)]
    return {
        a.dim.name: ctx.versions.get(a.dim.name)
        or ctx.catalog.mapping_version(a.dim.name, entity, None)[0]
        for a in axes
        if a.dim.kind != "time" and ctx.catalog.mapping(a.dim.name, entity)
    }


def _cells(
    ctx: _Ctx, metric: Metric, parts: dict | None, reason: str | None
) -> list[Cell]:
    """The full member cross product of the grouped dimensions; absent members stay distinct."""
    observed = [{k[i] for k in (parts or {})} for i in range(len(ctx.groups))]
    axes_members = [
        _members(ctx, a, o) for a, o in zip(ctx.groups, observed, strict=True)
    ]
    versions = _resolved_versions(ctx, metric)
    filtered_out = any(_inapplicable(metric, a, set(m)) for a, m in ctx.filters)
    out = []
    for key in product(*axes_members):
        part = (parts or {}).get(key)
        na = filtered_out or any(
            _inapplicable(metric, a, {m}) for a, m in zip(ctx.groups, key, strict=True)
        )
        if reason is not None and not na:
            cell = (None, None, None, "applicable", "unavailable", reason, "measured")
        elif na:
            # rows that land where the metric has no meaning are never dropped: they appear, flagged, so slices still sum
            rows = (
                part is not None and part.eligible and part.availability == "measured"
            )
            cell = (
                part.value if rows else None,
                part.num if rows else None,
                part.den if rows else None,
                "not_applicable",
                "measured",
                None,
                "measured",
            )
            part = part if rows else _Part()
        elif part is None:
            part = _empty(metric)
            cell = (
                part.value,
                part.num,
                part.den,
                "applicable",
                part.availability,
                part.reason,
                "measured",
            )
        else:
            cell = (
                part.value,
                part.num,
                part.den,
                "applicable",
                part.availability,
                part.reason,
                part.derivation,
            )
        extra = ("reconciliation",) if na and part.eligible else ()
        out.append(
            Cell(
                key,
                *cell[:3],
                cell[3],
                cell[4],
                cell[5],
                cell[6],
                _contract(ctx, metric, key, part, versions, extra),
            )
        )
    return out


def _empty(metric: Metric) -> _Part:
    if metric.kind == "sum":
        return _Part(0, bound="exact")
    reason = {"conversion": "no_mature_anchors", "ratio": "no_denominator"}.get(
        metric.kind, "no_rows"
    )
    counted = metric.kind == "ratio" or (
        metric.kind == "conversion" and metric.spec["output"] == "rate"
    )
    return _Part(
        num=0 if counted else None,
        den=0,
        bound=None,
        availability="insufficient",
        reason=reason,
    )


def _provide(
    catalog,
    metric,
    metric_version,
    groups,
    filters,
    window,
    asof,
    kind,
    plan_version,
    run_id,
    versions,
):
    """Providers get the requested horizon untouched, and the versions that resolved."""
    ctx = _Ctx(None, catalog, asof, groups, filters, {}, window)
    keys = list(product(*[_members(ctx, a, set()) for a in groups]))
    resolved = {
        a.dim.name: versions.get(a.dim.name) or catalog.mapping_version(a.dim.name, catalog.metric_entities(metric)[0], None)[0]
        for a, _ in [(g, 0) for g in groups] + list(filters)
        if a.dim.kind != "time" and catalog.mapping(a.dim.name, catalog.metric_entities(metric)[0])
    }  # fmt: skip
    request = ProviderRequest(
        catalog, metric, tuple(a.name for a in groups), keys, {a.name: m for a, m in filters}, window,
        asof.t, asof.k, kind, plan_version, run_id, metric.version, resolved,
    )  # fmt: skip
    if kind in PROVIDERS:
        return PROVIDERS[kind](request)
    status = (
        ("not_planned", "no_provider")
        if kind == "plan"
        else ("unavailable", "no_provider")
    )
    return [
        Cell(key, None, None, None, "applicable", *status, "measured", _contract(ctx, metric, key, _Part(bound=None), resolved))
        for key in keys
    ]  # fmt: skip


def query(
    store,
    catalog: Catalog,
    metric: str,
    group_by=(),
    filters: dict | None = None,
    window: tuple[date, date] | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    mode: str | None = None,
    kind: str = "actual",
    metric_version: str | None = None,
    mapping_versions: dict | None = None,
    plan_version: str | None = None,
    run_id: str | None = None,
) -> list[Cell]:
    """Answer one metric as of business date `as_of` and knowledge instant K (`known_at`, or a named `mode`).

    `window` is inclusive; for actuals it is clipped to `as_of`, and no event after `as_of` is ever counted.
    Returns one cell per member of the cross product of `group_by` ("segment", "source.group",
    "month", "fiscal_quarter"); `filters` maps a dimension (or level) to members.
    """
    m = catalog.metric(metric, metric_version)
    if as_of is None:
        raise ValueError("as_of is required")
    asof = _asof(store, as_of, known_at, mode)
    groups = [parse_axis(catalog, g) for g in group_by]
    for a in groups:
        if a.dim.name not in m.dimensions:
            raise ValueError(
                f"metric {m.id!r} does not support dimension {a.dim.name!r}; it supports {list(m.dimensions)}"
            )
    cuts = []
    for name, members in (filters or {}).items():
        axis = parse_axis(catalog, name)
        wanted = (members,) if isinstance(members, str) else tuple(members)
        dim = axis.dim
        if dim.kind == "categorical" and not dim.observed:
            known = {v[axis.level] for v in dim.members.values()}
            if set(wanted) - known:
                raise ValueError(
                    f"{name!r} has no member(s) {sorted(set(wanted) - known)}; members are {sorted(known)}"
                )
        cuts.append((axis, wanted))
    if (
        kind != "actual"
    ):  # a plan, forecast or requirement keeps the horizon it was asked for
        return _provide(
            catalog,
            m,
            metric_version,
            groups,
            cuts,
            window,
            asof,
            kind,
            plan_version,
            run_id,
            dict(mapping_versions or {}),
        )
    effective, flags = _window(window, as_of)
    if m.basis == "snapshot":
        effective, flags = None, ()
    elif effective is None and (
        any(a.dim.kind == "time" for a in groups) or m.kind == "rollup"
    ):
        raise ValueError("a window is required for a time dimension or a rollup")
    ctx = _Ctx(
        store,
        catalog,
        asof,
        groups,
        cuts,
        dict(mapping_versions or {}),
        effective,
        flags,
    )
    if effective is not None and effective[0] > as_of:
        return _cells(ctx, m, None, "window_after_as_of")
    try:
        return _cells(ctx, m, _EVAL[m.kind](ctx, m), None)
    except _Unavailable as err:
        return _cells(ctx, m, None, err.reason)


# ---- records and re-aggregation ------------------------------------------------------------------------------

PRIMARY_SIDE = {
    "sum": "value",
    "ratio": "numerator",
    "quantile": "value",
    "conversion": "numerator",
    "rollup": "value",
}


def _side(catalog: Catalog, metric: Metric, side: str):
    """(spec, which rows) for a side of a metric."""
    specs = _specs(metric, catalog)
    if side.startswith("excluded:") or side == "immature":
        return specs.get(side) or next(reversed(specs.values())), side
    if metric.kind == "conversion":
        spec = specs["value"]
        converted = side == "numerator" or (
            metric.spec["output"] == "lag" and side == "value"
        )
        return spec, "converted" if converted else "eligible"
    if side not in specs:
        raise ValueError(
            f"metric {metric.id!r} has sides {sorted(specs)}, not {side!r}"
        )
    return specs[side], "eligible"


def _check_pins(catalog: Catalog, h: dict) -> None:
    """A cell replays what it used. If the catalog changed, every pinned version must still be there."""
    if h.get("catalog_hash") == catalog.content_hash:
        return
    missing = []
    if h["metric_version"] not in catalog.metric_versions(h["metric"]):
        missing.append(f"metric {h['metric']} version {h['metric_version']}")
    for dim, version in h["mapping_versions"].items():
        if not any(
            v == version
            for (d, _), mp in catalog.mappings.items()
            if d == dim
            for v in mp.versions
        ):
            missing.append(f"mapping {dim} version {version}")
    for role, dep in h["dependencies"].items():
        if role == "of" and dep[1] not in catalog.metric_versions(dep[0]):
            missing.append(f"metric {dep[0]} version {dep[1]}")
        elif role != "of" and dep not in catalog.measures:
            missing.append(f"measure {dep}")
    if missing:
        raise ValueError(
            f"the catalog content changed and {', '.join(missing)} is no longer present"
        )


def records(
    store, catalog: Catalog, cell: Cell | Lineage, side: str | None = None
) -> list[SourceRow]:
    """The source rows a cell counted (side: numerator, denominator, value, or excluded:<reason>)."""
    lineage = cell.contract.lineage if isinstance(cell, Cell) else cell
    if lineage is None or lineage.kind != "measured":
        raise ValueError("only measured cells resolve to source rows")
    h = lineage.handle
    _check_pins(catalog, h)
    metric = catalog.metric(h["metric"], h["metric_version"])
    asof = AsOf(store, date.fromisoformat(h["t"]), datetime.fromisoformat(h["k"]))
    window = (
        None
        if h["window"] is None
        else tuple(date.fromisoformat(d) for d in h["window"])
    )
    groups = [parse_axis(catalog, g) for g in h["group_by"]]
    cuts = [(parse_axis(catalog, n), tuple(m)) for n, m in h["filters"].items()]
    deps = {"of": h["dependencies"]["of"][1]} if "of" in h["dependencies"] else {}
    ctx = _Ctx(
        store, catalog, asof, groups, cuts, h["mapping_versions"], window, deps=deps
    )
    key = tuple(h["key"])
    if metric.kind == "rollup":
        _, _, span = _rollup_periods(ctx, _rollup_axis(ctx, metric))
        if (
            span is None
        ):  # no closed period: an empty population, never unrestricted history
            return []
        inner = _inner(ctx, metric)
        ctx = _Ctx(store, catalog, asof, groups, cuts, h["mapping_versions"], span)
        metric = inner
    spec, which = _side(
        catalog,
        metric,
        side or PRIMARY_SIDE.get(metric.kind, next(iter(_specs(metric, catalog)))),
    )
    return _rows(ctx, spec, which, key)


def total(cells: list[Cell]) -> int | float:
    """Sum additive cells (or a snapshot across non-time members); refuses everything else."""
    kinds = {c.contract.aggregation for c in cells if c.contract}
    if kinds != {"additive"} and kinds != {"snapshot"}:
        raise NonAdditiveError(
            "a non-additive metric cannot be summed: use reaggregate() on numerator and denominator"
        )
    if any(c.applicability == "applicable" and c.value is None for c in cells):
        raise ValueError("cannot total cells that are unavailable or insufficient")
    return sum(c.value for c in cells if c.value is not None)


def reaggregate(cells: list[Cell]) -> float | None:
    """The ratio of a set of ratio-like cells: sum of numerators over sum of denominators."""
    usable = [
        c
        for c in cells
        if c.applicability == "applicable"
        and c.numerator is not None
        and c.denominator is not None
    ]
    if len(usable) != len([c for c in cells if c.applicability == "applicable"]):
        raise ValueError(
            "every cell needs a numerator and a denominator to be re-aggregated"
        )
    den = sum(c.denominator for c in usable)
    return sum(c.numerator for c in usable) / den if den else None

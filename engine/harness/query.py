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
from .catalog.compile import Axis, Plan, parse_axis, time_member
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
    bound: str  # exact | lower_bound
    lineage: Lineage | None
    flags: tuple = ()


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
    total: int | float | None
    n: int


@dataclass(frozen=True)
class Estimate:
    value: float | None
    numerator: float | None = None
    denominator: float | None = None
    derivation: str = "pooled"
    reason: str | None = None


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
    bound: str = "exact"
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
        target = plan.column((link, c["target"]["time"]))[0]
        linked = plan.catalog.entities[
            plan.catalog.entities[spec.entity].relationships[link].to
        ]
        tcond = "TRUE"
        if c["target"].get("where"):
            tcond = compile_expr(
                c["target"]["where"],
                VIEWS[linked.view].typed(False),
                lambda n: plan.column((link, n))[0],
                plan.params,
            )
        series = f"date_diff('day', {spec.time}, {target})"
        window = plan.params.add(c["window_days"])
        converted = f"({eligible} AND {target} IS NOT NULL AND {target} <= $t AND {series} BETWEEN 0 AND {window} AND {tcond})"
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
    if spec.conversion:
        value = "1" if which != "converted" else p.series
    ident = VIEWS[ctx.catalog.entities[spec.entity].view].key
    sql = f"{plan.with_sql()} SELECT {ident}, source_record_ids, {value} FROM f WHERE {plan.where()} AND {cond}{match} ORDER BY 1"
    return [SourceRow(r[0], r[2], tuple(r[1])) for r in _execute(ctx, plan, sql)]


# ---- metric kinds ----------------------------------------------------------------------------------------


def _bound(*rows: _Row) -> str:
    return "lower_bound" if any(r.unknown or r.null for r in rows) else "exact"


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
    num, den, row: _Row, bound: str, reason_empty="no_denominator", minimum=None
) -> _Part:
    part = _Part(None, num, den, row.n, row.excluded, _counts(row), bound)
    if den and num is not None:
        part.value = num / den
    if not den:
        part.availability, part.reason = (
            "insufficient",
            "immature_cohort" if row.excluded.get("immature") else reason_empty,
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
        k: _Part(r.total or 0, None, None, r.n, r.excluded, _counts(r), _bound(r))
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
            _bound(n, d),
            minimum=metric.spec.get("min_denominator"),
        )
    return out


def _eval_quantile(ctx, metric):
    rows = _run(ctx, _specs(metric, ctx.catalog)["value"])
    out = {}
    for key, r in rows.items():
        out[key] = _part(None, r.n, r, _bound(r), "no_rows")
        out[key].value = r.quant if r.n else None
    return out


def _eval_conversion(ctx, metric):
    rows, out = _run(ctx, _specs(metric, ctx.catalog)["value"]), {}
    for key, r in rows.items():
        if metric.spec["output"] == "lag":
            out[key] = _part(None, r.converted, r, _bound(r), "no_conversions")
            out[key].value = r.quant if r.converted else None
        else:
            out[key] = _part(r.converted, r.n, r, _bound(r), "no_mature_anchors")
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
    inputs = {
        k: {
            role: Fact(rows[k].total or 0, rows[k].n) if k in rows else Fact(0, 0)
            for role, rows in ran.items()
        }
        for k in keys
    }
    out = {}
    for key, est in fn(inputs, dict(metric.spec.get("params", {}))).items():
        part = _Part(
            est.value,
            est.numerator,
            est.denominator,
            sum(f.n for f in inputs[key].values()),
            derivation=est.derivation,
        )
        if est.value is None:
            part.availability, part.reason = "insufficient", est.reason or "no_estimate"
        out[key] = part
    return out


def _periods(window: tuple[date, date], grain: str) -> list[str]:
    out, day = [], window[0]
    while day <= window[1]:
        label = time_member(day, grain)
        if label not in out:
            out.append(label)
        day += timedelta(days=1)
    return out


def _period_end(label: str, grain: str) -> date:
    if grain == "year":
        return date(int(label), 12, 31)
    if grain == "quarter":
        year, quarter = label.split("-Q")
        return date(
            int(year), int(quarter) * 3, monthrange(int(year), int(quarter) * 3)[1]
        )
    year, month = map(int, label.split("-"))
    return date(year, month, monthrange(year, month)[1])


def _rollup_axis(ctx, metric) -> Axis:
    inner = ctx.catalog.metric(metric.spec["of"], metric.spec.get("of_version"))
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


def _closed_window(ctx, axis: Axis) -> tuple[date, date] | None:
    """The span of whole periods closed by T and K: a period closes when K reaches its last day."""
    limit = min(ctx.window[1], ctx.asof.k.date())
    ends = [
        _period_end(p, axis.dim.grain) for p in _periods(ctx.window, axis.dim.grain)
    ]
    closed = [e for e in ends if e <= limit]
    return (ctx.window[0], closed[-1]) if closed else None


def _eval_rollup(ctx, metric):
    axis = _rollup_axis(ctx, metric)
    inner = ctx.catalog.metric(metric.spec["of"], metric.spec.get("of_version"))
    span = _closed_window(ctx, axis)
    periods = _periods(ctx.window, axis.dim.grain)
    closed = [] if span is None else _periods(span, axis.dim.grain)
    if span is None:
        return {}
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
    by_key: dict[tuple, dict[str, float | None]] = {}
    for key, part in parts.items():
        by_key.setdefault(key[:-1], {})[key[-1]] = part.value
    out = {}
    for key, per in by_key.items():
        series = [per.get(p, 0 if inner.kind == "sum" else None) for p in closed]
        series = [v for v in series if v is not None]
        part = _Part(
            excluded={"open_period": len(periods) - len(closed)}
            if len(periods) > len(closed)
            else {},
            eligible=len(series),
        )
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
        part.bound = (
            "lower_bound"
            if any(p.bound == "lower_bound" for k, p in parts.items() if k[:-1] == key)
            else "exact"
        )
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
        return sorted(
            {*(_periods(ctx.window, dim.grain) if ctx.window else []), *observed}
        )
    declared = list(dict.fromkeys(m[axis.level] for m in dim.members.values()))
    return [*declared, *sorted(observed - set(declared))]


def _not_applicable(metric: Metric, axes: list[Axis], key: tuple) -> bool:
    for rule in metric.applicability:
        for axis, member in zip(axes, key, strict=True):
            if axis.dim.name != rule["dimension"]:
                continue
            leaves = {k for k, v in axis.dim.members.items() if v[axis.level] == member}
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


def _handle(ctx: _Ctx, metric: Metric, key: tuple) -> dict:
    return {
        "metric": metric.id,
        "metric_version": metric.version,
        "group_by": [a.name for a in ctx.groups],
        "filters": {a.name: list(m) for a, m in ctx.filters},
        "window": None if ctx.window is None else [d.isoformat() for d in ctx.window],
        "t": ctx.asof.t.isoformat(),
        "k": ctx.asof.k.isoformat(),
        "mapping_versions": dict(ctx.versions),
        "key": list(key),
    }


def _contract(
    ctx: _Ctx, metric: Metric, key: tuple, part: _Part | None, versions: dict
) -> Contract:
    part = part or _Part()
    flags = [
        *ctx.flags,
        *(
            f
            for f, n in (
                ("unmapped_values", part.counts.get("unmapped")),
                (
                    "attribute_fallback_current",
                    part.counts.get("attribute_fallback_current"),
                ),
            )
            if n
        ),
        *part.flags,
    ]
    if part.bound == "lower_bound":
        flags.append("lower_bound")
    return Contract(
        metric.id, metric.version, metric.aggregation, versions, ctx.window, ctx.asof.t, ctx.asof.k, ctx.asof.mode,
        _maturity(metric, ctx.asof.t), part.eligible, part.excluded, part.counts, part.bound,
        Lineage("measured", _handle(ctx, metric, key)), tuple(dict.fromkeys(flags)),
    )  # fmt: skip


def _cells(
    ctx: _Ctx, metric: Metric, parts: dict | None, reason: str | None
) -> list[Cell]:
    """The full member cross product of the grouped dimensions; absent members stay distinct."""
    observed = [{k[i] for k in (parts or {})} for i in range(len(ctx.groups))]
    axes_members = [
        _members(ctx, a, o) for a, o in zip(ctx.groups, observed, strict=True)
    ]
    versions = {
        a.dim.name: ctx.versions.get(a.dim.name)
        or ctx.catalog.mapping_version(
            a.dim.name, ctx.catalog.metric_entities(metric)[0], None
        )[0]
        for a in [*ctx.groups, *(a for a, _ in ctx.filters)]
        if a.dim.kind != "time"
    }
    out = []
    for key in product(*axes_members):
        part = (parts or {}).get(key)
        if _not_applicable(metric, ctx.groups, key):
            cell = (None, None, None, "not_applicable", "measured", None, "measured")
            part = part or _Part()
            if (
                part.eligible
            ):  # rows that landed where the metric has no meaning: never hidden
                part.flags = (*part.flags, "inapplicable_member_has_rows")
        elif reason is not None:
            cell = (None, None, None, "applicable", "unavailable", reason, "measured")
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
        out.append(
            Cell(
                key,
                *cell[:3],
                cell[3],
                cell[4],
                cell[5],
                cell[6],
                _contract(ctx, metric, key, part, versions),
            )
        )
    return out


def _empty(metric: Metric) -> _Part:
    if metric.kind == "sum":
        return _Part(0)
    reason = {"conversion": "no_mature_anchors", "ratio": "no_denominator"}.get(
        metric.kind, "no_rows"
    )
    counted = metric.kind == "ratio" or (
        metric.kind == "conversion" and metric.spec["output"] == "rate"
    )
    return _Part(
        num=0 if counted else None, den=0, availability="insufficient", reason=reason
    )


def _provide(
    catalog, metric, groups, filters, window, asof, kind, plan_version, run_id
):
    ctx = _Ctx(None, catalog, asof, groups, filters, {}, window)
    keys = list(product(*[_members(ctx, a, set()) for a in groups]))
    request = ProviderRequest(
        catalog,
        metric,
        tuple(a.name for a in groups),
        keys,
        {a.name: m for a, m in filters},
        window,
        asof.t,
        asof.k,
        kind,
        plan_version,
        run_id,
    )
    if kind in PROVIDERS:
        return PROVIDERS[kind](request)
    status = (
        ("not_planned", "no_provider")
        if kind == "plan"
        else ("unavailable", "no_provider")
    )
    return [
        Cell(key, None, None, None, "applicable", *status, "measured", _contract(ctx, metric, key, None, {})) for key in keys
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

    `window` is inclusive and clipped to `as_of`. Returns one cell per member of the cross product of
    `group_by` ("segment", "source.group", "month"); `filters` maps a dimension (or level) to members.
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
    effective, flags = _window(window, as_of)
    if m.basis == "snapshot":
        effective, flags = None, ()
    elif effective is None and (
        any(a.dim.kind == "time" for a in groups) or m.kind == "rollup"
    ):
        raise ValueError("a window is required for a time dimension or a rollup")
    if kind != "actual":
        return _provide(
            catalog, m, groups, cuts, effective, asof, kind, plan_version, run_id
        )
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


def records(
    store, catalog: Catalog, cell: Cell | Lineage, side: str | None = None
) -> list[SourceRow]:
    """The source rows a cell counted (side: numerator, denominator, value, or excluded:<reason>)."""
    lineage = cell.contract.lineage if isinstance(cell, Cell) else cell
    if lineage is None or lineage.kind != "measured":
        raise ValueError("only measured cells resolve to source rows")
    h = lineage.handle
    metric = catalog.metric(h["metric"], h["metric_version"])
    asof = AsOf(store, date.fromisoformat(h["t"]), datetime.fromisoformat(h["k"]))
    window = (
        None
        if h["window"] is None
        else tuple(date.fromisoformat(d) for d in h["window"])
    )
    groups = [parse_axis(catalog, g) for g in h["group_by"]]
    cuts = [(parse_axis(catalog, n), tuple(m)) for n, m in h["filters"].items()]
    ctx = _Ctx(store, catalog, asof, groups, cuts, h["mapping_versions"], window)
    key = tuple(h["key"])
    if metric.kind == "rollup":
        axis = _rollup_axis(ctx, metric)
        span = _closed_window(ctx, axis)
        inner = catalog.metric(metric.spec["of"], metric.spec.get("of_version"))
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

"""Load and validate a catalog file. Every problem is a ConfigError naming the file line and the key."""

import re
from datetime import date
from pathlib import Path

from .calendar import GRAINS, Calendar
from .columns import VIEWS
from .expr import ExprError, Params, compile_expr
from .model import (
    AGGREGATION,
    ATTRIBUTE_TIMES,
    KINDS,
    Catalog,
    Dimension,
    Entity,
    Mapping,
    MappingVersion,
    Measure,
    Metric,
    Relationship,
    Rule,
    VerifiedQuery,
)
from .yamlio import ConfigError, LDict, LList, load_yaml

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CARDINALITY = ("many_to_one", "one_to_one", "one_to_many", "many_to_many")
TOP = ("calendar", "catalog", "version", "entities", "dimensions", "mappings", "attribution_policy", "measures", "metrics",
       "plan_grain", "model_grain", "roles", "verified_queries")  # fmt: skip
COMMON = ("id", "version", "label", "unit", "population", "basis", "kind", "aggregation", "dimensions", "applicability",
          "favorable", "owner", "definition", "ai_context", "exclusions", "maturity_days", "min_denominator")  # fmt: skip
KIND_KEYS = {
    "sum": ("measure",),
    "ratio": ("numerator", "denominator"),
    "quantile": ("measure", "q"),
    "rollup": ("of", "of_version", "period", "stat"),
    "conversion": ("anchor", "link", "event", "target", "window_days", "output", "q"),
    "estimator": ("estimator", "inputs", "params"),
}
ROLE_KEYS = ("owner", "funnel_link", "type")


class _Loader:
    def __init__(self, file: str):
        self.file = file

    def fail(self, node, key, message):
        line = (
            node.at(key)
            if isinstance(node, LDict) and key in node
            else getattr(node, "line", 0)
        )
        raise ConfigError(self.file, line, key, message)

    def item(self, node, index, key, message):
        raise ConfigError(self.file, node.at(index), key, message)

    def node(self, parent, key, kind, required=True, default=None):
        if key not in parent:
            if required:
                self._missing(parent, key)
            return default
        value = parent[key]
        if not isinstance(value, kind) or isinstance(value, bool) and kind is not bool:
            names = getattr(kind, "__name__", None) or "/".join(
                k.__name__ for k in kind
            )
            self.fail(parent, key, f"expected {names}, found {type(value).__name__}")
        return value

    def _missing(self, parent, key):
        raise ConfigError(
            self.file, getattr(parent, "line", 0), key, f"missing required key '{key}'"
        )

    def only(self, node, allowed, where):
        for key in node:
            if key not in allowed:
                self.fail(
                    node, key, f"unknown key in {where}; allowed: {', '.join(allowed)}"
                )

    def one_of(self, node, key, choices, required=True, default=None):
        value = self.node(node, key, str, required, default)
        if value is not None and value not in choices:
            self.fail(node, key, f"must be one of {', '.join(choices)}, not {value!r}")
        return value

    def predicate(self, node, key, columns, resolve=lambda n: n, normalize=False):
        text = self.node(node, key, str)
        try:
            compile_expr(text, columns, resolve, Params(), normalize)
        except ExprError as err:
            self.fail(node, key, f"invalid predicate {text!r}: {err}")
        return text


def _entity_columns(
    entities: dict[str, Entity], name: str, main: bool
) -> dict[str, str]:
    return VIEWS[entities[name].view].typed(main)


def resolve_path(entities: dict[str, Entity], entity: str, path: tuple[str, ...]):
    """Follow relationship names then a column. Returns (hops, column, type) or raises ValueError."""
    hops, here = [], entity
    for name in path[:-1]:
        rel = entities[here].relationships.get(name)
        if rel is None:
            raise ValueError(f"entity '{here}' has no relationship '{name}'")
        hops.append(rel)
        here = rel.to
    types = _entity_columns(entities, here, main=not hops)
    if path[-1] not in types:
        raise ValueError(f"entity '{here}' has no column '{path[-1]}'")
    return hops, path[-1], types[path[-1]]


def load_catalog(source: str | Path, file: str | None = None) -> Catalog:
    if isinstance(source, Path):
        file, source = file or str(source), source.read_text()
    root = load_yaml(source, file or "<catalog>")
    v = _Loader(file or "<catalog>")
    v.only(root, TOP, "the catalog")
    name = v.node(root, "catalog", str)
    version = str(root.get("version", "1"))
    entities = _entities(v, v.node(root, "entities", LDict))
    dimensions = _dimensions(v, v.node(root, "dimensions", LDict))
    attribution = _attribution(v, root, dimensions, entities)
    mappings = _mappings(
        v, v.node(root, "mappings", LDict), dimensions, entities, attribution
    )
    measures = _measures(v, v.node(root, "measures", LDict), entities)
    metrics = _metrics(
        v, v.node(root, "metrics", LList), measures, dimensions, mappings, entities
    )
    grains = {}
    for key in ("plan_grain", "model_grain"):
        grains[key] = _grain(v, root, key, dimensions)
    roles = _roles(v, root)
    queries = _verified(v, root, metrics)
    cal = v.node(root, "calendar", LDict, False, LDict())
    v.only(cal, ("fiscal_year_start_month", "fiscal_year_naming"), "calendar")
    start = cal.get("fiscal_year_start_month", 1)
    if not isinstance(start, int) or not 1 <= start <= 12:
        v.fail(cal, "fiscal_year_start_month", "a month number from 1 to 12")
    v.one_of(cal, "fiscal_year_naming", ("start_year",), False, "start_year")
    return Catalog(name, version, entities, dimensions, mappings, attribution, measures, tuple(metrics),
                   grains["plan_grain"], grains["model_grain"], roles, tuple(queries), Calendar(start))  # fmt: skip


# ---- entities ---------------------------------------------------------------------------


def _entities(v: _Loader, node: LDict) -> dict[str, Entity]:
    out: dict[str, Entity] = {}
    for name, body in node.items():
        if not NAME.match(name):
            v.fail(node, name, "entity names are plain identifiers")
        v.only(body, ("view", "label", "requires", "relationships"), f"entity '{name}'")
        view = v.one_of(body, "view", tuple(VIEWS))
        requires = tuple(v.node(body, "requires", LList, False, LList()))
        for i, req in enumerate(requires):
            if not isinstance(req, str) or not re.match(r"^\w+\.\w+$", req):
                v.item(
                    body["requires"],
                    i,
                    "requires",
                    f"expected 'system.object', found {req!r}",
                )
        out[name] = Entity(name, view, requires, {})
    for name, body in node.items():
        rels = v.node(body, "relationships", LDict, False, LDict())
        for rname, rbody in rels.items():
            v.only(
                rbody,
                ("to", "cardinality", "join", "dedup", "versioned"),
                f"relationship '{rname}'",
            )
            to = v.node(rbody, "to", str)
            if to not in out:
                v.fail(rbody, "to", f"unknown entity {to!r}")
            card = v.one_of(rbody, "cardinality", CARDINALITY)
            on = v.node(rbody, "join", LList)
            local_types, remote_types = (
                VIEWS[out[name].view].typed(True),
                VIEWS[out[to].view].typed(False),
            )
            if len(on) != 2 or on[0] not in local_types or on[1] not in remote_types:
                v.fail(
                    rbody, "join", f"expected [column of '{name}', column of '{to}']"
                )
            dedup: tuple[str, ...] = ()
            if "dedup" in rbody:
                order = v.node(v.node(rbody, "dedup", LDict), "order_by", LList)
                if not order or any(c not in remote_types for c in order):
                    v.fail(rbody["dedup"], "order_by", f"expected columns of '{to}'")
                dedup = tuple(order)
            if card in ("one_to_many", "many_to_many") and not dedup:
                v.item(
                    rels,
                    rname,
                    "dedup",
                    f"a {card} join can multiply rows: declare dedup.order_by (the first row is kept)",
                )
            out[name].relationships[rname] = Relationship(
                rname,
                name,
                to,
                card,
                on[0],
                on[1],
                dedup,
                bool(rbody.get("versioned", False)),
            )
    return out


# ---- dimensions ---------------------------------------------------------------------------


def _dimensions(v: _Loader, node: LDict) -> dict[str, Dimension]:
    out = {}
    for name, body in node.items():
        if not NAME.match(name):
            v.fail(node, name, "dimension names are plain identifiers")
        v.only(
            body,
            (
                "label",
                "kind",
                "grain",
                "attribute_time",
                "levels",
                "members",
                "unmapped",
                "observed",
            ),
            f"dimension '{name}'",
        )
        kind = v.one_of(body, "kind", ("categorical", "time"), False, "categorical")
        label = v.node(body, "label", str, False, name)
        if kind == "time":
            grain = v.one_of(body, "grain", GRAINS)
            out[name] = Dimension(
                name, label, kind, grain, "current", (name,), {}, None, False
            )
            continue
        attr = v.one_of(body, "attribute_time", ATTRIBUTE_TIMES, False, "current")
        levels = tuple(v.node(body, "levels", LList, False, [name]))
        members: dict[str, dict[str, str]] = {}
        raw = v.node(body, "members", LList)
        for i, m in enumerate(raw):
            row = {levels[-1]: m} if isinstance(m, str) else dict(m)
            if not isinstance(m, str):
                row[levels[-1]] = row.pop("key", None)
            key = row.get(levels[-1])
            if not isinstance(key, str) or any(lv not in row for lv in levels):
                v.item(
                    raw,
                    i,
                    "members",
                    f"each member names a key and a value for every level {list(levels)}",
                )
            if key in members:
                v.item(raw, i, "members", f"duplicate member {key!r}")
            members[key] = {lv: row[lv] for lv in levels}
        unmapped = v.node(body, "unmapped", str, False)
        if unmapped is not None and unmapped not in members:
            v.fail(body, "unmapped", f"{unmapped!r} is not a declared member")
        out[name] = Dimension(
            name,
            label,
            kind,
            None,
            attr,
            levels,
            members,
            unmapped,
            bool(body.get("observed", False)),
        )
    return out


# ---- attribution policy and mappings ---------------------------------------------------------


def _attribution(v, root, dimensions, entities):
    if "attribution_policy" not in root:
        return None
    node = v.node(root, "attribution_policy", LDict)
    v.only(node, ("dimension", "entity", "rule", "precedence"), "attribution_policy")
    if node.get("dimension") not in dimensions:
        v.fail(node, "dimension", "not a declared dimension")
    if node.get("entity") not in entities:
        v.fail(node, "entity", "not a declared entity")
    prec = v.node(node, "precedence", LList)
    if not prec or len(set(prec)) != len(prec):
        v.fail(node, "precedence", "a non-empty list of distinct step names")
    return {
        "dimension": node["dimension"],
        "entity": node["entity"],
        "rule": node.get("rule", ""),
        "precedence": tuple(prec),
    }


def _mappings(v, node, dimensions, entities, attribution):
    out: dict[tuple[str, str], Mapping] = {}
    for dim_name in node:
        dim = dimensions.get(dim_name)
        if dim is None or dim.kind == "time":
            v.fail(
                node, dim_name, "mappings belong to a declared categorical dimension"
            )
        versions_seen: set[str] | None = None
        for i, body in enumerate(v.node(node, dim_name, LList)):
            v.only(
                body,
                ("entity", "inputs", "normalize", "passthrough", "versions"),
                "mapping",
            )
            entity = v.node(body, "entity", str)
            if entity not in entities:
                v.fail(body, "entity", f"unknown entity {entity!r}")
            view = VIEWS[entities[entity].view]
            if dim.unmapped is None:
                v.fail(
                    body,
                    "entity",
                    f"dimension {dim_name!r} declares no 'unmapped' member for values no rule matches",
                )
            if (dim_name, entity) in out:
                v.fail(
                    body,
                    "entity",
                    f"dimension {dim_name!r} is already mapped on {entity!r}",
                )
            if (dim.attribute_time == "at_creation" and not view.created) or (
                dim.attribute_time == "at_close" and not view.close
            ):
                v.fail(
                    body,
                    "entity",
                    f"entity '{entity}' has no {dim.attribute_time[3:]} time for attribute_time {dim.attribute_time}",
                )
            inputs, types = {}, {}
            for alias, path in v.node(body, "inputs", LDict).items():
                try:
                    parts = tuple(str(path).split("."))
                    _, _, ctype = resolve_path(entities, entity, parts)
                except ValueError as err:
                    v.fail(body["inputs"], alias, str(err))
                inputs[alias], types[alias] = parts, ctype
            normalize = bool(body.get("normalize", False))
            passthrough = body.get("passthrough")
            if passthrough is not None and passthrough not in inputs:
                v.fail(body, "passthrough", "must name one of the inputs")
            versions = {}
            vlist = v.node(body, "versions", LList)
            if not vlist:
                v.fail(body, "versions", "declare at least one version")
            for j, vbody in enumerate(vlist):
                v.only(vbody, ("version", "adopted_on", "rules"), "mapping version")
                ver = str(v.node(vbody, "version", (str, int, float)))
                if ver in versions:
                    v.item(vlist, j, "version", f"duplicate version {ver!r}")
                adopted = vbody.get("adopted_on")
                if adopted is not None and not isinstance(adopted, date):
                    v.fail(vbody, "adopted_on", "expected a date (YYYY-MM-DD)")
                rules = _rules(
                    v,
                    vbody,
                    dim,
                    types,
                    normalize,
                    attribution
                    if attribution
                    and attribution["dimension"] == dim_name
                    and attribution["entity"] == entity
                    else None,
                    passthrough,
                )
                versions[ver] = MappingVersion(ver, adopted, rules)
            if versions_seen is not None and set(versions) != versions_seen:
                v.fail(
                    body,
                    "versions",
                    f"every mapping of dimension {dim_name!r} declares the same versions: {sorted(versions_seen)}",
                )
            versions_seen = set(versions)
            out[(dim_name, entity)] = Mapping(
                dim_name, entity, inputs, normalize, passthrough, versions
            )
    return out


def _rules(v, vbody, dim, types, normalize, policy, passthrough):
    rules, last_step = [], -1
    rlist = v.node(vbody, "rules", LList, passthrough is None, LList())
    for k, rule in enumerate(rlist):
        v.only(rule, ("when", "member", "step"), "mapping rule")
        when = v.predicate(rule, "when", types, normalize=normalize)
        member = v.node(rule, "member", str)
        if member not in dim.members:
            v.fail(
                rule, "member", f"{member!r} is not a member of dimension '{dim.name}'"
            )
        step = rule.get("step")
        if policy is not None:
            if step not in policy["precedence"]:
                v.fail(
                    rule,
                    "step",
                    f"the attribution policy's steps are {list(policy['precedence'])}",
                )
            if policy["precedence"].index(step) < last_step:
                v.fail(
                    rule,
                    "step",
                    "rules must follow the attribution policy's precedence order",
                )
            last_step = policy["precedence"].index(step)
        rules.append(Rule(when, member, step, rlist.at(k)))
    return tuple(rules)


# ---- measures ---------------------------------------------------------------------------


def _measures(v, node, entities):
    out = {}
    for name, body in node.items():
        if not NAME.match(name):
            v.fail(node, name, "measure names are plain identifiers")
        v.only(body, ("entity", "agg", "column", "time", "where"), f"measure '{name}'")
        entity = v.node(body, "entity", str)
        if entity not in entities:
            v.fail(body, "entity", f"unknown entity {entity!r}")
        types = _entity_columns(entities, entity, True)
        agg = v.one_of(body, "agg", ("count", "sum"))
        column = body.get("column")
        if agg == "sum" and (column not in types or types[column] != "int"):
            v.fail(
                body, "column", "a sum needs a declared integer column of the entity"
            )
        if column is not None and column not in types:
            v.fail(body, "column", f"entity '{entity}' has no column '{column}'")
        time = body.get("time")
        if time is not None and types.get(time) != "date":
            v.fail(
                body,
                "time",
                f"must be a date column of entity '{entity}' (or omit it for a stock at T)",
            )
        where = v.predicate(body, "where", types) if "where" in body else None
        out[name] = Measure(name, entity, agg, column, time, where, node.at(name))
    return out


# ---- metrics ---------------------------------------------------------------------------


def _metric_entities(spec, measures):
    kind = spec["kind"]
    if kind == "conversion":
        return [spec["anchor"]["entity"]]
    names = {
        "sum": ["measure"],
        "quantile": ["measure"],
        "ratio": ["numerator", "denominator"],
    }.get(kind, [])
    if kind == "estimator":
        return [measures[m].entity for m in spec["inputs"].values()]
    return [measures[spec[n]].entity for n in names]


def _metrics(v, node, measures, dimensions, mappings, entities):
    out: list[Metric] = []
    for i, body in enumerate(node):
        kind = v.one_of(body, "kind", KINDS)
        v.only(body, COMMON + KIND_KEYS[kind], f"a {kind} metric")
        for key in (
            "id",
            "version",
            "label",
            "unit",
            "population",
            "basis",
            "aggregation",
            "dimensions",
            "favorable",
            "owner",
            "definition",
        ):
            if key not in body:
                v._missing(body, key)
        mid, mver = v.node(body, "id", str), str(body["version"])
        if any(m.id == mid and m.version == mver for m in out):
            v.fail(
                body, "version", f"metric {mid!r} version {mver!r} is declared twice"
            )
        basis = v.one_of(body, "basis", ("period", "cohort", "snapshot"))
        agg = v.one_of(body, "aggregation", AGGREGATION)
        if (kind == "sum" and agg == "non_additive") or (
            kind != "sum" and agg != "non_additive"
        ):
            v.fail(
                body,
                "aggregation",
                f"a {kind} metric is {'additive or snapshot' if kind == 'sum' else 'non_additive'}",
            )
        if (basis == "snapshot") != (agg == "snapshot"):
            v.fail(
                body,
                "aggregation",
                "a snapshot metric has basis snapshot and aggregation snapshot, and only those",
            )
        favorable = v.one_of(body, "favorable", ("up", "down", "none"))
        spec = {k: body[k] for k in KIND_KEYS[kind] if k in body}
        for key in KIND_KEYS[kind]:
            if key not in body and key not in (
                "of_version",
                "q",
                "params",
                "output",
                "window_days",
                "target",
            ):
                v._missing(body, key)
        for ref in ("measure", "numerator", "denominator"):
            if ref in spec and spec[ref] not in measures:
                v.fail(body, ref, f"unknown measure {spec[ref]!r}")
        if kind == "quantile" and not (
            0 < float(spec["q"]) < 1 and measures[spec["measure"]].column
        ):
            v.fail(body, "q", "q is between 0 and 1 and the measure names a column")
        if kind == "rollup":
            v.one_of(spec, "stat", ("mean", "median", "max", "min"))
            v.one_of(spec, "period", GRAINS)
            if not any(m.id == spec["of"] for m in out):
                v.fail(
                    body,
                    "of",
                    f"rollup of {spec['of']!r}: declare the inner metric first",
                )
        if kind == "estimator":
            for role, mname in v.node(spec, "inputs", LDict).items():
                if mname not in measures:
                    v.fail(spec["inputs"], role, f"unknown measure {mname!r}")
        if kind == "conversion":
            spec = _conversion(v, body, spec, entities)
        if (
            basis == "snapshot"
            and spec.get("measure")
            and measures[spec["measure"]].time
        ):
            v.fail(body, "basis", "a snapshot measure has no time column")
        dims = v.node(body, "dimensions", LList)
        ents = (
            _metric_entities({**spec, "kind": kind}, measures)
            if kind != "rollup"
            else _rollup_entities(spec, out, measures)
        )
        for j, d in enumerate(dims):
            dim = dimensions.get(d)
            if dim is None:
                v.item(dims, j, "dimensions", f"unknown dimension {d!r}")
            if dim.kind == "time":
                if basis == "snapshot":
                    v.item(dims, j, "dimensions", "a snapshot has no time dimension")
            elif any((d, e) not in mappings for e in ents):
                v.item(
                    dims,
                    j,
                    "dimensions",
                    f"dimension {d!r} has no mapping on every entity this metric reads ({sorted(set(ents))})",
                )
        applic = _applicability(v, body, dims, dimensions)
        excl = _exclusions(v, body, ents, entities)
        out.append(Metric(mid, mver, v.node(body, "label", str), str(body["unit"]), str(body["population"]), basis, kind, agg,
                          tuple(dims), applic, favorable, str(body["owner"]), str(body["definition"]),
                          str(body.get("ai_context", "")), {**spec, "exclusions": excl, "maturity_days": body.get("maturity_days"),
                                                           "min_denominator": body.get("min_denominator")}, node.at(i)))  # fmt: skip
    return out


def _rollup_entities(spec, built, measures):
    inner = next(m for m in reversed(built) if m.id == spec["of"])
    return _metric_entities({**inner.spec, "kind": inner.kind}, measures)


def _conversion(v, body, spec, entities):
    anchor = v.node(spec, "anchor", LDict)
    v.only(anchor, ("entity", "time", "where"), "conversion anchor")
    entity = v.node(anchor, "entity", str)
    if entity not in entities:
        v.fail(anchor, "entity", f"unknown entity {entity!r}")
    types = _entity_columns(entities, entity, True)
    if types.get(anchor.get("time")) != "date":
        v.fail(
            anchor,
            "time",
            "the anchor event time is a date column of the anchor entity",
        )
    if "where" in anchor:
        v.predicate(anchor, "where", types)
    rel = entities[entity].relationships.get(spec["link"])
    if rel is None or rel.cardinality not in ("many_to_one", "one_to_one"):
        v.fail(body, "link", f"a many_to_one or one_to_one relationship of '{entity}'")
    if types.get(spec["event"]) != "date":
        v.fail(
            body,
            "event",
            f"the conversion event date is a date column of '{entity}' (when the lead converted)",
        )
    target = v.node(spec, "target", LDict, False, LDict())
    v.only(target, ("where",), "conversion target")
    ttypes = _entity_columns(entities, rel.to, False)
    if "where" in target:
        v.predicate(target, "where", ttypes)
    out = v.one_of(spec, "output", ("rate", "lag"), False, "rate")
    return {
        **spec,
        "output": out,
        "window_days": int(spec.get("window_days", 90)),
        "anchor": dict(anchor),
        "target": dict(target),
    }


def _applicability(v, body, dims, dimensions):
    out = []
    for entry in v.node(body, "applicability", LList, False, LList()):
        v.only(entry, ("dimension", "members", "reason"), "applicability rule")
        d = v.node(entry, "dimension", str)
        if d not in dims:
            v.fail(entry, "dimension", "must be one of the metric's dimensions")
        valid = {val for m in dimensions[d].members.values() for val in m.values()}
        for m in v.node(entry, "members", LList):
            if m not in valid:
                v.fail(entry, "members", f"{m!r} is not a member of '{d}'")
        out.append(
            {
                "dimension": d,
                "members": tuple(entry["members"]),
                "reason": str(entry.get("reason", "")),
            }
        )
    return tuple(out)


def _exclusions(v, body, ents, entities):
    out = []
    for entry in v.node(body, "exclusions", LList, False, LList()):
        v.only(entry, ("reason", "when"), "exclusion")
        types = _entity_columns(entities, ents[0], True)
        out.append(
            {
                "reason": v.node(entry, "reason", str),
                "when": v.predicate(entry, "when", types),
            }
        )
    return tuple(out)


# ---- grains, roles, verified queries -------------------------------------------------------


def _grain(v, root, key, dimensions):
    out = []
    for i, item in enumerate(v.node(root, key, LList, False, LList())):
        dim, _, level = str(item).partition(".")
        if dim not in dimensions or (level and level not in dimensions[dim].levels):
            v.item(
                root[key],
                i,
                key,
                f"{item!r} is not a dimension (or level) of this catalog",
            )
        out.append(str(item))
    return tuple(out)


def _roles(v, root):
    out = {}
    for kind, body in v.node(root, "roles", LDict, False, LDict()).items():
        v.only(body, ROLE_KEYS, f"role '{kind}'")
        v.one_of(body, "type", ("control", "outcome"))
        out[kind] = dict(body)
    return out


def _verified(v, root, metrics):
    out, ids = [], {m.id for m in metrics}
    for i, body in enumerate(v.node(root, "verified_queries", LList, False, LList())):
        v.only(
            body,
            (
                "id",
                "question",
                "call",
                "expect",
                "verified_by",
                "verified_at",
                "fixture",
            ),
            "verified query",
        )
        call = v.node(body, "call", LDict)
        if call.get("metric") not in ids:
            v.fail(call, "metric", f"unknown metric {call.get('metric')!r}")
        if not isinstance(body.get("verified_at"), date):
            v.fail(body, "verified_at", "expected a date (YYYY-MM-DD)")
        out.append(VerifiedQuery(v.node(body, "id", str), v.node(body, "question", str), dict(call), dict(v.node(body, "expect", LDict)),
                                 v.node(body, "verified_by", str), body["verified_at"], v.node(body, "fixture", str)))  # fmt: skip
    return out

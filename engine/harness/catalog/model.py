"""The validated catalog, as plain immutable data."""

from dataclasses import dataclass, field
from datetime import date

AGGREGATION = ("additive", "snapshot", "non_additive")
KINDS = ("sum", "ratio", "quantile", "rollup", "conversion", "estimator")
ATTRIBUTE_TIMES = ("at_creation", "at_close", "current")
GRAINS = ("month", "quarter", "year")


@dataclass(frozen=True)
class Relationship:
    name: str
    source: str  # entity it starts from
    to: str  # entity it reaches
    cardinality: str  # many_to_one | one_to_one | one_to_many | many_to_many
    local: str
    remote: str
    dedup: tuple[
        str, ...
    ] = ()  # order_by columns of `to`; the first row per remote key is kept
    versioned: bool = False  # read at the row's own date (attribute time), not as of T


@dataclass(frozen=True)
class Entity:
    name: str
    view: str
    requires: tuple[str, ...]  # "system.object", must be extracted at K
    relationships: dict[str, Relationship]


@dataclass(frozen=True)
class Dimension:
    name: str
    label: str
    kind: str  # categorical | time
    grain: str | None
    attribute_time: str
    levels: tuple[str, ...]  # top to leaf; the leaf is what mappings produce
    members: dict[str, dict[str, str]]  # leaf member to its value at every level
    unmapped: str | None  # the declared member that unmatched raw values land in
    observed: bool  # members are discovered from the data (people), not declared


@dataclass(frozen=True)
class Rule:
    when: str
    member: str
    step: str | None
    line: int


@dataclass(frozen=True)
class MappingVersion:
    version: str
    adopted_on: date | None
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class Mapping:
    dimension: str
    entity: str
    inputs: dict[
        str, tuple[str, ...]
    ]  # alias to path (relationship names, then a column)
    normalize: bool
    passthrough: (
        str | None
    )  # an input alias whose value is the member (observed dimensions)
    versions: dict[str, MappingVersion]


@dataclass(frozen=True)
class Measure:
    name: str
    entity: str
    agg: str  # count | sum
    column: str | None
    time: str | None
    where: str | None
    line: int = 0


@dataclass(frozen=True)
class Metric:
    id: str
    version: str
    label: str
    unit: str
    population: str
    basis: str  # period | cohort | snapshot
    kind: str
    aggregation: str
    dimensions: tuple[str, ...]
    applicability: tuple[dict, ...]
    favorable: str
    owner: str
    definition: str
    ai_context: str
    spec: dict = field(default_factory=dict)  # kind-specific keys, validated at load
    line: int = 0


@dataclass(frozen=True)
class VerifiedQuery:
    id: str
    question: str
    call: dict
    expect: dict
    verified_by: str
    verified_at: date
    fixture: str


@dataclass(frozen=True)
class Catalog:
    name: str
    version: str
    entities: dict[str, Entity]
    dimensions: dict[str, Dimension]
    mappings: dict[tuple[str, str], Mapping]  # (dimension, entity)
    attribution: dict | None
    measures: dict[str, Measure]
    metrics: tuple[Metric, ...]
    plan_grain: tuple[str, ...]
    model_grain: tuple[str, ...]
    roles: dict
    verified_queries: tuple[VerifiedQuery, ...]

    def metric(self, metric_id: str, version: str | None = None) -> Metric:
        found = [
            m
            for m in self.metrics
            if m.id == metric_id and version in (None, m.version)
        ]
        if not found:
            raise KeyError(
                f"no metric {metric_id!r}"
                + (f" version {version!r}" if version else "")
            )
        return found[-1]  # the last declared version is the default

    def metric_versions(self, metric_id: str) -> list[str]:
        return [m.version for m in self.metrics if m.id == metric_id]

    def metric_entities(self, metric: "Metric") -> list[str]:
        """The entities a metric reads (the first is its main one)."""
        s = metric.spec
        if metric.kind == "conversion":
            return [s["anchor"]["entity"]]
        if metric.kind == "rollup":
            return self.metric_entities(self.metric(s["of"], s.get("of_version")))
        names = (
            s["inputs"].values()
            if metric.kind == "estimator"
            else [s[k] for k in ("measure", "numerator", "denominator") if k in s]
        )
        return [self.measures[n].entity for n in names]

    def mapping(self, dimension: str, entity: str) -> Mapping | None:
        return self.mappings.get((dimension, entity))

    def mapping_version(
        self, dimension: str, entity: str, version: str | None
    ) -> tuple[str, MappingVersion]:
        mapping = self.mappings[(dimension, entity)]
        if (
            version is None
        ):  # most recently adopted; adopted_on is governance, never a row filter
            version = max(
                mapping.versions.values(), key=lambda v: v.adopted_on or date.min
            ).version
        if version not in mapping.versions:
            raise KeyError(
                f"mapping for {dimension!r} on {entity!r} has no version {version!r}"
            )
        return version, mapping.versions[version]

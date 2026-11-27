"""``plan.yaml``: the only source of further hires and of programme pipeline.

A hire is a segment, a start month and a count; it starts on the first day of
that month and must not repeat a signed hire on ``team_members.csv`` (same
segment, same start month). A programme is dollars of created pipeline, a start
month, an optional ramp in months, an optional length in months and an
optional cost. Items are applied in the order hires first, then programmes,
each in file order.

Programme arithmetic: a programme running N months (default: through the
fiscal-year end) creates its dollars in the month windows from its start month,
month j at a weight of min(1, j / ramp); the dollars are split in proportion to
those weights and spread evenly over each month's days. The dollars are exact:
they add to the programme's pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from .fiscal import Window, add_months
from .forecast import Inflow
from .roster import Member

DEFAULT_PROGRAMME_RAMP_MONTHS = 3
REST_OF_FY = "rest of fiscal year"
NEXT_12 = "next twelve months"


@dataclass(frozen=True)
class PlanHire:
    segment: str
    start: date  # the first day of the start month
    count: int

    @property
    def label(self) -> str:
        noun = "hire" if self.count == 1 else "hires"
        return f"{self.count} {self.segment} {noun} from {self.start:%Y-%m}"


@dataclass(frozen=True)
class PlanProgramme:
    name: str
    pipeline: Decimal
    start: date
    ramp_months: int | None = None
    months: int | None = None
    cost: Decimal | None = None

    @property
    def label(self) -> str:
        return self.name


@dataclass(frozen=True)
class Plan:
    hires: tuple[PlanHire, ...]
    programmes: tuple[PlanProgramme, ...]

    def items(self) -> list[PlanHire | PlanProgramme]:
        return [*self.hires, *self.programmes]

    def members_for(self, index: int) -> tuple[Member, ...]:
        """The people hire ``index`` adds."""
        h = self.hires[index]
        return tuple(
            Member(f"PLAN-{index + 1}-{j + 1}", "ae", h.segment, h.start, None, None)
            for j in range(h.count)
        )

    def hire_members(self) -> tuple[Member, ...]:
        return tuple(m for i in range(len(self.hires)) for m in self.members_for(i))


def next_month_start(as_of: date) -> date:
    return add_months(date(as_of.year, as_of.month, 1), 1)


def load_plan(path: Path, as_of: date, members) -> Plan:
    doc = yaml.safe_load(Path(path).read_text()) or {}
    signed = {
        (m.segment, m.start.year, m.start.month) for m in members if m.start > as_of
    }
    hires = []
    for i, raw in enumerate(doc.get("hires") or (), start=1):
        where = f"{path}: hires[{i}]"
        start = _month(raw.get("start"), as_of, where)
        segment = str(raw.get("segment") or "").strip()
        count = raw.get("count", 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(f"{where}: count must be a whole number of at least 1")
        if (segment, start.year, start.month) in signed:
            raise ValueError(
                f"{where}: {count} {segment} hire(s) in {start:%Y-%m} repeats a signed hire "
                "on team_members.csv; plan.yaml lists only further hires"
            )
        hires.append(PlanHire(segment, start, count))
    programmes = []
    for i, raw in enumerate(doc.get("programmes") or (), start=1):
        where = f"{path}: programmes[{i}]"
        pipeline = _decimal(raw.get("pipeline"), "pipeline", where)
        if pipeline <= 0:
            raise ValueError(f"{where}: pipeline must be more than 0")
        cost = raw.get("cost")
        programmes.append(
            PlanProgramme(
                str(raw.get("name") or f"programme {i}"),
                pipeline,
                _month(raw.get("start"), as_of, where),
                _opt_int(raw.get("ramp_months"), "ramp_months", where),
                _opt_int(raw.get("months"), "months", where),
                None if cost is None else _decimal(cost, "cost", where),
            )
        )
    return Plan(tuple(hires), tuple(programmes))


def programme_cost(p: PlanProgramme, per_dollar: Decimal | None) -> Decimal | None:
    """Its own cost if given, else pipeline times the cost per dollar of pipeline
    in capacity.yaml, else None: cost not entered."""
    if p.cost is not None:
        return p.cost
    return None if per_dollar is None else p.pipeline * per_dollar


def programme_inflows(
    p: PlanProgramme,
    windows: list[Window],
    as_of: date,
    fiscal_year_end: date,
    default_ramp_months: int,
) -> tuple[Inflow, ...]:
    """The dollars a programme creates in each month window, as exact inflows."""
    ramp = p.ramp_months or default_ramp_months
    starts = f"{p.start:%Y-%m}"
    months = [w for w in windows if w.label >= starts]
    if p.months is not None:
        months = months[: p.months]
    elif p.start <= fiscal_year_end:
        months = [w for w in months if w.end <= fiscal_year_end]
    weights = [Decimal(min(j, ramp)) / Decimal(ramp) for j in range(1, len(months) + 1)]
    total = sum(weights, Decimal(0))
    if not total:
        return ()
    return tuple(
        Inflow((w.start - as_of).days, (w.end - as_of).days, p.pipeline * wt / total)
        for w, wt in zip(months, weights)
    )


def _month(value, as_of: date, where: str) -> date:
    try:
        text = str(value)
        year, month = int(text[:4]), int(text[5:7])
        start = date(year, month, 1)
    except (ValueError, TypeError):
        raise ValueError(f"{where}: start must be a month, like 2026-10") from None
    if start <= as_of:
        raise ValueError(
            f"{where}: starts {start:%Y-%m}, which is not after the as-of date {as_of}"
        )
    return start


def _decimal(value, name: str, where: str) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{where}: {name} must be a number") from None


def _opt_int(value, name: str, where: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{where}: {name} must be a whole number of at least 1")
    return value

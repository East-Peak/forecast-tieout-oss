"""``plan.yaml``: the only source of further hires and of program pipeline.

A hire is a segment, a start month and a count; it starts on the first day of
that month and must not repeat a signed hire on ``team_members.csv`` (same
segment, same start month). A program is dollars of created pipeline, a start
month, an optional ramp in months, an optional length in months and an
optional cost. Items are applied in the order hires first, then programs,
each in file order.

Program arithmetic: a program running N months (default: through the
fiscal-year end) creates its dollars in the calendar months from its start
month, month j at a weight of min(1, j / ramp); the dollars of the whole
program are split in proportion to those weights and spread evenly over each
month's days. Only then is the schedule clipped to the report's twelve months
(a partial final month keeps its share of the days), so the dollars in the
window never exceed the program's pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from .fiscal import Window, add_months
from .forecast import Inflow
from .roster import Member

DEFAULT_PROGRAM_RAMP_MONTHS = 3
REST_OF_FY = "rest of fiscal year"
NEXT_12 = "next twelve months"


def segment_words(segment: str) -> str:
    """A segment key as words: ``mid_market`` reads "Mid Market"."""
    return " ".join(w[:1].upper() + w[1:] for w in segment.replace("_", " ").split())


@dataclass(frozen=True)
class PlanHire:
    segment: str
    start: date  # the first day of the start month
    count: int

    @property
    def label(self) -> str:
        noun = "hire" if self.count == 1 else "hires"
        return (
            f"{self.count} {segment_words(self.segment)} {noun} from {self.start:%Y-%m}"
        )


@dataclass(frozen=True)
class PlanProgram:
    name: str
    pipeline: Decimal
    start: date
    ramp_months: int | None = None
    months: int | None = None
    cost: Decimal | None = None
    # (month, amount) payments, when the plan gives them; otherwise the cost is
    # paid in step with the pipeline the program creates.
    payments: tuple[tuple[date, Decimal], ...] | None = None

    @property
    def label(self) -> str:
        return self.name


@dataclass(frozen=True)
class Plan:
    hires: tuple[PlanHire, ...]
    programs: tuple[PlanProgram, ...]

    def items(self) -> list[PlanHire | PlanProgram]:
        return [*self.hires, *self.programs]

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
    programs = []
    for i, raw in enumerate(doc.get("programs") or (), start=1):
        where = f"{path}: programs[{i}]"
        pipeline = _decimal(raw.get("pipeline"), "pipeline", where)
        if pipeline <= 0:
            raise ValueError(f"{where}: pipeline must be more than 0")
        cost = raw.get("cost")
        payments = _payments(raw.get("payments"), as_of, where)
        programs.append(
            PlanProgram(
                str(raw.get("name") or f"program {i}"),
                pipeline,
                _month(raw.get("start"), as_of, where),
                _opt_int(raw.get("ramp_months"), "ramp_months", where),
                _opt_int(raw.get("months"), "months", where),
                None
                if cost is None
                else _non_negative(_decimal(cost, "cost", where), "cost", where),
                payments,
            )
        )
    return Plan(tuple(hires), tuple(programs))


def program_cost(p: PlanProgram, per_dollar: Decimal | None) -> Decimal | None:
    """Its own cost if given, else pipeline times the cost per dollar of pipeline
    in capacity.yaml, else None: cost not entered."""
    if p.payments is not None:
        return sum((amount for _, amount in p.payments), Decimal(0))
    if p.cost is not None:
        return p.cost
    return None if per_dollar is None else p.pipeline * per_dollar


def program_cost_in_window(
    p: PlanProgram,
    per_dollar: Decimal | None,
    flows: tuple[Inflow, ...],
    window_end: date,
) -> Decimal | None:
    """The part of the cost that falls inside the report's twelve months. With a
    payment schedule in the plan, the payments dated in the window; otherwise
    the cost is paid in step with the pipeline created, so the share of the
    program's pipeline created in the window carries that share of the cost."""
    total = program_cost(p, per_dollar)
    if total is None:
        return None
    if p.payments is not None:
        return sum((a for m, a in p.payments if m <= window_end), Decimal(0))
    created = sum((f.dollars for f in flows), Decimal(0))
    return total * created / p.pipeline


def program_inflows(
    p: PlanProgram,
    windows: list[Window],
    as_of: date,
    fiscal_year_end: date,
    default_ramp_months: int,
) -> tuple[Inflow, ...]:
    """The dollars a program creates in each month window, as exact inflows."""
    ramp = p.ramp_months or default_ramp_months
    horizon = (windows[-1].end - as_of).days if windows else 0
    starts = f"{p.start:%Y-%m}"
    if p.months is not None:
        length = p.months
    elif p.start <= fiscal_year_end:
        length = (
            (fiscal_year_end.year - p.start.year) * 12
            + fiscal_year_end.month
            - p.start.month
            + 1
        )
    else:
        length = sum(1 for w in windows if w.label >= starts)
    # The whole program is normalized first; only then is it clipped to the
    # report's window (a partial final month keeps its share of the days).
    weights = [Decimal(min(j, ramp)) / Decimal(ramp) for j in range(1, length + 1)]
    total = sum(weights, Decimal(0))
    flows = []
    for j, wt in enumerate(weights):
        first = add_months(p.start, j)
        last = add_months(p.start, j + 1) - timedelta(days=1)
        lo, hi = (first - timedelta(days=1) - as_of).days, (last - as_of).days
        if lo >= horizon:
            break
        dollars = p.pipeline * wt / total
        if hi > horizon:
            dollars = dollars * Decimal(horizon - lo) / Decimal(hi - lo)
            hi = horizon
        flows.append(Inflow(lo, hi, dollars))
    return tuple(flows)


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
        out = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{where}: {name} must be a number") from None
    if not out.is_finite():
        raise ValueError(f"{where}: {name} must be a finite number")
    return out


def _payments(raw, as_of: date, where: str):
    if raw is None:
        return None
    out = []
    for k, item in enumerate(raw, start=1):
        at = f"{where}: payments[{k}]"
        month = _month(item.get("month"), as_of, at + " month")
        amount = _non_negative(_decimal(item.get("amount"), "amount", at), "amount", at)
        out.append((month, amount))
    return tuple(out)


def _non_negative(value: Decimal, name: str, where: str) -> Decimal:
    if value < 0:
        raise ValueError(f"{where}: {name} must not be negative")
    return value


def _opt_int(value, name: str, where: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{where}: {name} must be a whole number of at least 1")
    return value

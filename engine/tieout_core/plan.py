"""``plan.yaml``: the only source of further hires and of program pipeline.

A hire is a segment, a start month and a count; it starts on the first day of
that month and must not repeat a signed hire on ``team_members.csv`` (same
segment, same start month). A program is dollars of created pipeline, a start
month, an optional ramp in months, an optional length in months and an
optional cost. Items are applied in the order hires first, then programs,
each in file order.

An action is a named change to one driver in one slice (the company, or one
segment): a stable id, a start month, a ramp in months (0 is immediate) and a
target value. Only the win rate, the won ARR per win and creation productivity can be acted
on so far; a win rate's target is a probability, a size's is dollars per won deal and a
productivity's is deals per ramped AE-month (per day where the capacity term is not in use),
the last two read against the pooled value. An action changes the pipeline created from its
start, so it is not an item to apply in turn: the joint effect of all the actions is valued
together, on top of the hires and programs. Two actions on one driver may not
touch the same slice, and the company touches every segment.

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
from .worksheet_rules import PRODUCTIVITY, WIN_RATE, WON_ARR

DEFAULT_PROGRAM_RAMP_MONTHS = 3
REST_OF_FY = "rest of fiscal year"
NEXT_12 = "next twelve months"
COMPANY = "company"  # an action's slice when it is not one segment's
ACTION_DRIVERS = (WIN_RATE, WON_ARR, PRODUCTIVITY)
MAX_RAMP_MONTHS = 60  # five years: longer than any horizon a plan is read over


class ActionRefused(ValueError):
    """An action the loader refuses. The message is for a person (no item numbers, no field names, a
    segment by its display label); ``code`` says which rule refused it, for a program."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


def month_words(d: date) -> str:
    """A month as a person writes it: ``October 2026``."""
    return f"{d:%B} {d.year}"


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
class PlanAction:
    id: str
    name: str
    driver: str
    segment: str | None  # None: the company, every segment alike
    start: date  # the first day of the start month
    ramp_months: int  # 0: the whole change from the start
    target: Decimal  # the driver's value once the ramp is done

    @property
    def label(self) -> str:
        return self.name

    @property
    def slice_label(self) -> str:
        return "Company" if self.segment is None else segment_words(self.segment)


@dataclass(frozen=True)
class Plan:
    hires: tuple[PlanHire, ...]
    programs: tuple[PlanProgram, ...]
    actions: tuple[PlanAction, ...] = ()

    def items(self) -> list[PlanHire | PlanProgram | PlanAction]:
        return [*self.hires, *self.programs, *self.actions]

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
    return parse_plan(doc, as_of, members, str(path))


def parse_plan(doc: dict, as_of: date, members, source: str) -> Plan:
    """A plan from its parsed document; ``source`` names it at the start of every message
    (the file's path, or "your plan" when it came from a form)."""
    signed = {
        (m.segment, m.start.year, m.start.month) for m in members if m.start > as_of
    }
    hires = []
    for i, raw in enumerate(doc.get("hires") or (), start=1):
        where = f"{source}: hires[{i}]"
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
        where = f"{source}: programs[{i}]"
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
    actions = _actions(doc.get("actions") or (), as_of, members, source)
    return Plan(tuple(hires), tuple(programs), actions)


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


def _actions(raw_items, as_of: date, members, source: str) -> tuple[PlanAction, ...]:
    segments = {m.segment for m in members if m.segment}
    out: list[PlanAction] = []
    for i, raw in enumerate(raw_items, start=1):
        where = f"{source}: actions[{i}]"
        if not isinstance(raw, dict):
            raise ActionRefused(
                f"{where}: An action must be a set of fields: name, slice, start, ramp and target.",
                "shape",
            )
        out.append(_action(raw, as_of, segments, where))
        _refuse_overlap(out, where)
    return tuple(out)


def _action(raw: dict, as_of: date, segments: set[str], where: str) -> PlanAction:
    def refuse(code: str, message: str) -> ActionRefused:
        return ActionRefused(f"{where}: {message}", code)

    ident = str(raw.get("id") or "").strip()
    if not ident:
        raise refuse(
            "id", "An action needs an id that stays the same when the plan changes."
        )
    driver = raw.get("driver")
    if driver not in ACTION_DRIVERS:
        raise refuse(
            "driver",
            "Only the win rate, won ARR per win and creation productivity can be changed by an action so far.",
        )
    where_slice = str(raw.get("slice") or "").strip()
    if where_slice != COMPANY and where_slice not in segments:
        names = ", ".join(segment_words(s) for s in sorted(segments))
        raise refuse(
            "slice",
            f"{where_slice!r} is not the company or a segment on the roster ({names}).",
        )
    ramp = raw.get("ramp_months", 0)
    if (
        not isinstance(ramp, int)
        or isinstance(ramp, bool)
        or not 0 <= ramp <= MAX_RAMP_MONTHS
    ):
        raise refuse(
            "ramp",
            f"The ramp must be a whole number of months, from 0 to {MAX_RAMP_MONTHS}.",
        )
    target = _target(raw.get("target"), driver, where, refuse)
    try:
        start = _month(raw.get("start"), as_of, where)
    except ValueError:
        text = str(raw.get("start"))
        try:
            began = date(int(text[:4]), int(text[5:7]), 1)
        except (ValueError, TypeError):
            raise refuse("start", "The start must be a month, like 2026-10.") from None
        raise refuse(
            "start",
            f"Starts in {month_words(began)}, which is not after the as-of date, "
            f"{as_of:%B} {as_of.day}, {as_of.year}.",
        ) from None
    try:
        add_months(start, ramp)  # the ramp's last day must be a date
    except (ValueError, OverflowError):
        raise refuse(
            "ramp",
            f"A ramp of {ramp} months from {month_words(start)} runs past the last date the plan can hold.",
        ) from None
    return PlanAction(
        ident,
        str(raw.get("name") or ident),
        driver,
        None if where_slice == COMPANY else where_slice,
        start,
        ramp,
        target,
    )


def _target(value, driver: str, where: str, refuse) -> Decimal:
    """A target in the driver's own terms, or the refusal in a person's words."""
    noun = TARGET_NOUN[driver]
    try:
        target = _decimal(value, "target", where)
    except ValueError:
        raise refuse(
            "target", f"The target {noun} must be a number{_OF[driver]}."
        ) from None
    if driver == WIN_RATE and not 0 <= target <= 1:
        shown = (target * 100).normalize()
        raise refuse(
            "target",
            f"The target win rate must be between 0% and 100%, not {shown:f}%.",
        )
    if driver != WIN_RATE and target < 0:
        raise refuse(
            "target",
            f"The target {noun} must be zero or more {_UNIT[driver]}, not {_negative(driver, target)}.",
        )
    return target


def _negative(driver: str, target: Decimal) -> str:
    """A negative target as a person writes it: -$5 of dollars, -0.2 of deals."""
    shown = f"{-target.normalize():f}"
    return f"-${shown}" if driver == WON_ARR else f"-{shown}"


TARGET_NOUN = {
    WIN_RATE: "win rate",
    WON_ARR: "won ARR per win",
    PRODUCTIVITY: "creation productivity",
}
_OF = {WIN_RATE: "", WON_ARR: " of dollars", PRODUCTIVITY: " of deals"}
_UNIT = {WON_ARR: "dollars", PRODUCTIVITY: "deals"}
NOUN = {
    WIN_RATE: "win rate",
    WON_ARR: "size of a won deal",
    PRODUCTIVITY: "creation productivity",
}


def _refuse_overlap(actions: list[PlanAction], where: str) -> None:
    """The last action added may not change a driver where an earlier one already does: the
    same segment, or the company against any segment (it touches every one)."""
    new = actions[-1]
    for old in actions[:-1]:
        if old.id == new.id:
            raise ActionRefused(
                f"{where}: Another action already has the id {new.id!r}; ids are unique.",
                "duplicate_id",
            )
        if old.driver == new.driver and (
            old.segment is None or new.segment is None or old.segment == new.segment
        ):
            raise ActionRefused(
                f"{where}: Overlaps {old.name!r}: {_both(old, new)}, so the change would be counted twice.",
                "overlap",
            )


def _both(old: PlanAction, new: PlanAction) -> str:
    """What the two overlapping actions change, in words: the same slice, or the company and a segment in it."""
    noun = NOUN[new.driver]
    if old.segment == new.segment:
        return f"both change the {noun} for {old.slice_label}"
    segment = old.slice_label if old.segment is not None else new.slice_label
    return f"one changes the {noun} for the whole company, which includes {segment}"

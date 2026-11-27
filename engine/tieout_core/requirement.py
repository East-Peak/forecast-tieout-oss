"""Required against expected pipeline, by quarter (section 10).

One deterministic solve in quarter order. For each remaining quarter with a
target, the extra pipeline that must be created, spread evenly over every day
from the day after the as-of date to that quarter's end (creation starts now),
so that the quarter's bookings meet its target given its actuals, the pipeline
already open and what earlier quarters were assigned. Each quarter is covered,
needs $X, or is unreachable within the cap; an unreachable quarter is assigned
nothing and the next is solved from there. The cap is one cap across the
quarters: what is left of it after earlier assignments.

Goal 2C adds what a planner needs beside that: the cents of each created dollar
that book inside the quarter, the lead-time table, and the "too late" rule.

The "too late" rule, as specified: a quarter that needs extra pipeline is too late
to fund with new pipeline when its requirement is over the cap, or when its
requirement per ramped AE-month is above the team's best four-quarter average.
Builder's call on the second leg, declared before any demo result was computed:
it applies only when capacity is the forecast's basis (adopted). When capacity
was not shown to explain pipeline, the per-rep comparison stays a labeled
diagnostic (as in 2B), because a ceiling derived from headcount would rest on a
relationship this history did not support; the cap leg then decides alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import NamedTuple

from .fiscal import FiscalYear, Window, month_end, month_windows
from .fit import Model
from .forecast import ADDED, EXISTING, Creation, Inflow, model_forecast
from .history import UNKNOWN_STAGE
from .lever import COVERED, FEASIBLE, UNREACHABLE, solve_added_pipeline
from .records import Dataset

ZERO = Decimal(0)


@dataclass(frozen=True)
class QuarterResult:
    quarter: str
    status: str
    target: Decimal
    actual: Decimal
    outcome: str  # COVERED, FEASIBLE or UNREACHABLE
    required: Decimal | None  # the extra pipeline; None when no amount can help
    assigned: Decimal  # what later quarters are solved after: 0 unless FEASIBLE
    cap_left: Decimal
    forecast_without: (
        Decimal  # actual + forecast with earlier quarters' pipeline, none of its own
    )
    forecast_with: Decimal  # ... with its own assignment
    piece: tuple[date, date]  # (as-of, quarter end]: where its pipeline is created
    inflows: tuple[Inflow, ...]
    expected_created: (
        Decimal  # dollars the forward function expects created in the piece
    )
    ramped_ae_months: Decimal | None  # expected ramped AE-months in the piece
    # Goal 2C: of each dollar created on this quarter's own schedule, the share that
    # books inside the quarter (from the forward function, not from the solve)
    yield_per_dollar: Decimal = ZERO
    open_arr: Decimal = ZERO  # dollars of pipeline open at the as-of date
    open_expected: Decimal = ZERO  # what the open pipeline is expected to book in it
    # Review round: earlier quarters' assignments are created inside this quarter's
    # span too, so every total and benchmark comparison includes them
    earlier_assigned: Decimal = ZERO
    # the quarter's bookings when every quarter's schedule is created together
    full_bookings: Decimal | None = None

    @property
    def total_in_span(self) -> Decimal | None:
        """Everything created in the span: what the forward function expects, what
        earlier quarters were assigned and this quarter's own requirement."""
        if self.required is None:
            return None
        return self.expected_created + self.earlier_assigned + self.required

    @property
    def span_days(self) -> int:
        return (self.piece[1] - self.piece[0]).days

    @property
    def surplus(self) -> Decimal | None:
        return None if self.full_bookings is None else self.full_bookings - self.target


def _status(window: Window, as_of: date) -> str:
    if window.end <= as_of:
        return "closed"
    return "not started" if window.start >= as_of else "in progress"


def solve_quarters(
    model: Model,
    data: Dataset,
    as_of: date,
    windows: list[Window],
    targets: Mapping[str, tuple[Window, Decimal]],
    actual: Mapping[str, Decimal],
    creation: Creation | None,
    cap: Decimal,
    ramped: tuple[Decimal, ...] = (),
) -> list[QuarterResult]:
    """``targets`` maps a quarter to its window and bookings target, in
    chronological order; ``actual`` its bookings to date."""
    out: list[QuarterResult] = []
    month_labels: list[list[str]] = []
    assigned: list[Inflow] = []
    spent = ZERO
    new = model.new_pipeline
    open_arr = sum(
        (d.arr for d in data.deals if not d.is_closed and d.stage != UNKNOWN_STAGE),
        ZERO,
    )
    for quarter, (qw, target) in targets.items():
        status = _status(qw, as_of)
        if status == "closed":
            continue
        labels = [w.label for w in windows if qw.contains(w.end)]
        done = actual.get(quarter, ZERO)
        room = cap - spent
        forward = _bookings(
            model, data, as_of, windows, creation, tuple(assigned), qw.end, labels, done
        )
        solved = solve_added_pipeline(forward, target, room)
        mine = (
            schedule(as_of, qw.end, solved.required)
            if solved.outcome == FEASIBLE
            else ()
        )
        amount = solved.required if solved.outcome == FEASIBLE else ZERO
        first, last = 0, (qw.end - as_of).days
        earlier = model_forecast(
            model, data, as_of, windows, creation=creation, inflows=tuple(assigned)
        )
        per_day = (
            creation.per_day[first:last]
            if creation is not None
            else (new.created_per_day,) * (last - first)
        )
        out.append(
            QuarterResult(
                quarter, status, target, done, solved.outcome,
                solved.required if solved.outcome != COVERED else ZERO, amount, room,
                solved.base, solved.achieved if solved.outcome == FEASIBLE else solved.base,
                (as_of, qw.end), mine,
                sum(per_day, ZERO) * new.mean_created_arr,
                sum(ramped[first:last], ZERO) if ramped else None,
                yield_per_dollar(model, data, as_of, windows, qw.end, labels),
                open_arr,
                sum((earlier.components[EXISTING][m] for m in labels), ZERO),
                spent,
            )
        )  # fmt: skip
        assigned.extend(mine)
        month_labels.append(labels)
        spent += amount
    return _complete(out, month_labels, model, data, as_of, windows, creation)


def _complete(out, month_labels, model, data, as_of, windows, creation):
    """Each quarter's bookings, and so its surplus over target, when every quarter's
    schedule is created together (the solve itself stays sequential)."""
    if not out:
        return out
    f = model_forecast(
        model, data, as_of, windows, creation=creation,
        inflows=tuple(i for r in out for i in r.inflows),
    )  # fmt: skip
    return [
        replace(r, full_bookings=r.actual + sum((f.window_total(m) for m in ls), ZERO))
        for r, ls in zip(out, month_labels)
    ]


def schedule(as_of: date, end: date, amount: Decimal) -> tuple[Inflow, ...]:
    """``amount`` created evenly on every day after ``as_of`` through ``end``."""
    return (Inflow(0, (end - as_of).days, amount),) if amount else ()


def _bookings(model, data, as_of, windows, creation, assigned, end, labels, done):
    """The quarter's bookings as a function of the pipeline added on its own
    schedule, after what earlier quarters were assigned."""

    def forward(added: Decimal) -> Decimal:
        f = model_forecast(
            model, data, as_of, windows, creation=creation,
            inflows=(*assigned, *schedule(as_of, end, added)),
        )  # fmt: skip
        return done + sum((f.window_total(m) for m in labels), ZERO)

    return forward


PROBE = Decimal(10**6)


def yield_per_dollar(model, data, as_of, windows, end, labels) -> Decimal:
    """Of a dollar created evenly from the as-of date to ``end``, the share that
    books inside the quarter whose month windows are ``labels``. The forward
    function is linear in added pipeline, so one probe dollar-amount is exact."""
    f = model_forecast(model, data, as_of, windows, inflows=schedule(as_of, end, PROBE))
    return sum((f.components[ADDED][m] for m in labels), ZERO) / PROBE


# ------------------------------------------------- too late, and the open pipeline


class Reason(NamedTuple):
    code: str  # over_cap, cap_used_up, no_yield, total_rate or per_rep
    text: str


def per_rep_excess(r: QuarterResult, best_per_ae: Decimal | None) -> Decimal | None:
    """The requirement per ramped AE-month when it is above the team's best, else
    None. Whether it decides is the caller's rule; it is always worth showing."""
    total, months = r.total_in_span, r.ramped_ae_months
    if total is None or not months or best_per_ae is None:
        return None
    per = total / months
    return per if per > best_per_ae else None


def too_late(
    r: QuarterResult,
    best_per_ae: Decimal | None,
    best_per_day: Decimal | None,
    per_rep_applies: bool,
) -> tuple[Reason, ...]:
    """The legs that make a quarter too late to fund with new pipeline, each named;
    empty when none fires. A covered quarter asks nothing, so it is never too late.

    - the cap: the requirement is over the cap, or what is left of the cap is none
      (earlier quarters used it up), or nothing created in time books inside the
      quarter (told apart by the yield, a probe that does not depend on the cap);
    - the total rate: everything created in the span (expected, earlier assignments
      and this requirement) per day, above the team's best four-quarter average of
      total created pipeline per day (observed, no roster needed);
    - per ramped AE-month, above the team's best, only where capacity is the
      forecast's basis; elsewhere it is a diagnostic and decides nothing.
    The per-ramped-AE-month totals include earlier assignments, as every total does."""
    if r.outcome == COVERED:
        return ()
    out: list[Reason] = []
    if r.outcome == UNREACHABLE:
        if r.required is not None:
            out.append(Reason("over_cap", "the requirement is over the cap"))
        elif r.yield_per_dollar > 0:
            out.append(
                Reason(
                    "cap_used_up",
                    "earlier quarters' assignments used up the cap, although pipeline "
                    f"created now books {r.yield_per_dollar * 100:.2f} cents of each "
                    "dollar inside it",
                )
            )
        else:
            out.append(
                Reason("no_yield", "no pipeline created in time books inside it")
            )
    total = r.total_in_span
    if total is not None and best_per_day is not None and r.span_days > 0:
        per_day = total / r.span_days
        if per_day > best_per_day:
            out.append(
                Reason(
                    "total_rate",
                    f"needs ${per_day:,.2f} of pipeline created a day in total, above the "
                    f"team's best four-quarter average of ${best_per_day:,.2f} a day",
                )
            )
    if per_rep_applies:
        per = per_rep_excess(r, best_per_ae)
        if per is not None:
            out.append(
                Reason(
                    "per_rep",
                    f"needs ${per:,.0f} per ramped AE-month, above the team's best "
                    f"four-quarter average of ${best_per_ae:,.0f}",
                )
            )
    return tuple(out)


@dataclass(frozen=True)
class OpenPipelineClose:
    """What the pipeline already open would have to book inside the quarter to close
    it: plain arithmetic on figures the report already holds, not a solved lever."""

    expected: Decimal  # the open pipeline's expected contribution to the quarter
    needed: Decimal  # ... and what it would have to contribute for the quarter to close
    open_arr: Decimal
    expected_share: Decimal | None  # expected / open ARR
    needed_share: (
        Decimal | None
    )  # needed / open ARR: the implied win rate, in the quarter
    possible: bool  # needed is no more than the whole open pipeline


def close_with_open_pipeline(r: QuarterResult) -> OpenPipelineClose:
    needed = r.open_expected + (r.target - r.forecast_without)
    share = (lambda x: x / r.open_arr) if r.open_arr else (lambda x: None)
    return OpenPipelineClose(
        r.open_expected, needed, r.open_arr, share(r.open_expected), share(needed),
        bool(r.open_arr) and needed <= r.open_arr,
    )  # fmt: skip


# ------------------------------------------------- the lead-time table


@dataclass(frozen=True)
class LeadTimes:
    """Of a dollar of pipeline created next month (at its first recorded amount), the
    dollars booked in each of the next four quarters and after them. These are
    dollar yields, not probabilities: amounts change between creation and win, so
    they can exceed or fall short of what the deal counts imply. The count outcome,
    of the deals created, is separate and does sum to one."""

    created_between: tuple[date, date]
    booked: tuple[tuple[str, Decimal], ...]  # booked inside each quarter
    cumulative: tuple[tuple[str, Decimal], ...]  # booked by the end of each quarter
    later: Decimal  # booked after the last of the four
    win_share: Decimal  # of deals created, expected to win within the horizon
    not_win_share: Decimal  # ... and not


def next_quarters(
    fy: FiscalYear, as_of: date, count: int = 4
) -> list[tuple[str, Window]]:
    """The next ``count`` fiscal quarters that end after the as-of date."""
    out: list[tuple[str, Window]] = []
    for year in (fy, fy.next, fy.next.next):
        for key in year.quarter_keys:
            w = year.quarter_window(key)
            if w.end > as_of and len(out) < count:
                out.append((key, w))
    return out


def lead_windows(model: Model, as_of: date, quarters: list[tuple[str, Window]]):
    """The month windows long enough for every close the timing curve allows, and
    the first and last day (as dates) of the next calendar month."""
    first = month_end(as_of)
    last = month_end(first + timedelta(days=1))
    reach = max(quarters[-1][1].end, last + timedelta(days=model.params.horizon_days))
    return month_windows(as_of, reach), first, last


def lead_times(
    model: Model, data: Dataset, as_of: date, quarters: list[tuple[str, Window]]
) -> LeadTimes:
    """From the production forward function: one probe amount created evenly through
    the next calendar month, the bookings that come from it window by window, over
    a horizon long enough for every close the timing curve allows."""
    windows, first, last = lead_windows(model, as_of, quarters)
    f = model_forecast(
        model, data, as_of, windows,
        inflows=(Inflow((first - as_of).days, (last - as_of).days, PROBE),),
    )  # fmt: skip
    got = {w.label: f.components[ADDED][w.label] / PROBE for w in windows}
    booked = tuple(
        (k, sum((got[w.label] for w in windows if qw.contains(w.end)), ZERO))
        for k, qw in quarters
    )
    through = sum(booked_ for _, booked_ in booked)
    later = sum(got.values(), ZERO) - through
    running, cumulative = ZERO, []
    for k, v in booked:
        running += v
        cumulative.append((k, running))
    win = model.new_pipeline.win_rate
    return LeadTimes((first, last), booked, tuple(cumulative), later, win, 1 - win)


# ------------------------------------------------- the team's own history


@dataclass(frozen=True)
class History:
    quarters: int
    median: Decimal | None  # created dollars per ramped AE-month, across quarters
    best_four: Decimal | None  # the best average over four consecutive quarters
    best_four_per_day: Decimal | None = None  # total created per day, same rule


def summarize_history(quarters: list[tuple[Decimal, Decimal]]) -> History:
    """From (created dollars, ramped AE-months) per complete fiscal quarter, oldest first."""
    usable = [(c, m) for c, m in quarters if m > 0]
    if not usable:
        return History(0, None, None)
    med = Decimal(str(median(c / m for c, m in usable)))
    best = None
    for i in range(len(usable) - 3):
        block = usable[i : i + 4]
        value = sum((c for c, _ in block), ZERO) / sum((m for _, m in block), ZERO)
        best = value if best is None or value > best else best
    return History(len(usable), med, best)


def best_four_per_day(quarters: list[tuple[Decimal, int]]) -> Decimal | None:
    """From (created dollars, days) per complete fiscal quarter, oldest first: the best
    total created pipeline per day over four consecutive quarters. Observed; needs no
    roster. None with fewer than four quarters."""
    best = None
    for i in range(len(quarters) - 3):
        block = quarters[i : i + 4]
        value = sum((c for c, _ in block), ZERO) / sum(d for _, d in block)
        best = value if best is None or value > best else best
    return best

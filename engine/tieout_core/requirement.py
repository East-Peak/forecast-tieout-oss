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
was not shown to explain pipeline, the per-rep comparison stays a labelled
diagnostic (as in 2B), because a ceiling derived from headcount would rest on a
relationship this history did not support; the cap leg then decides alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

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
            )
        )  # fmt: skip
        assigned.extend(mine)
        spent += amount
    return out


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


def too_late(
    r: QuarterResult, best_four: Decimal | None, per_rep_applies: bool
) -> tuple[str, ...]:
    """The reasons a quarter is too late to fund with new pipeline; empty when it is
    not. A covered quarter asks nothing, so it is never too late. The per-rep leg
    needs the rule to apply (capacity adopted), a best four-quarter average on
    record and a positive expected ramped AE-months in the quarter's piece."""
    if r.outcome == COVERED:
        return ()
    reasons: list[str] = []
    if r.outcome == UNREACHABLE:
        reasons.append(
            "no pipeline created in time books inside it"
            if r.required is None
            else "over the cap"
        )
    months = r.ramped_ae_months
    if per_rep_applies and best_four is not None and months and r.required is not None:
        per = (r.expected_created + r.required) / months
        if per > best_four:
            reasons.append(
                f"needs ${per:,.0f} per ramped AE-month, above the team's best "
                f"four-quarter average of ${best_four:,.0f}"
            )
    return tuple(reasons)


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
    """Of a dollar of pipeline created next month, the share booked in each of the
    next four quarters, after them, and never (lost, or never closing)."""

    created_between: tuple[date, date]
    booked: tuple[tuple[str, Decimal], ...]  # booked inside each quarter
    cumulative: tuple[tuple[str, Decimal], ...]  # booked by the end of each quarter
    later: Decimal  # booked after the last of the four
    never: Decimal  # the rest: 1 less everything the forward function books


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


def lead_times(
    model: Model, data: Dataset, as_of: date, quarters: list[tuple[str, Window]]
) -> LeadTimes:
    """From the production forward function: one probe amount created evenly through
    the next calendar month, the bookings that come from it window by window, over
    a horizon long enough for every close the timing curve allows."""
    first = month_end(as_of)
    last = month_end(first + timedelta(days=1))
    reach = max(quarters[-1][1].end, last + timedelta(days=model.params.horizon_days))
    windows = month_windows(as_of, reach)
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
    return LeadTimes(
        (first, last), booked, tuple(cumulative), later, 1 - through - later
    )


# ------------------------------------------------- the team's own history


@dataclass(frozen=True)
class History:
    quarters: int
    median: Decimal | None  # created dollars per ramped AE-month, across quarters
    best_four: Decimal | None  # the best average over four consecutive quarters


def summarise_history(quarters: list[tuple[Decimal, Decimal]]) -> History:
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

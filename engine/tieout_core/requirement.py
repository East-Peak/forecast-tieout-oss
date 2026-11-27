"""Required against expected pipeline, by quarter (section 10).

One deterministic solve in quarter order. For each remaining quarter with a
target, the extra pipeline that must be created, spread evenly over the month
windows from the as-of date (or the previous quarter's end) to that quarter's
end, so that the quarter's bookings meet its target given its actuals, the
pipeline already open and what earlier quarters were assigned. Each quarter is
covered, needs $X, or is unreachable within the cap; an unreachable quarter is
assigned nothing and the next is solved from there. The cap is one cap across
the quarters: what is left of it after earlier assignments.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median

from .fiscal import Window
from .fit import Model
from .forecast import Creation, Inflow, model_forecast
from .lever import COVERED, FEASIBLE, solve_added_pipeline
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
    piece: tuple[date, date]  # (start, end]: where its pipeline is created
    inflows: tuple[Inflow, ...]
    expected_created: (
        Decimal  # dollars the forward function expects created in the piece
    )
    ramped_ae_months: Decimal | None  # expected ramped AE-months in the piece


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
    previous_end = as_of
    new = model.new_pipeline
    for quarter, (qw, target) in targets.items():
        status = _status(qw, as_of)
        if status == "closed":
            continue
        start = max(as_of, previous_end)
        previous_end = qw.end
        piece = [w for w in windows if start <= w.start and w.end <= qw.end]
        labels = [w.label for w in windows if qw.contains(w.end)]
        done = actual.get(quarter, ZERO)
        room = cap - spent
        forward = _bookings(
            model, data, as_of, windows, creation, tuple(assigned), piece, labels, done
        )
        solved = solve_added_pipeline(forward, target, room)
        mine = (
            spread_over(piece, as_of, solved.required)
            if solved.outcome == FEASIBLE
            else ()
        )
        amount = solved.required if solved.outcome == FEASIBLE else ZERO
        first, last = (start - as_of).days, (qw.end - as_of).days
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
                (start, qw.end), mine,
                sum(per_day, ZERO) * new.mean_created_arr,
                sum(ramped[first:last], ZERO) if ramped else None,
            )
        )  # fmt: skip
        assigned.extend(mine)
        spent += amount
    return out


def spread_over(
    piece: list[Window], as_of: date, amount: Decimal
) -> tuple[Inflow, ...]:
    """``amount`` created in equal parts over the month windows of a piece."""
    return tuple(
        Inflow((w.start - as_of).days, (w.end - as_of).days, amount / len(piece))
        for w in piece
    )


def _bookings(model, data, as_of, windows, creation, assigned, piece, labels, done):
    """The quarter's bookings as a function of the pipeline added in its piece,
    after what earlier quarters were assigned."""

    def forward(added: Decimal) -> Decimal:
        extra = spread_over(piece, as_of, added) if piece else ()
        f = model_forecast(
            model, data, as_of, windows, creation=creation, inflows=(*assigned, *extra)
        )
        return done + sum((f.window_total(m) for m in labels), ZERO)

    return forward


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

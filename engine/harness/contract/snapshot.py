"""`Snapshot` and `DealObservations`: what the evidence package hands the planning model.

Both are frozen. Every array is copied on construction and write-protected.
Measured money is integer cents. A `Measure` pairs values with a boolean
`missing` mask; missing cells hold 0 so equality is well defined.

Axes: `lane` (a model-grain cell, see keys.lane_key), `team` (an AE team: the
pool of carrying capacity), `month` ("YYYY-MM", consecutive) and, for exits,
`reason`. Flows are by lane and month. Open stock and queue stock are by lane
too, so a team's stock is the sum over its lanes (`Snapshot.by_team`).

The two stock-and-flow identities of the design hold per lane and month:

    open_start + admissions - wins - losses = open_end
    queue_start + arrivals = admissions + sum(exits) + queue_end

and the capacity inequality holds per team and month, on lane sums:

    admissions <= carrying_capacity - open_start + wins + losses

`flow_violations` also checks continuity (next start equals this end). Cells
with any missing input are skipped, never failed.
"""

import itertools
import re
from dataclasses import dataclass

import numpy as np

AXES = ("lane", "month")
TEAM_AXES = ("team", "month")

OPEN, WON, LOST = 0, 1, 2  # outcome codes in DealObservations
REOPENED_POLICY = "latest_outcome"  # a reopened deal takes its final closed outcome; flagged in `reopened`
MISSING_FIRST_STAGE_POLICY = (
    "unknown_until_first_transition"  # no stage is imputed before the first transition
)


def _frozen(array: np.ndarray) -> np.ndarray:
    array = np.array(array, copy=True)
    array.setflags(write=False)
    return array


@dataclass(frozen=True, eq=False)
class Measure:
    axes: tuple[str, ...]
    values: np.ndarray
    missing: np.ndarray | None = None  # None means nothing is missing

    def __post_init__(self):
        values = np.asarray(self.values)
        if values.ndim != len(self.axes):
            raise ValueError(
                f"axes {self.axes} need {len(self.axes)} dimensions, got {values.ndim}"
            )
        missing = (
            np.zeros(values.shape, dtype=bool)
            if self.missing is None
            else np.asarray(self.missing, dtype=bool)
        )
        if missing.shape != values.shape:
            raise ValueError(
                f"mask shape {missing.shape} differs from values shape {values.shape}"
            )
        if np.any(values[missing] != 0):
            raise ValueError("missing cells must hold zero")
        object.__setattr__(self, "values", _frozen(values))
        object.__setattr__(self, "missing", _frozen(missing))

    @property
    def shape(self):
        return self.values.shape


@dataclass(frozen=True)
class PendingRequisition:
    req_id: str
    team: str
    role: str
    planned_start: str  # YYYY-MM-DD


# name -> (axes, kind) for every Measure field of Snapshot; kind is "int" or "float".
_MEASURES: dict[str, tuple[tuple[str, ...], str]] = {
    "leads": (AXES, "int"),
    "mqls": (AXES, "int"),
    "arrivals": (AXES, "int"),  # demand episodes offered to sales
    "queue_start": (AXES, "int"),
    "admissions": (AXES, "int"),
    "exits": (("lane", "month", "reason"), "int"),
    "queue_end": (AXES, "int"),
    "opportunities_created": (AXES, "int"),
    "open_start": (AXES, "int"),
    "wins": (AXES, "int"),
    "losses": (AXES, "int"),
    "open_end": (AXES, "int"),
    "bookings_cents": (AXES, "int"),
    "spend_cents": (AXES, "int"),
    "heads": (TEAM_AXES, "int"),  # AEs on the roster
    "ramped_heads": (TEAM_AXES, "int"),  # AEs counted at full carrying capacity
    "ramp_exposure": (
        TEAM_AXES,
        "float",
    ),  # ramp-weighted person-months, for sourcing ramp
    "carrying_capacity": (
        TEAM_AXES,
        "int",
    ),  # ramped_heads times the ceiling, in open deals
}

_MONTH = re.compile(r"(\d{4})-(\d{2})")


def _month_index(label: str) -> int:
    found = _MONTH.fullmatch(label)
    if not found or not 1 <= int(found[2]) <= 12:
        raise ValueError(f"month label {label!r} is not YYYY-MM")
    return int(found[1]) * 12 + int(found[2]) - 1


@dataclass(frozen=True, eq=False)
class Snapshot:
    lanes: tuple[str, ...]
    teams: tuple[str, ...]
    months: tuple[str, ...]
    exit_reasons: tuple[str, ...]
    lane_team: tuple[str, ...]  # the team that sells each lane
    leads: Measure
    mqls: Measure
    arrivals: Measure
    queue_start: Measure
    admissions: Measure
    exits: Measure
    queue_end: Measure
    opportunities_created: Measure
    open_start: Measure
    wins: Measure
    losses: Measure
    open_end: Measure
    bookings_cents: Measure
    spend_cents: Measure
    heads: Measure
    ramped_heads: Measure
    ramp_exposure: Measure
    carrying_capacity: Measure
    pending_requisitions: tuple[PendingRequisition, ...] = ()

    def __post_init__(self):
        for name, labels in (
            ("lane", self.lanes),
            ("team", self.teams),
            ("month", self.months),
        ):
            if len(set(labels)) != len(labels):
                raise ValueError(f"duplicate {name} label")
        idx = [_month_index(m) for m in self.months]
        if any(b - a != 1 for a, b in itertools.pairwise(idx)):
            raise ValueError("months must be consecutive")
        if len(self.lane_team) != len(self.lanes) or not set(self.lane_team) <= set(
            self.teams
        ):
            raise ValueError("lane_team must name one known team per lane")
        sizes = {
            "lane": len(self.lanes),
            "team": len(self.teams),
            "month": len(self.months),
            "reason": len(self.exit_reasons),
        }
        for name, (axes, kind) in _MEASURES.items():
            meas = getattr(self, name)
            if meas.axes != axes:
                raise ValueError(f"{name}: axes {meas.axes} should be {axes}")
            want = tuple(sizes[a] for a in axes)
            if meas.shape != want:
                raise ValueError(f"{name}: shape {meas.shape} should be {want}")
            dtype_kind = meas.values.dtype.kind
            if kind == "int" and dtype_kind not in "iu":
                raise ValueError(f"{name}: expected an integer array")
            if kind == "float" and dtype_kind != "f":
                raise ValueError(f"{name}: expected a float array")
            if np.any(meas.values < 0):
                raise ValueError(f"{name}: negative values")
        if np.any(self.ramped_heads.values > self.heads.values):
            raise ValueError("ramped_heads exceeds heads")
        for req in self.pending_requisitions:
            if req.team not in self.teams:
                raise ValueError(
                    f"requisition {req.req_id}: team {req.team!r} is not a snapshot team"
                )
        object.__setattr__(
            self, "pending_requisitions", tuple(self.pending_requisitions)
        )

    def by_team(self, measure: Measure) -> Measure:
        """Sum a (lane, month) measure over each team's lanes; missing if any lane is missing."""
        if measure.axes != AXES:
            raise ValueError("by_team needs a (lane, month) measure")
        values = np.zeros(
            (len(self.teams), len(self.months)), dtype=measure.values.dtype
        )
        missing = np.zeros(values.shape, dtype=bool)
        for lane, team in enumerate(self.lane_team):
            t = self.teams.index(team)
            values[t] += measure.values[lane]
            missing[t] |= measure.missing[lane]
        values[missing] = 0
        return Measure(TEAM_AXES, values, missing)


def _cells(measures, *index):
    """The values of `measures` at `index`, or None if any of them is missing there."""
    if any(x.missing[index] for x in measures):
        return None
    return [int(x.values[index]) for x in measures]


def flow_violations(s: Snapshot) -> list[str]:
    """Every place the stock-and-flow identities or the capacity inequality fail."""
    problems = []
    exits_total = Measure(AXES, s.exits.values.sum(axis=2), s.exits.missing.any(axis=2))
    for lane, name in enumerate(s.lanes):
        for m, month in enumerate(s.months):
            where = f"{name} {month}"
            got = _cells(
                (s.open_start, s.admissions, s.wins, s.losses, s.open_end), lane, m
            )
            if got and got[0] + got[1] - got[2] - got[3] != got[4]:
                problems.append(
                    f"{where}: open_start + admissions - wins - losses = "
                    f"{got[0] + got[1] - got[2] - got[3]} but open_end = {got[4]}"
                )
            got = _cells(
                (s.queue_start, s.arrivals, s.admissions, exits_total, s.queue_end),
                lane,
                m,
            )
            if got and got[0] + got[1] != got[2] + got[3] + got[4]:
                problems.append(
                    f"{where}: queue_start + arrivals = {got[0] + got[1]} but "
                    f"admissions + exits + queue_end = {got[2] + got[3] + got[4]}"
                )
            if m + 1 == len(s.months):
                continue
            for label, start, end in (
                ("open", s.open_start, s.open_end),
                ("queue", s.queue_start, s.queue_end),
            ):
                this_end, next_start = (
                    _cells((end,), lane, m),
                    _cells((start,), lane, m + 1),
                )
                if this_end and next_start and this_end != next_start:
                    problems.append(
                        f"{where}: {label} continuity: next month starts at "
                        f"{next_start[0]} but this month ends at {this_end[0]}"
                    )
    open_start, admissions, wins, losses = (
        s.by_team(x) for x in (s.open_start, s.admissions, s.wins, s.losses)
    )
    for t, team in enumerate(s.teams):
        for m, month in enumerate(s.months):
            got = _cells(
                (open_start, admissions, wins, losses, s.carrying_capacity), t, m
            )
            if not got:
                continue
            room = got[4] - got[0] + got[2] + got[3]
            if got[1] > room:
                problems.append(
                    f"{team} {month}: admissions {got[1]} exceed capacity room {room} "
                    "(carrying_capacity - open_start + wins + losses)"
                )
    return problems


# ---- DealObservations --------------------------------------------------


def _check_aligned(obs, names, length):
    for name in names:
        if len(getattr(obs, name)) != length:
            raise ValueError(
                f"{name}: length {len(getattr(obs, name))} should be {length}"
            )


_DEAL_ARRAYS = (
    "deal_ids",
    "lane",
    "created",
    "outcome",
    "outcome_date",
    "reopened",
    "observed_from",
    "observed_to",
    "stage_history_complete",
    "transition_deal",
    "transition_stage",
    "transition_date",
    "amount_deal",
    "amount_date",
    "amount_cents",
)


@dataclass(frozen=True, eq=False)
class DealObservations:
    """Per-deal history in columnar form: what the competing-risk fit consumes.

    One row per deal in the deal arrays; stage transitions and amount points
    are long tables keyed by deal row index, sorted by (deal, date). `lane` is
    the deal's lane at its attribute time. The coverage columns say over which
    dates the deal's history was observed and whether stage transitions cover
    its whole life; the fit scores a deal only inside that window. Deal age
    and age in stage are derived from `created` and the transition dates.
    """

    lanes: tuple[str, ...]
    stages: tuple[str, ...]
    deal_ids: np.ndarray
    lane: np.ndarray
    created: np.ndarray  # datetime64[D]
    outcome: np.ndarray  # OPEN, WON or LOST
    outcome_date: np.ndarray  # datetime64[D]; NaT while open
    reopened: np.ndarray
    observed_from: np.ndarray
    observed_to: np.ndarray
    stage_history_complete: np.ndarray
    transition_deal: np.ndarray
    transition_stage: np.ndarray
    transition_date: np.ndarray
    amount_deal: np.ndarray
    amount_date: np.ndarray
    amount_cents: np.ndarray
    reopened_policy: str = REOPENED_POLICY
    missing_first_stage_policy: str = MISSING_FIRST_STAGE_POLICY

    def __post_init__(self):
        if (self.reopened_policy, self.missing_first_stage_policy) != (
            REOPENED_POLICY,
            MISSING_FIRST_STAGE_POLICY,
        ):
            raise ValueError("unsupported reopened or missing-first-stage policy")
        for name in _DEAL_ARRAYS:
            object.__setattr__(self, name, _frozen(getattr(self, name)))
        n = len(self.deal_ids)
        _check_aligned(
            self,
            [
                "lane",
                "created",
                "outcome",
                "outcome_date",
                "reopened",
                "observed_from",
                "observed_to",
                "stage_history_complete",
            ],
            n,
        )
        _check_aligned(
            self, ("transition_stage", "transition_date"), len(self.transition_deal)
        )
        _check_aligned(self, ("amount_date", "amount_cents"), len(self.amount_deal))
        if len(set(self.deal_ids.tolist())) != n:
            raise ValueError("duplicate deal id")
        if n and (self.lane.min() < 0 or self.lane.max() >= len(self.lanes)):
            raise ValueError("lane index out of range")
        if not np.isin(self.outcome, (OPEN, WON, LOST)).all():
            raise ValueError("outcome code must be OPEN, WON or LOST")
        for i in range(n):
            deal, closed = self.deal_ids[i], self.outcome[i] != OPEN
            if closed and np.isnat(self.outcome_date[i]):
                raise ValueError(f"closed deal {deal} has no outcome date")
            if not closed and not np.isnat(self.outcome_date[i]):
                raise ValueError(f"open deal {deal} has an outcome date")
            if closed and self.outcome_date[i] < self.created[i]:
                raise ValueError(f"deal {deal}: outcome before creation")
            if self.observed_to[i] < self.observed_from[i]:
                raise ValueError(f"deal {deal}: observed_to is before observed_from")
        self._check_long(self.transition_deal, self.transition_date, n, "transition")
        self._check_long(self.amount_deal, self.amount_date, n, "amount")
        if len(self.transition_stage) and (
            self.transition_stage.min() < 0
            or self.transition_stage.max() >= len(self.stages)
        ):
            raise ValueError("stage index out of range")
        if len(self.amount_cents) and self.amount_cents.min() < 0:
            raise ValueError("amount_cents must not be negative")
        before = (
            self.transition_date < self.created[self.transition_deal]
            if len(self.transition_deal)
            else []
        )
        if np.any(before):
            raise ValueError("a transition precedes its deal's creation")

    @staticmethod
    def _check_long(deal, date, n, label):
        if len(deal) == 0:
            return
        if deal.min() < 0 or deal.max() >= n:
            raise ValueError(f"{label} deal index out of range")
        order = np.lexsort((date, deal))
        if not np.array_equal(order, np.arange(len(deal))):
            raise ValueError(f"{label} rows must be sorted by deal then date")

    @property
    def n_deals(self) -> int:
        return len(self.deal_ids)

    def transitions(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """(stage indexes, dates) of deal row `i`, in date order."""
        rows = self.transition_deal == i
        return self.transition_stage[rows], self.transition_date[rows]

    def amounts(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """(dates, amounts in cents) of deal row `i`, in date order."""
        rows = self.amount_deal == i
        return self.amount_date[rows], self.amount_cents[rows]

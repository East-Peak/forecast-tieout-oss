"""`Snapshot` and `DealObservations`: what the evidence package hands the planning model.

Both are frozen. Every array is copied on construction and write-protected.
Measured money is integer cents. A `Measure` pairs values with a boolean
`missing` mask (missing cells hold 0, so equality is well defined) and a
`bound`: `exact`, or `lower_bound` where the estate cannot see all demand.
Identity checks never treat a lower bound as exact.

Axes: `lane` (a model-grain cell, see keys.lane_key), `team` (an AE team: the
pool of carrying capacity), `person`, `month` ("YYYY-MM", consecutive) and, for
exits, `reason`. Flows are by lane and month. Open stock and queue stock are by
lane too, so a team's stock is the sum over its lanes (`Snapshot.by_team`).
The team arrays (`heads`, `ramped_heads`, `ramp_exposure`, `carrying_capacity`)
are derived conveniences; `roster` and `sourced_by_person` are the evidence
that ramp, attrition, BDR output and AE self-sourcing are fitted from.

The stock-and-flow identities hold per lane and month:

    open_start + admissions + reopened - wins - losses - deleted = open_end
    queue_start + arrivals = admissions + sum(exits) + queue_end

A reopened deal re-enters the open stock (it starts a new selling spell, see
DealObservations) and takes a slot. A deleted deal leaves the stock without
being won or lost. The capacity inequality holds per team and month, on lane sums:

    admissions + reopened <= max(0, carrying_capacity - open_start + wins + losses + deleted)

The check constrains admissions, not the stock: after a departure a team may sit above
capacity (inherited deals) while it admits nothing.

`flow_check` also checks continuity (next start equals this end) and returns
how many cells it checked, which failed, and which could not be checked and why.
`outstanding_episodes` lists the demand episodes unresolved at the last month;
its per-lane count equals `queue_end` there.
"""

import re
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np

from .schema import parse_date, parse_datetime

AXES = ("lane", "month")
TEAM_AXES = ("team", "month")
BOUNDS = ("exact", "lower_bound")
ROLES = ("AE", "BDR", "Marketing", "Manager")


def _frozen(array: np.ndarray) -> np.ndarray:
    array = np.array(array, copy=True)
    array.setflags(write=False)
    return array


@dataclass(frozen=True, eq=False)
class Measure:
    axes: tuple[str, ...]
    values: np.ndarray
    missing: np.ndarray | None = None  # None means nothing is missing
    bound: str = "exact"

    def __post_init__(self):
        if self.bound not in BOUNDS:
            raise ValueError(f"bound must be one of {BOUNDS}, not {self.bound!r}")
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
    planned_start: str  # YYYY-MM-DD; an AE requisition names an AE team of the snapshot, others any team


@dataclass(frozen=True)
class RosterObservation:
    """One observation of a person's assignment, with when it holds and when it was learned."""

    person_id: str
    role: str
    team: str
    segment: str | None
    start_date: str
    end_date: str | None
    planned_start: (
        str | None
    )  # where a requisition exists: planned start, so slip is start - planned
    effective_at: str  # ISO datetime: business time the observation is about
    recorded_at: str  # ISO datetime: when the system learned it


@dataclass(frozen=True)
class RosterObservations:
    rows: tuple[RosterObservation, ...]

    def __post_init__(self):
        for r in self.rows:
            if r.role not in ROLES:
                raise ValueError(
                    f"{r.person_id}: role {r.role!r} is not one of {ROLES}"
                )
            start = parse_date(r.start_date)
            if r.end_date is not None and parse_date(r.end_date) < start:
                raise ValueError(f"{r.person_id}: end_date is before start_date")
            if r.planned_start is not None:
                parse_date(r.planned_start)
            parse_datetime(r.effective_at)
            parse_datetime(r.recorded_at)

    def persons(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(r.person_id for r in self.rows))

    def latest(self, person_id: str, known_at: str) -> RosterObservation | None:
        """The person's observation as known at `known_at` (latest effective, then recorded)."""
        known = [
            r
            for r in self.rows
            if r.person_id == person_id and r.recorded_at <= known_at
        ]
        return max(known, key=lambda r: (r.effective_at, r.recorded_at), default=None)


@dataclass(frozen=True)
class OutstandingEpisode:
    """A demand episode unresolved at the last month (key lead_id, offer_seq)."""

    lane: str
    lead_id: str
    offer_seq: int
    offered_on: str  # YYYY-MM-DD
    age_months: int  # whole months from the offer month to the last snapshot month


# name -> (axes, kind) for every Measure field of Snapshot; kind is "int" or "float".
_MEASURES: dict[str, tuple[tuple[str, ...], str]] = {
    "leads": (AXES, "int"),
    "mqls": (AXES, "int"),
    "arrivals": (AXES, "int"),  # demand episodes offered to sales
    "queue_start": (AXES, "int"),
    "admissions": (AXES, "int"),
    "reopened": (AXES, "int"),  # deals re-entering the open stock (a new spell)
    "exits": (("lane", "month", "reason"), "int"),
    "queue_end": (AXES, "int"),
    "opportunities_created": (AXES, "int"),
    "open_start": (AXES, "int"),
    "wins": (AXES, "int"),
    "losses": (AXES, "int"),
    "deleted": (AXES, "int"),  # deals leaving the stock as censored, not lost
    "open_end": (AXES, "int"),
    "bookings_cents": (AXES, "int"),
    "spend_cents": (AXES, "int"),
    "sourced_by_person": (
        ("person", "month"),
        "int",
    ),  # opportunities each person sourced
    "bdr_exposure": (AXES, "float"),  # ramp-weighted BDR person-months behind each lane
    "heads": (TEAM_AXES, "int"),  # AEs on the roster
    "ramped_heads": (TEAM_AXES, "int"),  # AEs counted at full carrying capacity
    "ramp_exposure": (TEAM_AXES, "float"),  # AE ramp-weighted person-months
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
    persons: tuple[str, ...]  # people with sourcing counts (a subset of the roster)
    leads: Measure
    mqls: Measure
    arrivals: Measure
    queue_start: Measure
    admissions: Measure
    reopened: Measure
    exits: Measure
    queue_end: Measure
    opportunities_created: Measure
    open_start: Measure
    wins: Measure
    losses: Measure
    deleted: Measure
    open_end: Measure
    bookings_cents: Measure
    spend_cents: Measure
    sourced_by_person: Measure
    bdr_exposure: Measure
    heads: Measure
    ramped_heads: Measure
    ramp_exposure: Measure
    carrying_capacity: Measure
    roster: RosterObservations
    outstanding_episodes: tuple[OutstandingEpisode, ...]
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
        if any(b - a != 1 for a, b in pairwise(idx)):
            raise ValueError("months must be consecutive")
        if len(self.lane_team) != len(self.lanes) or not set(self.lane_team) <= set(
            self.teams
        ):
            raise ValueError("lane_team must name one known team per lane")
        if not set(self.persons) <= set(self.roster.persons()):
            raise ValueError("persons must all appear in the roster")
        sizes = {
            "lane": len(self.lanes),
            "team": len(self.teams),
            "month": len(self.months),
            "reason": len(self.exit_reasons),
            "person": len(self.persons),
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
            if req.role == "AE" and req.team not in self.teams:
                raise ValueError(
                    f"requisition {req.req_id}: team {req.team!r} is not a snapshot team"
                )
        self._check_outstanding(idx[-1] if idx else 0)
        object.__setattr__(
            self, "pending_requisitions", tuple(self.pending_requisitions)
        )
        object.__setattr__(
            self, "outstanding_episodes", tuple(self.outstanding_episodes)
        )

    def _check_outstanding(self, last: int) -> None:
        per_lane = dict.fromkeys(self.lanes, 0)
        for ep in self.outstanding_episodes:
            if ep.lane not in per_lane:
                raise ValueError(
                    f"outstanding episode {ep.lead_id}: unknown lane {ep.lane!r}"
                )
            per_lane[ep.lane] += 1
            if (
                ep.age_months != last - _month_index(ep.offered_on[:7])
                or ep.age_months < 0
            ):
                raise ValueError(
                    f"outstanding episode {ep.lead_id}: age_months {ep.age_months} does not match its offer date"
                )
        queue = self.queue_end
        for i, lane in enumerate(self.lanes):
            if (
                queue.bound == "exact"
                and not queue.missing[i, -1]
                and per_lane[lane] != queue.values[i, -1]
            ):
                raise ValueError(
                    f"outstanding episodes for {lane}: {per_lane[lane]} but queue_end is {queue.values[i, -1]}"
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
        return Measure(TEAM_AXES, values, missing, measure.bound)


@dataclass
class FlowReport:
    """What `flow_check` found: cells checked, cells violated, cells it could not check."""

    checked: int = 0
    violations: list[str] = field(default_factory=list)
    unavailable: list[tuple[str, str]] = field(default_factory=list)  # (where, reason)

    @property
    def ok(self) -> bool:
        return not self.violations


def _read(*cells):
    """Values of (name, measure, index) cells, or (None, reason) if any is missing or a lower bound."""
    missing = [n for n, x, i in cells if x.missing[i]]
    lower = [n for n, x, _ in cells if x.bound == "lower_bound"]
    if missing or lower:
        reason = "; ".join(
            r
            for r in (
                f"missing: {', '.join(missing)}" if missing else "",
                f"lower_bound: {', '.join(lower)}" if lower else "",
            )
            if r
        )
        return None, reason
    return [int(x.values[i]) for _, x, i in cells], None


def _run(report: FlowReport, where: str, cells, broken) -> None:
    got, why = _read(*cells)
    if got is None:
        report.unavailable.append((where, why))
        return
    report.checked += 1
    problem = broken(got)
    if problem:
        report.violations.append(f"{where}: {problem}")


def flow_check(s: Snapshot) -> FlowReport:
    """Check both identities, continuity and the capacity inequality; skip what cannot be checked."""
    report = FlowReport()
    miss = s.exits.missing.any(axis=2)
    exits_total = Measure(
        AXES, np.where(miss, 0, s.exits.values.sum(axis=2)), miss, s.exits.bound
    )
    for lane, name in enumerate(s.lanes):
        for m, month in enumerate(s.months):
            at = (lane, m)
            where = f"{name} {month}"
            _run(
                report,
                f"{where} open identity",
                [
                    (n, getattr(s, n), at)
                    for n in (
                        "open_start",
                        "admissions",
                        "reopened",
                        "wins",
                        "losses",
                        "deleted",
                        "open_end",
                    )
                ],
                lambda v: (
                    f"open_start + admissions + reopened - wins - losses - deleted = {v[0] + v[1] + v[2] - v[3] - v[4] - v[5]} but open_end = {v[6]}"
                    if v[0] + v[1] + v[2] - v[3] - v[4] - v[5] != v[6]
                    else None
                ),
            )
            _run(
                report,
                f"{where} queue identity",
                [
                    ("queue_start", s.queue_start, at),
                    ("arrivals", s.arrivals, at),
                    ("admissions", s.admissions, at),
                    ("exits", exits_total, at),
                    ("queue_end", s.queue_end, at),
                ],
                lambda v: (
                    f"queue_start + arrivals = {v[0] + v[1]} but admissions + exits + queue_end = {v[2] + v[3] + v[4]}"
                    if v[0] + v[1] != v[2] + v[3] + v[4]
                    else None
                ),
            )
            if m + 1 == len(s.months):
                continue
            for label, start, end in (
                ("open", s.open_start, s.open_end),
                ("queue", s.queue_start, s.queue_end),
            ):
                _run(
                    report,
                    f"{where} {label} continuity",
                    [
                        (f"{label}_end", end, at),
                        (f"{label}_start", start, (lane, m + 1)),
                    ],
                    lambda v, label=label: (
                        f"{label} continuity: next month starts at {v[1]} but this month ends at {v[0]}"
                        if v[0] != v[1]
                        else None
                    ),
                )
    team = {
        n: s.by_team(getattr(s, n))
        for n in ("open_start", "admissions", "reopened", "wins", "losses", "deleted")
    }
    for t, name in enumerate(s.teams):
        for m, month in enumerate(s.months):
            at = (t, m)
            _run(
                report,
                f"{name} {month} capacity",
                [(n, x, at) for n, x in team.items()]
                + [("carrying_capacity", s.carrying_capacity, at)],
                lambda v: (
                    f"admissions + reopened {v[1] + v[2]} exceed capacity room {max(0, v[6] - v[0] + v[3] + v[4] + v[5])} (carrying_capacity - open_start + wins + losses + deleted)"
                    if v[1] + v[2] > max(0, v[6] - v[0] + v[3] + v[4] + v[5])
                    else None
                ),
            )
    return report


# ---- DealObservations --------------------------------------------------

OPEN, WON, LOST, DELETED = (
    0,
    1,
    2,
    3,
)  # spell outcomes; DELETED censors, it is not a loss
REOPEN_POLICY = (
    "selling_spells"  # a reopening ends nothing retroactively and starts spell n + 1
)
MISSING_FIRST_STAGE_POLICY = (
    "unknown_until_first_transition"  # no stage is imputed before the first transition
)

_DEAL_TABLES = {
    "deals": "deal_ids created observed_from observed_to stage_history_complete",
    "lane": "lane_deal lane_index lane_valid_from lane_recorded_at",
    "transition": "transition_deal transition_stage transition_effective transition_recorded",
    "amount": "amount_deal amount_cents amount_effective amount_recorded",
    "spell": "spell_deal spell_seq spell_start spell_end spell_outcome spell_close_date spell_end_recorded_at",
}


def _aligned(obs, table: str) -> int:
    names = _DEAL_TABLES[table].split()
    length = len(getattr(obs, names[0]))
    for name in names:
        if len(getattr(obs, name)) != length:
            raise ValueError(
                f"{name}: length {len(getattr(obs, name))} should be {length}"
            )
    return length


def _sorted_by_deal(deal, *then, label):
    order = np.lexsort((*reversed(then), deal))
    if not np.array_equal(order, np.arange(len(deal))):
        raise ValueError(f"{label} rows must be sorted by deal then time")


@dataclass(frozen=True, eq=False)
class DealObservations:
    """Per-deal history in columnar form: what the competing-risk fit consumes.

    Tables, each keyed by deal row index and sorted by (deal, time):
    lane history, stage transitions, amount history and selling spells.

    Two clocks on every history row. `*_effective` is business time; `*_recorded`
    is when the system learned it (recorded_at). A fit at a historical landmark L
    filters predictors (lane, stage, amount) to recorded_at <= L, so it sees only
    what was known then; labels may use later knowledge. Lane membership is a
    history (lane, valid_from, recorded_at), never one final lane.

    A selling spell has a stable deal id, a `spell_seq`, a start, an end and an
    outcome. Reopening a deal ends nothing retroactively: it starts spell n + 1.
    Which clock governs what:
    - win, loss and deleted labels use the observed closing transition time
      (`spell_end`, learned at `spell_end_recorded_at`);
    - bookings month uses the effective CloseDate of the spell (`spell_close_date`),
      which can differ from the observed end and be corrected later;
    - DELETED has no close date; its end is the first extract lacking the record
      (an upper bound) and it censors the deal, it is not a loss.
    Bookings adjustments are not spells. `observed_from`/`observed_to` say over
    which dates the deal's history was observed; the fit scores only inside it.
    """

    lanes: tuple[str, ...]
    stages: tuple[str, ...]
    deal_ids: np.ndarray
    created: np.ndarray  # datetime64[D]
    observed_from: np.ndarray
    observed_to: np.ndarray
    stage_history_complete: np.ndarray
    lane_deal: np.ndarray
    lane_index: np.ndarray
    lane_valid_from: np.ndarray  # datetime64[D]
    lane_recorded_at: np.ndarray  # datetime64[s]
    transition_deal: np.ndarray
    transition_stage: np.ndarray
    transition_effective: np.ndarray  # datetime64[s]
    transition_recorded: np.ndarray
    amount_deal: np.ndarray
    amount_cents: np.ndarray
    amount_effective: np.ndarray
    amount_recorded: np.ndarray
    spell_deal: np.ndarray
    spell_seq: np.ndarray  # 1, 2, ... within a deal
    spell_start: np.ndarray  # datetime64[D]
    spell_end: np.ndarray  # datetime64[D]; NaT while open
    spell_outcome: np.ndarray  # OPEN, WON, LOST or DELETED
    spell_close_date: np.ndarray  # datetime64[D]; NaT unless WON or LOST
    spell_end_recorded_at: np.ndarray  # datetime64[s]; NaT while open
    reopen_policy: str = REOPEN_POLICY
    missing_first_stage_policy: str = MISSING_FIRST_STAGE_POLICY

    def __post_init__(self):
        if (self.reopen_policy, self.missing_first_stage_policy) != (
            REOPEN_POLICY,
            MISSING_FIRST_STAGE_POLICY,
        ):
            raise ValueError("unsupported reopen or missing-first-stage policy")
        for names in _DEAL_TABLES.values():
            for name in names.split():
                object.__setattr__(self, name, _frozen(getattr(self, name)))
        n = _aligned(self, "deals")
        for table in ("lane", "transition", "amount", "spell"):
            _aligned(self, table)
        if len(set(self.deal_ids.tolist())) != n:
            raise ValueError("duplicate deal id")
        for i in range(n):
            if self.observed_to[i] < self.observed_from[i]:
                raise ValueError(
                    f"deal {self.deal_ids[i]}: observed_to is before observed_from"
                )
        self._check_long("lane", self.lane_deal, self.lane_valid_from, n)
        self._check_long(
            "transition", self.transition_deal, self.transition_effective, n
        )
        self._check_long("amount", self.amount_deal, self.amount_effective, n)
        for table, deal in (("lane", self.lane_deal), ("spell", self.spell_deal)):
            for i in sorted(set(range(n)) - set(deal.tolist())):
                raise ValueError(
                    f"deal {self.deal_ids[i]} has no {table} row"
                    if table == "lane"
                    else f"deal {self.deal_ids[i]} has no spell"
                )
        if len(self.lane_index) and (
            self.lane_index.min() < 0 or self.lane_index.max() >= len(self.lanes)
        ):
            raise ValueError("lane index out of range")
        if len(self.transition_stage) and (
            self.transition_stage.min() < 0
            or self.transition_stage.max() >= len(self.stages)
        ):
            raise ValueError("stage index out of range")
        if len(self.amount_cents) and self.amount_cents.min() < 0:
            raise ValueError("amount_cents must not be negative")
        before = (
            self.transition_effective.astype("datetime64[D]")
            < self.created[self.transition_deal]
        )
        if len(before) and before.any():
            raise ValueError("a transition precedes creation of its deal")
        self._check_spells(n)

    @staticmethod
    def _check_long(label, deal, when, n):
        if len(deal) == 0:
            return
        if deal.min() < 0 or deal.max() >= n:
            raise ValueError(f"{label} deal index out of range")
        _sorted_by_deal(deal, when, label=label)

    def _check_spells(self, n):
        _sorted_by_deal(self.spell_deal, self.spell_seq, label="spell")
        if not np.isin(self.spell_outcome, (OPEN, WON, LOST, DELETED)).all():
            raise ValueError("spell outcome code must be OPEN, WON, LOST or DELETED")
        previous_end = {}
        for r in range(len(self.spell_deal)):
            d, seq = int(self.spell_deal[r]), int(self.spell_seq[r])
            name = f"deal {self.deal_ids[d]} spell {seq}"
            if seq != previous_end.get(d, (0, None))[0] + 1:
                raise ValueError(f"{name}: spell_seq must run 1, 2, ... within a deal")
            if previous_end.get(d, (0, None))[1] is None and seq > 1:
                raise ValueError(f"{name}: an open spell must be the last")
            is_open = self.spell_outcome[r] == OPEN
            end = self.spell_end[r]
            if is_open != bool(np.isnat(end)):
                raise ValueError(
                    f"{name}: "
                    + (
                        "open spell has an end"
                        if is_open
                        else "closed spell has no end"
                    )
                )
            if np.isnat(self.spell_end_recorded_at[r]) != is_open:
                raise ValueError(
                    f"{name}: end recorded time must be set exactly when the spell is closed"
                )
            has_close = self.spell_outcome[r] in (WON, LOST)
            if has_close == bool(np.isnat(self.spell_close_date[r])):
                raise ValueError(
                    f"{name}: a WON or LOST spell needs a close date and no other spell has one"
                )
            start = self.spell_start[r]
            if start < self.created[d]:
                raise ValueError(
                    f"{name}: starts before its deal's creation (precedes creation)"
                )
            if not is_open and end < start:
                raise ValueError(f"{name}: ends before it starts")
            prev = previous_end.get(d, (0, None))[1]
            if seq > 1 and prev is not None and start < prev:
                raise ValueError(f"{name}: overlaps the previous spell")
            previous_end[d] = (seq, None if is_open else end)

    @property
    def n_deals(self) -> int:
        return len(self.deal_ids)

    def n_spells(self, i: int) -> int:
        return int((self.spell_deal == i).sum())

    def reopened(self, i: int) -> bool:
        return self.n_spells(i) > 1

    def spells(self, i: int) -> list[tuple]:
        """(seq, start, end, outcome, close_date) of each spell of deal row `i`."""
        rows = np.flatnonzero(self.spell_deal == i)
        return [
            (
                self.spell_seq[r],
                self.spell_start[r],
                self.spell_end[r],
                self.spell_outcome[r],
                self.spell_close_date[r],
            )
            for r in rows
        ]

    def transitions(self, i: int, known_at=None) -> tuple[np.ndarray, np.ndarray]:
        """(stage indexes, effective times) of deal row `i`, optionally only those recorded by `known_at`."""
        rows = self.transition_deal == i
        if known_at is not None:
            rows &= self.transition_recorded <= np.datetime64(known_at)
        return self.transition_stage[rows], self.transition_effective[rows]

    def amounts(self, i: int, known_at=None) -> tuple[np.ndarray, np.ndarray]:
        """(effective times, amounts in cents) of deal row `i`, optionally only those recorded by `known_at`."""
        rows = self.amount_deal == i
        if known_at is not None:
            rows &= self.amount_recorded <= np.datetime64(known_at)
        return self.amount_effective[rows], self.amount_cents[rows]

    def lane_at(self, i: int, on, known_at=None) -> int:
        """Lane index of deal row `i` on date `on`, as known at `known_at` (default: all knowledge)."""
        rows = (self.lane_deal == i) & (self.lane_valid_from <= np.datetime64(on, "D"))
        if known_at is not None:
            rows &= self.lane_recorded_at <= np.datetime64(known_at)
        chosen = np.flatnonzero(rows)
        return int(self.lane_index[chosen[-1]]) if len(chosen) else -1

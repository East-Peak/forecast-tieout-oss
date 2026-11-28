"""The roster: individual AEs, BDRs and support staff, and the requisitions behind the hires.

Each person's draws (ramp, skill, departure) come from their own stream keyed by
person id, so delaying one hire leaves everyone else's draws untouched.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from math import exp, log

from .params import CompanyParams, Intervention
from .rng import Streams

FIRST = (
    "Alex",
    "Bea",
    "Cal",
    "Dee",
    "Eli",
    "Fay",
    "Gus",
    "Hal",
    "Ivy",
    "Jo",
    "Kit",
    "Lou",
    "Max",
    "Ned",
    "Oli",
    "Pat",
    "Quin",
    "Rae",
    "Sam",
    "Tess",
)
LAST = ("Testwell", "Samplewood", "Mockridge", "Dummerton", "Fixtureman", "Placeholder")
TITLES = {
    "AE": "Account Executive",
    "BDR": "Business Development Rep",
    "Marketing": "Marketing Manager",
    "Manager": "Customer Success Manager",
}


def day_of(d: date) -> int:
    return d.toordinal()


@dataclass
class Person:
    idx: int
    pid: str  # people-system id
    uid: str  # Salesforce User id
    name: str
    email: str
    role: str
    team: str
    segment: str | None
    region: str
    req_id: str | None
    planned: int | None  # planned start day (requisition hires)
    start: int  # actual first day
    end: int | None  # last day employed (None while employed)
    ramp_days: int
    skill: float  # multiplier on win probability

    @property
    def leave_day(self) -> int:
        return (self.end + 1) if self.end is not None else 10**9

    def carry_factor(self, day: int, start: int, days: int) -> float:
        """Carrying ramp: the share of the ceiling this AE can hold, by days of tenure (0 until
        `start` days in, then linear over `days`; 0 when not employed). Separate from sourcing."""
        if day < self.start or day >= self.leave_day:
            return 0.0
        return min(1.0, max(0.0, (day - self.start - start) / days))

    def ramp_factor(self, day: int) -> float:
        """Sourcing ramp: 0 on the first day, 1 after `ramp_days`; 0 when not employed."""
        if day < self.start or day >= self.leave_day:
            return 0.0
        return min(1.0, (day - self.start) / self.ramp_days)


def build_people(
    params: CompanyParams,
    streams: Streams,
    intervention: Intervention,
    end_day: int,
    fork_day: int | None = None,
) -> list[Person]:
    people = []
    specs = [(s, None) for s in params.initial_staff] + [
        (s, f"REQ-{i + 1:03d}") for i, s in enumerate(params.hires)
    ]
    for idx, (spec, req_id) in enumerate(specs):
        if spec.cancelled:
            continue
        pid = f"P-{idx + 1:03d}"
        slip = spec.slip_days + (
            intervention.slip_hire[1]
            if intervention.slip_hire and intervention.slip_hire[0] == req_id
            else 0
        )
        planned = day_of(spec.planned_start)
        start = planned + (slip if req_id else 0)
        rng = streams.rng("person", pid, day=planned)
        lo, hi = params.ramp_days
        ramp = int(rng.integers(lo, hi + 1))
        skill = float(rng.normal(0.0, params.skill_sigma)) if spec.role == "AE" else 0.0
        hazard = params.attrition_annual.get(spec.role, 0.0)
        end = None
        if hazard:
            rate = -log(1.0 - hazard) / 365.0
            leave = start + int(-log(1.0 - rng.random()) / rate)
            if fork_day is not None and planned < fork_day <= leave:
                # a person already here at the fork: their departure after it is a fresh draw
                again = streams.rng("depart", pid, day=fork_day)
                leave = max(start, fork_day) + int(-log(1.0 - again.random()) / rate)
            end = leave if leave < end_day else None
        first, last = FIRST[idx % len(FIRST)], LAST[(idx // len(FIRST)) % len(LAST)]
        people.append(
            Person(
                idx,
                pid,
                f"005SY{idx + 1:010d}",
                f"{first} {last}",
                f"{first}.{last}.{idx + 1}@example.com".lower(),
                spec.role,
                spec.team,
                spec.segment,
                ("NA", "EMEA")[idx % 2],
                req_id,
                planned if req_id else None,
                start,
                end,
                ramp,
                float(exp(skill)),
            )
        )
    return people


def requisition_rows(
    params: CompanyParams, people: list[Person], at: date
) -> list[dict]:
    """People-system requisitions as known on `at`: open until the hire starts, then filled."""
    by_req = {p.req_id: p for p in people if p.req_id}
    rows = []
    for i, spec in enumerate(params.hires):
        req_id = f"REQ-{i + 1:03d}"
        opened = spec.planned_start - timedelta(days=75)
        if opened > at:
            continue
        person = by_req.get(req_id)
        if spec.cancelled:
            closed = spec.planned_start - timedelta(days=30)
            status, who, done = (
                ("cancelled", None, closed) if closed <= at else ("open", None, None)
            )
        elif person and date.fromordinal(person.start) <= at:
            status, who, done = "filled", person.pid, date.fromordinal(person.start)
        else:
            status, who, done = "open", None, None
        rows.append(
            {
                "req_id": req_id,
                "team": spec.team,
                "role": spec.role,
                "planned_start": spec.planned_start.isoformat(),
                "status": status,
                "person_id": who,
                "opened_date": opened.isoformat(),
                "closed_date": done.isoformat() if done else None,
            }
        )
    return rows

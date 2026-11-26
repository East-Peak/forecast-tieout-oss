"""Deterministic synthetic CRM history with a known right answer.

Used for the tieout_core test fixtures and for the demo companies in
``engine/data-v2``. Its mechanics are deliberately not the model's: a deal walks
the stages one at a time, spends an exponentially distributed dwell in each, and
at the end of it either advances or is lost; advancing out of the last stage is
a win. The true chance of winning from a stage is therefore the product of the
remaining advance probabilities, which the fitted model must recover by counting
snapshots, never by seeing these parameters.

A company may also be *staffed* (``Company.staffing``). Then pipeline creation
depends on people: each employed AE creates deals at a full-ramp rate scaled
by a linear ramp over their first months, and demand that does not respond to
headcount creates the rest. Every deal is owned by an AE employed on its
creation date. Without staffing the generator behaves exactly as before (the
recovery fixtures rely on that).

Standard library only (``random.Random``) so the output is identical across
platforms and library versions.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from engine.tieout_core.fiscal import month_end
from engine.tieout_core.records import Dataset, Deal, Observation, Transition

OPEN_CODES = ("S1", "S2", "S3", "S4", "S5")


@dataclass(frozen=True)
class Staffing:
    """How people create pipeline. ``headcount`` is the AE plan the company hires
    to, as (from date, heads) steps; departures are backfilled at the next
    month's hiring, so heads stay on plan apart from the month's leavers."""

    headcount: tuple[tuple[date, int], ...]
    monthly_attrition: float  # chance an AE (other than the first) leaves in a month
    deals_per_ramped_ae_month: float  # an AE's creation rate at full ramp
    ramp_months: int  # linear ramp from zero to full over this many months
    demand_deals_per_month: (
        float  # creation that ignores headcount; grows with the company
    )
    annual_quota: tuple[tuple[str, int], ...]  # full-ramp quota by segment
    other_roles: tuple[tuple[str, int], ...] = ()  # (role, count): counted, no deals


@dataclass(frozen=True)
class Member:
    id: str
    name: str
    role: str
    segment: str
    start: date
    end: date | None  # None while employed
    annual_quota: Decimal | None


@dataclass(frozen=True)
class Company:
    slug: str
    prefix: str
    start: date
    as_of: date
    seed: int
    deals_per_month: float
    advance: tuple[float, ...]  # chance of advancing out of S1..S5 (out of S5 = win)
    dwell_days: tuple[float, ...]  # mean days spent in S1..S5
    growth_per_year: float = 0.0
    segments: tuple[tuple[str, float, float], ...] = (("mid_market", 1.0, 50_000),)
    size_sigma: float = 0.6
    big_deal_share: float = 0.0
    big_deal_multiplier: float = 12.0
    slip_share: float = 0.0  # share of deals whose expected close is set optimistically
    stall_share: float = 0.0  # share of stage dwells that run eight times longer
    conversion_change: tuple[date, float] | None = (
        None  # from this date, advance x factor
    )
    missing_history_share: float = 0.0
    other_motions: tuple[
        tuple[str, float, float], ...
    ] = ()  # (type, per month, median arr)
    staffing: Staffing | None = None


@dataclass(frozen=True)
class Generated:
    company: Company
    dataset: Dataset
    roster: tuple[Member, ...] = ()
    owners: dict[str, str] = field(default_factory=dict)  # deal id -> member id
    origins: dict[str, str] = field(
        default_factory=dict
    )  # deal id -> "rep" or "demand"


def true_win_rates(company: Company) -> dict[str, float]:
    return {code: math.prod(company.advance[i:]) for i, code in enumerate(OPEN_CODES)}


def generate(company: Company) -> Generated:
    if company.staffing is not None:
        return _generate_staffed(company)
    rng = random.Random(company.seed)
    deals, transitions, observations = [], [], []
    n = 0
    day = company.start
    while day <= company.as_of:
        years = (day - company.start).days / 365
        rate = (
            company.deals_per_month * 12 / 365 * (1 + company.growth_per_year) ** years
        )
        for _ in range(_poisson(rng, rate)):
            n += 1
            d, ts, obs = _deal(rng, company, f"{company.prefix}-{n:05d}", day)
            deals.append(d)
            transitions += ts
            observations += obs
        for motion, per_month, median in company.other_motions:
            for _ in range(_poisson(rng, per_month * 12 / 365)):
                close = day + timedelta(days=rng.randint(10, 60))
                n += 1
                if close <= company.as_of:
                    arr = _dollars(median * math.exp(rng.gauss(0, company.size_sigma)))
                    deals.append(
                        Deal(
                            0,
                            f"{company.prefix}-{n:05d}",
                            motion,
                            company.segments[0][0],
                            "Won",
                            arr,
                            day,
                            close,
                            True,
                            True,
                        )
                    )
        day += timedelta(days=1)
    transitions.sort(key=lambda t: (t.deal_id, t.on))
    observations.sort(key=lambda o: (o.deal_id, o.on))
    return Generated(
        company, Dataset(tuple(deals), tuple(transitions), tuple(observations))
    )


def _deal(rng: random.Random, c: Company, deal_id: str, created: date, segment=None):
    if segment is None:
        segment = _pick(rng, c.segments)
    amount = segment[2] * math.exp(rng.gauss(0, c.size_sigma))
    if rng.random() < c.big_deal_share:
        amount *= c.big_deal_multiplier
    amount = _dollars(amount)
    optimistic = rng.random() < c.slip_share
    drop_history = rng.random() < c.missing_history_share

    def expected_after(at: date, stage_index: int) -> date:
        remaining = sum(c.dwell_days[stage_index:])
        return at + timedelta(days=math.ceil(remaining * (0.4 if optimistic else 1.0)))

    # Walk the stages: (date, stage code, amount after the change, expected close).
    events = [(created, "S1", amount, expected_after(created, 0))]
    t, k = created, 0
    while True:
        dwell = rng.expovariate(1 / c.dwell_days[k])
        if rng.random() < c.stall_share:
            dwell *= 8
        t = t + timedelta(days=max(1, math.ceil(dwell)))
        p = c.advance[k]
        if c.conversion_change and t >= c.conversion_change[0]:
            p *= c.conversion_change[1]
        if rng.random() < 0.15:
            amount = _dollars(float(amount) * rng.uniform(0.8, 1.2))
        if rng.random() >= p:
            events.append((t, "Lost", amount, t))
            break
        k += 1
        if k == len(OPEN_CODES):
            events.append((t, "Won", amount, t))
            break
        events.append((t, OPEN_CODES[k], amount, expected_after(t, k)))

    # Month-end reviews push out an expected close that has already passed.
    obs = [Observation(deal_id, on, amt, exp) for on, _, amt, exp in events]
    reviewed = []
    for i, o in enumerate(obs):
        reviewed.append(o)
        next_on = obs[i + 1].on if i + 1 < len(obs) else date.max
        expected = o.expected_close
        review = month_end(o.on)
        while review < next_on and review <= c.as_of and o.on != events[-1][0]:
            if expected < review:
                expected = review + timedelta(days=30)
                reviewed.append(Observation(deal_id, review, o.amount, expected))
            review = month_end(review + timedelta(days=1))

    known = [e for e in events if e[0] <= c.as_of]
    known_obs = [o for o in reviewed if o.on <= c.as_of]
    final_on, final_stage, final_amount, _ = events[-1]
    if final_on <= c.as_of:
        deal = Deal(0, deal_id, "new_business", segment[0], final_stage, final_amount, created,
                    final_on, True, final_stage == "Won")  # fmt: skip
    else:
        latest = known_obs[-1]
        deal = Deal(0, deal_id, "new_business", segment[0], known[-1][1], latest.amount, created,
                    latest.expected_close, False, False)  # fmt: skip
    transitions = (
        [] if drop_history else [Transition(deal_id, s, on) for on, s, _, _ in known]
    )
    return deal, transitions, known_obs


def _pick(rng: random.Random, segments):
    total = sum(s[1] for s in segments)
    x = rng.random() * total
    for s in segments:
        x -= s[1]
        if x <= 0:
            return s
    return segments[-1]


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _dollars(x: float) -> Decimal:
    return Decimal(max(1, round(x)))


# ---------------------------------------------------------------- staffing

FIRST_NAMES = (
    "Ada", "Bram", "Cleo", "Dev", "Esme", "Finn", "Gia", "Hugo", "Iris", "Jude",
    "Kai", "Lena", "Milo", "Nia", "Otto", "Pia", "Quinn", "Rhea", "Sami", "Tova",
    "Uma", "Vik", "Wren", "Xavi", "Yara", "Zane",
)  # fmt: skip
LAST_NAMES = (
    "Abbott", "Barros", "Chen", "Dalton", "Eze", "Farrow", "Gill", "Haas",
    "Ibarra", "Joshi", "Keane", "Lund", "Moreau", "Nakai", "Ortiz", "Price",
    "Quist", "Roth", "Sato", "Tran", "Udall", "Varga", "Ward", "Young",
)  # fmt: skip
DAYS_PER_MONTH = 365.25 / 12


def employed(m: Member, on: date) -> bool:
    return m.start <= on and (m.end is None or on <= m.end)


def ramp(m: Member, on: date, ramp_months: int) -> float:
    """Share of full productivity on ``on``: linear over the first months."""
    tenure = (on - m.start).days + 1
    return min(1.0, tenure / (ramp_months * DAYS_PER_MONTH))


def build_roster(company: Company) -> tuple[Member, ...]:
    """AEs hired to the headcount plan with monthly attrition, plus the other
    roles. Drawn from its own seeded stream so the deal stream is unaffected."""
    st = company.staffing
    rng = random.Random(f"roster-{company.seed}")
    quota = dict(st.annual_quota)
    names = iter(_names(rng))
    aes: list[Member] = []

    def hire(start: date) -> None:
        segment = _pick(rng, company.segments)[0]
        aes.append(Member(f"AE-{len(aes) + 1:03d}", next(names), "ae", segment, start,
                          None, Decimal(quota[segment])))  # fmt: skip

    for _ in range(_planned(st, company.start)):
        hire(company.start - timedelta(days=rng.randint(30, 720)))
    month = date(company.start.year, company.start.month, 1)
    while month <= company.as_of:
        days = (month_end(month) - month).days + 1
        for i, m in enumerate(aes):
            if i == 0 or m.end is not None or m.start >= month:
                continue  # the first AE stays, so someone can always own a deal
            if rng.random() < st.monthly_attrition:
                end = month + timedelta(days=rng.randint(0, days - 1))
                if end <= company.as_of:
                    aes[i] = Member(
                        m.id, m.name, m.role, m.segment, m.start, end, m.annual_quota
                    )
        heads = sum(1 for m in aes if m.end is None or m.end >= month)
        for _ in range(_planned(st, month) - heads):
            start = month + timedelta(days=rng.randint(0, 13))
            if start <= company.as_of:
                hire(start)
        month = month_end(month) + timedelta(days=1)

    others = []
    for role, count in st.other_roles:
        for k in range(count):
            start = company.start - timedelta(days=rng.randint(60, 900))
            others.append(Member(f"{role.upper()}-{k + 1:02d}", next(names), role, "",
                                 start, None, None))  # fmt: skip
    return tuple(aes) + tuple(others)


def _planned(st: Staffing, on: date) -> int:
    heads = st.headcount[0][1]
    for since, n in st.headcount:
        if since <= on:
            heads = n
    return heads


def _names(rng: random.Random):
    pairs = [(f, s) for f in FIRST_NAMES for s in LAST_NAMES]
    rng.shuffle(pairs)
    return [f"{f} {s}" for f, s in pairs]


def _generate_staffed(company: Company) -> Generated:
    st = company.staffing
    rng = random.Random(company.seed)
    roster = build_roster(company)
    aes = [m for m in roster if m.role == "ae"]
    segments = {s[0]: s for s in company.segments}
    deals, transitions, observations = [], [], []
    owners, origins = {}, {}
    n = 0

    def add(created: date, segment, owner: Member, origin: str) -> None:
        nonlocal n
        n += 1
        d, ts, obs = _deal(rng, company, f"{company.prefix}-{n:05d}", created, segment)
        deals.append(d)
        transitions.extend(ts)
        observations.extend(obs)
        owners[d.id], origins[d.id] = owner.id, origin

    day = company.start
    while day <= company.as_of:
        on_staff = [m for m in aes if employed(m, day)]
        years = (day - company.start).days / 365
        demand = (
            st.demand_deals_per_month
            * 12
            / 365
            * (1 + company.growth_per_year) ** years
        )
        for _ in range(_poisson(rng, demand)):
            segment = _pick(rng, company.segments)
            same = [m for m in on_staff if m.segment == segment[0]] or on_staff
            add(day, segment, same[rng.randrange(len(same))], "demand")
        for m in on_staff:
            rate = (
                st.deals_per_ramped_ae_month * 12 / 365 * ramp(m, day, st.ramp_months)
            )
            for _ in range(_poisson(rng, rate)):
                add(day, segments[m.segment], m, "rep")
        for motion, per_month, median in company.other_motions:
            for _ in range(_poisson(rng, per_month * 12 / 365)):
                close = day + timedelta(days=rng.randint(10, 60))
                n += 1
                if close <= company.as_of:
                    arr = _dollars(median * math.exp(rng.gauss(0, company.size_sigma)))
                    deal_id = f"{company.prefix}-{n:05d}"
                    deals.append(Deal(0, deal_id, motion, company.segments[0][0], "Won",
                                      arr, day, close, True, True))  # fmt: skip
                    owners[deal_id] = on_staff[rng.randrange(len(on_staff))].id
                    origins[deal_id] = "demand"
        day += timedelta(days=1)
    transitions.sort(key=lambda t: (t.deal_id, t.on))
    observations.sort(key=lambda o: (o.deal_id, o.on))
    dataset = Dataset(tuple(deals), tuple(transitions), tuple(observations))
    return Generated(company, dataset, roster, owners, origins)

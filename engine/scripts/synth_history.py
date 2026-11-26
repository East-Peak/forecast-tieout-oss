"""Deterministic synthetic CRM history with a known right answer.

Used for the tieout_core test fixtures and for the demo companies in
``engine/data-v2``. Its mechanics are deliberately not the model's: a deal walks
the stages one at a time, spends an exponentially distributed dwell in each, and
at the end of it either advances or is lost; advancing out of the last stage is
a win. The true chance of winning from a stage is therefore the product of the
remaining advance probabilities, which the fitted model must recover by counting
snapshots, never by seeing these parameters.

Standard library only (``random.Random``) so the output is identical across
platforms and library versions.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from engine.tieout_core.fiscal import month_end
from engine.tieout_core.records import Dataset, Deal, Observation, Transition

OPEN_CODES = ("S1", "S2", "S3", "S4", "S5")


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


@dataclass(frozen=True)
class Generated:
    company: Company
    dataset: Dataset


def true_win_rates(company: Company) -> dict[str, float]:
    return {code: math.prod(company.advance[i:]) for i, code in enumerate(OPEN_CODES)}


def generate(company: Company) -> Generated:
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


def _deal(rng: random.Random, c: Company, deal_id: str, created: date):
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

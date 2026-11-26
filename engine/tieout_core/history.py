"""What was known on a past date.

``as_known_at`` is the only way a past cutoff is reconstructed. Every later
step (fitting, forecasting, back-testing) receives its output and so cannot see
anything dated after the cutoff.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from .records import LOST, WON, Dataset

UNKNOWN_STAGE = "Unknown"


def as_known_at(data: Dataset, cutoff: date) -> Dataset:
    transitions = tuple(t for t in data.transitions if t.on <= cutoff)
    observations = None
    if data.observations is not None:
        observations = tuple(o for o in data.observations if o.on <= cutoff)

    stage_then = {t.deal_id: t.stage for t in transitions}  # sorted by date, last wins
    latest_obs = {}
    for o in observations or ():
        latest_obs[o.deal_id] = o

    deals = []
    for d in data.deals:
        if d.created > cutoff:
            continue
        if d.is_closed and d.close <= cutoff:
            deals.append(d)
            continue
        stage = stage_then.get(d.id, UNKNOWN_STAGE)
        if stage in (
            WON,
            LOST,
        ):  # history says closed but the deal is not: inconsistent
            stage = UNKNOWN_STAGE
        obs = latest_obs.get(d.id)
        deals.append(
            replace(
                d,
                stage=stage,
                arr=obs.amount if obs else None,
                close=obs.expected_close if obs else None,
                is_closed=False,
                is_won=False,
            )
        )
    return Dataset(tuple(deals), transitions, observations)


def latest_known_date(data: Dataset) -> date:
    """The latest dated fact in a dataset. An open deal's expected close date is
    a forecast, not a fact, and is not counted."""
    dates = [d.created for d in data.deals]
    dates += [d.close for d in data.deals if d.is_closed]
    dates += [t.on for t in data.transitions]
    dates += [o.on for o in data.observations or ()]
    return max(dates)


CREATION_AMOUNT_BASIS = "first recorded amount"


def creation_amounts(data: Dataset) -> dict[str, Decimal | None]:
    """The one rule for a deal's created-pipeline amount: its first observation
    when the files include deal_observations.csv (None if the deal has none),
    otherwise the amount on its deals.csv row, the only amount recorded."""
    if data.observations is None:
        return {d.id: d.arr for d in data.deals}
    first: dict[str, Decimal] = {}
    for o in data.observations:
        first.setdefault(o.deal_id, o.amount)
    return {d.id: first.get(d.id) for d in data.deals}

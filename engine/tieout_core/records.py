"""Typed records. Money is ``Decimal`` from the moment it is read."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .fiscal import FiscalYear

WON = "Won"
LOST = "Lost"


@dataclass(frozen=True)
class StageDef:
    name: str
    code: str
    order: int
    probability: Decimal


@dataclass(frozen=True)
class Profile:
    stages: tuple[StageDef, ...]
    fiscal_year: FiscalYear
    quarterly_targets: dict[str, Decimal]
    raw_to_code: dict[str, str] = field(repr=False)

    @property
    def open_codes(self) -> tuple[str, ...]:
        ordered = sorted(self.stages, key=lambda s: s.order)
        return tuple(s.code for s in ordered if s.code not in (WON, LOST))

    def code_for(self, raw: str) -> str | None:
        return self.raw_to_code.get(raw)

    def probability(self, code: str) -> Decimal:
        return next(s.probability for s in self.stages if s.code == code)

    def stage_name(self, code: str) -> str:
        return next(s.name for s in self.stages if s.code == code)


@dataclass(frozen=True)
class Deal:
    """One deal row. For a closed deal ``arr`` is the booked amount and ``close``
    the close date; for an open deal they are the current amount and the current
    expected close date."""

    row: int
    id: str
    type: str
    segment: str
    stage: str
    arr: Decimal | None
    created: date
    close: date | None
    is_closed: bool
    is_won: bool


@dataclass(frozen=True)
class Transition:
    deal_id: str
    stage: str
    on: date


@dataclass(frozen=True)
class Observation:
    """What the CRM said about a deal on a past date."""

    deal_id: str
    on: date
    amount: Decimal
    expected_close: date


@dataclass(frozen=True)
class Dataset:
    deals: tuple[Deal, ...]
    transitions: tuple[Transition, ...]
    observations: tuple[Observation, ...] | None


@dataclass(frozen=True)
class Exclusion:
    row: int
    deal_id: str
    reason: str
    arr: Decimal | None


@dataclass(frozen=True)
class Check:
    """A self-check the report runs on its own numbers."""

    name: str
    passed: bool
    detail: str

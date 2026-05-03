"""Domain-neutral connector interface for Forecast Tieout.

Connectors translate CRM-specific data models into these generic
domain types. The engine only works with these types — it never
sees CRM-specific field names.

Stage representation : Deal.stage and StageTransition.to_stage /
.from_stage are ALWAYS model-stage vocabulary (S0..S5/Won/Lost). Connectors
are responsible for translating from source-system stages using the
profile's field_mappings.yaml. The .raw_stage / .raw_to_stage / .raw_from_stage
fields preserve the source value for debugging and round-trip integrity.

Field contract (which derived analytics consume which Deal fields):
- compute_beginning_arr            : year_1_arr, arr, effective_start_date,
                                     effective_end_date, is_won, is_closed
- compute_closed_won_finance_summary: amount, year_1_arr, arr, nacv,
                                     non_recurring, close_date, is_won,
                                     type (for by_type groupings)
- compute_monthly_actuals           : close_date, first_s2_entry_date,
                                     amount, is_won, is_closed
- compute_open_inventory            : stage, amount, owner_id, owner_name,
                                     forecast_category, source_stream,
                                     is_closed
- compute_observed_velocity         : stage, created_date, close_date,
                                     stage history transitions
- compute_arr_movements             : revenue_type, amount, year_1_arr,
                                     close_date, is_won
- compute_funnel_rates              : stage, created_date, stage history

If you're writing a new connector, populate as many of these fields as your
source system exposes; leave the rest as None. Engine code handles None
gracefully (via documented fallbacks), but more populated fields = richer
downstream analytics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class Deal:
    id: str
    name: str
    amount: Optional[float]
    stage: str  # model-stage vocabulary (S0..S5/Won/Lost) — see ARCHITECTURE.md
    close_date: Optional[date]
    owner_id: str
    type: Optional[str] = None
    created_date: Optional[date] = None
    segment: Optional[str] = None
    source: Optional[str] = None
    is_closed: bool = False
    is_won: bool = False

    # ARR / finance fields — populated when source system exposes them
    year_1_arr: Optional[float] = None
    arr: Optional[float] = None
    nacv: Optional[float] = None
    non_recurring: Optional[float] = None

    # Effective period (for ARR snapshots and waterfall analysis)
    effective_start_date: Optional[date] = None
    effective_end_date: Optional[date] = None

    # Revenue classification (new_logo | expansion | renewal | other)
    revenue_type: Optional[str] = None

    # Stage normalization : preserves the source-system stage value
    raw_stage: Optional[str] = None

    # Earliest S2 transition for monthly-actuals semantics; populated by
    # connectors that have stage history.
    first_s2_entry_date: Optional[date] = None

    # Open-inventory parity fields
    owner_name: Optional[str] = None
    forecast_category: Optional[str] = None
    source_stream: Optional[str] = None

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Company:
    id: str
    name: str
    segment: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Contact:
    id: str
    name: str
    email: Optional[str] = None
    company_id: Optional[str] = None
    title: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamMember:
    id: str
    name: str
    role: str = "AE"
    segment: Optional[str] = None
    start_date: Optional[date] = None
    is_active: bool = True
    manager_id: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageTransition:
    deal_id: str
    from_stage: Optional[str]  # model-stage vocabulary 
    to_stage: str  # model-stage vocabulary 
    transition_date: datetime
    raw_from_stage: Optional[str] = None
    raw_to_stage: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorCapabilities:
    has_stage_history: bool = False
    has_contacts: bool = False
    has_companies: bool = False


class ConnectorInterface(ABC):
    """Abstract base class for data connectors."""

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities:
        """Declare which data this connector can provide."""
        ...

    @abstractmethod
    def fetch_deals(self, filters: dict[str, Any] | None = None) -> list[Deal]:
        ...

    @abstractmethod
    def fetch_team_members(self) -> list[TeamMember]:
        ...

    def fetch_companies(self, filters: dict[str, Any] | None = None) -> list[Company]:
        """Optional. Returns [] if capability is not supported."""
        return []

    def fetch_contacts(self, filters: dict[str, Any] | None = None) -> list[Contact]:
        """Optional. Returns [] if capability is not supported."""
        return []

    def fetch_stage_history(self, deal_ids: list[str] | None = None) -> list[StageTransition]:
        """Optional. Returns [] if capability is not supported."""
        return []

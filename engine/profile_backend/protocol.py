"""ProfileBackend Protocol + base class with default implementations.

Per ARCHITECTURE.md, ProfileBackend is the engine's wiring layer seam. Backends bundle:
- A ConnectorInterface (Concern A — raw domain data)
- An EnvironmentHealth (Concern C — observability; default no-op)
- compute_* methods (Concern B — derived analytics; default-Python via
  engine.gtm_model.derived.*)
- Optional Concern B′ overrides for source-pre-computed analytics
  (per ARCHITECTURE.md; default returns None)

Earlier work landed the abstraction; later work wires `wiring.py` /
`build_tieout_components()` to consume `ProfileBackend` instances instead
of warehouse/SF-specific lambdas.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Optional, Protocol, runtime_checkable

from engine.connectors.interface import (
    Company,
    ConnectorCapabilities,
    ConnectorInterface,
    Contact,
    Deal,
    StageTransition,
    TeamMember,
)
from engine.gtm_model.derived.arr_movements import (
    ARRMovements,
    compute_arr_movements,
)
from engine.gtm_model.derived.arr_snapshot import (
    ARRSnapshot,
    compute_beginning_arr,
)
from engine.gtm_model.derived.finance_summary import (
    FinanceSummary,
    compute_closed_won_finance_summary,
)
from engine.gtm_model.derived.funnel import FunnelRates, compute_funnel_rates
from engine.gtm_model.derived.monthly_actuals import (
    MonthlyActuals,
    compute_monthly_actuals,
)
from engine.gtm_model.derived.mql_signals import (
    MonthlyMQLSeries,
    MQLSignals,
)
from engine.gtm_model.derived.observed_productivity import (
    ProductivityProfile,
    RampCurve,
    compute_observed_ae_ramp_curve,
    compute_observed_productivity,
)
from engine.gtm_model.derived.observed_velocity import (
    VelocityProfile,
    compute_observed_velocity,
)
from engine.gtm_model.derived.open_inventory import (
    OpenInventorySnapshot,
    compute_open_inventory_snapshot,
)
from engine.gtm_model.derived.roster import compute_roster
from engine.gtm_model.derived.self_serve_velocity import SelfServeVelocity


# ── Concern C: Environment Health ──────────────────────────────────


@runtime_checkable
class EnvironmentHealth(Protocol):
    """Production-only observability surface (ARCHITECTURE.md Concern C).

    Default no-op (NoOpHealth) is appropriate for CSV / Salesforce
    backends. Snowflake-backed production deployments override with
    real mart freshness checks etc.
    """

    def mart_freshness(self) -> dict[str, Any]: ...
    def reconciliation_check(self, *, quarter: str) -> Optional[dict[str, Any]]: ...


class NoOpHealth:
    """Default Environment Health — declines all observability."""

    def mart_freshness(self) -> dict[str, Any]:
        return {}

    def reconciliation_check(self, *, quarter: str) -> Optional[dict[str, Any]]:
        return None


# ── Concern A+B+B′: ProfileBackend ────────────────────────────────


@runtime_checkable
class ProfileBackend(Protocol):
    """Everything the engine needs from a profile's data backend .

    Concern A — direct connector access.
    Concern B — derived analytics with default Python implementations.
    Concern B′ — source-pre-computed optional analytics (default None;
    per ARCHITECTURE.md).
    Concern C — environment health (default no-op).
    """

    connector: ConnectorInterface
    health: EnvironmentHealth

    # Concern A pass-throughs (the engine usually calls compute_* directly,
    # but raw fetch methods stay available for cases that need the data).
    def fetch_deals(self, filters: dict[str, Any] | None = None) -> list[Deal]: ...
    def fetch_team_members(self) -> list[TeamMember]: ...
    def fetch_stage_history(
        self, deal_ids: list[str] | None = None
    ) -> list[StageTransition]: ...
    def fetch_companies(self, filters: dict[str, Any] | None = None) -> list[Company]: ...
    def fetch_contacts(self, filters: dict[str, Any] | None = None) -> list[Contact]: ...
    def capabilities(self) -> ConnectorCapabilities: ...

    # Concern B — derived analytics
    def compute_beginning_arr(
        self,
        period_start: date,
        fallback_arr: float = 0.0,
        fallback_label: Optional[str] = None,
    ) -> ARRSnapshot: ...

    def compute_closed_won_finance_summary(
        self, period_start: date, period_end: date
    ) -> FinanceSummary: ...

    def compute_monthly_actuals(
        self, period_start: date, period_end: date
    ) -> MonthlyActuals: ...

    def compute_open_inventory(self, as_of: date) -> OpenInventorySnapshot: ...

    def compute_roster(
        self,
        yaml_overrides: Optional[dict[str, dict]] = None,
        yaml_phantoms: Optional[list[dict]] = None,
        ae_overrides: Optional[dict[str, dict]] = None,
    ) -> list[dict[str, Any]]: ...

    def compute_observed_velocity(
        self, as_of: date, rolling_lookback_days: int = 90
    ) -> VelocityProfile: ...

    def compute_observed_productivity(
        self, as_of: date, lookback_days: int = 180
    ) -> ProductivityProfile: ...

    def compute_observed_ae_ramp_curve(
        self, as_of: date, lookback_days: int = 365
    ) -> RampCurve: ...

    def compute_funnel_rates(self) -> FunnelRates: ...

    def compute_arr_movements(
        self, period_start: date, period_end: date
    ) -> ARRMovements: ...

    def compute_self_serve_velocity(self) -> Optional[SelfServeVelocity]: ...

    def compute_mql_signals(
        self, as_of: date, lookback_days: int = 180
    ) -> Optional[MQLSignals]: ...

    def compute_monthly_mql_actuals(
        self, as_of: date, months: int = 12, fy_start: Optional[date] = None
    ) -> Optional[MonthlyMQLSeries]: ...

    # Concern B′ — source-pre-computed analytics (default None per ARCHITECTURE.md)
    def compute_funnel_from_source(
        self, quarter: str
    ) -> Optional[dict[str, Any]]: ...

    def compute_weekly_targets(
        self, quarter: str
    ) -> Optional[dict[str, Any]]: ...

    def compute_quarter_conversion_overrides(
        self, quarter: str
    ) -> Optional[dict[str, Any]]: ...

    def compute_closed_won_timing(
        self, lookback_months: int = 12
    ) -> Optional[list[dict]]: ...


# ── Default base class for backends to inherit ────────────────────


class ProfileBackendBase:
    """Reusable base for ProfileBackend implementations.

    Provides:
    - Default Concern B implementations that call into engine.gtm_model.derived.*
    - Default Concern B′ that returns None (per ARCHITECTURE.md)
    - Default Concern C (NoOpHealth)

    Subclass and:
    - Pass a ConnectorInterface to __init__
    - Override Concern B methods if you have a faster path (e.g. SQL agg)
    - Override Concern B′ methods if your source has pre-computed analytics
    - Pass a real EnvironmentHealth if your source has observability
    """

    def __init__(
        self,
        connector: ConnectorInterface,
        health: Optional[EnvironmentHealth] = None,
    ) -> None:
        self.connector = connector
        self.health = health or NoOpHealth()

    # ── Concern A pass-throughs ──────────────────────────────────

    def fetch_deals(self, filters: dict[str, Any] | None = None) -> list[Deal]:
        return self.connector.fetch_deals(filters)

    def fetch_team_members(self) -> list[TeamMember]:
        return self.connector.fetch_team_members()

    def fetch_stage_history(
        self, deal_ids: list[str] | None = None
    ) -> list[StageTransition]:
        return self.connector.fetch_stage_history(deal_ids)

    def fetch_companies(self, filters: dict[str, Any] | None = None) -> list[Company]:
        return self.connector.fetch_companies(filters)

    def fetch_contacts(self, filters: dict[str, Any] | None = None) -> list[Contact]:
        return self.connector.fetch_contacts(filters)

    def capabilities(self) -> ConnectorCapabilities:
        return self.connector.capabilities()

    # ── Concern B defaults ────────────────────────────────────────

    def compute_beginning_arr(
        self,
        period_start: date,
        fallback_arr: float = 0.0,
        fallback_label: Optional[str] = None,
    ) -> ARRSnapshot:
        return compute_beginning_arr(
            self.fetch_deals(), period_start, fallback_arr, fallback_label
        )

    def compute_closed_won_finance_summary(
        self, period_start: date, period_end: date
    ) -> FinanceSummary:
        return compute_closed_won_finance_summary(
            self.fetch_deals(), period_start, period_end
        )

    def compute_monthly_actuals(
        self, period_start: date, period_end: date
    ) -> MonthlyActuals:
        return compute_monthly_actuals(self.fetch_deals(), period_start, period_end)

    def compute_open_inventory(self, as_of: date) -> OpenInventorySnapshot:
        return compute_open_inventory_snapshot(self.fetch_deals(), as_of)

    def compute_roster(
        self,
        yaml_overrides: Optional[dict[str, dict]] = None,
        yaml_phantoms: Optional[list[dict]] = None,
        ae_overrides: Optional[dict[str, dict]] = None,
    ) -> list[dict[str, Any]]:
        return compute_roster(
            self.fetch_team_members(),
            yaml_overrides=yaml_overrides,
            yaml_phantoms=yaml_phantoms,
            ae_overrides=ae_overrides,
        )

    def compute_observed_velocity(
        self, as_of: date, rolling_lookback_days: int = 90
    ) -> VelocityProfile:
        return compute_observed_velocity(
            self.fetch_deals(),
            self.fetch_stage_history(),
            as_of,
            rolling_lookback_days=rolling_lookback_days,
        )

    def compute_observed_productivity(
        self, as_of: date, lookback_days: int = 180
    ) -> ProductivityProfile:
        return compute_observed_productivity(
            self.fetch_deals(),
            self.fetch_team_members(),
            as_of,
            lookback_days=lookback_days,
        )

    def compute_observed_ae_ramp_curve(
        self, as_of: date, lookback_days: int = 365
    ) -> RampCurve:
        return compute_observed_ae_ramp_curve(
            self.fetch_deals(),
            self.fetch_team_members(),
            as_of,
            lookback_days=lookback_days,
        )

    def compute_funnel_rates(self) -> FunnelRates:
        return compute_funnel_rates(self.fetch_deals(), self.fetch_stage_history())

    def compute_arr_movements(
        self, period_start: date, period_end: date
    ) -> ARRMovements:
        return compute_arr_movements(self.fetch_deals(), period_start, period_end)

    def compute_self_serve_velocity(self) -> Optional[SelfServeVelocity]:
        # Default: no live PLG signal. Backends with PLG marts override.
        return None

    def compute_mql_signals(
        self, as_of: date, lookback_days: int = 180
    ) -> Optional[MQLSignals]:
        # Default: no live MQL surface. Backends with MQL data override.
        return None

    def compute_monthly_mql_actuals(
        self, as_of: date, months: int = 12, fy_start: Optional[date] = None
    ) -> Optional[MonthlyMQLSeries]:
        return None

    # ── Concern B′ defaults (Per ARCHITECTURE.md: return None) ────────────

    def compute_funnel_from_source(
        self, quarter: str
    ) -> Optional[dict[str, Any]]:
        return None

    def compute_weekly_targets(self, quarter: str) -> Optional[dict[str, Any]]:
        return None

    def compute_quarter_conversion_overrides(
        self, quarter: str
    ) -> Optional[dict[str, Any]]:
        return None

    def compute_closed_won_timing(
        self, lookback_months: int = 12
    ) -> Optional[list[dict]]:
        return None

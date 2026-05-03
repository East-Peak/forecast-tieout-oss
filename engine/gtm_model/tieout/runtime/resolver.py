"""Runtime signal and rate resolution facade for Planning Tie-Out."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from gtm_model.rate_registry import RateRegistry
from gtm_model.tieout.runtime.observed import TieoutObservedSignalResolver
from gtm_model.tieout.runtime.rates import TieoutRuntimeRateResolver
from gtm_model.tieout.runtime.velocity import TieoutStageVelocityResolver


@dataclass
class TieoutRuntimeResolver:
    """Resolve observed runtime inputs and canonical fallback rates."""

    get_assumptions: Callable[[], dict]
    get_rate_registry: Callable[[], Optional[RateRegistry]]
    get_cdw: Callable[[], object | None]
    get_sf: Callable[[], object | None]
    is_cdw_query_failed: Callable[[], bool]
    try_closed_won_timing: Callable[[], Optional[list[dict]]]
    get_closed_won_timing_source: Callable[[], Optional[str]]
    get_beginning_arr_snapshot: Callable[[], tuple[float, dict]]
    get_backend: Optional[Callable[[], object | None]] = None  # ProfileBackend 

    observed_signals: TieoutObservedSignalResolver = field(init=False, repr=False)
    rates: TieoutRuntimeRateResolver = field(init=False, repr=False)
    stage_velocity: TieoutStageVelocityResolver = field(init=False, repr=False)

    def __post_init__(self):
        self.observed_signals = TieoutObservedSignalResolver(
            get_cdw=self.get_cdw,
            get_sf=self.get_sf,
            is_cdw_query_failed=self.is_cdw_query_failed,
            get_beginning_arr_snapshot=self.get_beginning_arr_snapshot,
        )
        self.rates = TieoutRuntimeRateResolver(
            get_assumptions=self.get_assumptions,
            get_rate_registry=self.get_rate_registry,
            get_sf=self.get_sf,
            get_cdw=self.get_cdw,
            try_closed_won_timing=self.try_closed_won_timing,
            get_closed_won_timing_source=self.get_closed_won_timing_source,
            get_backend=self.get_backend,
        )
        self.stage_velocity = TieoutStageVelocityResolver(
            get_cdw=self.get_cdw,
            get_sf=self.get_sf,
            is_cdw_query_failed=self.is_cdw_query_failed,
            get_backend=self.get_backend,
        )

    def compute_trailing_ramped_ae_months(
        self,
        roster: dict,
        as_of: date,
        months: int = 6,
    ) -> float:
        return self.observed_signals.compute_trailing_ramped_ae_months(
            roster=roster,
            as_of=as_of,
            months=months,
        )

    def get_observed_ae_productivity(
        self,
        roster: dict,
        as_of: date,
        lookback_days: int = 180,
        compute_ramped_months: Optional[Callable[[dict, date, int], float]] = None,
    ) -> dict:
        return self.observed_signals.get_observed_ae_productivity(
            roster=roster,
            as_of=as_of,
            lookback_days=lookback_days,
            compute_ramped_months=compute_ramped_months,
        )

    def get_observed_ae_ramp_curve(
        self,
        roster: dict,
        as_of: date,
        lookback_days: int = 365,
    ) -> dict:
        return self.observed_signals.get_observed_ae_ramp_curve(
            roster=roster,
            as_of=as_of,
            lookback_days=lookback_days,
        )

    def get_trailing_mql_weekly_signal(
        self,
        as_of: date,
        lookback_days: int = 180,
    ) -> tuple[Optional[list[float]], str]:
        return self.observed_signals.get_trailing_mql_weekly_signal(
            as_of=as_of,
            lookback_days=lookback_days,
        )

    def get_monthly_mql_actuals(
        self,
        as_of: date,
        months: int = 12,
        fy_start: date | None = None,
    ) -> tuple[list, int | None]:
        return self.observed_signals.get_monthly_mql_actuals(
            as_of=as_of,
            months=months,
            fy_start=fy_start,
        )

    def get_registered_funnel_rate(self, key: str, default: float) -> float:
        return self.rates.get_registered_funnel_rate(key, default)

    def get_runtime_funnel_rates(self) -> dict[str, float]:
        return self.rates.get_runtime_funnel_rates()

    def describe_runtime_funnel_rates(self) -> dict[str, dict]:
        return self.rates.describe_runtime_funnel_rates()

    def get_decay_curve(self) -> list[float]:
        return self.rates.get_decay_curve()

    def get_rolling_s2_to_won_rate(self) -> dict:
        return self.rates.get_rolling_s2_to_won_rate()

    def get_s2_to_won_rate(self) -> float:
        return self.rates.get_s2_to_won_rate()

    def get_stage_win_rates(
        self,
        resolve_s2_to_won: Optional[Callable[[], float]] = None,
    ) -> dict[str, float]:
        return self.rates.get_stage_win_rates(resolve_s2_to_won=resolve_s2_to_won)

    def get_observed_stage_velocity(self) -> dict:
        return self.stage_velocity.get_observed_stage_velocity()

    def get_stage_velocity_from_cdw(self, min_sample: int) -> Optional[dict]:
        return self.stage_velocity.get_stage_velocity_from_cdw(min_sample)

    def get_stage_velocity_days(self) -> dict[str, float]:
        return self.stage_velocity.get_stage_velocity_days()

    def get_observed_arr_movements(self) -> dict:
        return self.observed_signals.get_observed_arr_movements()

    def get_self_serve_velocity(self, lookback_days: int = 180) -> dict:
        return self.observed_signals.get_self_serve_velocity(lookback_days=lookback_days)

    def get_actual_decay_from_cdw(
        self,
        config_curve: Optional[list[float]] = None,
    ) -> list[float]:
        return self.rates.get_actual_decay_from_cdw(config_curve=config_curve)

    def get_observed_decay_curve(
        self,
        config_curve: Optional[list[float]] = None,
    ) -> dict:
        return self.rates.get_observed_decay_curve(config_curve=config_curve)

"""Shared runtime snapshot helpers for Planning Tie-Out."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any, Callable, Optional

from gtm_model.tieout.runtime.env import resolve_config_resource_path

logger = logging.getLogger(__name__)


def load_trajectory_roster_snapshot(
    live_roster: Optional[list[dict]],
    config_dir: Path,
    load_config_yaml: Optional[Callable[[str], dict]] = None,
) -> tuple[dict[str, list[dict]], dict]:
    """Resolve the grouped roster shape used by trajectory computation."""
    from gtm_model.roster import load_roster, load_roster_data

    try:
        if live_roster:
            grouped = {"active": [], "incoming": [], "planned": []}
            for entry in live_roster:
                tier = str(entry.get("tier") or "active").strip().lower()
                if tier not in grouped:
                    tier = "active"
                grouped[tier].append(dict(entry))
            if grouped["active"]:
                return grouped, {"source": "warehouse + roster.yaml"}

        roster_path = resolve_config_resource_path("roster.yaml", config_dir=config_dir)
        if roster_path.exists():
            return load_roster(str(roster_path)), {"source": "roster.yaml"}
        if load_config_yaml is not None:
            return load_roster_data(load_config_yaml("roster.yaml")), {"source": "roster.yaml"}
        return {"active": [], "incoming": [], "planned": []}, {"source": "unavailable"}
    except Exception as exc:
        logger.warning("Could not load roster for trajectory: %s", exc)
        return {"active": [], "incoming": [], "planned": []}, {"source": "unavailable"}


class TieoutRuntimeSnapshot:
    """Lazy-loading runtime snapshot — each field computes on first access.

    This replaces the previous eager dataclass that computed all fields
    up-front in build().  With lazy loading, trajectory-only fields
    (observed_ae_ramp_curve, observed_ae_productivity, etc.) are not
    resolved until the trajectory path actually reads them, and plan-only
    fields (open_inventory_snapshot, stage_win_rates, etc.) are not
    resolved until the plan path reads them.

    Fields that are accessed by multiple paths (roster, beginning_arr,
    observed_arr_movements) are still computed at most once thanks to
    functools.cached_property.
    """

    def __init__(
        self,
        builder: TieoutRuntimeSnapshotBuilder,
        as_of: Optional[date] = None,
        fy_start: Optional[date] = None,
    ):
        # Store builder reference so cached_property getters can call it.
        # Use object.__setattr__ to avoid any descriptor conflicts.
        object.__setattr__(self, "_builder", builder)
        object.__setattr__(self, "_as_of_value", as_of or date.today())
        object.__setattr__(self, "_fy_start_value", fy_start)

    @property
    def as_of(self) -> date:
        return self._as_of_value

    # -- Beginning ARR (paired call) --

    @cached_property
    def _beginning_arr_pair(self) -> tuple[float, dict]:
        return self._builder.get_beginning_arr_snapshot()

    @cached_property
    def beginning_arr(self) -> float:
        return self._beginning_arr_pair[0]

    @cached_property
    def beginning_arr_provenance(self) -> dict:
        return self._beginning_arr_pair[1]

    # -- Bookings summary (paired call) --

    @cached_property
    def _bookings_pair(self) -> tuple[dict, dict]:
        # Honor --as-of for deterministic finance summary period_end
        return self._builder.get_closed_won_finance_summary(as_of=self._as_of_value)

    @cached_property
    def bookings_summary(self) -> dict:
        return self._bookings_pair[0]

    @cached_property
    def bookings_summary_provenance(self) -> dict:
        return self._bookings_pair[1]

    # -- Independent fields --

    @cached_property
    def observed_arr_movements(self) -> dict:
        return self._builder.get_observed_arr_movements()

    @cached_property
    def observed_decay_curve(self) -> dict:
        return self._builder.get_observed_decay_curve()

    @cached_property
    def s2_to_won_rate(self) -> float:
        return self._builder.get_s2_to_won_rate()

    @cached_property
    def rolling_s2_to_won_rate(self) -> dict:
        return self._builder.get_rolling_s2_to_won_rate()

    @cached_property
    def open_inventory_snapshot(self) -> Any:
        return self._builder.get_open_inventory_snapshot(as_of=self._as_of_value)

    @cached_property
    def stage_win_rates(self) -> dict[str, float]:
        return self._builder.get_stage_win_rates()

    @cached_property
    def stage_velocity_days(self) -> dict[str, float]:
        return self._builder.get_stage_velocity_days()

    @cached_property
    def runtime_funnel_rates(self) -> dict[str, float]:
        return self._builder.get_runtime_funnel_rates()

    @cached_property
    def runtime_funnel_rate_descriptions(self) -> dict[str, dict]:
        return self._builder.describe_runtime_funnel_rates()

    # -- Roster (base for trajectory roster) --

    @cached_property
    def roster(self) -> Optional[list[dict]]:
        return self._builder.try_roster(None)

    # -- Trajectory roster (depends on roster) --

    @cached_property
    def _trajectory_roster_pair(self) -> tuple[dict[str, list[dict]], dict]:
        return load_trajectory_roster_snapshot(
            live_roster=self.roster,
            config_dir=self._builder.get_config_dir(),
            load_config_yaml=self._builder.load_config_yaml,
        )

    @cached_property
    def trajectory_roster(self) -> dict[str, list[dict]]:
        return self._trajectory_roster_pair[0]

    @cached_property
    def trajectory_roster_meta(self) -> dict:
        return self._trajectory_roster_pair[1]

    # -- Trajectory-only expensive fields (depend on trajectory_roster) --

    @cached_property
    def observed_ae_productivity(self) -> dict:
        return self._builder.get_observed_ae_productivity(
            self.trajectory_roster, self._as_of_value
        )

    @cached_property
    def observed_ae_ramp_curve(self) -> dict:
        return self._builder.get_observed_ae_ramp_curve(
            self.trajectory_roster, self._as_of_value
        )

    @cached_property
    def trailing_mql_weekly_signal(self) -> tuple[Optional[list[float]], str]:
        return self._builder.get_trailing_mql_weekly_signal(self._as_of_value)

    @cached_property
    def self_serve_velocity(self) -> dict:
        return self._builder.get_self_serve_velocity()

    @cached_property
    def _mql_actuals_pair(self) -> tuple[list, int | None]:
        fy_start = getattr(self, "_fy_start_value", None)
        return self._builder.get_monthly_mql_actuals(
            self._as_of_value, months=12, fy_start=fy_start,
        )

    @cached_property
    def monthly_mql_actuals(self) -> list:
        return self._mql_actuals_pair[0]

    @cached_property
    def mql_partial_month_index(self) -> int | None:
        return self._mql_actuals_pair[1]

    @cached_property
    def monthly_actuals(self) -> dict:
        fy_start = getattr(self, "_fy_start_value", None)
        return self._builder.get_monthly_actuals(
            self._as_of_value,
            months=12,
            fy_start=fy_start,
        )


@dataclass
class TieoutRuntimeSnapshotBuilder:
    """Build a shared runtime snapshot once per full run."""

    get_config_dir: Callable[[], Path]
    load_config_yaml: Callable[[str], dict]
    get_beginning_arr_snapshot: Callable[[], tuple[float, dict]]
    get_closed_won_finance_summary: Callable[..., tuple[dict, dict]]  # accepts optional as_of
    get_observed_arr_movements: Callable[[], dict]
    get_observed_decay_curve: Callable[[], dict]
    get_s2_to_won_rate: Callable[[], float]
    get_rolling_s2_to_won_rate: Callable[[], dict]
    get_open_inventory_snapshot: Callable[[Optional[date]], Any]
    get_stage_win_rates: Callable[[], dict[str, float]]
    get_stage_velocity_days: Callable[[], dict[str, float]]
    get_runtime_funnel_rates: Callable[[], dict[str, float]]
    describe_runtime_funnel_rates: Callable[[], dict[str, dict]]
    try_roster: Callable[[Optional[dict]], Optional[list[dict]]]
    get_observed_ae_productivity: Callable[..., dict]
    get_observed_ae_ramp_curve: Callable[..., dict]
    get_trailing_mql_weekly_signal: Callable[..., tuple[Optional[list[float]], str]]
    get_self_serve_velocity: Callable[[], dict]
    get_monthly_mql_actuals: Callable[..., tuple] = lambda as_of, months=12, fy_start=None: ([None] * months, None)
    get_monthly_actuals: Callable[..., dict] = (
        lambda as_of, months=12, fy_start=None: {
            "bookings_by_month": [],
            "losses_by_month": [],
            "pipeline_created_by_month": [],
            "pipeline_entered_s2_by_month": [],
            "provenance": {},
        }
    )

    def build(self, as_of: Optional[date] = None, fy_start: Optional[date] = None) -> TieoutRuntimeSnapshot:
        """Create a lazy snapshot — fields resolve on first access only."""
        return TieoutRuntimeSnapshot(builder=self, as_of=as_of, fy_start=fy_start)

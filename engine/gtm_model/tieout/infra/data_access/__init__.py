"""Connector-backed data access for Planning Tie-Out.

Methods are split across domain mixins (open_inventory, roster,
beginning_arr, finance, monthly_actuals) for navigability. Each
domain owns a backend → warehouse → Salesforce → config fallback
chain for its data surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from gtm_model.tieout.infra.data_access.beginning_arr import BeginningArrMixin
from gtm_model.tieout.infra.data_access.finance import FinanceMixin
from gtm_model.tieout.infra.data_access.monthly_actuals import MonthlyActualsMixin
from gtm_model.tieout.infra.data_access.open_inventory import OpenInventoryMixin
from gtm_model.tieout.infra.data_access.roster import RosterMixin


@dataclass
class TieoutDataAccess(
    OpenInventoryMixin,
    RosterMixin,
    BeginningArrMixin,
    FinanceMixin,
    MonthlyActualsMixin,
):
    """Resolve connector-backed snapshots and roster state.

    When `get_backend` is supplied and returns a non-None ProfileBackend,
    methods route through it (per ARCHITECTURE.md) before falling back
    to the legacy warehouse/SF gateway. Profiles using the legacy
    `connector` + `data_dir` fields keep the existing warehouse/SF-or-
    config behavior.
    """

    get_config_dir: Callable[[], Path]
    load_config_yaml: Callable[[str], dict]
    get_targets: Callable[[], dict]
    get_quarter_dates: Callable[[], dict[str, tuple]]
    get_cdw: Callable[[], Any]
    get_sf: Callable[[], Any]
    is_cdw_query_failed: Callable[[], bool]
    get_beginning_arr_cache: Callable[[], Any]
    set_beginning_arr_cache: Callable[[Any], None]
    get_bookings_summary_cache: Callable[[], Any]
    set_bookings_summary_cache: Callable[[Any], None]
    get_roster_cache: Callable[[], dict]
    get_open_inventory_cache: Callable[[], dict]
    get_backend: Optional[Callable[[], Any]] = None  # ProfileBackend

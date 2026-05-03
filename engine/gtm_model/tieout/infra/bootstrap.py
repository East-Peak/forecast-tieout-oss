"""Constructor/bootstrap helpers for Planning Tie-Out."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from gtm_model.rate_registry import RateRegistry
from gtm_model.tieout.infra.plan_config import TieoutPlanConfigResolver
from gtm_model.tieout.runtime.env import get_config_stage, get_default_config_dir
from gtm_model.tieout.runtime.profile import get_active_profile_id, load_org_profile
from gtm_model.tieout.infra.wiring import build_tieout_components


def bootstrap_tieout_owner(
    owner: Any,
    config_dir: Optional[Path],
    plan_case_id: Optional[str],
    profile_id: Optional[str],
    logger: logging.Logger,
) -> None:
    """Initialize config, caches, connectors, and helper graph for an owner."""
    owner.config_dir = config_dir or get_default_config_dir()
    owner.config_stage = get_config_stage()
    owner.profile_id = get_active_profile_id(profile_id)
    owner.profile = load_org_profile(
        config_dir=owner.config_dir,
        profile_id=owner.profile_id,
    )
    owner.plan_config = TieoutPlanConfigResolver(
        config_dir=owner.config_dir,
        config_stage=owner.config_stage,
        profile_id=owner.profile_id,
    )
    owner.targets_raw = owner._load_yaml("targets.yaml")
    owner.plan_case_id = plan_case_id or owner._default_plan_case_id()
    owner.targets = owner._resolve_targets(owner.plan_case_id)
    owner.assumptions = owner._load_yaml("assumptions.yaml")
    owner.rate_registry = _build_rate_registry(owner.assumptions, logger)

    # Connector state stays lazy so __init__ remains cheap in tests.
    owner.cdw = None
    owner._cdw_checked = False
    owner._cdw_queries_failed = False
    owner.sf = None
    owner._sf_checked = False
    owner._beginning_arr_cache = None
    # Bookings cache is keyed by as_of.iso so different --as-of values
    # don't return stale results.
    owner._bookings_summary_cache = {}
    owner._roster_cache = {}
    owner._open_inventory_cache = {}
    owner._cdw_freshness_cache = {}
    owner._cdw_freshness_loaded = False
    owner._cdw_bookings_cache = {}
    owner._sf_bookings_cache = {}
    owner._closed_won_timing_cache = None
    owner._closed_won_timing_loaded = False
    owner._closed_won_timing_source = None
    owner._weekly_targets_cache = {}

    components = build_tieout_components(owner=owner)
    for name, value in vars(components).items():
        setattr(owner, name, value)
    # Keep the internal attribute alias.
    owner.bottoms_up = owner.archived_plan_model


def _build_rate_registry(
    assumptions: dict,
    logger: logging.Logger,
) -> Optional[RateRegistry]:
    """Try to build the shared runtime rate registry from config."""
    try:
        registry = RateRegistry()
        registry.load_from_config(assumptions)
        return registry
    except Exception as exc:
        logger.info("Rate registry unavailable; falling back to raw assumptions: %s", exc)
        return None

"""Connector-backed data access helpers for Planning Tie-Out."""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


def _monthly_series_to_rows(series: dict[date, float]) -> list[dict]:
    """Serialize a {month_start: value} mapping into stable JSON-friendly rows."""
    return [
        {"month": month.isoformat(), "total": float(total or 0.0)}
        for month, total in sorted((series or {}).items())
    ]


def _stable_override_cache_key(ae_overrides: Optional[dict]) -> str:
    """Serialize nested override payloads into a stable cache key."""
    if not ae_overrides:
        return "__base__"
    return json.dumps(ae_overrides, sort_keys=True, default=str)


def _parse_month_target_key(raw_month: Any) -> date:
    """Normalize month-target keys to a first-of-month date."""
    if isinstance(raw_month, date):
        return date(raw_month.year, raw_month.month, 1)

    month_str = str(raw_month or "").strip()
    if len(month_str) == 7:
        month_str = f"{month_str}-01"
    return date.fromisoformat(month_str[:10]).replace(day=1)


@dataclass
class TieoutDataAccess:
    """Resolve connector-backed snapshots and roster state.

    When `get_backend` is
    supplied and returns a non-None ProfileBackend, methods route through
    it (per ARCHITECTURE.md) before falling back to the legacy warehouse/SF gateway.
    Profiles using the legacy connector + data_dir fields keep the
    existing warehouse/SF-or-config behavior.
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

    def get_open_inventory_snapshot(self, as_of: Optional[date] = None):
        """Return the current open opportunity inventory.

        Resolution order (per ARCHITECTURE.md):
        1. ProfileBackend (CSV/Snowflake/Salesforce/custom) when configured
        2. Legacy warehouse gateway
        3. Legacy Salesforce gateway
        4. Empty snapshot (config-only mode)
        """
        from gtm_model.pipeline_rollforward import (
            OpenInventorySnapshot,
            build_open_inventory_snapshot_from_cdw,
            build_open_inventory_snapshot_from_salesforce,
        )

        as_of = as_of or date.today()
        cache = self.get_open_inventory_cache()
        if as_of in cache:
            return copy.deepcopy(cache[as_of])

        # Backend-first path (CSV / pluggable). Returns immediately when
        # the backend produces deals; falls through to warehouse/SF otherwise.
        backend_snapshot = self._open_inventory_from_backend(as_of)
        if backend_snapshot is not None and backend_snapshot.opportunities:
            cache[as_of] = copy.deepcopy(backend_snapshot)
            return backend_snapshot

        cdw_status = "not_attempted"

        cdw = self.get_cdw()
        if cdw is not None and not self.is_cdw_query_failed():
            try:
                rows = cdw.get_open_pipeline_detail()
                snapshot = build_open_inventory_snapshot_from_cdw(rows, as_of=as_of)
                if snapshot.opportunities:
                    cache[as_of] = copy.deepcopy(snapshot)
                    return snapshot
                cdw_status = "empty"
            except Exception as exc:
                logger.warning("Open inventory warehouse query failed: %s", exc)
                cdw_status = "query_failed"

        sf = self.get_sf()
        if sf is not None:
            try:
                rows = sf.get_pipeline_detail()
                snapshot = build_open_inventory_snapshot_from_salesforce(rows, as_of=as_of)
                if snapshot.opportunities:
                    snapshot.provenance["fallback_from"] = "warehouse"
                    snapshot.provenance["fallback_reason"] = cdw_status
                    cache[as_of] = copy.deepcopy(snapshot)
                    return snapshot
            except Exception as exc:
                logger.warning("Open inventory Salesforce query failed: %s", exc)

        snapshot = OpenInventorySnapshot(
            as_of=as_of,
            opportunities=[],
            provenance={
                "source": "unavailable",
                "is_live": False,
                "fallback_from": "warehouse",
                "fallback_reason": cdw_status,
            },
        )
        cache[as_of] = copy.deepcopy(snapshot)
        return snapshot

    def _open_inventory_from_backend(self, as_of: date):
        """Build a legacy-shape OpenInventorySnapshot from a ProfileBackend.

        Returns None when no backend is configured (legacy mode) or
        when the backend fetch raises. Returns an empty snapshot rather
        than None when the backend returns zero qualifying deals — the
        caller treats empty as "ProfileBackend was tried but had no data,"
        which is distinct from "no backend configured."
        """
        if self.get_backend is None:
            return None
        try:
            backend = self.get_backend()
        except Exception as exc:
            logger.warning("ProfileBackend resolution failed: %s", exc)
            return None
        if backend is None:
            return None

        from gtm_model.pipeline_rollforward import (
            OpenInventorySnapshot,
            OpenOpportunity,
            OPEN_STAGE_ORDER,
        )

        try:
            deals = backend.fetch_deals()
        except Exception as exc:
            logger.warning("ProfileBackend.fetch_deals() failed: %s", exc)
            return None

        opportunities: list[OpenOpportunity] = []
        for deal in deals:
            if deal.is_closed or deal.is_won:
                continue
            if deal.stage not in OPEN_STAGE_ORDER:
                continue
            opportunities.append(
                OpenOpportunity(
                    opp_id=deal.id,
                    stage=deal.stage,
                    amount=float(deal.amount or 0.0),
                    arr=float(deal.arr or 0.0),
                    close_date=deal.close_date,
                    created_date=deal.created_date,
                    source_stream=(deal.source_stream or deal.source or "unknown"),
                    opp_type=deal.type or "",
                    raw_stage_name=(deal.raw_stage or deal.stage),
                    record_type_name=deal.type or "",
                    forecast_category=deal.forecast_category or "",
                    owner_name=deal.owner_name or "",
                    metric_source=("ARR" if deal.arr else "Amount"),
                )
            )

        return OpenInventorySnapshot(
            as_of=as_of,
            opportunities=opportunities,
            provenance={
                "source": "ProfileBackend",
                "method": "backend_fetch_deals",
                "is_live": True,
                "opp_count": len(opportunities),
            },
        )

    def generate_staggered_start_dates(self, count: int) -> list[str]:
        """Generate staggered start dates for phantom AEs."""
        from gtm_model.roster import load_roster_data

        planned_dates: list[str] = []
        try:
            roster_data = load_roster_data(self.load_config_yaml("roster.yaml"))
            for entry in roster_data.get("planned", []):
                dt = entry.get("expected_start")
                if dt:
                    planned_dates.append(str(dt))
        except Exception:
            pass

        planned_dates.sort()
        today = date.today()
        future_planned = [entry for entry in planned_dates if date.fromisoformat(entry) >= today]

        if count <= len(future_planned):
            if count == 1:
                indices = [0]
            else:
                indices = [
                    round(i * (len(future_planned) - 1) / (count - 1))
                    for i in range(count)
                ]
            return [future_planned[idx] for idx in indices]

        result = list(future_planned)
        remaining = count - len(result)
        if remaining > 0:
            fy_end = date(2027, 1, 31)
            if future_planned:
                last_planned = date.fromisoformat(future_planned[-1])
                spread_start = (last_planned + relativedelta(months=1)).replace(day=1)
            else:
                spread_start = (today + relativedelta(months=1)).replace(day=1)

            if spread_start > fy_end:
                spread_start = fy_end.replace(day=1)

            months_available = max(
                (fy_end.year - spread_start.year) * 12
                + (fy_end.month - spread_start.month) + 1,
                1,
            )

            for index in range(remaining):
                month_offset = int(index * months_available / remaining)
                hire_date = spread_start + relativedelta(months=month_offset)
                if hire_date > fy_end:
                    hire_date = fy_end.replace(day=1)
                result.append(hire_date.isoformat())

        result.sort()
        return result

    def try_roster(self, ae_overrides: Optional[dict] = None) -> Optional[list[dict]]:
        """Build a full roster from warehouse plus YAML, or return `None` on failure.

        Per ARCHITECTURE.md: when a ProfileBackend is configured, its
        fetch_team_members() output is used as the active-AE input
        (replacing warehouse's get_active_aes). YAML augmentation
        (roster.yaml's planned hires + overrides) still applies on top.
        """
        cache_key = _stable_override_cache_key(ae_overrides)
        roster_cache = self.get_roster_cache()
        if cache_key in roster_cache:
            return copy.deepcopy(roster_cache[cache_key])
        try:
            from gtm_model.roster import get_full_roster_from_data, project_capacity_timeline

            sf_active_aes = []

            # Backend-first path: prefer ProfileBackend's team data over warehouse
            if self.get_backend is not None:
                try:
                    backend = self.get_backend()
                except Exception:
                    backend = None
                if backend is not None:
                    try:
                        members = backend.fetch_team_members()
                        sf_active_aes = [
                            {
                                "id": tm.id,
                                "name": tm.name,
                                "role": tm.role,
                                "segment": tm.segment,
                                "start_date": (
                                    tm.start_date.isoformat() if tm.start_date else None
                                ),
                                "is_active": tm.is_active,
                                "manager_id": tm.manager_id,
                            }
                            for tm in members
                            if tm.is_active
                        ]
                    except Exception as exc:
                        logger.warning(
                            "ProfileBackend.fetch_team_members() failed: %s", exc
                        )
                        sf_active_aes = []

            if not sf_active_aes:
                cdw = self.get_cdw()
                if cdw is not None and not self.is_cdw_query_failed():
                    try:
                        sf_active_aes = cdw.get_active_aes()
                    except Exception as exc:
                        logger.warning("warehouse active AEs query failed: %s", exc)

            roster = get_full_roster_from_data(
                sf_active_aes,
                self.load_config_yaml("roster.yaml"),
            )
            if not roster:
                return None

            if ae_overrides and "month_targets" in ae_overrides:
                normalized_targets = {
                    _parse_month_target_key(month): int(target)
                    for month, target in (ae_overrides.get("month_targets") or {}).items()
                    if int(target or 0) > 0
                }

                if normalized_targets:
                    start_month = min(normalized_targets)
                    end_month = max(normalized_targets)
                    span_months = (
                        (end_month.year - start_month.year) * 12
                        + (end_month.month - start_month.month)
                        + 1
                    )
                    next_override_index = (
                        sum(1 for entry in roster if str(entry.get("name", "")).startswith("Override AE "))
                        + 1
                    )

                    for target_month, target_total in sorted(normalized_targets.items()):
                        timeline = project_capacity_timeline(
                            roster=roster,
                            start_month=start_month,
                            months=span_months,
                        )
                        current_total = next(
                            (row.get("total_count", 0) for row in timeline if row.get("month") == target_month),
                            0,
                        )
                        shortfall = max(int(target_total) - int(current_total), 0)
                        for _ in range(shortfall):
                            roster.append({
                                "name": f"Override AE {next_override_index}",
                                "segment": "enterprise",
                                "start_date": target_month.isoformat(),
                                "tier": "planned",
                            })
                            next_override_index += 1
            elif ae_overrides and "add_aes" in ae_overrides:
                add_count = ae_overrides["add_aes"]
                staggered_dates = self.generate_staggered_start_dates(add_count)
                for index in range(add_count):
                    roster.append({
                        "name": f"Override AE {index + 1}",
                        "segment": "enterprise",
                        "start_date": staggered_dates[index],
                        "tier": "planned",
                    })
            elif ae_overrides and "total_aes" in ae_overrides:
                target = ae_overrides["total_aes"]
                current = len(roster)
                if target > current:
                    add_count = target - current
                    staggered_dates = self.generate_staggered_start_dates(add_count)
                    for index in range(add_count):
                        roster.append({
                            "name": f"Override AE {index + 1}",
                            "segment": "enterprise",
                            "start_date": staggered_dates[index],
                            "tier": "planned",
                        })

            roster_cache[cache_key] = copy.deepcopy(roster)
            return roster
        except Exception as exc:
            logger.warning("Roster build failed: %s", exc)
            roster_cache[cache_key] = None
            return None

    def get_beginning_arr_snapshot(self) -> tuple[float, dict]:
        """Resolve FY beginning ARR using active won-opportunity window logic.

        Resolution order (per ARCHITECTURE.md):
        1. ProfileBackend.compute_beginning_arr() when configured
        2. Legacy warehouse gateway
        3. Legacy Salesforce gateway
        4. targets.yaml config fallback
        """
        cached = self.get_beginning_arr_cache()
        if cached is not None:
            return cached

        targets = self.get_targets()
        quarter_dates = self.get_quarter_dates()
        fallback_arr = float(targets.get("beginning_arr", 0.0) or 0.0)
        # Pick the first (chronologically earliest) quarter as the fiscal-year
        # start anchor. quarter_dates is an ordered dict keyed by quarter label;
        # iteration order = chronological order per get_quarter_dates contract.
        first_q_label = next(iter(quarter_dates), None)
        first_q_start = quarter_dates[first_q_label][0] if first_q_label else None
        fiscal_year_start = (
            targets.get("fiscal_year_start")
            or (first_q_start.isoformat() if first_q_start else None)
        )
        period_start = first_q_start

        fallback = (
            fallback_arr,
            {
                "value": fallback_arr,
                "source": "targets.yaml",
                "method": "top_down_config_fallback",
                "as_of": fiscal_year_start,
                "is_live": False,
                "warning": "Using configured beginning ARR because a credible CRM-derived start-of-year ARR base was not available.",
            },
        )

        # Backend-first path
        if period_start is not None and self.get_backend is not None:
            try:
                backend = self.get_backend()
            except Exception:
                backend = None
            if backend is not None:
                try:
                    arr_snapshot = backend.compute_beginning_arr(
                        period_start=period_start,
                        fallback_arr=fallback_arr,
                        fallback_label="targets.yaml",
                    )
                    value, provenance = arr_snapshot.to_tuple()
                    if value > 0 and arr_snapshot.is_live:
                        # Backend produced a real signal — use it.
                        resolved = (value, provenance)
                        self.set_beginning_arr_cache(resolved)
                        return resolved
                except Exception as exc:
                    logger.warning("ProfileBackend beginning ARR failed: %s", exc)

        cdw = self.get_cdw()
        try:
            if cdw is not None and not self.is_cdw_query_failed():
                snapshot = cdw.get_beginning_arr_snapshot(period_start)
                value = float(snapshot.get("total_year1_arr") or 0.0)
                if value > 0:
                    resolved = (
                        value,
                        {
                            "value": value,
                            "source": "warehouse",
                            "method": "active_won_opportunity_window",
                            "metric_used": "YEAR_1_ARR__c",
                            "as_of": fiscal_year_start,
                            "is_live": True,
                            "opp_count": int(snapshot.get("opp_count") or 0),
                            "snapshot": snapshot,
                        },
                    )
                    self.set_beginning_arr_cache(resolved)
                    return resolved
        except Exception as exc:
            logger.warning("warehouse beginning ARR snapshot failed: %s", exc)

        sf = self.get_sf()
        if sf is None:
            self.set_beginning_arr_cache(fallback)
            return fallback

        try:
            snapshot = sf.get_beginning_arr_snapshot(period_start)
            year1_arr = float(snapshot.get("total_year1_arr") or 0.0)
            arr = float(snapshot.get("total_arr") or 0.0)
            chosen_value = year1_arr if year1_arr > 0 else arr
            metric_used = "Year_1_ARR__c" if year1_arr > 0 else "ARR__c"
            if chosen_value > 0:
                resolved = (
                    chosen_value,
                    {
                        "value": chosen_value,
                        "source": "Salesforce",
                        "method": "active_won_opportunity_window",
                        "metric_used": metric_used,
                        "as_of": fiscal_year_start,
                        "is_live": True,
                        "opp_count": int(snapshot.get("opp_count") or 0),
                        "snapshot": snapshot,
                    },
                )
                self.set_beginning_arr_cache(resolved)
                return resolved
        except Exception as exc:
            logger.warning("Salesforce beginning ARR snapshot failed; using config fallback: %s", exc)
            provenance = dict(fallback[1])
            provenance["warning"] = f"Salesforce ARR snapshot failed: {exc}"
            resolved = (fallback_arr, provenance)
            self.set_beginning_arr_cache(resolved)
            return resolved

        self.set_beginning_arr_cache(fallback)
        return fallback

    def _cache_bookings_summary(self, cache_key: str, resolved) -> None:
        """Write a finance-summary result into the as_of-keyed cache.

        Tolerates a legacy single-tuple cache shape: if the current
        cache isn't a dict, replace it with one keyed under cache_key.
        """
        cached = self.get_bookings_summary_cache()
        if not isinstance(cached, dict):
            cached = {}
        cached[cache_key] = resolved
        self.set_bookings_summary_cache(cached)

    def get_closed_won_finance_summary(
        self, as_of: Optional[date] = None
    ) -> tuple[dict, dict]:
        """Return closed-won finance totals for Amount vs ARR vs NACV display.

        Cache is keyed by `as_of` so repeated calls with different cutoff
        dates don't return stale results (e.g. parity-test reruns under
        different --as-of values within a single PlanningTieout instance).
        """
        cache_key = as_of.isoformat() if as_of is not None else "__today__"
        cached = self.get_bookings_summary_cache()
        if isinstance(cached, dict) and cache_key in cached:
            return cached[cache_key]

        empty_summary = {
            "totals": {
                "won_count": 0,
                "amount": 0.0,
                "year1_arr": 0.0,
                "arr": 0.0,
                "nacv": 0.0,
                "non_recurring": 0.0,
            },
            "by_type": {},
        }
        empty_provenance = {
            "source": "unavailable",
            "method": "none",
            "warning": "Closed-won finance summary unavailable.",
            "is_live": False,
        }

        # Pick the first quarter chronologically — quarter_dates iteration
        # order is fiscal-year-start order per the contract.
        _quarter_dates = self.get_quarter_dates()
        _first_q_label = next(iter(_quarter_dates), None)
        period_start = _quarter_dates[_first_q_label][0] if _first_q_label else date.today()
        # Honor --as-of for deterministic snapshots (per ARCHITECTURE.md).
        period_end = as_of or date.today()
        cdw_status = "not_attempted"

        # Backend-first path (per ARCHITECTURE.md)
        if self.get_backend is not None:
            try:
                backend = self.get_backend()
            except Exception:
                backend = None
            if backend is not None:
                try:
                    summary_obj = backend.compute_closed_won_finance_summary(
                        period_start, period_end
                    )
                    summary_dict = summary_obj.to_dict()
                    if summary_dict["totals"]["won_count"] > 0:
                        resolved = (
                            summary_dict,
                            {
                                "source": "ProfileBackend",
                                "method": "backend_compute_closed_won_finance_summary",
                                "is_live": True,
                                "period": summary_dict.get("period", {}),
                            },
                        )
                        self._cache_bookings_summary(cache_key, resolved)
                        return resolved
                except Exception as exc:
                    logger.warning(
                        "ProfileBackend closed-won finance summary failed: %s", exc
                    )

        try:
            cdw = self.get_cdw()
            if cdw is not None and not self.is_cdw_query_failed():
                summary = cdw.get_closed_won_finance_summary(
                    start_date=period_start,
                    end_date=period_end,
                )
                resolved = (
                    summary,
                    {
                        "source": "warehouse",
                        "method": "closed_won_aggregate",
                        "is_live": True,
                        "period": summary.get("period", {}),
                        "snapshot_time": summary.get("snapshot_time"),
                        "warning": "NACV may be 0 if your warehouse doesn't replicate the source NACV field.",
                    },
                )
                self._cache_bookings_summary(cache_key, resolved)
                return resolved
        except Exception as exc:
            logger.warning("warehouse closed-won finance summary failed: %s", exc)
            cdw_status = "query_failed"

        sf = self.get_sf()
        try:
            if sf is not None:
                summary = sf.get_closed_won_finance_summary(
                    start_date=period_start,
                    end_date=period_end,
                )
                resolved = (
                    summary,
                    {
                        "source": "Salesforce",
                        "method": "closed_won_aggregate",
                        "is_live": True,
                        "period": summary.get("period", {}),
                        "snapshot_time": summary.get("snapshot_time"),
                        "fallback_from": "warehouse",
                        "fallback_reason": cdw_status,
                    },
                )
                self._cache_bookings_summary(cache_key, resolved)
                return resolved
        except Exception as exc:
            logger.warning("Salesforce closed-won finance summary failed: %s", exc)

        resolved = (empty_summary, empty_provenance)
        self._cache_bookings_summary(cache_key, resolved)
        return resolved

    def _resolve_monthly_amount_series(
        self,
        *,
        start_date: date,
        end_date: date,
        cdw_loader: Callable[[Any, date, date], dict[date, float]],
        sf_loader: Callable[[Any, date, date], dict[date, float]],
        cdw_method: str,
        sf_method: str,
        unavailable_warning: str,
    ) -> tuple[dict[date, float], dict]:
        """Resolve a monthly amount series from warehouse first, then Salesforce."""
        period = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        cdw_status = "not_attempted"

        try:
            cdw = self.get_cdw()
            if cdw is not None and not self.is_cdw_query_failed():
                series = dict(cdw_loader(cdw, start_date, end_date) or {})
                return (
                    series,
                    {
                        "source": "warehouse",
                        "method": cdw_method,
                        "is_live": True,
                        "period": period,
                        "points": len(series),
                    },
                )
            cdw_status = "unavailable"
        except Exception as exc:
            logger.warning("warehouse monthly series failed (%s): %s", cdw_method, exc)
            cdw_status = "query_failed"

        try:
            sf = self.get_sf()
            if sf is not None:
                series = dict(sf_loader(sf, start_date, end_date) or {})
                return (
                    series,
                    {
                        "source": "Salesforce",
                        "method": sf_method,
                        "is_live": True,
                        "period": period,
                        "points": len(series),
                        "fallback_from": "warehouse",
                        "fallback_reason": cdw_status,
                    },
                )
        except Exception as exc:
            logger.warning("Salesforce monthly series failed (%s): %s", sf_method, exc)

        return (
            {},
            {
                "source": "unavailable",
                "method": "none",
                "is_live": False,
                "period": period,
                "warning": unavailable_warning,
            },
        )

    def get_monthly_actuals(
        self,
        as_of: date,
        months: int = 12,
        fy_start: date | None = None,
    ) -> dict:
        """Return canonical monthly actuals for the saved snapshot artifact.

        The generator and any audit-grade consumers should read these series
        through the shared runtime snapshot instead of issuing ad hoc
        connector-specific queries.

        Resolution order (per ARCHITECTURE.md): ProfileBackend first, then
        warehouse per-series fallbacks, then SF, then empty.
        """
        del months  # The current artifact only serializes completed months through as_of.
        start_date = fy_start or date(as_of.year - 1, as_of.month, 1)
        end_date = as_of

        # Backend-first path
        backend_result = self._monthly_actuals_from_backend(start_date, end_date)
        if backend_result is not None:
            return backend_result

        bookings_by_month, bookings_provenance = self._resolve_monthly_amount_series(
            start_date=start_date,
            end_date=end_date,
            cdw_loader=lambda cdw, start, end: cdw.get_monthly_bookings(start, end),
            sf_loader=lambda sf, start, end: sf.get_monthly_bookings(start, end),
            cdw_method="monthly_closed_won_close_date_amount",
            sf_method="monthly_closed_won_close_date_amount",
            unavailable_warning="Monthly bookings actuals unavailable.",
        )

        losses_by_month, losses_provenance = self._resolve_monthly_amount_series(
            start_date=start_date,
            end_date=end_date,
            cdw_loader=lambda cdw, start, end: cdw.get_monthly_closed_lost(start, end),
            sf_loader=lambda sf, start, end: sf.get_monthly_closed_lost(start, end),
            cdw_method="monthly_closed_lost_closed_at_amount",
            sf_method="monthly_closed_lost_closed_at_amount",
            unavailable_warning="Monthly losses actuals unavailable.",
        )

        pipeline_created_by_month, pipeline_provenance = self._resolve_monthly_amount_series(
            start_date=start_date,
            end_date=end_date,
            cdw_loader=lambda cdw, start, end: cdw.get_monthly_pipeline_creation(start, end),
            sf_loader=lambda sf, start, end: sf.get_monthly_pipeline_creation(start, end),
            cdw_method="monthly_opp_created_amount_for_s2_plus_or_closed",
            sf_method="monthly_opp_created_amount_for_s2_plus_or_closed",
            unavailable_warning="Monthly opportunity creation actuals unavailable.",
        )

        pipeline_entered_s2_by_month, pipeline_entered_s2_provenance = self._resolve_monthly_amount_series(
            start_date=start_date,
            end_date=end_date,
            cdw_loader=lambda cdw, start, end: cdw.get_monthly_s2_created(start, end),
            sf_loader=lambda sf, start, end: sf.get_monthly_s2_created(start, end),
            cdw_method="monthly_entered_s2_amount",
            sf_method="monthly_entered_s2_amount",
            unavailable_warning="Monthly S2-entry actuals unavailable.",
        )

        return {
            "bookings_by_month": _monthly_series_to_rows(bookings_by_month),
            "losses_by_month": _monthly_series_to_rows(losses_by_month),
            "pipeline_created_by_month": _monthly_series_to_rows(pipeline_created_by_month),
            "pipeline_entered_s2_by_month": _monthly_series_to_rows(pipeline_entered_s2_by_month),
            "provenance": {
                "bookings_by_month": bookings_provenance,
                "losses_by_month": losses_provenance,
                "pipeline_created_by_month": pipeline_provenance,
                "pipeline_entered_s2_by_month": pipeline_entered_s2_provenance,
            },
        }

    def _monthly_actuals_from_backend(
        self, start_date: date, end_date: date
    ) -> Optional[dict]:
        """Compute monthly actuals from a ProfileBackend.

        Returns None when no backend is configured (legacy mode falls
        through to the warehouse/SF chain). Returns the legacy-shape dict
        with all four series populated when the backend has data.
        """
        if self.get_backend is None:
            return None
        try:
            backend = self.get_backend()
        except Exception:
            return None
        if backend is None:
            return None
        try:
            actuals = backend.compute_monthly_actuals(start_date, end_date)
        except Exception as exc:
            logger.warning("ProfileBackend monthly actuals failed: %s", exc)
            return None

        provenance = {
            "source": "ProfileBackend",
            "method": "backend_compute_monthly_actuals",
            "is_live": True,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        rows = actuals.as_rows()
        return {
            "bookings_by_month": rows["monthly_bookings"],
            "losses_by_month": rows["monthly_closed_lost"],
            "pipeline_created_by_month": rows["monthly_pipeline_creation"],
            "pipeline_entered_s2_by_month": rows["monthly_entered_s2"],
            "provenance": {
                "bookings_by_month": dict(provenance, series="bookings"),
                "losses_by_month": dict(provenance, series="losses"),
                "pipeline_created_by_month": dict(provenance, series="creation"),
                "pipeline_entered_s2_by_month": dict(provenance, series="entered_s2"),
            },
        }

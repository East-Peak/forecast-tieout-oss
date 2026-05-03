#!/usr/bin/env python3
"""
Generate a static JSON snapshot for the React frontend.

Bootstraps the GTM Intelligence tieout engine, runs both scenarios,
and serializes the result into the structure expected by the TypeScript
Snapshot interface.

Usage:
    python scripts/generate_snapshot.py
    python scripts/generate_snapshot.py --profile-id default
    python scripts/generate_snapshot.py --all-profiles

Default compatibility output: frontend/public/data/snapshot.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the repo root is on sys.path so `gtm_model` is importable
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Import after sys.path is set up so the gtm_model package resolves.
from gtm_model.tieout.infra.plan_config import PlanConfigValidationError  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("generate_snapshot")

DEFAULT_DATA_ROOT = REPO_ROOT / "frontend" / "public" / "data"
DEFAULT_SNAPSHOT_OUTPUT = DEFAULT_DATA_ROOT / "snapshot.json"
DEFAULT_PROFILES_OUTPUT = DEFAULT_DATA_ROOT / "profiles"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    env_sha = str(os.getenv("GTM_TIEOUT_GIT_SHA", "")).strip()
    if env_sha:
        return env_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _to_iso(value) -> str | None:
    """Convert date/datetime to ISO string, or return None."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        f = float(value)
        if f != f:  # NaN check
            return default
        return f
    except (TypeError, ValueError):
        return default


def _serialize_deal(opp) -> dict:
    return {
        "opp_id": str(opp.opp_id or ""),
        "stage": str(opp.stage or ""),
        "amount": _safe_float(opp.amount),
        "arr": _safe_float(opp.arr),
        "metric_value": _safe_float(opp.metric_value),
        "close_date": _to_iso(getattr(opp, "close_date", None)),
        "created_date": _to_iso(getattr(opp, "created_date", None)),
        "source_stream": str(getattr(opp, "source_stream", "") or ""),
        "owner_name": str(getattr(opp, "owner_name", "") or ""),
        "opp_type": str(getattr(opp, "opp_type", "") or ""),
        "forecast_category": str(getattr(opp, "forecast_category", "") or ""),
    }


def _build_inventory_by_stage(deals: list[dict]) -> list[dict]:
    stage_buckets: dict[str, dict] = {}
    for d in deals:
        stage = d["stage"]
        if stage not in stage_buckets:
            stage_buckets[stage] = {"stage": stage, "count": 0, "total_value": 0.0}
        stage_buckets[stage]["count"] += 1
        stage_buckets[stage]["total_value"] += d["metric_value"]
    # Order by canonical stage ordering
    stage_order = ["S0", "S1", "S2", "S3", "S4", "S5"]
    ordered = []
    for s in stage_order:
        if s in stage_buckets:
            ordered.append(stage_buckets[s])
    # Append any non-standard stages
    for s, v in stage_buckets.items():
        if s not in stage_order:
            ordered.append(v)
    return ordered


def _months_to_iso(months) -> list[str]:
    result = []
    for m in (months or []):
        result.append(_to_iso(m) or "")
    return result


def _quarterly_to_dicts(quarters) -> list[dict]:
    result = []
    for q in (quarters or []):
        if hasattr(q, "to_dict"):
            d = q.to_dict()
        else:
            d = dict(q)
        # Ensure period_start / period_end are ISO strings
        for key in ("period_start", "period_end"):
            if key in d and hasattr(d[key], "isoformat"):
                d[key] = d[key].isoformat()
        result.append(d)
    return result


def _capacity_to_dicts(capacity_rows) -> list[dict]:
    result = []
    for row in (capacity_rows or []):
        if hasattr(row, "to_dict"):
            d = row.to_dict()
        else:
            d = dict(row)
        if "month" in d and hasattr(d["month"], "isoformat"):
            d["month"] = d["month"].isoformat()
        result.append(d)
    return result


def _source_detail_to_serializable(source_detail) -> list[dict]:
    result = []
    for row in (source_detail or []):
        serialized = {}
        for k, v in (row or {}).items():
            if hasattr(v, "isoformat"):
                serialized[k] = v.isoformat()
            else:
                serialized[k] = v
        result.append(serialized)
    return result


def _serialize_mapping(record) -> dict:
    serialized = {}
    for k, v in (dict(record or {})).items():
        if hasattr(v, "isoformat"):
            serialized[k] = v.isoformat()
        else:
            serialized[k] = v
    return serialized


def _get_ramp_months(observed_ae_ramp_curve: dict) -> float:
    """Find the month index where ramp fraction first reaches >= 0.8."""
    curve = observed_ae_ramp_curve or {}
    # curve may be a dict keyed by month integer with fraction values,
    # or have a 'curve' list, or 'ramp_curve' list
    ramp_list = None
    if isinstance(curve, dict):
        ramp_list = curve.get("ramp_curve") or curve.get("curve") or curve.get("monthly_ramp")
        if ramp_list is None:
            # try numeric keys (month -> fraction)
            numeric_keys = {k: v for k, v in curve.items() if isinstance(k, (int, float))}
            if numeric_keys:
                max_month = max(numeric_keys.keys())
                ramp_list = [numeric_keys.get(i, 0.0) for i in range(int(max_month) + 1)]
    if ramp_list:
        for i, val in enumerate(ramp_list):
            if _safe_float(val) >= 0.8:
                return float(i + 1)  # 1-indexed months
    return 6.0  # fallback: 6 months


def _get_avg_deal_size(observed_ae_productivity: dict) -> float:
    prod = observed_ae_productivity or {}
    for key in ("avg_deal_size", "average_deal_size", "deal_size"):
        if key in prod:
            return _safe_float(prod[key])
    # Derive from productivity / win rate if available
    productivity = _safe_float(prod.get("productivity_per_ae_per_month") or prod.get("s0_per_ae_per_month") or 0)
    return 0.0


def _extract_source_creation(monthly_source_detail, month_idx: int, month_key: str) -> tuple[float, float]:
    """Return (ae_creation, mql_creation) for a given month index.

    The trajectory serializer emits one flat row per source stream per month.
    Older snapshot code expected one nested row per month. Support both shapes
    so the static artifact always carries a real AE/MQL split when available.
    """
    try:
        if not monthly_source_detail:
            return 0.0, 0.0
        ae_total = 0.0
        mql_total = 0.0
        normalized_month = (month_key or "")[:7]
        matched_flat_rows = False

        for row in monthly_source_detail:
            if not isinstance(row, dict):
                continue
            row_month = str(row.get("month") or "")[:7]
            if not row_month or row_month != normalized_month:
                continue

            source_name = str(row.get("source") or row.get("stream") or "").lower()
            creation = _safe_float(row.get("pipeline_created") or row.get("creation") or 0)
            matched_flat_rows = True

            if any(token in source_name for token in ("marketing", "sdr", "mql")):
                mql_total += creation
            elif any(token in source_name for token in ("ae", "self-gen", "selfgen")):
                ae_total += creation

        if matched_flat_rows:
            return ae_total, mql_total

        if month_idx >= len(monthly_source_detail):
            return 0.0, 0.0

        row = monthly_source_detail[month_idx] or {}
        for stream_key, stream_data in row.items():
            if stream_key == "month" or not isinstance(stream_data, dict):
                continue
            creation = _safe_float(stream_data.get("creation", 0))
            if "ae" in stream_key.lower() or "selfgen" in stream_key.lower():
                ae_total += creation
            elif "marketing" in stream_key.lower() or "sdr" in stream_key.lower() or "mql" in stream_key.lower():
                mql_total += creation
            else:
                ae_total += creation
        return ae_total, mql_total
    except Exception:
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_snapshot(
    plan_case_id: str | None = None,
    profile_id: str | None = None,
    as_of: "date | None" = None,
) -> dict:
    """Build a snapshot dict for the given profile.

    Args:
        plan_case_id: Plan case to use (default: profile's configured).
        profile_id: Org profile id (default: active/configured).
        as_of: Override the snapshot's reference date. None → date.today()
            (production default). Per ARCHITECTURE.md, required for parity tests
            and CI smoke runs to produce deterministic output.
    """
    from gtm_model.tieout import PlanningTieout

    logger.info(
        "Bootstrapping PlanningTieout(plan_case_id=%r, profile_id=%r)...",
        plan_case_id,
        profile_id,
    )
    tieout = PlanningTieout(plan_case_id=plan_case_id, profile_id=profile_id)

    logger.info("Building runtime snapshot (as_of=%s)...", as_of or "today")
    try:
        # Pass as_of through to runtime snapshot if PlanningTieout's API
        # accepts it. Older builds didn't accept the kwarg, so we feature-
        # detect and call accordingly.
        try:
            runtime = tieout.public_api.build_runtime_snapshot(as_of=as_of)
        except TypeError:
            # Fallback: legacy signature without as_of.
            runtime = tieout.public_api.build_runtime_snapshot()
    except Exception as exc:
        logger.error("build_runtime_snapshot() failed: %s", exc)
        raise

    logger.info("Running compute_full()...")
    try:
        result = tieout.public_api.compute_full(runtime_snapshot=runtime)
    except Exception as exc:
        logger.error("compute_full() failed: %s", exc)
        raise

    traj = result.trajectory
    base = result.base
    as_of_date = getattr(runtime, "as_of", None) or date.today()

    # -----------------------------------------------------------------------
    # actuals — read the canonical runtime snapshot payload instead of issuing
    # script-local connector queries. This keeps the saved artifact aligned
    # with health checks, quarter actuals, and runtime provenance.
    # -----------------------------------------------------------------------
    logger.info("Serializing actuals...")
    monthly_actuals = {}
    actuals_provenance: dict[str, dict] = {}
    bookings_by_month: list[dict] = []
    losses_by_month: list[dict] = []
    pipeline_created_by_month: list[dict] = []
    pipeline_entered_s2_by_month: list[dict] = []
    try:
        monthly_actuals = getattr(runtime, "monthly_actuals", None) or {}
        bookings_by_month = list(monthly_actuals.get("bookings_by_month") or [])
        losses_by_month = list(monthly_actuals.get("losses_by_month") or [])
        pipeline_created_by_month = list(monthly_actuals.get("pipeline_created_by_month") or [])
        pipeline_entered_s2_by_month = list(monthly_actuals.get("pipeline_entered_s2_by_month") or [])
        actuals_provenance = {
            str(key): _serialize_mapping(value)
            for key, value in dict(monthly_actuals.get("provenance") or {}).items()
        }
        logger.info(
            "Loaded canonical monthly actuals: bookings=%d losses=%d opp_created=%d s2_entered=%d",
            len(bookings_by_month),
            len(losses_by_month),
            len(pipeline_created_by_month),
            len(pipeline_entered_s2_by_month),
        )
    except Exception as exc:
        logger.warning("Could not extract canonical monthly actuals: %s", exc)

    # -----------------------------------------------------------------------
    # actuals.mql_by_month
    # -----------------------------------------------------------------------
    mql_by_month: list[dict] = []
    try:
        mql_actuals = getattr(runtime, "monthly_mql_actuals", None) or []
        for idx, val in enumerate(mql_actuals):
            if val is not None:
                mql_by_month.append({"month_index": idx, "value": _safe_float(val)})
    except Exception as exc:
        logger.warning("Could not extract mql_by_month: %s", exc)

    # -----------------------------------------------------------------------
    # pipeline.deals + inventory_by_stage
    # -----------------------------------------------------------------------
    logger.info("Serializing pipeline inventory...")
    deals: list[dict] = []
    pipeline_provenance: dict = {}
    try:
        inv_snap = getattr(runtime, "open_inventory_snapshot", None)
        if inv_snap is not None:
            opps = getattr(inv_snap, "opportunities", []) or []
            deals = [_serialize_deal(o) for o in opps]
            pipeline_provenance = dict(getattr(inv_snap, "provenance", {}) or {})
    except Exception as exc:
        logger.warning("Could not extract open_inventory_snapshot: %s", exc)

    inventory_by_stage = _build_inventory_by_stage(deals)

    # -----------------------------------------------------------------------
    # rates
    # -----------------------------------------------------------------------
    logger.info("Serializing rates...")
    stage_conversion: dict = {}
    try:
        stage_conversion = dict(getattr(runtime, "stage_win_rates", {}) or {})
    except Exception as exc:
        logger.warning("stage_win_rates failed: %s", exc)

    stage_velocity_days: dict = {}
    try:
        stage_velocity_days = dict(getattr(runtime, "stage_velocity_days", {}) or {})
    except Exception as exc:
        logger.warning("stage_velocity_days failed: %s", exc)

    runtime_funnel_rates: dict = {}
    try:
        runtime_funnel_rates = dict(getattr(runtime, "runtime_funnel_rates", {}) or {})
    except Exception as exc:
        logger.warning("runtime_funnel_rates failed: %s", exc)

    s2_to_won = _safe_float(getattr(runtime, "s2_to_won_rate", None))

    # -----------------------------------------------------------------------
    # roster
    # -----------------------------------------------------------------------
    logger.info("Serializing roster...")
    current_aes: list[dict] = []
    try:
        raw_roster = getattr(runtime, "roster", None) or []
        current_aes = [dict(r) for r in raw_roster]
    except Exception as exc:
        logger.warning("roster failed: %s", exc)

    trajectory_roster: dict = {}
    try:
        trajectory_roster = dict(getattr(runtime, "trajectory_roster", None) or {})
    except Exception as exc:
        logger.warning("trajectory_roster failed: %s", exc)

    trajectory_roster_meta: dict = {}
    try:
        trajectory_roster_meta = dict(getattr(runtime, "trajectory_roster_meta", None) or {})
    except Exception as exc:
        logger.warning("trajectory_roster_meta failed: %s", exc)

    observed_productivity: dict = {}
    try:
        observed_productivity = dict(getattr(runtime, "observed_ae_productivity", None) or {})
    except Exception as exc:
        logger.warning("observed_ae_productivity failed: %s", exc)

    observed_ramp_curve: dict = {}
    try:
        observed_ramp_curve = dict(getattr(runtime, "observed_ae_ramp_curve", None) or {})
    except Exception as exc:
        logger.warning("observed_ae_ramp_curve failed: %s", exc)

    self_serve_velocity: dict = {}
    try:
        self_serve_velocity = _serialize_mapping(getattr(runtime, "self_serve_velocity", None) or {})
    except Exception as exc:
        logger.warning("self_serve_velocity failed: %s", exc)

    trailing_mql_signal_source = "unavailable"
    try:
        trailing_signal = getattr(runtime, "trailing_mql_weekly_signal", None)
        if isinstance(trailing_signal, tuple) and len(trailing_signal) >= 2:
            trailing_mql_signal_source = str(trailing_signal[1] or "unavailable")
    except Exception as exc:
        logger.warning("trailing_mql_weekly_signal failed: %s", exc)

    # Effective capacity from trajectory scenario
    effective_capacity: list[dict] = []
    try:
        effective_capacity = _capacity_to_dicts(getattr(traj, "monthly_capacity", None) or [])
    except Exception as exc:
        logger.warning("monthly_capacity (trajectory) failed: %s", exc)

    # -----------------------------------------------------------------------
    # model_output — bookings_bridge (trajectory)
    # -----------------------------------------------------------------------
    logger.info("Serializing model_output...")
    traj_months = _months_to_iso(getattr(traj, "monthly_months", []))
    base_months = _months_to_iso(getattr(base, "monthly_months", []))

    # Pad/align plan lists to match trajectory month count
    n_months = len(traj_months)

    def _pad(lst, n=n_months) -> list:
        lst = list(lst or [])
        if len(lst) < n:
            lst = lst + [0.0] * (n - len(lst))
        return lst[:n]

    traj_existing_wins = _pad(getattr(traj, "monthly_existing_inventory_wins", []))
    traj_future_wins = _pad(getattr(traj, "monthly_future_generation_wins", []))
    traj_total_expected = _pad(getattr(traj, "monthly_total_expected_wins", []))
    traj_capped = _pad(getattr(traj, "monthly_bookings_capped", []))
    traj_overflow = _pad(getattr(traj, "monthly_overflow", []))

    base_existing_wins = _pad(getattr(base, "monthly_existing_inventory_wins", []))
    base_future_wins = _pad(getattr(base, "monthly_future_generation_wins", []))
    base_total_expected = _pad(getattr(base, "monthly_total_expected_wins", []))

    traj_source_detail = _source_detail_to_serializable(getattr(traj, "monthly_source_detail", []))
    traj_provenance = dict(getattr(traj, "monthly_rollforward_provenance", {}) or {})

    bookings_bridge = {
        "months": traj_months,
        "existing_wins": traj_existing_wins,
        "future_wins": traj_future_wins,
        "total_expected": traj_total_expected,
        "capped": traj_capped,
        "overflow": traj_overflow,
        "plan_existing_wins": base_existing_wins,
        "plan_future_wins": base_future_wins,
        "plan_total": base_total_expected,
        "trajectory_quarters": _quarterly_to_dicts(getattr(traj, "quarters", [])),
        "plan_quarters": _quarterly_to_dicts(getattr(base, "quarters", [])),
        "provenance": traj_provenance,
        "source_detail": traj_source_detail,
        "capacity_warnings": list(getattr(traj, "capacity_warnings", []) or []),
    }

    # -----------------------------------------------------------------------
    # model_output — capacity_headcount
    # -----------------------------------------------------------------------
    plan_capacity = _capacity_to_dicts(getattr(base, "monthly_capacity", None) or [])

    capacity_headcount = {
        "trajectory_capacity": effective_capacity,
        "plan_capacity": plan_capacity,
        "trajectory_quarters": _quarterly_to_dicts(getattr(traj, "quarters", [])),
        "plan_quarters": _quarterly_to_dicts(getattr(base, "quarters", [])),
    }

    # -----------------------------------------------------------------------
    # model_output — funnel_health
    # -----------------------------------------------------------------------
    rolling_s2_to_won: dict = {}
    try:
        rolling_s2_to_won = dict(getattr(runtime, "rolling_s2_to_won_rate", None) or {})
    except Exception as exc:
        logger.warning("rolling_s2_to_won_rate failed: %s", exc)

    funnel_rate_descriptions: dict = {}
    try:
        funnel_rate_descriptions = dict(getattr(runtime, "runtime_funnel_rate_descriptions", None) or {})
    except Exception as exc:
        logger.warning("runtime_funnel_rate_descriptions failed: %s", exc)

    funnel_health = {
        "trajectory_quarters": _quarterly_to_dicts(getattr(traj, "quarters", [])),
        "plan_quarters": _quarterly_to_dicts(getattr(base, "quarters", [])),
        "funnel_rates": runtime_funnel_rates,
        "funnel_rate_descriptions": funnel_rate_descriptions,
        "mql_actuals": mql_by_month,
        "rolling_s2_to_won": rolling_s2_to_won,
    }

    # -----------------------------------------------------------------------
    # model_output — pipeline_inventory
    # -----------------------------------------------------------------------
    traj_existing_losses = _pad(getattr(traj, "monthly_existing_inventory_losses", []))
    traj_existing_remaining = _pad(getattr(traj, "monthly_existing_inventory_remaining", []))
    traj_pipeline_creation = _pad(getattr(traj, "monthly_pipeline_creation", []))

    pipeline_inventory = {
        "months": traj_months,
        "existing_wins": traj_existing_wins,
        "existing_losses": traj_existing_losses,
        "existing_remaining": traj_existing_remaining,
        "future_wins": traj_future_wins,
        "pipeline_creation": traj_pipeline_creation,
        "provenance": traj_provenance,
    }

    # -----------------------------------------------------------------------
    # scenario_building_blocks
    # -----------------------------------------------------------------------
    logger.info("Building scenario_building_blocks...")

    # monthly_is_actual: months before as_of are actuals
    monthly_is_actual: list[bool] = []
    for m_str in traj_months:
        try:
            m_date = date.fromisoformat(m_str[:10]) if m_str else None
            monthly_is_actual.append(bool(m_date and m_date < as_of_date))
        except (ValueError, TypeError):
            monthly_is_actual.append(False)

    # AE count and capacity from monthly_capacity rows
    monthly_ae_count: list[float] = []
    monthly_ae_capacity: list[float] = []
    monthly_ae_ramped: list[float] = []
    monthly_blended_ramp: list[float] = []
    for row in (effective_capacity or []):
        monthly_ae_count.append(_safe_float(row.get("ae_total")))
        monthly_ae_capacity.append(_safe_float(row.get("ae_capacity")))
        monthly_ae_ramped.append(_safe_float(row.get("ae_ramped")))
        monthly_blended_ramp.append(_safe_float(row.get("blended_ramp_pct")))
    # Pad to match traj_months
    monthly_ae_count = _pad(monthly_ae_count)
    monthly_ae_capacity = _pad(monthly_ae_capacity)
    monthly_ae_ramped = _pad(monthly_ae_ramped)
    monthly_blended_ramp = _pad(monthly_blended_ramp)

    # AE vs MQL creation split from source_detail
    monthly_ae_creation: list[float] = []
    monthly_mql_creation: list[float] = []
    for idx in range(n_months):
        ae_c, mql_c = _extract_source_creation(
            getattr(traj, "monthly_source_detail", []), idx, traj_months[idx]
        )
        # If no source_detail, fall back to putting all creation into AE
        total_c = _safe_float(traj_pipeline_creation[idx] if idx < len(traj_pipeline_creation) else 0)
        if ae_c == 0 and mql_c == 0 and total_c > 0:
            ae_c = total_c
        monthly_ae_creation.append(ae_c)
        monthly_mql_creation.append(mql_c)

    # Decay curve
    decay_curve: list[float] = []
    observed_decay_curve_info: dict = {}
    try:
        decay_dict = getattr(runtime, "observed_decay_curve", None) or {}
        if isinstance(decay_dict, dict):
            observed_decay_curve_info = _serialize_mapping(decay_dict)
        if isinstance(decay_dict, dict):
            decay_curve = [_safe_float(v) for v in (decay_dict.get("curve") or [])]
        elif isinstance(decay_dict, list):
            decay_curve = [_safe_float(v) for v in decay_dict]
    except Exception as exc:
        logger.warning("observed_decay_curve failed: %s", exc)

    # Observed values
    avg_deal_size = _get_avg_deal_size(observed_productivity)
    ramp_months = _get_ramp_months(observed_ramp_curve)
    productivity_per_ae = _safe_float(
        observed_productivity.get("productivity_per_ae_per_month")
        or observed_productivity.get("productivity")
        or observed_productivity.get("s0_per_ae_per_month")
        or 0
    )
    # Compute avg S2->close cycle time as sum of S2+ stage velocity
    s2_plus_stages = ["S2", "S3", "S4", "S5"]
    avg_cycle_days = sum(
        _safe_float(stage_velocity_days.get(s, 0)) for s in s2_plus_stages
    )
    if avg_cycle_days == 0:
        # fallback to any "total" key
        avg_cycle_days = _safe_float(stage_velocity_days.get("s2_to_won") or stage_velocity_days.get("total") or 0)

    # Compute avg_deal_size from pipeline if not in productivity dict
    if avg_deal_size == 0 and deals:
        non_zero_values = [d["metric_value"] for d in deals if d["metric_value"] > 0]
        if non_zero_values:
            avg_deal_size = sum(non_zero_values) / len(non_zero_values)

    observed_values = {
        "win_rate": s2_to_won,
        "avg_deal_size": avg_deal_size,
        "avg_cycle_days": avg_cycle_days,
        "ramp_months": ramp_months,
        "productivity_per_ae_per_month": productivity_per_ae,
    }

    # -----------------------------------------------------------------------
    # Lock actual months to Salesforce actuals across all downstream arrays.
    # Without this, charts can mix locked bookings with projected losses,
    # creation, or future-wins components for the same month.
    # -----------------------------------------------------------------------
    bookings_actual_by_month: dict[str, float] = {}
    for entry in bookings_by_month:
        m_key = (entry.get("month") or "")[:7]
        if m_key:
            bookings_actual_by_month[m_key] = _safe_float(entry.get("total"))

    losses_actual_by_month: dict[str, float] = {}
    for entry in losses_by_month:
        m_key = (entry.get("month") or "")[:7]
        if m_key:
            losses_actual_by_month[m_key] = _safe_float(entry.get("total"))

    creation_actual_by_month: dict[str, float] = {}
    creation_actual_rows = pipeline_entered_s2_by_month or pipeline_created_by_month
    for entry in creation_actual_rows:
        m_key = (entry.get("month") or "")[:7]
        if m_key:
            creation_actual_by_month[m_key] = _safe_float(entry.get("total"))

    for i, m_str in enumerate(traj_months):
        if i >= len(monthly_is_actual) or not monthly_is_actual[i]:
            continue

        m_key = m_str[:7]
        booking_actual = bookings_actual_by_month.get(m_key, 0.0)
        loss_actual = losses_actual_by_month.get(m_key, 0.0)
        creation_actual = creation_actual_by_month.get(m_key, 0.0)

        if i < len(traj_existing_wins):
            traj_existing_wins[i] = booking_actual
        if i < len(traj_future_wins):
            traj_future_wins[i] = 0.0
        if i < len(traj_total_expected):
            traj_total_expected[i] = booking_actual
        if i < len(traj_capped):
            traj_capped[i] = booking_actual
        if i < len(traj_existing_losses):
            traj_existing_losses[i] = loss_actual
        if i < len(traj_pipeline_creation):
            traj_pipeline_creation[i] = creation_actual
        if i < len(monthly_ae_creation):
            monthly_ae_creation[i] = creation_actual
        if i < len(monthly_mql_creation):
            monthly_mql_creation[i] = 0.0

        logger.info(
            "Locked actual month %s: bookings=$%s losses=$%s creation=$%s",
            m_key,
            f"{booking_actual:,.0f}",
            f"{loss_actual:,.0f}",
            f"{creation_actual:,.0f}",
        )

    # Reconcile trajectory_quarters after splice: update sales-led / reforecast
    # fields to match the spliced monthly totals so every page payload stays
    # consistent. The quarter dicts were serialized before splice, so they
    # still show the raw pre-splice model values unless we patch them here.
    def _month_in_quarter_key(m_key: str, q_key: str) -> bool:
        """Return True if YYYY-MM string m_key falls in fiscal quarter q_key (e.g. 'Q1FY26')."""
        import re
        match = re.match(r"Q(\d)FY(\d+)", q_key)
        if not match:
            return False
        quarter, fy_year = int(match.group(1)), int(match.group(2))
        base_year = 2000 + fy_year - 1
        if quarter == 1:
            q_months = {f"{base_year}-02", f"{base_year}-03", f"{base_year}-04"}
        elif quarter == 2:
            q_months = {f"{base_year}-05", f"{base_year}-06", f"{base_year}-07"}
        elif quarter == 3:
            q_months = {f"{base_year}-08", f"{base_year}-09", f"{base_year}-10"}
        else:  # Q4
            q_months = {f"{base_year}-11", f"{base_year}-12", f"{base_year + 1}-01"}
        return m_key in q_months

    def _gap_status(gap_pct: float) -> str:
        abs_gap = abs(gap_pct)
        if abs_gap <= 0.05:
            return "aligned"
        if abs_gap <= 0.15:
            return "minor_gap"
        if abs_gap <= 0.30:
            return "significant_gap"
        return "critical_gap"

    def _reconcile_spliced_quarters(section_name: str, page_payload: dict) -> None:
        for q_dict in page_payload.get("trajectory_quarters", []):
            q_name = q_dict.get("quarter", "")
            if not q_name:
                continue

            actual_month_indices = [
                i for i, m_str in enumerate(traj_months)
                if i < len(monthly_is_actual)
                and monthly_is_actual[i]
                and _month_in_quarter_key(m_str[:7], q_name)
            ]
            if not actual_month_indices:
                continue

            spliced_total = sum(
                traj_total_expected[i] for i in actual_month_indices
                if i < len(traj_total_expected)
            )
            projected_month_indices = [
                i for i, m_str in enumerate(traj_months)
                if i < len(monthly_is_actual)
                and not monthly_is_actual[i]
                and _month_in_quarter_key(m_str[:7], q_name)
            ]
            projected_total = sum(
                traj_total_expected[i] for i in projected_month_indices
                if i < len(traj_total_expected)
            )
            reconciled_sales_led = spliced_total + projected_total
            q_dict["bu_sales_led_arr"] = reconciled_sales_led

            bottoms_up = q_dict.get("bottoms_up")
            if isinstance(bottoms_up, dict):
                bottoms_up["sales_led_arr"] = reconciled_sales_led
                plg_arr = _safe_float(bottoms_up.get("plg_arr"))
                expansion_arr = _safe_float(bottoms_up.get("expansion_arr"))
                bottoms_up["total_arr"] = reconciled_sales_led + plg_arr + expansion_arr

            top_down = q_dict.get("top_down") or {}
            target_bookings = _safe_float(top_down.get("bookings"))
            target_total = _safe_float(top_down.get("total_net_new"))
            gap_value = target_bookings - reconciled_sales_led
            gap_pct = (gap_value / target_bookings) if target_bookings else 0.0
            gap_dict = q_dict.get("gap")
            if isinstance(gap_dict, dict):
                gap_dict["bookings"] = gap_value
                gap_dict["bookings_pct"] = gap_pct
                gap_dict["status"] = _gap_status(gap_pct)
                total_arr = _safe_float((bottoms_up or {}).get("total_arr")) if isinstance(bottoms_up, dict) else 0.0
                total_gap = target_total - total_arr
                gap_dict["total"] = total_gap
                gap_dict["total_pct"] = (total_gap / target_total) if target_total else 0.0

            reforecast = q_dict.get("reforecast")
            actuals = q_dict.get("actuals") or {}
            actual_bookings = _safe_float(actuals.get("bookings"))
            if isinstance(reforecast, dict):
                reforecast["remaining_plan_bookings"] = max(target_bookings - actual_bookings, 0.0)
                reforecast["remaining_bu_bookings"] = max(reconciled_sales_led - actual_bookings, 0.0)
                reforecast["reforecast_bookings"] = reconciled_sales_led
                reforecast["reforecast_gap"] = reconciled_sales_led - target_bookings
                reforecast["reforecast_gap_pct"] = (
                    (reconciled_sales_led - target_bookings) / target_bookings
                    if target_bookings else 0.0
                )

            logger.info(
                "Reconciled %s %s bu_sales_led_arr: $%s (actual $%s + projected $%s)",
                section_name,
                q_name,
                f"{reconciled_sales_led:,.0f}",
                f"{spliced_total:,.0f}",
                f"{projected_total:,.0f}",
            )

    for section_name, page_payload in (
        ("bookings_bridge", bookings_bridge),
        ("capacity_headcount", capacity_headcount),
        ("funnel_health", funnel_health),
    ):
        _reconcile_spliced_quarters(section_name, page_payload)

    # Derive quarter_by_month + overridable_quarters so the frontend scenario
    # engine can stay calendar-agnostic. quarter_dates comes from the profile's
    # configured fiscal calendar via tieout.data_access.
    try:
        quarter_dates = tieout.data_access.get_quarter_dates()
    except Exception:
        quarter_dates = {}

    def _quarter_for_month_iso(m_iso: str) -> str | None:
        try:
            m_date = date.fromisoformat(m_iso[:10])
        except Exception:
            return None
        for q_label, period in quarter_dates.items():
            if not period or len(period) < 2:
                continue
            q_start, q_end = period[0], period[1]
            if q_start <= m_date <= q_end:
                return q_label
        return None

    quarter_by_month = [_quarter_for_month_iso(m) for m in traj_months]

    # A quarter is overridable iff none of its months are actuals yet.
    quarter_status: dict[str, list[bool]] = {}
    for is_actual, q_label in zip(monthly_is_actual, quarter_by_month):
        if q_label is None:
            continue
        quarter_status.setdefault(q_label, []).append(is_actual)
    overridable_quarters = [q for q, flags in quarter_status.items() if not any(flags)]

    scenario_building_blocks = {
        "months": traj_months,
        "monthly_is_actual": monthly_is_actual,
        "quarter_by_month": quarter_by_month,
        "overridable_quarters": overridable_quarters,
        "monthly_inventory_wins": traj_existing_wins,
        "monthly_inventory_losses": traj_existing_losses,
        "monthly_inventory_remaining": traj_existing_remaining,
        "monthly_ae_creation": monthly_ae_creation,
        "monthly_mql_creation": monthly_mql_creation,
        "monthly_future_wins": traj_future_wins,
        "monthly_ae_count": monthly_ae_count,
        "monthly_ae_capacity": monthly_ae_capacity,
        "monthly_ae_ramped": monthly_ae_ramped,
        "monthly_blended_ramp": monthly_blended_ramp,
        "monthly_total_expected": traj_total_expected,
        "monthly_capped": traj_capped,
        "observed_values": observed_values,
        "decay_curve": decay_curve,
        "stage_win_rates": stage_conversion,
        "funnel_rates": runtime_funnel_rates,
    }

    # -----------------------------------------------------------------------
    # assumptions
    # -----------------------------------------------------------------------
    logger.info("Serializing assumptions...")
    assumptions: dict = {}
    try:
        assumptions = dict(result.assumptions_snapshot or {})
    except Exception as exc:
        logger.warning("assumptions_snapshot failed: %s", exc)

    # -----------------------------------------------------------------------
    # Assemble final snapshot
    # -----------------------------------------------------------------------
    # snapshot.capabilities mirrors what the schema declares; pages use it to
    # decide whether to render history/contacts/companies-dependent UI.
    # The canonical engine path always has stage history (built-in); contacts
    # and companies are connector-dependent but we report them as present
    # because the engine ingests them through the connector interface.
    capabilities = {
        "has_stage_history": True,
        "has_contacts": True,
        "has_companies": True,
    }

    snapshot = {
        "schema_version": "1.0.0",
        "engine_version": getattr(tieout, "engine_version", "unknown"),
        "profile_id": getattr(tieout, "profile_id", profile_id) or "default",
        "capabilities": capabilities,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "git_sha": _git_sha(),
        "as_of": _to_iso(as_of_date) or date.today().isoformat(),
        "actuals": {
            "bookings_by_month": bookings_by_month,
            "losses_by_month": losses_by_month,
            "pipeline_created_by_month": pipeline_created_by_month,
            "pipeline_entered_s2_by_month": pipeline_entered_s2_by_month,
            "mql_by_month": mql_by_month,
            "provenance": actuals_provenance,
        },
        "pipeline": {
            "deals": deals,
            "inventory_by_stage": inventory_by_stage,
            "provenance": pipeline_provenance,
        },
        "rates": {
            "stage_conversion": stage_conversion,
            "stage_velocity_days": stage_velocity_days,
            "overall_win_rate": s2_to_won,
            "funnel_rates": runtime_funnel_rates,
        },
        "roster": {
            "current_aes": current_aes,
            "trajectory_roster": trajectory_roster,
            "trajectory_roster_meta": trajectory_roster_meta,
            "effective_capacity": effective_capacity,
            "observed_productivity": observed_productivity,
            "observed_ramp_curve": observed_ramp_curve,
        },
        "model_output": {
            "bookings_bridge": bookings_bridge,
            "capacity_headcount": capacity_headcount,
            "funnel_health": funnel_health,
            "pipeline_inventory": pipeline_inventory,
        },
        "building_blocks": scenario_building_blocks,
        "scenario_building_blocks": scenario_building_blocks,
        "assumptions": assumptions,
        "health_status": dict(result.health_status or {}),
        "beginning_arr": _safe_float(result.beginning_arr),
        "beginning_arr_provenance": _serialize_mapping(getattr(result, "beginning_arr_provenance", {}) or {}),
        "bookings_summary_provenance": _serialize_mapping(getattr(result, "bookings_summary_provenance", {}) or {}),
        "top_down_plan": dict(result.top_down_plan or {}),
        "provenance": {
            "beginning_arr": _serialize_mapping(getattr(result, "beginning_arr_provenance", {}) or {}),
            "bookings_summary": _serialize_mapping(getattr(result, "bookings_summary_provenance", {}) or {}),
            "arr_movements": _serialize_mapping(getattr(result, "arr_movements", {}) or {}),
            "pipeline": _serialize_mapping(pipeline_provenance),
            "roster": _serialize_mapping(trajectory_roster_meta),
            "observed_productivity": _serialize_mapping(observed_productivity),
            "observed_ramp_curve": _serialize_mapping(observed_ramp_curve),
            "self_serve_velocity": self_serve_velocity,
            "trailing_mql_signal": {"source": trailing_mql_signal_source},
            "decay_curve": observed_decay_curve_info,
            "s2_to_won": _serialize_mapping(rolling_s2_to_won),
            "funnel_rates": _serialize_mapping(funnel_rate_descriptions),
        },
    }

    return snapshot


def _write_snapshot_json(path: Path, snapshot: dict, indent: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    indent_value = indent if indent > 0 else None
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=indent_value, default=str)


def _resolve_profile_snapshot_output_path(profiles_output_dir: Path, profile) -> Path:
    from gtm_model.tieout.runtime.profile import resolve_frontend_profile_data_path

    return resolve_frontend_profile_data_path(
        profiles_output_dir,
        profile,
        profile.data.snapshot,
    )


def _resolve_snapshot_output_targets(
    profiles_output_dir: Path,
    profile,
    legacy_output_path: Path | None = None,
) -> list[Path]:
    targets = [_resolve_profile_snapshot_output_path(profiles_output_dir, profile)]
    if legacy_output_path is not None:
        resolved_legacy = legacy_output_path.expanduser().resolve()
        if resolved_legacy not in targets:
            targets.insert(0, resolved_legacy)
    return targets


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate React frontend snapshot JSON")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_SNAPSHOT_OUTPUT),
        help="Compatibility output path for the selected profile snapshot",
    )
    parser.add_argument(
        "--profiles-output-dir",
        default=str(DEFAULT_PROFILES_OUTPUT),
        help="Output directory for profile-scoped org + plan JSON assets",
    )
    parser.add_argument(
        "--skip-legacy-output",
        action="store_true",
        help="Do not write the compatibility snapshot mirror path",
    )
    parser.add_argument(
        "--plan-case-id",
        default=None,
        help="Plan case ID to use (default: active profile's configured default)",
    )
    parser.add_argument(
        "--profile-id",
        default=None,
        help="Org profile id to generate (default: active/default profile)",
    )
    parser.add_argument(
        "--all-profiles",
        action="store_true",
        help="Generate snapshots for every configured org profile",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent level (default: 2, use 0 for compact)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help=(
            "Override the snapshot's 'as-of' date (YYYY-MM-DD). When omitted, "
            "uses date.today(). Useful for parity tests, CI smoke runs, and "
            "reproducing past snapshots. See ARCHITECTURE.md."
        ),
    )
    args = parser.parse_args()

    as_of_override = None
    if args.as_of:
        try:
            from datetime import date as _date

            as_of_override = _date.fromisoformat(args.as_of)
        except ValueError:
            logger.error("--as-of must be YYYY-MM-DD; got %r", args.as_of)
            sys.exit(2)

    try:
        from gtm_model.tieout.runtime.profile import (
            get_active_profile_id,
            list_org_profiles,
            load_org_profile,
            write_frontend_profile_bundle_assets,
        )
    except Exception as exc:
        logger.error("Profile bootstrap failed: %s", exc, exc_info=True)
        sys.exit(1)

    compatibility_output_path = Path(args.output).expanduser().resolve()
    profiles_output_dir = Path(args.profiles_output_dir).expanduser().resolve()
    if not args.skip_legacy_output:
        compatibility_output_path.parent.mkdir(parents=True, exist_ok=True)
    profiles_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        profile_assets = write_frontend_profile_bundle_assets(
            profiles_output_dir,
            indent=args.indent,
        )
    except PlanConfigValidationError as exc:
        # Plan-asset generation needs rich v2-style targets config
        # (annual_targets.{new_business_arr, plg_arr, expansion_arr, ...},
        # quarterly_targets dict-of-dicts, monthly_bookings, headcount_targets).
        # Surface the validation error precisely — never swallow other
        # exception types, and never proceed past this point. Operators
        # need to know their plan bundle is incomplete.
        logger.error(
            "Frontend plan-asset bundle is invalid for the active profile: %s",
            exc,
        )
        sys.exit(2)

    if args.all_profiles:
        profiles = list_org_profiles()
    else:
        profiles = [load_org_profile(profile_id=args.profile_id)]
    mirror_profile_id = get_active_profile_id(args.profile_id)

    written_snapshot_paths: list[Path] = []
    mirrored_snapshot: dict | None = None
    mirrored_deal_count = 0
    mirrored_month_count = 0

    for profile in profiles:
        try:
            snapshot = build_snapshot(
                plan_case_id=args.plan_case_id,
                profile_id=profile.id,
                as_of=as_of_override,
            )
        except Exception as exc:
            logger.error(
                "Snapshot generation failed for profile %s: %s",
                profile.id,
                exc,
                exc_info=True,
            )
            sys.exit(1)

        legacy_target = (
            compatibility_output_path
            if profile.id == mirror_profile_id and not args.skip_legacy_output
            else None
        )
        for target_path in _resolve_snapshot_output_targets(
            profiles_output_dir,
            profile,
            legacy_output_path=legacy_target,
        ):
            _write_snapshot_json(target_path, snapshot, args.indent)
            written_snapshot_paths.append(target_path)

        if profile.id == mirror_profile_id:
            mirrored_snapshot = snapshot
            mirrored_deal_count = len(snapshot["pipeline"]["deals"])
            mirrored_month_count = len(snapshot["scenario_building_blocks"]["months"])

    if mirrored_snapshot is None and profiles:
        mirrored_snapshot = snapshot
        mirrored_deal_count = len(snapshot["pipeline"]["deals"])
        mirrored_month_count = len(snapshot["scenario_building_blocks"]["months"])

    if mirrored_snapshot is None:
        logger.error("No snapshots were generated.")
        sys.exit(1)

    logger.info(
        "Snapshot outputs written: %d",
        len(written_snapshot_paths),
    )
    for path in written_snapshot_paths:
        logger.info("  snapshot %s", path)
    logger.info("Frontend data assets synced: %d", len(profile_assets))
    logger.info("  deals: %d, months: %d", mirrored_deal_count, mirrored_month_count)
    logger.info("  beginning_arr: $%s", f"{mirrored_snapshot['beginning_arr']:,.0f}")
    logger.info("  as_of: %s", mirrored_snapshot["as_of"])
    logger.info("  git_sha: %s", mirrored_snapshot["git_sha"])


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generate a pre-built snapshot.json from the Acme SaaS CSV data and config.

This is a bootstrapping script — it builds the snapshot directly from CSV data
without requiring the full tieout engine runtime (which needs live CRM
connections). The result is a complete JSON file that satisfies the frontend
Snapshot TypeScript interface.

Usage:
    cd /path/to/forecast-tieout
    python -m engine.scripts.generate_acme_snapshot
"""

from __future__ import annotations

import csv
import json
import os
import random
import subprocess
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# TargetSetter helpers (imported from canonical generator — single source of truth)
# ---------------------------------------------------------------------------
# These three helpers are defined in generate_snapshot.py and handle:
#   _load_scenarios_yaml  — read scenarios.yaml for the profile
#   _load_raw_assumptions — read full assumptions.yaml (incl. target_setter_defaults)
#   _build_observed_scenario — bake observed Scenario from funnel_rates + defaults
# Import here so we don't duplicate logic.  The import succeeds even though
# generate_snapshot.py pulls in gtm_model, because Python only executes module-level
# code that doesn't raise on this OSS path (gtm_model is present in the repo).
from engine.scripts.generate_snapshot import (  # noqa: E402
    _build_observed_scenario,
    _load_raw_assumptions,
    _load_scenarios_yaml,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "engine" / "data" / "acme-saas"
CONFIG_DIR = REPO_ROOT / "engine" / "config" / "profiles" / "acme-saas"
OUTPUT_DIR = REPO_ROOT / "frontend" / "public" / "data" / "profiles" / "acme-saas"
OUTPUT_FILE = OUTPUT_DIR / "snapshot.json"

# Fiscal year: Feb 2026 – Jan 2027 = FY26 (year-of-start convention)
FY_START = date(2026, 2, 1)
FY_END = date(2027, 1, 31)
AS_OF = date(2026, 4, 6)  # "today" for the demo

FISCAL_MONTHS = [
    "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07",
    "2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01",
]

QUARTERS = [
    {"quarter": "Q1FY26", "months": ["2026-02", "2026-03", "2026-04"],
     "period_start": "2026-02-01", "period_end": "2026-04-30"},
    {"quarter": "Q2FY26", "months": ["2026-05", "2026-06", "2026-07"],
     "period_start": "2026-05-01", "period_end": "2026-07-31"},
    {"quarter": "Q3FY26", "months": ["2026-08", "2026-09", "2026-10"],
     "period_start": "2026-08-01", "period_end": "2026-10-31"},
    {"quarter": "Q4FY26", "months": ["2026-11", "2026-12", "2027-01"],
     "period_start": "2026-11-01", "period_end": "2027-01-31"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def git_sha() -> str:
    env_sha = os.getenv("GTM_TIEOUT_GIT_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        return result.stdout.strip() or "local"
    except Exception:
        return "local"


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, "r") as f:
        return yaml.safe_load(f) or {}


def load_csv(name: str) -> list[dict]:
    with open(DATA_DIR / name, "r") as f:
        return list(csv.DictReader(f))


def safe_float(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return default if f != f else f  # NaN check
    except (TypeError, ValueError):
        return default


def month_key(date_str: str) -> str:
    """Extract YYYY-MM from a date string."""
    return (date_str or "")[:7]


def month_is_actual(m: str) -> bool:
    """Return True if month is fully elapsed (strictly before as_of month)."""
    return m < AS_OF.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_deals() -> list[dict]:
    raw = load_csv("deals.csv")
    deals = []
    for r in raw:
        deals.append({
            "id": r["id"],
            "name": r["name"],
            "amount": safe_float(r.get("amount")),
            "stage": r["stage"],
            "close_date": r.get("close_date") or None,
            "owner_id": r.get("owner_id", ""),
            "type": r.get("type", "New Business"),
            "created_date": r.get("created_date") or None,
            "segment": r.get("segment", ""),
            "source": r.get("source", ""),
            "is_closed": r.get("is_closed", "false") == "true",
            "is_won": r.get("is_won", "false") == "true",
        })
    return deals


def load_stage_history() -> list[dict]:
    raw = load_csv("stage_history.csv")
    return [
        {
            "deal_id": r["deal_id"],
            "from_stage": r.get("from_stage", ""),
            "to_stage": r.get("to_stage", ""),
            "transition_date": r.get("transition_date", ""),
        }
        for r in raw
    ]


# ---------------------------------------------------------------------------
# Computation functions
# ---------------------------------------------------------------------------

def build_actuals(deals: list[dict]) -> dict:
    """Build bookings_by_month, losses_by_month, and mql_by_month."""
    bookings: dict[str, float] = defaultdict(float)
    losses: dict[str, float] = defaultdict(float)

    for d in deals:
        m = month_key(d["close_date"])
        if not m:
            continue
        if d["is_won"]:
            bookings[m] += d["amount"]
        elif d["is_closed"]:
            losses[m] += d["amount"]

    bookings_by_month = [
        {"month": m, "total": round(bookings.get(m, 0))}
        for m in FISCAL_MONTHS
        if month_is_actual(m) and bookings.get(m, 0) > 0
    ]
    # Also include pre-FY months that have won deals (FY26 actuals)
    for m in sorted(bookings.keys()):
        if m < "2026-02" and bookings[m] > 0:
            bookings_by_month.insert(0, {"month": m, "total": round(bookings[m])})

    losses_by_month = [
        {"month": m, "total": round(losses.get(m, 0))}
        for m in sorted(losses.keys())
        if losses.get(m, 0) > 0
    ]

    # Synthetic MQL data — 25-40 per month for the fiscal year
    rng = random.Random(42)
    mql_by_month = [
        {"month_index": i, "value": rng.randint(25, 40)}
        for i in range(12)
    ]

    pipeline_created_by_month = []
    created_by_month: dict[str, float] = defaultdict(float)
    for d in deals:
        cm = month_key(d.get("created_date", ""))
        if cm:
            created_by_month[cm] += d["amount"]
    for m in FISCAL_MONTHS:
        if created_by_month.get(m, 0) > 0:
            pipeline_created_by_month.append({"month": m, "total": round(created_by_month[m])})

    return {
        "bookings_by_month": bookings_by_month,
        "losses_by_month": losses_by_month,
        "pipeline_created_by_month": pipeline_created_by_month,
        "pipeline_entered_s2_by_month": [],
        "mql_by_month": mql_by_month,
        "provenance": {"source": "acme-saas-csv", "note": "Pre-built from CSV data"},
    }


def build_pipeline(deals: list[dict], stages_config: dict) -> dict:
    """Build pipeline deals list and inventory_by_stage."""
    # Owner name lookup from roster
    roster = load_yaml("roster.yaml")
    owner_map = {}
    for tm in roster.get("team_members", []):
        owner_map[tm["id"]] = tm["name"]

    open_deals = []
    for d in deals:
        if d["is_closed"]:
            continue
        open_deals.append({
            "opp_id": d["id"],
            "stage": d["stage"],
            "amount": d["amount"],
            "arr": d["amount"],  # For demo, ARR = amount
            "metric_value": d["amount"],
            "close_date": d["close_date"],
            "created_date": d["created_date"],
            "source_stream": d.get("source", ""),
            "owner_name": owner_map.get(d["owner_id"], d["owner_id"]),
            "opp_type": d["type"],
            "forecast_category": _forecast_category(d["stage"]),
        })

    # Build inventory by stage in order
    stage_order = [s["name"] for s in stages_config.get("stages", [])
                   if s["name"] not in ("Closed Won", "Closed Lost")]
    inv: dict[str, dict] = {}
    for d in open_deals:
        s = d["stage"]
        if s not in inv:
            inv[s] = {"stage": s, "count": 0, "total_value": 0.0}
        inv[s]["count"] += 1
        inv[s]["total_value"] += d["metric_value"]

    inventory_by_stage = [inv[s] for s in stage_order if s in inv]
    # Round values
    for item in inventory_by_stage:
        item["total_value"] = round(item["total_value"])

    return {
        "deals": open_deals,
        "inventory_by_stage": inventory_by_stage,
        "provenance": {"source": "acme-saas-csv", "as_of": AS_OF.isoformat()},
    }


def _forecast_category(stage: str) -> str:
    mapping = {
        "Discovery": "Pipeline",
        "Qualification": "Pipeline",
        "Technical Evaluation": "Best Case",
        "Business Case": "Commit",
        "Negotiation": "Commit",
    }
    return mapping.get(stage, "Pipeline")


def build_rates(
    deals: list[dict],
    stage_history: list[dict],
    assumptions: dict,
    stages_config: dict,
) -> dict:
    """Build rates: stage_conversion, stage_velocity_days, overall_win_rate."""
    # Stage conversion from assumptions.yaml
    stage_conversion = dict(assumptions.get("stage_rates", {}))

    # Overall win rate: closed_won / (closed_won + closed_lost)
    n_won = sum(1 for d in deals if d["is_won"])
    n_lost = sum(1 for d in deals if d["is_closed"] and not d["is_won"])
    total_closed = n_won + n_lost
    overall_win_rate = round(n_won / total_closed, 3) if total_closed > 0 else 0.0

    # Stage velocity: average days between consecutive transitions per stage
    # Group transitions by deal
    deal_transitions: dict[str, list[dict]] = defaultdict(list)
    for h in stage_history:
        deal_transitions[h["deal_id"]].append(h)

    stage_days: dict[str, list[float]] = defaultdict(list)
    for deal_id, transitions in deal_transitions.items():
        sorted_t = sorted(transitions, key=lambda x: x["transition_date"])
        for i in range(len(sorted_t) - 1):
            from_stage = sorted_t[i]["to_stage"]
            to_stage = sorted_t[i + 1]["to_stage"]
            if from_stage == to_stage:
                continue  # skip same-stage re-entries
            try:
                d1 = datetime.fromisoformat(sorted_t[i]["transition_date"])
                d2 = datetime.fromisoformat(sorted_t[i + 1]["transition_date"])
                days = (d2 - d1).days
                if 0 < days < 365:
                    stage_days[from_stage].append(days)
            except (ValueError, TypeError):
                continue

    stage_velocity_days = {}
    for stage_name in [s["name"] for s in stages_config.get("stages", [])
                       if s["name"] not in ("Closed Won", "Closed Lost")]:
        if stage_name in stage_days and stage_days[stage_name]:
            stage_velocity_days[stage_name] = round(
                sum(stage_days[stage_name]) / len(stage_days[stage_name]), 1
            )
        else:
            # Reasonable defaults
            defaults = {
                "Discovery": 21, "Qualification": 18,
                "Technical Evaluation": 25, "Business Case": 20, "Negotiation": 14,
            }
            stage_velocity_days[stage_name] = defaults.get(stage_name, 20)

    # Funnel rates (synthetic but plausible)
    funnel_rates = {
        "mql_to_sql": 0.32,
        "sql_to_opp": 0.45,
        "opp_to_s2": 0.60,
        "s2_to_won": overall_win_rate,
    }

    return {
        "stage_conversion": stage_conversion,
        "stage_velocity_days": stage_velocity_days,
        "overall_win_rate": overall_win_rate,
        "funnel_rates": funnel_rates,
    }


def build_roster(roster_yaml: dict) -> dict:
    """Build roster section."""
    team_members = roster_yaml.get("team_members", [])

    # Current AEs
    current_aes = []
    for tm in team_members:
        if tm.get("role") != "ae":
            continue
        current_aes.append({
            "id": tm["id"],
            "name": tm["name"],
            "role": tm["role"],
            "segment": tm.get("segment", ""),
            "start_date": tm.get("start_date", ""),
            "quota": safe_float(tm.get("quota")),
            "status": tm.get("status", "tenured"),
            "manager_id": tm.get("manager_id", ""),
        })

    # Trajectory roster: AEs keyed by month they are active
    trajectory_roster: dict[str, list] = {}
    for m in FISCAL_MONTHS:
        m_date = date.fromisoformat(m + "-01")
        active_aes = []
        for ae in current_aes:
            start = date.fromisoformat(ae["start_date"])
            if start <= m_date:
                active_aes.append(ae)
        trajectory_roster[m] = active_aes

    # Effective capacity
    effective_capacity = []
    for i, m in enumerate(FISCAL_MONTHS):
        m_date = date.fromisoformat(m + "-01")
        active = [ae for ae in current_aes if date.fromisoformat(ae["start_date"]) <= m_date]
        tenured = [ae for ae in active if ae["status"] == "tenured" or
                   (m_date - date.fromisoformat(ae["start_date"])).days > 180]
        ramping = [ae for ae in active if ae not in tenured]

        ae_total = len(active)
        ae_ramped = len(tenured)
        ae_ramping = len(ramping)

        # Capacity = sum of monthly quota (annual / 12)
        capacity_ramped = sum(ae["quota"] / 12 for ae in tenured)
        capacity_ramping = sum(ae["quota"] / 12 * _ramp_pct(m_date, ae) for ae in ramping)
        total_capacity = capacity_ramped + capacity_ramping

        blended_ramp = (total_capacity / (sum(ae["quota"] / 12 for ae in active))
                        if active else 1.0)

        # Monthly target from targets.yaml (split evenly in quarter)
        targets = load_yaml("targets.yaml")
        q_targets = targets.get("quarterly_targets", {})
        q_idx = i // 3
        q_names = ["Q1", "Q2", "Q3", "Q4"]
        q_target = safe_float(q_targets.get(q_names[q_idx], 0))
        monthly_target = round(q_target / 3)

        effective_capacity.append({
            "month": m + "-01",
            "label": m,
            "ae_total": ae_total,
            "ae_ramped": ae_ramped,
            "ae_ramping": ae_ramping,
            "se_total": 0,
            "sdr_total": 0,
            "ae_capacity": round(total_capacity),
            "ae_capacity_ramped": round(capacity_ramped),
            "ae_capacity_ramping": round(capacity_ramping),
            "blended_ramp_pct": round(blended_ramp, 3),
            "monthly_target": monthly_target,
        })

    return {
        "current_aes": current_aes,
        "trajectory_roster": trajectory_roster,
        "trajectory_roster_meta": {
            "total_aes": len(current_aes),
            "ramping_count": sum(1 for ae in current_aes if ae["status"] == "ramping"),
        },
        "effective_capacity": effective_capacity,
        "observed_productivity": {
            "productivity_per_ae_per_month": 180000,
            "avg_deal_size": 175000,
            "s0_per_ae_per_month": 2.1,
        },
        "observed_ramp_curve": {
            "ramp_curve": [0.0, 0.15, 0.30, 0.50, 0.70, 0.85, 1.0],
            "months_to_full": 6,
        },
    }


def _ramp_pct(month_date: date, ae: dict) -> float:
    """Compute ramp percentage for a ramping AE."""
    start = date.fromisoformat(ae["start_date"])
    months_in = (month_date.year - start.year) * 12 + (month_date.month - start.month)
    # 6-month ramp: [0, 0.15, 0.30, 0.50, 0.70, 0.85, 1.0]
    ramp_curve = [0.0, 0.15, 0.30, 0.50, 0.70, 0.85, 1.0]
    if months_in >= len(ramp_curve):
        return 1.0
    if months_in < 0:
        return 0.0
    return ramp_curve[months_in]


def build_model_output(
    deals: list[dict],
    actuals: dict,
    effective_capacity: list[dict],
    assumptions: dict,
    targets: dict,
    stages_config: dict,
) -> dict:
    """Build the model_output section with all four sub-models."""
    stage_rates = assumptions.get("stage_rates", {})
    q_targets = targets.get("quarterly_targets", {})

    # Monthly plan totals (quarterly target / 3)
    plan_total = []
    for i, m in enumerate(FISCAL_MONTHS):
        q_idx = i // 3
        q_names = ["Q1", "Q2", "Q3", "Q4"]
        q_target = safe_float(q_targets.get(q_names[q_idx], 0))
        plan_total.append(round(q_target / 3))

    # Bookings actuals by month (for actual months)
    actuals_by_month: dict[str, float] = {}
    for entry in actuals.get("bookings_by_month", []):
        actuals_by_month[entry["month"]] = entry["total"]

    # --- Existing wins: weighted pipeline by close_date month ---
    open_deals = [d for d in deals if not d["is_closed"]]

    existing_wins = [0.0] * 12
    existing_losses = [0.0] * 12
    existing_remaining = [0.0] * 12

    for d in open_deals:
        cm = month_key(d["close_date"])
        stage = d["stage"]
        rate = safe_float(stage_rates.get(stage, 0.05))
        amt = d["amount"]

        idx = None
        for i, m in enumerate(FISCAL_MONTHS):
            if m == cm:
                idx = i
                break
        if idx is None:
            continue

        existing_wins[idx] += amt * rate
        existing_losses[idx] += amt * (1 - rate) * 0.4  # ~40% of unweighted lost
        existing_remaining[idx] += amt * (1 - rate) * 0.6  # ~60% remain/slip

    # Apply slippage: ~20% of pipeline in each month slips 1-2 months forward
    # This models deal pushes and creates a more realistic tail distribution.
    slip_rate = 0.20
    for i in range(len(FISCAL_MONTHS) - 1, -1, -1):
        if existing_wins[i] > 0 and i < len(FISCAL_MONTHS) - 2:
            slip_amount = existing_wins[i] * slip_rate
            existing_wins[i] -= slip_amount
            # 60% slips 1 month, 40% slips 2 months
            existing_wins[i + 1] += slip_amount * 0.6
            if i + 2 < len(FISCAL_MONTHS):
                existing_wins[i + 2] += slip_amount * 0.4

    existing_wins = [round(v) for v in existing_wins]
    existing_losses = [round(v) for v in existing_losses]
    existing_remaining = [round(v) for v in existing_remaining]

    # --- Future wins: capacity-based new pipeline ---
    # Calibrated so trajectory totals ~$34M against $40M plan (15% gap).
    future_wins = [0.0] * 12
    pipeline_creation = [0.0] * 12
    for i, cap_row in enumerate(effective_capacity):
        if i >= 12:
            break
        monthly_cap = safe_float(cap_row.get("ae_capacity", 0))
        # Future generation wins scaled to produce realistic trajectory
        # Calibrated to hit ~$34M total (vs $40M plan = ~15% gap)
        future_wins[i] = round(monthly_cap * 0.72)
        pipeline_creation[i] = round(monthly_cap * 2.0)  # creation > wins

    future_wins = [round(v) for v in future_wins]

    # --- Splice actuals for completed months ---
    # A month is "actual" if it's fully past. The as_of month (April 2026)
    # is partially elapsed: show actuals so far + projections for remainder.
    monthly_is_actual = [month_is_actual(m) for m in FISCAL_MONTHS]
    as_of_month = AS_OF.strftime("%Y-%m")
    for i, m in enumerate(FISCAL_MONTHS):
        if m == as_of_month:
            # Current month: actuals so far + partial projection
            actual_so_far = round(actuals_by_month.get(m, 0))
            # Keep existing_wins as the pipeline projection for this month,
            # but add actuals already booked
            existing_wins[i] = actual_so_far + round(existing_wins[i] * 0.7)
            future_wins[i] = round(future_wins[i] * 0.5)
            monthly_is_actual[i] = False  # partial — not fully locked
        elif monthly_is_actual[i] and m in actuals_by_month:
            existing_wins[i] = round(actuals_by_month[m])
            future_wins[i] = 0
        elif monthly_is_actual[i]:
            existing_wins[i] = 0
            future_wins[i] = 0

    # Total expected
    total_expected = [round(existing_wins[i] + future_wins[i]) for i in range(12)]

    # Capped at plan (overflow if above plan)
    capped = [min(total_expected[i], plan_total[i]) for i in range(12)]
    overflow = [max(total_expected[i] - plan_total[i], 0) for i in range(12)]

    # Plan breakdown: plan_existing_wins + plan_future_wins = plan_total
    # For plan, assume pipeline covers ~45% of target, rest is future generation
    plan_existing_wins = [round(plan_total[i] * 0.35) for i in range(12)]
    plan_future_wins = [plan_total[i] - plan_existing_wins[i] for i in range(12)]

    # --- Build trajectory quarters ---
    trajectory_quarters = _build_quarter_data(
        FISCAL_MONTHS, total_expected, actuals_by_month, q_targets
    )
    plan_quarters = _build_quarter_data(
        FISCAL_MONTHS, plan_total, actuals_by_month, q_targets, is_plan=True
    )

    months_iso = [m + "-01" for m in FISCAL_MONTHS]

    bookings_bridge = {
        "months": months_iso,
        "existing_wins": existing_wins,
        "future_wins": future_wins,
        "total_expected": total_expected,
        "capped": capped,
        "overflow": overflow,
        "plan_existing_wins": plan_existing_wins,
        "plan_future_wins": plan_future_wins,
        "plan_total": plan_total,
        "trajectory_quarters": trajectory_quarters,
        "plan_quarters": plan_quarters,
        "provenance": {"engine": "acme-snapshot-generator", "version": "1.0.0"},
        "source_detail": [],
        "capacity_warnings": [
            "AE-E05 (Nina Kowalski) ramping — started 2026-04-01",
            "AE-M08 (Sofia Garcia) ramping — starts 2026-05-01",
            "AE-C07 (Liam Park) ramping — starts 2026-06-01",
        ],
    }

    capacity_headcount = {
        "trajectory_capacity": effective_capacity,
        "plan_capacity": effective_capacity,  # Same for demo
        "trajectory_quarters": trajectory_quarters,
        "plan_quarters": plan_quarters,
    }

    funnel_health = {
        "trajectory_quarters": trajectory_quarters,
        "plan_quarters": plan_quarters,
        "funnel_rates": {
            "mql_to_sql": 0.32,
            "sql_to_opp": 0.45,
            "opp_to_s2": 0.60,
            "s2_to_won": 0.44,
        },
        "funnel_rate_descriptions": {
            "mql_to_sql": {"label": "MQL to SQL", "lookback_days": 180},
            "sql_to_opp": {"label": "SQL to Opportunity", "lookback_days": 180},
            "opp_to_s2": {"label": "Opp to Technical Evaluation", "lookback_days": 180},
            "s2_to_won": {"label": "Tech Eval to Closed Won", "lookback_days": 365},
        },
        "mql_actuals": actuals.get("mql_by_month", []),
        "rolling_s2_to_won": {
            "current": 0.44,
            "prior_quarter": 0.41,
            "trend": "improving",
        },
    }

    pipeline_inventory = {
        "months": months_iso,
        "existing_wins": existing_wins,
        "existing_losses": existing_losses,
        "existing_remaining": existing_remaining,
        "future_wins": future_wins,
        "pipeline_creation": pipeline_creation,
        "provenance": {"engine": "acme-snapshot-generator"},
    }

    return {
        "bookings_bridge": bookings_bridge,
        "capacity_headcount": capacity_headcount,
        "funnel_health": funnel_health,
        "pipeline_inventory": pipeline_inventory,
    }


def _build_quarter_data(
    months: list[str],
    monthly_totals: list[float],
    actuals_by_month: dict[str, float],
    q_targets: dict,
    is_plan: bool = False,
) -> list[dict]:
    """Build quarterly rollup data."""
    result = []
    for q in QUARTERS:
        q_name = q["quarter"]
        q_key = q_name[:2]  # "Q1", "Q2", etc.
        target = safe_float(q_targets.get(q_key, 0))

        # Sum monthly totals for this quarter's months
        q_total = 0.0
        actual_bookings = 0.0
        for m in q["months"]:
            idx = months.index(m) if m in months else -1
            if idx >= 0:
                q_total += monthly_totals[idx]
            if m in actuals_by_month:
                actual_bookings += actuals_by_month[m]

        bu_sales_led = round(q_total) if not is_plan else round(target)
        gap_value = target - bu_sales_led
        gap_pct = gap_value / target if target else 0.0

        result.append({
            "quarter": q_name,
            "period_start": q["period_start"],
            "period_end": q["period_end"],
            "td_bookings": round(target),
            "bu_sales_led_arr": bu_sales_led,
            "actual_bookings": round(actual_bookings),
            "top_down": {
                "bookings": round(target),
                "total_net_new": round(target),
            },
            "bottoms_up": {
                "sales_led_arr": bu_sales_led,
                "plg_arr": 0,
                "expansion_arr": 0,
                "total_arr": bu_sales_led,
            },
            "gap": {
                "bookings": round(gap_value),
                "bookings_pct": round(gap_pct, 3),
                "total": round(gap_value),
                "total_pct": round(gap_pct, 3),
                "status": _gap_status(gap_pct),
            },
            "actuals": {
                "bookings": round(actual_bookings),
            },
            "reforecast": {
                "remaining_plan_bookings": round(max(target - actual_bookings, 0)),
                "remaining_bu_bookings": round(max(bu_sales_led - actual_bookings, 0)),
                "reforecast_bookings": bu_sales_led,
                "reforecast_gap": bu_sales_led - round(target),
                "reforecast_gap_pct": round(
                    (bu_sales_led - target) / target if target else 0, 3
                ),
            },
        })
    return result


def _gap_status(gap_pct: float) -> str:
    abs_gap = abs(gap_pct)
    if abs_gap <= 0.05:
        return "aligned"
    if abs_gap <= 0.15:
        return "minor_gap"
    if abs_gap <= 0.30:
        return "significant_gap"
    return "critical_gap"


def build_scenario_building_blocks(
    effective_capacity: list[dict],
    model_output: dict,
    rates: dict,
    deals: list[dict],
) -> dict:
    """Build the scenario_building_blocks section."""
    bb = model_output["bookings_bridge"]
    pi = model_output["pipeline_inventory"]
    months = bb["months"]

    monthly_is_actual_flags = [month_is_actual(m[:7]) for m in months]

    # Quarter labels per month — emitted so the frontend scenario engine can stay
    # calendar-agnostic. Maps each `months[i]` (e.g. "2026-05-01") to its quarter
    # label (e.g. "Q2FY26"), or None if outside the configured fiscal year.
    month_to_quarter: dict[str, str] = {
        m: q["quarter"] for q in QUARTERS for m in q["months"]
    }
    quarter_by_month: list[str | None] = [month_to_quarter.get(m[:7]) for m in months]

    # Quarters the user can override in the scenario UI: the ordered set of
    # quarters whose months are ALL still projected (no actuals yet). A quarter
    # with even one elapsed month is treated as locked — overrides for it
    # would conflict with already-booked numbers.
    quarter_status: dict[str, list[bool]] = {}
    for is_actual, q in zip(monthly_is_actual_flags, quarter_by_month):
        if q is None:
            continue
        quarter_status.setdefault(q, []).append(is_actual)
    overridable_quarters = [
        q for q, flags in quarter_status.items() if not any(flags)
    ]

    # AE counts and capacity from effective_capacity
    monthly_ae_count = []
    monthly_ae_capacity = []
    monthly_ae_ramped = []
    monthly_blended_ramp = []
    for row in effective_capacity:
        monthly_ae_count.append(row.get("ae_total", 0))
        monthly_ae_capacity.append(safe_float(row.get("ae_capacity", 0)))
        monthly_ae_ramped.append(row.get("ae_ramped", 0))
        monthly_blended_ramp.append(safe_float(row.get("blended_ramp_pct", 1.0)))

    # Pipeline creation split: 70% AE, 30% MQL
    monthly_ae_creation = [round(v * 0.70) for v in pi["pipeline_creation"]]
    monthly_mql_creation = [round(v * 0.30) for v in pi["pipeline_creation"]]

    # Observed values
    won_deals = [d for d in deals if d["is_won"]]
    avg_deal_size = (sum(d["amount"] for d in won_deals) / len(won_deals)
                     if won_deals else 175000)
    n_won = len(won_deals)
    n_lost = sum(1 for d in deals if d["is_closed"] and not d["is_won"])
    win_rate = n_won / (n_won + n_lost) if (n_won + n_lost) > 0 else 0.44

    # Average cycle days from stage velocity
    stage_vel = rates.get("stage_velocity_days", {})
    avg_cycle_days = sum(stage_vel.values()) if stage_vel else 90

    # Decay curve (12-month lookforward weighting)
    decay_curve = [1.0, 0.95, 0.88, 0.80, 0.72, 0.63, 0.55, 0.47, 0.40, 0.33, 0.27, 0.22]

    return {
        "months": months,
        "monthly_is_actual": monthly_is_actual_flags,
        "quarter_by_month": quarter_by_month,
        "overridable_quarters": overridable_quarters,
        "monthly_inventory_wins": bb["existing_wins"],
        "monthly_inventory_losses": pi["existing_losses"],
        "monthly_inventory_remaining": pi["existing_remaining"],
        "monthly_ae_creation": monthly_ae_creation,
        "monthly_mql_creation": monthly_mql_creation,
        "monthly_future_wins": bb["future_wins"],
        "monthly_ae_count": monthly_ae_count,
        "monthly_ae_capacity": monthly_ae_capacity,
        "monthly_ae_ramped": monthly_ae_ramped,
        "monthly_blended_ramp": monthly_blended_ramp,
        "monthly_total_expected": bb["total_expected"],
        "monthly_capped": bb["capped"],
        "observed_values": {
            "win_rate": round(win_rate, 3),
            "avg_deal_size": round(avg_deal_size),
            "avg_cycle_days": round(avg_cycle_days),
            "ramp_months": 6,
            "productivity_per_ae_per_month": 180000,
        },
        "decay_curve": decay_curve,
        "stage_win_rates": rates["stage_conversion"],
        "funnel_rates": rates["funnel_rates"],
    }


def build_health_status(deals: list[dict]) -> dict:
    """Build health_status with data quality checks."""
    issues = []

    # Check for missing amounts
    missing_amount = [d for d in deals if not d["is_closed"] and d["amount"] == 0]
    if missing_amount:
        issues.append({
            "check": "missing_amount",
            "severity": "warning",
            "count": len(missing_amount),
            "message": f"{len(missing_amount)} open deals have $0 amount",
            "deal_ids": [d["id"] for d in missing_amount[:5]],
        })

    # Check for stale deals (open + close_date in the past)
    stale = [
        d for d in deals
        if not d["is_closed"] and d["close_date"]
        and d["close_date"] < AS_OF.isoformat()
    ]
    if stale:
        issues.append({
            "check": "stale_close_date",
            "severity": "warning",
            "count": len(stale),
            "message": f"{len(stale)} open deals have close dates in the past",
            "deal_ids": [d["id"] for d in stale[:5]],
        })

    # Check for missing close dates
    no_close = [d for d in deals if not d["is_closed"] and not d["close_date"]]
    if no_close:
        issues.append({
            "check": "missing_close_date",
            "severity": "warning",
            "count": len(no_close),
            "message": f"{len(no_close)} open deals have no close date",
            "deal_ids": [d["id"] for d in no_close[:5]],
        })

    # Overall status
    has_errors = any(i["severity"] == "error" for i in issues)
    has_warnings = any(i["severity"] == "warning" for i in issues)
    overall = "error" if has_errors else "warning" if has_warnings else "healthy"

    return {
        "overall": overall,
        "issue_count": len(issues),
        "issues": issues,
        "last_checked": AS_OF.isoformat(),
    }


def build_top_down_plan(targets: dict) -> dict:
    """Build top_down_plan from targets.yaml."""
    q_targets = targets.get("quarterly_targets", {})
    annual = safe_float(targets.get("annual_target", 40000000))

    return {
        "annual_target": round(annual),
        "quarterly_targets": {k: round(safe_float(v)) for k, v in q_targets.items()},
        "monthly_targets": [
            round(safe_float(q_targets.get(["Q1", "Q2", "Q3", "Q4"][i // 3], 0)) / 3)
            for i in range(12)
        ],
        "source": "targets.yaml",
    }


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def build_snapshot() -> dict:
    """Assemble the full snapshot from CSV data and config."""
    print("Loading data and config...")
    deals = load_deals()
    stage_history = load_stage_history()
    assumptions = load_yaml("assumptions.yaml")
    roster_yaml = load_yaml("roster.yaml")
    targets = load_yaml("targets.yaml")
    stages_config = load_yaml("stages.yaml")

    print(f"  Loaded {len(deals)} deals ({sum(1 for d in deals if not d['is_closed'])} open)")
    print(f"  Loaded {len(stage_history)} stage history records")

    print("Computing actuals...")
    actuals = build_actuals(deals)

    print("Building pipeline...")
    pipeline = build_pipeline(deals, stages_config)

    print("Computing rates...")
    rates = build_rates(deals, stage_history, assumptions, stages_config)

    print("Building roster...")
    roster = build_roster(roster_yaml)

    print("Computing model output...")
    model_output = build_model_output(
        deals, actuals, roster["effective_capacity"],
        assumptions, targets, stages_config,
    )

    print("Building scenario building blocks...")
    scenario_bb = build_scenario_building_blocks(
        roster["effective_capacity"], model_output, rates, deals,
    )

    print("Checking data health...")
    health_status = build_health_status(deals)

    print("Building top-down plan...")
    top_down_plan = build_top_down_plan(targets)

    # Beginning ARR: sum of all closed-won deals before FY start
    pre_fy_won = [d for d in deals if d["is_won"]
                  and d["close_date"] and d["close_date"] < "2026-02-01"]
    beginning_arr = sum(d["amount"] for d in pre_fy_won) if pre_fy_won else 12000000

    # Assemble
    snapshot = {
        "schema_version": "1.0.0",
        "engine_version": "1.0.0",
        "profile_id": "acme-saas",
        "capabilities": {
            "has_stage_history": True,
            "has_contacts": True,
            "has_companies": True,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "git_sha": git_sha(),
        "as_of": AS_OF.isoformat(),
        "actuals": actuals,
        "pipeline": pipeline,
        "rates": rates,
        "roster": roster,
        "model_output": model_output,
        "scenario_building_blocks": scenario_bb,
        "building_blocks": scenario_bb,  # Alias for backward compat
        "assumptions": {
            "stage_rates": assumptions.get("stage_rates", {}),
            "lookback_days": assumptions.get("lookback_days", 365),
            "monte_carlo_iterations": assumptions.get("monte_carlo_iterations", 10000),
        },
        "health_status": health_status,
        "beginning_arr": round(beginning_arr),
        "beginning_arr_provenance": {
            "source": "csv_closed_won_before_fy_start",
            "deal_count": len(pre_fy_won),
            "note": "Sum of closed-won amounts with close_date before 2026-02-01",
        },
        "bookings_summary_provenance": {
            "source": "acme-saas-csv",
            "methodology": "Direct sum from deals.csv closed-won records",
        },
        "top_down_plan": top_down_plan,
        "provenance": {
            "generator": "generate_acme_snapshot.py",
            "data_source": "engine/data/acme-saas/",
            "config_source": "engine/config/profiles/acme-saas/",
        },
    }

    # -----------------------------------------------------------------------
    # Optional target_setter block — mirrors generate_snapshot.py logic.
    # Emitted when the profile has scenarios.yaml and/or target_setter_defaults
    # in assumptions.yaml.  Uses the bundled snapshot's funnel_rates so the
    # observed_scenario values are always consistent with the page data.
    # -----------------------------------------------------------------------
    ts_scenarios = _load_scenarios_yaml("acme-saas")
    raw_assumptions = _load_raw_assumptions("acme-saas")
    ts_observed = _build_observed_scenario(raw_assumptions, snapshot)
    if ts_scenarios or ts_observed:
        snapshot["target_setter"] = {}
        if ts_observed:
            snapshot["target_setter"]["observed_scenario"] = ts_observed
        if ts_scenarios:
            snapshot["target_setter"]["scenarios"] = ts_scenarios

    return snapshot


def main() -> None:
    snapshot = build_snapshot()

    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, default=str)

    # Summary stats
    bb = snapshot["model_output"]["bookings_bridge"]
    trajectory_total = sum(bb["total_expected"])
    plan_total = sum(bb["plan_total"])
    gap = plan_total - trajectory_total
    gap_pct = gap / plan_total if plan_total else 0

    print(f"\nSnapshot written to {OUTPUT_FILE}")
    print(f"  as_of: {snapshot['as_of']}")
    print(f"  deals: {len(snapshot['pipeline']['deals'])} open")
    print(f"  beginning_arr: ${snapshot['beginning_arr']:,.0f}")
    print(f"  trajectory: ${trajectory_total:,.0f}")
    print(f"  plan: ${plan_total:,.0f}")
    print(f"  gap: ${gap:,.0f} ({gap_pct:.1%})")
    print(f"  health: {snapshot['health_status']['overall']}")
    print(f"  git_sha: {snapshot['git_sha']}")


if __name__ == "__main__":
    main()

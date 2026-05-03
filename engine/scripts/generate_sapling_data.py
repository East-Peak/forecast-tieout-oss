#!/usr/bin/env python3
"""
Generate deterministic CSV data for the Sapling Industries demo org.

Sapling Industries FY26 profile narrative:
- $40M beginning ARR → $60M new ARR → $100M EOY (150% YoY)
- Three-segment story: enterprise grinding (legal bottleneck), mid-market
  the engine, commercial the surprise outperformer (+60% vs plan)
- as_of = 2026-05-03

Produces three CSV files in engine/data/sapling-industries/:
  deals.csv, team_members.csv, stage_history.csv

Usage:
    python -m engine.scripts.generate_sapling_data
    python -m engine.scripts.generate_sapling_data --output-dir /tmp
    python -m engine.scripts.generate_sapling_data --verify
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "engine" / "data" / "sapling-industries"
ROSTER_PATH = REPO_ROOT / "engine" / "config" / "profiles" / "sapling-industries" / "roster.yaml"

# ---------------------------------------------------------------------------
# Fixed seed for determinism
# ---------------------------------------------------------------------------

SEED = 2026

# ---------------------------------------------------------------------------
# Calendar / temporal anchors
# Feb-start FY26: Q1=Feb/Mar/Apr, Q2=May/Jun/Jul, Q3=Aug/Sep/Oct, Q4=Nov/Dec/Jan(2027)
# ---------------------------------------------------------------------------

AS_OF = date(2026, 5, 3)
FY_START = date(2026, 2, 1)
FY_Q1_END = date(2026, 4, 30)
FY_Q2_START = date(2026, 5, 1)
FY_Q2_END = date(2026, 7, 31)
FY_Q3_START = date(2026, 8, 1)
FY_Q3_END = date(2026, 10, 31)
FY_Q4_START = date(2026, 11, 1)
FY_Q4_END = date(2027, 1, 31)

# Historical window for backfill deals
HIST_START = date(2025, 8, 1)

# ---------------------------------------------------------------------------
# Deal parameters per brief sections B & F
# ---------------------------------------------------------------------------

TOTAL_DEALS = 200
OPEN_DEALS = 118
CLOSED_WON_YTD = 42   # close_date in [2026-02-01, 2026-05-03]
CLOSED_LOST_YTD = 40  # close_date in [2026-02-01, 2026-05-03]

# YTD bookings target (to anchor amounts): $11.6M won, $9.4M lost
YTD_WON_ARR_TARGET = 11_600_000
YTD_LOST_ARR_TARGET = 9_400_000

# Open pipeline at as_of: $56.8M total open
OPEN_PIPELINE_TARGET = 56_800_000

# Open stage distribution (pct of 118 open deals)
OPEN_STAGE_DIST = {
    "Qualification":         0.19,  # S2 per brief — "19%"
    "Technical Evaluation":  0.28,  # S3
    "Business Case":         0.35,  # S4
    "Negotiation":           0.18,  # S5
}

# Segment distribution by deal count (all deals)
SEGMENT_DIST = {"enterprise": 0.28, "mid_market": 0.44, "commercial": 0.28}

# Source channel distribution by count
CHANNEL_DIST = {
    "inbound":    0.36,
    "outbound":   0.24,
    "ae_self_gen": 0.18,
    "partner":    0.12,
    "self_serve": 0.10,
}

# ACV parameters (mean, std, min, max) per segment
ACV_PARAMS = {
    "enterprise":  {"mean": 780_000, "std": 280_000, "min": 320_000, "max": 1_900_000},
    "mid_market":  {"mean": 240_000, "std":  80_000, "min": 110_000, "max":   520_000},
    "commercial":  {"mean":  58_000, "std":  22_000, "min":  18_000, "max":   120_000},
}

# Median cycle days per segment (for creating realistic created_date)
CYCLE_DAYS = {"enterprise": 119, "mid_market": 49, "commercial": 21}

# Win rate per segment (used for generating closed deals)
WIN_RATE = {"enterprise": 0.18, "mid_market": 0.31, "commercial": 0.39}

# Stage days by segment (for stage history generation)
STAGE_DAYS = {
    "enterprise":  {"Discovery": 12, "Qualification": 18, "Technical Evaluation": 27, "Business Case": 60, "Negotiation": 21},
    "mid_market":  {"Discovery":  7, "Qualification": 10, "Technical Evaluation": 14, "Business Case": 16, "Negotiation":  9},
    "commercial":  {"Discovery":  3, "Qualification":  4, "Technical Evaluation":  6, "Business Case":  7, "Negotiation":  3},
}

# Slip probabilities per segment (once, twice, thrice)
SLIP_PROBS = {
    "enterprise": (0.41, 0.23, 0.09),
    "mid_market": (0.23, 0.09, 0.03),
    "commercial": (0.10, 0.03, 0.01),
}

OPEN_STAGES_ORDERED = ["Discovery", "Qualification", "Technical Evaluation", "Business Case", "Negotiation"]
TERMINAL_WON  = "Closed Won"
TERMINAL_LOST = "Closed Lost"

# ---------------------------------------------------------------------------
# Account name banks per brief section F (industrial-flavor / tooling-flavor)
# ---------------------------------------------------------------------------

ENTERPRISE_ACCOUNTS = [
    "Telos Robotics", "Vellum Precision", "Iron Ridge Plastics", "Stratos Dynamics",
    "Cobalt Forge Industries", "Meridian Alloys", "Kronos Fabrication", "Aphelion Systems",
    "Crestline Manufacturing", "Nexus Heavy Industries", "Argon Metalworks", "Beryllium Tech",
    "Cerium Industrial", "Duratek Systems", "Elara Precision", "Fulcrum Engineering",
    "Garnet Industrial", "Halide Manufacturing", "Iridium Works", "Jericho Metals",
    "Kelvin Fabrication", "Lattice Industrial", "Monolith Precision", "Novum Engineering",
    "Obsidian Industries", "Palladium Systems", "Quorum Manufacturing", "Rhenium Tech",
    "Sinter Works", "Titanite Engineering", "Umbra Industrial", "Vanadium Systems",
    "Westbrook Manufacturing", "Xeon Fabrication", "Yuma Industrial", "Zephyr Precision",
    "Alcott Systems", "Bastion Manufacturing", "Ceres Industrial", "Dyson Metalworks",
    "Echelon Precision", "Flint Engineering", "Galena Works", "Harborview Manufacturing",
    "Ingot Systems", "Jasper Industrial", "Kinetic Fabrication", "Luminos Engineering",
    "Magnite Systems", "Noctilucent Manufacturing",
]

MID_MARKET_ACCOUNTS = [
    "Northspan Conveyance", "Brassline Components", "Foundry Lane Systems", "Millwork Partners",
    "Castleton Logistics", "Ridgeway Components", "Anvil Solutions", "Coldfront Systems",
    "Dellmar Services", "Eastbridge Fabrication", "Fairview Components", "Graymark Services",
    "Hillside Manufacturing", "Irondale Components", "Jameson Systems", "Kerrigan Solutions",
    "Lakewood Fabrication", "Markham Components", "Northgate Services", "Oakridge Systems",
    "Pinecrest Components", "Queensbury Services", "Riverside Fabrication", "Southfield Systems",
    "Timber Creek Components", "Upland Solutions", "Valmont Fabrication", "Westside Services",
    "Xerox Components", "Yellowstone Systems", "Ardmore Fabrication", "Belmont Components",
    "Claremont Services", "Dunmore Systems", "Elmwood Fabrication", "Foxhill Components",
    "Glenside Services", "Hillcrest Systems", "Ironwood Fabrication", "Junction Components",
    "Kingston Services", "Longview Systems", "Mapleton Fabrication", "Norden Components",
    "Orchard Systems", "Prescott Services", "Quakertown Fabrication", "Rosemont Components",
    "Stanton Services", "Thornwood Systems", "Upstate Fabrication", "Valhalla Components",
    "Weston Services", "Ximena Systems", "Yarmouth Fabrication", "Zenith Components",
    "Acton Services", "Bridgeway Systems", "Cromwell Fabrication", "Dalton Components",
    "Eastwood Services", "Foxboro Systems", "Groton Fabrication", "Hamden Components",
    "Iverton Services", "Jasper Systems", "Knightsbridge Fabrication", "Linden Components",
    "Millbrook Services", "Norwood Systems", "Oakwood Fabrication", "Pembrook Components",
    "Quincy Services", "Rockvale Systems", "Silverstone Fabrication", "Treemont Components",
    "Upton Services", "Vinemont Systems", "Willowbrook Fabrication", "Xerxes Components",
    "Yardley Services", "Zion Systems",
]

COMMERCIAL_ACCOUNTS = [
    "TorqueFox Warehouse", "QuickForge Ops", "SnapDock Field Tools", "GearPulse Works",
    "PitchBolt Ops", "CrankSet Tools", "SprintLift Depot", "BoltRush Services",
    "DrillPad Express", "FlexWeld Micro", "HammerLine Quick", "IronClip Fast",
    "JetFab Tools", "KeyBolt Lite", "LiftFlex Ops", "MicroForge Quick",
    "NanoWeld Tools", "OmniLift Depot", "PocketBolt Works", "QuickDrill Fast",
    "RapidFlex Tools", "SpeedForge Ops", "TinderBolt Works", "UltraLift Fast",
    "VaultBolt Depot", "WeldFlash Quick", "XpressForge Tools", "YieldBolt Works",
    "ZipLift Ops", "AgileBolt Tools", "BriefForge Fast", "CrispWeld Quick",
    "DashBolt Ops", "EasyLift Tools", "FastForge Works", "GlideWeld Depot",
    "HopBolt Quick", "ImpactForge Ops", "JumpLift Tools", "KeenBolt Works",
    "LeanForge Fast", "MiniWeld Quick", "NiftBolt Ops", "OmegaLift Tools",
    "ProForge Works", "QuickPulse Ops", "RapidWeld Fast", "SnapForge Tools",
    "TightBolt Works", "UniteLift Ops",
]

# Forecast categories by stage
FORECAST_CAT_BY_STAGE = {
    "Discovery":           "Pipeline",
    "Qualification":       "Pipeline",
    "Technical Evaluation": "Best Case",
    "Business Case":       "Best Case",
    "Negotiation":         "Commit",
    "Closed Won":          "Closed",
    "Closed Lost":         "Closed",
}

# AE IDs by segment (from roster.yaml)
AE_IDS = {
    "enterprise":  ["AE-E01", "AE-E02", "AE-E03", "AE-E04", "AE-E05",
                    "AE-E06", "AE-E07", "AE-E08", "AE-E09"],
    "mid_market":  ["AE-M01", "AE-M02", "AE-M03", "AE-M04", "AE-M05",
                    "AE-M06", "AE-M07", "AE-M08", "AE-M09", "AE-M10",
                    "AE-M11", "AE-M12", "AE-M13"],
    "commercial":  ["AE-C01", "AE-C02", "AE-C03", "AE-C04", "AE-C05",
                    "AE-C06", "AE-C07", "AE-C08"],
}

# AE names for owner field
AE_NAMES = {
    "AE-E01": "Naomi Walsh",       "AE-E02": "Tobias Mendez",
    "AE-E03": "Helena Park",       "AE-E04": "Diego Suzuki",
    "AE-E05": "Anika Volkov",      "AE-E06": "Claire Dufour",
    "AE-E07": "Malik Okoro",       "AE-E08": "Jenna Ellis",
    "AE-E09": "Priyanka Sen",
    "AE-M01": "Lucas Brennan",     "AE-M02": "Sienna Patel",
    "AE-M03": "Felix Andersson",   "AE-M04": "Wren Beauchamp",
    "AE-M05": "Ezra Lindgren",     "AE-M06": "Maya Brennan",
    "AE-M07": "Idris Vance",       "AE-M08": "Chloe Mercer",
    "AE-M09": "Benji Flores",      "AE-M10": "Hannah Cho",
    "AE-M11": "Matteo Russo",      "AE-M12": "Kira Wallace",
    "AE-M13": "Owen Delgado",
    "AE-C01": "June Holloway",     "AE-C02": "Rafael Costa",
    "AE-C03": "Imani Tate",        "AE-C04": "Brielle Navarro",
    "AE-C05": "Theo Mercer",       "AE-C06": "Paige Ellison",
    "AE-C07": "Andrej Novak",      "AE-C08": "Lila Hart",
}

# Commercial self-serve queue owner (for audit anomaly)
SELF_SERVE_QUEUE = "Self-Serve Queue"

# Top 4 mid-market reps (hold 42% of YTD won ARR)
TOP_MM_AES = ["AE-M01", "AE-M02", "AE-M03", "AE-M04"]

# Bottom-quarter AEs (pacing at 61% attainment)
BOTTOM_AES = ["AE-E08", "AE-E09", "AE-M11", "AE-M12", "AE-M13", "AE-C08"]

# The four emblematic enterprise deals stuck in legal review
LEGAL_REVIEW_DEALS = [
    {"id": "SAP-004", "name": "Telos Robotics - EMEA standardization",
     "account": "Telos Robotics", "owner_id": "AE-E01", "amount": 1_400_000,
     "created_date": date(2025, 12, 9), "close_date": date(2026, 4, 15)},
    {"id": "SAP-005", "name": "Vellum Precision - Audit fabric",
     "account": "Vellum Precision", "owner_id": "AE-E04", "amount": 1_180_000,
     "created_date": date(2026, 1, 16), "close_date": date(2026, 4, 22)},
    {"id": "SAP-011", "name": "Telos Robotics - NA compliance suite",
     "account": "Telos Robotics", "owner_id": "AE-E02", "amount": 920_000,
     "created_date": date(2025, 11, 30), "close_date": date(2026, 4, 28)},
    {"id": "SAP-012", "name": "Stratos Dynamics - Platform modernization",
     "account": "Stratos Dynamics", "owner_id": "AE-E03", "amount": 1_600_000,
     "created_date": date(2025, 12, 15), "close_date": date(2026, 4, 18)},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rand_date(start: date, end: date) -> date:
    delta = max((end - start).days, 0)
    return start + timedelta(days=random.randint(0, delta))


def _weekday(d: date) -> date:
    """Push to next Monday if weekend."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _acv(segment: str) -> float:
    p = ACV_PARAMS[segment]
    v = random.gauss(p["mean"], p["std"])
    v = max(p["min"], min(p["max"], v))
    return round(v / 1000) * 1000


def _channel(segment: str) -> str:
    """Pick source channel, with segment-aware weighting."""
    if segment == "commercial":
        # self_serve weighted higher for commercial
        channels = ["inbound", "outbound", "ae_self_gen", "partner", "self_serve"]
        weights  = [0.28, 0.15, 0.12, 0.08, 0.37]
    elif segment == "enterprise":
        channels = ["inbound", "outbound", "ae_self_gen", "partner", "self_serve"]
        weights  = [0.30, 0.28, 0.22, 0.18, 0.02]
    else:  # mid_market
        channels = ["inbound", "outbound", "ae_self_gen", "partner", "self_serve"]
        weights  = [0.38, 0.25, 0.20, 0.12, 0.05]
    return random.choices(channels, weights=weights, k=1)[0]


def _pick_ae(segment: str, weight_top: bool = False, weight_bottom: bool = False) -> str:
    ids = AE_IDS[segment]
    if weight_top and segment == "mid_market":
        # Overweight top 4 MMs
        weights = [4 if ae in TOP_MM_AES else 1 for ae in ids]
        return random.choices(ids, weights=weights, k=1)[0]
    if weight_bottom:
        weights = [3 if ae in BOTTOM_AES else 1 for ae in ids]
        return random.choices(ids, weights=weights, k=1)[0]
    return random.choice(ids)


def _account(segment: str, used: set[str]) -> str:
    pool = {
        "enterprise": ENTERPRISE_ACCOUNTS,
        "mid_market": MID_MARKET_ACCOUNTS,
        "commercial": COMMERCIAL_ACCOUNTS,
    }[segment]
    available = [a for a in pool if a not in used]
    if not available:
        available = pool
    name = random.choice(available)
    used.add(name)
    return name


def _fmt_dt(d: date) -> str:
    h = random.randint(8, 17)
    m = random.choice([0, 15, 30, 45])
    return f"{d.isoformat()}T{h:02d}:{m:02d}:00"


def _slip_count(segment: str) -> int:
    once, twice, thrice = SLIP_PROBS[segment]
    r = random.random()
    if r < thrice:
        return 3
    if r < twice:
        return 2
    if r < once:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Stage history generation
# ---------------------------------------------------------------------------


def _gen_stage_history(
    deal_id: str,
    segment: str,
    stages: list[str],   # ordered list of stages traversed (e.g. ["Discovery", "Qualification", "Closed Won"])
    created: date,
    close_date: date,
    is_legal_review: bool = False,
) -> list[dict]:
    """Generate realistic stage transitions for a deal."""
    rows: list[dict] = []
    days = STAGE_DAYS[segment]
    cur = created

    for i, stage in enumerate(stages):
        from_stage = "" if i == 0 else stages[i - 1]
        rows.append({
            "deal_id": deal_id,
            "from_stage": from_stage,
            "to_stage": stage,
            "transition_date": _fmt_dt(cur),
        })
        if i < len(stages) - 1:
            next_stage = stages[i + 1]
            base_days = days.get(stage, 14)
            # Add slip jitter
            slips = _slip_count(segment)
            extra = slips * int(base_days * 0.4)
            dwell = base_days + random.randint(-base_days // 4, base_days // 2) + extra

            # Legal review: Business Case stage gets extra 60-day dwell
            if is_legal_review and stage == "Business Case":
                dwell = 60 + random.randint(0, 30)

            cur = _weekday(cur + timedelta(days=max(1, dwell)))
            # Don't overshoot close_date for terminal transitions
            if next_stage in (TERMINAL_WON, TERMINAL_LOST) and cur > close_date:
                cur = _weekday(close_date - timedelta(days=random.randint(1, 5)))
                if cur < created:
                    cur = created + timedelta(days=1)
    return rows


def _stages_for_open(current_stage: str, segment: str) -> list[str]:
    """Return the traversed stage list for an open deal at current_stage."""
    idx = OPEN_STAGES_ORDERED.index(current_stage)
    stages = OPEN_STAGES_ORDERED[: idx + 1]
    # Occasionally skip a middle stage (not first)
    if len(stages) > 2 and random.random() < 0.15:
        skip = random.randint(1, len(stages) - 2)
        stages = stages[:skip] + stages[skip + 1:]
    return stages


def _stages_for_won(segment: str) -> list[str]:
    stages = list(OPEN_STAGES_ORDERED)
    if len(stages) > 2 and random.random() < 0.25:
        skip = random.randint(1, len(stages) - 2)
        stages = stages[:skip] + stages[skip + 1:]
    stages.append(TERMINAL_WON)
    return stages


def _stages_for_lost(segment: str) -> list[str]:
    lose_at = random.randint(1, len(OPEN_STAGES_ORDERED) - 1)
    stages = OPEN_STAGES_ORDERED[: lose_at + 1]
    if len(stages) > 2 and random.random() < 0.20:
        skip = random.randint(1, len(stages) - 2)
        stages = stages[:skip] + stages[skip + 1:]
    stages.append(TERMINAL_LOST)
    return stages


# ---------------------------------------------------------------------------
# Deal generation
# ---------------------------------------------------------------------------


def _make_deal_row(
    deal_id: str,
    name: str,
    account: str,
    owner_id: str,
    segment: str,
    source_channel: str,
    stage: str,
    amount: float,
    created_date: date,
    close_date: date,
    is_closed: bool,
    is_won: bool,
    lost_reason: str = "",
    raw_stage: str = "",
    deal_type: str = "new_business",
) -> dict:
    fc = FORECAST_CAT_BY_STAGE.get(stage, "Pipeline")
    if is_closed:
        fc = "Closed"
    return {
        "id": deal_id,
        "name": name,
        "account": account,
        "owner": AE_NAMES.get(owner_id, owner_id),
        "owner_id": owner_id,
        "segment": segment,
        "source_channel": source_channel,
        "stage": stage,
        "amount": int(amount) if amount else "",
        "arr": int(amount) if amount else "",
        "created_date": created_date.isoformat(),
        "close_date": close_date.isoformat() if close_date else "",
        "is_closed": "true" if is_closed else "false",
        "is_won": "true" if is_won else "false",
        "lost_reason": lost_reason,
        "raw_stage": raw_stage or stage,
        "type": deal_type,
        "forecast_category": fc,
    }


def generate_deals() -> tuple[list[dict], list[dict]]:
    """Generate 200 deals + stage_history.  Returns (deals, history)."""
    deals: list[dict] = []
    history: list[dict] = []
    used_accounts: set[str] = set()
    counter = 0

    def deal_id() -> str:
        nonlocal counter
        counter += 1
        return f"SAP-{counter:03d}"

    # -------------------------------------------------------------------------
    # 1) ANCHOR DEALS — from the brief's sample rows (pinned IDs)
    # -------------------------------------------------------------------------

    # SAP-001 Brassline — mid_market closed won YTD
    did = "SAP-001"
    counter = max(counter, 1)
    deals.append(_make_deal_row(
        did, "Brassline Components - Multi-plant rollout", "Brassline Components",
        "AE-M02", "mid_market", "outbound", TERMINAL_WON,
        420_000, date(2026, 1, 12), date(2026, 4, 24), True, True,
    ))
    history.extend(_gen_stage_history(did, "mid_market", _stages_for_won("mid_market"),
                                      date(2026, 1, 12), date(2026, 4, 24)))
    used_accounts.add("Brassline Components")

    # SAP-002 Northspan — mid_market closed won YTD
    did = "SAP-002"
    counter = max(counter, 2)
    deals.append(_make_deal_row(
        did, "Northspan Conveyance - Workforce hub", "Northspan Conveyance",
        "AE-M01", "mid_market", "inbound", TERMINAL_WON,
        285_000, date(2026, 2, 3), date(2026, 4, 28), True, True,
    ))
    history.extend(_gen_stage_history(did, "mid_market", _stages_for_won("mid_market"),
                                      date(2026, 2, 3), date(2026, 4, 28)))
    used_accounts.add("Northspan Conveyance")

    # SAP-003 TorqueFox — commercial closed won YTD
    did = "SAP-003"
    counter = max(counter, 3)
    deals.append(_make_deal_row(
        did, "TorqueFox Warehouse - Self-serve expansion", "TorqueFox Warehouse",
        "AE-C04", "commercial", "inbound", TERMINAL_WON,
        64_000, date(2026, 3, 7), date(2026, 4, 30), True, True, deal_type="expansion",
    ))
    history.extend(_gen_stage_history(did, "commercial", _stages_for_won("commercial"),
                                      date(2026, 3, 7), date(2026, 4, 30)))
    used_accounts.add("TorqueFox Warehouse")

    # SAP-004 Telos Robotics — enterprise open in legal review (stale close date)
    did = "SAP-004"
    counter = max(counter, 4)
    deals.append(_make_deal_row(
        did, "Telos Robotics - EMEA standardization", "Telos Robotics",
        "AE-E01", "enterprise", "partner", "Business Case",
        1_400_000, date(2025, 12, 9), date(2026, 4, 15), False, False,
        raw_stage="Business Case - Legal Review",
    ))
    history.extend(_gen_stage_history(did, "enterprise",
                                      ["Discovery", "Qualification", "Technical Evaluation", "Business Case"],
                                      date(2025, 12, 9), date(2026, 4, 15), is_legal_review=True))
    used_accounts.add("Telos Robotics")

    # SAP-005 Vellum Precision — enterprise open in legal review (stale close date)
    did = "SAP-005"
    counter = max(counter, 5)
    deals.append(_make_deal_row(
        did, "Vellum Precision - Audit fabric", "Vellum Precision",
        "AE-E04", "enterprise", "partner", "Business Case",
        1_180_000, date(2026, 1, 16), date(2026, 4, 22), False, False,
        raw_stage="Business Case - Legal Review",
    ))
    history.extend(_gen_stage_history(did, "enterprise",
                                      ["Discovery", "Qualification", "Technical Evaluation", "Business Case"],
                                      date(2026, 1, 16), date(2026, 4, 22), is_legal_review=True))
    used_accounts.add("Vellum Precision")

    # SAP-006 QuickForge — commercial open qualification (self-serve, Lila Hart ramping)
    did = "SAP-006"
    counter = max(counter, 6)
    deals.append(_make_deal_row(
        did, "QuickForge Ops - Starter bundle", "QuickForge Ops",
        "AE-C08", "commercial", "inbound", "Qualification",
        36_000, date(2026, 4, 22), date(2026, 5, 29), False, False,
        raw_stage="Qualification",
    ))
    history.extend(_gen_stage_history(did, "commercial", ["Discovery", "Qualification"],
                                      date(2026, 4, 22), date(2026, 5, 29)))
    used_accounts.add("QuickForge Ops")

    # SAP-007 Foundry Lane — mid_market open technical evaluation
    did = "SAP-007"
    counter = max(counter, 7)
    deals.append(_make_deal_row(
        did, "Foundry Lane Systems - Instrumentation cloud", "Foundry Lane Systems",
        "AE-M05", "mid_market", "outbound", "Technical Evaluation",
        260_000, date(2026, 3, 18), date(2026, 6, 26), False, False,
    ))
    history.extend(_gen_stage_history(did, "mid_market",
                                      ["Discovery", "Qualification", "Technical Evaluation"],
                                      date(2026, 3, 18), date(2026, 6, 26)))
    used_accounts.add("Foundry Lane Systems")

    # SAP-008 Iron Ridge Plastics — enterprise closed lost YTD (legal review exceeded sponsor window)
    did = "SAP-008"
    counter = max(counter, 8)
    deals.append(_make_deal_row(
        did, "Iron Ridge Plastics - EU rollout", "Iron Ridge Plastics",
        "AE-E02", "enterprise", "partner", TERMINAL_LOST,
        760_000, date(2025, 11, 20), date(2026, 3, 27), True, False,
        lost_reason="Legal review exceeded sponsor window",
    ))
    history.extend(_gen_stage_history(did, "enterprise", _stages_for_lost("enterprise"),
                                      date(2025, 11, 20), date(2026, 3, 27)))
    used_accounts.add("Iron Ridge Plastics")

    # SAP-009 SnapDock — commercial closed lost YTD (chose lower-priced point solution)
    did = "SAP-009"
    counter = max(counter, 9)
    deals.append(_make_deal_row(
        did, "SnapDock Field Tools - Team edition", "SnapDock Field Tools",
        "AE-C07", "commercial", "inbound", TERMINAL_LOST,
        28_000, date(2026, 2, 25), date(2026, 4, 14), True, False,
        lost_reason="Chose lower-priced point solution",
    ))
    history.extend(_gen_stage_history(did, "commercial", _stages_for_lost("commercial"),
                                      date(2026, 2, 25), date(2026, 4, 14)))
    used_accounts.add("SnapDock Field Tools")

    # Two more legal-review enterprise deals (SAP-011, SAP-012 per LEGAL_REVIEW_DEALS)
    # SAP-010 reserved for another sample — generate a mid-market won
    did = "SAP-010"
    counter = max(counter, 10)
    deals.append(_make_deal_row(
        did, "Millwork Partners - Operations hub", "Millwork Partners",
        "AE-M02", "mid_market", "inbound", TERMINAL_WON,
        310_000, date(2026, 1, 20), date(2026, 4, 15), True, True,
    ))
    history.extend(_gen_stage_history(did, "mid_market", _stages_for_won("mid_market"),
                                      date(2026, 1, 20), date(2026, 4, 15)))
    used_accounts.add("Millwork Partners")

    # SAP-011, SAP-012 — two more stale enterprise legal review deals
    for i, lr in enumerate(LEGAL_REVIEW_DEALS[2:], start=11):
        did = f"SAP-{i:03d}"
        counter = max(counter, i)
        deals.append(_make_deal_row(
            did, lr["name"], lr["account"],
            lr["owner_id"], "enterprise", "partner", "Business Case",
            lr["amount"], lr["created_date"], lr["close_date"], False, False,
            raw_stage="Business Case - Legal Review",
        ))
        history.extend(_gen_stage_history(did, "enterprise",
                                          ["Discovery", "Qualification", "Technical Evaluation", "Business Case"],
                                          lr["created_date"], lr["close_date"], is_legal_review=True))
        used_accounts.add(lr["account"])

    counter = 12

    # -------------------------------------------------------------------------
    # 2) COMMERCIAL SELF-SERVE AUDIT ANOMALY — 2 rows with queue ownership
    # -------------------------------------------------------------------------
    for i in range(2):
        counter += 1
        did = f"SAP-{counter:03d}"
        acc = _account("commercial", used_accounts)
        created = _rand_date(date(2026, 3, 1), date(2026, 4, 15))
        close_dt = _weekday(created + timedelta(days=random.randint(14, 35)))
        amt = _acv("commercial")
        # These start with the self-serve queue as owner (anomaly), then get reassigned
        owner_id = random.choice(["AE-C01", "AE-C02"])
        deals.append(_make_deal_row(
            did, f"{acc} - Self-serve trial", acc,
            owner_id, "commercial", "self_serve", "Qualification",
            amt, created, close_dt, False, False,
            raw_stage="Qualification",
        ))
        # Stage history: initial entry under queue name
        history.append({
            "deal_id": did, "from_stage": "", "to_stage": "Discovery",
            "transition_date": _fmt_dt(created),
        })
        reassign_date = _weekday(created + timedelta(days=random.randint(3, 8)))
        history.append({
            "deal_id": did, "from_stage": "Discovery", "to_stage": "Qualification",
            "transition_date": _fmt_dt(reassign_date),
        })

    # -------------------------------------------------------------------------
    # 3) YTD CLOSED WON — fill up to CLOSED_WON_YTD (42 total, anchor deals count)
    # -------------------------------------------------------------------------
    # Anchors: SAP-001 (MM won), SAP-002 (MM won), SAP-003 (commercial won), SAP-010 (MM won) = 4 YTD won
    ytd_won_remaining = CLOSED_WON_YTD - 4

    # Track YTD won ARR to loosely scale amounts
    ytd_won_arr = 420_000 + 285_000 + 64_000 + 310_000  # anchors
    # Target: $11.6M — distribute the rest roughly
    avg_remaining_ytd_arr = max(
        10_000,
        (YTD_WON_ARR_TARGET - ytd_won_arr) / max(ytd_won_remaining, 1)
    )

    # Segment mix for YTD won: enterprise~18%, mid_market~52%, commercial~30%
    seg_weights_won = [0.18, 0.52, 0.30]
    segments_won = ["enterprise", "mid_market", "commercial"]

    for _ in range(ytd_won_remaining):
        counter += 1
        did = f"SAP-{counter:03d}"
        seg = random.choices(segments_won, weights=seg_weights_won, k=1)[0]
        acc = _account(seg, used_accounts)
        owner = _pick_ae(seg, weight_top=(seg == "mid_market"))
        chan = _channel(seg)

        # Close in Feb-May 3 range
        close_dt = _rand_date(FY_START, AS_OF)
        cycle = int(CYCLE_DAYS[seg] * random.uniform(0.7, 1.3))
        created = _weekday(close_dt - timedelta(days=cycle))
        if created < HIST_START:
            created = HIST_START

        amt = _acv(seg)
        # Scale amounts loosely around target
        if seg == "enterprise":
            amt = max(ACV_PARAMS[seg]["min"], min(ACV_PARAMS[seg]["max"],
                      int(random.gauss(avg_remaining_ytd_arr * 2.5, 300_000) / 1000) * 1000))
        elif seg == "mid_market":
            amt = _acv(seg)
        else:
            amt = _acv(seg)

        stage_list = _stages_for_won(seg)
        product_desc = random.choice(["Platform rollout", "Operations suite", "Workforce hub",
                                       "Analytics platform", "Integration layer", "Compliance suite",
                                       "Field operations", "Starter bundle", "Team edition",
                                       "Infrastructure expansion"])
        deals.append(_make_deal_row(
            did, f"{acc} - {product_desc}", acc,
            owner, seg, chan, TERMINAL_WON,
            amt, created, close_dt, True, True,
        ))
        history.extend(_gen_stage_history(did, seg, stage_list, created, close_dt))

    # -------------------------------------------------------------------------
    # 4) YTD CLOSED LOST — CLOSED_LOST_YTD = 40 (anchor SAP-008, SAP-009 = 2)
    # -------------------------------------------------------------------------
    ytd_lost_remaining = CLOSED_LOST_YTD - 2

    lost_reasons = [
        "No decision - budget freeze",
        "Chose competitor solution",
        "Legal review exceeded sponsor window",
        "Champion left company",
        "Price - went with lower-cost alternative",
        "Chose lower-priced point solution",
        "Internal reprioritization",
        "Procurement stalled",
        "Technical requirements not met",
        "Timing - pushed to next fiscal",
    ]
    seg_weights_lost = [0.35, 0.38, 0.27]  # enterprise losses are more common pct

    for _ in range(ytd_lost_remaining):
        counter += 1
        did = f"SAP-{counter:03d}"
        seg = random.choices(segments_won, weights=seg_weights_lost, k=1)[0]
        acc = _account(seg, used_accounts)
        owner = _pick_ae(seg, weight_bottom=True)
        chan = _channel(seg)

        close_dt = _rand_date(FY_START, AS_OF)
        cycle = int(CYCLE_DAYS[seg] * random.uniform(0.5, 1.5))
        created = _weekday(close_dt - timedelta(days=cycle))
        if created < HIST_START:
            created = HIST_START

        amt = _acv(seg)
        stage_list = _stages_for_lost(seg)
        lost_rsn = random.choice(lost_reasons)

        product_desc = random.choice(["Platform rollout", "Enterprise suite", "Team edition",
                                       "Operations hub", "Analytics module", "Compliance layer",
                                       "Workforce platform", "Integration suite"])
        deals.append(_make_deal_row(
            did, f"{acc} - {product_desc}", acc,
            owner, seg, chan, TERMINAL_LOST,
            amt, created, close_dt, True, False,
            lost_reason=lost_rsn,
        ))
        history.extend(_gen_stage_history(did, seg, stage_list, created, close_dt))

    # -------------------------------------------------------------------------
    # 5) OPEN PIPELINE — 118 deals distributed per OPEN_STAGE_DIST
    # Legal review 4 anchor deals counted in SAP-004/005/011/012 = already 4 Business Case
    # -------------------------------------------------------------------------
    # Stage counts (per 118 open deals)
    stage_counts = {
        "Qualification":        round(0.19 * OPEN_DEALS),   # ~22
        "Technical Evaluation": round(0.28 * OPEN_DEALS),   # ~33
        "Business Case":        round(0.35 * OPEN_DEALS),   # ~41
        "Negotiation":          round(0.18 * OPEN_DEALS),   # ~21
    }
    # Adjust to hit exactly OPEN_DEALS including anchors already placed:
    # Anchors: SAP-004 (BC), SAP-005 (BC), SAP-006 (Qual), SAP-007 (TE), SAP-011 (BC), SAP-012 (BC),
    # plus 2 commercial self-serve (Qual)
    anchor_open_counts = {
        "Qualification": 3,        # SAP-006, 2 self-serve
        "Technical Evaluation": 1, # SAP-007
        "Business Case": 4,        # SAP-004/005/011/012
        "Negotiation": 0,
    }
    remaining_open = {}
    for stg, cnt in stage_counts.items():
        remaining_open[stg] = max(0, cnt - anchor_open_counts.get(stg, 0))

    # Trim to exactly hit OPEN_DEALS
    open_anchor_total = sum(anchor_open_counts.values())
    remaining_total = sum(remaining_open.values())
    target_remaining = OPEN_DEALS - open_anchor_total
    if remaining_total != target_remaining:
        diff = target_remaining - remaining_total
        # Adjust Negotiation or BC
        remaining_open["Negotiation"] = max(0, remaining_open.get("Negotiation", 0) + diff)

    # Segment weights for open deals
    seg_weights_open = [0.28, 0.44, 0.28]

    for stage, cnt in remaining_open.items():
        for _ in range(cnt):
            counter += 1
            did = f"SAP-{counter:03d}"
            seg = random.choices(["enterprise", "mid_market", "commercial"],
                                 weights=seg_weights_open, k=1)[0]
            acc = _account(seg, used_accounts)
            owner = _pick_ae(seg, weight_top=(seg == "mid_market"))
            chan = _channel(seg)

            # Close dates spread across Q2 and Q3 future quarters
            if stage == "Negotiation":
                close_range_start = AS_OF + timedelta(days=7)
                close_range_end = FY_Q2_END
            elif stage == "Business Case":
                close_range_start = AS_OF + timedelta(days=14)
                close_range_end = FY_Q3_START + timedelta(days=45)
            elif stage == "Technical Evaluation":
                close_range_start = AS_OF + timedelta(days=21)
                close_range_end = FY_Q3_END
            else:  # Qualification
                close_range_start = AS_OF + timedelta(days=28)
                close_range_end = FY_Q3_END

            close_dt = _rand_date(close_range_start, close_range_end)
            cycle = int(CYCLE_DAYS[seg] * random.uniform(0.6, 1.6))
            created = _weekday(close_dt - timedelta(days=cycle))
            if created < HIST_START:
                created = HIST_START

            amt = _acv(seg)
            stage_list = _stages_for_open(stage, seg)

            product_desc = random.choice(["Platform rollout", "Operations suite", "Workforce hub",
                                           "Analytics platform", "Integration layer", "Compliance suite",
                                           "Field operations", "Starter bundle", "Enterprise suite",
                                           "Infrastructure module"])
            raw_stg = stage
            # For enterprise in Business Case, sometimes mark as legal review
            if seg == "enterprise" and stage == "Business Case" and random.random() < 0.20:
                raw_stg = "Business Case - Legal Review"

            deals.append(_make_deal_row(
                did, f"{acc} - {product_desc}", acc,
                owner, seg, chan, stage,
                amt, created, close_dt, False, False,
                raw_stage=raw_stg,
            ))
            history.extend(_gen_stage_history(did, seg, stage_list, created, close_dt,
                                              is_legal_review=(raw_stg == "Business Case - Legal Review")))

    # Sort by ID for clean output
    deals.sort(key=lambda d: int(d["id"].split("-")[1]))
    history.sort(key=lambda h: (h["deal_id"], h["transition_date"]))
    return deals, history


# ---------------------------------------------------------------------------
# Team members generation
# ---------------------------------------------------------------------------


def generate_team_members() -> list[dict]:
    """Read roster.yaml and emit team_members.csv rows."""
    with open(ROSTER_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    members = data.get("team_members", [])
    rows = []
    for m in members:
        rows.append({
            "id": m["id"],
            "name": m["name"],
            "role": "AE" if m["role"] == "ae" else m["role"],
            "segment": m.get("segment") or "",
            "start_date": m.get("start_date") or "",
            "is_active": "true",
            "manager_id": m.get("manager_id") or "",
        })
    return rows


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------


def _to_csv(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fieldnames,
                            quoting=csv.QUOTE_MINIMAL, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().replace("\r\n", "\n")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)


DEALS_FIELDS = [
    "id", "name", "account", "owner", "owner_id", "segment", "source_channel",
    "stage", "amount", "arr", "created_date", "close_date",
    "is_closed", "is_won", "lost_reason", "raw_stage", "type", "forecast_category",
]

TEAM_FIELDS = ["id", "name", "role", "segment", "start_date", "is_active", "manager_id"]

HISTORY_FIELDS = ["deal_id", "from_stage", "to_stage", "transition_date"]


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def generate_all(output_dir: Path) -> dict[str, str]:
    random.seed(SEED)

    deals, history = generate_deals()
    team_rows = generate_team_members()

    results: dict[str, str] = {}

    deals_csv = _to_csv(deals, DEALS_FIELDS)
    history_csv = _to_csv(history, HISTORY_FIELDS)
    team_csv = _to_csv(team_rows, TEAM_FIELDS)

    _write(output_dir / "deals.csv", deals_csv)
    _write(output_dir / "stage_history.csv", history_csv)
    _write(output_dir / "team_members.csv", team_csv)

    results["deals.csv"] = deals_csv
    results["stage_history.csv"] = history_csv
    results["team_members.csv"] = team_csv

    return results


def _print_summary(deals: list[dict]) -> None:
    open_d = [d for d in deals if d["is_closed"] == "false"]
    ytd_won = [d for d in deals if d["is_won"] == "true" and
               d["close_date"] and date.fromisoformat(d["close_date"]) <= AS_OF
               and date.fromisoformat(d["close_date"]) >= FY_START]
    ytd_lost = [d for d in deals if d["is_closed"] == "true" and d["is_won"] == "false" and
                d["close_date"] and date.fromisoformat(d["close_date"]) <= AS_OF
                and date.fromisoformat(d["close_date"]) >= FY_START]
    open_arr = sum(float(d["amount"]) for d in open_d if d["amount"])
    ytd_won_arr = sum(float(d["amount"]) for d in ytd_won if d["amount"])
    ytd_lost_arr = sum(float(d["amount"]) for d in ytd_lost if d["amount"])
    print(f"  Total deals: {len(deals)}")
    print(f"  Open: {len(open_d)}  open pipeline ARR: ${open_arr:,.0f}  (target $56.8M)")
    print(f"  YTD won: {len(ytd_won)}  YTD won ARR: ${ytd_won_arr:,.0f}  (target $11.6M)")
    print(f"  YTD lost: {len(ytd_lost)}  YTD lost ARR: ${ytd_lost_arr:,.0f}  (target $9.4M)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Sapling Industries demo data CSVs.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--verify", action="store_true",
                        help="Regenerate and check counts (no file comparison).")
    args = parser.parse_args(argv)

    print(f"Generating Sapling Industries data to {args.output_dir} ...")
    results = generate_all(args.output_dir)

    for filename, content in results.items():
        lines = content.count("\n")
        print(f"  {filename}: {lines} rows (including header)")

    if args.verify:
        # Quick sanity check on deal counts
        random.seed(SEED)
        deals, _ = generate_deals()
        _print_summary(deals)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

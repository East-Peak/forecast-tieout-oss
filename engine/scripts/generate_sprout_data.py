#!/usr/bin/env python3
"""
Generate deterministic CSV data for the Sprout Labs demo org.

Sprout Labs profile narrative (FY26, Feb-start):
  - $2M beginning ARR, $8M new ARR target → $10M ending ARR
  - Feb-start fiscal: Q1FY26=Feb-Apr, Q2=May-Jul, Q3=Aug-Oct, Q4=Nov-Jan
  - 4 active AEs + 2 ramping AEs + founders Nadia Bloom & Evan Mercer
  - 2 SDRs + 1 SE (Rowan Khan)
  - as_of: 2026-05-03
  - YTD won: ~$1.45M (Feb-Apr 2026), YTD lost: ~$1.26M
  - Open pipeline at as_of: $3.85M

Produces three CSV files in engine/data/sprout-labs/:
  - deals.csv        25 deals (14 open / 6 closed-won YTD / 5 closed-lost YTD)
  - team_members.csv roster with AEs, founders, SDRs, SE
  - stage_history.csv stage transitions for all deals

Usage:
    python -m engine.scripts.generate_sprout_data
    python -m engine.scripts.generate_sprout_data --output-dir /tmp
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Parameters — all tunable values live near the top
# ---------------------------------------------------------------------------

SEED = 2026  # Fixed seed for reproducibility

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "engine" / "data" / "sprout-labs"

# Calendar anchors
AS_OF = date(2026, 5, 3)
FY_START = date(2026, 2, 1)   # Feb-start FY26

# YTD window: Feb 1 – May 3, 2026 (closed deals)
YTD_START = date(2026, 2, 1)
YTD_END = date(2026, 5, 3)

# Quarter boundaries (FY26)
Q1_START, Q1_END = date(2026, 2, 1), date(2026, 4, 30)
Q2_START, Q2_END = date(2026, 5, 1), date(2026, 7, 31)
Q3_START, Q3_END = date(2026, 8, 1), date(2026, 10, 31)
Q4_START, Q4_END = date(2026, 11, 1), date(2027, 1, 31)

# Segment parameters
SEGMENT_PARAMS = {
    "mid_market": {
        "acv_mean": 165_000,
        "acv_min":   90_000,
        "acv_max":  420_000,
        "acv_std":   55_000,
        "cycle_days_median": 71,
    },
    "commercial": {
        "acv_mean":  55_000,
        "acv_min":   12_000,
        "acv_max":   95_000,
        "acv_std":   18_000,
        "cycle_days_median": 43,
    },
}

# Open stage distribution: 14 open deals
# S1 29%, S2 29%, S3 21%, S4 14%, S5 7%
# 14 * 0.29 ≈ 4, 14 * 0.29 ≈ 4, 14 * 0.21 ≈ 3, 14 * 0.14 ≈ 2, 14 * 0.07 ≈ 1 = 14
OPEN_STAGE_COUNTS = {
    "S1": 4,  # Discovery
    "S2": 4,  # Qualification
    "S3": 3,  # Technical Evaluation
    "S4": 2,  # Business Case
    "S5": 1,  # Negotiation
}
assert sum(OPEN_STAGE_COUNTS.values()) == 14

# Stage names — short codes map to full names
STAGE_NAMES = {
    "S1": "Discovery",
    "S2": "Qualification",
    "S3": "Technical Evaluation",
    "S4": "Business Case",
    "S5": "Negotiation",
}

# Stage-history days-in-stage by segment
DAYS_IN_STAGE = {
    "mid_market": {
        "Discovery": 11,
        "Qualification": 17,
        "Technical Evaluation": 26,
        "Business Case": 18,
        "Negotiation": 11,
    },
    "commercial": {
        "Discovery": 7,
        "Qualification": 10,
        "Technical Evaluation": 14,
        "Business Case": 9,
        "Negotiation": 6,
    },
}

# Slip probabilities
SLIP_PROB = {
    "mid_market": {"once": 0.28, "twice": 0.12, "thrice": 0.03},
    "commercial": {"once": 0.19, "twice": 0.07, "thrice": 0.01},
}

# Source channel distribution (applied across all deals)
SOURCE_CHANNELS = ["inbound", "outbound", "ae_self_gen"]
SOURCE_WEIGHTS  = [0.52,      0.28,       0.20]

# AE assignments (for open + closed deals)
# Maya Singh: 29% of open pipe, 34% of YTD won ARR → high allocation
# Bottom quartile (Owen Hart, Leo Alvarez): 17% of open pipe
AE_NAMES = ["Maya Singh", "Jordan Reyes", "Tessa Nguyen", "Owen Hart", "Priya Desai", "Leo Alvarez"]
AE_SEGMENTS = {
    "Maya Singh":   "mid_market",
    "Jordan Reyes": "mid_market",
    "Tessa Nguyen": "mid_market",
    "Owen Hart":    "commercial",
    "Priya Desai":  "mid_market",
    "Leo Alvarez":  "commercial",
}
AE_STATUS = {
    "Maya Singh":   "tenured",
    "Jordan Reyes": "tenured",
    "Tessa Nguyen": "tenured",
    "Owen Hart":    "tenured",
    "Priya Desai":  "ramping",
    "Leo Alvarez":  "ramping",
}

FOUNDER_NAMES = ["Nadia Bloom", "Evan Mercer"]
SDR_NAMES     = ["Jamie Weston", "Dani Ortega"]
SE_NAME       = "Rowan Khan"

# Biotech/devtools/robotics Bay Area + Boston company names
ACCOUNT_NAMES_POOL = [
    # Bay Area flavor
    "Northline Biofabrication",
    "HarborForge Clinical",
    "Alder Creek Robotics",
    "SignalNest Robotics",
    "Maple Thread Health",
    "Blue Current Dental",
    "Helio Harbor Health",
    "Cypress Bridge Genomics",
    "Ironwood Biotech",
    "Redwood Circuit Labs",
    "Bayshore Devtools",
    "Crestline Automation",
    "Saffron Gate Systems",
    "Stillwater Biosystems",
    "Marin Edge Analytics",
    "Cinder Path Media",
    "Pocket Harbor Games",
    # Boston flavor
    "Kendall Bioworks",
    "Charles River Robotics",
    "Beacon Hill Genomics",
    "Newbury DevOps",
    "Cambridge Biosensors",
    "Somerville Automation",
    "Lexington DevTools",
    "Patriot Biosystems",
]

# Deal name suffixes by industry/stage
DEAL_SUFFIXES = [
    "Platform rollout",
    "Compliance cloud",
    "Advisor expansion",
    "Analytics pilot",
    "Ops suite",
    "Telemetry pilot",
    "ICP check",
    "Founder discovery",
    "Security module",
    "Devtools integration",
    "Genomics platform",
    "Robotics OS",
    "MLOps suite",
    "Data fabric",
    "Observability stack",
    "CI/CD platform",
    "Bioinformatics suite",
    "Cell therapy tracking",
    "Clinical ops cloud",
    "Lab automation platform",
]

# Forecast categories
FORECAST_CAT = {
    "S1": "Pipeline",
    "S2": "Pipeline",
    "S3": "Best Case",
    "S4": "Commit",
    "S5": "Commit",
    "Won": "Closed",
    "Lost": "Closed",
}

# Raw stage labels for founder-owned anomaly deals
FOUNDER_RAW_STAGES = {
    "S1": "Discovery - ICP Check",
    "S2": "Qualification - ICP Check",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rdate(start: date, end: date) -> date:
    delta = (end - start).days
    if delta <= 0:
        return start
    return start + timedelta(days=random.randint(0, delta))


def _weekday(d: date) -> date:
    """Advance d to next weekday if it falls on a weekend."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _fmt_dt(d: date) -> str:
    h = random.randint(8, 17)
    m = random.choice([0, 15, 30, 45])
    return f"{d.isoformat()}T{h:02d}:{m:02d}:00"


def _acv(segment: str) -> int:
    p = SEGMENT_PARAMS[segment]
    v = random.gauss(p["acv_mean"], p["acv_std"])
    v = max(p["acv_min"], min(p["acv_max"], v))
    return int(round(v / 1000) * 1000)


def _pick_source() -> str:
    return random.choices(SOURCE_CHANNELS, weights=SOURCE_WEIGHTS, k=1)[0]


def _slip_count(segment: str) -> int:
    """How many times does this deal slip (stage re-date)? 0/1/2/3."""
    sp = SLIP_PROB[segment]
    r = random.random()
    if r < sp["thrice"]:
        return 3
    if r < sp["twice"]:
        return 2
    if r < sp["once"]:
        return 1
    return 0


def _stage_history_for_deal(
    deal_id: str,
    segment: str,
    stages: list[str],   # ordered list of stages traversed
    created: date,
    *,
    anomaly_s1_to_s2_stale: bool = False,
) -> list[dict]:
    """Generate stage transitions for one deal.

    anomaly_s1_to_s2_stale: if True, simulate 21+ days at S1→S2 without
    amount/close-date cleanup (represented as a prolonged stay in S2).
    """
    rows = []
    current = created
    for i, stage in enumerate(stages):
        from_s = "" if i == 0 else stages[i - 1]
        rows.append({
            "deal_id": deal_id,
            "from_stage": from_s,
            "to_stage": stage,
            "transition_date": _fmt_dt(current),
        })
        if i < len(stages) - 1:
            dwell = DAYS_IN_STAGE.get(segment, {}).get(stage, 14)
            slips = _slip_count(segment)
            dwell += slips * dwell  # each slip adds one full dwell period
            # For the S1→S2 stale anomaly, force at least 21 days in Qualification
            if anomaly_s1_to_s2_stale and stage == "Qualification":
                dwell = max(dwell, 21)
            current = _weekday(current + timedelta(days=dwell + random.randint(-3, 3)))
    return rows


# ---------------------------------------------------------------------------
# Sample deal rows (anchors from brief Section E)
# ---------------------------------------------------------------------------

SAMPLE_DEALS = [
    {
        "id": "SPR-001",
        "name": "Northline Biofabrication - Platform rollout",
        "account": "Northline Biofabrication",
        "owner": "Maya Singh",
        "segment": "mid_market",
        "source_channel": "inbound",
        "stage": "Won",
        "amount": 420000,
        "arr": 420000,
        "created_date": "2026-01-08",
        "close_date": "2026-04-18",
        "is_closed": True,
        "is_won": True,
        "lost_reason": "",
        "raw_stage": "Closed Won",
        "type": "new_business",
        "forecast_category": "Closed",
    },
    {
        "id": "SPR-002",
        "name": "HarborForge Clinical - Compliance cloud",
        "account": "HarborForge Clinical",
        "owner": "Jordan Reyes",
        "segment": "mid_market",
        "source_channel": "inbound",
        "stage": "Won",
        "amount": 310000,
        "arr": 310000,
        "created_date": "2026-01-19",
        "close_date": "2026-04-25",
        "is_closed": True,
        "is_won": True,
        "lost_reason": "",
        "raw_stage": "Closed Won",
        "type": "new_business",
        "forecast_category": "Closed",
    },
    {
        "id": "SPR-003",
        "name": "Alder Creek Robotics - Advisor expansion",
        "account": "Alder Creek Robotics",
        "owner": "Maya Singh",
        "segment": "mid_market",
        "source_channel": "ae_self_gen",
        "stage": "Won",
        "amount": 265000,
        "arr": 265000,
        "created_date": "2026-02-02",
        "close_date": "2026-04-29",
        "is_closed": True,
        "is_won": True,
        "lost_reason": "",
        "raw_stage": "Closed Won",
        "type": "new_business",
        "forecast_category": "Closed",
    },
    {
        "id": "SPR-004",
        "name": "Cinder Path Media - Analytics pilot",
        "account": "Cinder Path Media",
        "owner": "Owen Hart",
        "segment": "commercial",
        "source_channel": "inbound",
        "stage": "Lost",
        "amount": 42000,
        "arr": 42000,
        "created_date": "2026-02-11",
        "close_date": "2026-03-21",
        "is_closed": True,
        "is_won": False,
        "lost_reason": "No ICP fit after discovery",
        "raw_stage": "Closed Lost",
        "type": "new_business",
        "forecast_category": "Closed",
    },
    {
        "id": "SPR-005",
        "name": "Pocket Harbor Games - Ops suite",
        "account": "Pocket Harbor Games",
        "owner": "Tessa Nguyen",
        "segment": "mid_market",
        "source_channel": "inbound",
        "stage": "Lost",
        "amount": 185000,
        "arr": 185000,
        "created_date": "2026-01-27",
        "close_date": "2026-03-28",
        "is_closed": True,
        "is_won": False,
        "lost_reason": "Champion left before POC",
        "raw_stage": "Closed Lost",
        "type": "new_business",
        "forecast_category": "Closed",
    },
    {
        "id": "SPR-006",
        "name": "SignalNest Robotics - Telemetry pilot",
        "account": "SignalNest Robotics",
        "owner": "Priya Desai",
        "segment": "mid_market",
        "source_channel": "outbound",
        "stage": "S3",
        "amount": 180000,
        "arr": 180000,
        "created_date": "2026-03-12",
        "close_date": "2026-06-24",
        "is_closed": False,
        "is_won": False,
        "lost_reason": "",
        "raw_stage": "Technical Evaluation",
        "type": "new_business",
        "forecast_category": "Best Case",
    },
    {
        "id": "SPR-007",
        "name": "Maple Thread Health - ICP check",
        "account": "Maple Thread Health",
        "owner": "Nadia Bloom",
        "segment": "mid_market",
        "source_channel": "inbound",
        "stage": "S2",
        "amount": 0,
        "arr": 0,
        "created_date": "2026-03-18",
        "close_date": "2026-05-30",
        "is_closed": False,
        "is_won": False,
        "lost_reason": "",
        "raw_stage": "Qualification - ICP Check",
        "type": "new_business",
        "forecast_category": "Pipeline",
    },
    {
        "id": "SPR-008",
        "name": "Blue Current Dental - Founder discovery",
        "account": "Blue Current Dental",
        "owner": "Evan Mercer",
        "segment": "commercial",
        "source_channel": "inbound",
        "stage": "S1",
        "amount": 0,
        "arr": 0,
        "created_date": "2026-04-07",
        "close_date": "2026-06-15",
        "is_closed": False,
        "is_won": False,
        "lost_reason": "",
        "raw_stage": "Discovery - ICP Check",
        "type": "new_business",
        "forecast_category": "Pipeline",
    },
    {
        "id": "SPR-009",
        "name": "Helio Harbor Health - Security module",
        "account": "Helio Harbor Health",
        "owner": "Maya Singh",
        "segment": "mid_market",
        "source_channel": "ae_self_gen",
        "stage": "S5",
        "amount": 260000,
        "arr": 260000,
        "created_date": "2026-02-26",
        "close_date": "2026-05-21",
        "is_closed": False,
        "is_won": False,
        "lost_reason": "",
        "raw_stage": "Negotiation",
        "type": "new_business",
        "forecast_category": "Commit",
    },
]

# Verify sample deals: 3 closed-won YTD, 2 closed-lost YTD, 4 open
# SPR-001,002,003 won (Apr 18/25/29) — YTD; SPR-004,005 lost — YTD
# SPR-006,007,008,009 open
# Remaining 16 deals generated programmatically below


# ---------------------------------------------------------------------------
# Programmatic deal generation
# ---------------------------------------------------------------------------

def _build_generated_deals(seed_state: random.Random) -> list[dict]:
    """Generate 16 additional deals to complement the 9 sample anchors.

    Target totals:
      14 open (we have 4 from samples, need 10 more)
      6 closed-won YTD (we have 3, need 3 more)
      5 closed-lost YTD (we have 2, need 3 more)

    Open pipeline ~$3.85M total (anchors contribute ~$440k open, so
    generated open deals need ~$3.41M).

    YTD won ~$1.45M (anchors: 420+310+265=$995k, need ~$455k more).
    YTD lost ~$1.26M (anchors: 42+185=$227k, need ~$1.03M more).
    """
    rng = seed_state
    deals = []

    def _make_id(n: int) -> str:
        return f"SPR-{n:03d}"

    counter = 10  # start after SPR-009

    # ---- 3 more closed-won YTD deals ----
    # Need ~$455k total from these 3 to reach $1.45M YTD won target
    # (samples contribute $995k; 995+455=1450)
    won_specs = [
        # (owner, segment, source, amount, created, close_date, acct_suffix, deal_suffix)
        ("Maya Singh",   "mid_market", "ae_self_gen", 190000, "2026-01-15", "2026-03-14",
         "Cypress Bridge Genomics",    "Genomics platform"),
        ("Tessa Nguyen", "mid_market", "outbound",    212000, "2026-01-22", "2026-03-19",
         "Kendall Bioworks",           "MLOps suite"),
        ("Owen Hart",    "commercial", "outbound",     53000, "2026-02-05", "2026-04-10",
         "Bayshore Devtools",          "CI/CD platform"),
    ]
    for (owner, seg, src, amt, created, close, acct, suffix) in won_specs:
        deals.append({
            "id": _make_id(counter),
            "name": f"{acct} - {suffix}",
            "account": acct,
            "owner": owner,
            "segment": seg,
            "source_channel": src,
            "stage": "Won",
            "amount": amt,
            "arr": amt,
            "created_date": created,
            "close_date": close,
            "is_closed": True,
            "is_won": True,
            "lost_reason": "",
            "raw_stage": "Closed Won",
            "type": "new_business",
            "forecast_category": "Closed",
        })
        counter += 1

    # ---- 3 more closed-lost YTD deals ----
    # Need ~$1.033M total from these 3 to reach $1.26M YTD lost target
    # (samples contribute $227k; 227+1033=1260)
    lost_specs = [
        # (owner, segment, source, amount, created, close_date, acct, suffix, lost_reason)
        ("Jordan Reyes", "mid_market", "inbound",  395000, "2025-12-10", "2026-02-28",
         "Stillwater Biosystems", "Lab automation platform",
         "Went with incumbent vendor"),
        ("Owen Hart",    "commercial", "inbound",   63000, "2026-01-15", "2026-03-05",
         "Marin Edge Analytics",  "Devtools integration",
         "No budget this quarter"),
        ("Tessa Nguyen", "mid_market", "inbound",  575000, "2025-12-20", "2026-04-02",
         "Charles River Robotics", "Robotics OS",
         "Lost to competitor at POC"),
    ]
    for (owner, seg, src, amt, created, close, acct, suffix, reason) in lost_specs:
        deals.append({
            "id": _make_id(counter),
            "name": f"{acct} - {suffix}",
            "account": acct,
            "owner": owner,
            "segment": seg,
            "source_channel": src,
            "stage": "Lost",
            "amount": amt,
            "arr": amt,
            "created_date": created,
            "close_date": close,
            "is_closed": True,
            "is_won": False,
            "lost_reason": reason,
            "raw_stage": "Closed Lost",
            "type": "new_business",
            "forecast_category": "Closed",
        })
        counter += 1

    # ---- 10 more open deals ----
    # Need stages: S1=4, S2=4, S3=3, S4=2, S5=1 (14 total)
    # Already have from samples: S3=1(SPR-006), S2=1(SPR-007), S1=1(SPR-008), S5=1(SPR-009)
    # Need: S1=3, S2=3, S3=2, S4=2, S5=0
    # Open pipe target breakdown:
    # Samples contribute: SPR-006 $180k, SPR-009 $260k = $440k
    # Generated 10 deals need: $3.85M - $440k = $3.41M
    # Distribution: S1×3=~$180k (two $0-founders + one commercial ~$45k)
    #               S2×3=~$290k (two $0-founders + one mid ~$290k)
    #               S3×2=~$960k (SDR-sourced mid-market, high conviction)
    #               S4×2=~$1.98M (near-close, large mid-market)
    # Total: ~$3.41M ✓
    open_specs = [
        # (owner, segment, source, stage_code, amount, created, close_date, acct, suffix, founder_owned)
        # S1 deals — 2 founder-owned ($0) + 1 commercial
        ("Nadia Bloom",  "mid_market", "inbound",  "S1", 0,      "2026-03-25", "2026-06-10",
         "Ironwood Biotech",       "ICP check",         True),   # founder_owned
        ("Evan Mercer",  "commercial", "inbound",  "S1", 0,      "2026-04-01", "2026-06-18",
         "Beacon Hill Genomics",   "Founder discovery", True),   # founder_owned
        ("Leo Alvarez",  "commercial", "outbound", "S1", 45000,  "2026-04-10", "2026-07-01",
         "Lexington DevTools",     "Devtools integration", False),
        # S2 deals — 2 founder-owned ($0) + 1 mid-market non-founder
        ("Nadia Bloom",  "mid_market", "inbound",  "S2", 0,      "2026-03-05", "2026-06-20",
         "Cambridge Biosensors",   "ICP check",         True),   # founder_owned
        ("Jordan Reyes", "mid_market", "outbound", "S2", 290000, "2026-03-08", "2026-07-15",
         "Crestline Automation",   "Robotics OS",       False),
        ("Evan Mercer",  "commercial", "inbound",  "S2", 0,      "2026-03-20", "2026-06-30",
         "Saffron Gate Systems",   "Analytics pilot",   True),   # 6th founder_owned
        # S3 deals — outbound SDR-sourced, high-conviction
        ("Maya Singh",   "mid_market", "outbound", "S3", 455000, "2026-02-15", "2026-07-10",
         "Redwood Circuit Labs",   "Observability stack", False),
        ("Tessa Nguyen", "mid_market", "ae_self_gen","S3",505000,"2026-03-01", "2026-07-22",
         "Somerville Automation",  "Lab automation platform", False),
        # S4 deals — large mid-market nearing close
        ("Maya Singh",   "mid_market", "outbound", "S4", 985000, "2026-01-20", "2026-06-05",
         "Newbury DevOps",         "MLOps suite",       False),
        ("Jordan Reyes", "mid_market", "ae_self_gen","S4",1125000,"2026-01-10","2026-06-17",
         "Patriot Biosystems",     "Cell therapy tracking", False),
    ]

    # founder-owned deals tracking
    # Samples SPR-007 (Nadia, S2) + SPR-008 (Evan, S1) = 2 founder-owned
    # open_specs adds 4 more (Nadia S1, Evan S1, Nadia S2, Evan S2) = 4
    # Total founder-owned with amount=0: 6 ✓
    founder_owned_ids: list[str] = []

    for spec in open_specs:
        (owner, seg, src, stage_code, amt, created, close_date, acct, suffix, is_founder_owned) = spec
        stage_name = STAGE_NAMES[stage_code]
        forecast_cat = FORECAST_CAT[stage_code]
        raw_stage = stage_name
        if is_founder_owned and stage_code in ("S1", "S2"):
            raw_stage = FOUNDER_RAW_STAGES[stage_code]

        deal = {
            "id": _make_id(counter),
            "name": f"{acct} - {suffix}",
            "account": acct,
            "owner": owner,
            "segment": seg,
            "source_channel": src,
            "stage": stage_code,
            "amount": amt,
            "arr": amt,
            "created_date": created,
            "close_date": close_date,
            "is_closed": False,
            "is_won": False,
            "lost_reason": "",
            "raw_stage": raw_stage,
            "type": "new_business",
            "forecast_category": forecast_cat,
        }
        if is_founder_owned:
            founder_owned_ids.append(_make_id(counter))
        deals.append(deal)
        counter += 1

    return deals, founder_owned_ids


# ---------------------------------------------------------------------------
# Stage history generation
# ---------------------------------------------------------------------------

def _build_stage_history(all_deals: list[dict], stale_s1s2_ids: list[str]) -> list[dict]:
    """Build stage_history rows for all 25 deals.

    Audit anomalies encoded:
    - 6 founder-owned deals: amount=0, raw_stage uses "Discovery/Qualification - ICP Check"
    - 2 deals moved S1→S2 without amount or close-date update for 21+ days
    """
    rows = []
    stale_set = set(stale_s1s2_ids)

    for deal in all_deals:
        deal_id = deal["id"]
        segment = deal["segment"]
        created = date.fromisoformat(deal["created_date"])
        is_closed = deal["is_closed"]
        is_won = deal["is_won"]
        stage_code = deal["stage"]

        if is_closed and is_won:
            # Full progression: Discovery → Qualification → Tech Eval → Biz Case → Negotiation → Won
            stages = ["Discovery", "Qualification", "Technical Evaluation", "Business Case", "Negotiation", "Closed Won"]
            # Sometimes skip one middle stage
            if random.random() < 0.25:
                skip = random.randint(1, 3)
                stages = [s for i, s in enumerate(stages) if i != skip]
        elif is_closed and not is_won:
            # Progressed to some stage then lost
            all_open = ["Discovery", "Qualification", "Technical Evaluation", "Business Case", "Negotiation"]
            # Pick where they lost
            lose_at = random.randint(1, 4)
            stages = all_open[:lose_at + 1] + ["Closed Lost"]
        else:
            # Open deal — go up to current stage
            stage_name = STAGE_NAMES.get(stage_code, stage_code)
            all_open = ["Discovery", "Qualification", "Technical Evaluation", "Business Case", "Negotiation"]
            if stage_name in all_open:
                idx = all_open.index(stage_name)
                stages = all_open[:idx + 1]
            else:
                stages = ["Discovery"]

        anomaly = deal_id in stale_set
        deal_rows = _stage_history_for_deal(
            deal_id, segment, stages, created,
            anomaly_s1_to_s2_stale=anomaly,
        )
        rows.extend(deal_rows)

    return rows


# ---------------------------------------------------------------------------
# Team members CSV
# ---------------------------------------------------------------------------

def _build_team_members() -> list[dict]:
    rows = []

    # Active AEs
    ae_data = [
        ("AE-M01", "Maya Singh",   "ae", "mid_market", "2025-03-10", True),
        ("AE-M02", "Jordan Reyes", "ae", "mid_market", "2025-06-02", True),
        ("AE-M03", "Tessa Nguyen", "ae", "mid_market", "2025-09-15", True),
        ("AE-C01", "Owen Hart",    "ae", "commercial", "2025-08-04", True),
        ("AE-M04", "Priya Desai",  "ae", "mid_market", "2026-03-03", True),
        ("AE-C02", "Leo Alvarez",  "ae", "commercial", "2026-04-14", True),
    ]
    for (tid, name, role, seg, start, active) in ae_data:
        rows.append({
            "id": tid,
            "name": name,
            "role": role,
            "segment": seg,
            "start_date": start,
            "is_active": "true" if active else "false",
            "manager_id": "",
        })

    # Founders
    rows.append({
        "id": "FOUND-01", "name": "Nadia Bloom", "role": "founder",
        "segment": "", "start_date": "2024-01-01",
        "is_active": "true", "manager_id": "",
    })
    rows.append({
        "id": "FOUND-02", "name": "Evan Mercer", "role": "founder",
        "segment": "", "start_date": "2024-01-01",
        "is_active": "true", "manager_id": "",
    })

    # SDRs
    rows.append({
        "id": "SDR-01", "name": "Jamie Weston", "role": "sdr",
        "segment": "", "start_date": "2026-01-15",
        "is_active": "true", "manager_id": "",
    })
    rows.append({
        "id": "SDR-02", "name": "Dani Ortega", "role": "sdr",
        "segment": "", "start_date": "2026-01-15",
        "is_active": "true", "manager_id": "",
    })

    # SE
    rows.append({
        "id": "SE-01", "name": "Rowan Khan", "role": "se",
        "segment": "", "start_date": "2025-11-01",
        "is_active": "true", "manager_id": "",
    })

    return rows


# ---------------------------------------------------------------------------
# CSV writing utilities
# ---------------------------------------------------------------------------

def _rows_to_csv(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames,
        quoting=csv.QUOTE_MINIMAL,
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().replace("\r\n", "\n")


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> str:
    content = _rows_to_csv(rows, fieldnames)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return content


# ---------------------------------------------------------------------------
# Owner name → ID mapping (matches team_members.csv ids)
# ---------------------------------------------------------------------------

OWNER_NAME_TO_ID: dict[str, str] = {
    "Maya Singh":   "AE-M01",
    "Jordan Reyes": "AE-M02",
    "Tessa Nguyen": "AE-M03",
    "Owen Hart":    "AE-C01",
    "Priya Desai":  "AE-M04",
    "Leo Alvarez":  "AE-C02",
    "Nadia Bloom":  "FOUND-01",
    "Evan Mercer":  "FOUND-02",
}

# Stage code → full model stage name (for CSV output, matching field_mappings)
STAGE_CODE_TO_NAME: dict[str, str] = {
    "S1": "Discovery",
    "S2": "Qualification",
    "S3": "Technical Evaluation",
    "S4": "Business Case",
    "S5": "Negotiation",
    "Won": "Closed Won",
    "Lost": "Closed Lost",
}

# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

# Engine-compatible deals.csv columns (owner_id required, source matches field_mappings)
DEALS_FIELDS = [
    "id", "name", "amount", "stage", "close_date", "owner_id",
    "type", "created_date", "segment", "source", "is_closed", "is_won",
    "arr", "forecast_category", "owner_name",
]

TEAM_FIELDS = ["id", "name", "role", "segment", "start_date", "is_active", "manager_id"]

HISTORY_FIELDS = ["deal_id", "from_stage", "to_stage", "transition_date"]


def _to_csv_deal(d: dict) -> dict:
    """Convert internal deal dict to engine-compatible CSV row."""
    stage_code = d["stage"]
    # Map stage code to full name; fall through if already a full name
    stage_name = STAGE_CODE_TO_NAME.get(stage_code, stage_code)
    owner_name = d["owner"]
    owner_id = OWNER_NAME_TO_ID.get(owner_name, owner_name)

    return {
        "id": d["id"],
        "name": d["name"],
        "amount": d["amount"] if d["amount"] != 0 else "",
        "stage": stage_name,
        "close_date": d["close_date"],
        "owner_id": owner_id,
        "type": d["type"],
        "created_date": d["created_date"],
        "segment": d["segment"],
        "source": d["source_channel"],
        "is_closed": "true" if d["is_closed"] else "false",
        "is_won": "true" if d["is_won"] else "false",
        "arr": d["arr"] if d["arr"] != 0 else "",
        "forecast_category": d["forecast_category"],
        "owner_name": owner_name,
    }


def generate_all(output_dir: Path) -> dict[str, str]:
    """Generate all CSV files deterministically. Returns {filename: content}."""
    random.seed(SEED)

    # --- Build deals ---
    all_deals = list(SAMPLE_DEALS)  # 9 anchor deals

    generated_deals, founder_owned_ids = _build_generated_deals(random)
    all_deals.extend(generated_deals)

    assert len(all_deals) == 25, f"Expected 25 deals, got {len(all_deals)}"

    # Identify stale S1→S2 anomaly deals (2 deals where stage_history shows 21+ days in S1).
    # "Stale" means the deal moved S1→S2 but without amount or close-date cleanup for 21+ days.
    # We pick open non-founder deals that have passed S1 (currently at S2 or beyond).
    # If <2 S2 non-founder deals, fall back to S3+ non-founder deals.
    open_non_founder_past_s1 = [
        d["id"] for d in all_deals
        if not d["is_closed"]
        and d["stage"] in ("S2", "S3", "S4", "S5")
        and d["owner"] not in FOUNDER_NAMES
    ]
    stale_s1s2_ids = open_non_founder_past_s1[:2]

    # Convert to engine-compatible CSV rows
    deals_csv_rows = [_to_csv_deal(d) for d in all_deals]

    # --- Build team members ---
    team_rows = _build_team_members()

    # --- Build stage history ---
    history_rows = _build_stage_history(all_deals, stale_s1s2_ids)
    history_rows.sort(key=lambda r: (r["deal_id"], r["transition_date"]))

    # --- Write CSVs ---
    output_dir = Path(output_dir)
    results: dict[str, str] = {}

    results["deals.csv"] = _write_csv(
        output_dir / "deals.csv", deals_csv_rows, DEALS_FIELDS
    )
    results["team_members.csv"] = _write_csv(
        output_dir / "team_members.csv", team_rows, TEAM_FIELDS
    )
    results["stage_history.csv"] = _write_csv(
        output_dir / "stage_history.csv", history_rows, HISTORY_FIELDS
    )

    return results


# ---------------------------------------------------------------------------
# Summary / verification helpers
# ---------------------------------------------------------------------------

def _print_summary(all_deals: list[dict]) -> None:
    open_deals = [d for d in all_deals if not d["is_closed"]]
    won_ytd = [
        d for d in all_deals
        if d["is_closed"] and d["is_won"]
        and YTD_START <= date.fromisoformat(d["close_date"]) <= YTD_END
    ]
    lost_ytd = [
        d for d in all_deals
        if d["is_closed"] and not d["is_won"]
        and YTD_START <= date.fromisoformat(d["close_date"]) <= YTD_END
    ]
    open_pipe = sum(d["amount"] for d in open_deals if d["amount"])
    won_arr = sum(d["arr"] for d in won_ytd)
    lost_arr = sum(d["arr"] for d in lost_ytd)
    founder_zero = [d for d in all_deals if d["owner"] in FOUNDER_NAMES and d["amount"] == 0]

    print(f"  Total deals: {len(all_deals)}")
    print(f"  Open deals: {len(open_deals)} (pipe ${open_pipe:,.0f})")
    print(f"  Closed-won YTD: {len(won_ytd)} (ARR ${won_arr:,.0f})")
    print(f"  Closed-lost YTD: {len(lost_ytd)} (ARR ${lost_arr:,.0f})")
    print(f"  Founder-owned $0 deals: {len(founder_zero)}")

    by_stage = {}
    for d in open_deals:
        by_stage[d["stage"]] = by_stage.get(d["stage"], 0) + 1
    print(f"  Open by stage: {dict(sorted(by_stage.items()))}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic Sprout Labs CSV data."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args(argv)

    print(f"Generating Sprout Labs data to {args.output_dir} ...")
    results = generate_all(args.output_dir)
    for filename, content in results.items():
        line_count = content.count("\n")
        print(f"  {filename}: {line_count} rows (including header)")

    # Print summary (re-seed to reconstruct deal list for reporting)
    random.seed(SEED)
    all_deals_check = list(SAMPLE_DEALS)
    generated, _ = _build_generated_deals(random)
    all_deals_check.extend(generated)
    _print_summary(all_deals_check)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

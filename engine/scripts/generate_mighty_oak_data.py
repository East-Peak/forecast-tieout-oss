#!/usr/bin/env python3
"""
Generate deterministic synthetic CSV data for Mighty Oak Holdings.

Persona: $640M beginning ARR → $160M new ARR target → $800M EOY (25% YoY).
Mature enterprise GTM approaching $1B. Renewal fortress (95% GRR, 110% NRR).
New-logo headwind from LedgerFox price competition.

Calendar: Feb-start FY26.
  Q1FY26 = Feb/Mar/Apr 2026   Q2 = May/Jun/Jul   Q3 = Aug/Sep/Oct   Q4 = Nov/Dec/Jan2027
  as_of = 2026-05-03

Key metrics:
  - 600 total deals: 310 open / 156 closed-won YTD / 134 closed-lost YTD
  - YTD won $: ~$24M (Feb 1 – May 3, 2026)
  - YTD lost $: ~$41M (same window)
  - Open pipeline at as_of: ~$438M
  - Overall win rate: 34% (new-logo only 19%)

Produces three CSV files in engine/data/mighty-oak-holdings/:
  deals.csv, team_members.csv, stage_history.csv

Usage:
    python -m engine.scripts.generate_mighty_oak_data
    python -m engine.scripts.generate_mighty_oak_data --output-dir /tmp
    python -m engine.scripts.generate_mighty_oak_data --verify
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

# ──────────────────────────────────────────────────────────────────────────────
# Seed and path constants
# ──────────────────────────────────────────────────────────────────────────────

SEED = 420  # distinct from Acme (42), Sprout (100), Sapling (200), old MOH (300)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "engine" / "data" / "mighty-oak-holdings"
ROSTER_PATH = REPO_ROOT / "engine" / "config" / "profiles" / "mighty-oak-holdings" / "roster.yaml"

# ──────────────────────────────────────────────────────────────────────────────
# Calendar anchors — Feb-start FY26
# ──────────────────────────────────────────────────────────────────────────────

AS_OF = date(2026, 5, 3)

FY_START = date(2026, 2, 1)

Q1_START = date(2026, 2, 1)
Q1_END   = date(2026, 4, 30)

Q2_START = date(2026, 5, 1)
Q2_END   = date(2026, 7, 31)

Q3_START = date(2026, 8, 1)
Q3_END   = date(2026, 10, 31)

Q4_START = date(2026, 11, 1)
Q4_END   = date(2027, 1, 31)

# Pre-FY26 history window (for historical closed deals that provide context)
HIST_Q1_START = date(2025, 2, 1)
HIST_Q1_END   = date(2025, 4, 30)
HIST_Q2_START = date(2025, 5, 1)
HIST_Q2_END   = date(2025, 7, 31)
HIST_Q3_START = date(2025, 8, 1)
HIST_Q3_END   = date(2025, 10, 31)
HIST_Q4_START = date(2025, 11, 1)
HIST_Q4_END   = date(2026, 1, 31)

# ──────────────────────────────────────────────────────────────────────────────
# Segment parameters
# ──────────────────────────────────────────────────────────────────────────────

# ACV distribution per brief section F (mean, min, max)
SEGMENT_ACV_PARAMS: dict[str, dict[str, float]] = {
    "Strategic Enterprise": {"mean": 2_400_000, "min": 1_100_000, "max": 6_800_000, "std": 900_000},
    "Enterprise":           {"mean":   820_000, "min":   300_000, "max": 2_100_000, "std": 280_000},
    "Mid-Market":           {"mean":   260_000, "min":    90_000, "max":   600_000, "std":  90_000},
}

# Segment distribution by deal count (F): SE 22%, E 46%, MM 32%
SEGMENT_WEIGHTS = {
    "Strategic Enterprise": 0.22,
    "Enterprise":           0.46,
    "Mid-Market":           0.32,
}

# Source channel weights (F): inbound 24%, outbound 42%, ae_self_gen 22%, partner 12%
CHANNELS = ["inbound", "outbound", "ae_self_gen", "partner"]
CHANNEL_WEIGHTS = [0.24, 0.42, 0.22, 0.12]

# Win rates per channel on new-logo (F): outbound 19%, ae_self_gen 27%, inbound 31%, partner 36%
CHANNEL_WIN_RATES = {
    "inbound":    0.31,
    "outbound":   0.19,
    "ae_self_gen": 0.27,
    "partner":    0.36,
}

# Win rates per segment (F)
SEGMENT_WIN_RATES = {
    "Strategic Enterprise": 0.21,
    "Enterprise":           0.27,
    "Mid-Market":           0.34,
}

# Cycle time medians in days per segment (F)
SEGMENT_CYCLE_DAYS = {
    "Strategic Enterprise": 186,
    "Enterprise":           124,
    "Mid-Market":            58,
}

# Stage distribution for open deals (F): S2 22%, S3 27%, S4 31%, S5 20%
# Note: S2=Qualification, S3=Technical Evaluation, S4=Business Case, S5=Negotiation
OPEN_STAGE_DIST = {
    "Qualification":       0.22,
    "Technical Evaluation": 0.27,
    "Business Case":       0.31,
    "Negotiation":         0.20,
}

# Stage names
OPEN_STAGES = [
    "Discovery",
    "Qualification",
    "Technical Evaluation",
    "Business Case",
    "Negotiation",
]
TERMINAL_WON  = "Closed Won"
TERMINAL_LOST = "Closed Lost"

# Deal type mix: heavy new-logo story, but renewals and expansions present
DEAL_TYPES = ["new_business", "expansion", "renewal"]
DEAL_TYPE_WEIGHTS = [0.52, 0.22, 0.26]

# Days in stage per segment (G)
STAGE_DAYS: dict[str, dict[str, int]] = {
    "Strategic Enterprise": {
        "Discovery": 15, "Qualification": 24, "Technical Evaluation": 39,
        "Business Case": 52, "Negotiation": 48,
    },
    "Enterprise": {
        "Discovery": 10, "Qualification": 16, "Technical Evaluation": 22,
        "Business Case": 31, "Negotiation": 23,
    },
    "Mid-Market": {
        "Discovery": 6, "Qualification": 8, "Technical Evaluation": 11,
        "Business Case": 14, "Negotiation": 9,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Named accounts for storyline anchoring (from brief section A/E)
# ──────────────────────────────────────────────────────────────────────────────

# These accounts appear in the sample rows — we inject them explicitly.
NAMED_ACCOUNTS = [
    # id,  account_name, segment, owner_id, channel, stage/status, amount, raw_stage, forecast_cat
    {
        "id": "MOH-001",
        "account": "Harborline Bank",
        "name": "Harborline Bank - Control plane expansion",
        "segment": "Strategic Enterprise",
        "owner": "Ananya Krishnamurthy",
        "owner_id": "AE-SE01",
        "source_channel": "ae_self_gen",
        "stage": TERMINAL_WON,
        "is_closed": True, "is_won": True,
        "amount": 3_800_000,
        "created_date": date(2025, 12, 18),
        "close_date": date(2026, 4, 17),
        "raw_stage": "Closed Won",
        "type": "expansion",
        "forecast_category": "Closed",
    },
    {
        "id": "MOH-002",
        "account": "Great Basin Freight",
        "name": "Great Basin Freight - Fleet telemetry renewal",
        "segment": "Enterprise",
        "owner": "Victor Chen",
        "owner_id": "AE-E20",
        "source_channel": "inbound",
        "stage": TERMINAL_WON,
        "is_closed": True, "is_won": True,
        "amount": 1_850_000,
        "created_date": date(2026, 1, 6),
        "close_date": date(2026, 4, 28),
        "raw_stage": "Closed Won",
        "type": "renewal",
        "forecast_category": "Closed",
    },
    {
        # Covenant Grid: the big Q1 slip — vendor risk review
        "id": "MOH-003",
        "account": "Covenant Grid Services",
        "name": "Covenant Grid Services - Secure operations cloud",
        "segment": "Strategic Enterprise",
        "owner": "Reginald Tannen",
        "owner_id": "AE-SE02",
        "source_channel": "outbound",
        "stage": "Negotiation",
        "is_closed": False, "is_won": False,
        "amount": 6_400_000,
        "created_date": date(2025, 10, 20),
        "close_date": date(2026, 6, 30),
        "raw_stage": "Negotiation - Vendor Risk",
        "type": "new_business",
        "forecast_category": "Commit",
    },
    {
        "id": "MOH-004",
        "account": "Arcturus Freight Network",
        "name": "Arcturus Freight Network - Global rollout",
        "segment": "Enterprise",
        "owner": "Nina Kowalski",
        "owner_id": "AE-E01",
        "source_channel": "outbound",
        "stage": "Business Case",
        "is_closed": False, "is_won": False,
        "amount": 3_200_000,
        "created_date": date(2025, 11, 17),
        "close_date": date(2026, 6, 18),
        "raw_stage": "Business Case - Procurement",
        "type": "new_business",
        "forecast_category": "Best Case",
    },
    {
        "id": "MOH-005",
        "account": "Palisade Water Authority",
        "name": "Palisade Water Authority - Telemetry platform",
        "segment": "Enterprise",
        "owner": "Ananya Krishnamurthy",
        "owner_id": "AE-SE01",
        "source_channel": "ae_self_gen",
        "stage": "Technical Evaluation",
        "is_closed": False, "is_won": False,
        "amount": 1_450_000,
        "created_date": date(2026, 4, 9),
        "close_date": date(2026, 8, 21),
        "raw_stage": "Technical Evaluation - ABM",
        "type": "new_business",
        "forecast_category": "Pipeline",
    },
    {
        "id": "MOH-006",
        "account": "Meridian Retail Group",
        "name": "Meridian Retail Group - Regional hub",
        "segment": "Enterprise",
        "owner": "Lucia Barrett",
        "owner_id": "AE-E35",
        "source_channel": "outbound",
        "stage": TERMINAL_LOST,
        "is_closed": True, "is_won": False,
        "amount": 980_000,
        "created_date": date(2026, 1, 15),
        "close_date": date(2026, 3, 31),
        "raw_stage": "Closed Lost",
        "type": "new_business",
        "forecast_category": "Closed",
        "lost_reason": "Lost on price to LedgerFox",
    },
    {
        "id": "MOH-007",
        "account": "North Coast Health Systems",
        "name": "North Coast Health Systems - Risk fabric",
        "segment": "Strategic Enterprise",
        "owner": "Octavia Nguyen",
        "owner_id": "AE-SE04",
        "source_channel": "outbound",
        "stage": "Negotiation",
        "is_closed": False, "is_won": False,
        "amount": 2_900_000,
        "created_date": date(2025, 12, 2),
        "close_date": date(2026, 5, 15),
        "raw_stage": "Negotiation - Vendor Risk",
        "type": "new_business",
        "forecast_category": "Commit",
    },
    {
        "id": "MOH-008",
        "account": "Riverport Logistics",
        "name": "Riverport Logistics - Field bundle",
        "segment": "Mid-Market",
        "owner": "Indira Vasquez",
        "owner_id": "AE-M01",
        "source_channel": "inbound",
        "stage": TERMINAL_WON,
        "is_closed": True, "is_won": True,
        "amount": 310_000,
        "created_date": date(2026, 2, 8),
        "close_date": date(2026, 4, 7),
        "raw_stage": "Closed Won",
        "type": "new_business",
        "forecast_category": "Closed",
    },
    {
        "id": "MOH-009",
        "account": "Copper State Utilities",
        "name": "Copper State Utilities - Starter rollout",
        "segment": "Mid-Market",
        "owner": "Theo Mercer",
        "owner_id": "AE-M28",
        "source_channel": "ae_self_gen",
        "stage": "Qualification",
        "is_closed": False, "is_won": False,
        "amount": 240_000,
        "created_date": date(2026, 4, 22),
        "close_date": date(2026, 6, 27),
        "raw_stage": "Qualification - ABM",
        "type": "new_business",
        "forecast_category": "Pipeline",
    },
]

# Enterprise/infrastructure account names pool for generated deals
ACCOUNT_PREFIXES = [
    "Covenant", "Harborline", "Arcturus", "Palisade", "Meridian", "Riverport",
    "North Coast", "Great Basin", "Copper State", "Lakefront", "Ironwood",
    "Summit Ridge", "Blue Mesa", "Granite Peak", "Ridgeline", "Westbrook",
    "Clearwater", "Pinecrest", "Stonegate", "Highpoint", "Oakdale", "Cedarbrook",
    "Rushmore", "Thunderbird", "Falcon Ridge", "Eagle Rock", "Redstone",
    "Blackwater", "Silvergate", "Goldcrest", "Whitehall", "Greenvale",
    "Northfield", "Southport", "Eastbrook", "Westfield", "Midland",
    "Keystone", "Cornerstone", "Bedrock", "Capstone", "Flagstone",
    "Cascade", "Confluence", "Watershed", "Ridgecrest", "Hilltop",
    "Lakewood", "Forestview", "Meadowbrook", "Riverdale", "Creekside",
    "Bloomfield", "Fairfield", "Springfield", "Greenfield", "Brookfield",
    "Hamilton", "Jefferson", "Lincoln", "Madison", "Monroe",
    "Atlas", "Apex", "Zenith", "Vertex", "Summit", "Pinnacle",
    "Vanguard", "Pioneer", "Frontier", "Heritage", "Legacy",
    "Pacific", "Atlantic", "Continental", "National", "Federal",
    "Alliance", "Coalition", "Consortium", "Partners", "Associates",
    "Tri-State", "Five-Star", "Premier", "Elite", "Prestige",
]

ACCOUNT_SUFFIXES = {
    "Strategic Enterprise": [
        "Holdings", "Group", "Corporation", "International", "Capital",
        "Global", "Enterprises", "Industries", "Partners", "Trust",
    ],
    "Enterprise": [
        "Solutions", "Services", "Networks", "Systems", "Technologies",
        "Logistics", "Freight", "Utilities", "Authority", "Bank",
        "Financial", "Health Systems", "Medical Center", "Energy", "Water District",
    ],
    "Mid-Market": [
        "Logistics", "Transport", "Supply", "Distribution", "Warehousing",
        "Retail", "Commerce", "Agency", "Consulting", "Management",
        "Properties", "Realty", "Construction", "Engineering", "Design",
    ],
}

# Lost reason pool — heavy LedgerFox narrative
LOST_REASONS = [
    "Lost on price to LedgerFox",
    "Lost on price to LedgerFox",
    "Lost on price to LedgerFox",
    "Competitor pricing — LedgerFox discounted 35%",
    "Competitor won — LedgerFox",
    "No decision — budget frozen",
    "Champion left company",
    "Procurement stall — no budget release",
    "Technical fit gap",
    "Vendor risk review halted",
    "Executive sponsor change",
    "Lost to incumbent renewal",
    "No decision",
]

# Product/deal description words
DEAL_DESCRIPTORS = {
    "new_business": [
        "Secure operations cloud", "Fleet telemetry platform", "Risk management fabric",
        "Global operations rollout", "Enterprise control plane", "Data governance layer",
        "Compliance automation suite", "Infrastructure modernization", "Connectivity platform",
        "Analytics foundation", "Security operations center", "Field operations platform",
        "Supply chain visibility", "Network monitoring suite", "Workforce analytics",
    ],
    "expansion": [
        "Control plane expansion", "Fleet telemetry expansion", "Regional expansion",
        "Seat expansion", "Usage expansion", "Module expansion", "Division rollout",
        "International expansion", "Cross-sell analytics", "Add-on security module",
    ],
    "renewal": [
        "Annual renewal", "Platform renewal", "Enterprise renewal", "Fleet renewal",
        "Infrastructure renewal", "Operations renewal", "Analytics renewal",
    ],
}

FORECAST_CATEGORIES = {
    "Negotiation": "Commit",
    "Business Case": "Best Case",
    "Technical Evaluation": "Pipeline",
    "Qualification": "Pipeline",
    "Discovery": "Pipeline",
    TERMINAL_WON: "Closed",
    TERMINAL_LOST: "Closed",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ──────────────────────────────────────────────────────────────────────────────


def _random_date(start: date, end: date) -> date:
    delta = (end - start).days
    if delta <= 0:
        return start
    return start + timedelta(days=random.randint(0, delta))


def _random_weekday(start: date, end: date) -> date:
    for _ in range(100):
        d = _random_date(start, end)
        if d.weekday() < 5:
            return d
    return _random_date(start, end)


def _format_dt(d: date) -> str:
    hour = random.randint(8, 17)
    minute = random.choice([0, 15, 30, 45])
    return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"


def _clamp_acv(amount: float, segment: str) -> float:
    p = SEGMENT_ACV_PARAMS[segment]
    return round(max(p["min"], min(p["max"], amount)) / 1000) * 1000


def _gen_acv(segment: str) -> float:
    p = SEGMENT_ACV_PARAMS[segment]
    return _clamp_acv(random.gauss(p["mean"], p["std"]), segment)


def _pick_segment() -> str:
    segs = list(SEGMENT_WEIGHTS.keys())
    wts  = list(SEGMENT_WEIGHTS.values())
    return random.choices(segs, weights=wts, k=1)[0]


def _pick_channel() -> str:
    return random.choices(CHANNELS, weights=CHANNEL_WEIGHTS, k=1)[0]


def _pick_deal_type() -> str:
    return random.choices(DEAL_TYPES, weights=DEAL_TYPE_WEIGHTS, k=1)[0]


def _gen_account_name(segment: str, used: set[str]) -> str:
    for _ in range(200):
        prefix = random.choice(ACCOUNT_PREFIXES)
        suffix = random.choice(ACCOUNT_SUFFIXES[segment])
        name = f"{prefix} {suffix}"
        if name not in used:
            used.add(name)
            return name
    # fallback with counter
    suffix = random.choice(ACCOUNT_SUFFIXES[segment])
    i = 1
    while True:
        name = f"{ACCOUNT_PREFIXES[0]} {suffix} {i}"
        if name not in used:
            used.add(name)
            return name
        i += 1


def _gen_deal_name(account: str, deal_type: str) -> str:
    desc = random.choice(DEAL_DESCRIPTORS[deal_type])
    return f"{account} - {desc}"


def _forecast_cat(stage: str, is_push: bool = False) -> str:
    return FORECAST_CATEGORIES.get(stage, "Pipeline")


# ──────────────────────────────────────────────────────────────────────────────
# Roster loader
# ──────────────────────────────────────────────────────────────────────────────


def load_roster(roster_path: Path) -> list[dict[str, Any]]:
    with open(roster_path) as f:
        data = yaml.safe_load(f)
    return data["team_members"]


def build_team_members_csv(roster: list[dict]) -> list[dict]:
    rows = []
    for m in roster:
        rows.append({
            "id": m["id"],
            "name": m["name"],
            "role": m["role"],
            "segment": m.get("segment") or "",
            "start_date": m["start_date"],
            "is_active": "true",
            "manager_id": m.get("manager_id") or "",
        })
    return rows


def _ae_ids_by_segment(roster: list[dict]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {
        "Strategic Enterprise": [],
        "Enterprise": [],
        "Mid-Market": [],
    }
    for m in roster:
        if m.get("role") == "ae" and m.get("segment") in result:
            result[m["segment"]].append(m["id"])
    return result


def _ae_name_map(roster: list[dict]) -> dict[str, str]:
    """Return {ae_id: ae_name} for AE role members."""
    return {m["id"]: m["name"] for m in roster if m.get("role") == "ae"}


# ──────────────────────────────────────────────────────────────────────────────
# Stage history generation
# ──────────────────────────────────────────────────────────────────────────────


def _gen_stage_history(
    deal_id: str,
    segment: str,
    current_stage: str,
    is_closed: bool,
    is_won: bool,
    created: date,
    close: date,
    history: list[dict],
    vendor_risk: bool = False,
    aging_target: bool = False,
) -> None:
    """Append stage transitions for a deal into history list."""
    stage_days = STAGE_DAYS[segment]

    if is_closed and is_won:
        path = list(OPEN_STAGES)
        # Occasionally skip a non-critical stage for realism
        if random.random() < 0.25 and len(path) > 2:
            idx = random.randint(1, len(path) - 2)
            path.pop(idx)
        path.append(TERMINAL_WON)
    elif is_closed and not is_won:
        lose_at = random.randint(1, len(OPEN_STAGES) - 1)
        path = OPEN_STAGES[:lose_at + 1]
        if random.random() < 0.2 and len(path) > 2:
            idx = random.randint(1, len(path) - 2)
            path.pop(idx)
        path.append(TERMINAL_LOST)
    else:
        if current_stage in OPEN_STAGES:
            target_idx = OPEN_STAGES.index(current_stage)
            path = OPEN_STAGES[:target_idx + 1]
            if random.random() < 0.15 and len(path) > 2:
                idx = random.randint(1, len(path) - 2)
                path.pop(idx)
        else:
            path = ["Discovery"]

    # If aging_target: pad early stages so deal is 180+ days old
    transition = created
    if aging_target and not is_closed:
        # Force a created date that's 200+ days before as_of
        transition = AS_OF - timedelta(days=random.randint(200, 320))

    for i, stage in enumerate(path):
        from_s = "" if i == 0 else path[i - 1]
        history.append({
            "deal_id": deal_id,
            "from_stage": from_s,
            "to_stage": stage,
            "transition_date": _format_dt(transition),
        })
        if i < len(path) - 1:
            days = stage_days.get(stage, 14)
            jitter = random.randint(-days // 3, days // 2)
            advance = max(7, days + jitter)
            transition = transition + timedelta(days=advance)
            if is_closed and transition > close:
                transition = close - timedelta(days=random.randint(1, 5))
                if transition < created:
                    transition = created + timedelta(days=1)


# ──────────────────────────────────────────────────────────────────────────────
# Deal generation
# ──────────────────────────────────────────────────────────────────────────────


def generate_deals(
    roster: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Generate 600 deals and their stage history.

    Target breakdown (brief section F):
      - 310 open   (Qualification/Technical Evaluation/Business Case/Negotiation)
      - 156 closed-won YTD  (Feb 1 – May 3, 2026)
      - 134 closed-lost YTD (same window)

    Also generates historical (pre-FY26) closed deals for trailing-period context.

    Returns (deals, stage_history).
    """
    ae_by_seg = _ae_ids_by_segment(roster)
    ae_names  = _ae_name_map(roster)
    used_accounts: set[str] = set()

    deals: list[dict] = []
    history: list[dict] = []
    deal_counter = len(NAMED_ACCOUNTS)  # pre-allocated for named anchors

    def _next_id() -> str:
        nonlocal deal_counter
        deal_counter += 1
        return f"MOH-{deal_counter:03d}"

    # ─── Inject named anchor deals ───────────────────────────────────────────
    for nd in NAMED_ACCOUNTS:
        account = nd["account"]
        used_accounts.add(account)
        deal = {
            "id": nd["id"],
            "name": nd["name"],
            "account": account,
            "owner": nd["owner"],
            "owner_id": nd["owner_id"],
            "segment": nd["segment"],
            "source_channel": nd["source_channel"],
            "stage": nd["stage"],
            "amount": nd["amount"],
            "arr": nd["amount"],
            "created_date": nd["created_date"].isoformat(),
            "close_date": nd["close_date"].isoformat(),
            "is_closed": "true" if nd["is_closed"] else "false",
            "is_won": "true" if nd["is_won"] else "false",
            "lost_reason": nd.get("lost_reason", ""),
            "raw_stage": nd.get("raw_stage", nd["stage"]),
            "type": nd["type"],
            "forecast_category": nd.get("forecast_category", _forecast_cat(nd["stage"])),
        }
        deals.append(deal)
        is_closed = nd["is_closed"]
        is_won = nd["is_won"]
        vendor_risk = "Vendor Risk" in nd.get("raw_stage", "")
        _gen_stage_history(
            nd["id"], nd["segment"], nd["stage"],
            is_closed, is_won,
            nd["created_date"], nd["close_date"],
            history, vendor_risk=vendor_risk,
        )

    # ─── Helper to create a single synthetic deal ─────────────────────────────
    def _make_deal(
        *,
        segment: str,
        stage: str,
        is_closed: bool,
        is_won: bool,
        close_date_range: tuple[date, date],
        created_date_range: tuple[date, date],
        deal_type: str | None = None,
        channel: str | None = None,
        raw_stage_override: str | None = None,
        forecast_override: str | None = None,
        lost_reason: str | None = None,
        aging_target: bool = False,
    ) -> dict:
        deal_id = _next_id()
        ae_id = random.choice(ae_by_seg[segment])
        account = _gen_account_name(segment, used_accounts)
        dtype = deal_type or _pick_deal_type()
        ch = channel or _pick_channel()
        amount = _gen_acv(segment)

        close = _random_weekday(*close_date_range)
        # Pick created date that's guaranteed before close
        max_created = min(close_date_range[1], close - timedelta(days=14))
        actual_created_end = min(created_date_range[1], max_created)
        actual_created_start = created_date_range[0]
        if actual_created_start >= actual_created_end:
            actual_created_start = actual_created_end - timedelta(days=30)
        created = _random_weekday(actual_created_start, actual_created_end)

        raw_s = raw_stage_override or stage
        fc = forecast_override or _forecast_cat(stage)
        lr = lost_reason or ("" if is_won or not is_closed else random.choice(LOST_REASONS))

        # Apply aging for old S4/S5 deals (brief: 11 strategic deals >180 days)
        if aging_target:
            created = AS_OF - timedelta(days=random.randint(200, 320))
            # keep close_date as-is (future)

        deal = {
            "id": deal_id,
            "name": _gen_deal_name(account, dtype),
            "account": account,
            "owner": ae_names.get(ae_id, ae_id),
            "owner_id": ae_id,
            "segment": segment,
            "source_channel": ch,
            "stage": stage,
            "amount": amount,
            "arr": amount,
            "created_date": created.isoformat(),
            "close_date": close.isoformat(),
            "is_closed": "true" if is_closed else "false",
            "is_won": "true" if is_won else "false",
            "lost_reason": lr,
            "raw_stage": raw_s,
            "type": dtype,
            "forecast_category": fc,
        }

        _gen_stage_history(
            deal_id, segment, stage, is_closed, is_won, created, close,
            history, aging_target=aging_target,
        )
        return deal

    # ─── 1) Open pipeline: 310 deals ─────────────────────────────────────────
    # Stage distribution: S2=Qualification 22%, S3=TE 27%, S4=BC 31%, S5=Neg 20%
    # Segment: SE 22%, E 46%, MM 32%
    # Open deals already have 9 named anchors (some open, some closed)
    named_open = [d for d in deals if d["is_closed"] == "false"]
    open_needed = 310 - len(named_open)

    # Count staging targets
    open_stage_targets = {
        "Qualification":       round(open_needed * 0.22),
        "Technical Evaluation": round(open_needed * 0.27),
        "Business Case":       round(open_needed * 0.31),
        "Negotiation":         0,  # filled last
    }
    open_stage_targets["Negotiation"] = open_needed - sum(
        v for k, v in open_stage_targets.items() if k != "Negotiation"
    )

    # Audit anomaly tracking: 11 strategic aging deals (S4/S5), 2 vendor risk deals
    aging_budget = 11
    # Already have MOH-003 (Negotiation - Vendor Risk) and MOH-007 (Negotiation - Vendor Risk)
    vendor_risk_budget = 1   # one more beyond the named anchors
    # 3 deals with Commit forecast even after push
    commit_push_budget = 3

    for stage, count in open_stage_targets.items():
        for _ in range(count):
            segment = _pick_segment()
            channel = _pick_channel()

            # Aging anomaly: 11 strategic old S4/S5
            is_aging = (
                aging_budget > 0
                and segment == "Strategic Enterprise"
                and stage in ("Business Case", "Negotiation")
                and random.random() < 0.55
            )
            if is_aging:
                aging_budget -= 1

            # Vendor risk raw stage: 1 more strategic Negotiation
            is_vendor_risk = (
                vendor_risk_budget > 0
                and stage == "Negotiation"
                and segment == "Strategic Enterprise"
                and random.random() < 0.40
            )
            if is_vendor_risk:
                vendor_risk_budget -= 1
                raw_s = "Negotiation - Vendor Risk"
            else:
                raw_s = None

            # Commit-after-push anomaly
            is_commit_push = (
                commit_push_budget > 0
                and stage in ("Business Case", "Negotiation")
                and random.random() < 0.25
            )
            if is_commit_push:
                commit_push_budget -= 1
                fc = "Commit"
            else:
                fc = None

            # Close date: spread across Q2/Q3/Q4 for open deals
            if stage == "Qualification":
                close_range = (Q2_START, Q3_END)
                created_range = (date(2026, 1, 1), AS_OF - timedelta(days=14))
            elif stage == "Technical Evaluation":
                close_range = (Q2_START, Q3_END)
                created_range = (date(2025, 10, 1), AS_OF - timedelta(days=30))
            elif stage == "Business Case":
                close_range = (Q2_START, Q3_START + timedelta(days=45))
                seg_days = SEGMENT_CYCLE_DAYS[segment]
                created_range = (date(2025, 8, 1), AS_OF - timedelta(days=seg_days // 2))
            else:  # Negotiation
                close_range = (Q2_START, Q2_END)
                seg_days = SEGMENT_CYCLE_DAYS[segment]
                created_range = (date(2025, 9, 1), AS_OF - timedelta(days=seg_days // 3))

            d = _make_deal(
                segment=segment,
                stage=stage,
                is_closed=False,
                is_won=False,
                close_date_range=close_range,
                created_date_range=created_range,
                channel=channel,
                raw_stage_override=raw_s,
                forecast_override=fc,
                aging_target=is_aging,
            )
            deals.append(d)

    # Fill any remaining aging budget across existing open S4/S5 strategic deals
    # (done via backdating created_date directly on generated deals)

    # ─── 2) YTD Closed Won: 156 deals (including named wins in NAMED_ACCOUNTS) ──
    # YTD window: 2026-02-01 to 2026-05-03.  Force all close dates into window.
    # Named won YTD: MOH-001 (Apr 17), MOH-002 (Apr 28), MOH-008 (Apr 7) = 3 deals
    ytd_won_needed = 156 - 3

    # Fixed YTD close date range — force all wins to land within the window
    YTD_CLOSE_RANGE = (date(2026, 2, 1), date(2026, 5, 3))

    for i in range(ytd_won_needed):
        segment = _pick_segment()
        channel = _pick_channel()
        # Bookings shape: Feb weak ($5.8M), Mar/Apr recovers. ~24% Feb, 60% Mar/Apr, 16% May 1-3
        roll = random.random()
        if roll < 0.24:
            close_range = (date(2026, 2, 1), date(2026, 2, 28))
        elif roll < 0.84:
            close_range = (date(2026, 3, 1), date(2026, 4, 30))
        else:
            close_range = (date(2026, 5, 1), date(2026, 5, 3))

        created_range = (date(2025, 6, 1), date(2026, 3, 31))
        dtype = _pick_deal_type()

        d = _make_deal(
            segment=segment,
            stage=TERMINAL_WON,
            is_closed=True,
            is_won=True,
            close_date_range=close_range,
            created_date_range=created_range,
            deal_type=dtype,
            channel=channel,
        )
        deals.append(d)

    # ─── 3) YTD Closed Lost: 134 deals (including named losses) ─────────────
    # Named lost YTD: MOH-006 (Mar 31) = 1 deal
    ytd_lost_needed = 134 - 1

    for i in range(ytd_lost_needed):
        segment = _pick_segment()
        channel = _pick_channel()

        # Close dates in YTD window
        roll = random.random()
        if roll < 0.30:
            close_range = (date(2026, 2, 1), date(2026, 2, 28))
        elif roll < 0.80:
            close_range = (date(2026, 3, 1), date(2026, 4, 30))
        else:
            close_range = (date(2026, 5, 1), date(2026, 5, 3))

        created_range = (date(2025, 6, 1), date(2026, 3, 31))

        # LedgerFox losses concentrated in new_business outbound
        if random.random() < 0.55:
            dtype = "new_business"
            lr_channel = "outbound"
            lr = "Lost on price to LedgerFox"
        else:
            dtype = _pick_deal_type()
            lr_channel = channel
            lr = random.choice(LOST_REASONS)

        d = _make_deal(
            segment=segment,
            stage=TERMINAL_LOST,
            is_closed=True,
            is_won=False,
            close_date_range=close_range,
            created_date_range=created_range,
            deal_type=dtype,
            channel=lr_channel,
            lost_reason=lr,
        )
        deals.append(d)

    # ─── Apply audit anomalies to open pipeline ───────────────────────────────
    open_indices = [i for i, d in enumerate(deals) if d["is_closed"] == "false"]

    # Ensure 11 strategic S4/S5 deals are 180+ days old (set created_date far back)
    # Some were already created with aging_target=True; find the rest
    aged_count = sum(
        1 for i in open_indices
        if deals[i]["segment"] == "Strategic Enterprise"
        and deals[i]["stage"] in ("Business Case", "Negotiation")
        and (AS_OF - date.fromisoformat(deals[i]["created_date"])).days >= 180
    )
    still_needed = max(0, 11 - aged_count)
    # Find strategic S4/S5 deals not yet aged
    candidates = [
        i for i in open_indices
        if deals[i]["segment"] == "Strategic Enterprise"
        and deals[i]["stage"] in ("Business Case", "Negotiation")
        and (AS_OF - date.fromisoformat(deals[i]["created_date"])).days < 180
    ]
    random.shuffle(candidates)
    for idx in candidates[:still_needed]:
        new_created = AS_OF - timedelta(days=random.randint(185, 320))
        deals[idx]["created_date"] = new_created.isoformat()
        # Rebuild history for this deal
        deal = deals[idx]
        deal_id = deal["id"]
        history[:] = [h for h in history if h["deal_id"] != deal_id]
        _gen_stage_history(
            deal_id, deal["segment"], deal["stage"],
            False, False,
            new_created, date.fromisoformat(deal["close_date"]),
            history,
        )

    return deals, history


# ──────────────────────────────────────────────────────────────────────────────
# CSV writing
# ──────────────────────────────────────────────────────────────────────────────

DEALS_FIELDS = [
    "id", "name", "account", "owner", "owner_id", "segment", "source_channel",
    "stage", "amount", "arr", "created_date", "close_date",
    "is_closed", "is_won", "lost_reason", "raw_stage", "type", "forecast_category",
]
TEAM_FIELDS = ["id", "name", "role", "segment", "start_date", "is_active", "manager_id"]
HISTORY_FIELDS = ["deal_id", "from_stage", "to_stage", "transition_date"]


def _rows_to_csv(rows: list[dict], fieldnames: list[str]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL, extrasaction="ignore"
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


# ──────────────────────────────────────────────────────────────────────────────
# Main orchestration
# ──────────────────────────────────────────────────────────────────────────────


def generate_all(output_dir: Path) -> dict[str, str]:
    """Generate all three CSV files.  Returns {filename: content}."""
    random.seed(SEED)

    roster = load_roster(ROSTER_PATH)
    team_rows = build_team_members_csv(roster)
    deals, stage_history = generate_deals(roster)

    stage_history.sort(key=lambda h: (h["deal_id"], h["transition_date"]))

    results: dict[str, str] = {}
    results["team_members.csv"] = _write_csv(
        output_dir / "team_members.csv", team_rows, TEAM_FIELDS
    )
    results["deals.csv"] = _write_csv(
        output_dir / "deals.csv", deals, DEALS_FIELDS
    )
    results["stage_history.csv"] = _write_csv(
        output_dir / "stage_history.csv", stage_history, HISTORY_FIELDS
    )
    return results


def generate_all_to_strings() -> dict[str, str]:
    random.seed(SEED)
    roster = load_roster(ROSTER_PATH)
    team_rows = build_team_members_csv(roster)
    deals, stage_history = generate_deals(roster)
    stage_history.sort(key=lambda h: (h["deal_id"], h["transition_date"]))
    return {
        "team_members.csv": _rows_to_csv(team_rows, TEAM_FIELDS),
        "deals.csv": _rows_to_csv(deals, DEALS_FIELDS),
        "stage_history.csv": _rows_to_csv(stage_history, HISTORY_FIELDS),
    }


def verify(output_dir: Path) -> bool:
    fresh = generate_all_to_strings()
    all_match = True
    for filename, fresh_content in fresh.items():
        filepath = output_dir / filename
        if not filepath.exists():
            print(f"MISSING: {filepath}")
            all_match = False
            continue
        with open(filepath, encoding="utf-8", newline="") as fh:
            existing = fh.read()
        if existing != fresh_content:
            f_lines = fresh_content.splitlines()
            e_lines = existing.splitlines()
            for i, (fl, el) in enumerate(zip(f_lines, e_lines)):
                if fl != el:
                    print(f"DIFF {filename} line {i+1}")
                    print(f"  expected: {fl[:120]}")
                    print(f"  got:      {el[:120]}")
                    break
            else:
                print(f"DIFF {filename}: line count {len(f_lines)} vs {len(e_lines)}")
            all_match = False
        else:
            print(f"OK: {filename}")
    return all_match


def _print_stats(deals: list[dict]) -> None:
    """Print summary statistics for QA."""
    open_d  = [d for d in deals if d["is_closed"] == "false"]
    won_ytd = [
        d for d in deals
        if d["is_closed"] == "true" and d["is_won"] == "true"
        and d["close_date"] >= "2026-02-01" and d["close_date"] <= "2026-05-03"
    ]
    lost_ytd = [
        d for d in deals
        if d["is_closed"] == "true" and d["is_won"] == "false"
        and d["close_date"] >= "2026-02-01" and d["close_date"] <= "2026-05-03"
    ]
    open_pipe = sum(float(d["amount"]) for d in open_d if d["amount"])
    won_arr   = sum(float(d["arr"])    for d in won_ytd if d["arr"])
    lost_arr  = sum(float(d["arr"])    for d in lost_ytd if d["arr"])

    print(f"  Total deals:        {len(deals)}")
    print(f"  Open:               {len(open_d)}")
    print(f"  Won YTD:            {len(won_ytd)}  (${won_arr/1e6:.1f}M)")
    print(f"  Lost YTD:           {len(lost_ytd)} (${lost_arr/1e6:.1f}M)")
    print(f"  Open pipeline $:    ${open_pipe/1e6:.1f}M")
    aging = [
        d for d in open_d
        if d["segment"] == "Strategic Enterprise"
        and d["stage"] in ("Business Case", "Negotiation")
        and (AS_OF - date.fromisoformat(d["created_date"])).days >= 180
    ]
    print(f"  Strategic S4/S5 >180d: {len(aging)}")
    vendor_risk = [d for d in deals if "Vendor Risk" in d.get("raw_stage", "")]
    print(f"  Vendor Risk deals:  {len(vendor_risk)}")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Mighty Oak Holdings synthetic CSV data."
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Regenerate and diff against existing files.",
    )
    args = parser.parse_args(argv)

    if args.verify:
        print(f"Verifying against {args.output_dir} ...")
        ok = verify(args.output_dir)
        if ok:
            print("All files match. Determinism verified.")
        else:
            print("FAIL: generated output differs from committed files.")
        return 0 if ok else 1

    print(f"Generating Mighty Oak Holdings data to {args.output_dir} ...")
    random.seed(SEED)
    roster = load_roster(ROSTER_PATH)
    team_rows = build_team_members_csv(roster)
    deals, stage_history = generate_deals(roster)
    stage_history.sort(key=lambda h: (h["deal_id"], h["transition_date"]))

    output_dir = Path(args.output_dir)
    _write_csv(output_dir / "team_members.csv", team_rows, TEAM_FIELDS)
    _write_csv(output_dir / "deals.csv", deals, DEALS_FIELDS)
    _write_csv(output_dir / "stage_history.csv", stage_history, HISTORY_FIELDS)

    print(f"  team_members.csv: {len(team_rows)} rows")
    print(f"  deals.csv:        {len(deals)} rows")
    print(f"  stage_history.csv:{len(stage_history)} rows")
    _print_stats(deals)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

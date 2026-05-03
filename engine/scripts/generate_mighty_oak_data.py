#!/usr/bin/env python3
"""
Generate deterministic example CSV data for the Mighty Oak Holdings demo org.

Mighty Oak Holdings profile narrative:
- $100M ARR target (Feb-start fiscal — same calendar as Acme)
- Capacity-constrained — strong pipeline but team is undersized
- Enterprise + Mid-Market mix (no Commercial)
- Larger deal sizes than Sprout, larger team than Sprout/Acme

Produces five CSV files in engine/data/mighty-oak-holdings/.

Usage:
    python -m engine.scripts.generate_mighty_oak_data                  # Generate to engine/data/mighty-oak-holdings/
    python -m engine.scripts.generate_mighty_oak_data --verify         # Regenerate and diff against existing
    python -m engine.scripts.generate_mighty_oak_data --output-dir /tmp  # Custom output directory
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "engine" / "data" / "mighty-oak-holdings"
ROSTER_PATH = REPO_ROOT / "engine" / "config" / "profiles" / "mighty-oak-holdings" / "roster.yaml"

SEED = 300  # Different from Sprout (100), Sapling (200), Acme (42)

# Stage pipeline (open stages only — Closed Won/Lost are terminal)
OPEN_STAGES = [
    "Discovery",
    "Qualification",
    "Technical Evaluation",
    "Business Case",
    "Negotiation",
]
TERMINAL_WON = "Closed Won"
TERMINAL_LOST = "Closed Lost"

# Segment deal size parameters (min, max, center, std_dev)
# Mighty Oak is $800M scale — Strategic Enterprise + Enterprise + Mid-Market.
SEGMENT_DEAL_PARAMS: dict[str, dict[str, float]] = {
    "Strategic Enterprise": {"min": 800_000, "max": 4_000_000, "center": 1_800_000, "std": 600_000},
    "Enterprise": {"min": 250_000, "max": 1_200_000, "center": 550_000, "std": 180_000},
    "Mid-Market": {"min": 80_000, "max": 350_000, "center": 180_000, "std": 60_000},
}

# Deal types — Mighty Oak's narrative is renewal compression, so renewals
# dominate the deal flow. Heavy renewal book.
DEAL_TYPES = ["New Business", "Expansion", "Renewal"]
DEAL_TYPE_WEIGHTS = [0.30, 0.25, 0.45]

# Lead sources
SOURCES = ["Inbound", "Outbound", "Partner", "Event", "PLG"]
SOURCE_WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]

# Company generation
INDUSTRIES = ["Technology", "Finance", "Healthcare", "Manufacturing", "Retail", "Media", "Education", "Energy"]

COMPANY_PREFIXES = [
    "Apex", "Zenith", "Cobalt", "Vertex", "Nimbus", "Forge", "Atlas", "Prism",
    "Helix", "Onyx", "Sable", "Quantum", "Cipher", "Lumen", "Vector", "Nexus",
    "Stratos", "Aether", "Crest", "Vanguard", "Pinnacle", "Ember", "Nova", "Orbit",
    "Ridge", "Beacon", "Pulse", "Summit", "Drake", "Titan", "Horizon", "Sterling",
    "Ironclad", "Basalt", "Radiant", "Sapphire", "Cedar", "Granite", "Crimson", "Azure",
    "Keystone", "Marble", "Falcon", "Phoenix", "Spectra", "Coral", "Flint", "Opal",
    "Tempest", "Cascade", "Verdant", "Indigo", "Sequoia", "Obsidian", "Mercury", "Solstice",
    "Borealis", "Catalyst", "Eclipse", "Pavilion", "Lattice", "Monolith", "Synapse", "Thrive",
    "Dynamo", "Aegis", "Axiom", "Nebula", "Compass", "Bedrock", "Sentry", "Paragon",
]

COMPANY_SUFFIXES = [
    "Systems", "Technologies", "Solutions", "Labs", "Corp", "Group", "Inc",
    "Industries", "Analytics", "Networks", "Dynamics", "Software", "Digital",
    "Platforms", "Ventures", "Global", "Partners", "Sciences", "Cloud", "Data",
]

FIRST_NAMES = [
    "James", "Emma", "Liam", "Sophia", "Noah", "Olivia", "Ethan", "Ava",
    "Mason", "Isabella", "Lucas", "Mia", "Logan", "Charlotte", "Alexander", "Amelia",
    "Jacob", "Harper", "Michael", "Evelyn", "Daniel", "Abigail", "Henry", "Emily",
    "Sebastian", "Ella", "Jack", "Elizabeth", "Owen", "Sofia", "Samuel", "Avery",
    "Ryan", "Chloe", "Nathan", "Victoria", "Andrew", "Madison", "Gabriel", "Luna",
    "Dylan", "Grace", "Joshua", "Scarlett", "Caleb", "Lily", "Matthew", "Aria",
    "Adrian", "Zoe", "Connor", "Penelope", "Isaac", "Layla", "Nolan", "Riley",
    "Thomas", "Nora", "Aaron", "Zoey", "Robert", "Hannah", "Benjamin", "Stella",
    "Patrick", "Audrey", "Kevin", "Savannah", "Trevor", "Brooklyn", "Gavin", "Leah",
    "Colin", "Natalie", "Scott", "Hazel", "Derek", "Violet", "Marcus", "Aurora",
]

LAST_NAMES = [
    "Thompson", "Rivera", "Campbell", "Mitchell", "Roberts", "Carter", "Phillips",
    "Evans", "Turner", "Torres", "Parker", "Collins", "Edwards", "Stewart", "Flores",
    "Morris", "Murphy", "Cook", "Rogers", "Morgan", "Peterson", "Cooper", "Reed",
    "Bailey", "Bell", "Gomez", "Kelly", "Howard", "Ward", "Cox", "Diaz",
    "Richardson", "Wood", "Watson", "Brooks", "Bennett", "Gray", "James", "Reyes",
    "Cruz", "Hughes", "Price", "Myers", "Long", "Foster", "Sanders", "Ross",
    "Sullivan", "Powell", "Russell", "Bryant", "Griffin", "Hayes", "Wallace", "West",
]

TITLES = [
    "VP Engineering", "CTO", "Director of IT", "Head of Infrastructure",
    "VP Operations", "Director of Engineering", "Head of Security",
    "Chief Information Officer", "SVP Technology", "Director of Platform",
    "Head of DevOps", "VP Product", "Director of Cloud Operations",
    "Chief Architect", "VP Technology", "Director of Data Engineering",
    "Head of SRE", "VP Cloud", "Director of Solutions", "Head of Analytics",
]

# Today anchor: 2026-04-06 (consistent with Acme for parity)
TODAY = date(2026, 4, 6)

# Fiscal year: Mighty Oak uses April-start fiscal (FY26 = Apr 1, 2026 - Mar 31, 2027)
# As of TODAY=2026-04-06, FY26 just started (Q1 in progress, only ~6 days in)
# Q1: Apr 1 - Jun 30, 2026
# Q2: Jul 1 - Sep 30, 2026
# Q3: Oct 1 - Dec 31, 2026
# Q4: Jan 1 - Mar 31, 2027
FY_Q1_START = date(2026, 4, 1)
FY_Q1_END = date(2026, 6, 30)
FY_Q2_START = date(2026, 7, 1)
FY_Q2_END = date(2026, 9, 30)
FY_Q3_START = date(2026, 10, 1)
FY_Q3_END = date(2026, 12, 31)
FY_Q4_START = date(2027, 1, 1)
FY_Q4_END = date(2027, 3, 31)

# Historical quarters (FY25 Q3 and Q4 — Oct 2025 through Mar 2026)
HIST_Q3_START = date(2025, 10, 1)
HIST_Q3_END = date(2025, 12, 31)
HIST_Q4_START = date(2026, 1, 1)
HIST_Q4_END = date(2026, 3, 31)

# Departed AE IDs for dirty data
DEPARTED_AE_IDS = ["AE-X01", "AE-X02"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _random_date(start: date, end: date) -> date:
    """Return a random date between start and end (inclusive)."""
    delta = (end - start).days
    if delta <= 0:
        return start
    return start + timedelta(days=random.randint(0, delta))


def _random_weekday_date(start: date, end: date) -> date:
    """Return a random weekday date between start and end."""
    for _ in range(100):
        d = _random_date(start, end)
        if d.weekday() < 5:
            return d
    return _random_date(start, end)


def _clamp_amount(amount: float, segment: str) -> float:
    """Clamp deal amount to segment range and round to nearest $1K."""
    params = SEGMENT_DEAL_PARAMS[segment]
    clamped = max(params["min"], min(params["max"], amount))
    return round(clamped / 1000) * 1000


def _generate_amount(segment: str) -> float:
    """Generate a segment-appropriate deal amount."""
    params = SEGMENT_DEAL_PARAMS[segment]
    raw = random.gauss(params["center"], params["std"])
    return _clamp_amount(raw, segment)


def _generate_deal_name(company_name: str, deal_type: str) -> str:
    """Generate a deal name from company and type."""
    product_lines = ["Platform", "Enterprise Suite", "Analytics", "Security Module",
                     "Data Pipeline", "API Gateway", "Monitoring", "Compliance"]
    product = random.choice(product_lines)
    if deal_type == "Expansion":
        return f"{company_name} - {product} Expansion"
    elif deal_type == "Renewal":
        return f"{company_name} - {product} Renewal"
    else:
        return f"{company_name} - {product}"


# ---------------------------------------------------------------------------
# Roster loader
# ---------------------------------------------------------------------------


def load_roster(roster_path: Path) -> list[dict[str, Any]]:
    """Load team members from roster.yaml."""
    with open(roster_path) as f:
        data = yaml.safe_load(f)
    return data["team_members"]


def roster_to_csv_rows(members: list[dict]) -> list[dict]:
    """Convert roster YAML entries to CSV-compatible dicts."""
    rows = []
    for m in members:
        rows.append({
            "id": m["id"],
            "name": m["name"],
            "role": m["role"] if m["role"] != "ae" else "AE",
            "segment": m.get("segment", ""),
            "start_date": m["start_date"],
            "is_active": "true",
            "manager_id": m.get("manager_id", ""),
        })
    return rows


# ---------------------------------------------------------------------------
# Company generation
# ---------------------------------------------------------------------------


def generate_companies(n: int = 150) -> list[dict]:
    """Generate n fictional companies with deterministic names."""
    companies = []
    used_names: set[str] = set()

    # Shuffle to get deterministic but varied combinations
    prefixes = list(COMPANY_PREFIXES)
    suffixes = list(COMPANY_SUFFIXES)

    for i in range(n):
        # Pick unique name
        for _ in range(100):
            prefix = random.choice(prefixes)
            suffix = random.choice(suffixes)
            name = f"{prefix} {suffix}"
            if name not in used_names:
                used_names.add(name)
                break

        # Mighty Oak: 3-tier. Strategic Enterprise / Enterprise / Mid-Market.
        # Companies skew larger.
        segment_roll = random.random()
        if segment_roll < 0.20:
            segment = "Strategic Enterprise"
            emp_count = random.randint(15000, 200000)
        elif segment_roll < 0.55:
            segment = "Enterprise"
            emp_count = random.randint(2000, 15000)
        else:
            segment = "Mid-Market"
            emp_count = random.randint(200, 2000)

        companies.append({
            "id": f"COMP-{i + 1:03d}",
            "name": name,
            "segment": segment,
            "industry": random.choice(INDUSTRIES),
            "employee_count": emp_count,
        })

    return companies


# ---------------------------------------------------------------------------
# Contact generation
# ---------------------------------------------------------------------------


def generate_contacts(companies: list[dict], n: int = 200) -> list[dict]:
    """Generate n fictional contacts distributed across companies."""
    contacts = []
    used_emails: set[str] = set()

    for i in range(n):
        company = random.choice(companies)
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"

        # Generate unique email
        domain = company["name"].lower().replace(" ", "").replace(".", "") + ".com"
        base_email = f"{first.lower()}.{last.lower()}@{domain}"
        email = base_email
        counter = 2
        while email in used_emails:
            email = f"{first.lower()}.{last.lower()}{counter}@{domain}"
            counter += 1
        used_emails.add(email)

        contacts.append({
            "id": f"CT-{i + 1:03d}",
            "name": name,
            "email": email,
            "company_id": company["id"],
            "title": random.choice(TITLES),
        })

    return contacts


# ---------------------------------------------------------------------------
# Deal generation
# ---------------------------------------------------------------------------


def _get_ae_ids_by_segment(roster: list[dict]) -> dict[str, list[str]]:
    """Group active AE IDs by segment."""
    # Mighty Oak: 3-tier (Strategic Enterprise / Enterprise / Mid-Market).
    result: dict[str, list[str]] = {
        "Strategic Enterprise": [],
        "Enterprise": [],
        "Mid-Market": [],
    }
    for m in roster:
        if m.get("role") == "ae" and m.get("segment") in result:
            result[m["segment"]].append(m["id"])
    return result


def generate_deals(
    roster: list[dict],
    companies: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Generate ~400 deals and their stage history.

    Returns (deals, stage_history) where each is a list of dicts.
    """
    ae_by_segment = _get_ae_ids_by_segment(roster)
    companies_by_segment: dict[str, list[dict]] = {
        "Strategic Enterprise": [],
        "Enterprise": [],
        "Mid-Market": [],
    }
    for c in companies:
        if c["segment"] in companies_by_segment:
            companies_by_segment[c["segment"]].append(c)

    deals: list[dict] = []
    history: list[dict] = []
    deal_counter = 0

    # Track which deals get dirty data treatment
    dirty_missing_amount_indices: list[int] = []
    dirty_missing_close_date_indices: list[int] = []
    dirty_departed_owner_indices: list[int] = []
    dirty_pusher_indices: list[int] = []
    dirty_stale_indices: list[int] = []
    dirty_zero_amount_cw_index: int | None = None
    dirty_past_close_bc_index: int | None = None

    # -----------------------------------------------------------------------
    # Helper to create one deal + its stage history
    # -----------------------------------------------------------------------
    def _make_deal(
        target_stage: str,
        is_closed: bool,
        is_won: bool,
        segment: str,
        close_date_range: tuple[date, date],
        created_date_range: tuple[date, date],
    ) -> dict:
        nonlocal deal_counter
        deal_counter += 1
        deal_id = f"D-{deal_counter:03d}"

        # Pick AE and company
        ae_id = random.choice(ae_by_segment[segment])
        company = random.choice(companies_by_segment[segment])

        # Deal type and source
        deal_type = random.choices(DEAL_TYPES, weights=DEAL_TYPE_WEIGHTS, k=1)[0]
        source = random.choices(SOURCES, weights=SOURCE_WEIGHTS, k=1)[0]

        # Amount
        amount = _generate_amount(segment)

        # Dates
        created = _random_weekday_date(*created_date_range)
        if is_closed:
            close = _random_weekday_date(*close_date_range)
            # Ensure close_date is after created_date
            if close <= created:
                close = created + timedelta(days=random.randint(30, 90))
        else:
            close = _random_weekday_date(*close_date_range)
            if close <= created:
                close = created + timedelta(days=random.randint(45, 120))

        deal_name = _generate_deal_name(company["name"], deal_type)

        deal = {
            "id": deal_id,
            "name": deal_name,
            "amount": amount,
            "stage": target_stage,
            "close_date": close.isoformat(),
            "owner_id": ae_id,
            "type": deal_type,
            "created_date": created.isoformat(),
            "segment": segment,
            "source": source,
            "is_closed": "true" if is_closed else "false",
            "is_won": "true" if is_won else "false",
        }

        # Generate stage history
        _generate_stage_history(deal_id, target_stage, is_closed, is_won, created, close, history)

        return deal

    # Mighty Oak segment helper: 20% Strategic, 40% Enterprise, 40% Mid-Market.
    def _pick_segment() -> str:
        roll = random.random()
        if roll < 0.20:
            return "Strategic Enterprise"
        elif roll < 0.60:
            return "Enterprise"
        return "Mid-Market"

    # -----------------------------------------------------------------------
    # 1) Open deals (~180) distributed across stages — bigger team than
    # Sprout, capacity-constrained narrative means lots of pipeline.
    # -----------------------------------------------------------------------
    open_stage_distribution = {
        "Discovery": 38,
        "Qualification": 32,
        "Technical Evaluation": 42,
        "Business Case": 32,
        "Negotiation": 22,
        "Closed Won": 14,  # Recent wins this quarter
    }

    for stage, count in open_stage_distribution.items():
        is_won = stage == "Closed Won"
        is_closed = is_won
        for _ in range(count):
            segment = _pick_segment()
            if is_won:
                # Recent wins: closed this quarter (Q1 in progress as of TODAY)
                close_range = (FY_Q1_START, TODAY)
                created_range = (HIST_Q4_START, FY_Q1_START + timedelta(days=30))
            else:
                # Open deals: close dates spread across Q1 and Q2
                close_range = (TODAY - timedelta(days=10), FY_Q2_END)
                created_range = (HIST_Q4_START, TODAY - timedelta(days=7))
            deal = _make_deal(stage, is_closed, is_won, segment, close_range, created_range)
            deals.append(deal)

    # -----------------------------------------------------------------------
    # 2) Historical (FY25) Closed Won (~70) over Q3 + Q4
    # -----------------------------------------------------------------------
    for _ in range(70):
        segment = _pick_segment()
        if random.random() < 0.45:
            close_range = (HIST_Q3_START, HIST_Q3_END)
            created_range = (HIST_Q3_START - timedelta(days=120), HIST_Q3_END - timedelta(days=30))
        else:
            close_range = (HIST_Q4_START, HIST_Q4_END)
            created_range = (HIST_Q4_START - timedelta(days=120), HIST_Q4_END - timedelta(days=30))
        deal = _make_deal(TERMINAL_WON, True, True, segment, close_range, created_range)
        deals.append(deal)

    # -----------------------------------------------------------------------
    # 3) Historical Closed Lost (~110) over past 2 quarters
    # -----------------------------------------------------------------------
    for _ in range(110):
        segment = _pick_segment()
        if random.random() < 0.45:
            close_range = (HIST_Q3_START, HIST_Q3_END)
            created_range = (HIST_Q3_START - timedelta(days=120), HIST_Q3_END - timedelta(days=30))
        else:
            close_range = (HIST_Q4_START, HIST_Q4_END)
            created_range = (HIST_Q4_START - timedelta(days=120), HIST_Q4_END - timedelta(days=30))
        deal = _make_deal(TERMINAL_LOST, True, False, segment, close_range, created_range)
        deals.append(deal)

    # -----------------------------------------------------------------------
    # 4) Apply dirty data mutations
    # -----------------------------------------------------------------------
    open_deal_indices = [i for i, d in enumerate(deals) if d["is_closed"] == "false"]
    all_indices = list(range(len(deals)))

    # 5-8 deals with missing Amount
    missing_amount_count = random.randint(5, 8)
    dirty_missing_amount_indices = random.sample(open_deal_indices, min(missing_amount_count, len(open_deal_indices)))
    for idx in dirty_missing_amount_indices:
        deals[idx]["amount"] = ""

    # 3 deals with missing CloseDate
    available_for_missing_close = [i for i in open_deal_indices if i not in dirty_missing_amount_indices]
    dirty_missing_close_date_indices = random.sample(available_for_missing_close, min(3, len(available_for_missing_close)))
    for idx in dirty_missing_close_date_indices:
        deals[idx]["close_date"] = ""

    # 2-3 deals with departed AE owners
    departed_count = random.randint(2, 3)
    available_for_departed = [
        i for i in open_deal_indices
        if i not in dirty_missing_amount_indices and i not in dirty_missing_close_date_indices
    ]
    dirty_departed_owner_indices = random.sample(available_for_departed, min(departed_count, len(available_for_departed)))
    for j, idx in enumerate(dirty_departed_owner_indices):
        deals[idx]["owner_id"] = DEPARTED_AE_IDS[j % len(DEPARTED_AE_IDS)]

    # ~10 deals that pushed CloseDate 2-3 times
    available_for_push = [
        i for i in open_deal_indices
        if i not in dirty_missing_amount_indices
        and i not in dirty_missing_close_date_indices
        and i not in dirty_departed_owner_indices
    ]
    dirty_pusher_indices = random.sample(available_for_push, min(10, len(available_for_push)))
    for idx in dirty_pusher_indices:
        deal = deals[idx]
        push_count = random.randint(2, 3)
        current_close = date.fromisoformat(deal["close_date"])
        created = date.fromisoformat(deal["created_date"])

        # Generate pushes — each push moves close date out by 2-6 weeks
        push_date = created + timedelta(days=random.randint(20, 40))
        for p in range(push_count):
            old_close = current_close - timedelta(days=random.randint(14, 42) * (push_count - p))
            history.append({
                "deal_id": deal["id"],
                "from_stage": deal["stage"],
                "to_stage": deal["stage"],
                "transition_date": _format_datetime(push_date),
                "_is_push": True,
                "_old_close": old_close.isoformat(),
                "_new_close": deal["close_date"],
            })
            push_date += timedelta(days=random.randint(14, 30))

    # Several deals at Technical Evaluation sitting 200+ days with no movement
    te_deals = [
        i for i in open_deal_indices
        if deals[i]["stage"] == "Technical Evaluation"
        and i not in dirty_missing_amount_indices
        and i not in dirty_missing_close_date_indices
        and i not in dirty_departed_owner_indices
        and i not in dirty_pusher_indices
    ]
    stale_count = min(5, len(te_deals))
    dirty_stale_indices = random.sample(te_deals, stale_count)
    for idx in dirty_stale_indices:
        # Push created_date way back so time-in-stage > 200 days
        old_created = TODAY - timedelta(days=random.randint(210, 300))
        deals[idx]["created_date"] = old_created.isoformat()
        # Rewrite stage history: entered Tech Eval early, no movement since
        deal_id = deals[idx]["id"]
        # Remove existing history for this deal and regenerate
        history[:] = [h for h in history if h["deal_id"] != deal_id]
        enter_discovery = old_created
        enter_qual = enter_discovery + timedelta(days=random.randint(7, 14))
        enter_te = enter_qual + timedelta(days=random.randint(7, 14))
        history.extend([
            {"deal_id": deal_id, "from_stage": "", "to_stage": "Discovery",
             "transition_date": _format_datetime(enter_discovery)},
            {"deal_id": deal_id, "from_stage": "Discovery", "to_stage": "Qualification",
             "transition_date": _format_datetime(enter_qual)},
            {"deal_id": deal_id, "from_stage": "Qualification", "to_stage": "Technical Evaluation",
             "transition_date": _format_datetime(enter_te)},
        ])

    # 1 Closed Won deal with $0 Amount
    cw_deals = [i for i, d in enumerate(deals) if d["stage"] == TERMINAL_WON and d["is_closed"] == "true"]
    if cw_deals:
        dirty_zero_amount_cw_index = random.choice(cw_deals)
        deals[dirty_zero_amount_cw_index]["amount"] = 0

    # 1 deal in Business Case with CloseDate in the past
    bc_deals = [
        i for i in open_deal_indices
        if deals[i]["stage"] == "Business Case"
        and i not in dirty_missing_amount_indices
        and i not in dirty_missing_close_date_indices
        and i not in dirty_departed_owner_indices
    ]
    if bc_deals:
        dirty_past_close_bc_index = random.choice(bc_deals)
        past_date = TODAY - timedelta(days=random.randint(20, 45))
        deals[dirty_past_close_bc_index]["close_date"] = past_date.isoformat()

    return deals, history


def _format_datetime(d: date) -> str:
    """Format a date as an ISO datetime string with a plausible time."""
    hour = random.randint(8, 17)
    minute = random.choice([0, 15, 30, 45])
    return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"


def _generate_stage_history(
    deal_id: str,
    current_stage: str,
    is_closed: bool,
    is_won: bool,
    created: date,
    close_date: date,
    history: list[dict],
) -> None:
    """Generate realistic stage progression history for a deal."""
    # Determine the progression path
    if is_closed and is_won:
        # Closed Won: went through stages up to Negotiation, then Closed Won
        # Sometimes skip a stage
        stages_to_traverse = list(OPEN_STAGES)
        # Randomly skip 0-1 stages (but not Discovery — always start there)
        if random.random() < 0.3 and len(stages_to_traverse) > 2:
            skip_idx = random.randint(1, len(stages_to_traverse) - 2)
            stages_to_traverse.pop(skip_idx)
        stages_to_traverse.append(TERMINAL_WON)
    elif is_closed and not is_won:
        # Closed Lost: went through some stages then lost
        # Pick a random stage to lose at
        lose_at = random.randint(1, len(OPEN_STAGES) - 1)
        stages_to_traverse = OPEN_STAGES[:lose_at + 1]
        # Sometimes skip a stage
        if random.random() < 0.2 and len(stages_to_traverse) > 2:
            skip_idx = random.randint(1, len(stages_to_traverse) - 2)
            stages_to_traverse.pop(skip_idx)
        stages_to_traverse.append(TERMINAL_LOST)
    else:
        # Open deal: went through stages up to current_stage
        if current_stage in OPEN_STAGES:
            target_idx = OPEN_STAGES.index(current_stage)
            stages_to_traverse = OPEN_STAGES[:target_idx + 1]
            # Sometimes skip a stage (but not if only 1-2 stages)
            if random.random() < 0.15 and len(stages_to_traverse) > 2:
                skip_idx = random.randint(1, len(stages_to_traverse) - 2)
                stages_to_traverse.pop(skip_idx)
        elif current_stage == TERMINAL_WON:
            # Recent wins
            stages_to_traverse = list(OPEN_STAGES)
            if random.random() < 0.3 and len(stages_to_traverse) > 2:
                skip_idx = random.randint(1, len(stages_to_traverse) - 2)
                stages_to_traverse.pop(skip_idx)
            stages_to_traverse.append(TERMINAL_WON)
        else:
            stages_to_traverse = ["Discovery"]

    # Generate transition dates
    transition_date = created
    for i, stage in enumerate(stages_to_traverse):
        from_stage = "" if i == 0 else stages_to_traverse[i - 1]

        history.append({
            "deal_id": deal_id,
            "from_stage": from_stage,
            "to_stage": stage,
            "transition_date": _format_datetime(transition_date),
        })

        # Next transition 15-45 days later
        if i < len(stages_to_traverse) - 1:
            transition_date += timedelta(days=random.randint(15, 45))
            # Don't go past close_date for closed deals
            if is_closed and transition_date > close_date:
                transition_date = close_date - timedelta(days=random.randint(1, 5))
                if transition_date < created:
                    transition_date = created + timedelta(days=1)


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------


def _rows_to_csv_string(rows: list[dict], fieldnames: list[str]) -> str:
    """Serialize rows to a CSV string with Unix line endings."""
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    # csv module writes \r\n; normalize to \n for cross-platform determinism
    return buf.getvalue().replace("\r\n", "\n")


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> str:
    """Write rows to CSV and return the content string."""
    content = _rows_to_csv_string(rows, fieldnames)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return content


# ---------------------------------------------------------------------------
# Main generation orchestrator
# ---------------------------------------------------------------------------


def generate_all(output_dir: Path) -> dict[str, str]:
    """Generate all CSV files and return {filename: content} for verification.

    Reseeds random at the start for determinism.
    """
    random.seed(SEED)

    # 1) Load roster
    roster = load_roster(ROSTER_PATH)
    team_rows = roster_to_csv_rows(roster)

    # 2) Generate companies
    companies = generate_companies(150)

    # 3) Generate contacts
    contacts = generate_contacts(companies, 200)

    # 4) Generate deals and stage history
    deals, stage_history = generate_deals(roster, companies)

    # Sort stage history by deal_id then transition_date for readability
    stage_history.sort(key=lambda h: (h["deal_id"], h["transition_date"]))

    # 5) Write all CSVs
    output_dir = Path(output_dir)
    results: dict[str, str] = {}

    results["team_members.csv"] = _write_csv(
        output_dir / "team_members.csv",
        team_rows,
        ["id", "name", "role", "segment", "start_date", "is_active", "manager_id"],
    )

    results["companies.csv"] = _write_csv(
        output_dir / "companies.csv",
        companies,
        ["id", "name", "segment", "industry", "employee_count"],
    )

    results["contacts.csv"] = _write_csv(
        output_dir / "contacts.csv",
        contacts,
        ["id", "name", "email", "company_id", "title"],
    )

    results["deals.csv"] = _write_csv(
        output_dir / "deals.csv",
        deals,
        ["id", "name", "amount", "stage", "close_date", "owner_id", "type", "created_date", "segment", "source", "is_closed", "is_won"],
    )

    results["stage_history.csv"] = _write_csv(
        output_dir / "stage_history.csv",
        stage_history,
        ["deal_id", "from_stage", "to_stage", "transition_date"],
    )

    return results


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(output_dir: Path) -> bool:
    """Regenerate data and compare against committed files.

    Returns True if all files match, False otherwise.
    """
    # Generate fresh content
    fresh = generate_all_to_strings()

    output_dir = Path(output_dir)
    all_match = True

    for filename, fresh_content in fresh.items():
        filepath = output_dir / filename
        if not filepath.exists():
            print(f"MISSING: {filepath}")
            all_match = False
            continue

        with open(filepath, encoding="utf-8", newline="") as fh:
            existing_content = fh.read()
        if existing_content != fresh_content:
            # Find first difference
            fresh_lines = fresh_content.splitlines()
            existing_lines = existing_content.splitlines()
            for i, (fl, el) in enumerate(zip(fresh_lines, existing_lines)):
                if fl != el:
                    print(f"DIFF: {filename} line {i + 1}")
                    print(f"  expected: {fl[:120]}")
                    print(f"  got:      {el[:120]}")
                    break
            else:
                if len(fresh_lines) != len(existing_lines):
                    print(f"DIFF: {filename} line count differs ({len(fresh_lines)} vs {len(existing_lines)})")
            all_match = False
        else:
            print(f"OK: {filename}")

    return all_match


def generate_all_to_strings() -> dict[str, str]:
    """Generate all CSV content as strings without writing to disk."""
    random.seed(SEED)

    roster = load_roster(ROSTER_PATH)
    team_rows = roster_to_csv_rows(roster)
    companies = generate_companies(150)
    contacts = generate_contacts(companies, 200)
    deals, stage_history = generate_deals(roster, companies)
    stage_history.sort(key=lambda h: (h["deal_id"], h["transition_date"]))

    results: dict[str, str] = {}

    results["team_members.csv"] = _rows_to_csv_string(
        team_rows,
        ["id", "name", "role", "segment", "start_date", "is_active", "manager_id"],
    )
    results["companies.csv"] = _rows_to_csv_string(
        companies,
        ["id", "name", "segment", "industry", "employee_count"],
    )
    results["contacts.csv"] = _rows_to_csv_string(
        contacts,
        ["id", "name", "email", "company_id", "title"],
    )
    results["deals.csv"] = _rows_to_csv_string(
        deals,
        ["id", "name", "amount", "stage", "close_date", "owner_id", "type", "created_date", "segment", "source", "is_closed", "is_won"],
    )
    results["stage_history.csv"] = _rows_to_csv_string(
        stage_history,
        ["deal_id", "from_stage", "to_stage", "transition_date"],
    )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic example CSV data for the Mighty Oak Holdings demo org.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Regenerate and diff against existing files (exit 1 if different).",
    )

    args = parser.parse_args(argv)

    if args.verify:
        print(f"Verifying deterministic output against {args.output_dir} ...")
        if verify(args.output_dir):
            print("All files match. Determinism verified.")
            return 0
        else:
            print("FAIL: Generated output differs from committed files.")
            return 1
    else:
        print(f"Generating Mighty Oak Holdings data to {args.output_dir} ...")
        results = generate_all(args.output_dir)
        for filename, content in results.items():
            line_count = content.count("\n")
            print(f"  {filename}: {line_count} rows (including header)")
        print("Done.")
        return 0


if __name__ == "__main__":
    sys.exit(main())

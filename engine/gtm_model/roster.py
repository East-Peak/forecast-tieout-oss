"""
Roster module for GTM capacity planning.

Merges Salesforce active headcount (the floor) with a YAML file that augments
with incoming/planned hires and critical start_date metadata that SF doesn't track.

The core contract:
  - SF headcount is the FLOOR — we can never undercount real people.
  - YAML augments: adds start_date for ramp calculation, and incoming/planned hires.
  - start_date in YAML is stored as a string "YYYY-MM-DD"; parsed to date internally
    for all calculations.
  - SF-only entries (no YAML match) get a default start_date 12+ months ago → fully ramped.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from dateutil.relativedelta import relativedelta

from gtm_model.tieout.runtime.env import get_default_config_dir, load_yaml_resource


# =============================================================================
# Ramp Curve Definitions
# =============================================================================

# Key: month number since start (1-indexed). After max key → fully ramped.
ENTERPRISE_RAMP: dict[int, float] = {
    1: 0.00,
    2: 0.10,
    3: 0.30,
    4: 0.50,
    5: 0.75,
    6: 1.00,
}

COMMERCIAL_RAMP: dict[int, float] = {
    1: 0.00,
    2: 0.15,
    3: 0.50,
    4: 1.00,
}

GENERIC_RAMP: dict[int, float] = {
    1: 0.00,
    2: 0.15,
    3: 0.50,
    4: 1.00,
}

# Ramp curves keyed by segment string (lowercase)
SEGMENT_RAMP_CURVES: dict[str, dict[int, float]] = {
    "enterprise": ENTERPRISE_RAMP,
    "commercial": COMMERCIAL_RAMP,
    "mid_market": COMMERCIAL_RAMP,
}

# Default annual quotas by segment
SEGMENT_QUOTAS: dict[str, float] = {
    "enterprise": 1_400_000,
    "commercial": 650_000,
    "mid_market": 650_000,
}

# Default attainment rates by segment
SEGMENT_ATTAINMENT: dict[str, float] = {
    "enterprise": 1.0,
    "commercial": 0.80,
    "mid_market": 0.80,
}

# How many months ago to set as "default" start_date for SF-only entries (fully ramped)
_RAMPED_DEFAULT_MONTHS_AGO = 18
_SEGMENT_ALIASES: dict[str, str] = {
    "enterprise": "enterprise",
    "commercial": "commercial",
    "midmarket": "commercial",
    "mid_market": "commercial",
    "mid-market": "commercial",
}


# =============================================================================
# Helpers
# =============================================================================

def _ensure_str_date(value) -> str:
    """Return a YYYY-MM-DD string regardless of whether value is str or date."""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _parse_date(value) -> date:
    """Parse YYYY-MM-DD string or date object → date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _default_ramped_start() -> str:
    """Return a start_date string far enough in the past that the rep is fully ramped."""
    past = date.today() - relativedelta(months=_RAMPED_DEFAULT_MONTHS_AGO)
    return past.isoformat()


def _normalize_key(value) -> str:
    """Normalize identifiers like names/user_ids for matching."""
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _normalize_segment(segment) -> str:
    """Collapse segment aliases to the keys used by assumptions.yaml."""
    normalized = str(segment or "enterprise").strip().lower().replace(" ", "_")
    return _SEGMENT_ALIASES.get(normalized, normalized)


def _parse_ramp_curve(raw_curve: dict | None) -> dict[int, float]:
    """Convert YAML ramp-curve keys like month_4_plus into numeric buckets."""
    if not raw_curve:
        return {}

    parsed: dict[int, float] = {}
    for key, value in raw_curve.items():
        if not str(key).startswith("month_"):
            continue
        suffix = str(key)[6:]
        month_num = None
        if suffix.isdigit():
            month_num = int(suffix)
        elif suffix.endswith("_plus") and suffix[:-5].isdigit():
            month_num = int(suffix[:-5])
        if month_num is not None:
            parsed[month_num] = float(value)
    return parsed


@lru_cache(maxsize=1)
def _load_assumptions() -> dict:
    """Load assumptions.yaml once so roster math can follow config defaults."""
    return load_yaml_resource("assumptions.yaml", config_dir=get_default_config_dir())


def _get_ramp_curve(segment: str) -> dict[int, float]:
    """Return the configured ramp curve for a segment with sensible fallbacks."""
    normalized = _normalize_segment(segment)
    assumptions = _load_assumptions()
    segment_curve = _parse_ramp_curve(
        assumptions.get("segment_productivity", {}).get(normalized, {}).get("ramp_curve")
    )
    if segment_curve:
        return segment_curve

    generic_curve = _parse_ramp_curve(assumptions.get("capacity", {}).get("ramp_curve"))
    if generic_curve:
        return generic_curve

    return SEGMENT_RAMP_CURVES.get(normalized, GENERIC_RAMP)


def _get_segment_quota(segment: str) -> float:
    """Return annual quota default for a segment."""
    normalized = _normalize_segment(segment)
    assumptions = _load_assumptions()

    segment_quota = assumptions.get("segment_productivity", {}).get(normalized, {}).get("annual_quota")
    if segment_quota is not None:
        return float(segment_quota)

    quotas_cfg = assumptions.get("capacity", {}).get("quotas", {})
    if normalized == "enterprise" and quotas_cfg.get("enterprise_ae_annual") is not None:
        return float(quotas_cfg["enterprise_ae_annual"])
    if normalized == "commercial" and quotas_cfg.get("midmarket_ae_annual") is not None:
        return float(quotas_cfg["midmarket_ae_annual"])

    return SEGMENT_QUOTAS.get(normalized, 1_400_000)


def _get_segment_attainment(segment: str) -> float:
    """Return attainment default for a segment."""
    normalized = _normalize_segment(segment)
    assumptions = _load_assumptions()

    segment_attainment = assumptions.get("segment_productivity", {}).get(normalized, {}).get("attainment_rate")
    if segment_attainment is not None:
        return float(segment_attainment)

    global_attainment = assumptions.get("capacity", {}).get("attainment_rate")
    if global_attainment is not None:
        return float(global_attainment)

    return SEGMENT_ATTAINMENT.get(normalized, 1.0)


def _get_ramp_factor(segment: str, months_since_start: int) -> float:
    """
    Return the ramp multiplier for a given segment and number of months since start.

    Months is 0-indexed from start month:
      - month 0 = start month → uses key 1 in curve
      - month 1 = one month later → uses key 2
    We shift: curve_key = months_since_start + 1 (1-indexed).
    """
    curve = _get_ramp_curve(segment)
    key = months_since_start + 1  # convert 0-indexed months → 1-indexed key
    if key in curve:
        return curve[key]
    max_key = max(curve.keys())
    if key > max_key:
        return curve[max_key]  # fully ramped
    return 0.0


def _months_since(start: date, as_of: date) -> int:
    """Return full months elapsed from start to as_of (0 in the start month)."""
    return (as_of.year - start.year) * 12 + (as_of.month - start.month)


def _is_ramped(segment: str, start: date, as_of: date) -> bool:
    """Return True if the rep is fully ramped by as_of."""
    months = _months_since(start, as_of)
    curve = _get_ramp_curve(segment)
    max_key = max(curve.keys())
    # Fully ramped when curve key >= max_key (i.e. months + 1 >= max_key)
    return (months + 1) >= max_key


# =============================================================================
# Public API
# =============================================================================

def load_roster_data(data: dict | None) -> dict:
    """Normalize raw roster YAML data into the canonical grouped shape."""
    result = {
        "active": [],
        "incoming": [],
        "planned": [],
    }

    for key in ("active", "incoming", "planned"):
        raw = data.get(key) or []
        entries = []
        for item in raw:
            if item is None:
                continue
            item = deepcopy(item)
            # Normalize date fields to string
            if "start_date" in item:
                item["start_date"] = _ensure_str_date(item["start_date"])
            if "expected_start" in item:
                item["expected_start"] = _ensure_str_date(item["expected_start"])
            if "employee_start_date" in item:
                item["employee_start_date"] = _ensure_str_date(item["employee_start_date"])
            if "segment" in item:
                item["segment"] = _normalize_segment(item["segment"])
            entries.append(item)
        result[key] = entries

    return result


def load_roster(path: str) -> dict:
    """
    Read the roster YAML file and return a dict with 'active', 'incoming', 'planned' lists.

    start_date values are preserved as strings in the returned dict (consistent with YAML).
    Handles YAML dates (which PyYAML parses as date objects) by converting to strings.
    """
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    return load_roster_data(data)


def merge_roster_with_sf(
    yaml_active: list[dict],
    sf_active: list[dict],
) -> list[dict]:
    """
    Merge YAML active roster with Salesforce active AEs. SF is the floor.

    Rules:
    - If person is in SF but NOT in YAML → add them; default start_date = ramped.
    - If person is in both SF and YAML → use SF for existence, YAML for start_date.
    - If person is in YAML but NOT in SF → exclude them (SF is the floor).
    - Always return at least as many people as SF has.
    - Match is case-insensitive on name.
    """
    yaml_by_name: dict[str, dict] = {}
    yaml_by_user_id: dict[str, dict] = {}
    for entry in yaml_active:
        if "name" in entry:
            yaml_by_name[_normalize_key(entry["name"])] = entry
        if entry.get("user_id"):
            yaml_by_user_id[_normalize_key(entry["user_id"])] = entry

    merged = []
    for sf_entry in sf_active:
        entry = deepcopy(sf_entry)
        sf_name_key = _normalize_key(entry.get("name"))
        sf_user_key = _normalize_key(entry.get("user_id"))
        yaml_entry = yaml_by_user_id.get(sf_user_key) or yaml_by_name.get(sf_name_key)

        if entry.get("employee_start_date"):
            entry["employee_start_date"] = _ensure_str_date(entry["employee_start_date"])

        if yaml_entry:
            if yaml_entry.get("start_date"):
                entry["start_date"] = _ensure_str_date(yaml_entry["start_date"])
            elif entry.get("employee_start_date"):
                entry["start_date"] = _ensure_str_date(entry["employee_start_date"])
            else:
                entry["start_date"] = _default_ramped_start()

            if yaml_entry.get("segment"):
                entry["segment"] = _normalize_segment(yaml_entry["segment"])
            elif entry.get("segment"):
                entry["segment"] = _normalize_segment(entry["segment"])
        else:
            if entry.get("employee_start_date"):
                entry["start_date"] = _ensure_str_date(entry["employee_start_date"])
            else:
                entry["start_date"] = _default_ramped_start()
            if entry.get("segment"):
                entry["segment"] = _normalize_segment(entry["segment"])

        merged.append(entry)

    return merged


def calculate_monthly_capacity(roster: list[dict], month: date) -> dict:
    """
    Calculate aggregate monthly capacity for all reps in the roster for a given month.

    Ramp factor is looked up from assumptions.yaml `segment_productivity.[segment].ramp_curve`
    if available, otherwise from the module-level SEGMENT_RAMP_CURVES constants.

    Returns:
        {
            "total": float,          # total effective capacity (dollars)
            "ramped_count": int,     # reps at full ramp
            "ramping_count": int,    # reps still ramping
            "total_count": int,      # all reps in roster
            "per_rep": list[dict],   # per-rep details
        }
    """
    total = 0.0
    ramped_count = 0
    ramping_count = 0
    per_rep = []

    for rep in roster:
        start_date_raw = rep.get("start_date") or rep.get("expected_start") or rep.get("employee_start_date")
        if not start_date_raw:
            # No start date → assume fully ramped
            start_date_raw = _default_ramped_start()

        start = _parse_date(start_date_raw)

        # Don't count reps who haven't started yet
        if month < start:
            per_rep.append({
                "name": rep.get("name", "unknown"),
                "segment": rep.get("segment", "enterprise"),
                "start_date": _ensure_str_date(start),
                "months_since_start": None,
                "ramp_factor": 0.0,
                "effective_capacity": 0.0,
                "is_ramped": False,
            })
            continue

        segment = _normalize_segment(rep.get("segment") or "enterprise")
        annual_quota = rep.get("annual_quota") or _get_segment_quota(segment)
        attainment = rep.get("attainment_rate") or _get_segment_attainment(segment)

        months = _months_since(start, month)
        ramp_factor = _get_ramp_factor(segment, months)
        monthly_quota = annual_quota / 12
        capacity = monthly_quota * ramp_factor * attainment

        ramped = _is_ramped(segment, start, month)
        if ramped:
            ramped_count += 1
        else:
            ramping_count += 1

        total += capacity
        per_rep.append({
            "name": rep.get("name", "unknown"),
            "segment": segment,
            "start_date": _ensure_str_date(start),
            "months_since_start": months,
            "ramp_factor": ramp_factor,
            "effective_capacity": capacity,
            "is_ramped": ramped,
        })

    return {
        "total": total,
        "ramped_count": ramped_count,
        "ramping_count": ramping_count,
        "total_count": len(roster),
        "per_rep": per_rep,
    }


def get_full_roster_from_data(
    sf_active_aes: list[dict],
    yaml_data: dict | None,
) -> list[dict]:
    """
    Orchestrate: merge normalized roster data with active Salesforce/warehouse AEs.

    Returns a unified list where each entry has a 'tier' field:
      - "active"   → currently employed (SF floor + YAML augmentation)
      - "incoming" → signed offer, not yet started
      - "planned"  → req open / expected hire
    """
    normalized_roster = load_roster_data(yaml_data)

    # Active: SF is the floor, YAML augments
    merged_active = merge_roster_with_sf(normalized_roster["active"], sf_active_aes)
    for entry in merged_active:
        entry["tier"] = "active"

    # Incoming: normalize date fields, tag tier
    incoming = []
    for entry in normalized_roster["incoming"]:
        e = deepcopy(entry)
        e["tier"] = "incoming"
        if "start_date" in e:
            e["start_date"] = _ensure_str_date(e["start_date"])
        if "employee_start_date" in e:
            e["employee_start_date"] = _ensure_str_date(e["employee_start_date"])
        if "segment" in e:
            e["segment"] = _normalize_segment(e["segment"])
        incoming.append(e)

    # Planned: normalize date fields, tag tier
    planned = []
    for entry in normalized_roster["planned"]:
        e = deepcopy(entry)
        e["tier"] = "planned"
        if "expected_start" in e:
            e["expected_start"] = _ensure_str_date(e["expected_start"])
        if "segment" in e:
            e["segment"] = _normalize_segment(e["segment"])
        planned.append(e)

    return merged_active + incoming + planned


def get_full_roster(
    sf_active_aes: list[dict],
    yaml_path: str,
) -> list[dict]:
    """
    Orchestrate: load YAML, merge active with SF, append incoming + planned.

    Returns a unified list where each entry has a 'tier' field:
      - "active"   → currently employed (SF floor + YAML augmentation)
      - "incoming" → signed offer, not yet started
      - "planned"  → req open / expected hire
    """
    return get_full_roster_from_data(sf_active_aes, load_roster(yaml_path))


def roster_data_quality(roster: list[dict]) -> dict:
    """Assess data quality of the merged roster.

    Returns a dict with:
        total: int — total reps
        active: int — active tier count
        missing_sf_start_date: list[str] — names using fallback dates
        using_yaml_override: list[str] — names where YAML overrides SF date
        fully_sf_driven: int — count using SF date directly
        quality_score: float — 0-1 (1 = all dates from SF)
    """
    active_reps = [r for r in roster if r.get("tier") == "active"]
    missing_sf = []
    yaml_override = []
    sf_driven = 0

    default_ramped = _default_ramped_start()

    for rep in active_reps:
        name = rep.get("name", "Unknown")
        has_sf_date = bool(rep.get("employee_start_date"))
        has_yaml_date = bool(rep.get("start_date")) and rep.get("start_date") != default_ramped
        using_default = rep.get("start_date") == default_ramped

        if not has_sf_date and using_default:
            missing_sf.append(name)
        elif has_yaml_date and has_sf_date and rep.get("start_date") != _ensure_str_date(rep.get("employee_start_date")):
            yaml_override.append(name)
        else:
            sf_driven += 1

    total_active = len(active_reps)
    quality = sf_driven / max(total_active, 1)

    return {
        "total": len(roster),
        "active": total_active,
        "incoming": len([r for r in roster if r.get("tier") == "incoming"]),
        "planned": len([r for r in roster if r.get("tier") == "planned"]),
        "missing_sf_start_date": missing_sf,
        "using_yaml_override": yaml_override,
        "fully_sf_driven": sf_driven,
        "quality_score": quality,
        "message": (
            f"{sf_driven}/{total_active} active AEs fully SF-driven. "
            + (f"{len(missing_sf)} missing SF start dates: {', '.join(missing_sf)}. " if missing_sf else "")
            + (f"{len(yaml_override)} using YAML date overrides." if yaml_override else "")
        ),
    }


def project_capacity_timeline(
    roster: list[dict],
    start_month: date,
    months: int = 12,
) -> list[dict]:
    """
    Month-by-month capacity projection over `months` months starting at `start_month`.

    For each rep, uses their `start_date` (or `expected_start` for planned entries).
    Reps with a `tier` of "incoming" or "planned" are included once their start date
    has been reached.

    Returns a list of dicts, one per month:
        {
            "month": date,
            "label": str,   # e.g. "Apr 2026"
            "total": float,
            "ramped_count": int,
            "ramping_count": int,
            "total_count": int,
        }
    """
    timeline = []
    current = start_month

    for _ in range(months):
        # Build the "active" slice for this month: reps who have started by this month
        active_this_month = []
        for rep in roster:
            # Determine start date for this rep
            start_raw = rep.get("start_date") or rep.get("expected_start") or rep.get("employee_start_date")
            if not start_raw:
                start_raw = _default_ramped_start()

            start = _parse_date(start_raw)

            # Only include reps who have started by this month
            if start <= current:
                active_this_month.append(rep)

        cap = calculate_monthly_capacity(active_this_month, current)

        timeline.append({
            "month": current,
            "label": current.strftime("%b %Y"),
            "total": cap["total"],
            "ramped_count": cap["ramped_count"],
            "ramping_count": cap["ramping_count"],
            "total_count": cap["total_count"],
        })

        current = current + relativedelta(months=1)

    return timeline

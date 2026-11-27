"""Read ``capacity.yaml`` (per profile) and ``team_members.csv`` (per company).

``team_members.csv`` is the only authority on people. ``capacity.yaml`` names
the quota-carrying roles, the roles that are counted but carry no capacity,
an entered ramp curve and attrition rate (used only where history cannot
supply them) and the costs of the two actions.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from .load import parse_date, parse_money
from .roster import Member

DEFAULT_PROGRAMME_RAMP_MONTHS = 3


@dataclass(frozen=True)
class CapacityConfig:
    quota_roles: tuple[str, ...]
    other_roles: tuple[str, ...] = ()
    ramp: tuple[Decimal, ...] | None = None  # entered
    attrition: Decimal | None = None  # entered, per AE-month
    loaded_cost_per_ae_month: Decimal | None = None
    programme_cost_per_dollar: Decimal | None = None
    programme_ramp_months: int | None = None  # entered; None means the default
    hires_bound: int | None = None


def load_capacity(profile_dir: Path) -> CapacityConfig | None:
    path = Path(profile_dir) / "capacity.yaml"
    if not path.exists():
        return None
    doc = yaml.safe_load(path.read_text()) or {}
    roles = doc.get("roles") or {}
    quota = tuple(str(r).strip().lower() for r in roles.get("quota_carrying") or ())
    if not quota:
        raise ValueError(f"{path}: roles.quota_carrying must name at least one role")
    ramp = (doc.get("ramp") or {}).get("months")
    costs = doc.get("costs") or {}
    return CapacityConfig(
        quota_roles=quota,
        other_roles=tuple(str(r).strip().lower() for r in roles.get("other") or ()),
        ramp=None
        if ramp is None
        else tuple(_opt(x, "ramp weight", Decimal(0), Decimal(1)) for x in ramp),
        attrition=_opt(
            (doc.get("attrition") or {}).get("monthly_per_ae"),
            "monthly_per_ae",
            Decimal(0),
            Decimal("0.999999"),
        ),
        loaded_cost_per_ae_month=_opt(
            costs.get("loaded_cost_per_ae_month"),
            "loaded_cost_per_ae_month",
            Decimal(0),
        ),
        programme_cost_per_dollar=_opt(
            costs.get("programme_cost_per_dollar_of_pipeline"),
            "programme_cost_per_dollar_of_pipeline",
            Decimal(0),
        ),
        programme_ramp_months=_opt_int(
            (doc.get("programme") or {}).get("ramp_months"), "ramp_months", 1
        ),
        hires_bound=_opt_int(
            (doc.get("hires") or {}).get("max_in_one_quarter"), "max_in_one_quarter", 0
        ),
    )


@dataclass(frozen=True)
class RosterExclusion:
    id: str
    role: str
    reason: str


@dataclass(frozen=True)
class RosterLoad:
    members: tuple[Member, ...]
    excluded: tuple[RosterExclusion, ...]
    other_roles: dict[str, int]  # counted, carry no capacity
    rows: int
    unavailable: str = ""


def load_roster(path: Path, cfg: CapacityConfig | None) -> RosterLoad:
    path = Path(path)
    if cfg is None:
        return RosterLoad((), (), {}, 0, "no capacity.yaml in the profile")
    if not path.exists():
        return RosterLoad((), (), {}, 0, "no team_members.csv")
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    for column in ("id", "role", "start_date"):
        if not rows or column not in rows[0]:
            extra = ": no roster history" if column == "start_date" else ""
            return RosterLoad(
                (), (), {}, len(rows), f"team_members.csv has no {column} column{extra}"
            )
    members, excluded, others = [], [], Counter()
    first_row: dict[str, int] = {}
    for row_number, raw in enumerate(rows, start=2):
        role = (raw.get("role") or "").strip().lower()
        rid = (raw.get("id") or "").strip()
        if not rid:
            excluded.append(RosterExclusion(rid, role, "id is blank"))
            continue
        if rid in first_row:
            excluded.append(
                RosterExclusion(
                    rid, role, f"duplicate id (first seen on row {first_row[rid]})"
                )
            )
            continue
        first_row[rid] = row_number
        if role in cfg.other_roles:
            others[role] += 1
            continue
        if role not in cfg.quota_roles:
            excluded.append(
                RosterExclusion(
                    rid, role, f"role '{role}' is not named in capacity.yaml"
                )
            )
            continue
        parsed = _member(raw, rid, role)
        if isinstance(parsed, Member):
            members.append(parsed)
        else:
            excluded.append(RosterExclusion(rid, role, parsed))
    return RosterLoad(tuple(members), tuple(excluded), dict(others), len(rows))


def _member(raw: dict, rid: str, role: str) -> Member | str:
    try:
        start = parse_date(raw.get("start_date") or "")
    except ValueError:
        return "start date is missing or invalid"
    end_text = (raw.get("end_date") or "").strip()
    try:
        end = parse_date(end_text) if end_text else None
    except ValueError:
        return "end date is invalid"
    if end is not None and end < start:
        return "ends before it starts"
    quota = parse_money(raw.get("annual_quota") or "")
    if quota is not None and quota < 0:
        return "annual quota is negative"
    return Member(rid, role, (raw.get("segment") or "").strip(), start, end, quota)


def _dec(x, field: str = "value") -> Decimal:
    try:
        value = Decimal(str(x))
    except InvalidOperation as exc:
        raise ValueError(f"capacity.yaml: {field} '{x}' is not a number") from exc
    if not value.is_finite():
        raise ValueError(f"capacity.yaml: {field} '{x}' is not a finite number")
    return value


def _opt(
    x, field: str = "value", low: Decimal | None = None, high: Decimal | None = None
):
    """A finite decimal within [low, high], or None when absent."""
    if x is None:
        return None
    value = _dec(x, field)
    if (low is not None and value < low) or (high is not None and value > high):
        bound = (
            f"between {low} and {high}"
            if None not in (low, high)
            else f"at least {low}"
        )
        raise ValueError(f"capacity.yaml: {field} {value} must be {bound}")
    return value


def _opt_int(x, field: str = "value", low: int = 0) -> int | None:
    if x is None:
        return None
    if isinstance(x, bool) or not isinstance(x, int) or x < low:
        raise ValueError(
            f"capacity.yaml: {field} '{x}' must be a whole number of at least {low}"
        )
    return x


def load_headcount_targets(profile_dir: Path) -> dict[str, int]:
    """``monthly_ae_targets`` from targets.yaml, by 'YYYY-MM'. A comparison
    line only: it never creates a hire."""
    path = Path(profile_dir) / "targets.yaml"
    doc = yaml.safe_load(path.read_text()) or {}
    return {
        str(day)[:7]: int(n) for day, n in (doc.get("monthly_ae_targets") or {}).items()
    }

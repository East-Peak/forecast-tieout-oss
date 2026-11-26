"""Read a profile directory and a company's CSV files.

This package keeps its own small reader (rather than reusing the old engine's
connector) so that it has no path into ``engine.gtm_model`` and so that money is
parsed straight into exact decimals.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from .fiscal import FiscalYear
from .records import (
    LOST,
    WON,
    Dataset,
    Deal,
    Exclusion,
    Observation,
    Profile,
    StageDef,
    Transition,
)


def load_profile(path: Path) -> Profile:
    path = Path(path)
    stages_doc = _yaml(path / "stages.yaml")
    mapping = _yaml(path / "field_mappings.yaml")["opportunity"]["stage"][
        "stage_mapping"
    ]
    targets_doc = _yaml(path / "targets.yaml")

    stages = tuple(
        StageDef(
            name=s["name"],
            code=mapping[s["name"]],
            order=int(s["order"]),
            probability=Decimal(str(s["probability"])),
        )
        for s in stages_doc["stages"]
    )
    fy = FiscalYear(date.fromisoformat(str(targets_doc["fiscal_year_start"])))
    quarterly = targets_doc.get("quarterly_targets") or {}
    missing = [k for k in fy.quarter_keys if k not in quarterly]
    if missing:
        raise ValueError(
            f"targets.yaml has no bookings target for {', '.join(missing)} "
            f"(fiscal year starting {fy.start})"
        )
    targets = {k: _target(quarterly[k]) for k in fy.quarter_keys}
    later = {k: _target(quarterly[k]) for k in fy.next.quarter_keys if k in quarterly}
    return Profile(
        stages=stages,
        fiscal_year=fy,
        quarterly_targets=targets,
        raw_to_code=dict(mapping),
        later_targets=later,
    )


@dataclass(frozen=True)
class LoadedCompany:
    dataset: Dataset
    exclusions: tuple[Exclusion, ...]
    source_rows: int
    source_arr_total: Decimal
    unparseable_arr_rows: int
    roster_roles: dict[str, int]
    unmapped_transitions: int


def load_company(path: Path, profile: Profile) -> LoadedCompany:
    path = Path(path)
    rows = _csv(path / "deals.csv")
    deals: list[Deal] = []
    exclusions: list[Exclusion] = []
    total = Decimal(0)
    unparseable = 0
    first_row: dict[str, int] = {}
    for row_number, raw in enumerate(rows, start=2):
        arr = parse_money(raw.get("arr", ""))
        if arr is None:
            unparseable += 1
        else:
            total += arr
        deal_id = (raw.get("id") or "").strip()
        if not deal_id:
            parsed = "deal id is blank"
        elif deal_id in first_row:
            parsed = f"duplicate deal id (first seen on row {first_row[deal_id]})"
        else:
            first_row[deal_id] = row_number
            parsed = _parse_deal(row_number, raw, arr, profile)
        if isinstance(parsed, Deal):
            deals.append(parsed)
        else:
            exclusions.append(Exclusion(row_number, raw.get("id", ""), parsed, arr))

    known = {d.id for d in deals}
    timed: list[tuple[str, datetime, Transition]] = []
    unmapped = 0
    for raw in _csv(path / "stage_history.csv"):
        if raw["deal_id"] not in known:
            continue
        code = profile.code_for(raw["to_stage"])
        if code is None:
            unmapped += 1
            continue
        # Order by the full timestamp so same-day changes resolve by time, not row order.
        at = datetime.fromisoformat(raw["transition_date"].strip())
        timed.append((raw["deal_id"], at, Transition(raw["deal_id"], code, at.date())))
    timed.sort(key=lambda x: (x[0], x[1]))
    transitions = [t for _, _, t in timed]

    observations = None
    obs_path = path / "deal_observations.csv"
    if obs_path.exists():
        observations = tuple(
            sorted(
                (
                    Observation(
                        raw["deal_id"],
                        parse_date(raw["observed_date"]),
                        Decimal(raw["amount"]),
                        parse_date(raw["expected_close_date"]),
                    )
                    for raw in _csv(obs_path)
                    if raw["deal_id"] in known
                ),
                key=lambda o: (o.deal_id, o.on),
            )
        )

    roster_path = path / "team_members.csv"
    roles = (
        Counter(r["role"].strip().lower() for r in _csv(roster_path))
        if roster_path.exists()
        else Counter()
    )

    return LoadedCompany(
        dataset=Dataset(tuple(deals), tuple(transitions), observations),
        exclusions=tuple(exclusions),
        source_rows=len(rows),
        source_arr_total=total,
        unparseable_arr_rows=unparseable,
        roster_roles=dict(roles),
        unmapped_transitions=unmapped,
    )


def _parse_deal(
    row: int, raw: dict, arr: Decimal | None, profile: Profile
) -> Deal | str:
    if arr is None:
        return "arr is missing or not a number"
    code = profile.code_for(raw.get("stage", ""))
    if code is None:
        return f"stage '{raw.get('stage', '')}' is not in the profile's stage mapping"
    try:
        created = parse_date(raw["created_date"])
    except (KeyError, ValueError):
        return "created date is missing or invalid"
    is_closed = parse_flag(raw.get("is_closed", ""))
    is_won = parse_flag(raw.get("is_won", ""))
    if (is_closed, is_won) != (code in (WON, LOST), code == WON):
        return "is_closed/is_won flags disagree with the stage"
    close_text = (raw.get("close_date") or "").strip()
    close = None
    if close_text:
        try:
            close = parse_date(close_text)
        except ValueError:
            return "close date is invalid"
    if is_closed and close is None:
        return "closed deal has no close date"
    if is_closed and close < created:
        return "close date is before created date"
    return Deal(
        row=row,
        id=raw["id"],
        type=(raw.get("type") or "").strip(),
        segment=(raw.get("segment") or "").strip(),
        stage=code,
        arr=arr,
        created=created,
        close=close,
        is_closed=is_closed,
        is_won=is_won,
    )


def parse_money(text: str) -> Decimal | None:
    try:
        value = Decimal((text or "").strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _target(entry) -> Decimal:
    value = entry["bookings_target"] if isinstance(entry, dict) else entry
    return Decimal(str(value))


def parse_date(text: str) -> date:
    text = text.strip()
    return (
        datetime.fromisoformat(text).date()
        if "T" in text or " " in text
        else date.fromisoformat(text)
    )


def parse_flag(text: str) -> bool:
    return text.strip().lower() in ("true", "1", "yes")


def _csv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _yaml(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)

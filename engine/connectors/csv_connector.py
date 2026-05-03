"""CSV file connector for Forecast Tieout.

Reads deal, team, and optional company/contact/history data from CSV files.
Simplest onboarding path — export from any CRM, match the template format, run.

Stage normalization : if `field_mapping_path` is provided, this
connector loads the profile's `field_mappings.yaml` and translates raw
source-system stages to engine model stages (S0..S5/Won/Lost). Both
`Deal.stage` and `StageTransition.to_stage`/`from_stage` are populated with
model stages; the raw source value is preserved on `Deal.raw_stage` /
`StageTransition.raw_to_stage` / `.raw_from_stage`.

If `field_mapping_path` is None, stages pass through unchanged (the connector
behaves as it did pre-refactor). This is intended for tests and fixtures only;
production use should always supply the mapping path.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from .interface import (
    ConnectorCapabilities,
    ConnectorInterface,
    Company,
    Contact,
    Deal,
    StageTransition,
    TeamMember,
)

# Required files and their mandatory columns
REQUIRED_FILES = {
    "deals.csv": {"id", "name", "amount", "stage", "close_date", "owner_id"},
    "team_members.csv": {"id", "name", "role"},
}

# Optional files and their expected columns (used for validation when present)
OPTIONAL_FILES = {
    "companies.csv": {"id", "name"},
    "contacts.csv": {"id", "name"},
    "stage_history.csv": {"deal_id", "to_stage", "transition_date"},
}


def _parse_date(value: str) -> Optional[date]:
    """Parse an ISO date string (YYYY-MM-DD) into a date, or None if empty."""
    if not value or not value.strip():
        return None
    return date.fromisoformat(value.strip())


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO datetime string into a datetime."""
    v = value.strip()
    # Handle both 2026-01-15T10:00:00 and 2026-01-15 formats
    if "T" in v:
        return datetime.fromisoformat(v)
    return datetime.fromisoformat(v + "T00:00:00")


def _parse_float(value: str) -> Optional[float]:
    """Parse a float, returning None for empty/blank strings."""
    if not value or not value.strip():
        return None
    return float(value.strip())


def _parse_int(value: str) -> Optional[int]:
    """Parse an int, returning None for empty/blank strings."""
    if not value or not value.strip():
        return None
    return int(value.strip())


def _parse_bool(value: str, default: bool = False) -> bool:
    """Parse a boolean string. Accepts true/false/1/0/yes/no (case-insensitive)."""
    if not value or not value.strip():
        return default
    return value.strip().lower() in ("true", "1", "yes")


def _get(row: dict[str, str], key: str, default: str = "") -> str:
    """Get a value from a CSV row dict, returning default if key missing or empty."""
    return row.get(key, default) or default


class CSVConnector(ConnectorInterface):
    """Reads forecast data from a directory of CSV files.

    Required files:
        - deals.csv (id, name, amount, stage, close_date, owner_id)
        - team_members.csv (id, name, role)

    Optional files:
        - companies.csv
        - contacts.csv
        - stage_history.csv
    """

    def __init__(
        self,
        data_dir: str | Path,
        field_mapping_path: Optional[str | Path] = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._field_mapping_path = (
            Path(field_mapping_path) if field_mapping_path else None
        )
        self._stage_mapping = self._load_stage_mapping()
        self._validate()
        self._caps = ConnectorCapabilities(
            has_stage_history=(self._data_dir / "stage_history.csv").is_file(),
            has_contacts=(self._data_dir / "contacts.csv").is_file(),
            has_companies=(self._data_dir / "companies.csv").is_file(),
        )

    def _load_stage_mapping(self) -> dict[str, str]:
        """Load opportunity.stage.stage_mapping from the profile's
        field_mappings.yaml.

        ARCHITECTURE.md contract: if a field_mapping_path is configured, the
        profile MUST declare a non-empty stage_mapping. Returning {} on
        a configured-but-empty mapping would cause Deal.stage to silently
        stay in raw source vocabulary, which is the failure mode
        ARCHITECTURE.md explicitly prevents.

        Returns {} only when no field_mapping_path is configured (test
        and fixture mode).
        """
        if self._field_mapping_path is None:
            return {}
        if not self._field_mapping_path.is_file():
            raise FileNotFoundError(
                f"field_mappings.yaml not found at {self._field_mapping_path}"
            )
        with open(self._field_mapping_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        opp_block = data.get("opportunity") or {}
        stage_block = opp_block.get("stage") or {}
        mapping = stage_block.get("stage_mapping")
        if mapping is None:
            raise ValueError(
                f"opportunity.stage.stage_mapping is required in "
                f"{self._field_mapping_path} when CSVConnector is "
                f"constructed with field_mapping_path. Per ARCHITECTURE.md, "
                f"connectors must normalize source stages to model "
                f"vocabulary; declare the mapping or omit "
                f"field_mapping_path entirely."
            )
        if not isinstance(mapping, dict):
            raise ValueError(
                f"opportunity.stage.stage_mapping in {self._field_mapping_path} "
                f"must be a dict; got {type(mapping).__name__}"
            )
        if not mapping:
            raise ValueError(
                f"opportunity.stage.stage_mapping in {self._field_mapping_path} "
                f"is empty. Declare at least one source-stage → model-stage "
                f"mapping or omit field_mapping_path."
            )
        # Coerce all keys/values to strings; YAML loaders sometimes return
        # ints for numeric stages.
        return {str(k): str(v) for k, v in mapping.items()}

    def _normalize_stage(self, raw_stage: str) -> str:
        """Translate a raw source-system stage to model-stage vocabulary.

        Pass-through if no mapping is loaded (legacy/test mode) or if the
        raw value isn't in the mapping (engine handles unknown stages
        downstream, but we don't silently drop information).
        """
        if not self._stage_mapping:
            return raw_stage
        return self._stage_mapping.get(raw_stage, raw_stage)

    def _validate(self) -> None:
        """Check that required files exist and have required columns."""
        for filename, required_cols in REQUIRED_FILES.items():
            filepath = self._data_dir / filename
            if not filepath.is_file():
                raise FileNotFoundError(
                    f"Required file missing: {filename} "
                    f"(looked in {self._data_dir})"
                )
            with open(filepath, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise ValueError(f"File {filename} appears empty or has no header row")
                actual_cols = set(reader.fieldnames)
                missing = required_cols - actual_cols
                if missing:
                    raise ValueError(
                        f"File {filename} missing required columns: "
                        f"{', '.join(sorted(missing))}"
                    )

    def _read_csv(self, filename: str) -> list[dict[str, str]]:
        """Read a CSV file and return list of row dicts."""
        filepath = self._data_dir / filename
        with open(filepath, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    # ── Interface implementation ─────────────────────────────────────

    def capabilities(self) -> ConnectorCapabilities:
        return self._caps

    def fetch_deals(self, filters: dict[str, Any] | None = None) -> list[Deal]:
        rows = self._read_csv("deals.csv")
        first_s2 = self._compute_first_s2_entry_dates() if self._caps.has_stage_history else {}
        deals: list[Deal] = []
        for row in rows:
            raw_stage = row["stage"].strip()
            deal_id = row["id"].strip()
            deals.append(Deal(
                id=deal_id,
                name=row["name"].strip(),
                amount=_parse_float(row["amount"]),
                stage=self._normalize_stage(raw_stage),
                raw_stage=raw_stage if self._stage_mapping else None,
                close_date=_parse_date(row.get("close_date", "")),
                owner_id=row["owner_id"].strip(),
                type=_get(row, "type") or None,
                created_date=_parse_date(_get(row, "created_date")),
                segment=_get(row, "segment") or None,
                source=_get(row, "source") or None,
                is_closed=_parse_bool(_get(row, "is_closed"), default=False),
                is_won=_parse_bool(_get(row, "is_won"), default=False),
                # ARR / finance fields (optional CSV columns)
                year_1_arr=_parse_float(_get(row, "year_1_arr")),
                arr=_parse_float(_get(row, "arr")),
                nacv=_parse_float(_get(row, "nacv")),
                non_recurring=_parse_float(_get(row, "non_recurring")),
                effective_start_date=_parse_date(_get(row, "effective_start_date")),
                effective_end_date=_parse_date(_get(row, "effective_end_date")),
                revenue_type=_get(row, "revenue_type") or None,
                # Open-inventory parity fields (optional CSV columns)
                owner_name=_get(row, "owner_name") or None,
                forecast_category=_get(row, "forecast_category") or None,
                source_stream=_get(row, "source_stream") or None,
                # Computed from stage_history.csv if present
                first_s2_entry_date=first_s2.get(deal_id),
            ))
        return deals

    def _compute_first_s2_entry_dates(self) -> dict[str, date]:
        """For each deal, find the earliest stage_history transition where
        the destination stage normalizes to 'S2'. Returns {deal_id: date}.

        Used to populate Deal.first_s2_entry_date — the canonical "entered
        pipeline" timestamp for monthly-actuals semantics. If no S2
        transition exists for a deal (e.g., it skipped S2 or never reached
        it), the deal won't appear in the result and Deal.first_s2_entry_date
        stays None.
        """
        rows = self._read_csv("stage_history.csv")
        first_s2: dict[str, date] = {}
        for row in rows:
            raw_to = (row.get("to_stage") or "").strip()
            if not raw_to:
                continue
            normalized = self._normalize_stage(raw_to)
            if normalized != "S2":
                continue
            deal_id = (row.get("deal_id") or "").strip()
            if not deal_id:
                continue
            transition = _parse_datetime(row["transition_date"])
            transition_date = transition.date() if isinstance(transition, datetime) else transition
            existing = first_s2.get(deal_id)
            if existing is None or transition_date < existing:
                first_s2[deal_id] = transition_date
        return first_s2

    def fetch_team_members(self) -> list[TeamMember]:
        rows = self._read_csv("team_members.csv")
        members: list[TeamMember] = []
        for row in rows:
            members.append(TeamMember(
                id=row["id"].strip(),
                name=row["name"].strip(),
                role=_get(row, "role") or "AE",
                segment=_get(row, "segment") or None,
                start_date=_parse_date(_get(row, "start_date")),
                is_active=_parse_bool(_get(row, "is_active"), default=True),
                manager_id=_get(row, "manager_id") or None,
            ))
        return members

    def fetch_companies(self, filters: dict[str, Any] | None = None) -> list[Company]:
        if not self._caps.has_companies:
            return []
        rows = self._read_csv("companies.csv")
        companies: list[Company] = []
        for row in rows:
            companies.append(Company(
                id=row["id"].strip(),
                name=row["name"].strip(),
                segment=_get(row, "segment") or None,
                industry=_get(row, "industry") or None,
                employee_count=_parse_int(_get(row, "employee_count")),
            ))
        return companies

    def fetch_contacts(self, filters: dict[str, Any] | None = None) -> list[Contact]:
        if not self._caps.has_contacts:
            return []
        rows = self._read_csv("contacts.csv")
        contacts: list[Contact] = []
        for row in rows:
            contacts.append(Contact(
                id=row["id"].strip(),
                name=row["name"].strip(),
                email=_get(row, "email") or None,
                company_id=_get(row, "company_id") or None,
                title=_get(row, "title") or None,
            ))
        return contacts

    def fetch_stage_history(
        self, deal_ids: list[str] | None = None
    ) -> list[StageTransition]:
        if not self._caps.has_stage_history:
            return []
        rows = self._read_csv("stage_history.csv")
        transitions: list[StageTransition] = []
        for row in rows:
            deal_id = row["deal_id"].strip()
            if deal_ids is not None and deal_id not in deal_ids:
                continue
            raw_from_str = _get(row, "from_stage").strip()
            raw_from = raw_from_str or None
            raw_to = row["to_stage"].strip()
            transitions.append(StageTransition(
                deal_id=deal_id,
                from_stage=self._normalize_stage(raw_from) if raw_from else None,
                to_stage=self._normalize_stage(raw_to),
                transition_date=_parse_datetime(row["transition_date"]),
                raw_from_stage=raw_from if self._stage_mapping else None,
                raw_to_stage=raw_to if self._stage_mapping else None,
            ))
        return transitions

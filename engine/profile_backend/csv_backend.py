"""CSVBackend — wraps CSVConnector for CSV-backed profiles."""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from engine.connectors.csv_connector import CSVConnector
from engine.gtm_model.derived.mql_signals import (
    MQLSignals,
    MonthlyMQLSeries,
    compute_mql_signals_from_buckets,
    compute_monthly_mql_from_buckets,
)
from engine.profile_backend.protocol import ProfileBackendBase


class CSVBackend(ProfileBackendBase):
    """ProfileBackend backed by a directory of CSV files.

    Uses Concern B defaults (pure-Python `derived/*` computation) since
    CSV has no source-system aggregation. Concern B′ returns None — CSV
    profiles don't have warehouse-style pre-computed mart helpers.

    Args:
        data_dir: Path to the CSV directory.
        field_mapping_path: Path to the profile's field_mappings.yaml
            (required for ARCHITECTURE.md stage normalization).
    """

    def __init__(
        self,
        data_dir: str | Path,
        field_mapping_path: Optional[str | Path] = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        connector = CSVConnector(data_dir, field_mapping_path=field_mapping_path)
        super().__init__(connector=connector)

    def _read_mql_rows(self) -> list[dict[str, str]]:
        path = self._data_dir / "mqls.csv"
        if not path.is_file():
            return []
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return []
            fields = set(reader.fieldnames)
            if "count" not in fields or not ({"month", "month_start", "week_start"} & fields):
                raise ValueError(
                    "mqls.csv must include count plus one of month, month_start, or week_start"
                )
            return list(reader)

    def _monthly_mql_counts(self) -> dict[date, int]:
        counts: dict[date, int] = {}
        for row in self._read_mql_rows():
            raw_date = row.get("month") or row.get("month_start") or row.get("week_start") or ""
            try:
                row_date = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
            month = row_date.replace(day=1)
            counts[month] = counts.get(month, 0) + int(float(row.get("count") or 0))
        return counts

    def compute_mql_signals(
        self, as_of: date, lookback_days: int = 180
    ) -> Optional[MQLSignals]:
        rows = self._read_mql_rows()
        if not rows:
            return None

        lookback_start = as_of - timedelta(days=lookback_days)
        explicit_weekly: list[dict] = []
        for row in rows:
            week_start_raw = row.get("week_start") or ""
            if not week_start_raw:
                continue
            try:
                week_start = date.fromisoformat(str(week_start_raw)[:10])
            except ValueError:
                continue
            if lookback_start <= week_start <= as_of:
                explicit_weekly.append({
                    "week_start": week_start.isoformat(),
                    "count": float(row.get("count") or 0),
                })
        if explicit_weekly:
            return compute_mql_signals_from_buckets(
                explicit_weekly,
                lookback_days=lookback_days,
                source="csv:mqls.csv",
            )

        weekly: list[dict] = []
        for month_start, count in sorted(self._monthly_mql_counts().items()):
            for offset in (0, 7, 14, 21):
                week_start = month_start + timedelta(days=offset)
                if lookback_start <= week_start <= as_of:
                    weekly.append({
                        "week_start": week_start.isoformat(),
                        "count": float(count) / 4.0,
                    })
        if not weekly:
            return None
        return compute_mql_signals_from_buckets(
            weekly,
            lookback_days=lookback_days,
            source="csv:mqls.csv",
        )

    def compute_monthly_mql_actuals(
        self, as_of: date, months: int = 12, fy_start: Optional[date] = None
    ) -> Optional[MonthlyMQLSeries]:
        counts = self._monthly_mql_counts()
        if not counts:
            return None
        return compute_monthly_mql_from_buckets(
            counts,
            fy_start=fy_start,
            source="csv:mqls.csv",
        )

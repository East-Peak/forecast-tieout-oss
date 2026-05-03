"""CSVBackend — wraps CSVConnector for CSV-backed profiles."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from engine.connectors.csv_connector import CSVConnector
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
        connector = CSVConnector(data_dir, field_mapping_path=field_mapping_path)
        super().__init__(connector=connector)

"""Shared fixtures for the query tests (no tests live here)."""

from datetime import date
from pathlib import Path

ADAPTERS = Path(__file__).resolve().parents[1] / "adapters" / "generated"
CATALOG_PATH = ADAPTERS / "catalog.yaml"
D = date.fromisoformat


def catalog_text() -> str:
    return CATALOG_PATH.read_text()


def by_key(cells) -> dict:
    out = {c.key: c for c in cells}
    assert len(out) == len(cells), "duplicate cell keys"
    return out


def values(cells) -> dict:
    return {c.key: c.value for c in cells}

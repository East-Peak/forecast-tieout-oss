"""Shared module-level helpers used across data_access mixins."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional


def _monthly_series_to_rows(series: dict[date, float]) -> list[dict]:
    """Serialize a {month_start: value} mapping into stable JSON-friendly rows."""
    return [
        {"month": month.isoformat(), "total": float(total or 0.0)}
        for month, total in sorted((series or {}).items())
    ]


def _stable_override_cache_key(ae_overrides: Optional[dict]) -> str:
    """Serialize nested override payloads into a stable cache key."""
    if not ae_overrides:
        return "__base__"
    return json.dumps(ae_overrides, sort_keys=True, default=str)


def _parse_month_target_key(raw_month: Any) -> date:
    """Normalize month-target keys to a first-of-month date."""
    if isinstance(raw_month, date):
        return date(raw_month.year, raw_month.month, 1)

    month_str = str(raw_month or "").strip()
    if len(month_str) == 7:
        month_str = f"{month_str}-01"
    return date.fromisoformat(month_str[:10]).replace(day=1)

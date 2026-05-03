"""Forecast Tieout Engine.

Public API for revenue planning and forecasting.
External consumers should import from this package only.

Usage:
    from gtm_model.tieout import PlanningTieout, TieoutResult
    tieout = PlanningTieout()
    result = tieout.compute_full()
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import PlanningTieout
    from .types import MonthlyCapacityRow, QuarterTieout, ScenarioResult, TieoutResult
    from .views.recommendations import format_money

__all__ = [
    "PlanningTieout",
    "TieoutResult",
    "ScenarioResult",
    "QuarterTieout",
    "MonthlyCapacityRow",
    "format_money",
]


def __getattr__(name: str):
    if name == "PlanningTieout":
        from .engine import PlanningTieout

        return PlanningTieout
    if name in {"TieoutResult", "ScenarioResult", "QuarterTieout", "MonthlyCapacityRow"}:
        from .types import MonthlyCapacityRow, QuarterTieout, ScenarioResult, TieoutResult

        values = {
            "TieoutResult": TieoutResult,
            "ScenarioResult": ScenarioResult,
            "QuarterTieout": QuarterTieout,
            "MonthlyCapacityRow": MonthlyCapacityRow,
        }
        return values[name]
    if name == "format_money":
        from .views.recommendations import format_money

        return format_money
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Runtime signal and rate resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .resolver import TieoutRuntimeResolver

__all__ = ["TieoutRuntimeResolver"]


def __getattr__(name: str):
    if name == "TieoutRuntimeResolver":
        from .resolver import TieoutRuntimeResolver

        return TieoutRuntimeResolver
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""Self-serve PLG velocity metrics (signup → activation → conversion).

PLG signals don't fit cleanly into the connector's fetch_*() surface, so
this module accepts pre-bucketed PLG metrics from the backend. Backends
with native PLG data fetch directly; CSV backends pass seed values from
profile config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SelfServeVelocity:
    """PLG funnel metrics for the self-serve revenue stream."""

    signups_per_week: Optional[float] = None
    activations_per_week: Optional[float] = None
    conversions_per_week: Optional[float] = None
    activation_rate: Optional[float] = None  # 0..1
    conversion_rate: Optional[float] = None  # 0..1
    avg_acv: Optional[float] = None
    source: Optional[str] = None  # filled in by backend

    def is_available(self) -> bool:
        """True when at least one signal is populated."""
        return any(
            v is not None
            for v in (
                self.signups_per_week,
                self.activations_per_week,
                self.conversions_per_week,
            )
        )

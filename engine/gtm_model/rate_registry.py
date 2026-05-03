"""
Central Rate Registry with semantic enforcement.

Every rate in the model has a declared semantic type. Consumers must request
rates by semantic, preventing the class of bugs where a quarterly velocity
metric is used as a lifetime probability.

Architectural decision: docs/decisions/002-rate-registry-semantic-enforcement.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from gtm_model.tieout.runtime.env import load_yaml_resource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Semantic types
# ---------------------------------------------------------------------------

class RateSemantic(str, Enum):
    """Declared semantic type for a rate.

    Each type describes what the rate measures, preventing misuse.
    """

    LIFETIME_PROBABILITY = "lifetime_probability"
    """P(win | reached stage), all-inclusive (won / (won+lost+open)).
    Example: S2→Won = 0.18 means 18% of deals reaching S2 eventually win."""

    SEQUENTIAL_TRANSITION = "sequential_transition"
    """P(advance to next stage). Multiplicative chain.
    Example: S0→S1 = 0.55 means 55% of S0 deals advance to S1."""

    QUARTERLY_VELOCITY = "quarterly_velocity"
    """Same-quarter transition rate. UNSAFE for multi-quarter projections.
    Quarter-bounded conversion rates (e.g. "what fraction of deals that
    entered S2 this quarter also closed won this quarter") undercount
    deals that crossed quarter boundaries — only useful for in-quarter
    velocity analysis, not for forecasting future bookings."""

    ACTIVITY_RATE = "activity_rate"
    """Observed activity volume or conversion rate from activity data.
    Example: mql_to_s0 = 0.15 means 15% of MQLs become S0."""

    TIMING_DISTRIBUTION = "timing_distribution"
    """Close timing curve, values sum to 1.0.
    Example: [0.50, 0.17, 0.11, ...] = 50% close in month 1 from S2."""


# ---------------------------------------------------------------------------
# Rate definition
# ---------------------------------------------------------------------------

@dataclass
class RateDefinition:
    """A single rate with full provenance."""

    value: float
    source: str  # "salesforce", "cdw", "config", "computed"
    semantic: RateSemantic
    key: str  # "s2_to_won", "s0_to_s1", etc.
    sample_size: int = 0
    lookback_days: int = 0
    updated_at: datetime = field(default_factory=datetime.now)
    description: str = ""

    def __post_init__(self):
        if isinstance(self.semantic, str):
            self.semantic = RateSemantic(self.semantic)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SemanticMismatchError(TypeError):
    """Raised when a consumer requests a rate with the wrong semantic type."""
    pass


class RateNotFoundError(KeyError):
    """Raised when a requested rate key does not exist in the registry."""
    pass


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class RateRegistry:
    """Central store for all model rates with semantic enforcement.

    Usage:
        registry = RateRegistry()
        registry.load_from_config(assumptions)  # bulk load from YAML

        # Consumers declare what semantic they need:
        rate = registry.get("s2_to_won", RateSemantic.LIFETIME_PROBABILITY)
        # Raises SemanticMismatchError if the rate has a different semantic.
    """

    def __init__(self):
        self._rates: dict[str, RateDefinition] = {}

    def register(self, rate: RateDefinition) -> None:
        """Register or update a rate."""
        self._rates[rate.key] = rate
        logger.debug("Registered rate %s = %.4f (%s, %s)",
                     rate.key, rate.value, rate.semantic.value, rate.source)

    def get(self, key: str, required_semantic: RateSemantic) -> RateDefinition:
        """Get a rate, enforcing semantic match.

        Raises:
            RateNotFoundError: if key not registered.
            SemanticMismatchError: if the rate's semantic differs from required.
        """
        if key not in self._rates:
            raise RateNotFoundError(f"Rate '{key}' not registered")

        rate = self._rates[key]
        if rate.semantic != required_semantic:
            raise SemanticMismatchError(
                f"Rate '{key}' has semantic '{rate.semantic.value}', "
                f"but consumer requires '{required_semantic.value}'. "
                f"Source: {rate.source}, value: {rate.value}"
            )
        return rate

    def get_value(self, key: str, required_semantic: RateSemantic) -> float:
        """Convenience: get just the float value with semantic check."""
        return self.get(key, required_semantic).value

    def try_get(self, key: str, required_semantic: RateSemantic,
                default: float = 0.0) -> float:
        """Get value with semantic check, returning default if not found."""
        try:
            return self.get_value(key, required_semantic)
        except RateNotFoundError:
            return default

    def has(self, key: str) -> bool:
        """Check if a rate is registered."""
        return key in self._rates

    def keys(self) -> list[str]:
        """List all registered rate keys."""
        return list(self._rates.keys())

    def all_rates(self) -> dict[str, RateDefinition]:
        """Return a copy of all registered rates."""
        return dict(self._rates)

    def update_value(self, key: str, value: float, source: str,
                     sample_size: int = 0, lookback_days: int = 0) -> None:
        """Update an existing rate's value and provenance without changing its semantic."""
        if key not in self._rates:
            raise RateNotFoundError(f"Rate '{key}' not registered, cannot update")
        rate = self._rates[key]
        rate.value = value
        rate.source = source
        rate.sample_size = sample_size
        rate.lookback_days = lookback_days
        rate.updated_at = datetime.now()

    # ------------------------------------------------------------------
    # Bulk loading from config
    # ------------------------------------------------------------------

    def load_stage_win_rates(self, stage_conversion: dict) -> None:
        """Load stage-to-won conversion rates from forecast.stage_conversion config.

        These are all-inclusive rates: P(win | reached stage).
        Keys are prefixed with 'stage_' to distinguish from sequential funnel
        rates (e.g., funnel.s5_to_won=0.80 is sequential, stage_s5_win=0.61 is
        all-inclusive). This prevents the exact semantic collision the registry
        is designed to catch.
        """
        mapping = {
            "s2_to_won": ("stage_s2_win", "S2→Won all-inclusive"),
            "s3_to_won": ("stage_s3_win", "S3→Won all-inclusive"),
            "s4_to_won": ("stage_s4_win", "S4→Won all-inclusive"),
            "s5_to_won": ("stage_s5_win", "S5→Won all-inclusive"),
        }
        for config_key, (registry_key, desc) in mapping.items():
            val = stage_conversion.get(config_key)
            if val is not None and float(val) > 0:
                self.register(RateDefinition(
                    value=float(val),
                    source="config",
                    semantic=RateSemantic.LIFETIME_PROBABILITY,
                    key=registry_key,
                    description=desc,
                ))

    def load_funnel_rates(self, funnel: dict) -> None:
        """Load funnel transition rates from config.funnel section.

        s0_to_s1, s1_to_s2 are sequential transitions.
        mql_to_s0 is an activity rate (conversion from marketing activity).
        """
        transition_keys = {
            "s0_to_s1": ("S0→S1 sequential", RateSemantic.SEQUENTIAL_TRANSITION),
            "s1_to_s2": ("S1→S2 sequential", RateSemantic.SEQUENTIAL_TRANSITION),
            "s2_to_s3": ("S2→S3 sequential", RateSemantic.SEQUENTIAL_TRANSITION),
            "s3_to_s4": ("S3→S4 sequential", RateSemantic.SEQUENTIAL_TRANSITION),
            "s4_to_s5": ("S4→S5 sequential", RateSemantic.SEQUENTIAL_TRANSITION),
            "s5_to_won": ("S5→Won sequential", RateSemantic.SEQUENTIAL_TRANSITION),
        }
        for key, (desc, semantic) in transition_keys.items():
            val = funnel.get(key)
            if val is not None and float(val) > 0:
                self.register(RateDefinition(
                    value=float(val),
                    source="config",
                    semantic=semantic,
                    key=key,
                    description=desc,
                ))

        # MQL→S0 is an activity rate, not a stage transition
        mql_to_s0 = funnel.get("mql_to_s0")
        if mql_to_s0 is not None and float(mql_to_s0) > 0:
            self.register(RateDefinition(
                value=float(mql_to_s0),
                source="config",
                semantic=RateSemantic.ACTIVITY_RATE,
                key="mql_to_s0",
                description="MQL→S0 activity conversion",
            ))

    def load_close_timing_curve(self, close_rate_dist: dict) -> None:
        """Load the 9-month close rate distribution as a timing distribution."""
        curve = [
            float(close_rate_dist.get(f"month_{i}", 0.0))
            for i in range(1, 10)
        ]
        total = sum(curve)
        if total > 0:
            # Normalize to sum to 1.0
            curve = [v / total for v in curve]
        self.register(RateDefinition(
            value=0.0,  # Not a single value — use get_timing_curve() instead
            source="config",
            semantic=RateSemantic.TIMING_DISTRIBUTION,
            key="close_timing_curve",
            description="9-month S2→Close timing distribution",
        ))
        # Store the actual curve as a private attribute
        self._timing_curves = getattr(self, "_timing_curves", {})
        self._timing_curves["close_timing_curve"] = curve

    def get_timing_curve(self, key: str = "close_timing_curve") -> list[float]:
        """Get a timing distribution curve (list of floats summing to 1.0)."""
        curves = getattr(self, "_timing_curves", {})
        if key not in curves:
            raise RateNotFoundError(f"Timing curve '{key}' not registered")
        # Verify it's actually a timing distribution
        if key in self._rates and self._rates[key].semantic != RateSemantic.TIMING_DISTRIBUTION:
            raise SemanticMismatchError(
                f"'{key}' is not a timing distribution"
            )
        return curves[key]

    # ------------------------------------------------------------------
    # Full config loading
    # ------------------------------------------------------------------

    def load_from_config(self, assumptions: dict) -> None:
        """Bulk load rates from assumptions.yaml dict.

        Loads stage win rates, funnel rates, and close timing curve.
        """
        forecast_cfg = assumptions.get("forecast", {})
        stage_conversion = forecast_cfg.get("stage_conversion", {})
        if stage_conversion:
            self.load_stage_win_rates(stage_conversion)

        funnel_cfg = assumptions.get("funnel", {})
        if funnel_cfg:
            self.load_funnel_rates(funnel_cfg)

        close_dist = assumptions.get("close_rate_distribution", {})
        if close_dist:
            self.load_close_timing_curve(close_dist)

        logger.info("RateRegistry loaded %d rates from config", len(self._rates))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_default_registry: Optional[RateRegistry] = None


def get_default_registry() -> RateRegistry:
    """Get or create the default rate registry, loaded from assumptions.yaml."""
    global _default_registry
    if _default_registry is None:
        _default_registry = RateRegistry()
        try:
            assumptions = load_yaml_resource("assumptions.yaml")
            _default_registry.load_from_config(assumptions)
        except Exception as e:
            logger.warning("Could not load default rate registry: %s", e)
    return _default_registry


def reset_default_registry() -> None:
    """Reset the singleton (for testing)."""
    global _default_registry
    _default_registry = None

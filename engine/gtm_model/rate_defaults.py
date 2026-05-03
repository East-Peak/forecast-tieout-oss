"""Shared registry-backed default rates for legacy model modules."""

from __future__ import annotations

import logging

from .rate_registry import (
    RateNotFoundError,
    RateSemantic,
    SemanticMismatchError,
    get_default_registry,
)

logger = logging.getLogger(__name__)

_FUNNEL_RATE_DEFAULTS = {
    "mql_to_s0": 0.15,
    "s0_to_s1": 0.55,
    "s1_to_s2": 0.25,
    "s2_to_s3": 0.40,
    "s3_to_s4": 0.50,
    "s4_to_s5": 0.60,
    "s5_to_won": 0.80,
}

_FUNNEL_SEMANTICS = {
    "mql_to_s0": RateSemantic.ACTIVITY_RATE,
    "s0_to_s1": RateSemantic.SEQUENTIAL_TRANSITION,
    "s1_to_s2": RateSemantic.SEQUENTIAL_TRANSITION,
    "s2_to_s3": RateSemantic.SEQUENTIAL_TRANSITION,
    "s3_to_s4": RateSemantic.SEQUENTIAL_TRANSITION,
    "s4_to_s5": RateSemantic.SEQUENTIAL_TRANSITION,
    "s5_to_won": RateSemantic.SEQUENTIAL_TRANSITION,
}

_STAGE_WIN_DEFAULTS = {
    "stage_s2_win": 0.18,
    "stage_s3_win": 0.42,
    "stage_s4_win": 0.58,
    "stage_s5_win": 0.61,
}


def _registry_value(key: str, semantic: RateSemantic, default: float) -> float:
    """Read a value from the default registry, falling back safely."""
    try:
        return float(get_default_registry().get_value(key, semantic))
    except (RateNotFoundError, SemanticMismatchError, TypeError, ValueError) as exc:
        logger.debug("Falling back to static default for %s: %s", key, exc)
        return default


def get_default_funnel_rates() -> dict[str, float]:
    """Return the canonical sequential funnel defaults."""
    return {
        key: _registry_value(key, _FUNNEL_SEMANTICS[key], default)
        for key, default in _FUNNEL_RATE_DEFAULTS.items()
    }


def get_default_stage_win_rates() -> dict[str, float]:
    """Return canonical all-inclusive stage-to-won defaults."""
    registry_keys = {
        "S2": "stage_s2_win",
        "S3": "stage_s3_win",
        "S4": "stage_s4_win",
        "S5": "stage_s5_win",
    }
    return {
        stage: _registry_value(
            registry_key,
            RateSemantic.LIFETIME_PROBABILITY,
            _STAGE_WIN_DEFAULTS[registry_key],
        )
        for stage, registry_key in registry_keys.items()
    }


def get_default_forecast_stage_conversion() -> dict[str, float]:
    """Return sequential stage-to-won defaults used by the forecast module."""
    funnel = get_default_funnel_rates()
    s5 = funnel["s5_to_won"]
    s4 = funnel["s4_to_s5"] * s5
    s3 = funnel["s3_to_s4"] * s4
    s2 = funnel["s2_to_s3"] * s3
    return {
        "S2": s2,
        "S3": s3,
        "S4": s4,
        "S5": s5,
    }


def get_default_bottleneck_benchmark_rates() -> dict[str, float]:
    """Return bottleneck benchmark rates keyed by stage transition label."""
    funnel = get_default_funnel_rates()
    return {
        "S0→S1": funnel["s0_to_s1"],
        "S1→S2": funnel["s1_to_s2"],
        "S2→S3": funnel["s2_to_s3"],
        "S3→S4": funnel["s3_to_s4"],
        "S4→S5": funnel["s4_to_s5"],
        "S5→Won": funnel["s5_to_won"],
    }

"""Every rate once: each has a single definition, a sample and a source."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

FITTED = "fitted"
ENTERED = "entered"
DEFAULT = "default"


@dataclass(frozen=True)
class Rate:
    name: str
    value: Decimal
    definition: str
    numerator: str
    denominator: str
    cohort: str
    horizon: str
    sample_size: int
    source: str  # FITTED, ENTERED or DEFAULT
    low95: float | None = None
    high95: float | None = None
    label: str | None = None  # a short name for a screen row, where the name is a code


class RateBook:
    """An ordered registry that refuses a second definition of a name."""

    def __init__(self) -> None:
        self._rates: dict[str, Rate] = {}

    def add(self, rate: Rate) -> Rate:
        if rate.name in self._rates:
            raise ValueError(f"rate '{rate.name}' is already defined")
        self._rates[rate.name] = rate
        return rate

    def __getitem__(self, name: str) -> Rate:
        return self._rates[name]

    def __contains__(self, name: str) -> bool:
        return name in self._rates

    def __iter__(self):
        return iter(self._rates.values())


# What a rate's value is, so a screen can say it right: a share (shown as a percent), dollars,
# or a plain number (its definition says what it counts). Keyed by the name before any ":".
RATE_UNITS = {
    **dict.fromkeys(
        (
            "win_within_horizon",
            "new_pipeline_win_rate",
            "stage_probability",
            "ramp_weight",
            "attrition_per_ae_month",
            "capacity_min_staffing_variation",
            "capacity_min_improvement",
        ),
        "share",
    ),
    **dict.fromkeys(
        (
            "mean_won_arr",
            "mean_created_arr",
            "trailing_bookings_per_day",
            "created_arr_per_day",
            "loaded_cost_per_ae_month",
        ),
        "dollars",
    ),
    **dict.fromkeys(
        (
            "created_deals_per_day",
            "created_deals_per_ramped_ae_month",
            "median_won_cycle_days",
            "horizon_days",
            "smoothing_pseudo_observations",
            "min_timing_samples",
            "trailing_days",
            "recency_months",
            "lever_cap_multiple",
            "simulation_draws",
            "programme_cost_per_dollar_of_pipeline",
            "programme_ramp_months",
            "capacity_min_folds",
            "days_per_ae_month",
        ),
        "number",
    ),
}


def rate_unit(name: str) -> str:
    key = name.split(":")[0]
    if key not in RATE_UNITS:
        raise KeyError(f"no unit declared for rate '{name}'")
    return RATE_UNITS[key]


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n == 0:
        return (0.0, 1.0)
    return wilson_interval(successes / n, n, z)


def wilson_interval(p: float, n: float, z: float = 1.959964) -> tuple[float, float]:
    """Wilson interval for an estimate ``p`` worth ``n`` (possibly effective,
    non-integer) binomial observations."""
    if n <= 0:
        return (0.0, 1.0)
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))

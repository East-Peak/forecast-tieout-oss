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

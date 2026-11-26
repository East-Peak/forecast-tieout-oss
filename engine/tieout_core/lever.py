"""One lever, solved through the forward function: new pipeline required.

The forward function is linear in added pipeline, so the solve is a single
division; the answer is then put back through the forward function and the
result is reported, so the agreement is checked rather than assumed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

COVERED = "already covered"
FEASIBLE = "feasible"
UNREACHABLE = "unreachable within bounds"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class LeverResult:
    outcome: str
    required: Decimal | None  # added pipeline needed; None when no amount can help
    cap: Decimal
    target: Decimal
    base: Decimal  # the forecast with nothing added
    achieved: Decimal  # forward(required), or forward(cap) when unreachable

    @property
    def headline(self) -> str:
        if self.outcome == FEASIBLE:
            return f"feasible: ${self.required:,.2f}"
        return self.outcome


def solve_added_pipeline(
    forward: Callable[[Decimal], Decimal], target: Decimal, cap: Decimal
) -> LeverResult:
    base = forward(Decimal(0))
    if base >= target:
        return LeverResult(COVERED, Decimal(0), cap, target, base, base)
    at_cap = forward(cap) if cap > 0 else base
    slope = (at_cap - base) / cap if cap > 0 else Decimal(0)
    if slope <= 0:
        return LeverResult(UNREACHABLE, None, cap, target, base, at_cap)
    required = ((target - base) / slope).quantize(CENT, rounding=ROUND_CEILING)
    if required > cap:
        return LeverResult(UNREACHABLE, required, cap, target, base, at_cap)
    return LeverResult(FEASIBLE, required, cap, target, base, forward(required))

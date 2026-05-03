"""Pure-function port of `_get_runtime_funnel_rates()`.

Computes per-stage conversion rates from raw deal + transition data,
with provenance metadata for the rate registry.

Legacy implementation (engine/gtm_model/tieout/runtime/rates.py:232,315)
combines multiple sources: cohort-based warehouse queries, fallback to config
defaults, and per-stage observed rates. Per ARCHITECTURE.md, this pure function
computes the observed component from raw data; backends override with
source-specific fast paths if available (Concern B′).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from engine.connectors.interface import Deal, StageTransition


@dataclass
class FunnelRates:
    """Stage-to-stage conversion rates with provenance."""

    # rates[(from_stage, to_stage)] = 0..1
    transitions: dict[tuple[str, str], float] = field(default_factory=dict)
    sample_sizes: dict[tuple[str, str], int] = field(default_factory=dict)
    source: Optional[str] = None  # filled in by backend
    method: str = "observed_per_deal"


def compute_funnel_rates(
    deals: Iterable[Deal],
    stage_history: Iterable[StageTransition],
) -> FunnelRates:
    """Compute observed stage-to-stage conversion rates.

    For each pair (S_n, S_{n+1}), counts:
    - deals that ever entered S_n
    - subset that progressed to S_{n+1}
    Rate = progressed / entered.

    Args:
        deals: All deals.
        stage_history: All stage transitions.

    Returns:
        FunnelRates with per-pair conversion rates and sample sizes.
        Empty when there's insufficient transition data.
    """
    transitions = list(stage_history)

    # Track which stages each deal ever reached
    stages_per_deal: dict[str, set[str]] = defaultdict(set)
    for t in transitions:
        if t.from_stage:
            stages_per_deal[t.deal_id].add(t.from_stage)
        if t.to_stage:
            stages_per_deal[t.deal_id].add(t.to_stage)

    # For each adjacent pair, count "entered S_n" and "advanced to S_{n+1}"
    stage_order = ["S0", "S1", "S2", "S3", "S4", "S5", "Won"]
    rates: dict[tuple[str, str], float] = {}
    samples: dict[tuple[str, str], int] = {}

    for i in range(len(stage_order) - 1):
        from_stage = stage_order[i]
        to_stage = stage_order[i + 1]
        entered = sum(1 for stages in stages_per_deal.values() if from_stage in stages)
        advanced = sum(
            1 for stages in stages_per_deal.values()
            if from_stage in stages and to_stage in stages
        )
        if entered > 0:
            rates[(from_stage, to_stage)] = advanced / entered
            samples[(from_stage, to_stage)] = entered

    return FunnelRates(
        transitions=rates,
        sample_sizes=samples,
        method="observed_per_deal",
    )

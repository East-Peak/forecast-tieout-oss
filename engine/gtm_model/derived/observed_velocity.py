"""Pure-function ports of velocity-related observed metrics.

Ports of:
- `_get_observed_decay_curve()` — pipeline decay curve
- `_get_s2_to_won_rate()` — composite S2-to-Won conversion
- `_get_rolling_s2_to_won_rate()` — rolling 90-day S2-to-Won
- `_get_stage_velocity_days()` — average days in each stage
- `_get_stage_win_rates()` — per-stage win probability

Legacy implementations live in PlanningTieout (engine/gtm_model/tieout/
runtime/observed.py / rates.py / velocity.py) and are heavily intertwined
with cached source-system aggregates. The pure-function port here uses
raw deal + stage-history input.

NOTE: this module currently provides the *shape* and a basic implementation
adequate for backends that don't override. SnowflakeBackend will likely
override these with SQL pre-aggregation with SQL pre-aggregation. The runtime wiring
modules to consume `ProfileBackend.compute_*()` which delegates here for
default Python implementations.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional

from engine.connectors.interface import Deal, StageTransition


@dataclass
class VelocityProfile:
    """Aggregate velocity metrics for the engine's runtime."""

    s2_to_won_rate: Optional[float] = None  # 0..1
    rolling_s2_to_won_rate: Optional[float] = None
    stage_velocity_days: dict[str, float] = field(default_factory=dict)  # stage -> avg days
    stage_win_rates: dict[str, float] = field(default_factory=dict)  # stage -> 0..1
    decay_curve: list[float] = field(default_factory=list)  # decay rate per day


def compute_observed_velocity(
    deals: Iterable[Deal],
    stage_history: Iterable[StageTransition],
    as_of: date,
    rolling_lookback_days: int = 90,
) -> VelocityProfile:
    """Compute velocity metrics from raw deal + transition data.

    Args:
        deals: All deals (open + closed).
        stage_history: All stage transitions for those deals.
        as_of: Reference date for "rolling" calculations.
        rolling_lookback_days: Window for rolling S2-to-Won.

    Returns:
        VelocityProfile with the 5 metrics. Fields default to None / {}
        / [] when there's insufficient data.
    """
    deals = list(deals)
    transitions = list(stage_history)

    profile = VelocityProfile()

    # ── S2-to-Won rate (composite over all closed-since-S2 deals) ──
    s2_entered_ids = {
        t.deal_id for t in transitions if t.to_stage == "S2"
    }
    if s2_entered_ids:
        won = sum(
            1 for d in deals
            if d.id in s2_entered_ids and d.is_won
        )
        closed = sum(
            1 for d in deals
            if d.id in s2_entered_ids and d.is_closed
        )
        if closed > 0:
            profile.s2_to_won_rate = won / closed

    # ── Rolling S2-to-Won (lookback window) ──
    rolling_cutoff = as_of - timedelta(days=rolling_lookback_days)
    recent_s2_ids = {
        t.deal_id for t in transitions
        if t.to_stage == "S2" and t.transition_date.date() >= rolling_cutoff
    }
    if recent_s2_ids:
        recent_won = sum(
            1 for d in deals if d.id in recent_s2_ids and d.is_won
        )
        recent_closed = sum(
            1 for d in deals if d.id in recent_s2_ids and d.is_closed
        )
        if recent_closed > 0:
            profile.rolling_s2_to_won_rate = recent_won / recent_closed

    # ── Stage velocity (avg days in each stage before transitioning) ──
    stage_durations: dict[str, list[int]] = defaultdict(list)
    transitions_by_deal: dict[str, list[StageTransition]] = defaultdict(list)
    for t in transitions:
        transitions_by_deal[t.deal_id].append(t)

    for deal_id, ts in transitions_by_deal.items():
        ts_sorted = sorted(ts, key=lambda x: x.transition_date)
        for i, t in enumerate(ts_sorted):
            if t.to_stage in ("Won", "Lost"):
                continue
            # Find the next transition out of this stage
            for next_t in ts_sorted[i + 1:]:
                if next_t.from_stage == t.to_stage:
                    days = (next_t.transition_date - t.transition_date).days
                    if days >= 0:
                        stage_durations[t.to_stage].append(days)
                    break

    for stage, durations in stage_durations.items():
        if durations:
            profile.stage_velocity_days[stage] = sum(durations) / len(durations)

    # ── Stage win rates (per-stage probability of reaching Won) ──
    stage_won_counts: dict[str, int] = defaultdict(int)
    stage_seen_counts: dict[str, int] = defaultdict(int)
    deals_won = {d.id for d in deals if d.is_won}
    deals_closed = {d.id for d in deals if d.is_closed}
    for deal_id, ts in transitions_by_deal.items():
        if deal_id not in deals_closed:
            continue
        seen_stages = {t.to_stage for t in ts}
        for stage in ("S0", "S1", "S2", "S3", "S4", "S5"):
            if stage in seen_stages:
                stage_seen_counts[stage] += 1
                if deal_id in deals_won:
                    stage_won_counts[stage] += 1

    for stage in stage_seen_counts:
        if stage_seen_counts[stage] > 0:
            profile.stage_win_rates[stage] = (
                stage_won_counts[stage] / stage_seen_counts[stage]
            )

    # ── Decay curve (left as TODO — legacy uses pipeline
    # rollforward simulation; pure port needs the full simulation) ──
    profile.decay_curve = []

    return profile

"""
Trajectory Engine: Capacity-driven pipeline creation from observed reality.

Derives pipeline creation from actual AE roster, observed productivity,
trailing MQL volume, and trend extrapolation. This replaces config-driven
S1 targets with "where are we actually headed?"

Architectural decision: docs/decisions/001-two-scenario-architecture.md
Architectural decision: docs/decisions/003-ae-productivity-drives-pipeline.md
Architectural decision: docs/decisions/004-hiring-velocity-not-plan-headcount.md
Architectural decision: docs/decisions/006-ewma-trend-extrapolation.md
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from .rate_defaults import get_default_funnel_rates

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryProvenance:
    """Provenance for the trajectory pipeline creation vector."""
    observed_ae_productivity: float = 0.0  # S0s per ramped-AE-month
    trailing_ramped_ae_months: float = 0.0
    trailing_ae_sourced_s0s: int = 0
    roster_snapshot_size: int = 0
    incoming_hires: int = 0
    hiring_velocity_per_month: float = 0.0
    include_planned: bool = True
    planned_slots_excluded: int = 0
    extrapolate_hiring: bool = True
    projected_hires_added: int = 0
    annual_attrition_rate: float = 0.0
    mql_ewma_level: float = 0.0
    mql_growth_rate: float = 0.0
    mql_growth_cap_applied: bool = False
    ewma_alpha: float = 0.3
    avg_deal_size: float = 300_000.0
    fallback_used: bool = False
    fallback_reason: str = ""
    ramp_curve_source: str = "config"
    ramp_curve_reason: str = ""
    ramp_curve_by_segment: dict[str, dict[str, float]] = field(default_factory=dict)
    ramp_curve_sample_sizes: dict[str, dict[str, float]] = field(default_factory=dict)
    mql_month_sources: list = field(default_factory=list)
    mql_trend_horizon: int = 3
    mql_actuals_count: int = 0

    def to_dict(self, exclude: set | None = None) -> dict:
        """Serialize all fields to a dict, optionally excluding named fields."""
        from dataclasses import asdict
        d = asdict(self)
        if exclude:
            for key in exclude:
                d.pop(key, None)
        return d


@dataclass
class TrajectoryResult:
    """Output of the trajectory pipeline creation engine."""
    monthly_s2_creation: list[float]  # 12-month S2 pipeline in dollars
    monthly_ae_s2_creation: list[float]  # AE self-gen S2 pipeline in dollars
    monthly_mql_s2_creation: list[float]  # Marketing / SDR S2 pipeline in dollars
    monthly_ae_count: list[float]     # Effective AE count per month
    monthly_mql_volume: list[float]   # Projected MQL volume per month
    provenance: TrajectoryProvenance = field(default_factory=TrajectoryProvenance)


# ---------------------------------------------------------------------------
# AE Pipeline Creation
# ---------------------------------------------------------------------------


def _month_start_for_offset(as_of: date, month_idx: int) -> date:
    """Return the first day of the projected calendar month."""
    return date(
        as_of.year + (as_of.month + month_idx - 1) // 12,
        (as_of.month + month_idx - 1) % 12 + 1,
        1,
    )


def _month_end(month_start: date) -> date:
    """Return the last day of the month containing `month_start`."""
    next_month = date(
        month_start.year + (month_start.month // 12),
        (month_start.month % 12) + 1,
        1,
    )
    return next_month - timedelta(days=1)


def _active_month_fraction(start_dt: date, month_start: date, month_end: date) -> float:
    """Return the fraction of a calendar month the AE is active."""
    if start_dt > month_end:
        return 0.0
    active_start = max(start_dt, month_start)
    active_days = (month_end - active_start).days + 1
    total_days = (month_end - month_start).days + 1
    if total_days <= 0:
        return 0.0
    return max(0.0, min(1.0, active_days / total_days))


def _serialize_ramp_curve(curve_by_segment: dict[str, dict[int, float]]) -> dict[str, dict[str, float]]:
    """Convert numeric ramp buckets to stable month_N keys for provenance."""
    serialized: dict[str, dict[str, float]] = {}
    for segment, curve in (curve_by_segment or {}).items():
        serialized[str(segment)] = {
            f"month_{int(bucket)}": float(value)
            for bucket, value in sorted((curve or {}).items())
        }
    return serialized


def _resolve_ramp_factor(
    segment: str,
    months_since_start: int,
    ramp_curves_by_segment: Optional[dict[str, dict[int, float]]] = None,
) -> float:
    """Resolve a ramp factor from observed overrides first, then config defaults."""
    from .roster import _get_ramp_factor, _normalize_segment

    normalized = _normalize_segment(segment)
    curve = (ramp_curves_by_segment or {}).get(normalized)
    if curve:
        key = months_since_start + 1
        if key in curve:
            return float(curve[key])
        max_key = max(curve.keys())
        if key > max_key:
            return float(curve[max_key])
        return 0.0
    return _get_ramp_factor(normalized, months_since_start)

def _build_projected_hire_starts(
    last_confirmed_start: date,
    hiring_velocity: float,
    months_elapsed: int,
    segment: str = "enterprise",
) -> list[tuple[date, str]]:
    """Build cumulative projected hire starts without backdating.

    Hires are allocated month by month after the last confirmed start date using
    the observed hires/month velocity. Multiple hires in the same month are
    represented by repeated mid-month dates.
    """
    if hiring_velocity <= 0 or months_elapsed <= 0:
        return []

    projected: list[tuple[date, str]] = []
    anchor_year = last_confirmed_start.year
    anchor_month = last_confirmed_start.month

    for month_offset in range(1, months_elapsed + 1):
        month_index = anchor_month - 1 + month_offset
        year = anchor_year + month_index // 12
        month = month_index % 12 + 1
        cumulative = int(math.floor(hiring_velocity * month_offset + 1e-9))
        previous = int(math.floor(hiring_velocity * (month_offset - 1) + 1e-9))
        hires_this_month = max(cumulative - previous, 0)
        hire_date = date(year, month, 15)
        projected.extend((hire_date, segment) for _ in range(hires_this_month))

    return projected


def compute_ae_pipeline_creation(
    roster: dict,
    as_of: date,
    months: int = 12,
    observed_ae_productivity: Optional[float] = None,
    trailing_ae_sourced_s0s: int = 0,
    trailing_ramped_ae_months: float = 0.0,
    annual_attrition_rate: float = 0.15,
    avg_deal_size: float = 300_000.0,
    s0_to_s1: Optional[float] = None,
    s1_to_s2: Optional[float] = None,
    ramp_curves_by_segment: Optional[dict[str, dict[int, float]]] = None,
    include_planned: bool = True,
    extrapolate_hiring: bool = True,
) -> tuple[list[float], list[float], TrajectoryProvenance]:
    """Compute monthly AE self-gen S2 pipeline from roster and observed productivity.

    Uses existing _get_ramp_factor from roster.py (1-indexed convention).

    Args:
        roster: Dict with 'active', 'incoming', 'planned' lists from roster.yaml.
        as_of: Projection start date.
        months: Number of months to project.
        observed_ae_productivity: S0s per ramped-AE-month (override).
            If None, computed from trailing_ae_sourced_s0s / trailing_ramped_ae_months.
        trailing_ae_sourced_s0s: AE-sourced S0 count in trailing period.
        trailing_ramped_ae_months: Sum of ramp factors for AEs in trailing period.
        annual_attrition_rate: Annual AE attrition rate (default 15%).
        avg_deal_size: Average S2 deal size in dollars.
        s0_to_s1: S0→S1 conversion rate.
        s1_to_s2: S1→S2 conversion rate.

    Returns:
        (monthly_s2_dollars, monthly_ae_count, provenance)
    """
    from .roster import _months_since

    provenance = TrajectoryProvenance(
        annual_attrition_rate=annual_attrition_rate,
        avg_deal_size=avg_deal_size,
    )
    funnel_rates = get_default_funnel_rates()
    s0_to_s1 = funnel_rates["s0_to_s1"] if s0_to_s1 is None else s0_to_s1
    s1_to_s2 = funnel_rates["s1_to_s2"] if s1_to_s2 is None else s1_to_s2

    # --- Compute observed productivity ---
    if observed_ae_productivity is not None:
        productivity = observed_ae_productivity
    elif trailing_ramped_ae_months > 0:
        productivity = trailing_ae_sourced_s0s / trailing_ramped_ae_months
    else:
        # Fallback: no observed data — use 0 (will trigger fallback in caller)
        productivity = 0.0
        provenance.fallback_used = True
        provenance.fallback_reason = "no_trailing_ae_data"

    provenance.observed_ae_productivity = productivity
    provenance.trailing_ramped_ae_months = trailing_ramped_ae_months
    provenance.trailing_ae_sourced_s0s = trailing_ae_sourced_s0s

    # --- Build AE timeline ---
    active = roster.get("active", [])
    incoming = roster.get("incoming", [])
    planned = roster.get("planned", [])

    provenance.roster_snapshot_size = len(active)
    provenance.incoming_hires = len(incoming)

    # Compute hiring velocity from recent active starts plus confirmed incoming hires.
    # Planned reqs stay out of the trajectory path on purpose.
    six_months_ago = as_of - timedelta(days=180)
    recent_hires = 0
    for ae in active:
        start_str = ae.get("start_date", ae.get("employee_start_date", ""))
        if not start_str:
            continue
        try:
            start = date.fromisoformat(str(start_str)[:10])
            if six_months_ago <= start <= as_of:
                recent_hires += 1
        except (ValueError, TypeError):
            continue
    for ae in incoming:
        start_str = ae.get("start_date", ae.get("expected_start", ""))
        if not start_str:
            continue
        try:
            start = date.fromisoformat(str(start_str)[:10])
            if six_months_ago <= start <= as_of:
                recent_hires += 1
        except (ValueError, TypeError):
            continue

    hiring_velocity = recent_hires / 6.0  # hires per month
    provenance.hiring_velocity_per_month = hiring_velocity
    provenance.include_planned = include_planned
    provenance.planned_slots_excluded = len(planned) if not include_planned else 0
    provenance.extrapolate_hiring = extrapolate_hiring
    if ramp_curves_by_segment:
        provenance.ramp_curve_by_segment = _serialize_ramp_curve(ramp_curves_by_segment)

    # --- Project each month ---
    monthly_s2 = []
    monthly_ae_count = []

    # All AEs with their start dates
    all_aes = []
    for ae in active:
        start_str = ae.get("start_date", ae.get("employee_start_date", ""))
        segment = ae.get("segment", "enterprise")
        if start_str:
            try:
                all_aes.append((date.fromisoformat(str(start_str)[:10]), segment))
            except (ValueError, TypeError):
                all_aes.append((as_of - timedelta(days=365), segment))  # assume tenured

    for ae in incoming:
        start_str = ae.get("start_date", ae.get("expected_start", ""))
        segment = ae.get("segment", "enterprise")
        if start_str:
            try:
                all_aes.append((date.fromisoformat(str(start_str)[:10]), segment))
            except (ValueError, TypeError):
                pass

    # Include planned roster slots to prevent trajectory cliff-off.
    # These are named reqs in roster.yaml with expected_start dates.
    # Without them, the trajectory artificially declines in later quarters.
    if include_planned:
        for ae in planned:
            start_str = ae.get("expected_start", ae.get("start_date", ""))
            segment = ae.get("segment", "enterprise")
            if start_str:
                try:
                    all_aes.append((date.fromisoformat(str(start_str)[:10]), segment))
                except (ValueError, TypeError):
                    pass

    # Determine when confirmed hires run out
    last_confirmed_start = as_of
    for start_dt, _ in all_aes:
        if start_dt > last_confirmed_start:
            last_confirmed_start = start_dt

    for month_idx in range(months):
        month_start = _month_start_for_offset(as_of, month_idx)
        month_end = _month_end(month_start)

        # Add projected hires beyond confirmed (hiring velocity)
        projected_new_hires = []
        if extrapolate_hiring and month_start > last_confirmed_start and hiring_velocity > 0:
            months_beyond = ((month_start.year - last_confirmed_start.year) * 12 +
                           month_start.month - last_confirmed_start.month)
            projected_new_hires = _build_projected_hire_starts(
                last_confirmed_start=last_confirmed_start,
                hiring_velocity=hiring_velocity,
                months_elapsed=months_beyond,
            )

        # Compute effective AEs this month (with ramp and attrition)
        month_all_aes = all_aes + projected_new_hires
        total_ramp_weighted = 0.0

        for start_dt, segment in month_all_aes:
            if start_dt > month_end:
                continue  # Not started yet
            active_fraction = _active_month_fraction(start_dt, month_start, month_end)
            if active_fraction <= 0.0:
                continue
            months_active = _months_since(start_dt, month_end)
            ramp = _resolve_ramp_factor(
                segment,
                months_active,
                ramp_curves_by_segment=ramp_curves_by_segment,
            )
            total_ramp_weighted += ramp * active_fraction

        # Apply attrition to the pool
        months_from_now = month_idx
        retention_factor = (1.0 - annual_attrition_rate / 12.0) ** months_from_now
        effective_aes = total_ramp_weighted * retention_factor

        monthly_ae_count.append(effective_aes)

        # Compute S0 creation from AE productivity
        monthly_s0s = productivity * effective_aes

        # Convert S0 → S1 → S2 using sequential rates, then to dollars
        monthly_s2_deals = monthly_s0s * s0_to_s1 * s1_to_s2
        monthly_s2_dollars = monthly_s2_deals * avg_deal_size

        monthly_s2.append(monthly_s2_dollars)
        provenance.projected_hires_added = max(
            provenance.projected_hires_added, len(projected_new_hires)
        )

    return monthly_s2, monthly_ae_count, provenance


# ---------------------------------------------------------------------------
# EWMA Trend Extrapolation
# ---------------------------------------------------------------------------

def compute_ewma(values: list[float], alpha: float = 0.3) -> float:
    """Compute exponentially weighted moving average.

    More recent values get higher weight.
    """
    if not values:
        return 0.0
    ewma_val = values[0]
    for v in values[1:]:
        ewma_val = alpha * v + (1 - alpha) * ewma_val
    return ewma_val


def compute_growth_rate(
    monthly_values: list[float],
    cap: float = 0.10,
) -> float:
    """Compute monthly growth rate from trailing data via linear regression.

    Returns percentage growth rate (slope / level), capped at ±cap.
    """
    if len(monthly_values) < 2:
        return 0.0

    n = len(monthly_values)
    x_mean = (n - 1) / 2.0
    y_mean = sum(monthly_values) / n

    numerator = sum((i - x_mean) * (monthly_values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0 or y_mean == 0:
        return 0.0

    slope = numerator / denominator
    growth_rate = slope / max(abs(y_mean), 1.0)

    # Cap
    capped = max(-cap, min(cap, growth_rate))
    return capped


def compute_ewma_projection(
    weekly_values: list[float],
    months: int = 12,
    alpha: float = 0.3,
    trend_monthly_values: Optional[list[float]] = None,
    growth_cap: float = 0.10,
    trend_horizon: int = 3,
    monthly_actuals: Optional[list[Optional[float]]] = None,
    partial_month_index: Optional[int] = None,
) -> tuple[list[float], dict]:
    """Project a metric forward using EWMA level + trend extrapolation.

    Growth rate decays linearly to zero over ``trend_horizon`` months,
    then the projection flat-carries.  This prevents compound growth
    from producing unrealistic spikes in MQL / PLG projections.

    Args:
        weekly_values: Trailing weekly observations (for current level).
        months: Number of months to project.
        alpha: EWMA smoothing parameter.
        trend_monthly_values: Trailing monthly values (for trend slope).
            If None, derives from weekly_values by grouping into 4-week chunks.
        growth_cap: Maximum monthly growth rate (±).
        trend_horizon: Number of months over which the growth rate decays
            linearly to zero.  After this horizon, the projection flat-carries
            at the level reached.  Default 3.

    Returns:
        (projected_monthly_values, metadata)
    """
    metadata = {
        "ewma_alpha": alpha,
        "growth_cap": growth_cap,
        "growth_cap_applied": False,
        "weekly_points": len(weekly_values),
        "monthly_points": 0,
    }

    # Current level from EWMA
    if len(weekly_values) >= 8:
        level = compute_ewma(weekly_values, alpha)
        # Convert weekly to monthly (4.33 weeks/month)
        monthly_level = level * 4.33
    elif weekly_values:
        # Insufficient for EWMA — use simple average
        level = sum(weekly_values) / len(weekly_values)
        monthly_level = level * 4.33
        metadata["fallback"] = "simple_average"
    else:
        return [0.0] * months, metadata

    metadata["ewma_level"] = level
    metadata["monthly_level"] = monthly_level

    # Trend from monthly values
    if trend_monthly_values is None and len(weekly_values) >= 16:
        # Group weekly into 4-week months
        trend_monthly_values = []
        for i in range(0, len(weekly_values) - 3, 4):
            chunk = weekly_values[i:i + 4]
            trend_monthly_values.append(sum(chunk))

    if trend_monthly_values and len(trend_monthly_values) >= 4:
        growth_rate = compute_growth_rate(trend_monthly_values, cap=growth_cap)
        metadata["monthly_points"] = len(trend_monthly_values)
        metadata["raw_growth_rate"] = growth_rate
        if abs(growth_rate) >= growth_cap:
            metadata["growth_cap_applied"] = True
    else:
        growth_rate = 0.0  # Flat carry-forward
        metadata["fallback_trend"] = "flat_carry_forward"

    metadata["growth_rate"] = growth_rate

    # Project forward with decaying growth + actuals splicing
    metadata["trend_horizon"] = trend_horizon
    effective_growth_rates = []
    month_sources = []
    projected = []
    anchor = monthly_level  # Default anchor is EWMA level

    # Find the last actual to use as anchor for projected months
    if monthly_actuals:
        for i in range(min(len(monthly_actuals), months) - 1, -1, -1):
            if monthly_actuals[i] is not None:
                anchor = monthly_actuals[i]
                break

    metadata["anchor_value"] = anchor

    projected_month_counter = 0  # Counts only projected months for decay

    for n in range(months):
        has_actual = (
            monthly_actuals is not None
            and n < len(monthly_actuals)
            and monthly_actuals[n] is not None
        )

        if has_actual:
            val = monthly_actuals[n]
            effective_growth_rates.append(0.0)
            if partial_month_index is not None and n == partial_month_index:
                month_sources.append("partial_actual")
            else:
                month_sources.append("actual")
        else:
            # Decay based on how many projected months we've emitted
            if projected_month_counter < trend_horizon:
                decay = 1.0 - (projected_month_counter / trend_horizon)
                effective_rate = growth_rate * decay
            else:
                effective_rate = 0.0
            effective_growth_rates.append(effective_rate)
            month_sources.append("projected")

            # Anchor from previous value (last actual or last projected)
            prev = projected[-1] if projected else anchor
            val = prev * (1 + effective_rate)
            projected_month_counter += 1

        projected.append(max(0.0, val))

    metadata["effective_growth_rates"] = effective_growth_rates
    if monthly_actuals is not None:
        metadata["month_sources"] = month_sources
        metadata["actuals_count"] = sum(1 for s in month_sources if s in ("actual", "partial_actual"))

    return projected, metadata


# ---------------------------------------------------------------------------
# Full Trajectory Engine
# ---------------------------------------------------------------------------

def build_trajectory_pipeline_creation(
    roster: dict,
    as_of: date,
    months: int = 12,
    observed_ae_productivity: Optional[float] = None,
    trailing_ae_sourced_s0s: int = 0,
    trailing_ramped_ae_months: float = 0.0,
    trailing_mql_weekly: Optional[list[float]] = None,
    trailing_mql_monthly: Optional[list[float]] = None,
    annual_attrition_rate: float = 0.15,
    avg_deal_size: float = 300_000.0,
    mql_to_s0: Optional[float] = None,
    s0_to_s1: Optional[float] = None,
    s1_to_s2: Optional[float] = None,
    ewma_alpha: float = 0.3,
    growth_cap: float = 0.10,
    plg_quarterly_targets: Optional[dict] = None,
    ramp_curves_by_segment: Optional[dict[str, dict[int, float]]] = None,
    ramp_curve_source: str = "config",
    ramp_curve_reason: str = "",
    ramp_curve_sample_sizes: Optional[dict[str, dict[str, float]]] = None,
    include_planned: bool = True,
    extrapolate_hiring: bool = True,
    monthly_mql_actuals: Optional[list] = None,
    mql_partial_month_index: Optional[int] = None,
) -> TrajectoryResult:
    """Build the full trajectory pipeline creation vector.

    Combines:
    1. AE self-gen from roster × observed productivity × ramp
    2. Marketing/inbound MQL trend extrapolation
    3. PLG flat quarterly targets

    Args:
        roster: Roster dict with active/incoming/planned.
        as_of: Projection start date.
        months: Projection horizon (default 12).
        observed_ae_productivity: S0s per ramped-AE-month (or computed).
        trailing_ae_sourced_s0s: For computing productivity if not provided.
        trailing_ramped_ae_months: Ditto.
        trailing_mql_weekly: Weekly MQL counts for EWMA level.
        trailing_mql_monthly: Monthly MQL counts for trend.
        annual_attrition_rate: AE attrition (default 15%).
        avg_deal_size: Average S2 deal size.
        mql_to_s0: MQL→S0 conversion rate.
        s0_to_s1: S0→S1 conversion rate.
        s1_to_s2: S1→S2 conversion rate.
        ewma_alpha: EWMA smoothing parameter.
        growth_cap: Max monthly growth rate.
        plg_quarterly_targets: {quarter: dollars} for PLG (flat targets).

    Returns:
        TrajectoryResult with 12-month S2 pipeline creation vector.
    """
    funnel_rates = get_default_funnel_rates()
    mql_to_s0 = funnel_rates["mql_to_s0"] if mql_to_s0 is None else mql_to_s0
    s0_to_s1 = funnel_rates["s0_to_s1"] if s0_to_s1 is None else s0_to_s1
    s1_to_s2 = funnel_rates["s1_to_s2"] if s1_to_s2 is None else s1_to_s2

    # --- Stream 1: AE Self-Gen ---
    ae_s2, ae_counts, prov = compute_ae_pipeline_creation(
        roster=roster,
        as_of=as_of,
        months=months,
        observed_ae_productivity=observed_ae_productivity,
        trailing_ae_sourced_s0s=trailing_ae_sourced_s0s,
        trailing_ramped_ae_months=trailing_ramped_ae_months,
        annual_attrition_rate=annual_attrition_rate,
        avg_deal_size=avg_deal_size,
        s0_to_s1=s0_to_s1,
        s1_to_s2=s1_to_s2,
        ramp_curves_by_segment=ramp_curves_by_segment,
        include_planned=include_planned,
        extrapolate_hiring=extrapolate_hiring,
    )
    prov.ramp_curve_source = ramp_curve_source
    prov.ramp_curve_reason = ramp_curve_reason
    prov.ramp_curve_sample_sizes = dict(ramp_curve_sample_sizes or {})

    # --- Stream 2: Marketing/Inbound MQL ---
    if trailing_mql_weekly and len(trailing_mql_weekly) >= 4:
        mql_projected, mql_meta = compute_ewma_projection(
            weekly_values=trailing_mql_weekly,
            months=months,
            alpha=ewma_alpha,
            trend_monthly_values=trailing_mql_monthly,
            growth_cap=growth_cap,
            trend_horizon=0,  # Architectural decision: conservative flat-carry until back-testable
            monthly_actuals=monthly_mql_actuals,
            partial_month_index=mql_partial_month_index,
        )
        prov.mql_ewma_level = mql_meta.get("ewma_level", 0.0)
        prov.mql_growth_rate = mql_meta.get("growth_rate", 0.0)
        prov.mql_growth_cap_applied = mql_meta.get("growth_cap_applied", False)
        prov.ewma_alpha = ewma_alpha
        prov.mql_month_sources = mql_meta.get("month_sources", [])
        prov.mql_trend_horizon = mql_meta.get("trend_horizon", 3)
        prov.mql_actuals_count = mql_meta.get("actuals_count", 0)

        # Convert MQLs → S0 → S1 → S2 → dollars
        mql_s2 = [
            mql_count * mql_to_s0 * s0_to_s1 * s1_to_s2 * avg_deal_size
            for mql_count in mql_projected
        ]
    else:
        mql_projected = [0.0] * months
        mql_s2 = [0.0] * months
        if not prov.fallback_reason:
            prov.fallback_reason = "no_trailing_mql_data"

    # --- Stream 3: PLG (flat quarterly targets, no bottoms-up) ---
    plg_monthly = [0.0] * months
    # PLG is added at the scenario level from config, not here

    # --- Combine streams ---
    total_s2 = [ae + mql for ae, mql in zip(ae_s2, mql_s2)]

    return TrajectoryResult(
        monthly_s2_creation=total_s2,
        monthly_ae_s2_creation=ae_s2,
        monthly_mql_s2_creation=mql_s2,
        monthly_ae_count=ae_counts,
        monthly_mql_volume=mql_projected,
        provenance=prov,
    )

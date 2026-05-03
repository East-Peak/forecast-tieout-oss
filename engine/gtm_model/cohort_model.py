"""
Cohort Model: Pipeline Decay Curve

Takes monthly pipeline creation amounts and spreads them across future months
using a calibrated decay curve. Core of the "dotted stack into the future"
visualization for the Planning Tie-Out v2 app.

Key concepts:
- Decay curve: 9-bucket distribution of when pipeline created in a given month
  eventually books (month_1 = same month, month_2 = one month later, etc.)
- Cohort: all pipeline created in a single month
- Stacking: summing overlapping cohort tails into monthly total expected bookings
- Capacity ceiling: AE capacity caps what can close in any month; excess either
  pushes to next month or is lost

Usage:
    from gtm_model.cohort_model import project_bookings, load_decay_curve

    decay = load_decay_curve("config/assumptions.yaml")
    result = project_bookings(
        monthly_creation=[1_000_000, 1_200_000, 1_500_000],
        decay_curve=decay,
        monthly_capacity=[500_000] * 11,
    )
"""

from __future__ import annotations

from datetime import date
from typing import Optional
import yaml


# =============================================================================
# DECAY CURVE LOADING
# =============================================================================

def load_decay_curve(assumptions_path: str) -> list[float]:
    """Load the 9-bucket close rate distribution from assumptions.yaml.

    Reads the ``close_rate_distribution`` key (1-indexed: month_1 through
    month_9) and returns a 0-indexed list of floats.

    Args:
        assumptions_path: Absolute or relative path to assumptions.yaml.

    Returns:
        List of 9 floats summing to 1.0.
        Example: [0.16, 0.26, 0.17, 0.15, 0.11, 0.06, 0.04, 0.03, 0.02]
    """
    with open(assumptions_path, "r") as f:
        config = yaml.safe_load(f)

    dist = config["close_rate_distribution"]
    # Keys are month_1 … month_9 — extract in order
    curve = [dist[f"month_{i}"] for i in range(1, 10)]
    return curve


# =============================================================================
# COHORT SPREADING
# =============================================================================

def spread_cohort(
    pipeline_created: float,
    creation_month: int,
    decay_curve: list[float],
) -> list[float]:
    """Spread a single cohort's pipeline across future booking months.

    Args:
        pipeline_created: Dollar amount of pipeline created this month.
        creation_month: Index of the month pipeline was created (0-based).
            Used only by callers for stacking alignment; does not affect the
            spread values themselves.
        decay_curve: List of N bucket weights (must sum to 1.0).

    Returns:
        List of N floats representing expected bookings in each of the next
        N months (starting from creation_month).
    """
    return [pipeline_created * rate for rate in decay_curve]


# =============================================================================
# COHORT STACKING
# =============================================================================

def stack_cohorts(
    monthly_creation: list[float],
    decay_curve: list[float],
) -> list[float]:
    """Stack multiple cohorts into total expected monthly bookings.

    Each month's pipeline creation spawns a cohort that spreads bookings
    across the following N months (where N = len(decay_curve)). This function
    sums all cohort tails for each calendar month.

    Output length = len(monthly_creation) + len(decay_curve) - 1

    Args:
        monthly_creation: Pipeline created each month (list of dollar amounts).
        decay_curve: Close-rate distribution (9 buckets).

    Returns:
        List of expected bookings per month covering the full horizon.
    """
    n_months = len(monthly_creation)
    n_buckets = len(decay_curve)
    output_len = n_months + n_buckets - 1

    result = [0.0] * output_len

    for month_idx, pipeline in enumerate(monthly_creation):
        cohort = spread_cohort(pipeline, month_idx, decay_curve)
        for bucket_idx, booking in enumerate(cohort):
            result[month_idx + bucket_idx] += booking

    return result


# =============================================================================
# CAPACITY CEILING
# =============================================================================

def apply_capacity_ceiling(
    expected: list[float],
    capacity: list[float],
    overflow: str = "push",
) -> list[float]:
    """Cap expected bookings at AE capacity each month.

    Args:
        expected: Expected bookings per month (from stack_cohorts).
        capacity: Maximum bookings AEs can close each month.
        overflow: How to handle excess above capacity.
            "push" — rolls excess to the next month.
            "lost" — excess pipeline is dropped.

    Returns:
        List of actual bookings per month, respecting capacity constraints.

    Raises:
        ValueError: If overflow is not "push" or "lost".
    """
    if overflow not in ("push", "lost"):
        raise ValueError(
            f"overflow must be 'push' or 'lost', got '{overflow}'"
        )

    result = [0.0] * len(expected)
    carry = 0.0  # overflow from previous month (only used in push mode)

    for i, (exp, cap) in enumerate(zip(expected, capacity)):
        available = exp + carry if overflow == "push" else exp
        if available <= cap:
            result[i] = available
            carry = 0.0
        else:
            result[i] = cap
            carry = available - cap if overflow == "push" else 0.0

    return result


# =============================================================================
# CONFIDENCE TIER LABELING
# =============================================================================

def label_confidence_tiers(
    months: list[date],
    current_quarter_end: date,
    next_quarter_end: date,
) -> dict[date, str]:
    """Label each month-start date with a confidence tier.

    Tiers:
        "committed" — within the current quarter (month <= current_quarter_end)
        "building"  — within the next quarter
        "planned"   — beyond the next quarter

    Args:
        months: List of month-start dates to label.
        current_quarter_end: Last day of the current quarter.
        next_quarter_end: Last day of the next quarter.

    Returns:
        Dict mapping each date to its tier string.
    """
    result: dict[date, str] = {}
    for month in months:
        if month <= current_quarter_end:
            result[month] = "committed"
        elif month <= next_quarter_end:
            result[month] = "building"
        else:
            result[month] = "planned"
    return result


# =============================================================================
# ORCHESTRATOR
# =============================================================================

def project_bookings(
    monthly_creation: list[float],
    decay_curve: list[float],
    monthly_capacity: list[float],
    overflow: str = "push",
    months: Optional[list[date]] = None,
    current_quarter_end: Optional[date] = None,
    next_quarter_end: Optional[date] = None,
) -> dict:
    """Orchestrate the full cohort model pipeline.

    Steps:
        1. Spread each monthly cohort using the decay curve.
        2. Stack cohorts into total expected bookings per month.
        3. Apply capacity ceiling to get capped bookings.
        4. Label months with confidence tiers (if dates provided).

    Args:
        monthly_creation: Pipeline created each month.
        decay_curve: 9-bucket close rate distribution.
        monthly_capacity: Max bookings per month (AE capacity).
        overflow: "push" or "lost" (default "push").
        months: Optional list of month-start dates for tier labeling.
        current_quarter_end: Required for tier labeling.
        next_quarter_end: Required for tier labeling.

    Returns:
        Dict with keys:
            "expected"         — list[float]: uncapped stacked bookings
            "capped"           — list[float]: bookings after capacity ceiling
            "overflow_amounts" — list[float]: excess per month
            "tiers"            — dict[date, str] or {} if dates not provided
    """
    # Step 1 + 2: spread and stack
    expected = stack_cohorts(monthly_creation, decay_curve)

    # Step 3: apply capacity ceiling
    capped = apply_capacity_ceiling(expected, monthly_capacity, overflow=overflow)

    # Compute overflow amounts (difference between expected+carry and capped)
    # Re-run the ceiling to track carry precisely
    overflow_amounts = [0.0] * len(expected)
    carry = 0.0
    for i, (exp, cap) in enumerate(zip(expected, monthly_capacity)):
        available = exp + carry if overflow == "push" else exp
        if available <= cap:
            overflow_amounts[i] = 0.0
            carry = 0.0
        else:
            overflow_amounts[i] = available - cap
            carry = available - cap if overflow == "push" else 0.0

    # Step 4: confidence tiers
    tiers: dict[date, str] = {}
    if months is not None and current_quarter_end is not None and next_quarter_end is not None:
        tiers = label_confidence_tiers(months, current_quarter_end, next_quarter_end)

    return {
        "expected": expected,
        "capped": capped,
        "overflow_amounts": overflow_amounts,
        "tiers": tiers,
    }

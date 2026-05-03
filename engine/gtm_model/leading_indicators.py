"""
Leading Indicators Module for GTM Intelligence.

Provides calculations for pipeline velocity burn-up charts,
weekly pacing tables, and Point of No Return (PONR) analysis.

These metrics answer: "Are we generating enough pipeline to hit future targets?"
This complements the Monte Carlo (which answers "What will S2+ yield THIS quarter?")
by providing early funnel visibility.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass
class BurnUpData:
    """Data for burn-up chart visualization."""

    metric_name: str
    weeks: list[date]
    plan_cumulative: list[float]
    actual_cumulative: list[Optional[float]]  # None for future weeks
    projected_cumulative: list[float]


@dataclass
class PacingRow:
    """Row data for the weekly pacing table."""

    metric: str
    this_week_actual: float
    this_week_plan: float
    this_week_variance_pct: float
    ytd_actual: float
    ytd_plan: float
    ytd_variance_pct: float
    status: str  # "on_track", "at_risk", "behind"


@dataclass
class PointOfNoReturn:
    """Point of No Return analysis for a metric."""

    can_still_hit_target: bool
    weeks_to_course_correct: int
    required_weekly_velocity: float
    current_weekly_velocity: float
    velocity_gap_pct: float
    message: str


def get_quarter_weeks(start_date: date, end_date: date) -> list[date]:
    """
    Generate Monday-aligned week starts for a quarter.

    Args:
        start_date: Quarter start date
        end_date: Quarter end date

    Returns:
        List of Monday dates representing each week in the quarter
    """
    weeks = []

    # Find first Monday on or after start_date
    current = start_date
    days_until_monday = (7 - current.weekday()) % 7
    if days_until_monday == 0 and current.weekday() != 0:
        days_until_monday = 7
    first_monday = current + timedelta(days=days_until_monday)

    # If start_date is already a Monday, use it
    if current.weekday() == 0:
        first_monday = current

    # Include partial first week if quarter doesn't start on Monday
    if first_monday > start_date:
        weeks.append(start_date - timedelta(days=start_date.weekday()))

    # Generate all Mondays through end of quarter
    current = first_monday
    while current <= end_date:
        weeks.append(current)
        current += timedelta(days=7)

    # Remove duplicates and sort
    weeks = sorted(set(weeks))

    return weeks


def calculate_burn_up(
    weekly_actuals: list[dict],
    weekly_target: float,
    quarter_start: date,
    quarter_end: date,
    metric_name: str,
    is_currency: bool = False,
) -> BurnUpData:
    """
    Calculate cumulative plan/actual/projected for burn-up chart.

    Args:
        weekly_actuals: List of {"week_start": date, "count": int} or {"week_start": date, "arr": float}
        weekly_target: Target value per week
        quarter_start: Quarter start date
        quarter_end: Quarter end date
        metric_name: Display name for the metric
        is_currency: If True, use 'arr' field; otherwise use 'count' field

    Returns:
        BurnUpData with cumulative values for plan, actual, and projected lines
    """
    weeks = get_quarter_weeks(quarter_start, quarter_end)
    today = date.today()

    # Build actuals map
    actuals_by_week: dict[date, float] = {}
    for item in weekly_actuals:
        week_start = item.get("week_start")
        if isinstance(week_start, date):
            value = item.get("arr" if is_currency else "count", 0) or 0
            actuals_by_week[week_start] = value

    # Calculate cumulative values
    plan_cumulative = []
    actual_cumulative = []
    projected_cumulative = []

    cumulative_plan = 0.0
    cumulative_actual = 0.0
    last_actual_week_idx = -1

    for i, week in enumerate(weeks):
        # Plan: linear accumulation
        cumulative_plan += weekly_target
        plan_cumulative.append(cumulative_plan)

        # Actual: only for past/current weeks
        if week <= today:
            week_actual = actuals_by_week.get(week, 0)
            cumulative_actual += week_actual
            actual_cumulative.append(cumulative_actual)
            last_actual_week_idx = i
        else:
            actual_cumulative.append(None)

    # Calculate projection based on current velocity
    if last_actual_week_idx >= 0:
        weeks_with_data = last_actual_week_idx + 1
        current_velocity = cumulative_actual / weeks_with_data if weeks_with_data > 0 else 0
    else:
        current_velocity = 0

    # Project forward from last actual
    projected_value = cumulative_actual if last_actual_week_idx >= 0 else 0
    for i, week in enumerate(weeks):
        if i <= last_actual_week_idx:
            projected_cumulative.append(actual_cumulative[i])
        else:
            projected_value += current_velocity
            projected_cumulative.append(projected_value)

    return BurnUpData(
        metric_name=metric_name,
        weeks=weeks,
        plan_cumulative=plan_cumulative,
        actual_cumulative=actual_cumulative,
        projected_cumulative=projected_cumulative,
    )


def calculate_pacing_table(
    actuals: dict[str, list[dict]],
    targets: dict[str, float],
    quarter_start: date,
    quarter_end: date,
) -> list[PacingRow]:
    """
    Generate pacing table with WoW and YTD comparisons.

    Args:
        actuals: Dict mapping metric name to weekly actuals list
            {"mql": [{"week_start": date, "count": int}, ...], ...}
        targets: Dict mapping metric name to weekly target
            {"mql": 264, "s0": 65, "s1": 46, "s2": 14}
        quarter_start: Quarter start date
        quarter_end: Quarter end date

    Returns:
        List of PacingRow for each metric
    """
    rows = []
    today = date.today()

    # Calculate current week and weeks elapsed
    weeks = get_quarter_weeks(quarter_start, quarter_end)
    current_week_idx = 0
    for i, week in enumerate(weeks):
        week_end = week + timedelta(days=6)
        if week <= today <= week_end:
            current_week_idx = i
            break
        elif week > today:
            current_week_idx = max(0, i - 1)
            break
    else:
        current_week_idx = len(weeks) - 1

    weeks_elapsed = current_week_idx + 1

    metric_labels = {
        "mql": "MQLs",
        "s0": "S0 Booked",
        "s1": "S1 Held",
        "s2": "S2 Created ($)",
    }

    for metric_key, weekly_data in actuals.items():
        weekly_target = targets.get(metric_key, 0)
        label = metric_labels.get(metric_key, metric_key)
        is_currency = metric_key == "s2"

        # Build actuals by week
        actuals_by_week: dict[date, float] = {}
        for item in weekly_data:
            week_start = item.get("week_start")
            if isinstance(week_start, date):
                value = item.get("arr" if is_currency else "count", 0) or 0
                actuals_by_week[week_start] = value

        # Calculate this week actual
        current_week = weeks[current_week_idx] if current_week_idx < len(weeks) else None
        this_week_actual = actuals_by_week.get(current_week, 0) if current_week else 0

        # Calculate YTD actual
        ytd_actual = sum(
            actuals_by_week.get(w, 0)
            for i, w in enumerate(weeks)
            if i <= current_week_idx
        )

        # Calculate plan values
        this_week_plan = weekly_target
        ytd_plan = weekly_target * weeks_elapsed

        # Calculate variances
        this_week_variance = (
            (this_week_actual - this_week_plan) / this_week_plan
            if this_week_plan > 0
            else 0
        )
        ytd_variance = (ytd_actual - ytd_plan) / ytd_plan if ytd_plan > 0 else 0

        # Determine status
        if ytd_variance >= -0.05:
            status = "on_track"
        elif ytd_variance >= -0.15:
            status = "at_risk"
        else:
            status = "behind"

        rows.append(
            PacingRow(
                metric=label,
                this_week_actual=this_week_actual,
                this_week_plan=this_week_plan,
                this_week_variance_pct=this_week_variance,
                ytd_actual=ytd_actual,
                ytd_plan=ytd_plan,
                ytd_variance_pct=ytd_variance,
                status=status,
            )
        )

    return rows


def calculate_point_of_no_return(
    ytd_actual: float,
    quarterly_target: float,
    weeks_elapsed: int,
    weeks_in_quarter: int = 13,
) -> PointOfNoReturn:
    """
    Calculate if target is achievable and time to course-correct.

    Uses S2 pipeline as the PONR metric per user decision.

    Args:
        ytd_actual: Year-to-date actual for the metric
        quarterly_target: Quarterly target
        weeks_elapsed: Number of weeks elapsed in quarter
        weeks_in_quarter: Total weeks in quarter (default 13)

    Returns:
        PointOfNoReturn with analysis and messaging
    """
    weeks_remaining = weeks_in_quarter - weeks_elapsed

    # Calculate required velocity to hit target
    shortfall = quarterly_target - ytd_actual
    required_velocity = shortfall / weeks_remaining if weeks_remaining > 0 else float("inf")

    # Calculate current velocity
    current_velocity = ytd_actual / weeks_elapsed if weeks_elapsed > 0 else 0

    # Calculate velocity gap
    velocity_gap_pct = (
        (required_velocity - current_velocity) / current_velocity
        if current_velocity > 0
        else float("inf")
    )

    # Determine if target is achievable
    # Assume max achievable velocity is 1.5x current (aggressive but possible)
    max_achievable_velocity = current_velocity * 1.5
    can_hit_target = required_velocity <= max_achievable_velocity

    # Calculate weeks to course correct (when does it become impossible?)
    # Working backwards: at what point does required velocity exceed 2x current?
    weeks_to_course_correct = 0
    if current_velocity > 0:
        for w in range(weeks_remaining, 0, -1):
            remaining = quarterly_target - ytd_actual
            req_vel = remaining / w
            if req_vel <= current_velocity * 2:
                weeks_to_course_correct = w
                break

    # Generate message
    if velocity_gap_pct <= 0:
        message = "On track - current velocity sufficient to hit target"
        status_indicator = "[OK]"
    elif velocity_gap_pct <= 0.15:
        message = f"Slight velocity increase needed ({velocity_gap_pct:.0%})"
        status_indicator = "[!]"
    elif can_hit_target:
        message = f"At risk - need {velocity_gap_pct:.0%} velocity increase on S2"
        status_indicator = "[!]"
    else:
        message = f"Behind - target likely unachievable without intervention"
        status_indicator = "[X]"

    return PointOfNoReturn(
        can_still_hit_target=can_hit_target,
        weeks_to_course_correct=weeks_to_course_correct,
        required_weekly_velocity=required_velocity,
        current_weekly_velocity=current_velocity,
        velocity_gap_pct=velocity_gap_pct,
        message=f"{status_indicator} {message}",
    )


def get_status_color(status: str) -> str:
    """Get CSS class for status indicator."""
    return {
        "on_track": "status-on-track",
        "at_risk": "status-at-risk",
        "behind": "status-behind",
    }.get(status, "")


def get_status_emoji(status: str) -> str:
    """Get text indicator for status (ASCII-safe)."""
    return {
        "on_track": "[OK]",
        "at_risk": "[!]",
        "behind": "[X]",
    }.get(status, "")

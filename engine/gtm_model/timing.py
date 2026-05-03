"""
Time-shifted pipeline planning for GTM Intelligence Platform.

This module answers: "To hit Q2 bookings ($12M), when do we need to create
pipeline? When do we need MQLs? Are we on track?"

It works backward from bookings targets through velocity to generate
actionable creation schedules.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
import math

from .funnel import SOURCE_CATEGORY_MAP
from .tieout.runtime.env import load_yaml_resource


@dataclass
class HealthAdjustedProbability:
    """Health-adjusted pipeline probability for forecasting."""

    stage: str
    base_probability: float
    health_status: str  # "Healthy", "Moderate", "At Risk", "Unknown"
    health_multiplier: float
    adjusted_probability: float = field(init=False)

    HEALTH_MULTIPLIERS = {
        "Healthy": 1.15,
        "Moderate": 1.00,
        "At Risk": 0.70,
        "Unknown": 0.90,
    }

    def __post_init__(self):
        """Calculate health-adjusted probability."""
        self.adjusted_probability = min(1.0, self.base_probability * self.health_multiplier)

    @classmethod
    def from_stage_and_health(cls, stage: str, health_status: str) -> "HealthAdjustedProbability":
        """Create from stage and health status."""
        from connectors.field_mapping import get_stage_probability

        base_prob = get_stage_probability(stage)
        multiplier = cls.HEALTH_MULTIPLIERS.get(health_status, 0.90)

        return cls(
            stage=stage,
            base_probability=base_prob,
            health_status=health_status,
            health_multiplier=multiplier,
        )


@dataclass
class MonthlyRequirement:
    """Required pipeline or MQLs for a specific month."""

    month: date  # First day of the month
    required: float  # Pipeline value or MQL count
    actual: float = 0.0
    gap: float = field(init=False)
    status: str = field(init=False)

    def __post_init__(self):
        """Calculate derived fields."""
        self.gap = max(0, self.required - self.actual)
        if self.actual >= self.required:
            self.status = "on_track"
        elif self.actual >= self.required * 0.75:
            self.status = "at_risk"
        else:
            self.status = "behind"

    @property
    def month_label(self) -> str:
        """Return month label like 'Jan-26'."""
        return self.month.strftime("%b-%y")


@dataclass
class TimelineRequirement:
    """Complete timeline requirements for a target period."""

    target_period: str  # "Q2FY26"
    target_bookings: float  # $12M
    close_months: list[date]  # Months in which deals close
    pipeline_by_month: dict[date, float]  # {month: required_value}
    mql_by_month: dict[date, int]  # {month: required_count}
    earliest_action_date: date  # When you need to start

    @property
    def total_pipeline_required(self) -> float:
        """Total pipeline that must be created."""
        return sum(self.pipeline_by_month.values())

    @property
    def total_mqls_required(self) -> int:
        """Total MQLs that must be generated."""
        return sum(self.mql_by_month.values())


@dataclass
class TimelineStatus:
    """Assessment of current status against timeline requirements."""

    target_period: str
    target_bookings: float
    analysis_date: date
    overall_status: str  # "on_track", "at_risk", "behind"

    # Month-by-month comparison
    pipeline_status: list[MonthlyRequirement]
    mql_status: list[MonthlyRequirement]

    # Summary metrics
    pipeline_gap_total: float = 0.0
    mql_gap_total: int = 0
    months_behind_pipeline: int = 0
    months_behind_mql: int = 0

    # Recommendations
    risk_factors: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate summary metrics."""
        self.pipeline_gap_total = sum(m.gap for m in self.pipeline_status if m.month <= self.analysis_date)
        self.mql_gap_total = int(sum(m.gap for m in self.mql_status if m.month <= self.analysis_date))
        self.months_behind_pipeline = sum(1 for m in self.pipeline_status if m.status == "behind" and m.month <= self.analysis_date)
        self.months_behind_mql = sum(1 for m in self.mql_status if m.status == "behind" and m.month <= self.analysis_date)


# Default close rate distribution from typical B2B SaaS distributions
DEFAULT_CLOSE_DISTRIBUTION = {
    0: 0.16,  # 16% closes same month as created
    1: 0.26,  # 26% closes 1 month after creation
    2: 0.17,  # 17% closes 2 months after creation
    3: 0.15,  # 15% closes 3 months after creation
    4: 0.10,  # 10% closes 4 months after creation
    5: 0.06,  # 6% closes 5 months after creation
    6: 0.10,  # 10% closes 6+ months after creation (spread across 6-8)
}


def _load_config(config_path: Optional[Path] = None) -> dict:
    """Load configuration from YAML file."""
    targets = load_yaml_resource("targets.yaml", config_dir=config_path)
    assumptions = load_yaml_resource("assumptions.yaml", config_dir=config_path)

    return {"targets": targets, "assumptions": assumptions}


def _get_month_start(d: date) -> date:
    """Return the first day of the month for a given date."""
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    """Add or subtract months from a date."""
    year = d.year + (d.month + months - 1) // 12
    month = (d.month + months - 1) % 12 + 1
    return date(year, month, 1)


def _get_quarter_months(quarter: str, config: Optional[dict] = None) -> list[date]:
    """
    Get the months in a quarter.

    Args:
        quarter: Quarter identifier (e.g., 'Q2FY26')
        config: Config dict (loads from file if not provided)

    Returns:
        List of month start dates in the quarter
    """
    if config is None:
        config = _load_config()

    targets = config["targets"]
    quarterly = targets.get("quarterly_targets", {})
    q_config = quarterly.get(quarter, {})

    if not q_config:
        raise ValueError(f"Unknown quarter: {quarter}. Available: {', '.join(quarterly.keys())}")

    period_start = q_config.get("period_start")
    period_end = q_config.get("period_end")

    if isinstance(period_start, str):
        period_start = date.fromisoformat(period_start)
    if isinstance(period_end, str):
        period_end = date.fromisoformat(period_end)

    # Generate list of months in the quarter
    months = []
    current = _get_month_start(period_start)
    while current <= period_end:
        months.append(current)
        current = _add_months(current, 1)

    return months


def _get_monthly_bookings(quarter: str, config: Optional[dict] = None) -> dict[date, float]:
    """
    Get monthly bookings targets for a quarter.

    Args:
        quarter: Quarter identifier (e.g., 'Q2FY26')
        config: Config dict

    Returns:
        Dict mapping month start date to bookings target
    """
    if config is None:
        config = _load_config()

    targets = config["targets"]
    monthly = targets.get("monthly_bookings", {})

    # Convert month labels to dates
    months = _get_quarter_months(quarter, config)
    result = {}

    for month in months:
        # Try different label formats
        label = month.strftime("%b-%y")  # "May-26"
        if label in monthly:
            result[month] = float(monthly[label])
        else:
            # Fall back to quarterly target / 3
            quarterly = targets.get("quarterly_targets", {})
            q_config = quarterly.get(quarter, {})
            quarterly_target = q_config.get("bookings_target", 0)
            result[month] = quarterly_target / len(months)

    return result


def calculate_pipeline_creation_schedule(
    bookings_target: float,
    close_months: list[date],
    close_distribution: Optional[dict[int, float]] = None,
    monthly_bookings: Optional[dict[date, float]] = None,
) -> dict[date, float]:
    """
    Work backward from bookings target to determine when pipeline must be created.

    Uses close rate distribution to calculate how much pipeline needs to be
    created each month to hit bookings targets.

    Args:
        bookings_target: Total bookings target for the period
        close_months: List of months when deals close
        close_distribution: Dict mapping month offset to close rate
        monthly_bookings: Optional dict of bookings per close month

    Returns:
        Dict mapping creation month to required pipeline value

    Example:
        >>> schedule = calculate_pipeline_creation_schedule(
        ...     bookings_target=12_000_000,
        ...     close_months=[date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1)]
        ... )
        >>> schedule[date(2026, 2, 1)]  # Feb-26 requirement
        2640000.0
    """
    if close_distribution is None:
        close_distribution = DEFAULT_CLOSE_DISTRIBUTION

    if monthly_bookings is None:
        # Distribute evenly across close months
        per_month = bookings_target / len(close_months)
        monthly_bookings = {month: per_month for month in close_months}

    # For each close month, work backward using distribution
    pipeline_by_month: dict[date, float] = {}

    for close_month, close_amount in monthly_bookings.items():
        for offset, rate in close_distribution.items():
            # Creation month = close month minus offset
            creation_month = _add_months(close_month, -offset)
            required = close_amount * rate

            if creation_month not in pipeline_by_month:
                pipeline_by_month[creation_month] = 0.0
            pipeline_by_month[creation_month] += required

    return dict(sorted(pipeline_by_month.items()))


def calculate_mql_schedule(
    pipeline_schedule: dict[date, float],
    source_mix: Optional[dict[str, float]] = None,
    velocity_days: int = 10,
    mql_to_s0_rate: float = 0.15,
    avg_acv: float = 300_000,
    use_actual_source_mix: bool = False,
    sf_connector: Optional[object] = None,
) -> dict[date, int]:
    """
    Shift pipeline requirements backward by velocity to get MQL schedule.

    Only non-AE-sourced pipeline needs MQLs (SDR + Marketing sourced).
    AE-sourced pipeline goes direct to S0.

    Args:
        pipeline_schedule: Required pipeline by month from calculate_pipeline_creation_schedule
        source_mix: Dict with ae_sourced, sdr_sourced, marketing_sourced percentages
        velocity_days: Days from MQL to S0 (default 10)
        mql_to_s0_rate: Conversion rate from MQL to S0 (default 15%)
        avg_acv: Average contract value for MQL count calculation
        use_actual_source_mix: If True, fetch actual source mix from Salesforce
        sf_connector: SalesforceConnector instance (required if use_actual_source_mix=True)

    Returns:
        Dict mapping MQL generation month to required count
    """
    # Fetch actual source mix from Salesforce if requested
    if use_actual_source_mix and sf_connector is not None:
        try:
            # Get attribution data for last 6 months using new authoritative method
            lookback_start = _add_months(date.today(), -6)
            attribution = sf_connector.get_opportunity_source_mix(lookback_start, date.today())

            # Convert from SF picklist values to config keys using centralized map
            raw_mix = attribution.get("source_mix", {})
            source_mix = {
                config_key: raw_mix.get(sf_key, 0)
                for sf_key, config_key in SOURCE_CATEGORY_MAP.items()
            }
        except Exception:
            # Fall back to defaults if SF query fails
            source_mix = None

    if source_mix is None:
        # Default source mix (Phase 5: 6 categories)
        source_mix = {
            "sdr_sourced": 0.40,
            "marketing_sourced": 0.16,
            "ae_sourced": 0.29,
            "leadership_sourced": 0.09,
            "se_sourced": 0.02,
            "unknown": 0.04,
        }

    # Percentage of pipeline that needs MQLs (SDR + Marketing)
    mql_sourced_pct = source_mix.get("sdr_sourced", 0.40) + source_mix.get("marketing_sourced", 0.16)

    mql_by_month: dict[date, int] = {}

    for pipeline_month, pipeline_value in pipeline_schedule.items():
        # Only MQL-sourced pipeline needs MQLs
        mql_pipeline = pipeline_value * mql_sourced_pct

        # Convert pipeline value to MQL count
        # MQLs needed = pipeline / (mql_to_s0_rate * avg_acv)
        if mql_to_s0_rate > 0 and avg_acv > 0:
            mqls_needed = math.ceil(mql_pipeline / (mql_to_s0_rate * avg_acv))
        else:
            mqls_needed = 0

        # Shift backward by velocity (convert days to months, roughly)
        # 10 days ~= 1/3 month, so we round to same month if < 15 days
        months_offset = velocity_days // 30
        if months_offset > 0:
            mql_month = _add_months(pipeline_month, -months_offset)
        else:
            mql_month = pipeline_month

        if mql_month not in mql_by_month:
            mql_by_month[mql_month] = 0
        mql_by_month[mql_month] += mqls_needed

    return dict(sorted(mql_by_month.items()))


def build_timeline_requirement(
    quarter: str,
    config_path: Optional[Path] = None,
    use_actual_source_mix: bool = False,
    sf_connector: Optional[object] = None,
) -> TimelineRequirement:
    """
    Build complete timeline requirements for a quarter from config files.

    Args:
        quarter: Quarter identifier (e.g., 'Q2FY26')
        config_path: Path to config directory
        use_actual_source_mix: If True, fetch actual source mix from Salesforce
        sf_connector: SalesforceConnector instance (required if use_actual_source_mix=True)

    Returns:
        TimelineRequirement with pipeline and MQL schedules
    """
    config = _load_config(config_path)
    targets = config["targets"]
    assumptions = config["assumptions"]

    # Get quarter info
    quarterly = targets.get("quarterly_targets", {})
    q_config = quarterly.get(quarter, {})

    if not q_config:
        raise ValueError(f"Unknown quarter: {quarter}")

    bookings_target = float(q_config.get("bookings_target", 0))
    close_months = _get_quarter_months(quarter, config)
    monthly_bookings = _get_monthly_bookings(quarter, config)

    # Get close rate distribution from config
    close_dist_config = targets.get("close_rate_distribution", {})
    if close_dist_config:
        close_distribution = {
            0: close_dist_config.get("same_month", 0.16),
            1: close_dist_config.get("month_1_before", 0.26),
            2: close_dist_config.get("month_2_before", 0.17),
            3: close_dist_config.get("month_3_before", 0.15),
            4: close_dist_config.get("month_4_before", 0.10),
            5: close_dist_config.get("month_5_before", 0.06),
            6: close_dist_config.get("month_6_plus_before", 0.10),
        }
    else:
        close_distribution = DEFAULT_CLOSE_DISTRIBUTION

    # Calculate pipeline schedule
    pipeline_schedule = calculate_pipeline_creation_schedule(
        bookings_target=bookings_target,
        close_months=close_months,
        close_distribution=close_distribution,
        monthly_bookings=monthly_bookings,
    )

    # Get source mix and velocity from assumptions (Phase 5: 6 categories)
    funnel = assumptions.get("funnel", {})
    source_mix = funnel.get("source_mix", {
        "sdr_sourced": 0.40,
        "marketing_sourced": 0.16,
        "ae_sourced": 0.29,
        "leadership_sourced": 0.09,
        "se_sourced": 0.02,
        "unknown": 0.04,
    })
    mql_to_s0_rate = funnel.get("mql_to_s0", 0.15)
    avg_acv = funnel.get("avg_acv", 300_000)

    velocity = assumptions.get("velocity", {})
    # MQL to S0 includes lead stages
    mql_to_s0_days = (
        velocity.get("lead_to_mql_days", 2) +
        velocity.get("mql_to_sql_days", 3) +
        velocity.get("sql_to_s0_days", 5)
    )

    # Calculate MQL schedule
    mql_schedule = calculate_mql_schedule(
        pipeline_schedule=pipeline_schedule,
        source_mix=source_mix if not use_actual_source_mix else None,
        velocity_days=mql_to_s0_days,
        mql_to_s0_rate=mql_to_s0_rate,
        avg_acv=avg_acv,
        use_actual_source_mix=use_actual_source_mix,
        sf_connector=sf_connector,
    )

    # Find earliest action date (earliest month with requirements)
    all_months = list(pipeline_schedule.keys()) + list(mql_schedule.keys())
    earliest_action_date = min(all_months) if all_months else close_months[0]

    return TimelineRequirement(
        target_period=quarter,
        target_bookings=bookings_target,
        close_months=close_months,
        pipeline_by_month=pipeline_schedule,
        mql_by_month=mql_schedule,
        earliest_action_date=earliest_action_date,
    )


def assess_timeline_status(
    requirement: TimelineRequirement,
    pipeline_actuals: Optional[dict[date, float]] = None,
    mql_actuals: Optional[dict[date, int]] = None,
    analysis_date: Optional[date] = None,
) -> TimelineStatus:
    """
    Compare actuals vs requirements and return status + recommendations.

    Args:
        requirement: TimelineRequirement from build_timeline_requirement
        pipeline_actuals: Dict mapping month to actual pipeline created
        mql_actuals: Dict mapping month to actual MQL count
        analysis_date: Date of analysis (defaults to today)

    Returns:
        TimelineStatus with assessment and recommendations
    """
    if analysis_date is None:
        analysis_date = date.today()

    if pipeline_actuals is None:
        pipeline_actuals = {}

    if mql_actuals is None:
        mql_actuals = {}

    # Build month-by-month status
    pipeline_status = []
    for month, required in sorted(requirement.pipeline_by_month.items()):
        actual = pipeline_actuals.get(month, 0.0)
        pipeline_status.append(MonthlyRequirement(
            month=month,
            required=required,
            actual=actual,
        ))

    mql_status = []
    for month, required in sorted(requirement.mql_by_month.items()):
        actual = float(mql_actuals.get(month, 0))
        mql_status.append(MonthlyRequirement(
            month=month,
            required=float(required),
            actual=actual,
        ))

    # Determine overall status
    past_pipeline_months = [m for m in pipeline_status if m.month <= analysis_date]
    past_mql_months = [m for m in mql_status if m.month <= analysis_date]

    behind_pipeline = sum(1 for m in past_pipeline_months if m.status == "behind")
    behind_mql = sum(1 for m in past_mql_months if m.status == "behind")

    if behind_pipeline > 0 or behind_mql > 0:
        overall_status = "behind"
    elif any(m.status == "at_risk" for m in past_pipeline_months + past_mql_months):
        overall_status = "at_risk"
    else:
        overall_status = "on_track"

    # Build risk factors
    risk_factors = []
    pipeline_gap = sum(m.gap for m in past_pipeline_months)
    mql_gap = sum(m.gap for m in past_mql_months)

    if behind_pipeline > 0:
        risk_factors.append(f"Behind on pipeline creation for {behind_pipeline} month(s)")
    if behind_mql > 0:
        risk_factors.append(f"Behind on MQL generation for {behind_mql} month(s)")
    if pipeline_gap > 0:
        risk_factors.append(f"Total pipeline gap: ${pipeline_gap:,.0f}")
    if mql_gap > 0:
        risk_factors.append(f"Total MQL gap: {int(mql_gap):,} MQLs")

    # Build recommendations
    recommended_actions = []
    current_month = _get_month_start(analysis_date)
    next_month = _add_months(current_month, 1)

    if pipeline_gap > 0:
        # How much pipeline needed this month plus catch-up?
        current_required = requirement.pipeline_by_month.get(current_month, 0)
        catch_up_needed = current_required + (pipeline_gap * 0.5)  # Catch up half this month
        recommended_actions.append(
            f"Create ${catch_up_needed:,.0f} pipeline this month to recover deficit"
        )

    if mql_gap > 0:
        # When is next MQL requirement?
        next_mql_required = requirement.mql_by_month.get(next_month, 0)
        catch_up_mqls = int(mql_gap * 0.5) + next_mql_required
        recommended_actions.append(
            f"Generate {catch_up_mqls:,} additional MQLs by {next_month.strftime('%b %d')} to recover deficit"
        )

    if not risk_factors:
        recommended_actions.append("Continue current pace to hit target")

    return TimelineStatus(
        target_period=requirement.target_period,
        target_bookings=requirement.target_bookings,
        analysis_date=analysis_date,
        overall_status=overall_status,
        pipeline_status=pipeline_status,
        mql_status=mql_status,
        risk_factors=risk_factors,
        recommended_actions=recommended_actions,
    )

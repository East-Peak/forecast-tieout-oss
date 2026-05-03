"""Pipeline forecasting: weighted bookings projection, channel requirements, and rolling-trajectory forecast."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional
import math

from .rate_defaults import get_default_forecast_stage_conversion
from .tieout.runtime.env import load_yaml_resource


# Sequential multiplicative methodology: product of per-stage advance rates
# (s2→s3 * s3→s4 * ... * s5→won). Intentionally differs from monte_carlo.py's
# all-inclusive win rates.
DEFAULT_STAGE_CONVERSION = get_default_forecast_stage_conversion()

AGE_MULTIPLIERS = {
    (0, 30): 1.00,     # 0-30 days: full probability
    (31, 60): 0.85,    # 31-60 days: 85%
    (61, 90): 0.70,    # 61-90 days: 70%
    (91, 120): 0.55,   # 91-120 days: 55%
    (121, 180): 0.40,  # 121-180 days: 40%
    (181, float("inf")): 0.25,  # 180+ days: 25%
}


class ChannelStatus(Enum):
    """Channel pipeline status."""
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BEHIND = "behind"


@dataclass
class PipelineForecast:
    """
    Forecast bookings from current pipeline.

    Uses stage conversion rates and age adjustments to predict
    expected bookings with confidence intervals.
    """

    # Context
    as_of_date: date
    target_period: str
    target: float

    # Pipeline state
    pipeline_by_stage: dict[str, float] = field(default_factory=dict)
    age_adjusted_pipeline: float = 0.0

    # Forecast
    expected_bookings: float = 0.0
    low_estimate: float = 0.0       # Low end of CI (80% default)
    high_estimate: float = 0.0      # High end of CI
    probability_of_hitting_target: float = 0.0

    # Breakdown by stage
    expected_by_stage: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        """Validate forecast values."""
        if self.expected_bookings < 0:
            raise ValueError(f"Expected bookings cannot be negative: {self.expected_bookings}")
        if self.target < 0:
            raise ValueError(f"Target cannot be negative: {self.target}")
        if not 0.0 <= self.probability_of_hitting_target <= 1.0:
            # Clamp to valid range instead of erroring
            self.probability_of_hitting_target = max(0.0, min(1.0, self.probability_of_hitting_target))

    @property
    def gap_to_target(self) -> float:
        """Gap between expected bookings and target."""
        return max(0, self.target - self.expected_bookings)

    @property
    def expected_attainment(self) -> float:
        """Expected attainment percentage."""
        return self.expected_bookings / self.target if self.target > 0 else 0.0

    @property
    def forecast_range(self) -> str:
        """Formatted forecast range string."""
        return f"${self.low_estimate:,.0f} - ${self.high_estimate:,.0f}"

    def summary(self) -> str:
        """Return formatted text summary."""
        lines = [
            f"Pipeline Forecast (as of {self.as_of_date})",
            f"  Target: ${self.target:,.0f}",
            "",
            "  Pipeline State:",
        ]

        for stage, arr in sorted(self.pipeline_by_stage.items()):
            expected = self.expected_by_stage.get(stage, 0)
            lines.append(f"    {stage}: ${arr:,.0f} -> ${expected:,.0f} expected")

        lines.extend([
            "",
            f"  Age-Adjusted Pipeline: ${self.age_adjusted_pipeline:,.0f}",
            "",
            "  Forecast:",
            f"    Expected Bookings: ${self.expected_bookings:,.0f}",
            f"    Range (80% CI): {self.forecast_range}",
            f"    Probability of Hitting Target: {self.probability_of_hitting_target:.0%}",
        ])

        if self.gap_to_target > 0:
            lines.append(f"    Gap to Target: ${self.gap_to_target:,.0f}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "target_period": self.target_period,
            "target": self.target,
            "pipeline_by_stage": self.pipeline_by_stage,
            "age_adjusted_pipeline": self.age_adjusted_pipeline,
            "expected_bookings": self.expected_bookings,
            "low_estimate": self.low_estimate,
            "high_estimate": self.high_estimate,
            "probability_of_hitting_target": self.probability_of_hitting_target,
            "expected_by_stage": self.expected_by_stage,
            "gap_to_target": self.gap_to_target,
            "expected_attainment": self.expected_attainment,
        }


@dataclass
class ChannelRequirement:
    """Requirements for one source channel (SDR/Marketing/AE)."""

    channel: str
    total_required: float
    total_actual: float
    gap: float
    monthly_requirements: dict[date, float] = field(default_factory=dict)
    monthly_actuals: dict[date, float] = field(default_factory=dict)
    status: ChannelStatus = ChannelStatus.ON_TRACK

    def __post_init__(self):
        """Validate and calculate derived fields."""
        if self.total_required < 0:
            raise ValueError(f"Required cannot be negative: {self.total_required}")
        if self.total_actual < 0:
            raise ValueError(f"Actual cannot be negative: {self.total_actual}")

        # Calculate gap if not provided
        if self.gap == 0:
            self.gap = max(0, self.total_required - self.total_actual)

        # Determine status if not set
        if self.total_required > 0:
            pct = self.total_actual / self.total_required
            if pct >= 0.95:
                self.status = ChannelStatus.ON_TRACK
            elif pct >= 0.80:
                self.status = ChannelStatus.AT_RISK
            else:
                self.status = ChannelStatus.BEHIND

    @property
    def attainment(self) -> float:
        """Attainment percentage."""
        return self.total_actual / self.total_required if self.total_required > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "channel": self.channel,
            "total_required": self.total_required,
            "total_actual": self.total_actual,
            "gap": self.gap,
            "attainment": self.attainment,
            "status": self.status.value,
            "monthly_requirements": {
                k.isoformat() if isinstance(k, date) else str(k): v
                for k, v in self.monthly_requirements.items()
            },
            "monthly_actuals": {
                k.isoformat() if isinstance(k, date) else str(k): v
                for k, v in self.monthly_actuals.items()
            },
        }


@dataclass
class ChannelBreakdown:
    """Pipeline requirements by channel."""

    # Context
    target_bookings: float
    target_period: str

    # Channel breakdown
    channels: dict[str, ChannelRequirement] = field(default_factory=dict)
    priority_channel: str = ""
    recommendations: list[str] = field(default_factory=list)

    # Totals
    total_required: float = 0.0
    total_actual: float = 0.0
    total_gap: float = 0.0

    def __post_init__(self):
        """Calculate totals and recommendations."""
        if self.channels:
            self.total_required = sum(c.total_required for c in self.channels.values())
            self.total_actual = sum(c.total_actual for c in self.channels.values())
            self.total_gap = sum(c.gap for c in self.channels.values())

            # Find priority channel (biggest gap)
            max_gap = 0
            for name, channel in self.channels.items():
                if channel.gap > max_gap:
                    max_gap = channel.gap
                    self.priority_channel = name

            # Generate recommendations
            self._generate_recommendations()

    def _generate_recommendations(self):
        """Generate actionable recommendations based on channel status."""
        self.recommendations = []

        for name, channel in self.channels.items():
            if channel.status == ChannelStatus.BEHIND:
                self.recommendations.append(
                    f"URGENT: {name} is behind by ${channel.gap:,.0f} "
                    f"({channel.attainment:.0%} of target)"
                )
            elif channel.status == ChannelStatus.AT_RISK:
                self.recommendations.append(
                    f"WATCH: {name} is at risk - gap of ${channel.gap:,.0f}"
                )

        if not self.recommendations:
            self.recommendations.append("All channels on track")

    def summary(self) -> str:
        """Return formatted text summary."""
        lines = [
            f"Channel Requirements for {self.target_period}",
            f"  Target Bookings: ${self.target_bookings:,.0f}",
            "",
            f"  {'Channel':<20} {'Required':>12} {'Actual':>12} {'Gap':>12} {'Status':>10}",
            "  " + "-" * 68,
        ]

        for name, channel in sorted(self.channels.items()):
            gap_str = f"${channel.gap:,.0f}" if channel.gap > 0 else "-"
            lines.append(
                f"  {name:<20} ${channel.total_required:>10,.0f} "
                f"${channel.total_actual:>10,.0f} {gap_str:>12} "
                f"{channel.status.value.upper():>10}"
            )

        lines.extend([
            "  " + "-" * 68,
            f"  {'TOTAL':<20} ${self.total_required:>10,.0f} "
            f"${self.total_actual:>10,.0f} ${self.total_gap:>10,.0f}",
            "",
            "  Recommendations:",
        ])

        for rec in self.recommendations:
            lines.append(f"    - {rec}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "target_bookings": self.target_bookings,
            "target_period": self.target_period,
            "channels": {k: v.to_dict() for k, v in self.channels.items()},
            "priority_channel": self.priority_channel,
            "recommendations": self.recommendations,
            "total_required": self.total_required,
            "total_actual": self.total_actual,
            "total_gap": self.total_gap,
        }


@dataclass
class RollingForecast:
    """Trajectory-based forecast from historical run rate."""

    # Context
    as_of_date: date
    target_period: str
    target: float

    # Historical data
    bookings_ytd: float = 0.0
    months_elapsed: int = 0
    monthly_run_rate: float = 0.0

    # Projection
    months_remaining: int = 0
    projected_bookings: float = 0.0
    projected_gap: float = 0.0
    required_rate_to_hit_target: float = 0.0
    rate_increase_needed: float = 0.0  # Percentage increase needed

    # Monthly breakdown
    monthly_projection: list[dict] = field(default_factory=list)

    def __post_init__(self):
        """Validate forecast values."""
        if self.bookings_ytd < 0:
            raise ValueError(f"Bookings YTD cannot be negative: {self.bookings_ytd}")
        if self.target < 0:
            raise ValueError(f"Target cannot be negative: {self.target}")

    @property
    def projected_attainment(self) -> float:
        """Projected attainment percentage."""
        return self.projected_bookings / self.target if self.target > 0 else 0.0

    @property
    def on_track(self) -> bool:
        """Whether current trajectory meets target."""
        return self.projected_bookings >= self.target

    def summary(self) -> str:
        """Return formatted text summary."""
        lines = [
            f"Rolling Forecast for {self.target_period} (as of {self.as_of_date})",
            f"  Target: ${self.target:,.0f}",
            "",
            "  YTD Performance:",
            f"    Bookings YTD: ${self.bookings_ytd:,.0f}",
            f"    Months Elapsed: {self.months_elapsed}",
            f"    Run Rate: ${self.monthly_run_rate:,.0f}/month",
            "",
            "  Projection:",
            f"    Months Remaining: {self.months_remaining}",
            f"    Projected Bookings: ${self.projected_bookings:,.0f}",
            f"    Projected Attainment: {self.projected_attainment:.0%}",
        ]

        if self.projected_gap > 0:
            lines.extend([
                "",
                f"  Gap Analysis:",
                f"    Gap to Target: ${self.projected_gap:,.0f}",
                f"    Required Rate: ${self.required_rate_to_hit_target:,.0f}/month",
                f"    Rate Increase Needed: +{self.rate_increase_needed:.0%}",
            ])
        else:
            lines.append("")
            lines.append("  Status: ON TRACK to hit target")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "target_period": self.target_period,
            "target": self.target,
            "bookings_ytd": self.bookings_ytd,
            "months_elapsed": self.months_elapsed,
            "monthly_run_rate": self.monthly_run_rate,
            "months_remaining": self.months_remaining,
            "projected_bookings": self.projected_bookings,
            "projected_gap": self.projected_gap,
            "projected_attainment": self.projected_attainment,
            "required_rate_to_hit_target": self.required_rate_to_hit_target,
            "rate_increase_needed": self.rate_increase_needed,
            "on_track": self.on_track,
            "monthly_projection": self.monthly_projection,
        }


def get_age_multiplier(days_in_stage: int) -> float:
    """
    Get age-based probability multiplier for a deal.

    Args:
        days_in_stage: Days the deal has been in current stage

    Returns:
        Probability multiplier (0.25 to 1.0)
    """
    for (low, high), multiplier in AGE_MULTIPLIERS.items():
        if low <= days_in_stage <= high:
            return multiplier
    return 0.25  # Default for very old deals


def calculate_pipeline_forecast(
    pipeline_by_stage: dict[str, float],
    pipeline_aging: Optional[list[dict]] = None,
    target: float = 0.0,
    close_start: Optional[date] = None,
    close_end: Optional[date] = None,
    target_period: str = "",
    stage_conversion: Optional[dict[str, float]] = None,
    historical_variance: float = 0.15,
    confidence_level: float = 0.80,
) -> PipelineForecast:
    """
    Apply stage conversion rates + age adjustments to forecast bookings.

    Args:
        pipeline_by_stage: Current pipeline by stage (S2-S5)
        pipeline_aging: Optional list of deals with age info for age adjustment
        target: Bookings target for the period
        close_start: Period start date
        close_end: Period end date
        target_period: Period label (e.g., "Q2FY26")
        stage_conversion: Override conversion rates (stage -> won probability)
        historical_variance: Standard deviation as fraction of mean (default 15%)
        confidence_level: Confidence level for interval (default 80%)

    Returns:
        PipelineForecast with expected bookings and confidence intervals
    """
    as_of = date.today()
    conversion = stage_conversion or get_default_forecast_stage_conversion()

    # Calculate expected bookings by stage
    expected_by_stage = {}
    total_expected = 0.0

    for stage, arr in pipeline_by_stage.items():
        if stage not in conversion:
            continue

        rate = conversion[stage]
        expected = arr * rate
        expected_by_stage[stage] = expected
        total_expected += expected

    # Apply age adjustment if aging data provided
    age_adjusted_pipeline = sum(pipeline_by_stage.values())

    if pipeline_aging:
        # Group aging data by stage and calculate weighted average multiplier
        stage_adjustments = {}
        for deal in pipeline_aging:
            stage = deal.get("stage", "")
            arr = float(deal.get("arr", 0))
            days = int(deal.get("days_in_stage", 0))

            if stage not in stage_adjustments:
                stage_adjustments[stage] = {"total_arr": 0, "adjusted_arr": 0}

            multiplier = get_age_multiplier(days)
            stage_adjustments[stage]["total_arr"] += arr
            stage_adjustments[stage]["adjusted_arr"] += arr * multiplier

        # Recalculate expected with age adjustment
        total_expected = 0.0
        age_adjusted_pipeline = 0.0

        for stage, arr in pipeline_by_stage.items():
            if stage not in conversion:
                continue

            rate = conversion[stage]

            # Apply age adjustment if we have data for this stage
            if stage in stage_adjustments and stage_adjustments[stage]["total_arr"] > 0:
                adjustment = (
                    stage_adjustments[stage]["adjusted_arr"] /
                    stage_adjustments[stage]["total_arr"]
                )
            else:
                adjustment = 1.0

            adjusted_arr = arr * adjustment
            age_adjusted_pipeline += adjusted_arr
            expected = adjusted_arr * rate
            expected_by_stage[stage] = expected
            total_expected += expected

    # Calculate confidence interval using historical variance
    # Assuming normal distribution, 80% CI is approximately +/- 1.28 standard deviations
    z_score = 1.28 if confidence_level == 0.80 else 1.96  # 1.96 for 95%
    std_dev = total_expected * historical_variance
    low_estimate = max(0, total_expected - z_score * std_dev)
    high_estimate = total_expected + z_score * std_dev

    # Calculate probability of hitting target
    # Using normal CDF approximation
    if std_dev > 0 and target > 0:
        z = (total_expected - target) / std_dev
        # Approximate CDF using error function
        prob = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    else:
        prob = 1.0 if total_expected >= target else 0.0

    return PipelineForecast(
        as_of_date=as_of,
        target_period=target_period,
        target=target,
        pipeline_by_stage=pipeline_by_stage,
        age_adjusted_pipeline=age_adjusted_pipeline,
        expected_bookings=total_expected,
        low_estimate=low_estimate,
        high_estimate=high_estimate,
        probability_of_hitting_target=prob,
        expected_by_stage=expected_by_stage,
    )


def calculate_channel_requirements(
    target_bookings: float,
    target_period: str,
    source_mix: dict[str, float],
    pipeline_by_source: Optional[dict[str, dict[date, float]]] = None,
    close_rate_distribution: Optional[dict[int, float]] = None,
    pipeline_coverage_ratio: float = 3.5,
) -> ChannelBreakdown:
    """
    Split total pipeline requirement by source channel.

    Uses close_rate_distribution to work backward from bookings target to
    monthly pipeline creation requirements.

    Args:
        target_bookings: Total bookings target for the period
        target_period: Period label (e.g., "Q2FY26")
        source_mix: Channel mix (e.g., {"sdr_sourced": 0.40, ...})
        pipeline_by_source: Actual pipeline created by source and month
        close_rate_distribution: Monthly close rate distribution (month -> %)
        pipeline_coverage_ratio: Required pipeline coverage multiple (default 3.5x)

    Returns:
        ChannelBreakdown with requirements by channel
    """
    # Calculate total pipeline required (with coverage ratio)
    total_pipeline_required = target_bookings * pipeline_coverage_ratio

    # Friendly channel names
    channel_names = {
        "sdr_sourced": "SDR Sourced",
        "marketing_sourced": "Marketing",
        "ae_sourced": "AE Sourced",
        "leadership_sourced": "Leadership",
        "se_sourced": "SE Sourced",
        "unknown": "Unknown",
    }

    # Calculate requirements per channel
    channels = {}

    for source_key, mix_pct in source_mix.items():
        if mix_pct <= 0:
            continue

        channel_required = total_pipeline_required * mix_pct
        channel_name = channel_names.get(source_key, source_key)

        # Get actual pipeline for this channel
        channel_actual = 0.0
        monthly_actuals = {}

        if pipeline_by_source and source_key in pipeline_by_source:
            source_data = pipeline_by_source[source_key]
            for month, arr in source_data.items():
                monthly_actuals[month] = arr
                channel_actual += arr

        # Calculate gap
        gap = max(0, channel_required - channel_actual)

        channels[channel_name] = ChannelRequirement(
            channel=channel_name,
            total_required=channel_required,
            total_actual=channel_actual,
            gap=gap,
            monthly_actuals=monthly_actuals,
        )

    return ChannelBreakdown(
        target_bookings=target_bookings,
        target_period=target_period,
        channels=channels,
    )


def calculate_rolling_forecast(
    monthly_bookings: dict,
    target: float,
    target_end: date,
    target_period: str = "",
    trailing_months: int = 3,
    period_start: Optional[date] = None,
) -> RollingForecast:
    """
    Calculate run rate from trailing average and project forward.

    Args:
        monthly_bookings: Historical bookings by month (date or str -> float)
        target: Bookings target for the period
        target_end: Period end date
        target_period: Period label (e.g., "Q2FY26")
        trailing_months: Number of months for run rate calculation (default 3)
        period_start: Period start date (for YTD calculation)

    Returns:
        RollingForecast with trajectory projection
    """
    as_of = date.today()

    # Normalize monthly_bookings keys to date objects
    normalized_bookings = {}
    for k, v in monthly_bookings.items():
        if isinstance(k, date):
            normalized_bookings[k] = v
        elif isinstance(k, str):
            # Try to parse as YYYY-MM or YYYY-MM-DD
            try:
                if len(k) == 7:
                    normalized_bookings[date.fromisoformat(k + "-01")] = v
                else:
                    normalized_bookings[date.fromisoformat(k)] = v
            except ValueError:
                continue

    # Sort by date
    sorted_months = sorted(normalized_bookings.keys())

    # Calculate YTD bookings (from period start to now)
    bookings_ytd = 0.0
    months_with_data = []

    for month in sorted_months:
        if period_start and month < period_start:
            continue
        if month <= as_of:
            bookings_ytd += normalized_bookings[month]
            months_with_data.append(month)

    months_elapsed = len(months_with_data)

    # Calculate trailing run rate
    if len(sorted_months) >= trailing_months:
        recent_months = sorted_months[-trailing_months:]
        recent_total = sum(normalized_bookings.get(m, 0) for m in recent_months)
        monthly_run_rate = recent_total / trailing_months
    elif months_elapsed > 0:
        monthly_run_rate = bookings_ytd / months_elapsed
    else:
        monthly_run_rate = 0.0

    # Calculate months remaining
    # Count full months between now and target_end
    months_remaining = 0
    check_date = date(as_of.year, as_of.month, 1)
    while check_date <= target_end:
        if check_date > as_of:
            months_remaining += 1
        check_date = date(
            check_date.year + (check_date.month // 12),
            (check_date.month % 12) + 1,
            1
        )

    # Project forward
    projected_additional = monthly_run_rate * months_remaining
    projected_bookings = bookings_ytd + projected_additional

    # Calculate gap and required rate
    projected_gap = max(0, target - projected_bookings)
    remaining_to_close = target - bookings_ytd

    if months_remaining > 0:
        required_rate = remaining_to_close / months_remaining
    else:
        required_rate = remaining_to_close if remaining_to_close > 0 else 0

    # Calculate rate increase needed
    if monthly_run_rate > 0:
        rate_increase_needed = (required_rate - monthly_run_rate) / monthly_run_rate
    else:
        rate_increase_needed = 0.0

    rate_increase_needed = max(0, rate_increase_needed)

    # Build monthly projection
    monthly_projection = []
    cumulative = bookings_ytd
    projection_date = date(as_of.year, as_of.month, 1)

    for i in range(months_remaining):
        projection_date = date(
            projection_date.year + (projection_date.month // 12),
            (projection_date.month % 12) + 1,
            1
        )
        cumulative += monthly_run_rate
        monthly_projection.append({
            "month": projection_date.isoformat()[:7],
            "projected_bookings": monthly_run_rate,
            "cumulative": cumulative,
        })

    return RollingForecast(
        as_of_date=as_of,
        target_period=target_period,
        target=target,
        bookings_ytd=bookings_ytd,
        months_elapsed=months_elapsed,
        monthly_run_rate=monthly_run_rate,
        months_remaining=months_remaining,
        projected_bookings=projected_bookings,
        projected_gap=projected_gap,
        required_rate_to_hit_target=required_rate,
        rate_increase_needed=rate_increase_needed,
        monthly_projection=monthly_projection,
    )


def load_forecast_config(config_path: Optional[str] = None) -> dict:
    """
    Load forecast configuration from assumptions.yaml.

    Args:
        config_path: Optional path to config file

    Returns:
        Forecast configuration dictionary
    """
    if config_path:
        path = Path(config_path)
        if path.suffix in {".yml", ".yaml"}:
            config = load_yaml_resource(path.name, config_dir=path.parent)
        else:
            config = load_yaml_resource("assumptions.yaml", config_dir=path)
    else:
        config = load_yaml_resource("assumptions.yaml")

    return config.get("forecast", {})


def format_currency(value: float) -> str:
    """Format value as currency string."""
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value / 1_000:.0f}K"
    else:
        return f"${value:,.0f}"

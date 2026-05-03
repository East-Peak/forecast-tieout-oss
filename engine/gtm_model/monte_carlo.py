"""
Monte Carlo simulation for GTM forecasting.

Provides deal-level simulation with probabilistic stage transitions,
confidence intervals, and variance attribution by channel.

Key features:
- Deal-level simulation (not aggregate) for accurate probability distributions
- Beta priors for conversion rates (handles sparse data)
- Age-based probability decay for stale deals
- Variance attribution showing which channels drive gaps to plan
- Stage×Age conversion matrix (v3.3) - dynamic rates by stage AND deal age
- Bimodal sales cycle modeling (v3.3) - fast movers vs long haulers

Usage:
    from gtm_model.monte_carlo import (
        run_monte_carlo_forecast,
        calculate_variance_attribution,
        MonteCarloResult,
    )

    # Run simulation
    result = run_monte_carlo_forecast(
        deals=pipeline_deals,
        target=12_000_000,
        n_simulations=1000,
    )

    print(f"P50 forecast: ${result.p50:,.0f}")
    print(f"Probability of hitting target: {result.prob_hit_target:.0%}")

    # Get variance attribution
    attribution = calculate_variance_attribution(
        deals=pipeline_deals,
        target=12_000_000,
        expected_mix={"sdr_sourced": 0.40, "marketing_sourced": 0.16, ...},
    )
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional
import random
import math

from .rate_defaults import get_default_stage_win_rates
from .tieout.runtime.env import load_yaml_resource


# =============================================================================
# CONSTANTS & DEFAULTS
# =============================================================================

# Default stage transition matrix
# Rows: current stage, Columns: [stay, advance, won, lost]
# Based on typical B2B SaaS patterns - tune with your data
DEFAULT_TRANSITION_MATRIX = {
    # From S2 (Scope): 35% advance to S3, 10% won (fast track), 25% lost, 30% stay
    "S2": {"S2": 0.30, "S3": 0.35, "won": 0.10, "lost": 0.25},
    # From S3 (Tech Val): 40% advance to S4, 15% won, 20% lost, 25% stay
    "S3": {"S3": 0.25, "S4": 0.40, "won": 0.15, "lost": 0.20},
    # From S4 (Business Case): 50% advance to S5, 20% won, 15% lost, 15% stay
    "S4": {"S4": 0.15, "S5": 0.50, "won": 0.20, "lost": 0.15},
    # From S5 (Vendor Choice): 70% won, 15% lost, 15% stay
    "S5": {"S5": 0.15, "won": 0.70, "lost": 0.15},
}

# Stage-to-won conversion rates (all-inclusive: won / (won + lost + open))
# Shared with the central rate registry to avoid config drift.
DEFAULT_STAGE_WIN_RATES = get_default_stage_win_rates()

# Beta distribution priors for conversion rates
# Beta(alpha, beta) where mean = alpha / (alpha + beta)
# Lower alpha+beta = more uncertainty, higher = more confident
DEFAULT_BETA_PRIORS = {
    "S2_to_won": (2, 19),    # Mean ~10%, wide uncertainty
    "S3_to_won": (5, 16),    # Mean ~24%
    "S4_to_won": (10, 11),   # Mean ~48%
    "S5_to_won": (16, 4),    # Mean ~80%
}

# Age decay multipliers (days in stage -> probability multiplier)
# LEGACY: Use get_stage_age_conversion_rate() for stage-specific decay
AGE_DECAY = [
    (30, 1.00),    # 0-30 days: full probability
    (60, 0.85),    # 31-60 days: 85%
    (90, 0.70),    # 61-90 days: 70%
    (120, 0.55),   # 91-120 days: 55%
    (180, 0.40),   # 121-180 days: 40%
    (999, 0.25),   # 180+ days: 25%
]

# =============================================================================
# STAGE × AGE CONVERSION MATRIX (v3.3)
# =============================================================================
# Dynamic conversion rates where older deals in earlier stages decay faster

# DEPRECATED - Stage×Age decay not supported by data 
# Base rates updated 2026-02-03 for consistency if ever re-enabled
STAGE_AGE_CONVERSION = {
    "S2": {
        "days_0_30": 0.18,     # Fresh: full 18%
        "days_31_60": 0.14,    # 20% decay
        "days_61_90": 0.11,    # 40% decay
        "days_90_plus": 0.05,  # 70% decay
    },
    "S3": {
        "days_0_30": 0.42,     # Fresh: full 42%
        "days_31_60": 0.36,    # 15% decay
        "days_61_90": 0.29,    # 30% decay
        "days_90_plus": 0.17,  # 60% decay
    },
    "S4": {
        "days_0_30": 0.58,     # Fresh: full 58%
        "days_31_60": 0.52,    # 10% decay
        "days_61_90": 0.46,    # 20% decay
        "days_90_plus": 0.35,  # 40% decay
    },
    "S5": {
        "days_0_30": 0.61,     # Fresh: full 61%
        "days_31_60": 0.58,    # 5% decay
        "days_61_90": 0.55,    # 10% decay
        "days_90_plus": 0.49,  # 20% decay
    },
}

# =============================================================================
# BIMODAL SALES CYCLE DISTRIBUTION (v3.3)
# =============================================================================
# Two distinct populations: fast movers and long haulers

BIMODAL_SALES_CYCLE = {
    "fast_movers": {
        "weight": 0.35,
        "mean_days": 75,
        "std_days": 20,
    },
    "long_haulers": {
        "weight": 0.65,
        "mean_days": 150,
        "std_days": 45,
    },
}

# Deal size variance (log-normal parameters)
# Deals vary around their stated value
DEAL_SIZE_VARIANCE = 0.15  # 15% standard deviation


# =============================================================================
# SLIP PROBABILITY MODEL
# =============================================================================
# Probability a deal closes in the target quarter vs. slipping. Default
# parameters reflect typical B2B SaaS observation (most won deals slip at
# least one quarter from their original close-date estimate); override
# via slip_rates.yaml in your profile.

def load_slip_rates() -> dict:
    """
    Load slip probability rates from config file.

    Returns:
        Dict with slip rates configuration, or defaults if file not found
    """
    try:
        loaded = load_yaml_resource("slip_rates.yaml")
        if loaded:
            return loaded
    except Exception:
        pass

        # Return default values
    return {
        "pusher_discount": {"probability": 0.35},
        "low_time_remaining": {"threshold_days": 14, "probability": 0.10, "exclude_stages": ["S5", "S6"]},
        "stage_rates": {
            "S5": {"rates": {30: 0.80, 14: 0.60, 0: 0.40}},
            "S4": {"rates": {45: 0.60, 30: 0.40, 0: 0.20}},
            "S3": {"rates": {60: 0.40, 45: 0.25, 0: 0.10}},
            "S2": {"rates": {90: 0.20, 60: 0.10, 0: 0.05}},
        },
        "default_probability": 0.30,
    }


def get_in_quarter_probability(
    stage: str,
    days_to_quarter_end: int,
    has_pushed: bool,
    slip_rates: Optional[dict] = None,
) -> float:
    """
    Calculate probability a deal closes in the target quarter.

    Predictors used: stage, days remaining in quarter, and whether the
    deal has previously pushed its CloseDate (pushed deals close in-
    quarter much less often). Default parameters reflect typical B2B
    SaaS behavior; override via slip_rates.yaml in your profile.

    Args:
        stage: Deal stage (S2, S3, S4, S5)
        days_to_quarter_end: Days remaining until quarter end
        has_pushed: Whether deal has ever pushed its CloseDate
        slip_rates: Optional override for slip rates config

    Returns:
        Probability (0.0 to 1.0) that deal closes in target quarter
    """
    if slip_rates is None:
        slip_rates = load_slip_rates()

    # Deals that have pushed get heavy discount
    if has_pushed:
        return slip_rates.get("pusher_discount", {}).get("probability", 0.35)

    # Check for low time remaining (except late-stage deals)
    low_time = slip_rates.get("low_time_remaining", {})
    threshold = low_time.get("threshold_days", 14)
    exclude = low_time.get("exclude_stages", ["S5", "S6"])

    if days_to_quarter_end < threshold and stage not in exclude:
        return low_time.get("probability", 0.10)

    # Stage-based probability given time remaining
    stage_rates = slip_rates.get("stage_rates", {})

    if stage in stage_rates:
        rates = stage_rates[stage].get("rates", {})

        # Find applicable rate based on days remaining
        # Rates are keyed by minimum days threshold
        for min_days in sorted(rates.keys(), reverse=True):
            if days_to_quarter_end >= int(min_days):
                return rates[min_days]

        # Fallback to lowest threshold (default)
        return rates.get(0, 0.30)

    # Unknown stage
    return slip_rates.get("default_probability", 0.30)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class Deal:
    """A single deal in the pipeline for simulation."""
    id: str
    name: str
    stage: str
    arr: float
    days_in_stage: int = 0
    source: str = "unknown"
    close_date: Optional[date] = None
    segment: str = "unknown"
    has_pushed: bool = False  # True if deal has ever pushed its CloseDate

    def __post_init__(self):
        if self.arr < 0:
            raise ValueError(f"Deal ARR cannot be negative: {self.arr}")
        if self.stage not in ("S2", "S3", "S4", "S5"):
            # Allow but warn - might be S0/S1 which we skip
            pass


@dataclass
class SimulationRun:
    """Result of a single Monte Carlo simulation run."""
    total_won: float
    deals_won: int
    deals_lost: int
    by_source: dict[str, float] = field(default_factory=dict)
    by_stage: dict[str, float] = field(default_factory=dict)


@dataclass
class MonteCarloResult:
    """
    Complete result of Monte Carlo simulation.

    Contains percentiles, probability distributions, and deal-level details.
    """
    # Context
    n_simulations: int
    n_deals: int
    total_pipeline: float
    target: float

    # Percentile outcomes
    p10: float = 0.0   # 10th percentile (pessimistic)
    p25: float = 0.0   # 25th percentile
    p50: float = 0.0   # 50th percentile (median)
    p75: float = 0.0   # 75th percentile
    p90: float = 0.0   # 90th percentile (optimistic)
    mean: float = 0.0
    std_dev: float = 0.0

    # Target analysis
    prob_hit_target: float = 0.0
    expected_gap: float = 0.0

    # Distribution (for histograms)
    distribution: list[float] = field(default_factory=list)

    # Breakdown
    by_source: dict[str, dict] = field(default_factory=dict)
    by_stage: dict[str, dict] = field(default_factory=dict)

    @property
    def confidence_range(self) -> str:
        """80% confidence interval as string."""
        return f"${self.p10:,.0f} - ${self.p90:,.0f}"

    @property
    def median_attainment(self) -> float:
        """Median attainment vs target."""
        return self.p50 / self.target if self.target > 0 else 0.0

    def summary(self) -> str:
        """Return formatted text summary."""
        lines = [
            f"Monte Carlo Forecast ({self.n_simulations:,} simulations)",
            f"=" * 60,
            f"Pipeline: ${self.total_pipeline:,.0f} ({self.n_deals} deals)",
            f"Target:   ${self.target:,.0f}",
            "",
            "Forecast Distribution:",
            f"  P10 (pessimistic):  ${self.p10:,.0f}",
            f"  P25:                ${self.p25:,.0f}",
            f"  P50 (median):       ${self.p50:,.0f}",
            f"  P75:                ${self.p75:,.0f}",
            f"  P90 (optimistic):   ${self.p90:,.0f}",
            "",
            f"  Mean:               ${self.mean:,.0f}",
            f"  Std Dev:            ${self.std_dev:,.0f}",
            "",
            f"Target Analysis:",
            f"  Prob of hitting target: {self.prob_hit_target:.0%}",
            f"  Expected gap:           ${self.expected_gap:,.0f}",
        ]

        if self.by_source:
            lines.extend(["", "By Source (P50):"])
            for source, data in sorted(self.by_source.items()):
                lines.append(f"  {source:<20} ${data.get('p50', 0):>10,.0f}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "n_simulations": self.n_simulations,
            "n_deals": self.n_deals,
            "total_pipeline": self.total_pipeline,
            "target": self.target,
            "percentiles": {
                "p10": self.p10,
                "p25": self.p25,
                "p50": self.p50,
                "p75": self.p75,
                "p90": self.p90,
            },
            "mean": self.mean,
            "std_dev": self.std_dev,
            "prob_hit_target": self.prob_hit_target,
            "expected_gap": self.expected_gap,
            "confidence_range": self.confidence_range,
            "median_attainment": self.median_attainment,
            "by_source": self.by_source,
            "by_stage": self.by_stage,
        }


@dataclass
class VarianceAttribution:
    """
    Attribution of forecast variance by channel/source.

    Shows which channels are contributing positively or negatively
    to the gap between expected and target.
    """
    target: float
    expected: float  # P50 or mean forecast
    total_gap: float

    # By channel
    channels: dict[str, dict] = field(default_factory=dict)

    # Ranked contributors
    top_contributors: list[dict] = field(default_factory=list)

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Return formatted text summary."""
        lines = [
            "Variance Attribution",
            "=" * 60,
            f"Target:    ${self.target:,.0f}",
            f"Expected:  ${self.expected:,.0f}",
            f"Gap:       ${self.total_gap:,.0f}",
            "",
            "Channel Contribution to Gap:",
            f"  {'Channel':<20} {'Expected':>12} {'Required':>12} {'Variance':>12} {'% of Gap':>10}",
            "  " + "-" * 68,
        ]

        for name, data in sorted(self.channels.items(), key=lambda x: x[1].get('variance', 0)):
            variance = data.get('variance', 0)
            pct_of_gap = data.get('pct_of_gap', 0)
            sign = "+" if variance > 0 else ""
            lines.append(
                f"  {name:<20} ${data.get('expected', 0):>10,.0f} "
                f"${data.get('required', 0):>10,.0f} "
                f"{sign}${variance:>10,.0f} {pct_of_gap:>9.0%}"
            )

        if self.recommendations:
            lines.extend(["", "Recommendations:"])
            for rec in self.recommendations:
                lines.append(f"  - {rec}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "target": self.target,
            "expected": self.expected,
            "total_gap": self.total_gap,
            "channels": self.channels,
            "top_contributors": self.top_contributors,
            "recommendations": self.recommendations,
        }


# =============================================================================
# PROBABILITY HELPERS
# =============================================================================

def sample_beta(alpha: float, beta: float) -> float:
    """
    Sample from a Beta distribution.

    Uses the gamma function method for generating beta variates.
    """
    if alpha <= 0 or beta <= 0:
        raise ValueError(f"Alpha and beta must be positive: {alpha}, {beta}")

    # Generate using gamma variates
    x = random.gammavariate(alpha, 1)
    y = random.gammavariate(beta, 1)
    return x / (x + y)


def get_age_multiplier(days_in_stage: int) -> float:
    """Get probability multiplier based on deal age."""
    for threshold, multiplier in AGE_DECAY:
        if days_in_stage <= threshold:
            return multiplier
    return 0.25


def get_age_bucket(days_in_stage: int) -> str:
    """Get age bucket key for stage×age matrix lookup."""
    if days_in_stage <= 30:
        return "days_0_30"
    elif days_in_stage <= 60:
        return "days_31_60"
    elif days_in_stage <= 90:
        return "days_61_90"
    else:
        return "days_90_plus"


def get_stage_age_conversion_rate(
    stage: str,
    days_in_stage: int,
    stage_age_matrix: Optional[dict] = None,
) -> float:
    """
    Get conversion rate based on both stage AND deal age.

    Uses the stage×age conversion matrix for more accurate forecasting.
    Older deals in earlier stages have steeper decay than late-stage deals.

    Args:
        stage: Deal stage (S2, S3, S4, S5)
        days_in_stage: Days the deal has been in current stage
        stage_age_matrix: Optional override matrix (uses default if None)

    Returns:
        Conversion rate (0.0 to 1.0)

    Example:
        >>> get_stage_age_conversion_rate("S2", 15)
        0.18  # Fresh S2 deal
        >>> get_stage_age_conversion_rate("S2", 100)
        0.05  # Stale S2 deal (70% decay)
    """
    matrix = stage_age_matrix or STAGE_AGE_CONVERSION

    if stage not in matrix:
        # Fall back to default rates for unknown stages
        return get_default_stage_win_rates().get(stage, 0.0)

    age_bucket = get_age_bucket(days_in_stage)
    stage_rates = matrix[stage]

    return stage_rates.get(age_bucket, stage_rates.get("days_90_plus", 0.0))


def sample_sales_cycle(
    bimodal_config: Optional[dict] = None,
) -> float:
    """
    Sample a sales cycle duration from bimodal distribution.

    Models the reality that deals follow two distinct patterns:
    - Fast movers: Champion-driven, 60-90 days
    - Long haulers: Committee-driven, 180+ days

    Args:
        bimodal_config: Optional config override (uses default if None)

    Returns:
        Sampled sales cycle in days

    Example:
        >>> cycles = [sample_sales_cycle() for _ in range(1000)]
        >>> # Distribution should be bimodal, not normal
    """
    config = bimodal_config or BIMODAL_SALES_CYCLE

    fast = config.get("fast_movers", {})
    slow = config.get("long_haulers", {})

    # Choose which population to sample from
    if random.random() < fast.get("weight", 0.35):
        # Fast mover
        mean = fast.get("mean_days", 75)
        std = fast.get("std_days", 20)
    else:
        # Long hauler
        mean = slow.get("mean_days", 150)
        std = slow.get("std_days", 45)

    # Sample from normal distribution, clamp to reasonable bounds
    cycle = random.gauss(mean, std)
    return max(30, min(365, cycle))  # Between 30 days and 1 year


def project_close_date(
    deal: "Deal",
    as_of_date: Optional["date"] = None,
    bimodal_config: Optional[dict] = None,
) -> "date":
    """
    Project when a deal might close using bimodal sales cycle model.

    Args:
        deal: Deal object with stage and days_in_stage
        as_of_date: Reference date (defaults to today)
        bimodal_config: Optional bimodal config override

    Returns:
        Projected close date
    """
    from datetime import date, timedelta

    if as_of_date is None:
        as_of_date = date.today()

    # Sample total sales cycle
    total_cycle = sample_sales_cycle(bimodal_config)

    # Estimate days remaining based on stage
    # Rough stage progression: S2=25%, S3=50%, S4=75%, S5=90%
    stage_progress = {
        "S2": 0.25,
        "S3": 0.50,
        "S4": 0.75,
        "S5": 0.90,
    }

    progress = stage_progress.get(deal.stage, 0.25)
    days_remaining = total_cycle * (1 - progress)

    # Account for time already spent in stage
    days_remaining = max(7, days_remaining - deal.days_in_stage * 0.5)

    return as_of_date + timedelta(days=int(days_remaining))


def sample_deal_value(base_value: float, variance: float = DEAL_SIZE_VARIANCE) -> float:
    """
    Sample deal value with log-normal variance.

    Deals can close at slightly different values than stated.
    """
    if base_value <= 0:
        return 0

    # Log-normal: mean stays at base_value, with specified variance
    mu = math.log(base_value) - (variance ** 2) / 2
    sigma = variance
    return random.lognormvariate(mu, sigma)


# =============================================================================
# SIMULATION ENGINE
# =============================================================================

def simulate_deal(
    deal: Deal,
    transition_matrix: dict[str, dict[str, float]],
    beta_priors: dict[str, tuple[float, float]],
    use_age_decay: bool = True,
    use_stage_age_matrix: bool = False,
    stage_age_matrix: Optional[dict] = None,
    max_iterations: int = 20,
    use_slip_probability: bool = False,
    days_to_quarter_end: Optional[int] = None,
    slip_rates: Optional[dict] = None,
) -> tuple[bool, float]:
    """
    Simulate a single deal through the pipeline.

    Args:
        deal: The deal to simulate
        transition_matrix: Stage transition probabilities
        beta_priors: Beta distribution parameters for win rates
        use_age_decay: Whether to apply age-based probability decay (legacy)
        use_stage_age_matrix: Whether to use stage×age conversion matrix (v3.3)
        stage_age_matrix: Optional override for stage×age matrix
        max_iterations: Max steps before forcing resolution
        use_slip_probability: Whether to apply slip probability (v3.5)
        days_to_quarter_end: Days until quarter end (required if use_slip_probability)
        slip_rates: Optional override for slip rates config

    Returns:
        Tuple of (won: bool, value: float)
        Note: With slip probability, "won" means "won AND closed in quarter"
    """
    current_stage = deal.stage

    # Skip if not in pipeline stages
    if current_stage not in ("S2", "S3", "S4", "S5"):
        return (False, 0.0)

    # Determine age multiplier based on mode
    if use_stage_age_matrix:
        # Use stage×age conversion matrix (more precise)
        base_rate = get_default_stage_win_rates().get(current_stage, 0.1)
        adjusted_rate = get_stage_age_conversion_rate(
            current_stage, deal.days_in_stage, stage_age_matrix
        )
        age_multiplier = adjusted_rate / base_rate if base_rate > 0 else 1.0
    elif use_age_decay:
        # Legacy: flat age decay across all stages
        age_multiplier = get_age_multiplier(deal.days_in_stage)
    else:
        age_multiplier = 1.0

    iterations = 0
    while iterations < max_iterations:
        iterations += 1

        if current_stage not in transition_matrix:
            # Unknown stage, assume lost
            return (False, 0.0)

        transitions = transition_matrix[current_stage]

        # Adjust win probability by age
        adjusted_transitions = {}
        total = 0
        for next_state, prob in transitions.items():
            if next_state == "won":
                adjusted_prob = prob * age_multiplier
            elif next_state == "lost":
                # Increase lost probability to compensate
                adjusted_prob = prob + (transitions.get("won", 0) * (1 - age_multiplier))
            else:
                adjusted_prob = prob
            adjusted_transitions[next_state] = adjusted_prob
            total += adjusted_prob

        # Normalize
        for state in adjusted_transitions:
            adjusted_transitions[state] /= total

        # Sample next state
        rand = random.random()
        cumulative = 0
        next_stage = "lost"  # Default

        for state, prob in adjusted_transitions.items():
            cumulative += prob
            if rand < cumulative:
                next_stage = state
                break

        # Check terminal states
        if next_stage == "won":
            # Sample final value with some variance
            final_value = sample_deal_value(deal.arr)

            # Apply slip probability: even if deal wins, does it close THIS quarter?
            if use_slip_probability and days_to_quarter_end is not None:
                in_quarter_prob = get_in_quarter_probability(
                    stage=deal.stage,  # Use original stage, not current
                    days_to_quarter_end=days_to_quarter_end,
                    has_pushed=deal.has_pushed,
                    slip_rates=slip_rates,
                )

                # Sample whether deal closes in quarter
                if random.random() > in_quarter_prob:
                    # Deal wins but slips to next quarter
                    return (False, 0.0)

            return (True, final_value)
        elif next_stage == "lost":
            return (False, 0.0)
        else:
            current_stage = next_stage

    # Max iterations reached, assume lost
    return (False, 0.0)


def run_single_simulation(
    deals: list[Deal],
    transition_matrix: dict[str, dict[str, float]],
    beta_priors: dict[str, tuple[float, float]],
    use_age_decay: bool = True,
    use_stage_age_matrix: bool = False,
    stage_age_matrix: Optional[dict] = None,
    use_slip_probability: bool = False,
    days_to_quarter_end: Optional[int] = None,
    slip_rates: Optional[dict] = None,
) -> SimulationRun:
    """
    Run a single Monte Carlo simulation across all deals.

    Args:
        deals: List of deals to simulate
        transition_matrix: Stage transition probabilities
        beta_priors: Beta priors for conversion rates
        use_age_decay: Whether to apply age-based probability decay (legacy)
        use_stage_age_matrix: Whether to use stage×age conversion matrix (v3.3)
        stage_age_matrix: Optional override for stage×age matrix
        use_slip_probability: Whether to apply slip probability (v3.5)
        days_to_quarter_end: Days until quarter end (required if use_slip_probability)
        slip_rates: Optional override for slip rates config

    Returns:
        SimulationRun with results
    """
    total_won = 0.0
    deals_won = 0
    deals_lost = 0
    by_source: dict[str, float] = {}
    by_stage: dict[str, float] = {}

    for deal in deals:
        won, value = simulate_deal(
            deal=deal,
            transition_matrix=transition_matrix,
            beta_priors=beta_priors,
            use_age_decay=use_age_decay,
            use_stage_age_matrix=use_stage_age_matrix,
            stage_age_matrix=stage_age_matrix,
            use_slip_probability=use_slip_probability,
            days_to_quarter_end=days_to_quarter_end,
            slip_rates=slip_rates,
        )

        if won:
            total_won += value
            deals_won += 1

            # Track by source
            source = deal.source or "unknown"
            by_source[source] = by_source.get(source, 0) + value

            # Track by starting stage
            stage = deal.stage
            by_stage[stage] = by_stage.get(stage, 0) + value
        else:
            deals_lost += 1

    return SimulationRun(
        total_won=total_won,
        deals_won=deals_won,
        deals_lost=deals_lost,
        by_source=by_source,
        by_stage=by_stage,
    )


def run_monte_carlo_forecast(
    deals: list[Deal],
    target: float,
    n_simulations: int = 1000,
    transition_matrix: Optional[dict] = None,
    beta_priors: Optional[dict] = None,
    use_age_decay: bool = True,
    use_stage_age_matrix: bool = False,
    stage_age_matrix: Optional[dict] = None,
    seed: Optional[int] = None,
    use_slip_probability: bool = False,
    quarter_end_date: Optional[date] = None,
    slip_rates: Optional[dict] = None,
) -> MonteCarloResult:
    """
    Run full Monte Carlo simulation for pipeline forecast.

    Args:
        deals: List of Deal objects in pipeline
        target: Bookings target for the period
        n_simulations: Number of simulation runs (default 1000)
        transition_matrix: Override stage transition probabilities
        beta_priors: Override beta distribution priors
        use_age_decay: Whether to apply age-based probability decay (legacy)
        use_stage_age_matrix: Whether to use stage×age conversion matrix (v3.3)
        stage_age_matrix: Optional override for stage×age matrix
        seed: Random seed for reproducibility
        use_slip_probability: Whether to apply slip probability (v3.5)
        quarter_end_date: End date of target quarter (required if use_slip_probability)
        slip_rates: Optional override for slip rates config

    Returns:
        MonteCarloResult with percentiles, distribution, and breakdowns
    """
    if seed is not None:
        random.seed(seed)

    matrix = transition_matrix or DEFAULT_TRANSITION_MATRIX
    priors = beta_priors or DEFAULT_BETA_PRIORS

    # Filter to pipeline stages only
    pipeline_deals = [d for d in deals if d.stage in ("S2", "S3", "S4", "S5")]
    total_pipeline = sum(d.arr for d in pipeline_deals)

    if not pipeline_deals:
        return MonteCarloResult(
            n_simulations=n_simulations,
            n_deals=0,
            total_pipeline=0,
            target=target,
            expected_gap=target,
        )

    # Calculate days to quarter end for slip probability
    days_to_quarter_end = None
    if use_slip_probability and quarter_end_date:
        days_to_quarter_end = (quarter_end_date - date.today()).days
        days_to_quarter_end = max(0, days_to_quarter_end)  # Can't be negative

    # Run simulations
    results: list[float] = []
    source_results: dict[str, list[float]] = {}
    stage_results: dict[str, list[float]] = {}

    for _ in range(n_simulations):
        run = run_single_simulation(
            deals=pipeline_deals,
            transition_matrix=matrix,
            beta_priors=priors,
            use_age_decay=use_age_decay,
            use_stage_age_matrix=use_stage_age_matrix,
            stage_age_matrix=stage_age_matrix,
            use_slip_probability=use_slip_probability,
            days_to_quarter_end=days_to_quarter_end,
            slip_rates=slip_rates,
        )
        results.append(run.total_won)

        # Track by source
        for source, value in run.by_source.items():
            if source not in source_results:
                source_results[source] = []
            source_results[source].append(value)

        # Track by stage
        for stage, value in run.by_stage.items():
            if stage not in stage_results:
                stage_results[stage] = []
            stage_results[stage].append(value)

    # Calculate percentiles
    sorted_results = sorted(results)
    n = len(sorted_results)

    def percentile(p: float) -> float:
        idx = int(p * n)
        return sorted_results[min(idx, n - 1)]

    p10 = percentile(0.10)
    p25 = percentile(0.25)
    p50 = percentile(0.50)
    p75 = percentile(0.75)
    p90 = percentile(0.90)

    mean = sum(results) / n
    variance = sum((x - mean) ** 2 for x in results) / n
    std_dev = math.sqrt(variance)

    # Probability of hitting target
    hits = sum(1 for r in results if r >= target)
    prob_hit_target = hits / n

    # Expected gap
    expected_gap = max(0, target - p50)

    # Aggregate source breakdowns
    by_source = {}
    for source, values in source_results.items():
        sorted_vals = sorted(values)
        m = len(sorted_vals)
        by_source[source] = {
            "p10": sorted_vals[int(0.10 * m)] if m > 0 else 0,
            "p50": sorted_vals[int(0.50 * m)] if m > 0 else 0,
            "p90": sorted_vals[int(0.90 * m)] if m > 0 else 0,
            "mean": sum(values) / m if m > 0 else 0,
        }

    # Aggregate stage breakdowns
    by_stage = {}
    for stage, values in stage_results.items():
        sorted_vals = sorted(values)
        m = len(sorted_vals)
        by_stage[stage] = {
            "p10": sorted_vals[int(0.10 * m)] if m > 0 else 0,
            "p50": sorted_vals[int(0.50 * m)] if m > 0 else 0,
            "p90": sorted_vals[int(0.90 * m)] if m > 0 else 0,
            "mean": sum(values) / m if m > 0 else 0,
        }

    return MonteCarloResult(
        n_simulations=n_simulations,
        n_deals=len(pipeline_deals),
        total_pipeline=total_pipeline,
        target=target,
        p10=p10,
        p25=p25,
        p50=p50,
        p75=p75,
        p90=p90,
        mean=mean,
        std_dev=std_dev,
        prob_hit_target=prob_hit_target,
        expected_gap=expected_gap,
        distribution=results,
        by_source=by_source,
        by_stage=by_stage,
    )


# =============================================================================
# VARIANCE ATTRIBUTION
# =============================================================================

def calculate_variance_attribution(
    deals: list[Deal],
    target: float,
    expected_mix: dict[str, float],
    monte_carlo_result: Optional[MonteCarloResult] = None,
    n_simulations: int = 1000,
) -> VarianceAttribution:
    """
    Calculate variance attribution by channel/source.

    Shows which channels are contributing positively or negatively
    to the gap between forecast and target.

    Args:
        deals: List of Deal objects in pipeline
        target: Bookings target for the period
        expected_mix: Expected source mix (e.g., {"sdr_sourced": 0.40, ...})
        monte_carlo_result: Pre-computed MC result (will compute if not provided)
        n_simulations: Number of simulations if computing

    Returns:
        VarianceAttribution with channel-level breakdown
    """
    # Run Monte Carlo if not provided
    if monte_carlo_result is None:
        monte_carlo_result = run_monte_carlo_forecast(
            deals=deals,
            target=target,
            n_simulations=n_simulations,
        )

    expected = monte_carlo_result.p50
    total_gap = target - expected

    # Calculate required contribution by channel
    channels = {}

    for source, mix_pct in expected_mix.items():
        if mix_pct <= 0:
            continue

        # What this channel should contribute
        required = target * mix_pct

        # What Monte Carlo says this channel will deliver
        source_data = monte_carlo_result.by_source.get(source, {})
        channel_expected = source_data.get("p50", 0)

        # Variance (negative = contributing to gap)
        variance = channel_expected - required

        # Percentage of total gap
        pct_of_gap = abs(variance) / abs(total_gap) if total_gap != 0 else 0

        channels[source] = {
            "required": required,
            "expected": channel_expected,
            "variance": variance,
            "pct_of_gap": pct_of_gap if variance < 0 else -pct_of_gap,
            "status": "ahead" if variance > 0 else "behind",
        }

    # Rank contributors by absolute variance
    top_contributors = sorted(
        [{"channel": k, **v} for k, v in channels.items()],
        key=lambda x: x["variance"],
    )

    # Generate recommendations
    recommendations = []
    for contrib in top_contributors:
        if contrib["variance"] < -100_000:  # Significant gap
            pct = abs(contrib["variance"]) / target * 100
            recommendations.append(
                f"{contrib['channel']}: ${abs(contrib['variance']):,.0f} below plan "
                f"({pct:.0f}% of target) - investigate pipeline generation"
            )

    if not recommendations:
        if total_gap <= 0:
            recommendations.append("All channels on track or ahead of plan")
        else:
            recommendations.append(f"Gap of ${total_gap:,.0f} distributed across channels")

    return VarianceAttribution(
        target=target,
        expected=expected,
        total_gap=total_gap,
        channels=channels,
        top_contributors=top_contributors,
        recommendations=recommendations,
    )


# =============================================================================
# HELPERS FOR SALESFORCE DATA
# =============================================================================

def deals_from_sf_pipeline(pipeline_data: list[dict]) -> list[Deal]:
    """
    Convert Salesforce pipeline data to Deal objects.

    Args:
        pipeline_data: List of dicts from SF connector (get_pipeline_with_aging
                       or get_pipeline_with_push_history)

    Returns:
        List of Deal objects for simulation
    """
    deals = []

    for record in pipeline_data:
        stage = record.get("stage", "")
        if stage not in ("S2", "S3", "S4", "S5"):
            continue

        deal = Deal(
            id=record.get("id", ""),
            name=record.get("name", ""),
            stage=stage,
            arr=float(record.get("arr", 0)),
            days_in_stage=int(record.get("days_in_stage", 0)),
            source=normalize_source(record.get("source")),
            segment=record.get("segment", "unknown"),
            close_date=record.get("close_date"),  # For slip probability
            has_pushed=record.get("has_pushed", False),  # For slip probability
        )
        deals.append(deal)

    return deals


def normalize_source(sf_source: Optional[str]) -> str:
    """Normalize Salesforce source category to model key."""
    if not sf_source:
        return "unknown"

    source_map = {
        "SDR Sourced": "sdr_sourced",
        "SDR": "sdr_sourced",
        "Outbound": "sdr_sourced",
        "Marketing Sourced": "marketing_sourced",
        "Marketing": "marketing_sourced",
        "Inbound": "marketing_sourced",
        "AE Sourced": "ae_sourced",
        "AE": "ae_sourced",
        "Self-Sourced": "ae_sourced",
        "Leadership Sourced": "leadership_sourced",
        "Leadership": "leadership_sourced",
        "SE Sourced": "se_sourced",
        "SE": "se_sourced",
    }

    return source_map.get(sf_source, "unknown")


# =============================================================================
# SCENARIO ANALYSIS
# =============================================================================

def run_scenario(
    deals: list[Deal],
    target: float,
    scenario_name: str,
    adjustments: dict,
    n_simulations: int = 1000,
) -> dict:
    """
    Run a what-if scenario with adjusted parameters.

    Args:
        deals: Base deals
        target: Bookings target
        scenario_name: Name for the scenario
        adjustments: Dict of adjustments:
            - "win_rate_multiplier": 1.2 = 20% better win rates
            - "deal_size_multiplier": 1.1 = 10% larger deals
            - "add_pipeline": 1_000_000 = add $1M of S3 pipeline

    Returns:
        Dict with scenario results
    """
    # Apply adjustments
    adjusted_deals = []

    for deal in deals:
        adjusted_deal = Deal(
            id=deal.id,
            name=deal.name,
            stage=deal.stage,
            arr=deal.arr * adjustments.get("deal_size_multiplier", 1.0),
            days_in_stage=deal.days_in_stage,
            source=deal.source,
            segment=deal.segment,
        )
        adjusted_deals.append(adjusted_deal)

    # Add synthetic pipeline if specified
    if "add_pipeline" in adjustments:
        add_amount = adjustments["add_pipeline"]
        add_stage = adjustments.get("add_stage", "S3")
        add_source = adjustments.get("add_source", "sdr_sourced")

        # Create synthetic deals (assume $300K average)
        n_deals = max(1, int(add_amount / 300_000))
        deal_size = add_amount / n_deals

        for i in range(n_deals):
            adjusted_deals.append(Deal(
                id=f"scenario_{i}",
                name=f"Scenario Deal {i+1}",
                stage=add_stage,
                arr=deal_size,
                days_in_stage=0,  # Fresh deals
                source=add_source,
            ))

    # Adjust transition matrix if win rate multiplier specified
    matrix = DEFAULT_TRANSITION_MATRIX.copy()
    if "win_rate_multiplier" in adjustments:
        mult = adjustments["win_rate_multiplier"]
        matrix = {}
        for stage, transitions in DEFAULT_TRANSITION_MATRIX.items():
            matrix[stage] = {}
            for next_state, prob in transitions.items():
                if next_state == "won":
                    matrix[stage][next_state] = min(0.95, prob * mult)
                elif next_state == "lost":
                    matrix[stage][next_state] = max(0.05, prob / mult)
                else:
                    matrix[stage][next_state] = prob

    # Run simulation
    result = run_monte_carlo_forecast(
        deals=adjusted_deals,
        target=target,
        n_simulations=n_simulations,
        transition_matrix=matrix,
    )

    return {
        "scenario": scenario_name,
        "adjustments": adjustments,
        "p50": result.p50,
        "p10": result.p10,
        "p90": result.p90,
        "prob_hit_target": result.prob_hit_target,
        "expected_gap": result.expected_gap,
    }


def compare_scenarios(
    deals: list[Deal],
    target: float,
    scenarios: list[dict],
    n_simulations: int = 1000,
) -> list[dict]:
    """
    Compare multiple scenarios.

    Args:
        deals: Base deals
        target: Bookings target
        scenarios: List of {"name": str, "adjustments": dict}
        n_simulations: Number of simulations per scenario

    Returns:
        List of scenario results, sorted by P50
    """
    results = []

    # Run base case
    base = run_monte_carlo_forecast(deals=deals, target=target, n_simulations=n_simulations)
    results.append({
        "scenario": "Base Case",
        "adjustments": {},
        "p50": base.p50,
        "p10": base.p10,
        "p90": base.p90,
        "prob_hit_target": base.prob_hit_target,
        "expected_gap": base.expected_gap,
    })

    # Run each scenario
    for scenario in scenarios:
        result = run_scenario(
            deals=deals,
            target=target,
            scenario_name=scenario["name"],
            adjustments=scenario["adjustments"],
            n_simulations=n_simulations,
        )
        results.append(result)

    return sorted(results, key=lambda x: -x["p50"])

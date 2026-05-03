"""
Funnel math for the GTM model.

Provides reverse funnel calculation (target → required inputs) and
forward funnel calculation (inputs → expected outputs).
"""

from dataclasses import dataclass, field
from typing import Optional
import math

from .rate_defaults import get_default_funnel_rates

_DEFAULT_FUNNEL_RATES = get_default_funnel_rates()


# Source category constants for Phase 5 attribution
# MQL-sourced: Need leads to feed pipeline (SDR + Marketing)
MQL_SOURCES = {"sdr_sourced", "marketing_sourced"}

# Direct-sourced: Go straight to S0, skip MQL stage
DIRECT_SOURCES = {"ae_sourced", "leadership_sourced", "se_sourced", "unknown"}

# All valid source categories
ALL_SOURCES = MQL_SOURCES | DIRECT_SOURCES

# Mapping from SF picklist values to config keys (centralized)
SOURCE_CATEGORY_MAP = {
    "SDR Sourced": "sdr_sourced",
    "AE Sourced": "ae_sourced",
    "Marketing Sourced": "marketing_sourced",
    "Leadership Sourced": "leadership_sourced",
    "SE Sourced": "se_sourced",
    "Unknown": "unknown",
}

# Reverse mapping (config keys to SF picklist values)
SOURCE_CATEGORY_MAP_REVERSE = {v: k for k, v in SOURCE_CATEGORY_MAP.items()}


@dataclass
class FunnelAssumptions:
    """
    Assumptions for funnel calculations.

    All conversion rates are expressed as decimals (0.0 to 1.0).
    Source mix percentages should sum to 1.0.
    """

    # Average deal size
    avg_acv: float = 300_000  # $300K average ACV

    # Lead to opportunity conversion
    mql_to_s0: float = _DEFAULT_FUNNEL_RATES["mql_to_s0"]

    # Opportunity stage conversions
    s0_to_s1: float = _DEFAULT_FUNNEL_RATES["s0_to_s1"]
    s1_to_s2: float = _DEFAULT_FUNNEL_RATES["s1_to_s2"]
    s2_to_s3: float = _DEFAULT_FUNNEL_RATES["s2_to_s3"]
    s3_to_s4: float = _DEFAULT_FUNNEL_RATES["s3_to_s4"]
    s4_to_s5: float = _DEFAULT_FUNNEL_RATES["s4_to_s5"]
    s5_to_won: float = _DEFAULT_FUNNEL_RATES["s5_to_won"]

    # Source mix (should sum to 1.0). Six categories.
    # Override these in your profile's assumptions.yaml to match your
    # actual source distribution.
    # MQL-sourced (need leads)
    source_mix_sdr: float = 0.40
    source_mix_marketing: float = 0.16
    # Direct-sourced (skip MQL)
    source_mix_ae: float = 0.29
    source_mix_leadership: float = 0.09
    source_mix_se: float = 0.02
    source_mix_unknown: float = 0.04

    def __post_init__(self):
        """Validate assumptions on creation."""
        # Check conversion rates are valid percentages
        rates = [
            self.mql_to_s0,
            self.s0_to_s1,
            self.s1_to_s2,
            self.s2_to_s3,
            self.s3_to_s4,
            self.s4_to_s5,
            self.s5_to_won,
        ]
        for rate in rates:
            if not 0.0 <= rate <= 1.0:
                raise ValueError(f"Conversion rate must be between 0 and 1, got {rate}")

        # Check source mix sums to 1.0 (with small tolerance)
        source_total = (
            self.source_mix_ae +
            self.source_mix_sdr +
            self.source_mix_marketing +
            self.source_mix_leadership +
            self.source_mix_se +
            self.source_mix_unknown
        )
        if not 0.99 <= source_total <= 1.01:
            raise ValueError(f"Source mix must sum to 1.0, got {source_total}")

    @property
    def mql_sourced_pct(self) -> float:
        """Percentage of pipeline that needs MQLs (SDR + Marketing)."""
        return self.source_mix_sdr + self.source_mix_marketing

    @property
    def direct_sourced_pct(self) -> float:
        """Percentage of pipeline that goes direct to S0 (AE + Leadership + SE + Unknown)."""
        return (
            self.source_mix_ae +
            self.source_mix_leadership +
            self.source_mix_se +
            self.source_mix_unknown
        )

    @property
    def s2_to_won(self) -> float:
        """Calculate composite S2-to-Won conversion rate."""
        return self.s2_to_s3 * self.s3_to_s4 * self.s4_to_s5 * self.s5_to_won

    @property
    def s1_to_won(self) -> float:
        """Calculate composite S1-to-Won conversion rate."""
        return self.s1_to_s2 * self.s2_to_won

    @property
    def s0_to_won(self) -> float:
        """Calculate composite S0-to-Won conversion rate."""
        return self.s0_to_s1 * self.s1_to_won

    @property
    def mql_to_won(self) -> float:
        """Calculate composite MQL-to-Won conversion rate."""
        return self.mql_to_s0 * self.s0_to_won


@dataclass
class FunnelRequirements:
    """
    Output of reverse funnel calculation.

    Given a bookings target, this shows the required volume at each stage.
    """

    # Target
    bookings_target: float
    avg_acv: float

    # Required volume at each stage
    required_deals: int
    required_s5: int
    required_s4: int
    required_s3: int
    required_s2: int
    required_s1: int
    required_s0: int
    required_mqls: int

    # Pipeline value at each stage
    pipeline_s5: float = field(init=False)
    pipeline_s4: float = field(init=False)
    pipeline_s3: float = field(init=False)
    pipeline_s2: float = field(init=False)
    pipeline_s1: float = field(init=False)
    pipeline_s0: float = field(init=False)

    # Split by source (Phase 5: MQL vs Direct)
    direct_sourced_opps: int = 0  # AE + Leadership + SE + Unknown (skip MQL)
    mql_sourced_opps: int = 0     # SDR + Marketing (need MQLs)
    sdr_sourced_mqls: int = 0
    marketing_sourced_mqls: int = 0

    # Legacy alias for backwards compatibility
    @property
    def ae_sourced_opps(self) -> int:
        """Alias for direct_sourced_opps (backwards compatibility)."""
        return self.direct_sourced_opps

    def __post_init__(self):
        """Calculate pipeline values from volume and ACV."""
        self.pipeline_s5 = self.required_s5 * self.avg_acv
        self.pipeline_s4 = self.required_s4 * self.avg_acv
        self.pipeline_s3 = self.required_s3 * self.avg_acv
        self.pipeline_s2 = self.required_s2 * self.avg_acv
        self.pipeline_s1 = self.required_s1 * self.avg_acv
        self.pipeline_s0 = self.required_s0 * self.avg_acv

    def summary(self) -> str:
        """Return a formatted summary of requirements."""
        return f"""
Reverse Funnel Requirements
===========================
Target: ${self.bookings_target:,.0f} at ${self.avg_acv:,.0f} ACV

Stage Requirements (count / pipeline value):
  Closed Won: {self.required_deals:,} deals = ${self.bookings_target:,.0f}
  S5:         {self.required_s5:,} opps   = ${self.pipeline_s5:,.0f}
  S4:         {self.required_s4:,} opps   = ${self.pipeline_s4:,.0f}
  S3:         {self.required_s3:,} opps   = ${self.pipeline_s3:,.0f}
  S2:         {self.required_s2:,} opps   = ${self.pipeline_s2:,.0f}
  S1:         {self.required_s1:,} opps   = ${self.pipeline_s1:,.0f}
  S0:         {self.required_s0:,} opps   = ${self.pipeline_s0:,.0f}
  MQLs:       {self.required_mqls:,}

Source Split:
  Direct-Sourced:       {self.direct_sourced_opps:,} opps (AE + Leadership + SE + Unknown)
  SDR Sourced MQLs:     {self.sdr_sourced_mqls:,}
  Marketing MQLs:       {self.marketing_sourced_mqls:,}
"""


@dataclass
class FunnelForecast:
    """
    Output of forward funnel calculation.

    Given inputs at each stage, this forecasts expected outputs.
    """

    # Inputs
    mqls_in: int
    s0_in: int
    s1_in: int
    s2_in: int
    avg_acv: float

    # Expected outputs
    expected_s0: int
    expected_s1: int
    expected_s2: int
    expected_won: int
    expected_bookings: float

    def summary(self) -> str:
        """Return a formatted summary of forecast."""
        return f"""
Forward Funnel Forecast
=======================
Inputs:
  MQLs:  {self.mqls_in:,}
  S0:    {self.s0_in:,}
  S1:    {self.s1_in:,}
  S2:    {self.s2_in:,}

Expected Outputs:
  → S0:       {self.expected_s0:,} opportunities
  → S1:       {self.expected_s1:,} qualified
  → S2:       {self.expected_s2:,} scoped
  → Won:      {self.expected_won:,} deals
  → Bookings: ${self.expected_bookings:,.0f}
"""


def reverse_funnel(
    bookings_target: float,
    assumptions: Optional[FunnelAssumptions] = None,
) -> FunnelRequirements:
    """
    Calculate required volume at each stage to hit a bookings target.

    This is the core "how many MQLs do we need" calculation.

    Args:
        bookings_target: Target bookings in dollars
        assumptions: Funnel assumptions (uses defaults if not provided)

    Returns:
        FunnelRequirements with volumes at each stage

    Example:
        >>> req = reverse_funnel(6_000_000)  # $6M target
        >>> print(req.required_mqls)
        6453
    """
    if assumptions is None:
        assumptions = FunnelAssumptions()

    avg_acv = assumptions.avg_acv

    # Work backwards from bookings target
    required_deals = math.ceil(bookings_target / avg_acv)
    required_s5 = math.ceil(required_deals / assumptions.s5_to_won)
    required_s4 = math.ceil(required_s5 / assumptions.s4_to_s5)
    required_s3 = math.ceil(required_s4 / assumptions.s3_to_s4)
    required_s2 = math.ceil(required_s3 / assumptions.s2_to_s3)
    required_s1 = math.ceil(required_s2 / assumptions.s1_to_s2)
    required_s0 = math.ceil(required_s1 / assumptions.s0_to_s1)
    required_mqls = math.ceil(required_s0 / assumptions.mql_to_s0)

    # Calculate source split (Phase 5: MQL vs Direct)
    # Direct-sourced skip MQL stage, go straight to S0 (AE + Leadership + SE + Unknown)
    direct_sourced_opps = math.ceil(required_s0 * assumptions.direct_sourced_pct)

    # MQL-sourced go through MQL (SDR + Marketing)
    mql_sourced_opps = required_s0 - direct_sourced_opps
    total_mql_pct = assumptions.source_mix_sdr + assumptions.source_mix_marketing
    sdr_pct_of_mql = assumptions.source_mix_sdr / total_mql_pct if total_mql_pct > 0 else 0.5
    sdr_sourced_mqls = math.ceil(mql_sourced_opps / assumptions.mql_to_s0 * sdr_pct_of_mql)
    marketing_sourced_mqls = math.ceil(mql_sourced_opps / assumptions.mql_to_s0) - sdr_sourced_mqls

    return FunnelRequirements(
        bookings_target=bookings_target,
        avg_acv=avg_acv,
        required_deals=required_deals,
        required_s5=required_s5,
        required_s4=required_s4,
        required_s3=required_s3,
        required_s2=required_s2,
        required_s1=required_s1,
        required_s0=required_s0,
        required_mqls=required_mqls,
        direct_sourced_opps=direct_sourced_opps,
        mql_sourced_opps=mql_sourced_opps,
        sdr_sourced_mqls=sdr_sourced_mqls,
        marketing_sourced_mqls=marketing_sourced_mqls,
    )


def forward_funnel(
    mqls_in: int = 0,
    s0_in: int = 0,
    s1_in: int = 0,
    s2_in: int = 0,
    assumptions: Optional[FunnelAssumptions] = None,
) -> FunnelForecast:
    """
    Forecast expected outputs given inputs at each stage.

    This is the "given X MQLs, how many deals will close" calculation.

    Args:
        mqls_in: Number of MQLs entering the funnel
        s0_in: Number of opps already in S0
        s1_in: Number of opps already in S1
        s2_in: Number of opps already in S2
        assumptions: Funnel assumptions (uses defaults if not provided)

    Returns:
        FunnelForecast with expected outputs

    Example:
        >>> forecast = forward_funnel(mqls_in=1000)
        >>> print(forecast.expected_won)
        3
    """
    if assumptions is None:
        assumptions = FunnelAssumptions()

    # MQLs → S0
    mqls_to_s0 = int(mqls_in * assumptions.mql_to_s0)
    total_s0 = mqls_to_s0 + s0_in

    # S0 → S1
    s0_to_s1 = int(total_s0 * assumptions.s0_to_s1)
    total_s1 = s0_to_s1 + s1_in

    # S1 → S2
    s1_to_s2 = int(total_s1 * assumptions.s1_to_s2)
    total_s2 = s1_to_s2 + s2_in

    # S2 → Won (using composite rate)
    expected_won = int(total_s2 * assumptions.s2_to_won)
    expected_bookings = expected_won * assumptions.avg_acv

    return FunnelForecast(
        mqls_in=mqls_in,
        s0_in=s0_in,
        s1_in=s1_in,
        s2_in=s2_in,
        avg_acv=assumptions.avg_acv,
        expected_s0=total_s0,
        expected_s1=total_s1,
        expected_s2=total_s2,
        expected_won=expected_won,
        expected_bookings=expected_bookings,
    )


def calculate_pipeline_coverage(
    bookings_target: float,
    current_pipeline: float,
    assumptions: Optional[FunnelAssumptions] = None,
) -> dict:
    """
    Calculate pipeline coverage ratio and gap.

    Args:
        bookings_target: Target bookings in dollars
        current_pipeline: Current pipeline value (typically S2+)
        assumptions: Funnel assumptions

    Returns:
        Dict with coverage ratio, gap, and required new pipeline
    """
    if assumptions is None:
        assumptions = FunnelAssumptions()

    # Calculate required pipeline (typically 3-4x coverage)
    # Based on S2-to-Won rate
    coverage_multiplier = 1 / assumptions.s2_to_won
    required_pipeline = bookings_target * coverage_multiplier

    coverage_ratio = current_pipeline / required_pipeline if required_pipeline > 0 else 0
    pipeline_gap = max(0, required_pipeline - current_pipeline)

    return {
        "bookings_target": bookings_target,
        "current_pipeline": current_pipeline,
        "required_pipeline": required_pipeline,
        "coverage_ratio": coverage_ratio,
        "coverage_pct": coverage_ratio * 100,
        "pipeline_gap": pipeline_gap,
        "s2_to_won_rate": assumptions.s2_to_won,
    }


def calculate_close_time_distribution(
    bookings_target: float,
    close_month: int,
    avg_acv: float = 300_000,
) -> dict[int, float]:
    """
    Calculate when pipeline needs to be created to close in a target month.

    Default values reflect typical B2B SaaS distributions close rate distribution:
    - Month 1 (same month): 16%
    - Month 2: 26%
    - Month 3: 17%
    - Month 4: 15%
    - Month 5: 10%
    - Month 6: 6%
    - Month 7+: 10%

    Args:
        bookings_target: Target bookings for the close month
        close_month: The month number to close (1-12)
        avg_acv: Average ACV for deal sizing

    Returns:
        Dict mapping creation month offset (0 = same month) to required pipeline
    """
    # Close rate distribution from FY26 model
    distribution = {
        0: 0.16,  # Same month
        1: 0.26,  # 1 month before
        2: 0.17,  # 2 months before
        3: 0.15,  # 3 months before
        4: 0.10,  # 4 months before
        5: 0.06,  # 5 months before
        6: 0.10,  # 6+ months before
    }

    result = {}
    for offset, rate in distribution.items():
        pipeline_needed = bookings_target * rate
        creation_month = close_month - offset
        if creation_month > 0:  # Only include valid months
            result[creation_month] = pipeline_needed

    return result


def calculate_win_rate(
    won_deals: int,
    total_opps: int,
    from_stage: str = "S0",
) -> float:
    """
    Calculate win rate from a given stage.

    Args:
        won_deals: Number of closed won deals
        total_opps: Total opportunities from the starting stage
        from_stage: The starting stage for calculation

    Returns:
        Win rate as a decimal (0.0 to 1.0)
    """
    if total_opps == 0:
        return 0.0
    return won_deals / total_opps

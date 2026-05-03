"""
ARR Waterfall calculations for the GTM model.

Tracks revenue flows: new business, expansion, contraction, and churn.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from enum import Enum


class RevenueType(Enum):
    """Types of ARR movement."""

    NEW_BUSINESS = "new_business"  # First contract with customer
    EXPANSION = "expansion"  # Upsell/cross-sell
    PLG = "plg"  # Product-led/self-serve conversions
    CONTRACTION = "contraction"  # Downgrades
    CHURN = "churn"  # Cancellations


@dataclass
class ARRWaterfall:
    """
    ARR waterfall for a period.

    Tracks the flow from beginning ARR to ending ARR including
    all sources of growth and contraction.
    """

    period: str  # e.g., "Q1FY26", "Jan 2026", "FY26"
    beginning_arr: float

    # Growth
    new_business_arr: float = 0.0
    expansion_arr: float = 0.0
    plg_arr: float = 0.0

    # Contraction
    contraction_arr: float = 0.0
    churned_arr: float = 0.0

    @property
    def ending_arr(self) -> float:
        """Calculate ending ARR from waterfall components."""
        return (
            self.beginning_arr
            + self.new_business_arr
            + self.expansion_arr
            + self.plg_arr
            - self.contraction_arr
            - self.churned_arr
        )

    @property
    def gross_new_arr(self) -> float:
        """Total new ARR added (before churn/contraction)."""
        return self.new_business_arr + self.expansion_arr + self.plg_arr

    @property
    def net_new_arr(self) -> float:
        """Net ARR change (gross new minus losses)."""
        return self.gross_new_arr - self.contraction_arr - self.churned_arr

    @property
    def gross_dollar_retention(self) -> float:
        """
        Gross Dollar Retention (GDR).

        Measures retained revenue without counting expansion.
        Formula: (Beginning - Churn - Contraction) / Beginning
        """
        if self.beginning_arr == 0:
            return 1.0
        retained = self.beginning_arr - self.churned_arr - self.contraction_arr
        return retained / self.beginning_arr

    @property
    def net_dollar_retention(self) -> float:
        """
        Net Dollar Retention (NDR).

        Measures retained revenue including expansion.
        Formula: (Beginning + Expansion - Churn - Contraction) / Beginning
        """
        if self.beginning_arr == 0:
            return 1.0
        retained = (
            self.beginning_arr
            + self.expansion_arr
            - self.churned_arr
            - self.contraction_arr
        )
        return retained / self.beginning_arr

    @property
    def logo_churn_implied(self) -> float:
        """
        Implied logo churn rate from ARR churn.

        This is a rough estimate assuming average deal size.
        Not as accurate as actual logo count tracking.
        """
        if self.beginning_arr == 0:
            return 0.0
        return self.churned_arr / self.beginning_arr

    @property
    def growth_rate(self) -> float:
        """Period-over-period growth rate."""
        if self.beginning_arr == 0:
            return 0.0 if self.ending_arr == 0 else float('inf')
        return (self.ending_arr - self.beginning_arr) / self.beginning_arr

    def validate(self) -> list[str]:
        """Validate waterfall for common errors."""
        errors = []

        # Check for negative values where they shouldn't be
        if self.beginning_arr < 0:
            errors.append("Beginning ARR cannot be negative")
        if self.new_business_arr < 0:
            errors.append("New business ARR cannot be negative")
        if self.expansion_arr < 0:
            errors.append("Expansion ARR cannot be negative")
        if self.plg_arr < 0:
            errors.append("PLG ARR cannot be negative")
        if self.contraction_arr < 0:
            errors.append("Contraction ARR should be positive (it's subtracted)")
        if self.churned_arr < 0:
            errors.append("Churned ARR should be positive (it's subtracted)")

        # Check for unrealistic retention
        if self.gross_dollar_retention < 0.5:
            errors.append(f"GDR of {self.gross_dollar_retention:.1%} seems unrealistically low")
        if self.net_dollar_retention > 2.0:
            errors.append(f"NDR of {self.net_dollar_retention:.1%} seems unrealistically high")

        return errors

    def summary(self) -> str:
        """Return formatted summary of waterfall."""
        return f"""
ARR Waterfall: {self.period}
===========================
Beginning ARR:     ${self.beginning_arr:>12,.0f}

  + New Business:  ${self.new_business_arr:>12,.0f}
  + Expansion:     ${self.expansion_arr:>12,.0f}
  + PLG:           ${self.plg_arr:>12,.0f}
  - Contraction:   ${self.contraction_arr:>12,.0f}
  - Churn:         ${self.churned_arr:>12,.0f}
                   ─────────────────
Ending ARR:        ${self.ending_arr:>12,.0f}

Metrics:
  Gross New ARR:   ${self.gross_new_arr:>12,.0f}
  Net New ARR:     ${self.net_new_arr:>12,.0f}
  Growth Rate:     {self.growth_rate:>12.1%}
  GDR:             {self.gross_dollar_retention:>12.1%}
  NDR:             {self.net_dollar_retention:>12.1%}
"""

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "period": self.period,
            "beginning_arr": self.beginning_arr,
            "new_business_arr": self.new_business_arr,
            "expansion_arr": self.expansion_arr,
            "plg_arr": self.plg_arr,
            "contraction_arr": self.contraction_arr,
            "churned_arr": self.churned_arr,
            "ending_arr": self.ending_arr,
            "net_new_arr": self.net_new_arr,
            "gdr": self.gross_dollar_retention,
            "ndr": self.net_dollar_retention,
        }


@dataclass
class RetentionAssumptions:
    """Assumptions for modeling retention and expansion."""

    gross_dollar_retention: float = 0.90  # 90% GDR
    expansion_rate: float = 0.15  # 15% of beginning ARR expands
    plg_conversion_rate: float = 0.02  # 2% of freemium converts

    # Breakdown of churn/contraction
    voluntary_churn_rate: float = 0.05  # 5% choose to leave
    involuntary_churn_rate: float = 0.02  # 2% fail to pay
    contraction_rate: float = 0.03  # 3% downgrade

    @property
    def total_churn_rate(self) -> float:
        """Total churn rate (voluntary + involuntary)."""
        return self.voluntary_churn_rate + self.involuntary_churn_rate

    @property
    def implied_ndr(self) -> float:
        """Calculate implied NDR from assumptions."""
        return (
            1.0
            + self.expansion_rate
            - self.total_churn_rate
            - self.contraction_rate
        )

    def validate(self) -> list[str]:
        """Validate assumptions for consistency."""
        errors = []

        # Check rates are reasonable
        if self.gross_dollar_retention < 0.7 or self.gross_dollar_retention > 1.0:
            errors.append(f"GDR of {self.gross_dollar_retention:.1%} outside normal range (70-100%)")

        if self.expansion_rate > 0.5:
            errors.append(f"Expansion rate of {self.expansion_rate:.1%} seems very high")

        # Check GDR consistency
        calculated_gdr = 1.0 - self.total_churn_rate - self.contraction_rate
        if abs(calculated_gdr - self.gross_dollar_retention) > 0.01:
            errors.append(
                f"GDR ({self.gross_dollar_retention:.1%}) doesn't match "
                f"churn + contraction ({calculated_gdr:.1%})"
            )

        return errors


def calculate_waterfall(
    period: str,
    beginning_arr: float,
    new_business_arr: float,
    expansion_arr: Optional[float] = None,
    plg_arr: float = 0.0,
    assumptions: Optional[RetentionAssumptions] = None,
) -> ARRWaterfall:
    """
    Calculate ARR waterfall for a period.

    If expansion/churn/contraction not provided, calculates from assumptions.

    Args:
        period: Period identifier (e.g., "Q1FY26")
        beginning_arr: Starting ARR
        new_business_arr: New business closed in period
        expansion_arr: Expansion ARR (calculated from assumptions if None)
        plg_arr: PLG conversion ARR
        assumptions: Retention assumptions

    Returns:
        ARRWaterfall for the period
    """
    if assumptions is None:
        assumptions = RetentionAssumptions()

    # Calculate retention-related metrics from assumptions if not provided
    if expansion_arr is None:
        expansion_arr = beginning_arr * assumptions.expansion_rate

    contraction_arr = beginning_arr * assumptions.contraction_rate
    churned_arr = beginning_arr * assumptions.total_churn_rate

    return ARRWaterfall(
        period=period,
        beginning_arr=beginning_arr,
        new_business_arr=new_business_arr,
        expansion_arr=expansion_arr,
        plg_arr=plg_arr,
        contraction_arr=contraction_arr,
        churned_arr=churned_arr,
    )


def project_arr_timeline(
    beginning_arr: float,
    quarterly_new_business: list[float],
    assumptions: Optional[RetentionAssumptions] = None,
    start_quarter: str = "Q1FY26",
) -> list[ARRWaterfall]:
    """
    Project ARR waterfall over multiple quarters.

    Args:
        beginning_arr: Starting ARR
        quarterly_new_business: List of new business ARR per quarter
        assumptions: Retention assumptions
        start_quarter: Starting quarter label

    Returns:
        List of ARRWaterfall for each quarter
    """
    if assumptions is None:
        assumptions = RetentionAssumptions()

    waterfalls = []
    current_arr = beginning_arr

    for i, new_biz in enumerate(quarterly_new_business):
        # Parse quarter for labeling
        q_num = int(start_quarter[1]) + i
        fy_num = int(start_quarter[4:6])
        while q_num > 4:
            q_num -= 4
            fy_num += 1
        period = f"Q{q_num}FY{fy_num}"

        wf = calculate_waterfall(
            period=period,
            beginning_arr=current_arr,
            new_business_arr=new_biz,
            assumptions=assumptions,
        )
        waterfalls.append(wf)
        current_arr = wf.ending_arr

    return waterfalls


def calculate_arr_at_date(
    beginning_arr: float,
    beginning_date: date,
    target_date: date,
    monthly_new_business: float,
    assumptions: Optional[RetentionAssumptions] = None,
) -> float:
    """
    Calculate projected ARR at a future date.

    Simple model that compounds retention monthly.

    Args:
        beginning_arr: Starting ARR
        beginning_date: Date of beginning ARR
        target_date: Date to project to
        monthly_new_business: Average monthly new business ARR
        assumptions: Retention assumptions

    Returns:
        Projected ARR at target date
    """
    if assumptions is None:
        assumptions = RetentionAssumptions()

    # Calculate months between dates
    months = (target_date.year - beginning_date.year) * 12 + (target_date.month - beginning_date.month)
    if months <= 0:
        return beginning_arr

    # Monthly rates from quarterly assumptions
    monthly_expansion = assumptions.expansion_rate / 3
    monthly_churn = assumptions.total_churn_rate / 3
    monthly_contraction = assumptions.contraction_rate / 3
    monthly_retention = 1.0 + monthly_expansion - monthly_churn - monthly_contraction

    # Compound retention and add new business
    current_arr = beginning_arr
    for _ in range(months):
        # Apply retention to existing ARR
        current_arr = current_arr * monthly_retention
        # Add new business
        current_arr += monthly_new_business

    return current_arr


def target_new_business_for_arr(
    beginning_arr: float,
    target_arr: float,
    periods: int = 4,  # quarters
    assumptions: Optional[RetentionAssumptions] = None,
) -> float:
    """
    Calculate required quarterly new business to reach target ARR.

    Uses goal seek to find the new business amount that
    results in target ending ARR.

    Args:
        beginning_arr: Starting ARR
        target_arr: Target ending ARR
        periods: Number of quarters
        assumptions: Retention assumptions

    Returns:
        Required quarterly new business ARR
    """
    if assumptions is None:
        assumptions = RetentionAssumptions()

    # Binary search for the right new business amount
    low, high = 0, target_arr
    tolerance = 1000  # $1K tolerance

    for _ in range(50):  # Max iterations
        mid = (low + high) / 2
        quarterly_new_biz = [mid] * periods

        waterfalls = project_arr_timeline(
            beginning_arr=beginning_arr,
            quarterly_new_business=quarterly_new_biz,
            assumptions=assumptions,
        )

        ending_arr = waterfalls[-1].ending_arr

        if abs(ending_arr - target_arr) < tolerance:
            return mid
        elif ending_arr < target_arr:
            low = mid
        else:
            high = mid

    return (low + high) / 2


@dataclass
class CohortRetention:
    """Track retention for a specific customer cohort."""

    cohort_period: str  # e.g., "Q1FY26"
    starting_arr: float
    starting_logos: int

    # Retention by period (period -> ARR)
    arr_by_period: dict[str, float] = field(default_factory=dict)
    logos_by_period: dict[str, int] = field(default_factory=dict)

    def dollar_retention_at_period(self, period: str) -> float:
        """Calculate dollar retention at a specific period."""
        if self.starting_arr == 0:
            return 1.0
        return self.arr_by_period.get(period, 0) / self.starting_arr

    def logo_retention_at_period(self, period: str) -> float:
        """Calculate logo retention at a specific period."""
        if self.starting_logos == 0:
            return 1.0
        return self.logos_by_period.get(period, 0) / self.starting_logos

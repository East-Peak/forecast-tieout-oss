"""
GTM Economics Module - Unit Economics and CAC Analysis

Calculates business metrics for scenario planning:
- CAC (Customer Acquisition Cost)
- CAC Payback period
- LTV/CAC ratio
- GTM efficiency metrics

Enables "what happens to economics if we add X reps?" analysis.
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# Default cost assumptions
DEFAULT_COSTS = {
    "sdr_fully_loaded": 85_000,     # Annual fully-loaded SDR cost
    "ae_fully_loaded": 250_000,     # Annual fully-loaded AE cost (including commission)
    "se_fully_loaded": 180_000,     # Annual fully-loaded SE cost
    "marketing_monthly": 50_000,    # Monthly marketing spend
}

# Default revenue assumptions
DEFAULT_REVENUE = {
    "avg_acv": 300_000,             # Average annual contract value
    "gross_margin": 0.80,           # 80% gross margin
    "avg_customer_lifetime_years": 4,  # Average customer lifetime
}


@dataclass
class UnitEconomics:
    """
    GTM unit economics for a period.

    Core metrics for evaluating GTM efficiency:
    - CAC: How much it costs to acquire a customer
    - LTV: Lifetime value of a customer
    - Payback: How long to recover CAC
    - LTV/CAC: Return on customer acquisition spend
    """

    # Period
    period: str = ""

    # Costs
    total_sales_cost: float = 0.0       # S&M spend
    total_marketing_cost: float = 0.0   # Marketing spend
    total_gtm_cost: float = field(init=False)  # Total S&M + Marketing

    # Results
    new_customers: int = 0
    new_arr: float = 0.0

    # Calculated metrics
    cac: float = field(init=False)          # Customer Acquisition Cost
    ltv: float = field(init=False)          # Lifetime Value
    ltv_cac_ratio: float = field(init=False)
    cac_payback_months: int = field(init=False)
    magic_number: float = field(init=False)  # Net New ARR / Previous Quarter S&M

    # Assumptions used
    gross_margin: float = 0.80
    avg_customer_lifetime_years: float = 4.0

    # Optional: previous quarter S&M for magic number
    previous_quarter_sm: float = 0.0

    def __post_init__(self):
        """Calculate derived metrics."""
        self.total_gtm_cost = self.total_sales_cost + self.total_marketing_cost

        # CAC = Total GTM Cost / New Customers
        if self.new_customers > 0:
            self.cac = self.total_gtm_cost / self.new_customers
        else:
            self.cac = 0.0

        # LTV = (ARR * Gross Margin * Customer Lifetime)
        avg_arr = self.new_arr / self.new_customers if self.new_customers > 0 else 0
        self.ltv = avg_arr * self.gross_margin * self.avg_customer_lifetime_years

        # LTV/CAC ratio
        if self.cac > 0:
            self.ltv_cac_ratio = self.ltv / self.cac
        else:
            self.ltv_cac_ratio = 0.0

        # CAC Payback (months)
        # Monthly revenue contribution = ARR/12 * Gross Margin
        if avg_arr > 0 and self.cac > 0:
            monthly_contribution = (avg_arr / 12) * self.gross_margin
            self.cac_payback_months = math.ceil(self.cac / monthly_contribution)
        else:
            self.cac_payback_months = 0

        # Magic Number = Net New ARR / Previous Quarter S&M
        if self.previous_quarter_sm > 0:
            self.magic_number = self.new_arr / self.previous_quarter_sm
        else:
            self.magic_number = 0.0

    @property
    def cac_payback_years(self) -> float:
        """CAC payback in years."""
        return self.cac_payback_months / 12

    @property
    def gtm_efficiency(self) -> float:
        """GTM efficiency ratio (ARR / GTM Cost)."""
        if self.total_gtm_cost > 0:
            return self.new_arr / self.total_gtm_cost
        return 0.0

    def summary(self) -> str:
        """Return formatted summary of unit economics."""
        lines = [
            f"Unit Economics{': ' + self.period if self.period else ''}",
            "=" * 50,
            "",
            "COSTS",
            "-" * 40,
            f"  Sales Cost:      ${self.total_sales_cost:,.0f}",
            f"  Marketing Cost:  ${self.total_marketing_cost:,.0f}",
            f"  Total GTM:       ${self.total_gtm_cost:,.0f}",
            "",
            "RESULTS",
            "-" * 40,
            f"  New Customers:   {self.new_customers:,}",
            f"  New ARR:         ${self.new_arr:,.0f}",
            "",
            "KEY METRICS",
            "-" * 40,
            f"  CAC:             ${self.cac:,.0f}",
            f"  LTV:             ${self.ltv:,.0f}",
            f"  LTV/CAC:         {self.ltv_cac_ratio:.1f}x",
            f"  CAC Payback:     {self.cac_payback_months} months",
            f"  GTM Efficiency:  {self.gtm_efficiency:.2f}x",
        ]

        if self.magic_number > 0:
            lines.append(f"  Magic Number:    {self.magic_number:.2f}")

        # Add health indicators
        lines.extend([
            "",
            "HEALTH INDICATORS",
            "-" * 40,
        ])

        # LTV/CAC benchmark
        if self.ltv_cac_ratio >= 3.0:
            lines.append(f"  LTV/CAC:         GOOD (>3x)")
        elif self.ltv_cac_ratio >= 2.0:
            lines.append(f"  LTV/CAC:         OK (2-3x)")
        else:
            lines.append(f"  LTV/CAC:         WARNING (<2x)")

        # Payback benchmark
        if self.cac_payback_months <= 12:
            lines.append(f"  CAC Payback:     GOOD (≤12 months)")
        elif self.cac_payback_months <= 18:
            lines.append(f"  CAC Payback:     OK (12-18 months)")
        else:
            lines.append(f"  CAC Payback:     WARNING (>18 months)")

        return "\n".join(lines)


@dataclass
class TeamCost:
    """
    Team cost breakdown by role.

    Used for calculating S&M spend.
    """

    # Headcount
    sdr_count: int = 0
    ae_count: int = 0
    se_count: int = 0

    # Annual costs per head
    sdr_cost: float = DEFAULT_COSTS["sdr_fully_loaded"]
    ae_cost: float = DEFAULT_COSTS["ae_fully_loaded"]
    se_cost: float = DEFAULT_COSTS["se_fully_loaded"]

    # Period (for prorating)
    months: int = 3  # Default to quarterly

    @property
    def total_sdr_cost(self) -> float:
        """Total SDR cost for period."""
        return self.sdr_count * self.sdr_cost * (self.months / 12)

    @property
    def total_ae_cost(self) -> float:
        """Total AE cost for period."""
        return self.ae_count * self.ae_cost * (self.months / 12)

    @property
    def total_se_cost(self) -> float:
        """Total SE cost for period."""
        return self.se_count * self.se_cost * (self.months / 12)

    @property
    def total_sales_cost(self) -> float:
        """Total sales team cost for period."""
        return self.total_sdr_cost + self.total_ae_cost + self.total_se_cost

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "sdr_count": self.sdr_count,
            "ae_count": self.ae_count,
            "se_count": self.se_count,
            "total_sdr_cost": self.total_sdr_cost,
            "total_ae_cost": self.total_ae_cost,
            "total_se_cost": self.total_se_cost,
            "total_sales_cost": self.total_sales_cost,
        }


def calculate_cac(
    marketing_spend: float,
    sales_cost: float,
    new_customers: int,
) -> float:
    """
    Calculate Customer Acquisition Cost.

    CAC = (Marketing Spend + Sales Cost) / New Customers

    Args:
        marketing_spend: Total marketing spend for period
        sales_cost: Total sales team cost for period (fully-loaded)
        new_customers: Number of new customers acquired

    Returns:
        CAC in dollars
    """
    if new_customers == 0:
        return 0.0

    return (marketing_spend + sales_cost) / new_customers


def calculate_ltv(
    avg_arr: float,
    gross_margin: float = 0.80,
    avg_lifetime_years: float = 4.0,
) -> float:
    """
    Calculate Customer Lifetime Value.

    LTV = ARR × Gross Margin × Average Lifetime

    Args:
        avg_arr: Average annual contract value
        gross_margin: Gross margin percentage (0-1)
        avg_lifetime_years: Average customer lifetime in years

    Returns:
        LTV in dollars
    """
    return avg_arr * gross_margin * avg_lifetime_years


def calculate_payback(
    cac: float,
    avg_arr: float,
    gross_margin: float = 0.80,
) -> int:
    """
    Calculate CAC payback period in months.

    Payback = CAC / (Monthly ARR × Gross Margin)

    Args:
        cac: Customer acquisition cost
        avg_arr: Average annual contract value
        gross_margin: Gross margin percentage (0-1)

    Returns:
        Payback period in months (rounded up)
    """
    if avg_arr == 0 or cac == 0:
        return 0

    monthly_contribution = (avg_arr / 12) * gross_margin
    return math.ceil(cac / monthly_contribution)


def calculate_unit_economics(
    team_cost: TeamCost,
    marketing_spend: float,
    new_customers: int,
    new_arr: float,
    gross_margin: float = 0.80,
    avg_lifetime_years: float = 4.0,
    period: str = "",
    previous_quarter_sm: float = 0.0,
) -> UnitEconomics:
    """
    Calculate complete unit economics for a period.

    Args:
        team_cost: Team cost breakdown
        marketing_spend: Marketing spend for period
        new_customers: New customers acquired
        new_arr: New ARR from those customers
        gross_margin: Gross margin percentage
        avg_lifetime_years: Average customer lifetime
        period: Period name (e.g., "Q1FY26")
        previous_quarter_sm: Previous quarter S&M (for magic number)

    Returns:
        UnitEconomics with all calculated metrics
    """
    return UnitEconomics(
        period=period,
        total_sales_cost=team_cost.total_sales_cost,
        total_marketing_cost=marketing_spend,
        new_customers=new_customers,
        new_arr=new_arr,
        gross_margin=gross_margin,
        avg_customer_lifetime_years=avg_lifetime_years,
        previous_quarter_sm=previous_quarter_sm,
    )


def scenario_economics(
    current: UnitEconomics,
    add_sdrs: int = 0,
    add_aes: int = 0,
    add_ses: int = 0,
    marketing_change_pct: float = 0.0,
    incremental_customers: int = 0,
    incremental_arr: float = 0.0,
) -> UnitEconomics:
    """
    Calculate economics impact of adding headcount.

    "What happens to our economics if we add 2 AEs?"

    Args:
        current: Current unit economics
        add_sdrs: Number of SDRs to add
        add_aes: Number of AEs to add
        add_ses: Number of SEs to add
        marketing_change_pct: Marketing spend change (e.g., 0.10 = +10%)
        incremental_customers: Additional customers from new capacity
        incremental_arr: Additional ARR from new capacity

    Returns:
        New UnitEconomics with scenario applied
    """
    # Calculate incremental costs (quarterly)
    incremental_sdr_cost = add_sdrs * DEFAULT_COSTS["sdr_fully_loaded"] / 4
    incremental_ae_cost = add_aes * DEFAULT_COSTS["ae_fully_loaded"] / 4
    incremental_se_cost = add_ses * DEFAULT_COSTS["se_fully_loaded"] / 4

    incremental_sales_cost = incremental_sdr_cost + incremental_ae_cost + incremental_se_cost

    # Calculate new totals
    new_sales_cost = current.total_sales_cost + incremental_sales_cost
    new_marketing_cost = current.total_marketing_cost * (1 + marketing_change_pct)
    new_customers = current.new_customers + incremental_customers
    new_arr = current.new_arr + incremental_arr

    return UnitEconomics(
        period=f"{current.period} (scenario)",
        total_sales_cost=new_sales_cost,
        total_marketing_cost=new_marketing_cost,
        new_customers=new_customers,
        new_arr=new_arr,
        gross_margin=current.gross_margin,
        avg_customer_lifetime_years=current.avg_customer_lifetime_years,
        previous_quarter_sm=current.total_gtm_cost,  # Use current as baseline
    )


def compare_economics(
    baseline: UnitEconomics,
    scenario: UnitEconomics,
) -> dict:
    """
    Compare economics between baseline and scenario.

    Args:
        baseline: Baseline unit economics
        scenario: Scenario unit economics

    Returns:
        Dict with comparison metrics and deltas
    """
    return {
        "baseline": {
            "cac": baseline.cac,
            "ltv_cac": baseline.ltv_cac_ratio,
            "payback_months": baseline.cac_payback_months,
            "gtm_efficiency": baseline.gtm_efficiency,
        },
        "scenario": {
            "cac": scenario.cac,
            "ltv_cac": scenario.ltv_cac_ratio,
            "payback_months": scenario.cac_payback_months,
            "gtm_efficiency": scenario.gtm_efficiency,
        },
        "delta": {
            "cac": scenario.cac - baseline.cac,
            "cac_pct": ((scenario.cac / baseline.cac) - 1) * 100 if baseline.cac > 0 else 0,
            "ltv_cac": scenario.ltv_cac_ratio - baseline.ltv_cac_ratio,
            "payback_months": scenario.cac_payback_months - baseline.cac_payback_months,
            "gtm_efficiency": scenario.gtm_efficiency - baseline.gtm_efficiency,
            "gtm_cost": scenario.total_gtm_cost - baseline.total_gtm_cost,
            "arr": scenario.new_arr - baseline.new_arr,
        },
        "impact_summary": _summarize_impact(baseline, scenario),
    }


def _summarize_impact(baseline: UnitEconomics, scenario: UnitEconomics) -> str:
    """Generate impact summary text."""
    cac_change = ((scenario.cac / baseline.cac) - 1) * 100 if baseline.cac > 0 else 0
    payback_change = scenario.cac_payback_months - baseline.cac_payback_months
    arr_change = scenario.new_arr - baseline.new_arr
    cost_change = scenario.total_gtm_cost - baseline.total_gtm_cost

    parts = []

    # Cost impact
    if cost_change > 0:
        parts.append(f"+${cost_change:,.0f} GTM cost")
    elif cost_change < 0:
        parts.append(f"-${abs(cost_change):,.0f} GTM cost")

    # ARR impact
    if arr_change > 0:
        parts.append(f"+${arr_change:,.0f} ARR")
    elif arr_change < 0:
        parts.append(f"-${abs(arr_change):,.0f} ARR")

    # CAC impact
    if abs(cac_change) > 5:
        direction = "increases" if cac_change > 0 else "decreases"
        parts.append(f"CAC {direction} {abs(cac_change):.0f}%")

    # Payback impact
    if abs(payback_change) > 1:
        direction = "+" if payback_change > 0 else ""
        parts.append(f"payback {direction}{payback_change} months")

    return "; ".join(parts) if parts else "Minimal impact"


# =============================================================================
# Role Costs Model (NEW for v3 - Org Planning)
# =============================================================================

# OTE by role (from FY26 Excel Model)
ROLE_COSTS = {
    # ICs
    "ae_enterprise": 360_000,
    "ae_midmarket": 240_000,
    "se": 250_000,
    "sdr": 100_000,
    "csm": 220_000,
    "fde": 180_000,
    # Managers
    "mgr_ae_enterprise": 400_000,
    "mgr_ae_midmarket": 315_000,
    "mgr_se": 280_000,
    "mgr_sdr": 200_000,
    "mgr_csm": 300_000,
}


@dataclass
class RoleCosts:
    """
    Fully-loaded costs by role (annual OTE).

    Supports both IC and Manager costs for full org planning.
    """

    # Individual Contributors
    ae_enterprise: float = 360_000
    ae_midmarket: float = 240_000
    se: float = 250_000
    sdr: float = 100_000
    csm: float = 220_000
    fde: float = 180_000

    # Managers
    mgr_ae_enterprise: float = 400_000
    mgr_ae_midmarket: float = 315_000
    mgr_se: float = 280_000
    mgr_sdr: float = 200_000
    mgr_csm: float = 300_000

    def get_cost(self, role: str) -> float:
        """Get cost for a specific role."""
        return getattr(self, role, 0.0)


@dataclass
class OrgCost:
    """
    Full cost breakdown for an org composition.

    Includes IC costs, manager costs, and efficiency metrics.
    """

    period_months: int = 12

    # IC costs
    ae_enterprise_cost: float = 0.0
    ae_midmarket_cost: float = 0.0
    se_cost: float = 0.0
    sdr_cost: float = 0.0
    csm_cost: float = 0.0
    fde_cost: float = 0.0

    # Manager costs
    mgr_ae_enterprise_cost: float = 0.0
    mgr_ae_midmarket_cost: float = 0.0
    mgr_se_cost: float = 0.0
    mgr_sdr_cost: float = 0.0
    mgr_csm_cost: float = 0.0

    # Headcount (for reference)
    ae_enterprise_count: int = 0
    ae_midmarket_count: int = 0
    se_count: int = 0
    sdr_count: int = 0
    csm_count: int = 0
    fde_count: int = 0
    mgr_count: int = 0

    @property
    def ic_cost(self) -> float:
        """Total IC cost for period."""
        return (
            self.ae_enterprise_cost +
            self.ae_midmarket_cost +
            self.se_cost +
            self.sdr_cost +
            self.csm_cost +
            self.fde_cost
        )

    @property
    def manager_cost(self) -> float:
        """Total manager cost for period."""
        return (
            self.mgr_ae_enterprise_cost +
            self.mgr_ae_midmarket_cost +
            self.mgr_se_cost +
            self.mgr_sdr_cost +
            self.mgr_csm_cost
        )

    @property
    def total_cost(self) -> float:
        """Total S&M cost for period."""
        return self.ic_cost + self.manager_cost

    @property
    def monthly_cost(self) -> float:
        """Average monthly cost."""
        return self.total_cost / self.period_months if self.period_months > 0 else 0.0

    @property
    def total_ae_count(self) -> int:
        """Total AE count."""
        return self.ae_enterprise_count + self.ae_midmarket_count

    @property
    def cost_per_ae(self) -> float:
        """Total S&M cost per AE (useful for benchmarking)."""
        return self.total_cost / self.total_ae_count if self.total_ae_count > 0 else 0.0

    @property
    def by_role(self) -> dict[str, float]:
        """Cost breakdown by role."""
        return {
            "ae_enterprise": self.ae_enterprise_cost,
            "ae_midmarket": self.ae_midmarket_cost,
            "se": self.se_cost,
            "sdr": self.sdr_cost,
            "csm": self.csm_cost,
            "fde": self.fde_cost,
            "mgr_ae_enterprise": self.mgr_ae_enterprise_cost,
            "mgr_ae_midmarket": self.mgr_ae_midmarket_cost,
            "mgr_se": self.mgr_se_cost,
            "mgr_sdr": self.mgr_sdr_cost,
            "mgr_csm": self.mgr_csm_cost,
        }

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "period_months": self.period_months,
            "ic_cost": self.ic_cost,
            "manager_cost": self.manager_cost,
            "total_cost": self.total_cost,
            "monthly_cost": self.monthly_cost,
            "cost_per_ae": self.cost_per_ae,
            "by_role": self.by_role,
            "headcount": {
                "ae_enterprise": self.ae_enterprise_count,
                "ae_midmarket": self.ae_midmarket_count,
                "total_aes": self.total_ae_count,
                "ses": self.se_count,
                "sdrs": self.sdr_count,
                "csms": self.csm_count,
                "fdes": self.fde_count,
                "managers": self.mgr_count,
            },
        }

    def summary(self) -> str:
        """Return formatted summary of org cost."""
        lines = [
            f"Org Cost ({self.period_months} months)",
            "=" * 50,
            "",
            "INDIVIDUAL CONTRIBUTORS",
            "-" * 40,
            f"  Enterprise AEs ({self.ae_enterprise_count}): ${self.ae_enterprise_cost:,.0f}",
            f"  Mid-Market AEs ({self.ae_midmarket_count}):  ${self.ae_midmarket_cost:,.0f}",
            f"  Sales Engineers ({self.se_count}):    ${self.se_cost:,.0f}",
            f"  SDRs ({self.sdr_count}):              ${self.sdr_cost:,.0f}",
            f"  CSMs ({self.csm_count}):              ${self.csm_cost:,.0f}",
            f"  FDEs ({self.fde_count}):              ${self.fde_cost:,.0f}",
            f"  Total IC Cost:          ${self.ic_cost:,.0f}",
            "",
            "MANAGERS",
            "-" * 40,
            f"  AE Managers (Ent):      ${self.mgr_ae_enterprise_cost:,.0f}",
            f"  AE Managers (MM):       ${self.mgr_ae_midmarket_cost:,.0f}",
            f"  SE Managers:            ${self.mgr_se_cost:,.0f}",
            f"  SDR Managers:           ${self.mgr_sdr_cost:,.0f}",
            f"  CSM Managers:           ${self.mgr_csm_cost:,.0f}",
            f"  Total Manager Cost:     ${self.manager_cost:,.0f}",
            "",
            "TOTALS",
            "-" * 40,
            f"  Total S&M Cost:         ${self.total_cost:,.0f}",
            f"  Monthly S&M:            ${self.monthly_cost:,.0f}",
            f"  Cost per AE:            ${self.cost_per_ae:,.0f}",
        ]
        return "\n".join(lines)


def calculate_org_cost(
    aes_enterprise: int = 0,
    aes_midmarket: int = 0,
    ses: int = 0,
    sdrs: int = 0,
    csms: int = 0,
    fdes: int = 0,
    ae_mgrs_enterprise: int = 0,
    ae_mgrs_midmarket: int = 0,
    se_mgrs: int = 0,
    sdr_mgrs: int = 0,
    csm_mgrs: int = 0,
    costs: Optional[RoleCosts] = None,
    period_months: int = 12,
) -> OrgCost:
    """
    Calculate total cost for a team composition.

    Args:
        aes_enterprise: Enterprise AE count
        aes_midmarket: Mid-Market AE count
        ses: SE count
        sdrs: SDR count
        csms: CSM count
        fdes: FDE count
        ae_mgrs_enterprise: Enterprise AE Manager count
        ae_mgrs_midmarket: MM AE Manager count
        se_mgrs: SE Manager count
        sdr_mgrs: SDR Manager count
        csm_mgrs: CSM Manager count
        costs: Role costs to use (defaults to RoleCosts())
        period_months: Period length in months

    Returns:
        OrgCost with full cost breakdown
    """
    if costs is None:
        costs = RoleCosts()

    # Pro-rate annual costs to period
    prorate = period_months / 12

    return OrgCost(
        period_months=period_months,
        # IC costs
        ae_enterprise_cost=aes_enterprise * costs.ae_enterprise * prorate,
        ae_midmarket_cost=aes_midmarket * costs.ae_midmarket * prorate,
        se_cost=ses * costs.se * prorate,
        sdr_cost=sdrs * costs.sdr * prorate,
        csm_cost=csms * costs.csm * prorate,
        fde_cost=fdes * costs.fde * prorate,
        # Manager costs
        mgr_ae_enterprise_cost=ae_mgrs_enterprise * costs.mgr_ae_enterprise * prorate,
        mgr_ae_midmarket_cost=ae_mgrs_midmarket * costs.mgr_ae_midmarket * prorate,
        mgr_se_cost=se_mgrs * costs.mgr_se * prorate,
        mgr_sdr_cost=sdr_mgrs * costs.mgr_sdr * prorate,
        mgr_csm_cost=csm_mgrs * costs.mgr_csm * prorate,
        # Headcount
        ae_enterprise_count=aes_enterprise,
        ae_midmarket_count=aes_midmarket,
        se_count=ses,
        sdr_count=sdrs,
        csm_count=csms,
        fde_count=fdes,
        mgr_count=ae_mgrs_enterprise + ae_mgrs_midmarket + se_mgrs + sdr_mgrs + csm_mgrs,
    )


def calculate_org_cost_from_team(
    team,  # DerivedTeam from team_structure.py
    costs: Optional[RoleCosts] = None,
    period_months: int = 12,
) -> OrgCost:
    """
    Calculate org cost from a DerivedTeam object.

    Args:
        team: DerivedTeam from team_structure.py
        costs: Role costs to use
        period_months: Period length in months

    Returns:
        OrgCost with full cost breakdown
    """
    return calculate_org_cost(
        aes_enterprise=team.aes_enterprise,
        aes_midmarket=team.aes_midmarket,
        ses=team.ses,
        sdrs=team.sdrs,
        csms=team.csms,
        fdes=team.fdes,
        ae_mgrs_enterprise=team.ae_managers_enterprise,
        ae_mgrs_midmarket=team.ae_managers_midmarket,
        se_mgrs=team.se_managers,
        sdr_mgrs=team.sdr_managers,
        csm_mgrs=team.csm_managers,
        costs=costs,
        period_months=period_months,
    )


def calculate_sm_efficiency(
    org_cost: OrgCost,
    arr_generated: float,
    total_aes: Optional[int] = None,
) -> dict:
    """
    Calculate S&M efficiency metrics.

    Includes Magic Number, cost per dollar ARR, and ARR per AE.

    Args:
        org_cost: OrgCost from calculate_org_cost()
        arr_generated: ARR generated during the period
        total_aes: Override total AE count (defaults to org_cost.total_ae_count)

    Returns:
        Dict with S&M efficiency metrics
    """
    if total_aes is None:
        total_aes = org_cost.total_ae_count

    # Quarterly S&M for magic number (assumes 12-month period)
    quarterly_sm = org_cost.total_cost / 4 if org_cost.period_months == 12 else org_cost.total_cost / (org_cost.period_months / 3)

    # Magic Number = Net New ARR / Previous Quarter S&M
    magic_number = arr_generated / quarterly_sm if quarterly_sm > 0 else 0.0

    return {
        "arr_generated": arr_generated,
        "total_sm_cost": org_cost.total_cost,
        "quarterly_sm": quarterly_sm,
        "cost_per_dollar_arr": org_cost.total_cost / arr_generated if arr_generated > 0 else 0.0,
        "arr_per_ae": arr_generated / total_aes if total_aes > 0 else 0.0,
        "magic_number": magic_number,
        "magic_number_health": "GOOD" if magic_number >= 1.0 else "OK" if magic_number >= 0.75 else "WARNING",
        "total_aes": total_aes,
        "headcount": {
            "ics": org_cost.ae_enterprise_count + org_cost.ae_midmarket_count + org_cost.se_count + org_cost.sdr_count + org_cost.csm_count + org_cost.fde_count,
            "managers": org_cost.mgr_count,
            "total": org_cost.ae_enterprise_count + org_cost.ae_midmarket_count + org_cost.se_count + org_cost.sdr_count + org_cost.csm_count + org_cost.fde_count + org_cost.mgr_count,
        },
    }


# =============================================================================
# Variable Compensation / Accelerator Modeling (v3.1)
# =============================================================================


@dataclass
class CompStructure:
    """
    Compensation structure for a role.

    Defines base/variable split, quota, and accelerator tiers.
    """
    role: str
    segment: str = "mid_market"

    # OTE breakdown
    ote: float = 240_000
    base_pct: float = 0.50  # 50% base, 50% variable
    variable_pct: float = 0.50

    # Quota
    annual_quota: float = 650_000
    quota_to_ote_ratio: float = field(init=False)

    # Expected attainment for planning
    expected_attainment: float = 0.80  # 80% of quota

    def __post_init__(self):
        """Calculate derived metrics."""
        variable_at_plan = self.ote * self.variable_pct
        self.quota_to_ote_ratio = self.annual_quota / self.ote if self.ote > 0 else 0

    @property
    def base_salary(self) -> float:
        """Annual base salary."""
        return self.ote * self.base_pct

    @property
    def variable_at_plan(self) -> float:
        """Variable comp at 100% attainment."""
        return self.ote * self.variable_pct

    @property
    def expected_variable(self) -> float:
        """Expected variable based on attainment assumption."""
        return self.variable_at_plan * self.expected_attainment

    @property
    def expected_total(self) -> float:
        """Expected total comp = base + expected variable."""
        return self.base_salary + self.expected_variable


@dataclass
class AcceleratorTier:
    """A single accelerator tier."""
    min_attainment: float  # e.g., 1.0 for 100%
    max_attainment: float  # e.g., 1.5 for 150%
    multiplier: float      # e.g., 1.5 for 1.5x


@dataclass
class AcceleratorPlan:
    """
    Accelerator structure for variable compensation.

    Models how commission rates change at different attainment levels.
    Typical structure:
    - 0-80%: 0.5x rate (reduced for missing quota)
    - 80-100%: 1.0x rate (standard)
    - 100-150%: 1.5x rate (accelerated)
    - 150%+: 2.0x rate (super accelerated)
    """
    tiers: list[AcceleratorTier] = field(default_factory=list)

    def __post_init__(self):
        """Set default tiers if empty."""
        if not self.tiers:
            self.tiers = [
                AcceleratorTier(min_attainment=0.0, max_attainment=0.80, multiplier=0.5),
                AcceleratorTier(min_attainment=0.80, max_attainment=1.0, multiplier=1.0),
                AcceleratorTier(min_attainment=1.0, max_attainment=1.5, multiplier=1.5),
                AcceleratorTier(min_attainment=1.5, max_attainment=float('inf'), multiplier=2.0),
            ]

    def get_multiplier(self, attainment: float) -> float:
        """Get the multiplier for a given attainment level."""
        for tier in self.tiers:
            if tier.min_attainment <= attainment < tier.max_attainment:
                return tier.multiplier
        return 1.0


@dataclass
class VariableCompCalculation:
    """
    Result of variable compensation calculation.
    """
    comp_structure: CompStructure
    actual_attainment: float
    accelerator_plan: AcceleratorPlan

    # Calculated values
    base_salary: float = field(init=False)
    variable_at_plan: float = field(init=False)
    effective_multiplier: float = field(init=False)
    actual_variable: float = field(init=False)
    total_compensation: float = field(init=False)

    # Bookings achieved
    bookings_achieved: float = field(init=False)

    def __post_init__(self):
        """Calculate compensation."""
        self.base_salary = self.comp_structure.base_salary
        self.variable_at_plan = self.comp_structure.variable_at_plan

        # Calculate effective multiplier using tiered accelerators
        self.effective_multiplier = self._calculate_blended_multiplier()

        # Variable = base variable × attainment × blended multiplier
        self.actual_variable = self.variable_at_plan * self.actual_attainment * self.effective_multiplier

        self.total_compensation = self.base_salary + self.actual_variable
        self.bookings_achieved = self.comp_structure.annual_quota * self.actual_attainment

    def _calculate_blended_multiplier(self) -> float:
        """
        Calculate blended multiplier for tiered accelerators.

        For attainment of 120%:
        - First 80% earns at 0.5x
        - Next 20% (80-100%) earns at 1.0x
        - Next 20% (100-120%) earns at 1.5x
        """
        total_weighted = 0.0
        remaining = self.actual_attainment

        for tier in sorted(self.accelerator_plan.tiers, key=lambda t: t.min_attainment):
            tier_range = tier.max_attainment - tier.min_attainment
            if remaining <= 0:
                break

            # How much of this tier applies?
            if self.actual_attainment <= tier.min_attainment:
                continue

            applicable = min(remaining, tier_range)
            if self.actual_attainment > tier.max_attainment:
                applicable = tier_range
            elif self.actual_attainment > tier.min_attainment:
                applicable = self.actual_attainment - tier.min_attainment

            total_weighted += applicable * tier.multiplier
            remaining = max(0, self.actual_attainment - tier.max_attainment)

        return total_weighted / self.actual_attainment if self.actual_attainment > 0 else 1.0

    @property
    def cost_per_dollar_booked(self) -> float:
        """Comp cost per dollar of bookings."""
        return self.total_compensation / self.bookings_achieved if self.bookings_achieved > 0 else 0

    @property
    def comp_efficiency(self) -> float:
        """Bookings per dollar of comp (inverse of cost_per_dollar)."""
        return self.bookings_achieved / self.total_compensation if self.total_compensation > 0 else 0

    def summary(self) -> str:
        """Return formatted summary."""
        return f"""
Variable Comp Calculation
=========================
Role: {self.comp_structure.role} ({self.comp_structure.segment})
Attainment: {self.actual_attainment:.0%}

Base Salary:           ${self.base_salary:,.0f}
Variable at Plan:      ${self.variable_at_plan:,.0f}
Effective Multiplier:  {self.effective_multiplier:.2f}x
Actual Variable:       ${self.actual_variable:,.0f}
---
Total Compensation:    ${self.total_compensation:,.0f}

Bookings Achieved:     ${self.bookings_achieved:,.0f}
Cost per $ Booked:     ${self.cost_per_dollar_booked:.3f}
"""


# Pre-defined comp structures by role and segment
DEFAULT_COMP_STRUCTURES = {
    "ae_enterprise": CompStructure(
        role="AE",
        segment="enterprise",
        ote=360_000,
        base_pct=0.50,
        variable_pct=0.50,
        annual_quota=1_800_000,
    ),
    "ae_midmarket": CompStructure(
        role="AE",
        segment="mid_market",
        ote=240_000,
        base_pct=0.50,
        variable_pct=0.50,
        annual_quota=650_000,
    ),
    "ae_smb": CompStructure(
        role="AE",
        segment="smb",
        ote=160_000,
        base_pct=0.50,
        variable_pct=0.50,
        annual_quota=400_000,
    ),
    "sdr": CompStructure(
        role="SDR",
        segment="all",
        ote=100_000,
        base_pct=0.60,  # SDRs typically have higher base %
        variable_pct=0.40,
        annual_quota=0,  # SDRs have meeting/SQL targets, not $ quota
    ),
    "csm": CompStructure(
        role="CSM",
        segment="all",
        ote=220_000,
        base_pct=0.70,  # CSMs have higher base
        variable_pct=0.30,
        annual_quota=0,  # Renewal targets, not new bookings
    ),
    "se": CompStructure(
        role="SE",
        segment="all",
        ote=250_000,
        base_pct=0.80,  # SEs mostly base
        variable_pct=0.20,
        annual_quota=0,  # Team bonus, not individual quota
    ),
}

# Default accelerator plan (standard B2B SaaS)
DEFAULT_ACCELERATOR_PLAN = AcceleratorPlan()


def calculate_variable_comp(
    attainment: float,
    role: str = "ae_midmarket",
    comp_structure: Optional[CompStructure] = None,
    accelerator_plan: Optional[AcceleratorPlan] = None,
) -> VariableCompCalculation:
    """
    Calculate variable compensation for a given attainment level.

    Args:
        attainment: Quota attainment as decimal (e.g., 1.2 for 120%)
        role: Role key from DEFAULT_COMP_STRUCTURES
        comp_structure: Override comp structure
        accelerator_plan: Override accelerator plan

    Returns:
        VariableCompCalculation with full breakdown
    """
    if comp_structure is None:
        comp_structure = DEFAULT_COMP_STRUCTURES.get(role, DEFAULT_COMP_STRUCTURES["ae_midmarket"])

    if accelerator_plan is None:
        accelerator_plan = DEFAULT_ACCELERATOR_PLAN

    return VariableCompCalculation(
        comp_structure=comp_structure,
        actual_attainment=attainment,
        accelerator_plan=accelerator_plan,
    )


def calculate_team_variable_comp(
    attainment_by_rep: list[float],
    role: str = "ae_midmarket",
    comp_structure: Optional[CompStructure] = None,
    accelerator_plan: Optional[AcceleratorPlan] = None,
) -> dict:
    """
    Calculate total team variable comp across multiple reps.

    Args:
        attainment_by_rep: List of attainment levels for each rep
        role: Role key for all reps
        comp_structure: Override comp structure
        accelerator_plan: Override accelerator plan

    Returns:
        Dict with team totals and per-rep breakdowns
    """
    calcs = []
    for att in attainment_by_rep:
        calcs.append(calculate_variable_comp(att, role, comp_structure, accelerator_plan))

    total_base = sum(c.base_salary for c in calcs)
    total_variable = sum(c.actual_variable for c in calcs)
    total_comp = sum(c.total_compensation for c in calcs)
    total_bookings = sum(c.bookings_achieved for c in calcs)
    avg_attainment = sum(attainment_by_rep) / len(attainment_by_rep) if attainment_by_rep else 0

    return {
        "rep_count": len(calcs),
        "avg_attainment": avg_attainment,
        "total_base_salary": total_base,
        "total_variable": total_variable,
        "total_compensation": total_comp,
        "total_bookings": total_bookings,
        "cost_per_dollar_booked": total_comp / total_bookings if total_bookings > 0 else 0,
        "avg_comp_per_rep": total_comp / len(calcs) if calcs else 0,
        "reps": [
            {
                "attainment": c.actual_attainment,
                "variable": c.actual_variable,
                "total_comp": c.total_compensation,
                "bookings": c.bookings_achieved,
            }
            for c in calcs
        ],
    }


def project_comp_scenarios(
    quota: float,
    ote: float,
    accelerator_plan: Optional[AcceleratorPlan] = None,
    attainment_levels: Optional[list[float]] = None,
) -> list[dict]:
    """
    Project compensation across multiple attainment scenarios.

    Useful for understanding comp exposure at different performance levels.

    Args:
        quota: Annual quota
        ote: On-target earnings
        accelerator_plan: Accelerator structure
        attainment_levels: List of attainment levels to model

    Returns:
        List of scenario results
    """
    if attainment_levels is None:
        attainment_levels = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]

    if accelerator_plan is None:
        accelerator_plan = DEFAULT_ACCELERATOR_PLAN

    comp_structure = CompStructure(
        role="Custom",
        segment="custom",
        ote=ote,
        base_pct=0.50,
        variable_pct=0.50,
        annual_quota=quota,
    )

    results = []
    for att in attainment_levels:
        calc = calculate_variable_comp(att, comp_structure=comp_structure, accelerator_plan=accelerator_plan)
        results.append({
            "attainment": att,
            "attainment_pct": f"{att:.0%}",
            "bookings": calc.bookings_achieved,
            "base": calc.base_salary,
            "variable": calc.actual_variable,
            "total_comp": calc.total_compensation,
            "effective_multiplier": calc.effective_multiplier,
            "cost_per_dollar": calc.cost_per_dollar_booked,
        })

    return results


def calculate_quota_to_ote_health(
    quota: float,
    ote: float,
    segment: str = "mid_market",
) -> dict:
    """
    Evaluate quota-to-OTE ratio health.

    Industry benchmarks:
    - Enterprise: 5-6x (high ACV, longer cycles)
    - Mid-Market: 2.5-3.5x
    - SMB: 2-2.5x

    Args:
        quota: Annual quota
        ote: On-target earnings
        segment: Segment for benchmarking

    Returns:
        Dict with ratio and health assessment
    """
    benchmarks = {
        "enterprise": {"min": 4.5, "target": 5.0, "max": 6.0},
        "mid_market": {"min": 2.5, "target": 3.0, "max": 3.5},
        "smb": {"min": 2.0, "target": 2.5, "max": 3.0},
    }

    bench = benchmarks.get(segment, benchmarks["mid_market"])
    ratio = quota / ote if ote > 0 else 0

    if ratio < bench["min"]:
        health = "LOW"
        recommendation = f"Ratio is low. Consider increasing quota or reducing OTE. Target: {bench['target']}x"
    elif ratio > bench["max"]:
        health = "HIGH"
        recommendation = f"Ratio is high. May struggle to attract talent. Target: {bench['target']}x"
    else:
        health = "HEALTHY"
        recommendation = "Ratio is within healthy range for this segment."

    return {
        "quota": quota,
        "ote": ote,
        "ratio": ratio,
        "segment": segment,
        "benchmark_min": bench["min"],
        "benchmark_target": bench["target"],
        "benchmark_max": bench["max"],
        "health": health,
        "recommendation": recommendation,
    }


def estimate_rep_productivity(
    role: str,
    months_ramped: int = 4,
    segment: str = "mid_market",
) -> dict:
    """
    Estimate productivity contribution from a new rep.

    Args:
        role: "sdr", "ae", or "se"
        months_ramped: Months since start (for ramp adjustment)
        segment: AE segment for quota calculation

    Returns:
        Dict with productivity metrics
    """
    if role == "sdr":
        # SDR productivity in SQLs
        base_meetings_monthly = 15
        meeting_to_sql = 0.50

        # Ramp curve
        if months_ramped < 1:
            ramp = 0.0
        elif months_ramped < 2:
            ramp = 0.50
        elif months_ramped < 3:
            ramp = 0.75
        else:
            ramp = 1.0

        monthly_meetings = base_meetings_monthly * ramp
        monthly_sqls = monthly_meetings * meeting_to_sql
        quarterly_sqls = monthly_sqls * 3

        return {
            "role": "SDR",
            "ramp_factor": ramp,
            "monthly_meetings": monthly_meetings,
            "monthly_sqls": monthly_sqls,
            "quarterly_sqls": quarterly_sqls,
            "unit": "SQLs",
        }

    elif role == "ae":
        # AE productivity in bookings
        quotas = {
            "enterprise": 1_800_000,
            "mid_market": 650_000,
            "smb": 400_000,
        }
        annual_quota = quotas.get(segment, 650_000)
        attainment = 0.80

        # Ramp curve
        if months_ramped < 1:
            ramp = 0.0
        elif months_ramped < 2:
            ramp = 0.15
        elif months_ramped < 3:
            ramp = 0.50
        else:
            ramp = 1.0

        quarterly_bookings = (annual_quota / 4) * attainment * ramp

        return {
            "role": "AE",
            "segment": segment,
            "ramp_factor": ramp,
            "annual_quota": annual_quota,
            "attainment": attainment,
            "quarterly_bookings": quarterly_bookings,
            "unit": "bookings",
        }

    elif role == "se":
        # SE productivity in POCs
        monthly_pocs = 4

        # Ramp curve (longer for SEs)
        if months_ramped < 1:
            ramp = 0.0
        elif months_ramped < 2:
            ramp = 0.25
        elif months_ramped < 3:
            ramp = 0.60
        else:
            ramp = 1.0

        quarterly_pocs = monthly_pocs * 3 * ramp

        return {
            "role": "SE",
            "ramp_factor": ramp,
            "monthly_pocs": monthly_pocs * ramp,
            "quarterly_pocs": quarterly_pocs,
            "unit": "POCs",
        }

    return {}

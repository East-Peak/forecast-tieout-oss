"""
GTM Segment Productivity and Self-Serve Stream Modeling.

Models segment-specific productivity (Enterprise vs Commercial) and
the self-serve/PLG revenue stream.

Example usage:
    from gtm_model.segments import (
        SegmentProductivity,
        SelfServeStream,
        calculate_segment_capacity,
        calculate_self_serve_arr,
    )

    # Enterprise vs Commercial productivity
    ent = SegmentProductivity.enterprise()
    comm = SegmentProductivity.commercial()

    print(f"Enterprise ACV: ${ent.avg_acv:,}")
    print(f"Commercial ACV: ${comm.avg_acv:,}")

    # Self-serve projections
    ss = SelfServeStream()
    arr = ss.project_arr(months=12)
    print(f"Self-serve FY ARR: ${arr:,}")
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import math

from dateutil.relativedelta import relativedelta


@dataclass
class SegmentProductivity:
    """
    Productivity assumptions for a sales segment.

    Captures ACV, sales cycle, close rates, quotas, and ramp curves
    that differ between Enterprise and Commercial motions.
    """

    name: str = "segment"

    # Deal characteristics
    avg_acv: float = 300_000          # Average deal size
    median_acv: float = 250_000       # Median deal size
    sales_cycle_days: int = 90        # Days from S0 to close
    close_rate: float = 0.20          # S0 → Closed Won rate

    # Quota and attainment
    annual_quota: float = 1_000_000   # Annual quota
    attainment_rate: float = 0.80     # Expected attainment
    deals_per_ae_per_year: float = 3  # Deals closed per AE

    # Ramp curve (months to productivity)
    ramp_months: int = 4              # Months to full productivity
    ramp_curve: dict = field(default_factory=lambda: {
        1: 0.00,
        2: 0.15,
        3: 0.50,
        4: 1.00,
    })

    # Stage conversions
    stage_conversions: dict = field(default_factory=lambda: {
        "s0_to_s1": 0.65,
        "s1_to_s2": 0.50,
        "s2_to_s3": 0.55,
        "s3_to_s4": 0.70,
        "s4_to_s5": 0.85,
        "s5_to_won": 0.80,
    })

    @property
    def monthly_quota(self) -> float:
        """Monthly quota."""
        return self.annual_quota / 12

    @property
    def effective_annual_capacity(self) -> float:
        """Effective annual capacity accounting for attainment."""
        return self.annual_quota * self.attainment_rate

    @property
    def sales_cycle_months(self) -> float:
        """Sales cycle in months."""
        return self.sales_cycle_days / 30

    def get_ramp_factor(self, month: int) -> float:
        """Get ramp factor for a specific month since hire."""
        if month in self.ramp_curve:
            return self.ramp_curve[month]
        elif month >= max(self.ramp_curve.keys()):
            return 1.0
        else:
            return 0.0

    def calculate_ramped_capacity(self, months_since_start: int) -> float:
        """Calculate monthly capacity accounting for ramp."""
        ramp = self.get_ramp_factor(months_since_start)
        return self.monthly_quota * self.attainment_rate * ramp

    @classmethod
    def enterprise(cls) -> "SegmentProductivity":
        """Create Enterprise segment with default assumptions."""
        return cls(
            name="enterprise",
            avg_acv=500_000,
            median_acv=400_000,
            sales_cycle_days=120,
            close_rate=0.25,
            annual_quota=1_800_000,
            attainment_rate=0.75,
            deals_per_ae_per_year=3,
            ramp_months=6,
            ramp_curve={
                1: 0.00,
                2: 0.10,
                3: 0.30,
                4: 0.50,
                5: 0.75,
                6: 1.00,
            },
            stage_conversions={
                "s0_to_s1": 0.70,
                "s1_to_s2": 0.55,
                "s2_to_s3": 0.60,
                "s3_to_s4": 0.75,
                "s4_to_s5": 0.90,
                "s5_to_won": 0.85,
            },
        )

    @classmethod
    def commercial(cls) -> "SegmentProductivity":
        """Create Commercial/Mid-Market segment with default assumptions."""
        return cls(
            name="commercial",
            avg_acv=150_000,
            median_acv=120_000,
            sales_cycle_days=75,
            close_rate=0.20,
            annual_quota=650_000,
            attainment_rate=0.80,
            deals_per_ae_per_year=4,
            ramp_months=4,
            ramp_curve={
                1: 0.00,
                2: 0.15,
                3: 0.50,
                4: 1.00,
            },
            stage_conversions={
                "s0_to_s1": 0.65,
                "s1_to_s2": 0.50,
                "s2_to_s3": 0.55,
                "s3_to_s4": 0.70,
                "s4_to_s5": 0.85,
                "s5_to_won": 0.80,
            },
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "avg_acv": self.avg_acv,
            "sales_cycle_days": self.sales_cycle_days,
            "close_rate": self.close_rate,
            "annual_quota": self.annual_quota,
            "attainment_rate": self.attainment_rate,
            "deals_per_ae_per_year": self.deals_per_ae_per_year,
            "ramp_months": self.ramp_months,
            "effective_annual_capacity": self.effective_annual_capacity,
        }

    def summary(self) -> str:
        """Return formatted summary."""
        lines = [
            f"{self.name.upper()} Segment Productivity",
            "=" * 50,
            "",
            "DEAL CHARACTERISTICS",
            "-" * 40,
            f"  Avg ACV:           ${self.avg_acv:,.0f}",
            f"  Sales Cycle:       {self.sales_cycle_days} days ({self.sales_cycle_months:.1f} months)",
            f"  Close Rate:        {self.close_rate:.0%}",
            f"  Deals/AE/Year:     {self.deals_per_ae_per_year:.1f}",
            "",
            "QUOTA & CAPACITY",
            "-" * 40,
            f"  Annual Quota:      ${self.annual_quota:,.0f}",
            f"  Monthly Quota:     ${self.monthly_quota:,.0f}",
            f"  Attainment Rate:   {self.attainment_rate:.0%}",
            f"  Effective Capacity: ${self.effective_annual_capacity:,.0f}/AE/year",
            "",
            "RAMP",
            "-" * 40,
            f"  Months to Full:    {self.ramp_months}",
        ]
        for month, factor in sorted(self.ramp_curve.items()):
            lines.append(f"    Month {month}: {factor:.0%}")

        return "\n".join(lines)


@dataclass
class SelfServeStream:
    """
    Self-serve/PLG revenue stream modeling.

    Models the PLG funnel, unit economics, and projections separate
    from the sales-led motion.
    """

    # Targets
    fy_arr_target: float = 5_000_000  # Annual target

    # Unit economics
    avg_acv: float = 15_000           # Average self-serve deal
    monthly_price: float = 1_250      # Monthly price point

    # Funnel
    monthly_signups: int = 200        # Monthly free signups
    free_to_paid_rate: float = 0.05   # Conversion rate
    time_to_convert_days: int = 30    # Days to convert

    # Expansion
    expansion_rate: float = 0.20      # % that expand via sales
    expansion_acv_multiplier: float = 5  # Expansion deal multiple

    # Churn
    monthly_churn_rate: float = 0.03  # 3% monthly churn

    # Cost model
    monthly_marketing_spend: float = 75_000
    monthly_product_cost: float = 50_000
    cac: float = 2_500                # CAC for self-serve

    @property
    def paid_customers_per_month(self) -> int:
        """New paid customers per month."""
        return int(self.monthly_signups * self.free_to_paid_rate)

    @property
    def monthly_new_arr(self) -> float:
        """ARR from new paid customers per month."""
        return self.paid_customers_per_month * self.avg_acv

    @property
    def annual_churn_rate(self) -> float:
        """Annual churn rate from monthly."""
        return 1 - (1 - self.monthly_churn_rate) ** 12

    @property
    def avg_expansion_acv(self) -> float:
        """Average expansion deal size."""
        return self.avg_acv * self.expansion_acv_multiplier

    @property
    def monthly_total_cost(self) -> float:
        """Total monthly PLG cost."""
        return self.monthly_marketing_spend + self.monthly_product_cost

    @property
    def ltv(self) -> float:
        """Lifetime value estimate."""
        # Simple LTV = ACV / annual_churn_rate
        if self.annual_churn_rate > 0:
            return self.avg_acv / self.annual_churn_rate
        return self.avg_acv * 5  # 5 year max

    @property
    def ltv_cac_ratio(self) -> float:
        """LTV/CAC ratio."""
        return self.ltv / self.cac if self.cac > 0 else 0

    def project_arr(
        self,
        months: int = 12,
        starting_arr: float = 0,
        include_expansion: bool = True,
    ) -> dict:
        """
        Project self-serve ARR over time.

        Args:
            months: Number of months to project
            starting_arr: Starting ARR base
            include_expansion: Whether to include expansion revenue

        Returns:
            Dict with monthly and total projections
        """
        monthly_data = []
        current_arr = starting_arr
        total_customers = int(starting_arr / self.avg_acv) if self.avg_acv > 0 else 0

        for month in range(1, months + 1):
            # New customers
            new_customers = self.paid_customers_per_month
            new_arr = new_customers * self.avg_acv

            # Churn
            churned_customers = int(total_customers * self.monthly_churn_rate)
            churned_arr = churned_customers * self.avg_acv

            # Expansion (on existing base after 6 months)
            expansion_arr = 0
            if include_expansion and month > 6:
                expansion_eligible = int(total_customers * 0.1)  # 10% eligible/month
                expanding = int(expansion_eligible * self.expansion_rate)
                expansion_arr = expanding * (self.avg_expansion_acv - self.avg_acv)

            # Net change
            net_new_arr = new_arr - churned_arr + expansion_arr
            current_arr += net_new_arr
            total_customers += new_customers - churned_customers

            monthly_data.append({
                "month": month,
                "new_customers": new_customers,
                "churned_customers": churned_customers,
                "total_customers": total_customers,
                "new_arr": new_arr,
                "churned_arr": churned_arr,
                "expansion_arr": expansion_arr,
                "net_new_arr": net_new_arr,
                "ending_arr": current_arr,
            })

        return {
            "monthly": monthly_data,
            "total_net_new_arr": sum(m["net_new_arr"] for m in monthly_data),
            "ending_arr": current_arr,
            "ending_customers": total_customers,
            "avg_monthly_net_new": sum(m["net_new_arr"] for m in monthly_data) / months,
        }

    def calculate_required_signups(self, target_arr: float, months: int = 12) -> int:
        """
        Calculate required monthly signups to hit target ARR.

        Args:
            target_arr: Target ARR to achieve
            months: Months to achieve it

        Returns:
            Required monthly signups
        """
        # Simplified: assumes steady state
        # Net new ARR/month = signups × conversion × ACV - churn
        # This requires iteration to solve properly

        # Approximate: ignore churn ramp
        monthly_target = target_arr / months
        new_arr_needed = monthly_target / (1 - self.annual_churn_rate / 12)
        customers_needed = new_arr_needed / self.avg_acv
        signups_needed = customers_needed / self.free_to_paid_rate

        return int(math.ceil(signups_needed))

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "fy_arr_target": self.fy_arr_target,
            "avg_acv": self.avg_acv,
            "monthly_signups": self.monthly_signups,
            "free_to_paid_rate": self.free_to_paid_rate,
            "paid_customers_per_month": self.paid_customers_per_month,
            "monthly_new_arr": self.monthly_new_arr,
            "monthly_churn_rate": self.monthly_churn_rate,
            "annual_churn_rate": self.annual_churn_rate,
            "expansion_rate": self.expansion_rate,
            "cac": self.cac,
            "ltv": self.ltv,
            "ltv_cac_ratio": self.ltv_cac_ratio,
        }

    def summary(self) -> str:
        """Return formatted summary."""
        lines = [
            "Self-Serve / PLG Stream",
            "=" * 50,
            "",
            "TARGETS",
            "-" * 40,
            f"  FY ARR Target:     ${self.fy_arr_target:,.0f}",
            "",
            "FUNNEL",
            "-" * 40,
            f"  Monthly Signups:   {self.monthly_signups:,}",
            f"  Free→Paid Rate:    {self.free_to_paid_rate:.1%}",
            f"  New Paid/Month:    {self.paid_customers_per_month}",
            f"  Time to Convert:   {self.time_to_convert_days} days",
            "",
            "UNIT ECONOMICS",
            "-" * 40,
            f"  Avg ACV:           ${self.avg_acv:,.0f}",
            f"  Monthly Price:     ${self.monthly_price:,.0f}",
            f"  CAC:               ${self.cac:,.0f}",
            f"  LTV:               ${self.ltv:,.0f}",
            f"  LTV/CAC:           {self.ltv_cac_ratio:.1f}x",
            "",
            "RETENTION",
            "-" * 40,
            f"  Monthly Churn:     {self.monthly_churn_rate:.1%}",
            f"  Annual Churn:      {self.annual_churn_rate:.1%}",
            "",
            "EXPANSION",
            "-" * 40,
            f"  Expansion Rate:    {self.expansion_rate:.0%}",
            f"  Expansion ACV:     ${self.avg_expansion_acv:,.0f}",
            "",
            "COST MODEL",
            "-" * 40,
            f"  Marketing/Month:   ${self.monthly_marketing_spend:,.0f}",
            f"  Product/Month:     ${self.monthly_product_cost:,.0f}",
            f"  Total/Month:       ${self.monthly_total_cost:,.0f}",
        ]
        return "\n".join(lines)


@dataclass
class AttritionModel:
    """
    Attrition modeling for headcount projections.

    Calculates gross hires needed accounting for attrition,
    and projects effective headcount over time.
    """

    # Annual attrition rates by role
    ae_annual: float = 0.15           # 15% AE attrition
    sdr_annual: float = 0.24          # 24% SDR attrition
    se_annual: float = 0.12           # 12% SE attrition
    csm_annual: float = 0.12          # 12% CSM attrition
    manager_annual: float = 0.10      # 10% Manager attrition

    # Backfill assumptions
    backfill_time_months: int = 2     # Months to hire replacement
    backfill_ramp_months: int = 4     # Months for replacement to ramp

    # Cost multipliers
    recruiting_cost_pct: float = 0.15  # 15% of OTE
    training_cost_pct: float = 0.05    # 5% of OTE

    @property
    def ae_monthly(self) -> float:
        """Monthly AE attrition rate."""
        return 1 - (1 - self.ae_annual) ** (1 / 12)

    @property
    def sdr_monthly(self) -> float:
        """Monthly SDR attrition rate."""
        return 1 - (1 - self.sdr_annual) ** (1 / 12)

    @property
    def se_monthly(self) -> float:
        """Monthly SE attrition rate."""
        return 1 - (1 - self.se_annual) ** (1 / 12)

    def calculate_gross_hires(
        self,
        starting_headcount: int,
        target_headcount: int,
        months: int,
        annual_attrition: float,
    ) -> dict:
        """
        Calculate gross hires needed to reach target accounting for attrition.

        Args:
            starting_headcount: Current headcount
            target_headcount: Target headcount at end of period
            months: Period length in months
            annual_attrition: Annual attrition rate for role

        Returns:
            Dict with net growth, attrition replacement, and gross hires
        """
        net_growth = target_headcount - starting_headcount

        # Average headcount over period
        avg_headcount = (starting_headcount + target_headcount) / 2

        # Expected attrition over period
        monthly_attrition = 1 - (1 - annual_attrition) ** (1 / 12)
        expected_attrition = int(math.ceil(avg_headcount * monthly_attrition * months))

        # Gross hires = net growth + attrition replacement
        gross_hires = max(0, net_growth) + expected_attrition

        return {
            "starting_headcount": starting_headcount,
            "target_headcount": target_headcount,
            "net_growth": net_growth,
            "expected_attrition": expected_attrition,
            "gross_hires": gross_hires,
            "months": months,
            "annual_attrition_rate": annual_attrition,
        }

    def project_headcount(
        self,
        starting_headcount: int,
        monthly_hires: list[int],
        annual_attrition: float,
    ) -> list[dict]:
        """
        Project headcount month-by-month with attrition.

        Args:
            starting_headcount: Starting headcount
            monthly_hires: List of hires per month
            annual_attrition: Annual attrition rate

        Returns:
            List of monthly headcount data
        """
        monthly_attrition = 1 - (1 - annual_attrition) ** (1 / 12)

        timeline = []
        current = starting_headcount

        for month, hires in enumerate(monthly_hires, 1):
            # Attrition (at start of month, before hires)
            departed = int(current * monthly_attrition)

            # Net change
            net_change = hires - departed
            ending = current + net_change

            timeline.append({
                "month": month,
                "starting": current,
                "hires": hires,
                "departed": departed,
                "net_change": net_change,
                "ending": ending,
            })

            current = ending

        return timeline

    def calculate_attrition_cost(
        self,
        departed_count: int,
        annual_ote: float,
    ) -> dict:
        """
        Calculate cost of attrition (recruiting + training + lost productivity).

        Args:
            departed_count: Number of departures
            annual_ote: Annual OTE for role

        Returns:
            Dict with cost breakdown
        """
        recruiting = departed_count * annual_ote * self.recruiting_cost_pct
        training = departed_count * annual_ote * self.training_cost_pct
        # Lost productivity = backfill_time + ramp time at 50% productivity
        lost_months = self.backfill_time_months + (self.backfill_ramp_months * 0.5)
        lost_productivity = departed_count * (annual_ote / 12) * lost_months * 0.5

        return {
            "departed_count": departed_count,
            "recruiting_cost": recruiting,
            "training_cost": training,
            "lost_productivity_cost": lost_productivity,
            "total_cost": recruiting + training + lost_productivity,
            "cost_per_departure": (recruiting + training + lost_productivity) / departed_count if departed_count > 0 else 0,
        }

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "annual_rates": {
                "ae": self.ae_annual,
                "sdr": self.sdr_annual,
                "se": self.se_annual,
                "csm": self.csm_annual,
                "manager": self.manager_annual,
            },
            "monthly_rates": {
                "ae": self.ae_monthly,
                "sdr": self.sdr_monthly,
                "se": self.se_monthly,
            },
            "backfill_time_months": self.backfill_time_months,
            "backfill_ramp_months": self.backfill_ramp_months,
        }

    def summary(self) -> str:
        """Return formatted summary."""
        lines = [
            "Attrition Model",
            "=" * 50,
            "",
            "ANNUAL RATES",
            "-" * 40,
            f"  AE:        {self.ae_annual:.0%} annual ({self.ae_monthly:.1%}/month)",
            f"  SDR:       {self.sdr_annual:.0%} annual ({self.sdr_monthly:.1%}/month)",
            f"  SE:        {self.se_annual:.0%} annual ({self.se_monthly:.1%}/month)",
            f"  CSM:       {self.csm_annual:.0%} annual",
            f"  Manager:   {self.manager_annual:.0%} annual",
            "",
            "BACKFILL",
            "-" * 40,
            f"  Time to Hire:   {self.backfill_time_months} months",
            f"  Ramp Time:      {self.backfill_ramp_months} months",
            "",
            "COST MULTIPLIERS",
            "-" * 40,
            f"  Recruiting:     {self.recruiting_cost_pct:.0%} of OTE",
            f"  Training:       {self.training_cost_pct:.0%} of OTE",
        ]
        return "\n".join(lines)


def calculate_segment_capacity(
    aes_enterprise: int,
    aes_commercial: int,
    months: int = 12,
    enterprise_ramp_months: int = 0,
    commercial_ramp_months: int = 0,
) -> dict:
    """
    Calculate combined capacity from both segments.

    Args:
        aes_enterprise: Enterprise AE count
        aes_commercial: Commercial AE count
        months: Period in months
        enterprise_ramp_months: Average months since hire for enterprise AEs
        commercial_ramp_months: Average months since hire for commercial AEs

    Returns:
        Dict with segment breakdown and total capacity
    """
    ent = SegmentProductivity.enterprise()
    comm = SegmentProductivity.commercial()

    # Enterprise capacity
    ent_ramp = ent.get_ramp_factor(enterprise_ramp_months) if enterprise_ramp_months > 0 else 1.0
    ent_capacity = aes_enterprise * ent.effective_annual_capacity * (months / 12) * ent_ramp

    # Commercial capacity
    comm_ramp = comm.get_ramp_factor(commercial_ramp_months) if commercial_ramp_months > 0 else 1.0
    comm_capacity = aes_commercial * comm.effective_annual_capacity * (months / 12) * comm_ramp

    return {
        "enterprise": {
            "aes": aes_enterprise,
            "capacity_per_ae": ent.effective_annual_capacity * (months / 12),
            "total_capacity": ent_capacity,
            "avg_acv": ent.avg_acv,
            "expected_deals": aes_enterprise * ent.deals_per_ae_per_year * (months / 12),
        },
        "commercial": {
            "aes": aes_commercial,
            "capacity_per_ae": comm.effective_annual_capacity * (months / 12),
            "total_capacity": comm_capacity,
            "avg_acv": comm.avg_acv,
            "expected_deals": aes_commercial * comm.deals_per_ae_per_year * (months / 12),
        },
        "total": {
            "aes": aes_enterprise + aes_commercial,
            "capacity": ent_capacity + comm_capacity,
            "blended_acv": (
                (ent.avg_acv * aes_enterprise + comm.avg_acv * aes_commercial) /
                (aes_enterprise + aes_commercial)
            ) if (aes_enterprise + aes_commercial) > 0 else 0,
        },
    }


def calculate_combined_arr_target(
    sales_led_target: float,
    self_serve_target: float = 5_000_000,
    expansion_target: float = 0,
) -> dict:
    """
    Calculate combined ARR target across all streams.

    Args:
        sales_led_target: Sales-led ARR target
        self_serve_target: Self-serve/PLG ARR target
        expansion_target: Expansion ARR target

    Returns:
        Dict with target breakdown
    """
    total = sales_led_target + self_serve_target + expansion_target

    return {
        "sales_led": sales_led_target,
        "self_serve": self_serve_target,
        "expansion": expansion_target,
        "total": total,
        "sales_led_pct": sales_led_target / total if total > 0 else 0,
        "self_serve_pct": self_serve_target / total if total > 0 else 0,
        "expansion_pct": expansion_target / total if total > 0 else 0,
    }

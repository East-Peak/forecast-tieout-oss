"""
GTM Hiring Plan Module - Hiring Timeline and Ramp Tracking.

Models hiring plans with ramp curves to calculate when to hire
in order to have ramped capacity by target dates.

Example usage:
    from gtm_model.hiring import HiringPlan, MonthlyHire, reverse_hiring_timeline

    # When do I need to hire to have 5 ramped AEs by Q3?
    hire_by = reverse_hiring_timeline(
        target_ramped_count=5,
        target_month=date(2027, 5, 1),
    )
    print(f"Hire by: {hire_by}")  # Shows latest hire date for ramp
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from enum import Enum
import math

from dateutil.relativedelta import relativedelta

from .capacity import RampCurve, Segment, DEFAULT_RAMP_CURVES
from .team_structure import DerivedTeam, GTMRole


@dataclass
class MonthlyHire:
    """
    A single hire in a specific month.

    Tracks role, segment, start date, and ramp status.
    """

    role: GTMRole
    hire_month: date  # First day of month hired
    segment: Optional[Segment] = None  # For AEs
    name: Optional[str] = None  # Optional identifier

    def months_since_start(self, as_of: date) -> int:
        """Calculate months since hire started."""
        return (as_of.year - self.hire_month.year) * 12 + (as_of.month - self.hire_month.month)

    def is_ramped(self, as_of: date, ramp_months: int = 4) -> bool:
        """Check if fully ramped as of given date."""
        return self.months_since_start(as_of) >= ramp_months

    def ramp_factor(self, as_of: date, ramp_curve: Optional[RampCurve] = None) -> float:
        """Get ramp factor for a given date."""
        if ramp_curve is None:
            # Use default ramp curve based on segment
            ramp_curve = DEFAULT_RAMP_CURVES.get(
                self.segment or Segment.MID_MARKET,
                RampCurve()
            )

        months = self.months_since_start(as_of)
        return ramp_curve.get_ramp_factor(months)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "role": self.role.value,
            "hire_month": self.hire_month.isoformat(),
            "segment": self.segment.value if self.segment else None,
            "name": self.name,
        }


class HiringPace(Enum):
    """Hiring pace strategy for spreading hires across months."""

    EVEN = "even"             # Spread evenly across period
    FRONT_LOADED = "front"    # Hire more early
    BACK_LOADED = "back"      # Hire more later
    IMMEDIATE = "immediate"   # All at once (start month)


@dataclass
class AttritionRates:
    """Monthly attrition rates by role."""

    ae_monthly: float = 0.012      # 1.2% monthly (~15% annual)
    sdr_monthly: float = 0.02      # 2% monthly (~24% annual)
    se_monthly: float = 0.01       # 1% monthly (~12% annual)
    csm_monthly: float = 0.01      # 1% monthly
    fde_monthly: float = 0.008     # 0.8% monthly
    manager_monthly: float = 0.008  # 0.8% monthly

    def get_rate(self, role: GTMRole) -> float:
        """Get attrition rate for a specific role."""
        role_map = {
            GTMRole.AE_ENTERPRISE: self.ae_monthly,
            GTMRole.AE_MIDMARKET: self.ae_monthly,
            GTMRole.SDR: self.sdr_monthly,
            GTMRole.SE: self.se_monthly,
            GTMRole.CSM: self.csm_monthly,
            GTMRole.FDE: self.fde_monthly,
            GTMRole.MGR_AE_ENTERPRISE: self.manager_monthly,
            GTMRole.MGR_AE_MIDMARKET: self.manager_monthly,
            GTMRole.MGR_SE: self.manager_monthly,
            GTMRole.MGR_SDR: self.manager_monthly,
            GTMRole.MGR_CSM: self.manager_monthly,
        }
        return role_map.get(role, 0.01)


@dataclass
class HiringPlan:
    """
    Full hiring plan by month.

    Tracks planned hires and calculates headcount/capacity over time.
    """

    hires: list[MonthlyHire] = field(default_factory=list)
    attrition: Optional[AttritionRates] = None
    start_month: Optional[date] = None
    end_month: Optional[date] = None

    def __post_init__(self):
        """Initialize defaults."""
        if self.attrition is None:
            self.attrition = AttritionRates()

        # Set date bounds from hires
        if self.hires and not self.start_month:
            self.start_month = min(h.hire_month for h in self.hires)
        if self.hires and not self.end_month:
            self.end_month = max(h.hire_month for h in self.hires) + relativedelta(months=6)

    def add_hire(
        self,
        role: GTMRole,
        hire_month: date,
        segment: Optional[Segment] = None,
        name: Optional[str] = None,
    ):
        """Add a hire to the plan."""
        self.hires.append(MonthlyHire(
            role=role,
            hire_month=hire_month,
            segment=segment,
            name=name,
        ))

    def hires_in_month(self, month: date, role: Optional[GTMRole] = None) -> list[MonthlyHire]:
        """Get all hires starting in a specific month."""
        result = [h for h in self.hires if h.hire_month == month]
        if role:
            result = [h for h in result if h.role == role]
        return result

    def headcount_at(
        self,
        month: date,
        role: Optional[GTMRole] = None,
        starting_headcount: int = 0,
    ) -> int:
        """
        Calculate headcount for role at given month.

        Includes hires up to that month, minus attrition.
        """
        # Filter hires
        relevant_hires = [h for h in self.hires if h.hire_month <= month]
        if role:
            relevant_hires = [h for h in relevant_hires if h.role == role]

        # Simple headcount (ignoring attrition for now)
        return starting_headcount + len(relevant_hires)

    def ramped_headcount_at(
        self,
        month: date,
        role: Optional[GTMRole] = None,
        starting_headcount: int = 0,
        ramp_months: int = 4,
    ) -> int:
        """
        Calculate fully ramped headcount at given month.

        Only counts hires that are past ramp period.
        """
        relevant_hires = [h for h in self.hires if h.hire_month <= month]
        if role:
            relevant_hires = [h for h in relevant_hires if h.role == role]

        ramped = sum(1 for h in relevant_hires if h.is_ramped(month, ramp_months))
        return starting_headcount + ramped

    def blended_ramp_factor(
        self,
        month: date,
        role: Optional[GTMRole] = None,
        starting_headcount: int = 0,
    ) -> float:
        """
        Calculate blended ramp factor for team at given month.

        This is the weighted average ramp factor accounting for all hires.
        """
        relevant_hires = [h for h in self.hires if h.hire_month <= month]
        if role:
            relevant_hires = [h for h in relevant_hires if h.role == role]

        if not relevant_hires and starting_headcount == 0:
            return 0.0

        # Starting headcount is assumed to be fully ramped
        total_ramp = starting_headcount * 1.0
        total_count = starting_headcount

        for hire in relevant_hires:
            total_ramp += hire.ramp_factor(month)
            total_count += 1

        return total_ramp / total_count if total_count > 0 else 0.0

    def get_hires_by_role(self) -> dict[GTMRole, list[MonthlyHire]]:
        """Group hires by role."""
        result: dict[GTMRole, list[MonthlyHire]] = {}
        for hire in self.hires:
            if hire.role not in result:
                result[hire.role] = []
            result[hire.role].append(hire)
        return result

    def get_hires_by_month(self) -> dict[date, list[MonthlyHire]]:
        """Group hires by month."""
        result: dict[date, list[MonthlyHire]] = {}
        for hire in self.hires:
            if hire.hire_month not in result:
                result[hire.hire_month] = []
            result[hire.hire_month].append(hire)
        return result

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "hires": [h.to_dict() for h in self.hires],
            "start_month": self.start_month.isoformat() if self.start_month else None,
            "end_month": self.end_month.isoformat() if self.end_month else None,
            "total_hires": len(self.hires),
            "by_role": {
                role.value: len(hires)
                for role, hires in self.get_hires_by_role().items()
            },
        }

    def summary(self) -> str:
        """Return formatted summary of hiring plan."""
        by_role = self.get_hires_by_role()
        by_month = self.get_hires_by_month()

        lines = [
            "Hiring Plan",
            "=" * 50,
            "",
            f"Period: {self.start_month} to {self.end_month}",
            f"Total Hires: {len(self.hires)}",
            "",
            "BY ROLE",
            "-" * 40,
        ]

        for role, hires in sorted(by_role.items(), key=lambda x: len(x[1]), reverse=True):
            lines.append(f"  {role.value:<25} {len(hires):>4}")

        lines.extend([
            "",
            "BY MONTH",
            "-" * 40,
        ])

        for month in sorted(by_month.keys()):
            hires = by_month[month]
            month_str = month.strftime("%Y-%m")
            role_counts = {}
            for h in hires:
                role_counts[h.role.value] = role_counts.get(h.role.value, 0) + 1
            role_summary = ", ".join(f"{c} {r}" for r, c in role_counts.items())
            lines.append(f"  {month_str}: {role_summary}")

        return "\n".join(lines)


def reverse_hiring_timeline(
    target_ramped_count: int,
    target_month: date,
    ramp_months: int = 4,
    current_ramped: int = 0,
) -> date:
    """
    Calculate when to hire to have X ramped capacity by target date.

    "To have 10 fully ramped AEs by July, when do I need to start hiring?"

    Args:
        target_ramped_count: Target number of fully ramped reps
        target_month: Month when you need them ramped
        ramp_months: Months to full productivity
        current_ramped: How many are already ramped

    Returns:
        Latest month to hire and still be ramped by target
    """
    hires_needed = target_ramped_count - current_ramped
    if hires_needed <= 0:
        return target_month  # Already have enough

    # To be ramped by target_month, must start ramp_months before
    hire_by = target_month - relativedelta(months=ramp_months)

    return hire_by


def reverse_hiring_timeline_detailed(
    target_ramped_count: int,
    target_month: date,
    ramp_curve: Optional[RampCurve] = None,
    current_ramped: int = 0,
    min_ramp_factor: float = 1.0,
) -> dict:
    """
    Detailed hiring timeline showing when to hire for various ramp levels.

    Args:
        target_ramped_count: Target ramped headcount
        target_month: Month when capacity is needed
        ramp_curve: Ramp curve to use
        current_ramped: Current ramped headcount
        min_ramp_factor: Minimum ramp factor to count as "productive"

    Returns:
        Dict with hiring timeline details
    """
    if ramp_curve is None:
        ramp_curve = RampCurve()

    hires_needed = target_ramped_count - current_ramped
    if hires_needed <= 0:
        return {
            "hires_needed": 0,
            "current_ramped": current_ramped,
            "target_ramped": target_ramped_count,
            "message": "Already have sufficient ramped capacity",
        }

    # Calculate hire-by dates for different ramp milestones
    timeline = {
        "hires_needed": hires_needed,
        "current_ramped": current_ramped,
        "target_ramped": target_ramped_count,
        "target_month": target_month.isoformat(),
        "milestones": {},
    }

    # Check each month from 6 months before to target
    for months_before in range(6, -1, -1):
        hire_month = target_month - relativedelta(months=months_before)
        months_ramped = months_before  # How many months they'll have ramped by target
        ramp_factor = ramp_curve.get_ramp_factor(months_ramped)

        timeline["milestones"][hire_month.isoformat()] = {
            "months_ramped_by_target": months_ramped,
            "ramp_factor": ramp_factor,
            "productivity_pct": f"{ramp_factor * 100:.0f}%",
        }

    # Recommend hire-by date for full ramp
    for months_before in range(6, 0, -1):
        hire_month = target_month - relativedelta(months=months_before)
        months_ramped = months_before
        ramp_factor = ramp_curve.get_ramp_factor(months_ramped)

        if ramp_factor >= min_ramp_factor:
            timeline["recommended_hire_by"] = hire_month.isoformat()
            timeline["recommended_lead_time_months"] = months_before
            break

    return timeline


def generate_hiring_plan(
    current_team: DerivedTeam,
    target_team: DerivedTeam,
    start_month: date,
    end_month: date,
    pace: HiringPace = HiringPace.EVEN,
) -> HiringPlan:
    """
    Generate month-by-month hiring plan to get from current to target.

    Args:
        current_team: Current team composition
        target_team: Target team composition
        start_month: When hiring can start
        end_month: When hiring should complete
        pace: How to spread hires across the period

    Returns:
        HiringPlan with monthly hires to close the gap
    """
    plan = HiringPlan(start_month=start_month, end_month=end_month)

    # Calculate gaps for each role
    gaps = {
        GTMRole.AE_ENTERPRISE: target_team.aes_enterprise - current_team.aes_enterprise,
        GTMRole.AE_MIDMARKET: target_team.aes_midmarket - current_team.aes_midmarket,
        GTMRole.SE: target_team.ses - current_team.ses,
        GTMRole.SDR: target_team.sdrs - current_team.sdrs,
        GTMRole.CSM: target_team.csms - current_team.csms,
        GTMRole.FDE: target_team.fdes - current_team.fdes,
        GTMRole.MGR_AE_ENTERPRISE: target_team.ae_managers_enterprise - current_team.ae_managers_enterprise,
        GTMRole.MGR_AE_MIDMARKET: target_team.ae_managers_midmarket - current_team.ae_managers_midmarket,
        GTMRole.MGR_SE: target_team.se_managers - current_team.se_managers,
        GTMRole.MGR_SDR: target_team.sdr_managers - current_team.sdr_managers,
        GTMRole.MGR_CSM: target_team.csm_managers - current_team.csm_managers,
    }

    # Calculate number of months
    months_diff = (end_month.year - start_month.year) * 12 + (end_month.month - start_month.month) + 1
    months_diff = max(1, months_diff)

    # Generate months list
    months = []
    current = start_month
    while current <= end_month:
        months.append(current)
        current = current + relativedelta(months=1)

    # Spread hires across months based on pace
    for role, gap in gaps.items():
        if gap <= 0:
            continue  # No hiring needed for this role

        # Determine segment for AE roles
        segment = None
        if role == GTMRole.AE_ENTERPRISE:
            segment = Segment.ENTERPRISE
        elif role == GTMRole.AE_MIDMARKET:
            segment = Segment.MID_MARKET

        # Distribute hires
        if pace == HiringPace.IMMEDIATE:
            # All hires in first month
            for i in range(gap):
                plan.add_hire(role=role, hire_month=start_month, segment=segment)

        elif pace == HiringPace.EVEN:
            # Spread evenly
            hires_per_month = gap / len(months)
            cumulative = 0.0
            for month in months:
                cumulative += hires_per_month
                while cumulative >= 1.0:
                    plan.add_hire(role=role, hire_month=month, segment=segment)
                    cumulative -= 1.0

        elif pace == HiringPace.FRONT_LOADED:
            # More hires early (60% in first half)
            first_half_hires = int(math.ceil(gap * 0.6))
            second_half_hires = gap - first_half_hires
            mid_point = len(months) // 2

            # First half
            for i, month in enumerate(months[:mid_point]):
                per_month = first_half_hires / max(1, mid_point)
                for _ in range(int(per_month)):
                    if first_half_hires > 0:
                        plan.add_hire(role=role, hire_month=month, segment=segment)
                        first_half_hires -= 1

            # Remaining first half hires
            for _ in range(first_half_hires):
                plan.add_hire(role=role, hire_month=months[mid_point - 1], segment=segment)

            # Second half
            for i, month in enumerate(months[mid_point:]):
                per_month = second_half_hires / max(1, len(months) - mid_point)
                for _ in range(int(per_month)):
                    if second_half_hires > 0:
                        plan.add_hire(role=role, hire_month=month, segment=segment)
                        second_half_hires -= 1

            # Remaining second half hires
            for _ in range(second_half_hires):
                plan.add_hire(role=role, hire_month=months[-1], segment=segment)

        elif pace == HiringPace.BACK_LOADED:
            # More hires later (60% in second half)
            first_half_hires = int(math.floor(gap * 0.4))
            second_half_hires = gap - first_half_hires
            mid_point = len(months) // 2

            # First half
            for i, month in enumerate(months[:mid_point]):
                per_month = first_half_hires / max(1, mid_point)
                for _ in range(int(per_month)):
                    if first_half_hires > 0:
                        plan.add_hire(role=role, hire_month=month, segment=segment)
                        first_half_hires -= 1

            for _ in range(first_half_hires):
                plan.add_hire(role=role, hire_month=months[mid_point - 1], segment=segment)

            # Second half
            for i, month in enumerate(months[mid_point:]):
                per_month = second_half_hires / max(1, len(months) - mid_point)
                for _ in range(int(per_month)):
                    if second_half_hires > 0:
                        plan.add_hire(role=role, hire_month=month, segment=segment)
                        second_half_hires -= 1

            for _ in range(second_half_hires):
                plan.add_hire(role=role, hire_month=months[-1], segment=segment)

    return plan


def project_headcount_timeline(
    current_team: DerivedTeam,
    hiring_plan: HiringPlan,
    months: int = 12,
    start_month: Optional[date] = None,
) -> list[dict]:
    """
    Project headcount month-by-month including ramp status.

    Args:
        current_team: Starting team composition
        hiring_plan: Hiring plan to apply
        months: Number of months to project
        start_month: Starting month (defaults to today)

    Returns:
        List of dicts with monthly headcount and capacity projections
    """
    if start_month is None:
        start_month = date.today().replace(day=1)

    timeline = []
    current = start_month

    for _ in range(months):
        # Get hires by this month
        ae_ent_hires = [h for h in hiring_plan.hires
                        if h.role == GTMRole.AE_ENTERPRISE and h.hire_month <= current]
        ae_mm_hires = [h for h in hiring_plan.hires
                       if h.role == GTMRole.AE_MIDMARKET and h.hire_month <= current]
        se_hires = [h for h in hiring_plan.hires
                    if h.role == GTMRole.SE and h.hire_month <= current]
        sdr_hires = [h for h in hiring_plan.hires
                     if h.role == GTMRole.SDR and h.hire_month <= current]

        # Calculate headcount
        ae_ent_count = current_team.aes_enterprise + len(ae_ent_hires)
        ae_mm_count = current_team.aes_midmarket + len(ae_mm_hires)
        se_count = current_team.ses + len(se_hires)
        sdr_count = current_team.sdrs + len(sdr_hires)

        # Calculate ramped headcount
        ae_ent_ramped = current_team.aes_enterprise + sum(
            1 for h in ae_ent_hires if h.is_ramped(current)
        )
        ae_mm_ramped = current_team.aes_midmarket + sum(
            1 for h in ae_mm_hires if h.is_ramped(current)
        )
        se_ramped = current_team.ses + sum(
            1 for h in se_hires if h.is_ramped(current)
        )
        sdr_ramped = current_team.sdrs + sum(
            1 for h in sdr_hires if h.is_ramped(current)
        )

        timeline.append({
            "month": current.isoformat(),
            "headcount": {
                "ae_enterprise": ae_ent_count,
                "ae_midmarket": ae_mm_count,
                "total_aes": ae_ent_count + ae_mm_count,
                "ses": se_count,
                "sdrs": sdr_count,
            },
            "ramped": {
                "ae_enterprise": ae_ent_ramped,
                "ae_midmarket": ae_mm_ramped,
                "total_aes": ae_ent_ramped + ae_mm_ramped,
                "ses": se_ramped,
                "sdrs": sdr_ramped,
            },
            "new_hires_this_month": len(hiring_plan.hires_in_month(current)),
        })

        current = current + relativedelta(months=1)

    return timeline


def calculate_capacity_with_ramp(
    headcount: int,
    monthly_quota: float,
    attainment_rate: float,
    blended_ramp_factor: float,
) -> float:
    """
    Calculate monthly capacity accounting for ramp.

    Formula: Headcount × Monthly Quota × Attainment % × Blended Ramp %

    Args:
        headcount: Total headcount
        monthly_quota: Monthly quota per rep
        attainment_rate: Expected attainment (0.0 to 1.0+)
        blended_ramp_factor: Blended ramp factor (0.0 to 1.0)

    Returns:
        Effective monthly capacity in dollars
    """
    return headcount * monthly_quota * attainment_rate * blended_ramp_factor

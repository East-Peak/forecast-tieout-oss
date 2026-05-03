"""
Rep capacity model for the GTM model.

Calculates effective capacity based on quotas, ramp schedules,
and expected attainment rates.

Supports three role types:
- SDR: Meeting/SQL generation capacity
- AE: Quota-based bookings capacity
- SE: POC/technical validation bandwidth
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from enum import Enum
import math


class Segment(Enum):
    """Sales segment definitions."""

    ENTERPRISE = "enterprise"
    MID_MARKET = "mid_market"
    SMB = "smb"
    VELOCITY = "velocity"  # PLG/self-serve


class Role(Enum):
    """GTM role types."""

    SDR = "sdr"
    AE = "ae"
    SE = "se"


@dataclass
class RampCurve:
    """
    Ramp curve defining productivity by month after start.

    Values are multipliers on monthly quota (0.0 to 1.0+).
    """

    month_1: float = 0.00  # First month: 0% productivity
    month_2: float = 0.15  # Second month: 15% productivity
    month_3: float = 0.50  # Third month: 50% productivity
    month_4_plus: float = 1.00  # Fourth month+: 100% productivity

    def get_ramp_factor(self, months_since_start: int) -> float:
        """Get the ramp factor for a given number of months since start."""
        if months_since_start < 1:
            return self.month_1
        elif months_since_start == 1:
            return self.month_2
        elif months_since_start == 2:
            return self.month_3
        else:
            return self.month_4_plus


# Default ramp curves by segment
DEFAULT_RAMP_CURVES = {
    Segment.ENTERPRISE: RampCurve(
        month_1=0.00,
        month_2=0.15,
        month_3=0.50,
        month_4_plus=1.00,
    ),
    Segment.MID_MARKET: RampCurve(
        month_1=0.00,
        month_2=0.25,
        month_3=0.60,
        month_4_plus=1.00,
    ),
    Segment.SMB: RampCurve(
        month_1=0.00,
        month_2=0.40,
        month_3=0.75,
        month_4_plus=1.00,
    ),
}

# Default quotas by segment (annual)
DEFAULT_QUOTAS = {
    Segment.ENTERPRISE: 1_800_000,  # $1.8M/year
    Segment.MID_MARKET: 650_000,  # $650K/year
    Segment.SMB: 400_000,  # $400K/year
}


@dataclass
class RepCapacity:
    """
    Individual sales rep capacity model.

    Tracks a rep's quota, start date, and calculates effective capacity
    based on ramp schedule.
    """

    name: str
    segment: Segment
    start_date: date
    annual_quota: float
    attainment_rate: float = 0.80  # Expected attainment (80% default)
    ramp_curve: Optional[RampCurve] = None

    def __post_init__(self):
        """Set default ramp curve if not provided."""
        if self.ramp_curve is None:
            self.ramp_curve = DEFAULT_RAMP_CURVES.get(
                self.segment, RampCurve()
            )

    @property
    def monthly_quota(self) -> float:
        """Calculate monthly quota from annual."""
        return self.annual_quota / 12

    def months_since_start(self, as_of: date) -> int:
        """Calculate months since rep started."""
        return (as_of.year - self.start_date.year) * 12 + (as_of.month - self.start_date.month)

    def is_ramped(self, as_of: date) -> bool:
        """Check if rep is fully ramped as of a given date."""
        return self.months_since_start(as_of) >= 4

    def ramp_factor(self, as_of: date) -> float:
        """Get ramp factor for a given date."""
        months = self.months_since_start(as_of)
        return self.ramp_curve.get_ramp_factor(months)

    def effective_monthly_capacity(self, month: date) -> float:
        """
        Calculate effective monthly capacity for a given month.

        Accounts for ramp and expected attainment.

        Args:
            month: The month to calculate capacity for

        Returns:
            Effective capacity in dollars
        """
        if month < self.start_date:
            return 0.0

        ramp = self.ramp_factor(month)
        return self.monthly_quota * ramp * self.attainment_rate

    def effective_quarterly_capacity(self, quarter_start: date) -> float:
        """
        Calculate effective capacity for a quarter.

        Args:
            quarter_start: First day of the quarter

        Returns:
            Total effective capacity for the quarter
        """
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta

        total = 0.0
        month = quarter_start
        for _ in range(3):
            total += self.effective_monthly_capacity(month)
            month = month + relativedelta(months=1)

        return total

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "segment": self.segment.value,
            "start_date": self.start_date.isoformat(),
            "annual_quota": self.annual_quota,
            "attainment_rate": self.attainment_rate,
        }


@dataclass
class TeamCapacity:
    """
    Aggregate capacity for a sales team.

    Combines individual rep capacities to calculate team-level metrics.
    """

    reps: list[RepCapacity]
    period: str  # e.g., "Q1FY26"
    period_start: date
    period_end: date

    # Calculated fields
    total_capacity: float = field(init=False)
    ramped_capacity: float = field(init=False)
    ramping_capacity: float = field(init=False)
    total_reps: int = field(init=False)
    ramped_reps: int = field(init=False)

    def __post_init__(self):
        """Calculate aggregate metrics."""
        self.total_reps = len(self.reps)
        self.ramped_reps = sum(1 for r in self.reps if r.is_ramped(self.period_start))

        # Calculate capacities
        self.total_capacity = 0.0
        self.ramped_capacity = 0.0
        self.ramping_capacity = 0.0

        for rep in self.reps:
            cap = rep.effective_quarterly_capacity(self.period_start)
            self.total_capacity += cap
            if rep.is_ramped(self.period_start):
                self.ramped_capacity += cap
            else:
                self.ramping_capacity += cap

    @property
    def capacity_by_segment(self) -> dict[Segment, float]:
        """Calculate capacity breakdown by segment."""
        result = {}
        for rep in self.reps:
            cap = rep.effective_quarterly_capacity(self.period_start)
            result[rep.segment] = result.get(rep.segment, 0) + cap
        return result

    def summary(self) -> str:
        """Return formatted summary of team capacity."""
        segment_breakdown = self.capacity_by_segment
        segment_lines = "\n".join(
            f"  {seg.value}: ${cap:,.0f}"
            for seg, cap in sorted(segment_breakdown.items(), key=lambda x: x[1], reverse=True)
        )

        return f"""
Team Capacity: {self.period}
========================
Period: {self.period_start} to {self.period_end}

Headcount:
  Total Reps:   {self.total_reps}
  Fully Ramped: {self.ramped_reps}
  Ramping:      {self.total_reps - self.ramped_reps}

Capacity (effective):
  Total:        ${self.total_capacity:,.0f}
  From Ramped:  ${self.ramped_capacity:,.0f}
  From Ramping: ${self.ramping_capacity:,.0f}

By Segment:
{segment_lines}
"""


def calculate_quarterly_capacity(
    reps: list[RepCapacity],
    quarter: str,
    fiscal_year_start_month: int = 2,  # FY starts in February
) -> TeamCapacity:
    """
    Calculate team capacity for a fiscal quarter.

    Args:
        reps: List of RepCapacity objects
        quarter: Quarter string (e.g., "Q1FY26")
        fiscal_year_start_month: Month when fiscal year starts (1-12)

    Returns:
        TeamCapacity with aggregate metrics
    """
    # Parse quarter string
    q_num = int(quarter[1])
    fy_year = int(quarter[4:6]) + 2000  # year+1 convention assumed

    # Calculate quarter start month
    # Q1 starts in fiscal_year_start_month
    quarter_month = fiscal_year_start_month + (q_num - 1) * 3
    if quarter_month > 12:
        quarter_month -= 12
        year = fy_year
    else:
        year = fy_year - 1  # year+1 convention: Q1 falls in calendar year before fiscal year ends

    quarter_start = date(year, quarter_month, 1)

    # Calculate quarter end
    from dateutil.relativedelta import relativedelta
    quarter_end = quarter_start + relativedelta(months=3, days=-1)

    return TeamCapacity(
        reps=reps,
        period=quarter,
        period_start=quarter_start,
        period_end=quarter_end,
    )


def required_reps_for_target(
    bookings_target: float,
    segment: Segment,
    attainment_rate: float = 0.80,
    months_of_ramp: int = 0,  # Assume fully ramped for planning
) -> int:
    """
    Calculate how many reps are needed to hit a bookings target.

    Args:
        bookings_target: Target bookings in dollars
        segment: Sales segment
        attainment_rate: Expected attainment rate
        months_of_ramp: How many months of ramp to account for (0 = fully ramped)

    Returns:
        Number of reps needed (rounded up)
    """
    import math

    annual_quota = DEFAULT_QUOTAS.get(segment, 1_000_000)
    effective_annual = annual_quota * attainment_rate

    # Adjust for ramp if needed
    if months_of_ramp > 0:
        ramp_curve = DEFAULT_RAMP_CURVES.get(segment, RampCurve())
        ramp_factor = ramp_curve.get_ramp_factor(months_of_ramp)
        effective_annual *= ramp_factor

    return math.ceil(bookings_target / effective_annual)


def create_hiring_plan(
    target_capacity: float,
    current_reps: list[RepCapacity],
    segment: Segment,
    start_date: date,
    months: int = 12,
) -> list[dict]:
    """
    Create a hiring plan to reach target capacity.

    Args:
        target_capacity: Target quarterly capacity
        current_reps: Current team
        segment: Segment for new hires
        start_date: When planning starts
        months: Planning horizon in months

    Returns:
        List of recommended hires with start dates
    """
    from dateutil.relativedelta import relativedelta
    import math

    # Calculate current capacity
    current_team = TeamCapacity(
        reps=current_reps,
        period="Current",
        period_start=start_date,
        period_end=start_date + relativedelta(months=3),
    )

    gap = target_capacity - current_team.total_capacity
    if gap <= 0:
        return []  # No hiring needed

    # Calculate capacity per fully ramped rep
    annual_quota = DEFAULT_QUOTAS.get(segment, 1_000_000)
    quarterly_quota = annual_quota / 4 * 0.80  # 80% attainment

    reps_needed = math.ceil(gap / quarterly_quota)

    # Spread hires across months (backload to allow for ramp)
    hires = []
    for i in range(reps_needed):
        # Stagger by 1-2 months per hire
        hire_date = start_date + relativedelta(months=i * 1)
        if hire_date <= start_date + relativedelta(months=months):
            hires.append({
                "segment": segment.value,
                "start_date": hire_date.isoformat(),
                "annual_quota": annual_quota,
                "months_to_ramp": 4,
            })

    return hires


# =============================================================================
# SDR Capacity Model
# =============================================================================

# SDR-specific ramp curve (faster ramp than AE)
SDR_RAMP = RampCurve(
    month_1=0.00,
    month_2=0.50,
    month_3=0.75,
    month_4_plus=1.00,
)

# Default SDR metrics
DEFAULT_SDR_METRICS = {
    "monthly_meeting_target": 15,  # meetings booked per month
    "meeting_to_sql_rate": 0.50,   # 50% of meetings become SQL
    "fully_loaded_cost": 85_000,   # annual cost
}


@dataclass
class SDRCapacity:
    """
    SDR capacity based on activity and conversion.

    SDRs generate meetings which convert to SQLs and eventually opportunities.
    Capacity is measured in meetings booked and SQLs generated.
    """

    name: str
    start_date: date
    monthly_meeting_target: int = 15  # meetings booked/month
    meeting_to_sql_rate: float = 0.50  # 50% become SQL
    ramp_curve: Optional[RampCurve] = None
    fully_loaded_cost: float = 85_000  # annual

    def __post_init__(self):
        """Set default ramp curve if not provided."""
        if self.ramp_curve is None:
            self.ramp_curve = SDR_RAMP

    def months_since_start(self, as_of: date) -> int:
        """Calculate months since SDR started."""
        return (as_of.year - self.start_date.year) * 12 + (as_of.month - self.start_date.month)

    def is_ramped(self, as_of: date) -> bool:
        """Check if SDR is fully ramped as of a given date."""
        return self.months_since_start(as_of) >= 4

    def ramp_factor(self, as_of: date) -> float:
        """Get ramp factor for a given date."""
        months = self.months_since_start(as_of)
        return self.ramp_curve.get_ramp_factor(months)

    def effective_monthly_meetings(self, month: date) -> int:
        """
        Calculate effective monthly meetings for a given month.

        Accounts for ramp.
        """
        if month < self.start_date:
            return 0

        ramp = self.ramp_factor(month)
        return int(self.monthly_meeting_target * ramp)

    def effective_monthly_sqls(self, month: date) -> int:
        """Calculate effective SQLs generated for a given month."""
        meetings = self.effective_monthly_meetings(month)
        return int(meetings * self.meeting_to_sql_rate)

    def effective_quarterly_meetings(self, quarter_start: date) -> int:
        """Calculate effective meetings for a quarter."""
        from dateutil.relativedelta import relativedelta

        total = 0
        month = quarter_start
        for _ in range(3):
            total += self.effective_monthly_meetings(month)
            month = month + relativedelta(months=1)
        return total

    def effective_quarterly_sqls(self, quarter_start: date) -> int:
        """Calculate effective SQLs for a quarter."""
        meetings = self.effective_quarterly_meetings(quarter_start)
        return int(meetings * self.meeting_to_sql_rate)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "role": "sdr",
            "start_date": self.start_date.isoformat(),
            "monthly_meeting_target": self.monthly_meeting_target,
            "meeting_to_sql_rate": self.meeting_to_sql_rate,
            "fully_loaded_cost": self.fully_loaded_cost,
        }


# =============================================================================
# SE Capacity Model
# =============================================================================

# SE-specific ramp curve (longer ramp due to product learning)
SE_RAMP = RampCurve(
    month_1=0.00,
    month_2=0.25,
    month_3=0.60,
    month_4_plus=1.00,
)

# Default SE metrics
DEFAULT_SE_METRICS = {
    "concurrent_pocs": 3,          # max active POCs at once
    "avg_poc_duration_days": 21,   # average POC length
    "monthly_poc_capacity": 4,     # ~4 POCs/month (some overlap)
    "fully_loaded_cost": 180_000,  # annual cost
}


@dataclass
class SECapacity:
    """
    SE capacity based on POC bandwidth.

    SEs handle technical validation (POCs/trials). Capacity is limited
    by concurrent POC capacity and POC duration.
    """

    name: str
    start_date: date
    concurrent_pocs: int = 3  # max active POCs
    avg_poc_duration_days: int = 21
    ramp_curve: Optional[RampCurve] = None
    fully_loaded_cost: float = 180_000  # annual

    def __post_init__(self):
        """Set default ramp curve if not provided."""
        if self.ramp_curve is None:
            self.ramp_curve = SE_RAMP

    @property
    def monthly_poc_capacity(self) -> int:
        """
        Calculate monthly POC capacity.

        Based on concurrent POCs and duration, with some overlap allowed.
        """
        # ~30 days/month, POCs can overlap
        pocs_per_month = (30 / self.avg_poc_duration_days) * self.concurrent_pocs
        return int(pocs_per_month)

    def months_since_start(self, as_of: date) -> int:
        """Calculate months since SE started."""
        return (as_of.year - self.start_date.year) * 12 + (as_of.month - self.start_date.month)

    def is_ramped(self, as_of: date) -> bool:
        """Check if SE is fully ramped as of a given date."""
        return self.months_since_start(as_of) >= 4

    def ramp_factor(self, as_of: date) -> float:
        """Get ramp factor for a given date."""
        months = self.months_since_start(as_of)
        return self.ramp_curve.get_ramp_factor(months)

    def effective_monthly_pocs(self, month: date) -> int:
        """Calculate effective monthly POC capacity for a given month."""
        if month < self.start_date:
            return 0

        ramp = self.ramp_factor(month)
        return int(self.monthly_poc_capacity * ramp)

    def effective_quarterly_pocs(self, quarter_start: date) -> int:
        """Calculate effective POC capacity for a quarter."""
        from dateutil.relativedelta import relativedelta

        total = 0
        month = quarter_start
        for _ in range(3):
            total += self.effective_monthly_pocs(month)
            month = month + relativedelta(months=1)
        return total

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "role": "se",
            "start_date": self.start_date.isoformat(),
            "concurrent_pocs": self.concurrent_pocs,
            "avg_poc_duration_days": self.avg_poc_duration_days,
            "monthly_poc_capacity": self.monthly_poc_capacity,
            "fully_loaded_cost": self.fully_loaded_cost,
        }


# =============================================================================
# Extended Team Capacity (SDR + AE + SE)
# =============================================================================

@dataclass
class ExtendedTeamCapacity:
    """
    Aggregate capacity for the full GTM team (SDR + AE + SE).

    Combines individual capacities to calculate team-level metrics
    and identify bottlenecks.
    """

    sdr_team: list[SDRCapacity]
    ae_team: list[RepCapacity]
    se_team: list[SECapacity]

    period: str  # e.g., "Q1FY26"
    period_start: date
    period_end: date

    # Calculated fields
    total_sdr_meetings: int = field(init=False)
    total_sdr_sqls: int = field(init=False)
    total_ae_capacity: float = field(init=False)
    total_se_pocs: int = field(init=False)

    # Headcount
    sdr_count: int = field(init=False)
    ae_count: int = field(init=False)
    se_count: int = field(init=False)
    ramped_sdr_count: int = field(init=False)
    ramped_ae_count: int = field(init=False)
    ramped_se_count: int = field(init=False)

    def __post_init__(self):
        """Calculate aggregate metrics."""
        # SDR metrics
        self.sdr_count = len(self.sdr_team)
        self.ramped_sdr_count = sum(
            1 for s in self.sdr_team if s.is_ramped(self.period_start)
        )
        self.total_sdr_meetings = sum(
            s.effective_quarterly_meetings(self.period_start) for s in self.sdr_team
        )
        self.total_sdr_sqls = sum(
            s.effective_quarterly_sqls(self.period_start) for s in self.sdr_team
        )

        # AE metrics
        self.ae_count = len(self.ae_team)
        self.ramped_ae_count = sum(
            1 for a in self.ae_team if a.is_ramped(self.period_start)
        )
        self.total_ae_capacity = sum(
            a.effective_quarterly_capacity(self.period_start) for a in self.ae_team
        )

        # SE metrics
        self.se_count = len(self.se_team)
        self.ramped_se_count = sum(
            1 for s in self.se_team if s.is_ramped(self.period_start)
        )
        self.total_se_pocs = sum(
            s.effective_quarterly_pocs(self.period_start) for s in self.se_team
        )

    @property
    def total_headcount(self) -> int:
        """Total GTM headcount."""
        return self.sdr_count + self.ae_count + self.se_count

    @property
    def total_cost(self) -> float:
        """Total quarterly fully-loaded cost."""
        sdr_cost = sum(s.fully_loaded_cost / 4 for s in self.sdr_team)
        ae_cost = sum(a.annual_quota * 0.25 for a in self.ae_team)  # Approx OTE
        se_cost = sum(s.fully_loaded_cost / 4 for s in self.se_team)
        return sdr_cost + ae_cost + se_cost

    def calculate_bottleneck(
        self,
        required_sqls: int,
        required_bookings: float,
        required_pocs: int,
    ) -> dict:
        """
        Identify which role is the constraint.

        Compares required capacity vs available capacity for each role.

        Args:
            required_sqls: SQLs needed (based on pipeline requirements)
            required_bookings: Bookings needed (target)
            required_pocs: POCs needed (based on S2→S3 volume)

        Returns:
            Dict with bottleneck analysis
        """
        # Calculate utilization for each role
        sdr_utilization = required_sqls / self.total_sdr_sqls if self.total_sdr_sqls > 0 else float("inf")
        ae_utilization = required_bookings / self.total_ae_capacity if self.total_ae_capacity > 0 else float("inf")
        se_utilization = required_pocs / self.total_se_pocs if self.total_se_pocs > 0 else float("inf")

        # Find the bottleneck (highest utilization)
        utilizations = {
            "SDR": sdr_utilization,
            "AE": ae_utilization,
            "SE": se_utilization,
        }

        max_util = max(utilizations.values())
        constrained_role = None
        if max_util > 1.0:
            constrained_role = max(utilizations, key=utilizations.get)

        return {
            "constrained_role": constrained_role,
            "utilization": {
                "SDR": min(sdr_utilization, 2.0),  # Cap for display
                "AE": min(ae_utilization, 2.0),
                "SE": min(se_utilization, 2.0),
            },
            "capacity": {
                "SDR": {"sqls": self.total_sdr_sqls, "required": required_sqls},
                "AE": {"bookings": self.total_ae_capacity, "required": required_bookings},
                "SE": {"pocs": self.total_se_pocs, "required": required_pocs},
            },
            "gap": {
                "SDR": max(0, required_sqls - self.total_sdr_sqls),
                "AE": max(0, required_bookings - self.total_ae_capacity),
                "SE": max(0, required_pocs - self.total_se_pocs),
            },
        }

    def summary(self) -> str:
        """Return formatted summary of extended team capacity."""
        return f"""
Extended Team Capacity: {self.period}
======================================
Period: {self.period_start} to {self.period_end}

SDR Team ({self.sdr_count} total, {self.ramped_sdr_count} ramped):
  Quarterly Meetings: {self.total_sdr_meetings:,}
  Quarterly SQLs:     {self.total_sdr_sqls:,}

AE Team ({self.ae_count} total, {self.ramped_ae_count} ramped):
  Quarterly Capacity: ${self.total_ae_capacity:,.0f}

SE Team ({self.se_count} total, {self.ramped_se_count} ramped):
  Quarterly POCs:     {self.total_se_pocs:,}

Total:
  Headcount:          {self.total_headcount}
  Quarterly Cost:     ${self.total_cost:,.0f}
"""


def calculate_extended_capacity(
    sdr_team: list[SDRCapacity],
    ae_team: list[RepCapacity],
    se_team: list[SECapacity],
    quarter: str,
    fiscal_year_start_month: int = 2,
) -> ExtendedTeamCapacity:
    """
    Calculate extended team capacity for a fiscal quarter.

    Args:
        sdr_team: List of SDRCapacity objects
        ae_team: List of RepCapacity (AE) objects
        se_team: List of SECapacity objects
        quarter: Quarter string (e.g., "Q1FY26")
        fiscal_year_start_month: Month when fiscal year starts (1-12)

    Returns:
        ExtendedTeamCapacity with aggregate metrics
    """
    # Parse quarter string
    q_num = int(quarter[1])
    fy_year = int(quarter[4:6]) + 2000  # year+1 convention assumed

    # Calculate quarter start month
    quarter_month = fiscal_year_start_month + (q_num - 1) * 3
    if quarter_month > 12:
        quarter_month -= 12
        year = fy_year
    else:
        year = fy_year - 1  # year+1 convention: Q1 falls in calendar year before fiscal year ends

    quarter_start = date(year, quarter_month, 1)

    # Calculate quarter end
    from dateutil.relativedelta import relativedelta
    quarter_end = quarter_start + relativedelta(months=3, days=-1)

    return ExtendedTeamCapacity(
        sdr_team=sdr_team,
        ae_team=ae_team,
        se_team=se_team,
        period=quarter,
        period_start=quarter_start,
        period_end=quarter_end,
    )


def required_sdrs_for_sqls(
    sql_target: int,
    monthly_meeting_target: int = 15,
    meeting_to_sql_rate: float = 0.50,
) -> int:
    """
    Calculate how many SDRs are needed to generate target SQLs.

    Args:
        sql_target: Required SQLs per quarter
        monthly_meeting_target: Meetings per SDR per month
        meeting_to_sql_rate: Conversion rate from meeting to SQL

    Returns:
        Number of SDRs needed (rounded up)
    """
    sqls_per_sdr_per_month = monthly_meeting_target * meeting_to_sql_rate
    sqls_per_sdr_per_quarter = sqls_per_sdr_per_month * 3

    return math.ceil(sql_target / sqls_per_sdr_per_quarter)


def required_ses_for_pocs(
    poc_target: int,
    monthly_poc_capacity: int = 4,
) -> int:
    """
    Calculate how many SEs are needed to handle target POCs.

    Args:
        poc_target: Required POCs per quarter
        monthly_poc_capacity: POCs per SE per month

    Returns:
        Number of SEs needed (rounded up)
    """
    pocs_per_se_per_quarter = monthly_poc_capacity * 3
    return math.ceil(poc_target / pocs_per_se_per_quarter)


# =============================================================================
# Monthly Capacity Calculations (NEW for v3)
# =============================================================================


@dataclass
class MonthlyCapacity:
    """
    Capacity snapshot for a single month.

    Used for month-by-month projections instead of quarterly rollups.
    """

    month: date
    month_label: str = ""  # e.g., "Feb 2027"

    # AE Capacity
    ae_headcount: int = 0
    ae_ramped_headcount: int = 0
    ae_blended_ramp: float = 0.0
    ae_capacity: float = 0.0  # In dollars

    # SDR Capacity
    sdr_headcount: int = 0
    sdr_ramped_headcount: int = 0
    sdr_blended_ramp: float = 0.0
    sdr_meetings: int = 0
    sdr_sqls: int = 0

    # SE Capacity
    se_headcount: int = 0
    se_ramped_headcount: int = 0
    se_blended_ramp: float = 0.0
    se_pocs: int = 0

    def __post_init__(self):
        """Set month label if not provided."""
        if not self.month_label:
            self.month_label = self.month.strftime("%b %Y")

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "month": self.month.isoformat(),
            "month_label": self.month_label,
            "ae": {
                "headcount": self.ae_headcount,
                "ramped": self.ae_ramped_headcount,
                "blended_ramp": self.ae_blended_ramp,
                "capacity": self.ae_capacity,
            },
            "sdr": {
                "headcount": self.sdr_headcount,
                "ramped": self.sdr_ramped_headcount,
                "blended_ramp": self.sdr_blended_ramp,
                "meetings": self.sdr_meetings,
                "sqls": self.sdr_sqls,
            },
            "se": {
                "headcount": self.se_headcount,
                "ramped": self.se_ramped_headcount,
                "blended_ramp": self.se_blended_ramp,
                "pocs": self.se_pocs,
            },
        }


def calculate_monthly_capacity(
    sdr_team: list[SDRCapacity],
    ae_team: list[RepCapacity],
    se_team: list[SECapacity],
    month: date,
) -> MonthlyCapacity:
    """
    Calculate capacity for a single month.

    Provides granular view compared to quarterly aggregates.

    Args:
        sdr_team: List of SDR capacity objects
        ae_team: List of AE capacity objects
        se_team: List of SE capacity objects
        month: The month to calculate for

    Returns:
        MonthlyCapacity with all metrics for that month
    """
    # AE metrics
    ae_headcount = len(ae_team)
    ae_ramped = sum(1 for a in ae_team if a.is_ramped(month))
    ae_capacity = sum(a.effective_monthly_capacity(month) for a in ae_team)
    ae_blended_ramp = ae_capacity / sum(a.monthly_quota * a.attainment_rate for a in ae_team) if ae_team else 0.0

    # SDR metrics
    sdr_headcount = len(sdr_team)
    sdr_ramped = sum(1 for s in sdr_team if s.is_ramped(month))
    sdr_meetings = sum(s.effective_monthly_meetings(month) for s in sdr_team)
    sdr_sqls = sum(s.effective_monthly_sqls(month) for s in sdr_team)
    sdr_blended_ramp = sdr_meetings / (sdr_headcount * 15) if sdr_headcount > 0 else 0.0  # 15 = default target

    # SE metrics
    se_headcount = len(se_team)
    se_ramped = sum(1 for s in se_team if s.is_ramped(month))
    se_pocs = sum(s.effective_monthly_pocs(month) for s in se_team)
    se_blended_ramp = se_pocs / (se_headcount * 4) if se_headcount > 0 else 0.0  # 4 = default capacity

    return MonthlyCapacity(
        month=month,
        ae_headcount=ae_headcount,
        ae_ramped_headcount=ae_ramped,
        ae_blended_ramp=ae_blended_ramp,
        ae_capacity=ae_capacity,
        sdr_headcount=sdr_headcount,
        sdr_ramped_headcount=sdr_ramped,
        sdr_blended_ramp=sdr_blended_ramp,
        sdr_meetings=sdr_meetings,
        sdr_sqls=sdr_sqls,
        se_headcount=se_headcount,
        se_ramped_headcount=se_ramped,
        se_blended_ramp=se_blended_ramp,
        se_pocs=se_pocs,
    )


def calculate_monthly_timeline(
    sdr_team: list[SDRCapacity],
    ae_team: list[RepCapacity],
    se_team: list[SECapacity],
    start_month: date,
    months: int = 12,
) -> list[MonthlyCapacity]:
    """
    Calculate capacity for each month in a range.

    Provides full monthly timeline for planning.

    Args:
        sdr_team: List of SDR capacity objects
        ae_team: List of AE capacity objects
        se_team: List of SE capacity objects
        start_month: First month to calculate
        months: Number of months to calculate

    Returns:
        List of MonthlyCapacity objects
    """
    from dateutil.relativedelta import relativedelta

    timeline = []
    current = start_month

    for _ in range(months):
        capacity = calculate_monthly_capacity(
            sdr_team=sdr_team,
            ae_team=ae_team,
            se_team=se_team,
            month=current,
        )
        timeline.append(capacity)
        current = current + relativedelta(months=1)

    return timeline


def calculate_required_aes_for_arr(
    arr_target: float,
    segment: Segment = Segment.MID_MARKET,
    attainment_rate: float = 0.80,
    period_months: int = 12,
) -> int:
    """
    Calculate AE headcount required to generate target ARR.

    Args:
        arr_target: Target ARR to generate
        segment: AE segment (affects quota)
        attainment_rate: Expected quota attainment
        period_months: Time period in months

    Returns:
        Number of AEs needed (rounded up)
    """
    annual_quota = DEFAULT_QUOTAS.get(segment, 650_000)
    quota_for_period = annual_quota * (period_months / 12)
    effective_capacity = quota_for_period * attainment_rate

    return math.ceil(arr_target / effective_capacity)


def calculate_team_arr_capacity(
    ae_team: list[RepCapacity],
    period_months: int = 12,
    start_month: Optional[date] = None,
) -> float:
    """
    Calculate total ARR capacity from AE team over a period.

    Accounts for ramp and segment mix.

    Args:
        ae_team: List of AE capacity objects
        period_months: Period length in months
        start_month: Start of period (defaults to today)

    Returns:
        Total achievable ARR for the period
    """
    from dateutil.relativedelta import relativedelta

    if start_month is None:
        start_month = date.today().replace(day=1)

    total_capacity = 0.0
    current = start_month

    for _ in range(period_months):
        monthly_capacity = sum(a.effective_monthly_capacity(current) for a in ae_team)
        total_capacity += monthly_capacity
        current = current + relativedelta(months=1)

    return total_capacity


def format_monthly_timeline(timeline: list[MonthlyCapacity]) -> str:
    """
    Format monthly timeline as a summary string.

    Args:
        timeline: List of MonthlyCapacity objects

    Returns:
        Formatted string with monthly capacity table
    """
    lines = [
        "Monthly Capacity Timeline",
        "=" * 80,
        "",
        f"{'Month':<10} {'AE HC':>6} {'Ramped':>6} {'Capacity':>12} {'SDRs':>5} {'SQLs':>5} {'SEs':>4} {'POCs':>4}",
        "-" * 80,
    ]

    for mc in timeline:
        lines.append(
            f"{mc.month_label:<10} {mc.ae_headcount:>6} {mc.ae_ramped_headcount:>6} "
            f"${mc.ae_capacity:>10,.0f} {mc.sdr_headcount:>5} {mc.sdr_sqls:>5} "
            f"{mc.se_headcount:>4} {mc.se_pocs:>4}"
        )

    # Summary row
    if timeline:
        lines.append("-" * 80)
        total_capacity = sum(mc.ae_capacity for mc in timeline)
        avg_aes = sum(mc.ae_headcount for mc in timeline) / len(timeline)
        avg_ramped = sum(mc.ae_ramped_headcount for mc in timeline) / len(timeline)
        total_sqls = sum(mc.sdr_sqls for mc in timeline)
        total_pocs = sum(mc.se_pocs for mc in timeline)

        lines.append(
            f"{'TOTAL':<10} {avg_aes:>6.1f} {avg_ramped:>6.1f} "
            f"${total_capacity:>10,.0f} {'':>5} {total_sqls:>5} "
            f"{'':>4} {total_pocs:>4}"
        )

    return "\n".join(lines)

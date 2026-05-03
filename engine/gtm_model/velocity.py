"""
Sales velocity model for the GTM model.

Measures actual velocity from Salesforce data:
- Sales cycle (CreatedDate → CloseDate)
- Stage velocity (time in each stage)
- Lead velocity (MQL → SQL where data exists)

Note: lead velocity data is often sparse — fall back to assumptions when
sample coverage is low.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional
from statistics import mean, median


@dataclass
class SalesCycleVelocity:
    """
    Sales cycle velocity from won deals.

    Calculated from Opportunity.CreatedDate to Opportunity.CloseDate
    for closed-won deals in the measurement period.
    """

    period_start: date
    period_end: date
    sample_size: int

    # Overall metrics
    avg_days: float
    median_days: float
    min_days: int
    max_days: int

    # By source category
    by_source: dict[str, dict] = field(default_factory=dict)
    # {"SDR Sourced": {"avg_days": 90, "median_days": 85, "sample_size": 10}, ...}

    # By segment (if available)
    by_segment: dict[str, dict] = field(default_factory=dict)
    # {"Enterprise": {"avg_days": 120, ...}, "Mid-Market": {"avg_days": 75, ...}}

    def summary(self) -> str:
        """Return formatted summary of sales cycle velocity."""
        lines = [
            "Sales Cycle Velocity",
            "=" * 50,
            f"Period: {self.period_start} to {self.period_end}",
            f"Sample Size: {self.sample_size} closed-won deals",
            "",
            f"Average:  {self.avg_days:.0f} days",
            f"Median:   {self.median_days:.0f} days",
            f"Range:    {self.min_days} - {self.max_days} days",
        ]

        if self.by_source:
            lines.append("")
            lines.append("By Source:")
            for source, data in sorted(
                self.by_source.items(),
                key=lambda x: x[1].get("sample_size", 0),
                reverse=True,
            ):
                avg = data.get("avg_days", 0)
                n = data.get("sample_size", 0)
                lines.append(f"  {source:<20} {avg:>5.0f} days (n={n})")

        if self.by_segment:
            lines.append("")
            lines.append("By Segment:")
            for segment, data in self.by_segment.items():
                avg = data.get("avg_days", 0)
                n = data.get("sample_size", 0)
                lines.append(f"  {segment:<20} {avg:>5.0f} days (n={n})")

        return "\n".join(lines)


@dataclass
class StageVelocity:
    """
    Stage-by-stage velocity from opportunity history.

    Measures time spent in each stage (S0→S1, S1→S2, etc.)
    Falls back to assumptions if history data is unavailable.
    """

    period_start: date
    period_end: date
    source: str  # "salesforce_history" or "assumptions"

    # Time in each stage (days)
    stage_days: dict[str, float] = field(default_factory=dict)
    # {"S0": 14, "S1": 21, "S2": 28, ...}

    # Sample sizes per stage (if from SF data)
    sample_sizes: dict[str, int] = field(default_factory=dict)

    # Cumulative days to each stage
    cumulative_days: dict[str, float] = field(default_factory=dict)
    # {"S0": 14, "S1": 35, "S2": 63, ...}

    def __post_init__(self):
        """Calculate cumulative days."""
        if self.stage_days and not self.cumulative_days:
            cumulative = 0
            for stage in ["S0", "S1", "S2", "S3", "S4", "S5"]:
                if stage in self.stage_days:
                    cumulative += self.stage_days[stage]
                    self.cumulative_days[stage] = cumulative

    def summary(self) -> str:
        """Return formatted summary of stage velocity."""
        lines = [
            "Stage Velocity",
            "=" * 50,
            f"Source: {self.source}",
            "",
            f"{'Stage':<10} {'Days':>8} {'Cumulative':>12} {'Sample':>10}",
            "-" * 50,
        ]

        for stage in ["S0", "S1", "S2", "S3", "S4", "S5"]:
            days = self.stage_days.get(stage, 0)
            cumul = self.cumulative_days.get(stage, 0)
            sample = self.sample_sizes.get(stage, 0)
            sample_str = f"n={sample}" if sample > 0 else "(assumed)"
            lines.append(f"{stage:<10} {days:>8.0f} {cumul:>12.0f} {sample_str:>10}")

        return "\n".join(lines)


@dataclass
class LeadVelocity:
    """
    Lead stage velocity (MQL → SQL).

    Note: lead-stamp coverage is often low in source CRMs. Fall back to
    assumptions when sample coverage is insufficient.
    """

    period_start: date
    period_end: date

    # MQL velocity
    mql_velocity_days: Optional[float] = None  # Raw Lead → MQL
    mql_sample_size: int = 0
    mql_coverage_pct: float = 0.0

    # SQL velocity
    sql_velocity_days: Optional[float] = None  # MQL → SQL
    sql_sample_size: int = 0
    sql_coverage_pct: float = 0.0

    # Data quality flags
    has_mql_data: bool = False
    has_sql_data: bool = False

    def summary(self) -> str:
        """Return formatted summary of lead velocity."""
        lines = [
            "Lead Velocity",
            "=" * 50,
            f"Period: {self.period_start} to {self.period_end}",
            "",
        ]

        if self.has_mql_data:
            lines.append(f"MQL Velocity:     {self.mql_velocity_days:.1f} days")
            lines.append(f"  Sample size:    {self.mql_sample_size}")
            lines.append(f"  Coverage:       {self.mql_coverage_pct:.1f}%")
        else:
            lines.append("MQL Velocity:     (insufficient data)")

        lines.append("")

        if self.has_sql_data:
            lines.append(f"SQL Velocity:     {self.sql_velocity_days:.1f} days")
            lines.append(f"  Sample size:    {self.sql_sample_size}")
            lines.append(f"  Coverage:       {self.sql_coverage_pct:.1f}%")
        else:
            lines.append("SQL Velocity:     (insufficient data)")

        return "\n".join(lines)


@dataclass
class VelocityComparison:
    """
    Comparison of actual vs assumed velocity.

    Useful for identifying where actual velocity differs from model assumptions.
    """

    sales_cycle: SalesCycleVelocity
    stage_velocity: StageVelocity
    lead_velocity: LeadVelocity

    # Assumed values (from config)
    assumed_sales_cycle_days: float = 112
    assumed_stage_days: dict[str, float] = field(default_factory=dict)

    # Variance
    sales_cycle_variance_days: float = field(init=False)
    sales_cycle_variance_pct: float = field(init=False)

    def __post_init__(self):
        """Calculate variances."""
        actual = self.sales_cycle.avg_days
        assumed = self.assumed_sales_cycle_days
        self.sales_cycle_variance_days = actual - assumed
        self.sales_cycle_variance_pct = (
            (actual / assumed - 1) * 100 if assumed > 0 else 0.0
        )

    def summary(self) -> str:
        """Return formatted summary comparing actual vs assumed velocity."""
        lines = [
            "Velocity: Actual vs Assumed",
            "=" * 60,
            "",
            "Sales Cycle:",
            f"  Actual:    {self.sales_cycle.avg_days:.0f} days (n={self.sales_cycle.sample_size})",
            f"  Assumed:   {self.assumed_sales_cycle_days:.0f} days",
        ]

        variance_str = f"+{self.sales_cycle_variance_days:.0f}" if self.sales_cycle_variance_days > 0 else f"{self.sales_cycle_variance_days:.0f}"
        lines.append(f"  Variance:  {variance_str} days ({self.sales_cycle_variance_pct:+.1f}%)")

        if self.assumed_stage_days and self.stage_velocity.stage_days:
            lines.append("")
            lines.append("Stage Velocity:")
            lines.append(f"{'Stage':<10} {'Actual':>10} {'Assumed':>10} {'Variance':>12}")
            lines.append("-" * 45)

            for stage in ["S0", "S1", "S2", "S3", "S4", "S5"]:
                actual_days = self.stage_velocity.stage_days.get(stage, 0)
                assumed_days = self.assumed_stage_days.get(stage, 0)
                variance = actual_days - assumed_days
                var_str = f"+{variance:.0f}" if variance > 0 else f"{variance:.0f}"
                lines.append(f"{stage:<10} {actual_days:>10.0f} {assumed_days:>10.0f} {var_str:>12}")

        return "\n".join(lines)


def calculate_sales_cycle_velocity(
    won_deals: list[dict],
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> SalesCycleVelocity:
    """
    Calculate sales cycle velocity from won deal data.

    Args:
        won_deals: List of closed-won opportunity records with CreatedDate, CloseDate,
                   and optionally source_category and segment info
        period_start: Start of measurement period
        period_end: End of measurement period

    Returns:
        SalesCycleVelocity with calculated metrics
    """
    if not period_start:
        period_start = date.today() - timedelta(days=365)
    if not period_end:
        period_end = date.today()

    if not won_deals:
        return SalesCycleVelocity(
            period_start=period_start,
            period_end=period_end,
            sample_size=0,
            avg_days=0,
            median_days=0,
            min_days=0,
            max_days=0,
        )

    # Calculate days for each deal
    cycle_days = []
    by_source: dict[str, list[int]] = {}
    by_segment: dict[str, list[int]] = {}

    for deal in won_deals:
        created_str = deal.get("CreatedDate", "")
        closed_str = deal.get("CloseDate", "")

        if not created_str or not closed_str:
            continue

        # Parse dates (handle both date and datetime formats)
        try:
            if "T" in str(created_str):
                created = date.fromisoformat(str(created_str)[:10])
            else:
                created = date.fromisoformat(str(created_str))

            if "T" in str(closed_str):
                closed = date.fromisoformat(str(closed_str)[:10])
            else:
                closed = date.fromisoformat(str(closed_str))
        except (ValueError, TypeError):
            continue

        days = (closed - created).days
        if days < 0:
            continue  # Invalid data

        cycle_days.append(days)

        # Group by source
        source = deal.get("source_category", "Unknown") or "Unknown"
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(days)

        # Group by segment (if available)
        segment = deal.get("segment") or deal.get("Segment__c")
        if segment:
            if segment not in by_segment:
                by_segment[segment] = []
            by_segment[segment].append(days)

    if not cycle_days:
        return SalesCycleVelocity(
            period_start=period_start,
            period_end=period_end,
            sample_size=0,
            avg_days=0,
            median_days=0,
            min_days=0,
            max_days=0,
        )

    # Calculate source breakdowns
    source_stats = {}
    for source, days_list in by_source.items():
        if days_list:
            source_stats[source] = {
                "avg_days": mean(days_list),
                "median_days": median(days_list),
                "sample_size": len(days_list),
            }

    # Calculate segment breakdowns
    segment_stats = {}
    for segment, days_list in by_segment.items():
        if days_list:
            segment_stats[segment] = {
                "avg_days": mean(days_list),
                "median_days": median(days_list),
                "sample_size": len(days_list),
            }

    return SalesCycleVelocity(
        period_start=period_start,
        period_end=period_end,
        sample_size=len(cycle_days),
        avg_days=mean(cycle_days),
        median_days=median(cycle_days),
        min_days=min(cycle_days),
        max_days=max(cycle_days),
        by_source=source_stats,
        by_segment=segment_stats,
    )


def calculate_stage_velocity_from_history(
    stage_history: list[dict],
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> StageVelocity:
    """
    Calculate stage velocity from OpportunityHistory or stage date fields.

    Args:
        stage_history: List of stage transition records with OppId, FromStage, ToStage, TransitionDate
        period_start: Start of measurement period
        period_end: End of measurement period

    Returns:
        StageVelocity with calculated time-in-stage
    """
    if not period_start:
        period_start = date.today() - timedelta(days=365)
    if not period_end:
        period_end = date.today()

    if not stage_history:
        # Return empty with assumptions fallback
        return get_assumed_stage_velocity(period_start, period_end)

    # Group transitions by opportunity
    opp_transitions: dict[str, list[dict]] = {}
    for record in stage_history:
        opp_id = record.get("OpportunityId") or record.get("opp_id")
        if opp_id:
            if opp_id not in opp_transitions:
                opp_transitions[opp_id] = []
            opp_transitions[opp_id].append(record)

    # Calculate time in each stage
    stage_durations: dict[str, list[int]] = {
        "S0": [], "S1": [], "S2": [], "S3": [], "S4": [], "S5": []
    }

    for opp_id, transitions in opp_transitions.items():
        # Sort by date
        sorted_trans = sorted(transitions, key=lambda x: x.get("TransitionDate", ""))

        for i, trans in enumerate(sorted_trans[:-1]):
            from_stage = _normalize_stage(trans.get("FromStage") or trans.get("from_stage"))
            next_trans = sorted_trans[i + 1]

            try:
                from_date = date.fromisoformat(str(trans.get("TransitionDate", ""))[:10])
                to_date = date.fromisoformat(str(next_trans.get("TransitionDate", ""))[:10])
                days = (to_date - from_date).days

                if from_stage in stage_durations and days >= 0:
                    stage_durations[from_stage].append(days)
            except (ValueError, TypeError):
                continue

    # Calculate averages
    stage_days = {}
    sample_sizes = {}
    for stage, durations in stage_durations.items():
        if durations:
            stage_days[stage] = mean(durations)
            sample_sizes[stage] = len(durations)
        else:
            stage_days[stage] = 0
            sample_sizes[stage] = 0

    return StageVelocity(
        period_start=period_start,
        period_end=period_end,
        source="salesforce_history",
        stage_days=stage_days,
        sample_sizes=sample_sizes,
    )


def get_assumed_stage_velocity(
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> StageVelocity:
    """
    Get stage velocity from assumptions (fallback when history unavailable).

    Returns:
        StageVelocity populated from config/assumptions.yaml defaults
    """
    if not period_start:
        period_start = date.today() - timedelta(days=365)
    if not period_end:
        period_end = date.today()

    # Default assumed values from assumptions.yaml
    stage_days = {
        "S0": 14,
        "S1": 21,
        "S2": 28,
        "S3": 21,
        "S4": 14,
        "S5": 14,
    }

    return StageVelocity(
        period_start=period_start,
        period_end=period_end,
        source="assumptions",
        stage_days=stage_days,
        sample_sizes={},
    )


def calculate_lead_velocity(
    leads: list[dict],
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> LeadVelocity:
    """
    Calculate lead velocity from mql_date and sql_date stamps.

    Note: lead-stamp coverage is often low in source CRMs; the function
    reports coverage % so callers can decide whether to trust the result.

    Args:
        leads: List of lead records with CreatedDate, mql_date, sql_date
        period_start: Start of measurement period
        period_end: End of measurement period

    Returns:
        LeadVelocity with calculated metrics and coverage stats
    """
    if not period_start:
        period_start = date.today() - timedelta(days=365)
    if not period_end:
        period_end = date.today()

    total_leads = len(leads)
    if total_leads == 0:
        return LeadVelocity(
            period_start=period_start,
            period_end=period_end,
        )

    # Calculate MQL velocity (CreatedDate → mql_date)
    mql_days = []
    for lead in leads:
        created = lead.get("CreatedDate")
        mql_date = lead.get("mql_date")

        if not created or not mql_date:
            continue

        try:
            created_dt = date.fromisoformat(str(created)[:10])
            mql_dt = date.fromisoformat(str(mql_date)[:10])
            days = (mql_dt - created_dt).days
            if days >= 0:
                mql_days.append(days)
        except (ValueError, TypeError):
            continue

    # Calculate SQL velocity (mql_date → sql_date)
    sql_days = []
    for lead in leads:
        mql_date = lead.get("mql_date")
        sql_date = lead.get("sql_date")

        if not mql_date or not sql_date:
            continue

        try:
            mql_dt = date.fromisoformat(str(mql_date)[:10])
            sql_dt = date.fromisoformat(str(sql_date)[:10])
            days = (sql_dt - mql_dt).days
            if days >= 0:
                sql_days.append(days)
        except (ValueError, TypeError):
            continue

    return LeadVelocity(
        period_start=period_start,
        period_end=period_end,
        mql_velocity_days=mean(mql_days) if mql_days else None,
        mql_sample_size=len(mql_days),
        mql_coverage_pct=(len(mql_days) / total_leads * 100) if total_leads > 0 else 0,
        sql_velocity_days=mean(sql_days) if sql_days else None,
        sql_sample_size=len(sql_days),
        sql_coverage_pct=(len(sql_days) / total_leads * 100) if total_leads > 0 else 0,
        has_mql_data=len(mql_days) >= 10,  # Minimum threshold for reliability
        has_sql_data=len(sql_days) >= 10,
    )


def compare_velocity(
    sales_cycle: SalesCycleVelocity,
    stage_velocity: StageVelocity,
    lead_velocity: LeadVelocity,
    assumed_sales_cycle_days: float = 112,
    assumed_stage_days: Optional[dict[str, float]] = None,
) -> VelocityComparison:
    """
    Compare actual velocity against assumed values.

    Args:
        sales_cycle: Calculated sales cycle velocity
        stage_velocity: Calculated stage velocity
        lead_velocity: Calculated lead velocity
        assumed_sales_cycle_days: Assumed total sales cycle (from config)
        assumed_stage_days: Assumed days per stage (from config)

    Returns:
        VelocityComparison with variance analysis
    """
    if assumed_stage_days is None:
        assumed_stage_days = {
            "S0": 14,
            "S1": 21,
            "S2": 28,
            "S3": 21,
            "S4": 14,
            "S5": 14,
        }

    return VelocityComparison(
        sales_cycle=sales_cycle,
        stage_velocity=stage_velocity,
        lead_velocity=lead_velocity,
        assumed_sales_cycle_days=assumed_sales_cycle_days,
        assumed_stage_days=assumed_stage_days,
    )


def _normalize_stage(stage_name: Optional[str]) -> str:
    """Normalize SF stage name to model stage (S0-S5)."""
    if not stage_name:
        return "Unknown"

    stage_map = {
        "0 - Interested": "S0",
        "1 - Discovery": "S1",
        "2 - Technical Fit": "S2",
        "3 - Tech Validation": "S2",  # Maps to S2 in model
        "4 - Business Case Alignment": "S3",
        "5 - Vendor of Choice": "S5",
    }

    return stage_map.get(stage_name, stage_name if stage_name.startswith("S") else "Unknown")

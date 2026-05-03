"""
Pipeline Coverage Model for GTM model.

Provides segment-specific coverage multiples, pipeline aging analysis,
source mix modeling, and coverage gap calculations.

Key concepts:
- Coverage Multiple: Pipeline needed per dollar of target (e.g., 4x = $4M pipeline for $1M target)
- Segment-Specific: Enterprise needs 4x, Mid-Market needs 5x, Expansion needs 2x
- Pipeline Aging: Older pipeline closes at lower rates
- Pipeline Quality: Scored based on stage distribution and aging
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional


class PipelineSegment(str, Enum):
    """Pipeline segment for coverage calculations."""
    ENTERPRISE = "enterprise"
    MID_MARKET = "mid_market"
    SMB = "smb"
    EXPANSION = "expansion"
    RENEWAL = "renewal"


@dataclass
class CoverageMultiples:
    """
    Segment-specific pipeline coverage multiples.

    Default values:
    - Enterprise: 4x (higher ACV, longer sales cycle)
    - Mid-Market: 5x (more competitive, faster churns)
    - SMB: 3x (faster cycles, lower complexity)
    - Expansion: 2x (existing relationships, higher win rates)
    - Renewal: 1.2x (high conversion, just need coverage for churn risk)
    """
    enterprise: float = 4.0
    mid_market: float = 5.0
    smb: float = 3.0
    expansion: float = 2.0
    renewal: float = 1.2

    def get_multiple(self, segment: PipelineSegment) -> float:
        """Get coverage multiple for a segment."""
        return getattr(self, segment.value, 4.0)


@dataclass
class PipelineSourceMix:
    """
    Pipeline source mix - where pipeline comes from.

    Default values:
    - AE Self-Sourced: 60% (enterprise-heavy orgs)
    - SDR Sourced: 20%
    - Marketing: 20%

    These percentages affect capacity planning and cost modeling.
    """
    ae_sourced: float = 0.60
    sdr_sourced: float = 0.20
    marketing_sourced: float = 0.15
    partner_sourced: float = 0.05

    def __post_init__(self):
        total = self.ae_sourced + self.sdr_sourced + self.marketing_sourced + self.partner_sourced
        if not 0.99 <= total <= 1.01:
            raise ValueError(f"Source mix must sum to 1.0, got {total}")

    @property
    def inbound_pct(self) -> float:
        """Percentage from inbound channels (marketing + partner)."""
        return self.marketing_sourced + self.partner_sourced

    @property
    def outbound_pct(self) -> float:
        """Percentage from outbound channels (AE + SDR)."""
        return self.ae_sourced + self.sdr_sourced


@dataclass
class PipelineAging:
    """
    Pipeline aging impact on close rates.

    Older pipeline converts at lower rates. Close rate decays as pipeline ages.
    Based on analysis of historical deal data.
    """
    # Close rate multiplier by age bracket (fraction of base close rate)
    age_0_30_days: float = 1.0      # Fresh pipeline, full close rate
    age_31_60_days: float = 0.85    # 15% reduction
    age_61_90_days: float = 0.70    # 30% reduction
    age_91_180_days: float = 0.50   # 50% reduction
    age_181_plus_days: float = 0.25  # 75% reduction

    def get_age_multiplier(self, days_old: int) -> float:
        """Get close rate multiplier based on pipeline age."""
        if days_old <= 30:
            return self.age_0_30_days
        elif days_old <= 60:
            return self.age_31_60_days
        elif days_old <= 90:
            return self.age_61_90_days
        elif days_old <= 180:
            return self.age_91_180_days
        else:
            return self.age_181_plus_days

    def effective_close_rate(self, base_close_rate: float, days_old: int) -> float:
        """Calculate effective close rate adjusted for aging."""
        return base_close_rate * self.get_age_multiplier(days_old)


@dataclass
class PipelineBucket:
    """A bucket of pipeline for coverage analysis."""
    segment: PipelineSegment
    amount: float
    stage: str  # S0, S1, S2, S3, S4, S5
    days_old: int = 0
    source: str = "unknown"

    @property
    def stage_number(self) -> int:
        """Extract stage number for sorting."""
        if self.stage.upper().startswith("S"):
            try:
                return int(self.stage[1])
            except ValueError:
                return 0
        return 0


@dataclass
class SegmentCoverage:
    """Coverage analysis for a single segment."""
    segment: PipelineSegment
    target: float
    pipeline: float
    coverage_multiple: float
    required_pipeline: float
    current_coverage: float  # As a multiple (e.g., 3.2x)
    coverage_gap: float
    is_healthy: bool

    # Age-adjusted figures
    age_adjusted_pipeline: float = 0
    age_adjusted_coverage: float = 0

    # Stage breakdown
    by_stage: dict = field(default_factory=dict)

    @property
    def coverage_pct(self) -> float:
        """Coverage as percentage of required."""
        if self.required_pipeline == 0:
            return 100.0
        return (self.pipeline / self.required_pipeline) * 100


@dataclass
class CoverageReport:
    """
    Complete pipeline coverage report.

    Provides segment-level and overall coverage analysis with
    recommendations for pipeline generation.
    """
    as_of_date: date
    total_target: float
    total_pipeline: float
    weighted_required_pipeline: float
    overall_coverage: float

    # Segment breakdowns
    segments: dict[PipelineSegment, SegmentCoverage] = field(default_factory=dict)

    # Source mix analysis
    pipeline_by_source: dict[str, float] = field(default_factory=dict)

    # Pipeline health
    healthy_segments: int = 0
    at_risk_segments: int = 0

    # Age analysis
    avg_pipeline_age_days: float = 0
    age_adjusted_coverage: float = 0

    # Recommendations
    pipeline_gap: float = 0
    recommended_weekly_create: float = 0
    weeks_to_close: int = 13  # Typical quarter

    def summary(self) -> str:
        """Generate formatted coverage summary."""
        lines = [
            "Pipeline Coverage Report",
            "=" * 50,
            f"As of: {self.as_of_date}",
            f"",
            f"Overall:",
            f"  Target:           ${self.total_target:,.0f}",
            f"  Pipeline:         ${self.total_pipeline:,.0f}",
            f"  Required:         ${self.weighted_required_pipeline:,.0f}",
            f"  Coverage:         {self.overall_coverage:.1f}x",
            f"  Gap:              ${self.pipeline_gap:,.0f}",
            f"",
            f"Segment Coverage:",
        ]

        for segment, cov in self.segments.items():
            status = "✓" if cov.is_healthy else "✗"
            lines.append(
                f"  {segment.value.replace('_', ' ').title():12} | "
                f"${cov.target:>10,.0f} target | "
                f"${cov.pipeline:>10,.0f} pipe | "
                f"{cov.current_coverage:.1f}x ({cov.coverage_multiple}x needed) {status}"
            )

        if self.pipeline_gap > 0:
            lines.extend([
                f"",
                f"Recommendations:",
                f"  Weekly Pipeline Create: ${self.recommended_weekly_create:,.0f}",
                f"  ({self.weeks_to_close} weeks to close)",
            ])

        return "\n".join(lines)


def calculate_segment_coverage(
    target: float,
    pipeline: float,
    segment: PipelineSegment,
    multiples: Optional[CoverageMultiples] = None,
    buckets: Optional[list[PipelineBucket]] = None,
    aging: Optional[PipelineAging] = None,
    base_close_rate: float = 0.20,
) -> SegmentCoverage:
    """
    Calculate coverage for a single segment.

    Args:
        target: Bookings target for the segment
        pipeline: Total pipeline value for the segment
        segment: The segment type
        multiples: Coverage multiple requirements
        buckets: Optional list of pipeline buckets for detailed analysis
        aging: Pipeline aging model
        base_close_rate: Base S2-to-Won close rate

    Returns:
        SegmentCoverage with detailed analysis
    """
    if multiples is None:
        multiples = CoverageMultiples()
    if aging is None:
        aging = PipelineAging()

    coverage_multiple = multiples.get_multiple(segment)
    required_pipeline = target * coverage_multiple
    current_coverage = pipeline / target if target > 0 else 0
    coverage_gap = max(0, required_pipeline - pipeline)
    is_healthy = current_coverage >= coverage_multiple

    # Calculate age-adjusted pipeline if buckets provided
    age_adjusted_pipeline = pipeline
    by_stage = {}

    if buckets:
        age_adjusted_pipeline = 0
        for bucket in buckets:
            if bucket.segment == segment:
                # Apply aging discount
                effective_value = bucket.amount * aging.get_age_multiplier(bucket.days_old)
                age_adjusted_pipeline += effective_value

                # Aggregate by stage
                stage = bucket.stage
                by_stage[stage] = by_stage.get(stage, 0) + bucket.amount

    age_adjusted_coverage = age_adjusted_pipeline / target if target > 0 else 0

    return SegmentCoverage(
        segment=segment,
        target=target,
        pipeline=pipeline,
        coverage_multiple=coverage_multiple,
        required_pipeline=required_pipeline,
        current_coverage=current_coverage,
        coverage_gap=coverage_gap,
        is_healthy=is_healthy,
        age_adjusted_pipeline=age_adjusted_pipeline,
        age_adjusted_coverage=age_adjusted_coverage,
        by_stage=by_stage,
    )


def calculate_coverage_report(
    targets: dict[PipelineSegment, float],
    pipeline: dict[PipelineSegment, float],
    as_of_date: Optional[date] = None,
    multiples: Optional[CoverageMultiples] = None,
    buckets: Optional[list[PipelineBucket]] = None,
    aging: Optional[PipelineAging] = None,
    weeks_to_close: int = 13,
) -> CoverageReport:
    """
    Calculate comprehensive coverage report across all segments.

    Args:
        targets: Bookings targets by segment
        pipeline: Pipeline values by segment
        as_of_date: Report date (defaults to today)
        multiples: Coverage multiples by segment
        buckets: Optional detailed pipeline buckets
        aging: Pipeline aging model
        weeks_to_close: Weeks remaining in period

    Returns:
        CoverageReport with full analysis
    """
    if as_of_date is None:
        as_of_date = date.today()
    if multiples is None:
        multiples = CoverageMultiples()
    if aging is None:
        aging = PipelineAging()

    # Calculate segment coverages
    segments: dict[PipelineSegment, SegmentCoverage] = {}
    total_target = 0
    total_pipeline = 0
    weighted_required = 0
    healthy_count = 0
    at_risk_count = 0

    # Filter buckets by segment if provided
    segment_buckets = {}
    if buckets:
        for bucket in buckets:
            if bucket.segment not in segment_buckets:
                segment_buckets[bucket.segment] = []
            segment_buckets[bucket.segment].append(bucket)

    for segment in targets:
        target = targets.get(segment, 0)
        pipe = pipeline.get(segment, 0)
        seg_buckets = segment_buckets.get(segment)

        coverage = calculate_segment_coverage(
            target=target,
            pipeline=pipe,
            segment=segment,
            multiples=multiples,
            buckets=seg_buckets,
            aging=aging,
        )

        segments[segment] = coverage
        total_target += target
        total_pipeline += pipe
        weighted_required += coverage.required_pipeline

        if coverage.is_healthy:
            healthy_count += 1
        else:
            at_risk_count += 1

    # Calculate overall metrics
    overall_coverage = total_pipeline / total_target if total_target > 0 else 0
    pipeline_gap = max(0, weighted_required - total_pipeline)

    # Recommended weekly pipeline create
    recommended_weekly = pipeline_gap / max(1, weeks_to_close) if pipeline_gap > 0 else 0

    # Pipeline by source if buckets provided
    pipeline_by_source = {}
    avg_age_days = 0
    total_age_weighted = 0
    total_pipe_for_age = 0

    if buckets:
        for bucket in buckets:
            source = bucket.source or "unknown"
            pipeline_by_source[source] = pipeline_by_source.get(source, 0) + bucket.amount
            total_age_weighted += bucket.days_old * bucket.amount
            total_pipe_for_age += bucket.amount

        avg_age_days = total_age_weighted / total_pipe_for_age if total_pipe_for_age > 0 else 0

    # Age-adjusted coverage
    total_age_adjusted = sum(s.age_adjusted_pipeline for s in segments.values())
    age_adjusted_coverage = total_age_adjusted / total_target if total_target > 0 else 0

    return CoverageReport(
        as_of_date=as_of_date,
        total_target=total_target,
        total_pipeline=total_pipeline,
        weighted_required_pipeline=weighted_required,
        overall_coverage=overall_coverage,
        segments=segments,
        pipeline_by_source=pipeline_by_source,
        healthy_segments=healthy_count,
        at_risk_segments=at_risk_count,
        avg_pipeline_age_days=avg_age_days,
        age_adjusted_coverage=age_adjusted_coverage,
        pipeline_gap=pipeline_gap,
        recommended_weekly_create=recommended_weekly,
        weeks_to_close=weeks_to_close,
    )


def calculate_required_pipeline(
    target: float,
    segment: PipelineSegment = PipelineSegment.ENTERPRISE,
    multiples: Optional[CoverageMultiples] = None,
) -> float:
    """
    Calculate required pipeline for a target.

    Simple helper for quick calculations.

    Args:
        target: Bookings target
        segment: Segment type
        multiples: Coverage multiples

    Returns:
        Required pipeline value
    """
    if multiples is None:
        multiples = CoverageMultiples()

    return target * multiples.get_multiple(segment)


def calculate_achievable_bookings(
    pipeline: float,
    segment: PipelineSegment = PipelineSegment.ENTERPRISE,
    multiples: Optional[CoverageMultiples] = None,
) -> float:
    """
    Calculate achievable bookings from pipeline.

    Inverse of required_pipeline - given pipeline, what can we close?

    Args:
        pipeline: Current pipeline value
        segment: Segment type
        multiples: Coverage multiples

    Returns:
        Achievable bookings
    """
    if multiples is None:
        multiples = CoverageMultiples()

    multiple = multiples.get_multiple(segment)
    return pipeline / multiple if multiple > 0 else 0


@dataclass
class StageConversion:
    """Stage-to-stage conversion rate with confidence."""
    from_stage: str
    to_stage: str
    rate: float
    sample_size: int = 0
    confidence: str = "assumed"  # "observed", "blended", "assumed"


@dataclass
class PipelineQualityScore:
    """
    Pipeline quality score based on stage distribution and aging.

    Score from 0-100:
    - 80-100: High quality - stage distribution and aging look healthy
    - 60-79: Medium quality - some concerns
    - 40-59: Low quality - significant issues
    - 0-39: At risk - needs immediate attention
    """
    score: float
    stage_score: float  # 0-100 based on stage distribution
    age_score: float    # 0-100 based on pipeline age
    source_score: float # 0-100 based on source diversity

    stage_breakdown: dict[str, float] = field(default_factory=dict)
    age_breakdown: dict[str, float] = field(default_factory=dict)

    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    @property
    def quality_label(self) -> str:
        """Human-readable quality label."""
        if self.score >= 80:
            return "High Quality"
        elif self.score >= 60:
            return "Medium Quality"
        elif self.score >= 40:
            return "Low Quality"
        else:
            return "At Risk"


def calculate_pipeline_quality(
    buckets: list[PipelineBucket],
    ideal_stage_distribution: Optional[dict[str, float]] = None,
    aging: Optional[PipelineAging] = None,
    ideal_source_mix: Optional[PipelineSourceMix] = None,
) -> PipelineQualityScore:
    """
    Calculate pipeline quality score.

    Evaluates pipeline health based on:
    1. Stage distribution (more late-stage = higher quality)
    2. Age distribution (fresher = higher quality)
    3. Source diversity (balanced sources = higher quality)

    Args:
        buckets: List of pipeline buckets to analyze
        ideal_stage_distribution: Ideal % at each stage
        aging: Pipeline aging model
        ideal_source_mix: Target source mix

    Returns:
        PipelineQualityScore with detailed breakdown
    """
    if aging is None:
        aging = PipelineAging()

    # Default ideal distribution (more weight to later stages)
    if ideal_stage_distribution is None:
        ideal_stage_distribution = {
            "S0": 0.10,  # Only 10% should be S0
            "S1": 0.15,
            "S2": 0.25,
            "S3": 0.20,
            "S4": 0.15,
            "S5": 0.15,
        }

    if ideal_source_mix is None:
        ideal_source_mix = PipelineSourceMix()

    total_pipeline = sum(b.amount for b in buckets)
    if total_pipeline == 0:
        return PipelineQualityScore(
            score=0,
            stage_score=0,
            age_score=0,
            source_score=0,
            issues=["No pipeline to analyze"],
            recommendations=["Generate pipeline immediately"],
        )

    # Calculate stage distribution
    stage_amounts = {}
    for bucket in buckets:
        stage = bucket.stage
        stage_amounts[stage] = stage_amounts.get(stage, 0) + bucket.amount

    stage_breakdown = {s: amt / total_pipeline for s, amt in stage_amounts.items()}

    # Stage score: penalize deviation from ideal
    stage_score = 100
    issues = []
    recommendations = []

    # Heavy penalty for too much early-stage
    s0_s1_pct = stage_breakdown.get("S0", 0) + stage_breakdown.get("S1", 0)
    if s0_s1_pct > 0.40:
        stage_score -= 30
        issues.append(f"Too much early-stage pipeline ({s0_s1_pct:.0%} is S0/S1)")
        recommendations.append("Focus on advancing deals through discovery/scoping")
    elif s0_s1_pct > 0.30:
        stage_score -= 15
        issues.append(f"Early-stage heavy ({s0_s1_pct:.0%} is S0/S1)")

    # Bonus for late-stage
    s4_s5_pct = stage_breakdown.get("S4", 0) + stage_breakdown.get("S5", 0)
    if s4_s5_pct >= 0.30:
        stage_score = min(100, stage_score + 10)

    # Calculate age distribution
    age_brackets = {
        "0-30 days": 0,
        "31-60 days": 0,
        "61-90 days": 0,
        "91-180 days": 0,
        "180+ days": 0,
    }

    for bucket in buckets:
        if bucket.days_old <= 30:
            age_brackets["0-30 days"] += bucket.amount
        elif bucket.days_old <= 60:
            age_brackets["31-60 days"] += bucket.amount
        elif bucket.days_old <= 90:
            age_brackets["61-90 days"] += bucket.amount
        elif bucket.days_old <= 180:
            age_brackets["91-180 days"] += bucket.amount
        else:
            age_brackets["180+ days"] += bucket.amount

    age_breakdown = {k: v / total_pipeline for k, v in age_brackets.items()}

    # Age score
    age_score = 100
    stale_pct = age_breakdown.get("91-180 days", 0) + age_breakdown.get("180+ days", 0)
    if stale_pct > 0.40:
        age_score -= 40
        issues.append(f"Significant stale pipeline ({stale_pct:.0%} is 90+ days old)")
        recommendations.append("Review and clean stale deals, reset close dates or mark lost")
    elif stale_pct > 0.25:
        age_score -= 20
        issues.append(f"Some stale pipeline ({stale_pct:.0%} is 90+ days old)")

    fresh_pct = age_breakdown.get("0-30 days", 0)
    if fresh_pct >= 0.30:
        age_score = min(100, age_score + 10)
    elif fresh_pct < 0.15:
        age_score -= 15
        issues.append(f"Low fresh pipeline ({fresh_pct:.0%} is under 30 days)")
        recommendations.append("Increase pipeline generation activity")

    # Calculate source distribution
    source_amounts = {}
    for bucket in buckets:
        source = bucket.source or "unknown"
        source_amounts[source] = source_amounts.get(source, 0) + bucket.amount

    # Source score: reward diversity, penalize over-reliance
    source_score = 100
    source_pcts = {s: amt / total_pipeline for s, amt in source_amounts.items()}

    # Check for over-reliance on single source
    max_source_pct = max(source_pcts.values()) if source_pcts else 0
    if max_source_pct > 0.80:
        source_score -= 30
        issues.append(f"Over-reliance on single source ({max_source_pct:.0%})")
        recommendations.append("Diversify pipeline sources")
    elif max_source_pct > 0.70:
        source_score -= 15

    # Calculate weighted score
    score = (stage_score * 0.40 + age_score * 0.40 + source_score * 0.20)

    if not issues:
        recommendations.append("Pipeline health looks good - maintain current cadence")

    return PipelineQualityScore(
        score=round(score, 1),
        stage_score=round(stage_score, 1),
        age_score=round(age_score, 1),
        source_score=round(source_score, 1),
        stage_breakdown=stage_breakdown,
        age_breakdown=age_breakdown,
        issues=issues,
        recommendations=recommendations,
    )


def calculate_weighted_pipeline(
    buckets: list[PipelineBucket],
    stage_weights: Optional[dict[str, float]] = None,
    aging: Optional[PipelineAging] = None,
) -> float:
    """
    Calculate weighted pipeline value.

    Weights pipeline by stage probability and aging discount.
    More realistic than raw pipeline value.

    Args:
        buckets: Pipeline buckets to analyze
        stage_weights: Close probability by stage
        aging: Pipeline aging model

    Returns:
        Weighted pipeline value
    """
    if stage_weights is None:
        # Default: probability of closing from each stage
        stage_weights = {
            "S0": 0.05,  # 5% from S0
            "S1": 0.10,  # 10% from S1
            "S2": 0.20,  # 20% from S2
            "S3": 0.40,  # 40% from S3
            "S4": 0.60,  # 60% from S4
            "S5": 0.80,  # 80% from S5
        }

    if aging is None:
        aging = PipelineAging()

    weighted = 0
    for bucket in buckets:
        stage_prob = stage_weights.get(bucket.stage, 0.10)
        age_multiplier = aging.get_age_multiplier(bucket.days_old)
        weighted += bucket.amount * stage_prob * age_multiplier

    return weighted


def project_pipeline_needs(
    quarterly_target: float,
    segment_mix: dict[PipelineSegment, float],
    multiples: Optional[CoverageMultiples] = None,
    source_mix: Optional[PipelineSourceMix] = None,
    weeks_in_quarter: int = 13,
) -> dict:
    """
    Project pipeline generation needs to hit a quarterly target.

    Breaks down by segment and source to guide activity planning.

    Args:
        quarterly_target: Total bookings target
        segment_mix: Target mix by segment (should sum to 1.0)
        multiples: Coverage multiples
        source_mix: Pipeline source mix
        weeks_in_quarter: Weeks in the quarter

    Returns:
        Dict with pipeline needs by segment and source
    """
    if multiples is None:
        multiples = CoverageMultiples()
    if source_mix is None:
        source_mix = PipelineSourceMix()

    # Calculate segment targets
    segment_targets = {}
    segment_pipeline_needs = {}
    total_pipeline_needed = 0

    for segment, pct in segment_mix.items():
        target = quarterly_target * pct
        segment_targets[segment] = target
        pipeline_needed = calculate_required_pipeline(target, segment, multiples)
        segment_pipeline_needs[segment] = pipeline_needed
        total_pipeline_needed += pipeline_needed

    # Calculate source breakdown
    source_needs = {
        "ae_sourced": total_pipeline_needed * source_mix.ae_sourced,
        "sdr_sourced": total_pipeline_needed * source_mix.sdr_sourced,
        "marketing_sourced": total_pipeline_needed * source_mix.marketing_sourced,
        "partner_sourced": total_pipeline_needed * source_mix.partner_sourced,
    }

    # Weekly generation rate
    weekly_pipeline = total_pipeline_needed / weeks_in_quarter

    return {
        "quarterly_target": quarterly_target,
        "total_pipeline_needed": total_pipeline_needed,
        "weighted_coverage_multiple": total_pipeline_needed / quarterly_target,
        "by_segment": {
            seg.value: {
                "target": segment_targets[seg],
                "pipeline_needed": segment_pipeline_needs[seg],
                "coverage_multiple": multiples.get_multiple(seg),
            }
            for seg in segment_mix
        },
        "by_source": source_needs,
        "weekly_pipeline_target": weekly_pipeline,
        "weekly_by_source": {
            source: amount / weeks_in_quarter
            for source, amount in source_needs.items()
        },
    }

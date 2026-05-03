"""Public result types for the planning tie-out model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class QuarterTieout:
    """Side-by-side comparison for a single quarter."""

    quarter: str  # e.g. "Q1FY26"
    period_start: date = date(2026, 2, 1)
    period_end: date = date(2026, 4, 30)

    # Top-down (from targets.yaml)
    td_bookings: float = 0
    td_plg: float = 0
    td_expansion: float = 0
    td_total_net_new: float = 0
    td_ending_arr: float = 0
    td_pipeline_target: float = 0

    # Top-down headcount targets
    td_aes: int = 0
    td_ses: int = 0
    td_sdrs: int = 0
    td_total_gtm: int = 0

    # Top-down funnel targets (weekly)
    td_mqls_weekly: int = 0
    td_s0_weekly: int = 0
    td_s1_weekly: int = 0
    td_s2_weekly: int = 0

    # Modeled scenario output
    bu_sales_led_arr: float = 0
    bu_plg_arr: float = 0
    bu_expansion_arr: float = 0
    bu_churn: float = 0  # plan-derived churn deducted from BU total
    bu_total_arr: float = 0
    bu_ramped_aes: int = 0
    bu_total_aes: int = 0
    bu_blended_ramp: float = 0

    # Modeled funnel (projected from conversion rates)
    bu_mqls_projected: int = 0
    bu_s0_projected: int = 0
    bu_s1_projected: int = 0
    bu_s2_projected: int = 0

    # Actuals (from Salesforce / warehouse, if available)
    actual_bookings: float = 0
    actual_pipeline: float = 0
    actual_mqls: int = 0
    actual_s0: int = 0
    actual_s1: int = 0
    actual_s2: int = 0

    # --- v2 additions ---
    conversion_rates: dict = field(default_factory=dict)
    funnel_tieout: dict = field(default_factory=dict)
    source_breakdown: dict = field(default_factory=dict)
    expansion_breakdown: dict = field(default_factory=dict)
    target_provenance: dict = field(default_factory=dict)
    confidence_tier: str = "planned"
    is_derived_targets: bool = False
    plg_source: str = "config"  # "config", "salesforce_observed", or "cdw_observed"

    @property
    def bookings_gap(self) -> float:
        """Gap between top-down target and modeled projection."""
        return self.td_bookings - self.bu_sales_led_arr

    @property
    def bookings_gap_pct(self) -> float:
        if self.td_bookings == 0:
            return 0
        return self.bookings_gap / self.td_bookings

    @property
    def total_gap(self) -> float:
        return self.td_total_net_new - self.bu_total_arr

    @property
    def total_gap_pct(self) -> float:
        if self.td_total_net_new == 0:
            return 0
        return self.total_gap / self.td_total_net_new

    @property
    def capacity_utilization(self) -> float:
        """How much of modeled capacity is needed to hit top-down."""
        if self.bu_sales_led_arr == 0:
            return float("inf")
        return self.td_bookings / self.bu_sales_led_arr

    @property
    def status(self) -> str:
        gap = abs(self.bookings_gap_pct)
        if gap <= 0.05:
            return "aligned"
        if gap <= 0.15:
            return "minor_gap"
        if gap <= 0.30:
            return "significant_gap"
        return "critical_gap"

    def quarter_state(self, as_of: Optional[date] = None) -> str:
        """Return whether the quarter is planned, in progress, or complete."""
        as_of = as_of or date.today()
        if as_of < self.period_start:
            return "not_started"
        if as_of > self.period_end:
            return "completed"
        return "in_progress"

    def elapsed_fraction(self, as_of: Optional[date] = None) -> float:
        """Return elapsed quarter fraction from 0.0 to 1.0."""
        as_of = as_of or date.today()
        total_days = max((self.period_end - self.period_start).days + 1, 1)
        if as_of < self.period_start:
            return 0.0
        if as_of > self.period_end:
            return 1.0
        elapsed_days = max((as_of - self.period_start).days + 1, 0)
        return min(max(elapsed_days / total_days, 0.0), 1.0)

    def reforecast_summary(self, as_of: Optional[date] = None) -> dict:
        """Return quarter-to-date actuals, remaining plan, and latest reforecast."""
        elapsed_fraction = self.elapsed_fraction(as_of)
        plan_to_date_bookings = self.td_bookings * elapsed_fraction
        pace_gap = self.actual_bookings - plan_to_date_bookings
        reforecast_gap = self.bu_sales_led_arr - self.td_bookings
        return {
            "quarter_state": self.quarter_state(as_of),
            "elapsed_fraction": elapsed_fraction,
            "actual_bookings": self.actual_bookings,
            "plan_to_date_bookings": plan_to_date_bookings,
            "pace_gap": pace_gap,
            "pace_gap_pct": (pace_gap / plan_to_date_bookings) if plan_to_date_bookings else 0.0,
            "remaining_plan_bookings": max(self.td_bookings - self.actual_bookings, 0.0),
            "remaining_bu_bookings": max(self.bu_sales_led_arr - self.actual_bookings, 0.0),
            "reforecast_bookings": self.bu_sales_led_arr,
            "reforecast_gap": reforecast_gap,
            "reforecast_gap_pct": (reforecast_gap / self.td_bookings) if self.td_bookings else 0.0,
            "has_actuals": self.actual_bookings > 0,
        }

    def to_dict(self) -> dict:
        return {
            "quarter": self.quarter,
            # Flat fields required by schema/snapshot.schema.json#/$defs/QuarterData.
            # Rich nested fields below are the canonical engine output;
            # the flat fields are consumer-friendly mirrors.
            "period_start": self.period_start.isoformat() if self.period_start else "",
            "period_end": self.period_end.isoformat() if self.period_end else "",
            "td_bookings": self.td_bookings,
            "bu_sales_led_arr": self.bu_sales_led_arr,
            "actual_bookings": self.actual_bookings,
            "top_down": {
                "bookings": self.td_bookings,
                "plg": self.td_plg,
                "expansion": self.td_expansion,
                "total_net_new": self.td_total_net_new,
                "ending_arr": self.td_ending_arr,
                "pipeline_target": self.td_pipeline_target,
                "aes": self.td_aes,
                "total_gtm": self.td_total_gtm,
            },
            "bottoms_up": {
                "sales_led_arr": self.bu_sales_led_arr,
                "plg_arr": self.bu_plg_arr,
                "expansion_arr": self.bu_expansion_arr,
                "total_arr": self.bu_total_arr,
                "ramped_aes": self.bu_ramped_aes,
                "total_aes": self.bu_total_aes,
            },
            "actuals": {
                "bookings": self.actual_bookings,
                "pipeline": self.actual_pipeline,
                "mqls_weekly": self.actual_mqls,
                "s0_weekly": self.actual_s0,
                "s1_weekly": self.actual_s1,
                "s2_weekly": self.actual_s2,
            },
            "gap": {
                "bookings": self.bookings_gap,
                "bookings_pct": self.bookings_gap_pct,
                "total": self.total_gap,
                "total_pct": self.total_gap_pct,
                "status": self.status,
            },
            "conversion_rates": self.conversion_rates,
            "funnel_tieout": self.funnel_tieout,
            "source_breakdown": self.source_breakdown,
            "expansion_breakdown": self.expansion_breakdown,
            "target_provenance": self.target_provenance,
            "reforecast": self.reforecast_summary(),
            "confidence_tier": self.confidence_tier,
            "is_derived_targets": self.is_derived_targets,
        }


@dataclass
class MonthlyCapacityRow:
    """Monthly capacity breakdown for the timeline view."""

    month: date
    label: str = ""

    # Headcount
    ae_total: int = 0
    ae_ramped: int = 0
    ae_ramping: int = 0
    se_total: int = 0
    sdr_total: int = 0

    # Capacity ($)
    ae_capacity: float = 0
    ae_capacity_ramped: float = 0
    ae_capacity_ramping: float = 0

    # Ramp
    blended_ramp_pct: float = 0

    # Targets (monthly slice of quarterly target when supported by the plan contract)
    monthly_target: Optional[float] = None

    def __post_init__(self):
        if not self.label:
            self.label = self.month.strftime("%b %Y")
        self.ae_ramping = self.ae_total - self.ae_ramped

    def to_dict(self) -> dict:
        return {
            "month": self.month.isoformat(),
            "label": self.label,
            "ae_total": self.ae_total,
            "ae_ramped": self.ae_ramped,
            "ae_ramping": self.ae_ramping,
            "se_total": self.se_total,
            "sdr_total": self.sdr_total,
            "ae_capacity": self.ae_capacity,
            "ae_capacity_ramped": self.ae_capacity_ramped,
            "ae_capacity_ramping": self.ae_capacity_ramping,
            "blended_ramp_pct": self.blended_ramp_pct,
            "monthly_target": self.monthly_target,
        }


@dataclass
class ScenarioResult:
    """Result of a scenario flex computation."""

    name: str
    description: str = ""
    quarters: list[QuarterTieout] = field(default_factory=list)
    monthly_capacity: list[MonthlyCapacityRow] = field(default_factory=list)
    monthly_months: list[date] = field(default_factory=list)
    monthly_pipeline_creation: list[float] = field(default_factory=list)
    monthly_bookings_expected: list[float] = field(default_factory=list)
    monthly_bookings_capped: list[float] = field(default_factory=list)
    monthly_overflow: list[float] = field(default_factory=list)
    monthly_existing_inventory_wins: list[float] = field(default_factory=list)
    monthly_existing_inventory_losses: list[float] = field(default_factory=list)
    monthly_existing_inventory_remaining: list[float] = field(default_factory=list)
    monthly_future_generation_wins: list[float] = field(default_factory=list)
    monthly_total_expected_wins: list[float] = field(default_factory=list)
    monthly_rollforward_provenance: dict = field(default_factory=dict)
    monthly_source_detail: list[dict] = field(default_factory=list)

    # Overrides applied
    overrides: dict = field(default_factory=dict)
    # Capacity warnings (e.g., roster vs plan divergence)
    capacity_warnings: list[str] = field(default_factory=list)

    @property
    def fy_total_td(self) -> float:
        return sum(q.td_total_net_new for q in self.quarters)

    @property
    def fy_total_bu(self) -> float:
        return sum(q.bu_total_arr for q in self.quarters)

    @property
    def fy_bookings_td(self) -> float:
        return sum(q.td_bookings for q in self.quarters)

    @property
    def fy_bookings_bu(self) -> float:
        return sum(q.bu_sales_led_arr for q in self.quarters)

    @property
    def fy_sales_led_gap(self) -> float:
        return self.fy_bookings_td - self.fy_bookings_bu

    @property
    def fy_sales_led_gap_pct(self) -> float:
        if self.fy_bookings_td == 0:
            return 0
        return self.fy_sales_led_gap / self.fy_bookings_td

    @property
    def fy_gap(self) -> float:
        return self.fy_total_td - self.fy_total_bu

    @property
    def fy_gap_pct(self) -> float:
        if self.fy_total_td == 0:
            return 0
        return self.fy_gap / self.fy_total_td

    @property
    def fy_ending_arr_td(self) -> float:
        if self.quarters:
            return self.quarters[-1].td_ending_arr
        return 0

    def to_dict(self) -> dict:
        source_detail = []
        for row in self.monthly_source_detail:
            serialized = dict(row)
            month = serialized.get("month")
            if hasattr(month, "isoformat"):
                serialized["month"] = month.isoformat()
            source_detail.append(serialized)
        return {
            "name": self.name,
            "description": self.description,
            "overrides": self.overrides,
            "fy_summary": {
                "total_net_new_td": self.fy_total_td,
                "total_net_new_bu": self.fy_total_bu,
                "bookings_td": self.fy_bookings_td,
                "bookings_bu": self.fy_bookings_bu,
                "gap": self.fy_sales_led_gap,
                "gap_pct": self.fy_sales_led_gap_pct,
                "executive_context_gap": self.fy_gap,
                "executive_context_gap_pct": self.fy_gap_pct,
            },
            "monthly_projection": {
                "months": [m.isoformat() for m in self.monthly_months],
                "pipeline_creation": self.monthly_pipeline_creation,
                "expected_bookings": self.monthly_bookings_expected,
                "capped_bookings": self.monthly_bookings_capped,
                "overflow": self.monthly_overflow,
                "existing_inventory_wins": self.monthly_existing_inventory_wins,
                "existing_inventory_losses": self.monthly_existing_inventory_losses,
                "existing_inventory_remaining": self.monthly_existing_inventory_remaining,
                "future_generation_wins": self.monthly_future_generation_wins,
                "total_expected_wins": self.monthly_total_expected_wins,
                "rollforward_provenance": self.monthly_rollforward_provenance,
                "source_detail": source_detail,
            },
            "quarters": [q.to_dict() for q in self.quarters],
        }


@dataclass
class TieoutResult:
    """Complete tie-out result with trajectory plus archived-plan compatibility."""

    base: ScenarioResult = field(default_factory=lambda: ScenarioResult(name="Archived Plan"))
    trajectory: ScenarioResult = field(default_factory=lambda: ScenarioResult(name="Trajectory"))
    scenarios: dict[str, ScenarioResult] = field(default_factory=dict)

    # Config used
    top_down_beginning_arr: float = 0
    beginning_arr: float = 0
    beginning_arr_provenance: dict = field(default_factory=dict)
    bookings_summary: dict = field(default_factory=dict)
    bookings_summary_provenance: dict = field(default_factory=dict)
    assumptions_snapshot: dict = field(default_factory=dict)
    top_down_plan: dict = field(default_factory=dict)

    # v2 addition
    health_status: dict = field(default_factory=dict)
    arr_movements: dict = field(default_factory=dict)
    as_of: date | None = None

    @property
    def has_trajectory(self) -> bool:
        """Return True when the trajectory scenario is populated."""
        return bool(self.trajectory and self.trajectory.quarters)

    @property
    def primary_scenario(self) -> ScenarioResult:
        """Return the default user-facing scenario, preferring trajectory."""
        if self.has_trajectory:
            return self.trajectory
        return self.base

    @property
    def archived_plan(self) -> ScenarioResult:
        """Return the archived config-driven plan scenario."""
        return self.base

    @property
    def primary_scenario_label(self) -> str:
        """Return a user-facing label for the default scenario."""
        if self.has_trajectory:
            return "Trajectory"
        return "Archived Plan"

    @property
    def fy_trajectory_bookings(self) -> float:
        """FY trajectory sales-led bookings."""
        return sum(q.bu_sales_led_arr for q in self.trajectory.quarters)

    @property
    def fy_trajectory_total(self) -> float:
        """FY trajectory total net new ARR."""
        return sum(q.bu_total_arr for q in self.trajectory.quarters)

    def summary(self) -> str:
        primary = self.primary_scenario
        top_down_sales_led = primary.fy_bookings_td if primary.quarters else self.base.fy_bookings_td
        sales_led_deficit = top_down_sales_led - primary.fy_bookings_bu
        sales_led_deficit_pct = sales_led_deficit / top_down_sales_led if top_down_sales_led else 0
        top_down_total = primary.fy_total_td if primary.quarters else self.base.fy_total_td
        total_deficit = top_down_total - primary.fy_total_bu
        total_deficit_pct = total_deficit / top_down_total if top_down_total else 0
        lines = [
            "",
            "Forecast Tieout",
            "=" * 80,
            "",
            f"Beginning ARR: ${self.beginning_arr:,.0f}",
            "",
            "Primary comparison: Sales-led ARR (operator-comparable).",
            "Executive-context total net new ARR is shown separately for reference.",
            "",
            f"{'':>15} {'Plan Sales-Led':>14} {self.primary_scenario_label:>14} {'Deficit':>14} {'Deficit %':>10}",
            "-" * 78,
        ]

        for q in primary.quarters:
            lines.append(
                f"{q.quarter:>15} "
                f"${q.td_bookings:>12,.0f} "
                f"${q.bu_sales_led_arr:>12,.0f} "
                f"${q.bookings_gap:>12,.0f} "
                f"{q.bookings_gap_pct:>9.1%}"
            )

        lines.append("-" * 78)
        lines.append(
            f"{'FY26 TOTAL':>15} "
            f"${top_down_sales_led:>12,.0f} "
            f"${primary.fy_bookings_bu:>12,.0f} "
            f"${sales_led_deficit:>12,.0f} "
            f"{sales_led_deficit_pct:>9.1%}"
        )
        lines.append("")
        lines.append(
            "Executive-context FY total net new ARR: "
            f"plan ${top_down_total:,.0f}, "
            f"{self.primary_scenario_label} ${primary.fy_total_bu:,.0f}, "
            f"deficit ${total_deficit:,.0f} ({total_deficit_pct:.1%})"
        )

        return "\n".join(lines)

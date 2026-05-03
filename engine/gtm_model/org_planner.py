"""
GTM Org Planner Module - Bi-Directional Org Planning Engine.

Unified planning engine for top-down and bottom-up org planning:
- Top-Down: Target ARR → Required AEs → Derived team → Hiring timeline → Costs
- Bottom-Up: Current team + Hiring plan → Achievable ARR → Gap analysis

Example usage:
    from gtm_model.org_planner import OrgPlanner, OrgPlan

    planner = OrgPlanner()

    # Top-down: What org do I need to hit $75M ARR?
    plan = planner.plan_to_target(target_arr=75_000_000, current_team=team)
    print(plan.summary())

    # Bottom-up: With my current team + hiring plan, what can I achieve?
    plan = planner.plan_from_capacity(current_team=team, hiring_plan=hires)
    print(f"Achievable ARR: ${plan.achievable_arr:,.0f}")

    # Flex scenario: Add 10 AEs and auto-derive support roles
    new_plan = planner.flex_scenario(base_plan=plan, add_aes=10)
    print(new_plan.team_delta.summary())
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import math

from dateutil.relativedelta import relativedelta

from .team_structure import (
    CoverageRatios,
    DerivedTeam,
    derive_team,
    derive_team_from_segments,
    calculate_incremental_support,
    team_from_headcount,
    validate_coverage,
)
from .hiring import (
    HiringPlan,
    HiringPace,
    AttritionRates,
    generate_hiring_plan,
    project_headcount_timeline,
    reverse_hiring_timeline,
)
from .economics import (
    RoleCosts,
    OrgCost,
    calculate_org_cost_from_team,
    calculate_sm_efficiency,
)
from .capacity import (
    MonthlyCapacity,
    calculate_monthly_timeline,
    calculate_required_aes_for_arr,
    calculate_team_arr_capacity,
    format_monthly_timeline,
    RepCapacity,
    SDRCapacity,
    SECapacity,
    Segment,
    DEFAULT_QUOTAS,
)
from .segments import (
    SegmentProductivity,
    SelfServeStream,
    AttritionModel,
    calculate_segment_capacity,
    calculate_combined_arr_target,
)


@dataclass
class OrgPlan:
    """
    Complete org plan state.

    Contains team composition, hiring plan, capacity projections, and costs.
    """

    period: str = ""  # e.g., "FY26"
    period_months: int = 12
    start_month: Optional[date] = None
    end_month: Optional[date] = None

    # Team composition
    current_team: Optional[DerivedTeam] = None
    target_team: Optional[DerivedTeam] = None
    team_delta: Optional[DerivedTeam] = None  # Incremental headcount needed

    # Hiring plan
    hiring_plan: Optional[HiringPlan] = None

    # Capacity projections
    monthly_capacity: list[MonthlyCapacity] = field(default_factory=list)
    quarterly_capacity: dict = field(default_factory=dict)  # Q1, Q2, Q3, Q4 rollups

    # Costs
    current_cost: Optional[OrgCost] = None
    target_cost: Optional[OrgCost] = None
    incremental_cost: float = 0.0

    # Targets and achievable
    arr_target: float = 0.0
    achievable_arr: float = 0.0
    gap: float = 0.0
    gap_pct: float = 0.0

    # Ratios used
    coverage_ratios: Optional[CoverageRatios] = None
    role_costs: Optional[RoleCosts] = None

    # Segment productivity (v3 extension)
    segment_capacity: dict = field(default_factory=dict)  # Enterprise vs Commercial breakdown
    enterprise_productivity: Optional[SegmentProductivity] = None
    commercial_productivity: Optional[SegmentProductivity] = None

    # Self-serve stream (v3 extension)
    self_serve_stream: Optional[SelfServeStream] = None
    self_serve_arr: float = 0.0

    # Attrition (v3 extension)
    attrition_model: Optional[AttritionModel] = None
    gross_hires_needed: dict = field(default_factory=dict)  # By role

    # Validation
    coverage_validation: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate derived fields."""
        if self.arr_target > 0 and self.achievable_arr > 0:
            self.gap = self.arr_target - self.achievable_arr
            self.gap_pct = (self.gap / self.arr_target) if self.arr_target > 0 else 0.0

        if self.target_cost and self.current_cost:
            self.incremental_cost = self.target_cost.total_cost - self.current_cost.total_cost

    @property
    def is_achievable(self) -> bool:
        """Check if target is achievable with current/target team."""
        return self.gap <= 0

    @property
    def total_new_hires(self) -> int:
        """Total new hires in the hiring plan."""
        return len(self.hiring_plan.hires) if self.hiring_plan else 0

    @property
    def annual_capacity(self) -> float:
        """Total ARR capacity for the period."""
        return sum(mc.ae_capacity for mc in self.monthly_capacity)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "period": self.period,
            "period_months": self.period_months,
            "start_month": self.start_month.isoformat() if self.start_month else None,
            "end_month": self.end_month.isoformat() if self.end_month else None,
            "current_team": self.current_team.to_dict() if self.current_team else None,
            "target_team": self.target_team.to_dict() if self.target_team else None,
            "team_delta": self.team_delta.to_dict() if self.team_delta else None,
            "hiring_plan": self.hiring_plan.to_dict() if self.hiring_plan else None,
            "current_cost": self.current_cost.to_dict() if self.current_cost else None,
            "target_cost": self.target_cost.to_dict() if self.target_cost else None,
            "incremental_cost": self.incremental_cost,
            "arr_target": self.arr_target,
            "achievable_arr": self.achievable_arr,
            "gap": self.gap,
            "gap_pct": self.gap_pct,
            "is_achievable": self.is_achievable,
            "total_new_hires": self.total_new_hires,
            "segment_capacity": self.segment_capacity,
            "self_serve_arr": self.self_serve_arr,
            "gross_hires_needed": self.gross_hires_needed,
            "warnings": self.warnings,
        }

    def summary(self) -> str:
        """Return formatted summary of org plan."""
        lines = [
            f"Org Plan: {self.period}",
            "=" * 70,
            "",
        ]

        if self.start_month and self.end_month:
            lines.append(f"Period: {self.start_month} to {self.end_month}")
            lines.append("")

        # Target vs Achievable
        lines.extend([
            "TARGETS",
            "-" * 50,
            f"  ARR Target:       ${self.arr_target:,.0f}",
            f"  Achievable ARR:   ${self.achievable_arr:,.0f}",
            f"  Gap:              ${self.gap:,.0f} ({self.gap_pct:.1%})",
            f"  Status:           {'ON TRACK' if self.is_achievable else 'GAP EXISTS'}",
            "",
        ])

        # Team composition
        if self.current_team:
            lines.extend([
                "CURRENT TEAM",
                "-" * 50,
                f"  Total AEs:        {self.current_team.total_aes}",
                f"  Total ICs:        {self.current_team.total_ics}",
                f"  Total Managers:   {self.current_team.total_managers}",
                f"  Total Headcount:  {self.current_team.total_headcount}",
                "",
            ])

        if self.target_team and self.current_team:
            lines.extend([
                "TARGET TEAM",
                "-" * 50,
                f"  Total AEs:        {self.target_team.total_aes} (+{self.target_team.total_aes - self.current_team.total_aes})",
                f"  Total ICs:        {self.target_team.total_ics} (+{self.target_team.total_ics - self.current_team.total_ics})",
                f"  Total Managers:   {self.target_team.total_managers} (+{self.target_team.total_managers - self.current_team.total_managers})",
                f"  Total Headcount:  {self.target_team.total_headcount} (+{self.target_team.total_headcount - self.current_team.total_headcount})",
                "",
            ])

        # Team delta
        if self.team_delta:
            lines.extend([
                "INCREMENTAL HEADCOUNT NEEDED",
                "-" * 50,
                f"  AEs (Enterprise): +{self.team_delta.aes_enterprise}",
                f"  AEs (Mid-Market): +{self.team_delta.aes_midmarket}",
                f"  SEs:              +{self.team_delta.ses}",
                f"  SDRs:             +{self.team_delta.sdrs}",
                f"  CSMs:             +{self.team_delta.csms}",
                f"  FDEs:             +{self.team_delta.fdes}",
                f"  AE Managers:      +{self.team_delta.total_ae_managers}",
                f"  Other Managers:   +{self.team_delta.se_managers + self.team_delta.sdr_managers + self.team_delta.csm_managers}",
                f"  Total New Hires:  +{self.team_delta.total_headcount}",
                "",
            ])

        # Costs
        if self.target_cost:
            lines.extend([
                "COSTS",
                "-" * 50,
                f"  Current S&M:      ${self.current_cost.total_cost:,.0f}" if self.current_cost else "  Current S&M:      N/A",
                f"  Target S&M:       ${self.target_cost.total_cost:,.0f}",
                f"  Incremental:      ${self.incremental_cost:,.0f}",
                f"  Monthly S&M:      ${self.target_cost.monthly_cost:,.0f}",
                "",
            ])

        # Segment capacity breakdown
        if self.segment_capacity:
            lines.extend([
                "SEGMENT CAPACITY",
                "-" * 50,
            ])
            if "enterprise" in self.segment_capacity:
                ent = self.segment_capacity["enterprise"]
                lines.append(f"  Enterprise:")
                lines.append(f"    AEs:             {ent.get('aes', 0)}")
                lines.append(f"    Capacity:        ${ent.get('total_capacity', 0):,.0f}")
                lines.append(f"    Avg ACV:         ${ent.get('avg_acv', 0):,.0f}")
            if "commercial" in self.segment_capacity:
                comm = self.segment_capacity["commercial"]
                lines.append(f"  Commercial:")
                lines.append(f"    AEs:             {comm.get('aes', 0)}")
                lines.append(f"    Capacity:        ${comm.get('total_capacity', 0):,.0f}")
                lines.append(f"    Avg ACV:         ${comm.get('avg_acv', 0):,.0f}")
            lines.append("")

        # Self-serve stream
        if self.self_serve_arr > 0:
            lines.extend([
                "SELF-SERVE / PLG",
                "-" * 50,
                f"  Self-serve ARR:   ${self.self_serve_arr:,.0f}",
            ])
            if self.self_serve_stream:
                lines.append(f"  Monthly Signups:  {self.self_serve_stream.monthly_signups}")
                lines.append(f"  Free→Paid Rate:   {self.self_serve_stream.free_to_paid_rate:.1%}")
                lines.append(f"  Monthly Churn:    {self.self_serve_stream.monthly_churn_rate:.1%}")
            lines.append("")

        # Hiring plan summary
        if self.hiring_plan and self.hiring_plan.hires:
            lines.extend([
                "HIRING PLAN",
                "-" * 50,
                f"  Total New Hires:  {len(self.hiring_plan.hires)}",
            ])
            by_role = self.hiring_plan.get_hires_by_role()
            for role, hires in sorted(by_role.items(), key=lambda x: len(x[1]), reverse=True):
                lines.append(f"    {role.value}: {len(hires)}")

            # Gross hires if attrition modeled
            if self.gross_hires_needed:
                lines.append("")
                lines.append("  Gross Hires (incl. attrition backfill):")
                for role, data in self.gross_hires_needed.items():
                    if isinstance(data, dict) and "gross_hires" in data:
                        lines.append(f"    {role}: {data['gross_hires']} (net: {data.get('net_growth', 0)}, backfill: {data.get('expected_attrition', 0)})")
            lines.append("")

        # Warnings
        if self.warnings:
            lines.extend([
                "WARNINGS",
                "-" * 50,
            ])
            for warning in self.warnings:
                lines.append(f"  ! {warning}")
            lines.append("")

        return "\n".join(lines)


class OrgPlanner:
    """
    Bi-directional org planning engine.

    Supports both top-down (target ARR → required org) and
    bottom-up (current org → achievable ARR) planning.

    Now supports segment-specific productivity (Enterprise vs Commercial)
    and attrition modeling for gross hire calculations.
    """

    def __init__(
        self,
        ratios: Optional[CoverageRatios] = None,
        costs: Optional[RoleCosts] = None,
        attainment_rate: float = 0.80,
        enterprise_pct: float = 0.5,
        enterprise_productivity: Optional[SegmentProductivity] = None,
        commercial_productivity: Optional[SegmentProductivity] = None,
        attrition_model: Optional[AttritionModel] = None,
        self_serve_stream: Optional[SelfServeStream] = None,
    ):
        """
        Initialize org planner.

        Args:
            ratios: Coverage ratios to use (defaults to CoverageRatios())
            costs: Role costs to use (defaults to RoleCosts())
            attainment_rate: Expected quota attainment (default 80%) - overridden by segment productivity if provided
            enterprise_pct: Percentage of AEs that are Enterprise (default 50%)
            enterprise_productivity: Enterprise segment productivity assumptions
            commercial_productivity: Commercial segment productivity assumptions
            attrition_model: Attrition rates and backfill assumptions
            self_serve_stream: Self-serve/PLG stream assumptions
        """
        self.ratios = ratios or CoverageRatios()
        self.costs = costs or RoleCosts()
        self.attainment_rate = attainment_rate
        self.enterprise_pct = enterprise_pct

        # Segment productivity (use defaults if not provided)
        self.enterprise_productivity = enterprise_productivity or SegmentProductivity.enterprise()
        self.commercial_productivity = commercial_productivity or SegmentProductivity.commercial()

        # Attrition and self-serve
        self.attrition_model = attrition_model
        self.self_serve_stream = self_serve_stream

    def plan_to_target(
        self,
        target_arr: float,
        current_team: DerivedTeam,
        period: str = "FY26",
        period_months: int = 12,
        start_month: Optional[date] = None,
        hiring_pace: HiringPace = HiringPace.EVEN,
        include_self_serve: bool = True,
    ) -> OrgPlan:
        """
        Top-Down: Given ARR target, derive required org.

        1. Target ARR → Required AE capacity → Required AEs (using segment productivity)
        2. Required AEs → Derived SEs, SDRs, Managers (via coverage ratios)
        3. Team delta → Hiring plan with timing
        4. Calculate gross hires accounting for attrition
        5. Calculate costs and validate economics

        Args:
            target_arr: Target ARR to achieve
            current_team: Current team composition
            period: Period name (e.g., "FY26")
            period_months: Period length in months
            start_month: Start of period (defaults to today)
            hiring_pace: How to spread hires
            include_self_serve: Whether to include self-serve ARR in achievable

        Returns:
            OrgPlan with target team, hiring plan, and costs
        """
        if start_month is None:
            start_month = date.today().replace(day=1)

        end_month = start_month + relativedelta(months=period_months - 1)

        warnings = []

        # Calculate self-serve contribution
        self_serve_arr = 0.0
        if include_self_serve and self.self_serve_stream:
            ss_projection = self.self_serve_stream.project_arr(months=period_months)
            self_serve_arr = ss_projection["total_net_new_arr"]

        # Adjust sales-led target
        sales_led_target = target_arr - self_serve_arr

        # Step 1: Calculate required AEs using segment productivity
        # Use segment-specific quotas and attainment
        ent_capacity = self.enterprise_productivity.effective_annual_capacity * (period_months / 12)
        comm_capacity = self.commercial_productivity.effective_annual_capacity * (period_months / 12)

        # Blended capacity per AE
        blended_capacity = (self.enterprise_pct * ent_capacity) + ((1 - self.enterprise_pct) * comm_capacity)

        # Ramp adjustment based on segment ramp curves (blended)
        ent_ramp_months = self.enterprise_productivity.ramp_months
        comm_ramp_months = self.commercial_productivity.ramp_months
        # For new hires spread across year, assume ~75% blended productivity
        ramp_adjustment = 0.75

        # Required AEs
        required_aes = math.ceil(sales_led_target / (blended_capacity * ramp_adjustment))

        # Step 2: Derive full target team from required AEs
        target_team = derive_team(
            ae_count=required_aes,
            ratios=self.ratios,
            enterprise_pct=self.enterprise_pct,
        )

        # Step 3: Calculate team delta
        team_delta = calculate_incremental_support(
            add_aes=required_aes - current_team.total_aes,
            current_team=current_team,
            ratios=self.ratios,
            enterprise_pct=self.enterprise_pct,
        )

        # Check if we need to reduce (negative delta)
        if team_delta.total_aes < 0:
            warnings.append("Target requires fewer AEs than current team - no hiring needed")
            team_delta = DerivedTeam()  # Zero delta

        # Step 4: Generate hiring plan
        hiring_plan = generate_hiring_plan(
            current_team=current_team,
            target_team=target_team,
            start_month=start_month,
            end_month=end_month,
            pace=hiring_pace,
        )

        # Step 5: Calculate gross hires with attrition
        gross_hires_needed = {}
        if self.attrition_model:
            # AE gross hires
            ae_net = target_team.total_aes - current_team.total_aes
            gross_hires_needed["AE"] = self.attrition_model.calculate_gross_hires(
                starting_headcount=current_team.total_aes,
                target_headcount=target_team.total_aes,
                months=period_months,
                annual_attrition=self.attrition_model.ae_annual,
            )

            # SDR gross hires
            sdr_net = target_team.sdrs - current_team.sdrs
            gross_hires_needed["SDR"] = self.attrition_model.calculate_gross_hires(
                starting_headcount=current_team.sdrs,
                target_headcount=target_team.sdrs,
                months=period_months,
                annual_attrition=self.attrition_model.sdr_annual,
            )

            # SE gross hires
            se_net = target_team.ses - current_team.ses
            gross_hires_needed["SE"] = self.attrition_model.calculate_gross_hires(
                starting_headcount=current_team.ses,
                target_headcount=target_team.ses,
                months=period_months,
                annual_attrition=self.attrition_model.se_annual,
            )

            # Total gross hires warning
            total_gross = sum(d.get("gross_hires", 0) for d in gross_hires_needed.values())
            total_net = sum(d.get("net_growth", 0) for d in gross_hires_needed.values())
            if total_gross > total_net * 1.2:
                warnings.append(f"Attrition adds {total_gross - total_net} extra hires ({total_gross} gross vs {total_net} net)")

        # Step 6: Calculate costs
        current_cost = calculate_org_cost_from_team(
            team=current_team,
            costs=self.costs,
            period_months=period_months,
        )

        target_cost = calculate_org_cost_from_team(
            team=target_team,
            costs=self.costs,
            period_months=period_months,
        )

        # Step 7: Calculate segment capacity breakdown
        segment_capacity = calculate_segment_capacity(
            aes_enterprise=target_team.aes_enterprise,
            aes_commercial=target_team.aes_midmarket,
            months=period_months,
        )

        # Step 8: Calculate achievable ARR with target team (using segment productivity)
        sales_led_achievable = target_team.total_aes * blended_capacity * ramp_adjustment
        achievable_arr = sales_led_achievable + self_serve_arr

        # Step 9: Validate coverage
        coverage_validation = validate_coverage(target_team, self.ratios)

        # Add warnings for understaffed roles
        for role, data in coverage_validation.items():
            if data.get("status") == "UNDERSTAFFED":
                warnings.append(f"{role} is understaffed: {data['actual']} vs {data['expected']} expected")

        return OrgPlan(
            period=period,
            period_months=period_months,
            start_month=start_month,
            end_month=end_month,
            current_team=current_team,
            target_team=target_team,
            team_delta=team_delta,
            hiring_plan=hiring_plan,
            current_cost=current_cost,
            target_cost=target_cost,
            arr_target=target_arr,
            achievable_arr=achievable_arr,
            coverage_ratios=self.ratios,
            role_costs=self.costs,
            segment_capacity=segment_capacity,
            enterprise_productivity=self.enterprise_productivity,
            commercial_productivity=self.commercial_productivity,
            self_serve_stream=self.self_serve_stream,
            self_serve_arr=self_serve_arr,
            attrition_model=self.attrition_model,
            gross_hires_needed=gross_hires_needed,
            coverage_validation=coverage_validation,
            warnings=warnings,
        )

    def plan_from_capacity(
        self,
        current_team: DerivedTeam,
        hiring_plan: Optional[HiringPlan] = None,
        period: str = "FY26",
        period_months: int = 12,
        start_month: Optional[date] = None,
        arr_target: float = 0.0,
        include_self_serve: bool = True,
    ) -> OrgPlan:
        """
        Bottom-Up: Given current team + hiring plan, project achievable ARR.

        1. Apply hiring plan → Future team state
        2. Calculate monthly capacity with ramp (using segment productivity)
        3. Capacity → Expected ARR (including self-serve)
        4. Calculate costs

        Args:
            current_team: Current team composition
            hiring_plan: Optional hiring plan to apply
            period: Period name
            period_months: Period length in months
            start_month: Start of period
            arr_target: Optional ARR target for gap calculation
            include_self_serve: Whether to include self-serve ARR

        Returns:
            OrgPlan with achievable ARR and gap analysis
        """
        if start_month is None:
            start_month = date.today().replace(day=1)

        end_month = start_month + relativedelta(months=period_months - 1)

        warnings = []

        # Build AE team for capacity calculation using segment productivity
        ae_team = []

        # Add current enterprise AEs (assumed fully ramped)
        for i in range(current_team.aes_enterprise):
            ae_team.append(RepCapacity(
                name=f"Current Ent AE {i+1}",
                segment=Segment.ENTERPRISE,
                start_date=start_month - relativedelta(months=self.enterprise_productivity.ramp_months),
                annual_quota=self.enterprise_productivity.annual_quota,
                attainment_rate=self.enterprise_productivity.attainment_rate,
            ))

        # Add current mid-market AEs (assumed fully ramped)
        for i in range(current_team.aes_midmarket):
            ae_team.append(RepCapacity(
                name=f"Current MM AE {i+1}",
                segment=Segment.MID_MARKET,
                start_date=start_month - relativedelta(months=self.commercial_productivity.ramp_months),
                annual_quota=self.commercial_productivity.annual_quota,
                attainment_rate=self.commercial_productivity.attainment_rate,
            ))

        # Add new hires from hiring plan
        if hiring_plan:
            from .team_structure import GTMRole
            for hire in hiring_plan.hires:
                if hire.role in (GTMRole.AE_ENTERPRISE, GTMRole.AE_MIDMARKET):
                    if hire.role == GTMRole.AE_ENTERPRISE:
                        prod = self.enterprise_productivity
                        segment = Segment.ENTERPRISE
                    else:
                        prod = self.commercial_productivity
                        segment = Segment.MID_MARKET

                    ae_team.append(RepCapacity(
                        name=hire.name or f"New AE {len(ae_team)+1}",
                        segment=segment,
                        start_date=hire.hire_month,
                        annual_quota=prod.annual_quota,
                        attainment_rate=prod.attainment_rate,
                    ))

        # Calculate sales-led capacity
        sales_led_arr = calculate_team_arr_capacity(
            ae_team=ae_team,
            period_months=period_months,
            start_month=start_month,
        )

        # Calculate self-serve contribution
        self_serve_arr = 0.0
        if include_self_serve and self.self_serve_stream:
            ss_projection = self.self_serve_stream.project_arr(months=period_months)
            self_serve_arr = ss_projection["total_net_new_arr"]

        achievable_arr = sales_led_arr + self_serve_arr

        # Calculate target team (current + planned hires)
        target_team = current_team  # Start with current
        if hiring_plan:
            # This is simplified - in full version would track by role
            target_team = derive_team(
                ae_count=len(ae_team),
                ratios=self.ratios,
                enterprise_pct=self.enterprise_pct,
            )

        # Calculate segment capacity
        segment_capacity = calculate_segment_capacity(
            aes_enterprise=target_team.aes_enterprise,
            aes_commercial=target_team.aes_midmarket,
            months=period_months,
        )

        # Calculate costs
        current_cost = calculate_org_cost_from_team(
            team=current_team,
            costs=self.costs,
            period_months=period_months,
        )

        target_cost = calculate_org_cost_from_team(
            team=target_team,
            costs=self.costs,
            period_months=period_months,
        )

        # Coverage validation
        coverage_validation = validate_coverage(current_team, self.ratios)
        for role, data in coverage_validation.items():
            if data.get("status") == "UNDERSTAFFED":
                warnings.append(f"{role} is understaffed: {data['actual']} vs {data['expected']} expected")

        return OrgPlan(
            period=period,
            period_months=period_months,
            start_month=start_month,
            end_month=end_month,
            current_team=current_team,
            target_team=target_team,
            hiring_plan=hiring_plan,
            current_cost=current_cost,
            target_cost=target_cost,
            arr_target=arr_target,
            achievable_arr=achievable_arr,
            coverage_ratios=self.ratios,
            role_costs=self.costs,
            segment_capacity=segment_capacity,
            enterprise_productivity=self.enterprise_productivity,
            commercial_productivity=self.commercial_productivity,
            self_serve_stream=self.self_serve_stream,
            self_serve_arr=self_serve_arr,
            coverage_validation=coverage_validation,
            warnings=warnings,
        )

    def flex_scenario(
        self,
        base_plan: OrgPlan,
        add_aes: int = 0,
        add_enterprise_aes: int = 0,
        add_midmarket_aes: int = 0,
        add_ses: int = 0,
        add_sdrs: int = 0,
    ) -> OrgPlan:
        """
        Flex the plan: Add AEs and auto-derive support roles.

        "What if I add 10 AEs to my plan?"

        Args:
            base_plan: Starting plan to flex
            add_aes: AEs to add (split by enterprise_pct)
            add_enterprise_aes: Explicit enterprise AEs to add
            add_midmarket_aes: Explicit mid-market AEs to add
            add_ses: Explicit SEs to add (overrides auto-derive)
            add_sdrs: Explicit SDRs to add (overrides auto-derive)

        Returns:
            New OrgPlan with flexed team
        """
        if base_plan.current_team is None:
            raise ValueError("Base plan must have current_team")

        # Calculate total AEs to add
        if add_aes > 0:
            # Split by enterprise_pct
            add_enterprise_aes = int(round(add_aes * self.enterprise_pct))
            add_midmarket_aes = add_aes - add_enterprise_aes

        total_new_aes = add_enterprise_aes + add_midmarket_aes

        if total_new_aes == 0 and add_ses == 0 and add_sdrs == 0:
            return base_plan  # No changes

        # Calculate new team
        new_total_aes = base_plan.current_team.total_aes + total_new_aes
        new_ent_aes = base_plan.current_team.aes_enterprise + add_enterprise_aes
        new_mm_aes = base_plan.current_team.aes_midmarket + add_midmarket_aes

        # Derive support roles from new AE count
        new_target = derive_team_from_segments(
            aes_enterprise=new_ent_aes,
            aes_midmarket=new_mm_aes,
            ratios=self.ratios,
        )

        # Override explicit additions
        if add_ses > 0:
            new_target.ses = base_plan.current_team.ses + add_ses
        if add_sdrs > 0:
            new_target.sdrs = base_plan.current_team.sdrs + add_sdrs

        # Calculate team delta
        team_delta = DerivedTeam(
            aes_enterprise=new_target.aes_enterprise - base_plan.current_team.aes_enterprise,
            aes_midmarket=new_target.aes_midmarket - base_plan.current_team.aes_midmarket,
            ses=new_target.ses - base_plan.current_team.ses,
            sdrs=new_target.sdrs - base_plan.current_team.sdrs,
            csms=new_target.csms - base_plan.current_team.csms,
            fdes=new_target.fdes - base_plan.current_team.fdes,
            ae_managers_enterprise=new_target.ae_managers_enterprise - base_plan.current_team.ae_managers_enterprise,
            ae_managers_midmarket=new_target.ae_managers_midmarket - base_plan.current_team.ae_managers_midmarket,
            se_managers=new_target.se_managers - base_plan.current_team.se_managers,
            sdr_managers=new_target.sdr_managers - base_plan.current_team.sdr_managers,
            csm_managers=new_target.csm_managers - base_plan.current_team.csm_managers,
            enterprise_pct=self.enterprise_pct,
            midmarket_pct=1.0 - self.enterprise_pct,
        )

        # Generate new hiring plan
        hiring_plan = generate_hiring_plan(
            current_team=base_plan.current_team,
            target_team=new_target,
            start_month=base_plan.start_month or date.today().replace(day=1),
            end_month=base_plan.end_month or (date.today().replace(day=1) + relativedelta(months=11)),
            pace=HiringPace.EVEN,
        )

        # Calculate new costs
        target_cost = calculate_org_cost_from_team(
            team=new_target,
            costs=self.costs,
            period_months=base_plan.period_months,
        )

        # Calculate segment capacity
        segment_capacity = calculate_segment_capacity(
            aes_enterprise=new_ent_aes,
            aes_commercial=new_mm_aes,
            months=base_plan.period_months,
        )

        # Calculate new achievable ARR using segment productivity
        ramp_adjustment = 0.75
        ent_capacity = self.enterprise_productivity.effective_annual_capacity * (base_plan.period_months / 12)
        comm_capacity = self.commercial_productivity.effective_annual_capacity * (base_plan.period_months / 12)

        sales_led_arr = (
            (new_ent_aes * ent_capacity * ramp_adjustment) +
            (new_mm_aes * comm_capacity * ramp_adjustment)
        )

        # Add self-serve contribution if applicable
        self_serve_arr = base_plan.self_serve_arr if base_plan.self_serve_arr else 0.0
        achievable_arr = sales_led_arr + self_serve_arr

        return OrgPlan(
            period=f"{base_plan.period} (flexed +{total_new_aes} AEs)",
            period_months=base_plan.period_months,
            start_month=base_plan.start_month,
            end_month=base_plan.end_month,
            current_team=base_plan.current_team,
            target_team=new_target,
            team_delta=team_delta,
            hiring_plan=hiring_plan,
            current_cost=base_plan.current_cost,
            target_cost=target_cost,
            arr_target=base_plan.arr_target,
            achievable_arr=achievable_arr,
            coverage_ratios=self.ratios,
            role_costs=self.costs,
            segment_capacity=segment_capacity,
            enterprise_productivity=self.enterprise_productivity,
            commercial_productivity=self.commercial_productivity,
            self_serve_stream=self.self_serve_stream,
            self_serve_arr=self_serve_arr,
            warnings=[f"Flexed scenario: +{total_new_aes} AEs from base plan"],
        )

    def compare_scenarios(
        self,
        scenarios: dict[str, OrgPlan],
    ) -> dict:
        """
        Compare multiple org planning scenarios.

        Args:
            scenarios: Dict of scenario name → OrgPlan

        Returns:
            Comparison dict with key metrics side-by-side
        """
        comparison = {
            "scenarios": {},
            "summary": {},
        }

        for name, plan in scenarios.items():
            comparison["scenarios"][name] = {
                "target_aes": plan.target_team.total_aes if plan.target_team else 0,
                "total_headcount": plan.target_team.total_headcount if plan.target_team else 0,
                "new_hires": plan.total_new_hires,
                "total_cost": plan.target_cost.total_cost if plan.target_cost else 0,
                "achievable_arr": plan.achievable_arr,
                "gap": plan.gap,
                "gap_pct": plan.gap_pct,
            }

        # Summary metrics
        if scenarios:
            comparison["summary"] = {
                "min_cost": min(s["total_cost"] for s in comparison["scenarios"].values()),
                "max_cost": max(s["total_cost"] for s in comparison["scenarios"].values()),
                "min_achievable": min(s["achievable_arr"] for s in comparison["scenarios"].values()),
                "max_achievable": max(s["achievable_arr"] for s in comparison["scenarios"].values()),
            }

        return comparison


def quick_derive_team(ae_count: int, enterprise_pct: float = 0.5) -> DerivedTeam:
    """
    Quick helper to derive team from AE count.

    Args:
        ae_count: Total AEs
        enterprise_pct: Enterprise segment percentage

    Returns:
        DerivedTeam with full headcount
    """
    return derive_team(ae_count=ae_count, enterprise_pct=enterprise_pct)


def quick_org_cost(
    ae_count: int,
    enterprise_pct: float = 0.5,
    period_months: int = 12,
) -> OrgCost:
    """
    Quick helper to calculate org cost from AE count.

    Args:
        ae_count: Total AEs
        enterprise_pct: Enterprise segment percentage
        period_months: Period length

    Returns:
        OrgCost with full cost breakdown
    """
    team = derive_team(ae_count=ae_count, enterprise_pct=enterprise_pct)
    return calculate_org_cost_from_team(team=team, period_months=period_months)

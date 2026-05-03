"""
Scenario planning for the GTM model.

Run what-if analyses by modifying assumptions and comparing outcomes.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
from copy import deepcopy

from .funnel import FunnelAssumptions, FunnelRequirements, reverse_funnel
from .capacity import RepCapacity, TeamCapacity, Segment, calculate_quarterly_capacity
from .waterfall import (
    ARRWaterfall,
    RetentionAssumptions,
    calculate_waterfall,
    project_arr_timeline,
)


@dataclass
class Scenario:
    """
    A named scenario with modified assumptions.

    Used for what-if analysis: "What if conversion rates improve by 10%?"
    """

    name: str
    description: str = ""

    # Assumption overrides (None means use default)
    funnel_assumptions: Optional[FunnelAssumptions] = None
    retention_assumptions: Optional[RetentionAssumptions] = None

    # Target overrides
    bookings_target: Optional[float] = None
    beginning_arr: Optional[float] = None

    # Results (populated after running)
    funnel_requirements: Optional[FunnelRequirements] = None
    waterfall: Optional[ARRWaterfall] = None

    def with_funnel_change(self, **kwargs) -> "Scenario":
        """
        Create a new scenario with modified funnel assumptions.

        Args:
            **kwargs: FunnelAssumptions fields to override

        Returns:
            New Scenario with modified assumptions
        """
        new_scenario = deepcopy(self)

        if new_scenario.funnel_assumptions is None:
            new_scenario.funnel_assumptions = FunnelAssumptions(**kwargs)
        else:
            for key, value in kwargs.items():
                setattr(new_scenario.funnel_assumptions, key, value)

        return new_scenario

    def with_retention_change(self, **kwargs) -> "Scenario":
        """
        Create a new scenario with modified retention assumptions.

        Args:
            **kwargs: RetentionAssumptions fields to override

        Returns:
            New Scenario with modified assumptions
        """
        new_scenario = deepcopy(self)

        if new_scenario.retention_assumptions is None:
            new_scenario.retention_assumptions = RetentionAssumptions(**kwargs)
        else:
            for key, value in kwargs.items():
                setattr(new_scenario.retention_assumptions, key, value)

        return new_scenario


@dataclass
class ScenarioResult:
    """Results from running a scenario."""

    scenario: Scenario
    funnel_requirements: FunnelRequirements
    waterfall: Optional[ARRWaterfall] = None
    team_capacity: Optional[TeamCapacity] = None

    # Key metrics for comparison
    required_mqls: int = field(init=False)
    required_pipeline: float = field(init=False)
    ending_arr: float = field(init=False)
    net_new_arr: float = field(init=False)

    def __post_init__(self):
        """Extract key metrics."""
        self.required_mqls = self.funnel_requirements.required_mqls
        self.required_pipeline = self.funnel_requirements.pipeline_s2

        if self.waterfall:
            self.ending_arr = self.waterfall.ending_arr
            self.net_new_arr = self.waterfall.net_new_arr
        else:
            self.ending_arr = 0
            self.net_new_arr = 0


def run_scenario(
    scenario: Scenario,
    bookings_target: float = 6_000_000,
    beginning_arr: float = 22_000_000,
    period: str = "Q1FY26",
) -> ScenarioResult:
    """
    Run a scenario and calculate results.

    Args:
        scenario: Scenario to run
        bookings_target: Target bookings (overridden by scenario if set)
        beginning_arr: Beginning ARR for waterfall (overridden by scenario if set)
        period: Period label for waterfall

    Returns:
        ScenarioResult with all calculated metrics
    """
    # Use scenario overrides if provided
    target = scenario.bookings_target or bookings_target
    start_arr = scenario.beginning_arr or beginning_arr

    # Run funnel calculation
    funnel_req = reverse_funnel(
        bookings_target=target,
        assumptions=scenario.funnel_assumptions,
    )

    # Run waterfall calculation
    waterfall = calculate_waterfall(
        period=period,
        beginning_arr=start_arr,
        new_business_arr=target,  # Assuming we hit target
        assumptions=scenario.retention_assumptions,
    )

    return ScenarioResult(
        scenario=scenario,
        funnel_requirements=funnel_req,
        waterfall=waterfall,
    )


@dataclass
class ScenarioComparison:
    """Comparison of multiple scenarios."""

    baseline: ScenarioResult
    scenarios: list[ScenarioResult]

    def summary_table(self) -> str:
        """Generate a comparison table."""
        rows = []

        # Header
        header = f"{'Scenario':<25} {'MQLs':>10} {'Pipeline':>15} {'Ending ARR':>15} {'Net New':>12}"
        rows.append(header)
        rows.append("-" * len(header))

        # Baseline
        b = self.baseline
        rows.append(
            f"{'Baseline':<25} {b.required_mqls:>10,} ${b.required_pipeline:>13,.0f} ${b.ending_arr:>13,.0f} ${b.net_new_arr:>10,.0f}"
        )

        # Each scenario
        for result in self.scenarios:
            name = result.scenario.name[:24]
            mql_delta = result.required_mqls - b.required_mqls
            mql_pct = mql_delta / b.required_mqls * 100 if b.required_mqls > 0 else 0

            rows.append(
                f"{name:<25} {result.required_mqls:>10,} ${result.required_pipeline:>13,.0f} ${result.ending_arr:>13,.0f} ${result.net_new_arr:>10,.0f}"
            )
            rows.append(
                f"  {'vs baseline':<23} {mql_delta:>+10,} ({mql_pct:>+.1f}%)"
            )

        return "\n".join(rows)


def compare_scenarios(
    scenarios: list[Scenario],
    bookings_target: float = 6_000_000,
    beginning_arr: float = 22_000_000,
) -> ScenarioComparison:
    """
    Compare multiple scenarios against baseline.

    The first scenario is treated as baseline.

    Args:
        scenarios: List of scenarios (first is baseline)
        bookings_target: Target bookings
        beginning_arr: Beginning ARR

    Returns:
        ScenarioComparison with all results
    """
    if not scenarios:
        raise ValueError("At least one scenario required")

    results = []
    for scenario in scenarios:
        result = run_scenario(
            scenario,
            bookings_target=bookings_target,
            beginning_arr=beginning_arr,
        )
        results.append(result)

    return ScenarioComparison(
        baseline=results[0],
        scenarios=results[1:],
    )


# Pre-built scenarios for common what-if analyses
def create_standard_scenarios() -> list[Scenario]:
    """
    Create standard scenarios for common analyses.

    Returns:
        List of pre-configured scenarios
    """
    return [
        Scenario(
            name="Baseline",
            description="Current assumptions from typical B2B SaaS distributions",
        ),
        Scenario(
            name="Improved S1→S2 (+10%)",
            description="What if we improve discovery to scope conversion?",
            funnel_assumptions=FunnelAssumptions(s1_to_s2=0.35),  # 25% → 35%
        ),
        Scenario(
            name="Higher ACV ($350K)",
            description="What if average deal size increases?",
            funnel_assumptions=FunnelAssumptions(avg_acv=350_000),
        ),
        Scenario(
            name="More Marketing MQLs",
            description="What if marketing contributes 30% of pipeline?",
            funnel_assumptions=FunnelAssumptions(
                source_mix_ae=0.50,
                source_mix_sdr=0.20,
                source_mix_marketing=0.30,
            ),
        ),
        Scenario(
            name="Better Retention (95% GDR)",
            description="What if we reduce churn?",
            retention_assumptions=RetentionAssumptions(
                gross_dollar_retention=0.95,
                voluntary_churn_rate=0.03,
                involuntary_churn_rate=0.01,
                contraction_rate=0.01,
            ),
        ),
        Scenario(
            name="High Expansion (20%)",
            description="What if expansion rate increases?",
            retention_assumptions=RetentionAssumptions(expansion_rate=0.20),
        ),
    ]


def sensitivity_analysis(
    parameter: str,
    values: list[float],
    bookings_target: float = 6_000_000,
) -> list[tuple[float, ScenarioResult]]:
    """
    Run sensitivity analysis on a single parameter.

    Args:
        parameter: Name of parameter to vary (e.g., "s1_to_s2", "avg_acv")
        values: List of values to test
        bookings_target: Target bookings

    Returns:
        List of (value, result) tuples
    """
    results = []

    for value in values:
        # Determine if funnel or retention parameter
        funnel_params = [
            "avg_acv", "mql_to_s0", "s0_to_s1", "s1_to_s2",
            "s2_to_s3", "s3_to_s4", "s4_to_s5", "s5_to_won",
            "source_mix_ae", "source_mix_sdr", "source_mix_marketing",
        ]

        if parameter in funnel_params:
            scenario = Scenario(
                name=f"{parameter}={value}",
                funnel_assumptions=FunnelAssumptions(**{parameter: value}),
            )
        else:
            scenario = Scenario(
                name=f"{parameter}={value}",
                retention_assumptions=RetentionAssumptions(**{parameter: value}),
            )

        result = run_scenario(scenario, bookings_target=bookings_target)
        results.append((value, result))

    return results


def what_if_close_rate_improves(
    improvement_pct: float = 0.10,
    bookings_target: float = 6_000_000,
) -> dict:
    """
    What if close rates improve across all stages?

    Args:
        improvement_pct: Percentage improvement (0.10 = 10% better)
        bookings_target: Target bookings

    Returns:
        Dict with baseline and improved scenario results
    """
    baseline_assumptions = FunnelAssumptions()

    improved_assumptions = FunnelAssumptions(
        s0_to_s1=min(1.0, baseline_assumptions.s0_to_s1 * (1 + improvement_pct)),
        s1_to_s2=min(1.0, baseline_assumptions.s1_to_s2 * (1 + improvement_pct)),
        s2_to_s3=min(1.0, baseline_assumptions.s2_to_s3 * (1 + improvement_pct)),
        s3_to_s4=min(1.0, baseline_assumptions.s3_to_s4 * (1 + improvement_pct)),
        s4_to_s5=min(1.0, baseline_assumptions.s4_to_s5 * (1 + improvement_pct)),
        s5_to_won=min(1.0, baseline_assumptions.s5_to_won * (1 + improvement_pct)),
    )

    baseline = reverse_funnel(bookings_target, baseline_assumptions)
    improved = reverse_funnel(bookings_target, improved_assumptions)

    mql_reduction = baseline.required_mqls - improved.required_mqls
    mql_reduction_pct = mql_reduction / baseline.required_mqls * 100

    return {
        "baseline_mqls": baseline.required_mqls,
        "improved_mqls": improved.required_mqls,
        "mql_reduction": mql_reduction,
        "mql_reduction_pct": mql_reduction_pct,
        "baseline_s2_to_won": baseline_assumptions.s2_to_won,
        "improved_s2_to_won": improved_assumptions.s2_to_won,
    }


def goal_seek_conversion_rate(
    target_mqls: int,
    stage: str = "s1_to_s2",
    bookings_target: float = 6_000_000,
) -> float:
    """
    Find the conversion rate needed to achieve a target MQL count.

    Args:
        target_mqls: Desired number of MQLs
        stage: Which stage conversion to adjust
        bookings_target: Target bookings

    Returns:
        Required conversion rate (0.0 to 1.0)
    """
    low, high = 0.01, 0.99
    tolerance = 10  # Within 10 MQLs

    for _ in range(50):
        mid = (low + high) / 2
        assumptions = FunnelAssumptions(**{stage: mid})
        result = reverse_funnel(bookings_target, assumptions)

        if abs(result.required_mqls - target_mqls) < tolerance:
            return mid
        elif result.required_mqls > target_mqls:
            low = mid  # Need higher conversion
        else:
            high = mid  # Need lower conversion

    return (low + high) / 2

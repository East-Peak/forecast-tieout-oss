"""Gap-closing recommendation helpers for Planning Tie-Out."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def format_money(value: float) -> str:
    """Format as currency with M/K suffix.

    Negative values display as -$3.9M (not $-3.9M).
    """
    if value is None:
        return "$0"
    negative = value < 0
    abs_val = abs(float(value))
    if abs_val >= 999_500:  # Round up to M at boundary
        formatted = f"${abs_val / 1_000_000:.1f}M"
    elif abs_val >= 1_000:
        formatted = f"${abs_val / 1_000:.1f}K"
    elif abs_val > 0:
        formatted = f"${abs_val:,.0f}"
    else:
        return "$0"
    return f"-{formatted}" if negative else formatted


@dataclass
class TieoutRecommendationsAnalyzer:
    """Analyze the FY gap and recommend prioritized closing actions."""

    compute_base: Callable[[str], Any]
    flex_scenario: Callable[..., Any]
    get_s2_to_won_rate: Callable[[], float]
    available_plan_cases: Callable[[], list[dict]]
    get_plan_case_id: Callable[[], Optional[str]]
    default_plan_case_id: Callable[[], str]
    tieout_factory: Callable[[str], Any]

    def analyze(
        self,
        base: Optional[Any] = None,
        overflow_mode: str = "push",
    ) -> dict:
        """Return structured recommendations for closing the FY gap."""
        if base is None:
            base = self.compute_base(overflow_mode=overflow_mode)

        fy_gap = base.fy_sales_led_gap
        fy_gap_pct = base.fy_sales_led_gap_pct
        if fy_gap <= 0:
            return {
                "gap": fy_gap,
                "gap_pct": fy_gap_pct,
                "executive_context_gap": base.fy_gap,
                "executive_context_gap_pct": base.fy_gap_pct,
                "comparison_metric": "sales_led_arr",
                "constraints": [],
                "levers": [],
                "narrative": "Trajectory meets or exceeds the selected plan's sales-led target.",
            }

        constraints = self._build_constraints(base)
        levers, context = self._build_levers(base, fy_gap, overflow_mode)

        levers.append({
            "lever": "Revise top-down targets",
            "category": "planning",
            "description": (
                f"Current machine supports ~{format_money(base.fy_bookings_bu)} "
                f"against a {format_money(base.fy_bookings_td)} sales-led plan. "
                f"If hiring and pipeline improvements can close "
                f"~{sum(l['closes_pct'] for l in levers):.0%} "
                f"of the gap, the remainder requires revised expectations."
            ),
            "realistic_lift": 0,
            "closes_pct": 0,
            "feasibility": "high",
            "action": "Present the board a revised operating plan with realistic hiring and pipeline assumptions.",
        })

        levers.sort(
            key=lambda item: (
                0 if item["lever"] == "Revise top-down targets" else 1,
                float(item.get("realistic_lift", 0) or 0),
            ),
            reverse=True,
        )

        total_addressable = sum(lever["realistic_lift"] for lever in levers)
        combined_close_pct = total_addressable / fy_gap if fy_gap > 0 else 0
        narrative = self._build_narrative(
            base=base,
            fy_gap=fy_gap,
            levers=levers,
            total_addressable=total_addressable,
            combined_close_pct=combined_close_pct,
            avg_plan_aes=context["avg_plan_aes"],
            avg_roster_aes=context["avg_roster_aes"],
            operating_draft_lever=context["operating_draft_lever"],
        )

        return {
            "gap": fy_gap,
            "gap_pct": fy_gap_pct,
            "executive_context_gap": base.fy_gap,
            "executive_context_gap_pct": base.fy_gap_pct,
            "comparison_metric": "sales_led_arr",
            "primary_constraint": narrative["primary_constraint"],
            "constraints": constraints,
            "levers": levers,
            "total_addressable": total_addressable,
            "combined_close_pct": combined_close_pct,
            "remaining_gap": max(fy_gap - total_addressable, 0),
            "narrative": narrative["text"],
        }

    @staticmethod
    def _build_constraints(base: Any) -> list[dict]:
        """Identify the main structural constraints in the model output."""
        constraints: list[dict] = []

        for quarter in base.quarters:
            if quarter.td_aes > 0 and quarter.bu_total_aes < quarter.td_aes:
                constraints.append({
                    "type": "hiring",
                    "quarter": quarter.quarter,
                    "current": quarter.bu_total_aes,
                    "planned": quarter.td_aes,
                    "gap": quarter.td_aes - quarter.bu_total_aes,
                    "message": (
                        f"{quarter.quarter}: {quarter.bu_total_aes} AEs in roster vs "
                        f"{quarter.td_aes} in plan ({quarter.td_aes - quarter.bu_total_aes} gap)"
                    ),
                })

        cap_bound_months = 0
        for expected, cap_row in zip(base.monthly_total_expected_wins, base.monthly_capacity):
            cap_val = getattr(cap_row, "ae_capacity", 0)
            if cap_val > 0 and expected > cap_val * 1.05:
                cap_bound_months += 1
        if cap_bound_months > 0:
            constraints.append({
                "type": "capacity_ceiling",
                "months_bound": cap_bound_months,
                "message": (
                    f"{cap_bound_months} of 12 months are capacity-constrained "
                    f"(expected wins exceed AE close capacity)."
                ),
            })

        total_pipeline_created = sum(base.monthly_pipeline_creation)
        total_pipeline_target = sum(quarter.td_pipeline_target for quarter in base.quarters)
        if total_pipeline_target > 0:
            pipeline_coverage = total_pipeline_created / total_pipeline_target
            if pipeline_coverage < 0.80:
                constraints.append({
                    "type": "pipeline_volume",
                    "created": total_pipeline_created,
                    "target": total_pipeline_target,
                    "coverage": pipeline_coverage,
                    "message": (
                        f"Modeled pipeline creation is {format_money(total_pipeline_created)} "
                        f"vs {format_money(total_pipeline_target)} target "
                        f"({pipeline_coverage:.0%} coverage)."
                    ),
                })

        return constraints

    def _build_levers(
        self,
        base: Any,
        fy_gap: float,
        overflow_mode: str,
    ) -> tuple[list[dict], dict]:
        """Build lever recommendations and shared narrative context."""
        levers: list[dict] = []
        avg_plan_aes = int(sum(q.td_aes for q in base.quarters) / max(len(base.quarters), 1))
        avg_roster_aes = int(sum(q.bu_total_aes for q in base.quarters) / max(len(base.quarters), 1))
        ae_gap = avg_plan_aes - avg_roster_aes

        per_quarter_hiring = []
        for quarter in base.quarters:
            q_gap = max(quarter.td_aes - quarter.bu_total_aes, 0)
            if q_gap > 0:
                per_quarter_hiring.append({
                    "quarter": quarter.quarter,
                    "roster_aes": quarter.bu_total_aes,
                    "plan_aes": quarter.td_aes,
                    "hires_needed": q_gap,
                })

        if ae_gap > 0:
            hire_to_plan = self.flex_scenario(
                name="Hire to plan",
                total_aes=avg_plan_aes,
                overflow_mode=overflow_mode,
            )
            hiring_lift = hire_to_plan.fy_bookings_bu - base.fy_bookings_bu
            timeline_str = ", ".join(
                f"{item['hires_needed']} in {item['quarter']}" for item in per_quarter_hiring
            ) or f"{ae_gap} AEs"

            levers.append({
                "lever": "Hire to plan headcount",
                "category": "capacity",
                "description": (
                    f"Hire to plan: {timeline_str}. "
                    f"Roster averages {avg_roster_aes} AEs vs plan of {avg_plan_aes}. "
                    f"Adds {format_money(max(hiring_lift, 0))} to FY BU "
                    f"(ramp-adjusted; new hires contribute at reduced capacity "
                    f"for first 6 months)."
                ),
                "realistic_lift": max(hiring_lift, 0),
                "closes_pct": max(hiring_lift, 0) / fy_gap if fy_gap > 0 else 0,
                "feasibility": "high" if ae_gap <= 10 else "medium" if ae_gap <= 20 else "low",
                "action": (
                    f"Hire {ae_gap} additional AEs: {timeline_str}. "
                    f"See roster.yaml planned section for staggered start dates."
                ),
                "per_quarter_hiring": per_quarter_hiring,
                "timeline": timeline_str,
            })

        full_ramp = self.flex_scenario(
            name="Full ramp",
            total_aes=max(avg_roster_aes + 3, avg_roster_aes),
            overflow_mode=overflow_mode,
        )
        ramp_lift = full_ramp.fy_bookings_bu - base.fy_bookings_bu
        if ramp_lift > 0:
            levers.append({
                "lever": "Accelerate AE ramp",
                "category": "enablement",
                "description": (
                    f"Get incoming/ramping AEs to full productivity faster. "
                    f"Adds ~{format_money(ramp_lift)} to FY BU."
                ),
                "realistic_lift": ramp_lift,
                "closes_pct": ramp_lift / fy_gap if fy_gap > 0 else 0,
                "feasibility": "high",
                "action": "Invest in onboarding, enablement, deal support for ramping reps.",
            })

        base_s2_won = self.get_s2_to_won_rate()
        improved_s2_won = min(base_s2_won * 1.50, 0.30)
        if improved_s2_won > base_s2_won:
            total_future_gen_wins = sum(base.monthly_future_generation_wins)
            win_rate_lift = total_future_gen_wins * (improved_s2_won / base_s2_won - 1)
            levers.append({
                "lever": "Improve pipeline win rate",
                "category": "sales_execution",
                "description": (
                    f"Improve S2→Won from {base_s2_won:.1%} to {improved_s2_won:.1%}. "
                    f"Adds ~{format_money(max(win_rate_lift, 0))} from existing pipeline."
                ),
                "realistic_lift": max(win_rate_lift, 0),
                "closes_pct": max(win_rate_lift, 0) / fy_gap if fy_gap > 0 else 0,
                "feasibility": "medium",
                "action": (
                    "Better discovery, solution engineering, deal qualification. "
                    "Focus on S2→S3 advancement and competitive win rate."
                ),
            })

        operating_draft_lever = self._build_operating_draft_lever(
            base=base,
            fy_gap=fy_gap,
            overflow_mode=overflow_mode,
        )
        if operating_draft_lever:
            levers.append(operating_draft_lever)

        return levers, {
            "avg_plan_aes": avg_plan_aes,
            "avg_roster_aes": avg_roster_aes,
            "operating_draft_lever": operating_draft_lever,
        }

    def _build_operating_draft_lever(
        self,
        base: Any,
        fy_gap: float,
        overflow_mode: str,
    ) -> Optional[dict]:
        """Estimate how much of the gap a lower target plan case closes."""
        current_plan = self.get_plan_case_id() or self.default_plan_case_id()
        available_cases = {case.get("plan_id"): case for case in self.available_plan_cases()}
        # Find a lower-target draft plan case to compare against
        draft_plan_id = None
        for case_id, case_meta in available_cases.items():
            if case_id != current_plan and case_meta.get("status") == "operating_draft":
                draft_plan_id = case_id
                break
        if draft_plan_id is None:
            return None

        try:
            draft_tieout = self.tieout_factory(draft_plan_id)
            compute_archived_plan = getattr(draft_tieout, "compute_archived_plan", None)
            if callable(compute_archived_plan):
                draft_base = compute_archived_plan(overflow_mode=overflow_mode)
            else:
                draft_base = draft_tieout.compute(overflow_mode=overflow_mode)
            draft_gap = draft_base.fy_sales_led_gap
            draft_gap_reduction = max(fy_gap - max(draft_gap, 0), 0)
            draft_label = available_cases[draft_plan_id].get("label", "Operating Draft")
            if draft_gap_reduction <= 0:
                return None

            return {
                "lever": "Switch to operating draft targets",
                "category": "planning",
                "description": (
                    f"Adopt \"{draft_label}\" targets. "
                    f"Reduces the sales-led target from {format_money(base.fy_bookings_td)} "
                    f"to {format_money(draft_base.fy_bookings_td)}, "
                    f"shrinking the gap by {format_money(draft_gap_reduction)} "
                    f"({draft_gap_reduction / fy_gap:.0%} of current gap). "
                    f"Remaining gap under draft: {format_money(max(draft_gap, 0))}."
                ),
                "realistic_lift": draft_gap_reduction,
                "closes_pct": draft_gap_reduction / fy_gap if fy_gap > 0 else 0,
                "feasibility": "high",
                "action": (
                    "Present the operating draft to the board: slower hiring, "
                    "lower sales-led targets, leaning into hybrid/PLG execution."
                ),
                "draft_plan_id": draft_plan_id,
                "draft_fy_target": draft_base.fy_bookings_td,
                "draft_fy_bu": draft_base.fy_bookings_bu,
                "draft_gap": max(draft_gap, 0),
            }
        except Exception as exc:
            logger.warning("Operating draft lever computation failed: %s", exc)
            return None

    @staticmethod
    def _build_narrative(
        base: Any,
        fy_gap: float,
        levers: list[dict],
        total_addressable: float,
        combined_close_pct: float,
        avg_plan_aes: int,
        avg_roster_aes: int,
        operating_draft_lever: Optional[dict],
    ) -> dict:
        """Build the high-level narrative and primary constraint label."""
        hiring_levers = [
            lever for lever in levers
            if lever["category"] == "capacity" and lever["realistic_lift"] > 0
        ]
        if operating_draft_lever and operating_draft_lever["closes_pct"] > 0.50:
            primary_constraint = "plan_ambition"
            narrative_lead = (
                f"The board-plan targets may be over-ambitious. "
                f"Switching to the operating draft closes "
                f"{operating_draft_lever['closes_pct']:.0%} of the gap "
                f"({format_money(operating_draft_lever['realistic_lift'])}). "
                f"The remaining {format_money(operating_draft_lever.get('draft_gap', 0))} "
                f"gap under the draft is addressable through hiring and execution."
            )
        elif hiring_levers and hiring_levers[0]["realistic_lift"] > fy_gap * 0.3:
            primary_constraint = "hiring"
            narrative_lead = (
                f"The primary constraint is headcount. The roster has {avg_roster_aes} AEs "
                f"against a plan of {avg_plan_aes}. Closing the hiring gap is the "
                f"highest-leverage action ({format_money(hiring_levers[0]['realistic_lift'])} impact)."
            )
        else:
            primary_constraint = "pipeline"
            narrative_lead = (
                f"The gap is structural. Even hiring to plan, the model shows "
                f"pipeline creation and win rates producing well below target. "
                f"A combination of hiring, execution improvements, and likely "
                f"target revision is needed."
            )

        return {
            "primary_constraint": primary_constraint,
            "text": (
                f"FY sales-led gap: {format_money(fy_gap)} ({base.fy_sales_led_gap_pct:.0%}). "
                f"{narrative_lead} "
                f"All levers combined address ~{combined_close_pct:.0%} "
                f"({format_money(total_addressable)}) of the gap."
            ),
        }

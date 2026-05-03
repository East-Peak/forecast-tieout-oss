"""
ARR Waterfall and Net Dollar Retention (NDR) Module.

Tracks ARR movements through the customer lifecycle:
- New Logo ARR
- Expansion ARR (upsells, cross-sells, price increases)
- Contraction ARR (downgrades, partial churn)
- Churned ARR (full logo loss)
- Renewed ARR (flat renewals)

Calculates key retention metrics:
- GRR (Gross Retention Rate) - retention excluding expansion
- NRR (Net Dollar Retention) - retention including expansion
- Logo Retention Rate
- Expansion Rate

Example usage:
    from gtm_model.arr_waterfall import (
        ARRWaterfallPeriod,
        CohortRetention,
        calculate_ndr,
        calculate_grr,
        build_arr_waterfall,
    )

    # Calculate NDR from renewal data
    ndr = calculate_ndr(
        beginning_arr=10_000_000,
        expansion_arr=1_500_000,
        contraction_arr=300_000,
        churned_arr=500_000,
    )
    print(f"NDR: {ndr:.1%}")  # 107.0%

    # Build full waterfall
    waterfall = build_arr_waterfall(opportunities, period="Q1FY26")
    print(waterfall.summary())
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List, Dict
from enum import Enum
import math


class ARRMovementType(Enum):
    """Types of ARR movements."""
    NEW_LOGO = "new_logo"
    EXPANSION = "expansion"
    CONTRACTION = "contraction"
    CHURN = "churn"
    RENEWAL = "renewal"  # Flat renewal (no expansion/contraction)


@dataclass
class ARRMovement:
    """Individual ARR movement event."""
    account_id: str
    account_name: str
    opportunity_id: Optional[str] = None
    movement_type: ARRMovementType = ARRMovementType.NEW_LOGO
    arr_amount: float = 0.0
    previous_arr: float = 0.0  # For renewals/expansions
    close_date: Optional[date] = None
    segment: str = "unknown"  # enterprise, commercial, smb

    @property
    def net_arr_change(self) -> float:
        """Net ARR change (positive for growth, negative for loss)."""
        if self.movement_type == ARRMovementType.NEW_LOGO:
            return self.arr_amount
        elif self.movement_type == ARRMovementType.EXPANSION:
            return self.arr_amount  # Already the delta
        elif self.movement_type == ARRMovementType.CONTRACTION:
            return -self.arr_amount  # Negative
        elif self.movement_type == ARRMovementType.CHURN:
            return -self.arr_amount  # Full loss
        else:  # RENEWAL
            return 0.0  # Flat


@dataclass
class ARRWaterfallPeriod:
    """
    ARR waterfall for a specific period.

    Tracks all ARR movements and calculates retention metrics.
    """
    period: str = ""  # e.g., "Q1FY26", "FY26"
    period_start: Optional[date] = None
    period_end: Optional[date] = None

    # Beginning state
    beginning_arr: float = 0.0
    beginning_logos: int = 0

    # Movements
    new_logo_arr: float = 0.0
    new_logos: int = 0

    expansion_arr: float = 0.0
    expansions: int = 0

    contraction_arr: float = 0.0
    contractions: int = 0

    churned_arr: float = 0.0
    churned_logos: int = 0

    renewed_arr: float = 0.0  # ARR that renewed flat (no change)
    renewals: int = 0

    # Ending state (calculated)
    ending_arr: float = 0.0
    ending_logos: int = 0

    # Detailed movements
    movements: List[ARRMovement] = field(default_factory=list)

    # Segment breakdown
    by_segment: Dict[str, dict] = field(default_factory=dict)

    def __post_init__(self):
        """Calculate derived fields."""
        self._calculate_ending_state()
        self._calculate_metrics()

    def _calculate_ending_state(self):
        """Calculate ending ARR and logos."""
        self.ending_arr = (
            self.beginning_arr
            + self.new_logo_arr
            + self.expansion_arr
            - self.contraction_arr
            - self.churned_arr
        )
        self.ending_logos = (
            self.beginning_logos
            + self.new_logos
            - self.churned_logos
        )

    def _calculate_metrics(self):
        """Calculate retention metrics."""
        # These are calculated as properties, but we can cache them
        pass

    @property
    def gross_arr_adds(self) -> float:
        """Total gross ARR added (new + expansion)."""
        return self.new_logo_arr + self.expansion_arr

    @property
    def gross_arr_loss(self) -> float:
        """Total gross ARR lost (contraction + churn)."""
        return self.contraction_arr + self.churned_arr

    @property
    def net_arr_change(self) -> float:
        """Net ARR change for the period."""
        return self.ending_arr - self.beginning_arr

    @property
    def arr_subject_to_renewal(self) -> float:
        """ARR that came up for renewal (renewed + contracted + churned)."""
        return self.renewed_arr + self.contraction_arr + self.churned_arr + self.expansion_arr

    @property
    def grr(self) -> float:
        """
        Gross Retention Rate.

        Measures retention excluding expansion.
        GRR = (Renewed ARR + Contracted ARR) / ARR Subject to Renewal

        Note: Contracted ARR is the amount retained after contraction,
        not the contraction amount itself.
        """
        if self.arr_subject_to_renewal <= 0:
            return 1.0

        # Retained ARR = total that renewed minus what was lost
        retained_arr = self.arr_subject_to_renewal - self.churned_arr - self.contraction_arr
        return retained_arr / self.arr_subject_to_renewal

    @property
    def nrr(self) -> float:
        """
        Net Revenue Retention (Net Dollar Retention).

        Measures retention including expansion.
        NRR = (Renewed ARR + Expansion ARR) / ARR Subject to Renewal
        """
        if self.arr_subject_to_renewal <= 0:
            return 1.0

        # Net retained = retained + expansion
        retained_arr = self.arr_subject_to_renewal - self.churned_arr - self.contraction_arr
        net_retained = retained_arr + self.expansion_arr
        return net_retained / self.arr_subject_to_renewal

    @property
    def logo_retention_rate(self) -> float:
        """Logo retention rate."""
        if self.beginning_logos <= 0:
            return 1.0
        return 1 - (self.churned_logos / self.beginning_logos)

    @property
    def expansion_rate(self) -> float:
        """Expansion rate as % of beginning ARR."""
        if self.beginning_arr <= 0:
            return 0.0
        return self.expansion_arr / self.beginning_arr

    @property
    def contraction_rate(self) -> float:
        """Contraction rate as % of beginning ARR."""
        if self.beginning_arr <= 0:
            return 0.0
        return self.contraction_arr / self.beginning_arr

    @property
    def churn_rate(self) -> float:
        """Churn rate as % of beginning ARR."""
        if self.beginning_arr <= 0:
            return 0.0
        return self.churned_arr / self.beginning_arr

    @property
    def net_growth_rate(self) -> float:
        """Net ARR growth rate."""
        if self.beginning_arr <= 0:
            return 0.0
        return self.net_arr_change / self.beginning_arr

    def add_movement(self, movement: ARRMovement):
        """Add an ARR movement and update totals."""
        self.movements.append(movement)

        if movement.movement_type == ARRMovementType.NEW_LOGO:
            self.new_logo_arr += movement.arr_amount
            self.new_logos += 1
        elif movement.movement_type == ARRMovementType.EXPANSION:
            self.expansion_arr += movement.arr_amount
            self.expansions += 1
        elif movement.movement_type == ARRMovementType.CONTRACTION:
            self.contraction_arr += movement.arr_amount
            self.contractions += 1
        elif movement.movement_type == ARRMovementType.CHURN:
            self.churned_arr += movement.arr_amount
            self.churned_logos += 1
        elif movement.movement_type == ARRMovementType.RENEWAL:
            self.renewed_arr += movement.arr_amount
            self.renewals += 1

        # Update segment breakdown
        seg = movement.segment
        if seg not in self.by_segment:
            self.by_segment[seg] = {
                "new_logo_arr": 0,
                "expansion_arr": 0,
                "contraction_arr": 0,
                "churned_arr": 0,
                "count": 0,
            }

        self.by_segment[seg]["count"] += 1
        if movement.movement_type == ARRMovementType.NEW_LOGO:
            self.by_segment[seg]["new_logo_arr"] += movement.arr_amount
        elif movement.movement_type == ARRMovementType.EXPANSION:
            self.by_segment[seg]["expansion_arr"] += movement.arr_amount
        elif movement.movement_type == ARRMovementType.CONTRACTION:
            self.by_segment[seg]["contraction_arr"] += movement.arr_amount
        elif movement.movement_type == ARRMovementType.CHURN:
            self.by_segment[seg]["churned_arr"] += movement.arr_amount

        # Recalculate ending state
        self._calculate_ending_state()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "period": self.period,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "beginning_arr": self.beginning_arr,
            "beginning_logos": self.beginning_logos,
            "new_logo_arr": self.new_logo_arr,
            "new_logos": self.new_logos,
            "expansion_arr": self.expansion_arr,
            "expansions": self.expansions,
            "contraction_arr": self.contraction_arr,
            "contractions": self.contractions,
            "churned_arr": self.churned_arr,
            "churned_logos": self.churned_logos,
            "renewed_arr": self.renewed_arr,
            "renewals": self.renewals,
            "ending_arr": self.ending_arr,
            "ending_logos": self.ending_logos,
            "grr": self.grr,
            "nrr": self.nrr,
            "logo_retention_rate": self.logo_retention_rate,
            "expansion_rate": self.expansion_rate,
            "contraction_rate": self.contraction_rate,
            "churn_rate": self.churn_rate,
            "net_growth_rate": self.net_growth_rate,
            "by_segment": self.by_segment,
        }

    def summary(self) -> str:
        """Return formatted summary."""
        lines = [
            f"ARR Waterfall: {self.period}",
            "=" * 70,
            "",
        ]

        if self.period_start and self.period_end:
            lines.append(f"Period: {self.period_start} to {self.period_end}")
            lines.append("")

        lines.extend([
            "ARR WATERFALL",
            "-" * 50,
            f"  Beginning ARR:        ${self.beginning_arr:>15,.0f}",
            f"  + New Logo ARR:       ${self.new_logo_arr:>15,.0f}  ({self.new_logos} logos)",
            f"  + Expansion ARR:      ${self.expansion_arr:>15,.0f}  ({self.expansions} expansions)",
            f"  - Contraction ARR:    ${self.contraction_arr:>15,.0f}  ({self.contractions} contractions)",
            f"  - Churned ARR:        ${self.churned_arr:>15,.0f}  ({self.churned_logos} logos)",
            "-" * 50,
            f"  Ending ARR:           ${self.ending_arr:>15,.0f}  ({self.ending_logos} logos)",
            f"  Net Change:           ${self.net_arr_change:>+15,.0f}  ({self.net_growth_rate:+.1%})",
            "",
        ])

        lines.extend([
            "RETENTION METRICS",
            "-" * 50,
            f"  Gross Retention (GRR):  {self.grr:>10.1%}",
            f"  Net Retention (NRR):    {self.nrr:>10.1%}",
            f"  Logo Retention:         {self.logo_retention_rate:>10.1%}",
            "",
            f"  Expansion Rate:         {self.expansion_rate:>10.1%}",
            f"  Contraction Rate:       {self.contraction_rate:>10.1%}",
            f"  Churn Rate:             {self.churn_rate:>10.1%}",
            "",
        ])

        # Segment breakdown
        if self.by_segment:
            lines.extend([
                "BY SEGMENT",
                "-" * 50,
            ])
            for seg, data in sorted(self.by_segment.items()):
                total = (
                    data["new_logo_arr"]
                    + data["expansion_arr"]
                    - data["contraction_arr"]
                    - data["churned_arr"]
                )
                lines.append(f"  {seg.capitalize()}: ${total:>+15,.0f} net ({data['count']} movements)")
            lines.append("")

        return "\n".join(lines)


@dataclass
class CohortRetention:
    """
    Cohort-based retention tracking.

    Tracks how a cohort of customers (by signup month/quarter)
    retains over time.
    """
    cohort_period: str = ""  # e.g., "2025-Q1"
    cohort_start_date: Optional[date] = None

    # Initial cohort
    initial_arr: float = 0.0
    initial_logos: int = 0

    # Retention by period (months or quarters since cohort start)
    retention_by_period: Dict[int, dict] = field(default_factory=dict)

    def add_period(
        self,
        periods_since_start: int,
        arr: float,
        logos: int,
        expansion: float = 0,
        contraction: float = 0,
        churn: float = 0,
    ):
        """Add retention data for a period."""
        self.retention_by_period[periods_since_start] = {
            "arr": arr,
            "logos": logos,
            "expansion": expansion,
            "contraction": contraction,
            "churn": churn,
            "grr": (arr - expansion) / self.initial_arr if self.initial_arr > 0 else 1.0,
            "nrr": arr / self.initial_arr if self.initial_arr > 0 else 1.0,
            "logo_retention": logos / self.initial_logos if self.initial_logos > 0 else 1.0,
        }

    def get_retention_curve(self) -> List[dict]:
        """Get retention curve data."""
        curve = []
        for period in sorted(self.retention_by_period.keys()):
            data = self.retention_by_period[period]
            curve.append({
                "period": period,
                "grr": data["grr"],
                "nrr": data["nrr"],
                "logo_retention": data["logo_retention"],
            })
        return curve

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "cohort_period": self.cohort_period,
            "cohort_start_date": self.cohort_start_date.isoformat() if self.cohort_start_date else None,
            "initial_arr": self.initial_arr,
            "initial_logos": self.initial_logos,
            "retention_curve": self.get_retention_curve(),
        }


@dataclass
class NDRProjection:
    """
    Project future ARR based on NDR assumptions.
    """
    starting_arr: float = 0.0
    ndr_assumption: float = 1.10  # 110% NDR
    new_logo_arr_monthly: float = 0.0
    months: int = 12

    # Projections
    monthly_projections: List[dict] = field(default_factory=list)

    def project(self) -> dict:
        """Project ARR over time."""
        self.monthly_projections = []
        current_arr = self.starting_arr

        # Monthly NDR factor
        monthly_ndr = self.ndr_assumption ** (1/12)

        for month in range(1, self.months + 1):
            # Existing base grows at NDR
            retained_arr = current_arr * monthly_ndr

            # Add new logos
            ending_arr = retained_arr + self.new_logo_arr_monthly

            self.monthly_projections.append({
                "month": month,
                "beginning_arr": current_arr,
                "retained_arr": retained_arr,
                "new_logo_arr": self.new_logo_arr_monthly,
                "ending_arr": ending_arr,
                "growth_from_ndr": retained_arr - current_arr,
            })

            current_arr = ending_arr

        return {
            "starting_arr": self.starting_arr,
            "ending_arr": current_arr,
            "total_new_logo_arr": self.new_logo_arr_monthly * self.months,
            "total_ndr_growth": sum(m["growth_from_ndr"] for m in self.monthly_projections),
            "monthly": self.monthly_projections,
        }

    def summary(self) -> str:
        """Return formatted summary."""
        if not self.monthly_projections:
            self.project()

        ending = self.monthly_projections[-1]["ending_arr"] if self.monthly_projections else self.starting_arr

        lines = [
            "NDR Projection",
            "=" * 50,
            "",
            f"  Starting ARR:        ${self.starting_arr:,.0f}",
            f"  NDR Assumption:      {self.ndr_assumption:.1%}",
            f"  New Logo ARR/Month:  ${self.new_logo_arr_monthly:,.0f}",
            f"  Projection Period:   {self.months} months",
            "",
            f"  Ending ARR:          ${ending:,.0f}",
            f"  Total Growth:        ${ending - self.starting_arr:,.0f}",
            "",
        ]
        return "\n".join(lines)


# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================

def calculate_ndr(
    beginning_arr: float,
    expansion_arr: float = 0,
    contraction_arr: float = 0,
    churned_arr: float = 0,
) -> float:
    """
    Calculate Net Dollar Retention.

    NRR = (Beginning ARR - Churn - Contraction + Expansion) / Beginning ARR

    Args:
        beginning_arr: ARR at start of period
        expansion_arr: ARR added from existing customers
        contraction_arr: ARR lost from downgrades
        churned_arr: ARR lost from churned customers

    Returns:
        NDR as a decimal (e.g., 1.10 for 110%)
    """
    if beginning_arr <= 0:
        return 1.0

    ending_arr = beginning_arr - churned_arr - contraction_arr + expansion_arr
    return ending_arr / beginning_arr


def calculate_grr(
    beginning_arr: float,
    contraction_arr: float = 0,
    churned_arr: float = 0,
) -> float:
    """
    Calculate Gross Retention Rate.

    GRR = (Beginning ARR - Churn - Contraction) / Beginning ARR

    Args:
        beginning_arr: ARR at start of period
        contraction_arr: ARR lost from downgrades
        churned_arr: ARR lost from churned customers

    Returns:
        GRR as a decimal (e.g., 0.92 for 92%)
    """
    if beginning_arr <= 0:
        return 1.0

    retained_arr = beginning_arr - churned_arr - contraction_arr
    return retained_arr / beginning_arr


def calculate_expansion_rate(
    beginning_arr: float,
    expansion_arr: float,
) -> float:
    """
    Calculate expansion rate.

    Args:
        beginning_arr: ARR at start of period
        expansion_arr: ARR added from existing customers

    Returns:
        Expansion rate as decimal
    """
    if beginning_arr <= 0:
        return 0.0
    return expansion_arr / beginning_arr


def annualize_retention(
    period_rate: float,
    periods_per_year: int = 4,
) -> float:
    """
    Annualize a periodic retention rate.

    Args:
        period_rate: Retention rate for the period (e.g., quarterly)
        periods_per_year: Number of periods in a year (4 for quarterly)

    Returns:
        Annualized retention rate
    """
    return period_rate ** periods_per_year


def monthly_to_annual_ndr(monthly_ndr: float) -> float:
    """Convert monthly NDR to annual."""
    return monthly_ndr ** 12


def annual_to_monthly_ndr(annual_ndr: float) -> float:
    """Convert annual NDR to monthly."""
    return annual_ndr ** (1/12)


def build_arr_waterfall(
    opportunities: List[dict],
    period: str,
    beginning_arr: float = 0,
    beginning_logos: int = 0,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> ARRWaterfallPeriod:
    """
    Build ARR waterfall from opportunity data.

    Expects opportunities with:
    - account_id, account_name
    - opportunity_id
    - type: "New Business", "Renewal", "Expansion"
    - arr (or arr__c)
    - previous_period_arr (or previous_period_arr__c) for renewals
    - expansion_arr (or expansion_arr__c)
    - contraction_arr (or contraction_arr__c)
    - close_date
    - segment (optional)

    Args:
        opportunities: List of closed won opportunity dicts
        period: Period name (e.g., "Q1FY26")
        beginning_arr: Starting ARR for the period
        beginning_logos: Starting logo count
        period_start: Period start date
        period_end: Period end date

    Returns:
        ARRWaterfallPeriod with all movements
    """
    waterfall = ARRWaterfallPeriod(
        period=period,
        period_start=period_start,
        period_end=period_end,
        beginning_arr=beginning_arr,
        beginning_logos=beginning_logos,
    )

    for opp in opportunities:
        # Normalize field names (handle SF naming)
        account_id = opp.get("account_id") or opp.get("AccountId", "")
        account_name = opp.get("account_name") or opp.get("Account", {}).get("Name", "Unknown")
        opp_id = opp.get("opportunity_id") or opp.get("Id", "")
        opp_type = opp.get("type") or opp.get("Type", "").lower()
        arr = opp.get("arr") or opp.get("ARR__c") or opp.get("arr__c", 0)
        previous_arr = opp.get("previous_period_arr") or opp.get("Previous_Period_ARR__c", 0)
        expansion = opp.get("expansion_arr") or opp.get("Expansion_ARR__c", 0)
        contraction = opp.get("contraction_arr") or opp.get("Contraction_ARR__c", 0)
        segment = opp.get("segment", "unknown")

        close_date_raw = opp.get("close_date") or opp.get("CloseDate")
        if isinstance(close_date_raw, str):
            close_date = date.fromisoformat(close_date_raw[:10])
        elif isinstance(close_date_raw, date):
            close_date = close_date_raw
        else:
            close_date = None

        # Determine movement type
        if opp_type in ("new business", "new_business", "new logo"):
            movement = ARRMovement(
                account_id=account_id,
                account_name=account_name,
                opportunity_id=opp_id,
                movement_type=ARRMovementType.NEW_LOGO,
                arr_amount=arr,
                close_date=close_date,
                segment=segment,
            )
            waterfall.add_movement(movement)

        elif opp_type in ("renewal", "existing business"):
            # Renewals may have expansion and/or contraction
            if expansion > 0:
                waterfall.add_movement(ARRMovement(
                    account_id=account_id,
                    account_name=account_name,
                    opportunity_id=opp_id,
                    movement_type=ARRMovementType.EXPANSION,
                    arr_amount=expansion,
                    previous_arr=previous_arr,
                    close_date=close_date,
                    segment=segment,
                ))

            if contraction > 0:
                waterfall.add_movement(ARRMovement(
                    account_id=account_id,
                    account_name=account_name,
                    opportunity_id=opp_id,
                    movement_type=ARRMovementType.CONTRACTION,
                    arr_amount=contraction,
                    previous_arr=previous_arr,
                    close_date=close_date,
                    segment=segment,
                ))

            # If flat renewal (no expansion/contraction)
            if expansion == 0 and contraction == 0 and previous_arr > 0:
                waterfall.add_movement(ARRMovement(
                    account_id=account_id,
                    account_name=account_name,
                    opportunity_id=opp_id,
                    movement_type=ARRMovementType.RENEWAL,
                    arr_amount=previous_arr,
                    previous_arr=previous_arr,
                    close_date=close_date,
                    segment=segment,
                ))

        elif opp_type == "expansion":
            # Standalone expansion opportunity
            waterfall.add_movement(ARRMovement(
                account_id=account_id,
                account_name=account_name,
                opportunity_id=opp_id,
                movement_type=ARRMovementType.EXPANSION,
                arr_amount=expansion if expansion > 0 else arr,
                previous_arr=previous_arr,
                close_date=close_date,
                segment=segment,
            ))

    return waterfall


def build_arr_waterfall_from_sf(
    sf_connector,
    period_start: date,
    period_end: date,
    period_name: str = "",
) -> ARRWaterfallPeriod:
    """
    Build ARR waterfall directly from Salesforce data.

    Args:
        sf_connector: SalesforceConnector instance
        period_start: Period start date
        period_end: Period end date
        period_name: Period name (e.g., "Q1FY26")

    Returns:
        ARRWaterfallPeriod
    """
    # Get beginning ARR (active ARR as of period start)
    beginning_data = sf_connector.get_account_arr_summary(as_of_date=period_start)
    beginning_arr = beginning_data.get("total_active_arr", 0)
    beginning_logos = beginning_data.get("total_accounts", 0)

    # Get closed won opportunities in period
    opportunities = sf_connector.get_closed_won_opportunities(
        start_date=period_start,
        end_date=period_end,
    )

    # Get churned accounts (accounts that had ARR but now have 0)
    churned = sf_connector.get_churned_accounts(
        start_date=period_start,
        end_date=period_end,
    )

    # Build waterfall
    waterfall = build_arr_waterfall(
        opportunities=opportunities,
        period=period_name or f"{period_start} to {period_end}",
        beginning_arr=beginning_arr,
        beginning_logos=beginning_logos,
        period_start=period_start,
        period_end=period_end,
    )

    # Add churned accounts
    for account in churned:
        waterfall.add_movement(ARRMovement(
            account_id=account.get("Id", ""),
            account_name=account.get("Name", "Unknown"),
            movement_type=ARRMovementType.CHURN,
            arr_amount=account.get("churned_arr", 0),
            segment=account.get("segment", "unknown"),
        ))

    return waterfall


def project_arr_with_ndr(
    starting_arr: float,
    new_logo_arr_per_period: float,
    ndr: float = 1.10,
    periods: int = 12,
    period_type: str = "monthly",
) -> List[dict]:
    """
    Project ARR forward with NDR and new logo growth.

    Args:
        starting_arr: Current ARR
        new_logo_arr_per_period: New logo ARR added each period
        ndr: Net Dollar Retention rate (e.g., 1.10 for 110%)
        periods: Number of periods to project
        period_type: "monthly" or "quarterly"

    Returns:
        List of period projections
    """
    # Adjust NDR for period type
    if period_type == "quarterly":
        period_ndr = ndr ** 0.25  # Quarterly = annual^0.25
    else:
        period_ndr = ndr ** (1/12)  # Monthly = annual^(1/12)

    projections = []
    current_arr = starting_arr

    for i in range(1, periods + 1):
        # Base grows at NDR
        base_after_ndr = current_arr * period_ndr
        ndr_growth = base_after_ndr - current_arr

        # Add new logos
        ending_arr = base_after_ndr + new_logo_arr_per_period

        projections.append({
            "period": i,
            "beginning_arr": current_arr,
            "ndr_growth": ndr_growth,
            "new_logo_arr": new_logo_arr_per_period,
            "ending_arr": ending_arr,
            "cumulative_growth": ending_arr - starting_arr,
        })

        current_arr = ending_arr

    return projections

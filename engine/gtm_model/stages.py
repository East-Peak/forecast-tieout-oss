"""
Stage definitions for the GTM model.

Maps Salesforce opportunity stages to model stages and provides
conversion rate defaults and stage metadata.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .rate_defaults import get_default_funnel_rates

_DEFAULT_FUNNEL_RATES = get_default_funnel_rates()


class LeadStage(Enum):
    """Pre-opportunity lead stages (marketing/SDR funnel)."""

    RAW_LEAD = "Raw Lead"
    ENRICHED = "Enriched"
    MQL = "MQL"  # Marketing Qualified Lead
    SQL = "SQL"  # Sales Qualified Lead (accepted by sales)
    SAL = "SAL"  # Sales Accepted Lead (legacy, maps to SQL)


class OpportunityStage(Enum):
    """
    Salesforce opportunity stages mapped to model stages.

    Values match exact Salesforce picklist values for easy integration.
    """

    S0_RESEARCH = "0 - Research"
    S1_DISCOVERY = "1 - Discovery"
    S2_SCOPE = "2 - Scope"
    S3_TECH_VALIDATION = "3 - Tech Validation"
    S4_BUSINESS_CASE = "4 - Business Case Alignment"
    S5_VENDOR_CHOICE = "5 - Vendor of Choice"
    CLOSED_WON = "Closed Won"
    CLOSED_LOST = "Closed Lost"

    @property
    def is_open(self) -> bool:
        """Return True if this is an open (active) stage."""
        return self not in (self.CLOSED_WON, self.CLOSED_LOST)

    @property
    def is_won(self) -> bool:
        """Return True if this is a won stage."""
        return self == self.CLOSED_WON

    @property
    def stage_number(self) -> Optional[int]:
        """Return the numeric stage (0-5) or None for closed stages."""
        stage_map = {
            self.S0_RESEARCH: 0,
            self.S1_DISCOVERY: 1,
            self.S2_SCOPE: 2,
            self.S3_TECH_VALIDATION: 3,
            self.S4_BUSINESS_CASE: 4,
            self.S5_VENDOR_CHOICE: 5,
        }
        return stage_map.get(self)

    @property
    def short_name(self) -> str:
        """Return a short display name for the stage."""
        names = {
            self.S0_RESEARCH: "S0",
            self.S1_DISCOVERY: "S1",
            self.S2_SCOPE: "S2",
            self.S3_TECH_VALIDATION: "S3",
            self.S4_BUSINESS_CASE: "S4",
            self.S5_VENDOR_CHOICE: "S5",
            self.CLOSED_WON: "Won",
            self.CLOSED_LOST: "Lost",
        }
        return names.get(self, self.value)

    @classmethod
    def from_salesforce(cls, sf_stage: str) -> "OpportunityStage":
        """
        Convert a Salesforce stage name to an OpportunityStage.

        Handles common variations and normalizes the stage name.
        """
        # Direct match first
        for stage in cls:
            if stage.value == sf_stage:
                return stage

        # Handle variations
        sf_lower = sf_stage.lower().strip()
        if "research" in sf_lower or sf_lower.startswith("0"):
            return cls.S0_RESEARCH
        elif "discovery" in sf_lower or sf_lower.startswith("1"):
            return cls.S1_DISCOVERY
        elif "scope" in sf_lower or sf_lower.startswith("2"):
            return cls.S2_SCOPE
        elif "tech" in sf_lower or sf_lower.startswith("3"):
            return cls.S3_TECH_VALIDATION
        elif "business" in sf_lower or sf_lower.startswith("4"):
            return cls.S4_BUSINESS_CASE
        elif "vendor" in sf_lower or sf_lower.startswith("5"):
            return cls.S5_VENDOR_CHOICE
        elif "won" in sf_lower:
            return cls.CLOSED_WON
        elif "lost" in sf_lower:
            return cls.CLOSED_LOST

        raise ValueError(f"Unknown Salesforce stage: {sf_stage}")


class CustomerStage(Enum):
    """Post-sale customer lifecycle stages."""

    ONBOARDING = "Onboarding"
    GO_LIVE = "Go-Live"
    ACTIVE = "Active"
    ENGAGED = "Engaged"
    AT_RISK = "At Risk"
    CHURNED = "Churned"


@dataclass
class StageMetrics:
    """
    Metrics for a single stage at a point in time.

    Used for both lead stages and opportunity stages.
    """

    stage: str  # Stage name (LeadStage or OpportunityStage value)
    volume: int  # Count of records in this stage
    value: float  # Total ARR/ACV value in this stage
    conversion_rate: float  # Rate of conversion to next stage (0.0-1.0)
    avg_days_in_stage: float  # Average days spent in this stage

    @property
    def weighted_value(self) -> float:
        """Calculate weighted pipeline value based on conversion rate."""
        return self.value * self.conversion_rate


@dataclass
class StageDefinition:
    """
    Definition of a stage with default metrics and Salesforce mapping.

    Used to configure the model with expected conversion rates and velocities.
    """

    name: str
    salesforce_value: str
    default_conversion_rate: float  # Historical average
    default_days_in_stage: float  # Historical average
    description: str = ""

    def __post_init__(self):
        if not 0.0 <= self.default_conversion_rate <= 1.0:
            raise ValueError(f"Conversion rate must be between 0 and 1, got {self.default_conversion_rate}")


# Default stage definitions based on typical B2B SaaS distributions
DEFAULT_LEAD_STAGES = [
    StageDefinition(
        name="Raw Lead",
        salesforce_value="Raw Lead",
        default_conversion_rate=0.30,  # 30% become MQL
        default_days_in_stage=2.0,
        description="New inbound lead, not yet enriched or scored",
    ),
    StageDefinition(
        name="MQL",
        salesforce_value="MQL",
        default_conversion_rate=0.15,  # 15% become S0
        default_days_in_stage=3.0,
        description="Marketing Qualified Lead, meets ICP criteria",
    ),
    StageDefinition(
        name="SQL",
        salesforce_value="SQL",
        default_conversion_rate=0.55,  # 55% become S0
        default_days_in_stage=2.0,
        description="Sales Qualified Lead, accepted by AE/SDR",
    ),
]

DEFAULT_OPPORTUNITY_STAGES = [
    StageDefinition(
        name="S0 - Research",
        salesforce_value="0 - Research",
        default_conversion_rate=_DEFAULT_FUNNEL_RATES["s0_to_s1"],
        default_days_in_stage=14.0,
        description="Initial research and qualification",
    ),
    StageDefinition(
        name="S1 - Discovery",
        salesforce_value="1 - Discovery",
        default_conversion_rate=_DEFAULT_FUNNEL_RATES["s1_to_s2"],
        default_days_in_stage=21.0,
        description="Discovery calls, understanding requirements",
    ),
    StageDefinition(
        name="S2 - Scope",
        salesforce_value="2 - Scope",
        default_conversion_rate=_DEFAULT_FUNNEL_RATES["s2_to_s3"],
        default_days_in_stage=28.0,
        description="Scoping the solution, building business case",
    ),
    StageDefinition(
        name="S3 - Tech Validation",
        salesforce_value="3 - Tech Validation",
        default_conversion_rate=_DEFAULT_FUNNEL_RATES["s3_to_s4"],
        default_days_in_stage=21.0,
        description="Technical proof of concept, security review",
    ),
    StageDefinition(
        name="S4 - Business Case",
        salesforce_value="4 - Business Case Alignment",
        default_conversion_rate=_DEFAULT_FUNNEL_RATES["s4_to_s5"],
        default_days_in_stage=14.0,
        description="Pricing, procurement, legal review",
    ),
    StageDefinition(
        name="S5 - Vendor of Choice",
        salesforce_value="5 - Vendor of Choice",
        default_conversion_rate=_DEFAULT_FUNNEL_RATES["s5_to_won"],
        default_days_in_stage=14.0,
        description="Selected vendor, finalizing contract",
    ),
]


def get_stage_progression() -> list[tuple[str, str]]:
    """
    Return the expected progression path through stages.

    Returns list of (from_stage, to_stage) tuples.
    """
    return [
        ("Raw Lead", "MQL"),
        ("MQL", "SQL"),
        ("SQL", "S0 - Research"),
        ("S0 - Research", "S1 - Discovery"),
        ("S1 - Discovery", "S2 - Scope"),
        ("S2 - Scope", "S3 - Tech Validation"),
        ("S3 - Tech Validation", "S4 - Business Case"),
        ("S4 - Business Case", "S5 - Vendor of Choice"),
        ("S5 - Vendor of Choice", "Closed Won"),
    ]


def calculate_s2_to_won_rate(
    s2_to_s3: Optional[float] = None,
    s3_to_s4: Optional[float] = None,
    s4_to_s5: Optional[float] = None,
    s5_to_won: Optional[float] = None,
) -> float:
    """
    Calculate the composite S2-to-Won conversion rate.

    This is the probability that an opportunity in S2 will eventually close.

    Args:
        s2_to_s3: Conversion rate from S2 to S3
        s3_to_s4: Conversion rate from S3 to S4
        s4_to_s5: Conversion rate from S4 to S5
        s5_to_won: Conversion rate from S5 to Won

    Returns:
        Composite conversion rate from S2 to Won
    """
    return (
        (s2_to_s3 if s2_to_s3 is not None else _DEFAULT_FUNNEL_RATES["s2_to_s3"])
        * (s3_to_s4 if s3_to_s4 is not None else _DEFAULT_FUNNEL_RATES["s3_to_s4"])
        * (s4_to_s5 if s4_to_s5 is not None else _DEFAULT_FUNNEL_RATES["s4_to_s5"])
        * (s5_to_won if s5_to_won is not None else _DEFAULT_FUNNEL_RATES["s5_to_won"])
    )


def calculate_mql_to_won_rate(
    mql_to_s0: Optional[float] = None,
    s0_to_s1: Optional[float] = None,
    s1_to_s2: Optional[float] = None,
    s2_to_won: Optional[float] = None,
) -> float:
    """
    Calculate the composite MQL-to-Won conversion rate.

    Args:
        mql_to_s0: Conversion rate from MQL to S0
        s0_to_s1: Conversion rate from S0 to S1
        s1_to_s2: Conversion rate from S1 to S2
        s2_to_won: Composite rate from S2 to Won (calculated if not provided)

    Returns:
        Composite conversion rate from MQL to Won
    """
    if s2_to_won is None:
        s2_to_won = calculate_s2_to_won_rate()

    return (
        (mql_to_s0 if mql_to_s0 is not None else _DEFAULT_FUNNEL_RATES["mql_to_s0"])
        * (s0_to_s1 if s0_to_s1 is not None else _DEFAULT_FUNNEL_RATES["s0_to_s1"])
        * (s1_to_s2 if s1_to_s2 is not None else _DEFAULT_FUNNEL_RATES["s1_to_s2"])
        * s2_to_won
    )

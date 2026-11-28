"""Every knob of the synthetic company, in one typed object.

`CompanyParams` is written to the truth manifest next to the extracts, so a
reader can see exactly which company produced them. All values are fabricated.
Money is in dollars here (the extracts convert to cents where the contract wants
cents). Dates are `datetime.date`; the fiscal year starts February 1 and is named
by its starting year (FY25 = 2025-02-01 to 2026-01-31).
"""

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from typing import Any

SEGMENTS = ("SMB", "Mid-Market", "Enterprise")
SOURCES = (
    "Paid",
    "Events",
    "Inbound",
    "ABM",
    "Outbound",
    "SelfSourced",
    "Partner",
    "Unknown",
)
MARKETING_SOURCES = ("Paid", "Events", "Inbound", "ABM")
VARIANTS = ("demand_limited", "capacity_constrained")


@dataclass(frozen=True)
class SegmentSpec:
    """A segment, the account tier it comes from and the AE team that sells it."""

    name: str
    tier: str  # Account/Lead Tier__c value that maps to this segment
    team: str  # AE team: the pool of carrying capacity
    ceiling: int  # concurrent open deals one ramped AE can carry
    amount_median: float  # dollars; deal sizes are lognormal around it
    amount_sigma: float  # heavy tail: larger sigma, fatter tail
    cycle_days: float  # median days from creation to close


@dataclass(frozen=True)
class CampaignSpec:
    """A marketing program: spend drives MQLs with diminishing returns and seasonality.

    expected monthly MQLs = (k * (spend / 1000) ** alpha + base) * trend * season
    """

    name: str
    type: str  # Campaign.Type; the catalog maps type to source
    source: str  # Paid, Events, Inbound or ABM
    segment_mix: dict[str, float]  # share of the program's leads by segment
    spend: float  # monthly dollars at the simulation start
    k: float
    alpha: float = 0.8  # diminishing returns on spend
    base: float = 0.0  # MQLs per month that spend does not buy (organic)
    growth: float = 0.0  # base trend: yearly growth until the plateau date
    plateau: date | None = None  # growth stops here: the plateaued lane
    launch: date | None = None  # None: live from the start
    end: date | None = None  # None: still running


@dataclass(frozen=True)
class HireSpec:
    """A requisition and the hire it becomes; the start slips by `slip_days`."""

    team: str  # AE-SMB, AE-MidMarket, AE-Enterprise, BDR or Marketing
    role: str
    planned_start: date
    slip_days: int = 0
    segment: str | None = None  # coverage (BDRs target one segment)
    cancelled: bool = False


@dataclass(frozen=True)
class WinStep:
    """A step change in one lane's win probability for deals created on or after `on`."""

    segment: str
    source: str
    on: date
    before: float
    after: float


@dataclass(frozen=True)
class SpendStep:
    """Paid, Events and ABM budgets are multiplied by `factor` from `on` (an earlier step is kept)."""

    on: date
    factor: float


@dataclass(frozen=True)
class Intervention:
    """One change for a paired counterfactual; the default changes nothing.

    slip_hire:    (requisition id, extra days): that hire starts later.
    spend_change: (campaign name, first month, factor): that program's budget is
                  multiplied by `factor` from that month on.
    """

    slip_hire: tuple[str, int] | None = None
    spend_change: tuple[str, date, float] | None = None


def _t(*rows):
    return tuple(rows)


@dataclass(frozen=True)
class CompanyParams:
    variant: str = "demand_limited"
    company_name: str = "Brindlewick Analytics (fictional)"
    start: date = date(2022, 2, 1)  # FY22 start; the pipeline starts empty (warm-up)
    end: date = date(2026, 7, 31)
    plan_date: date = date(2025, 1, 24)
    queue_max_days: int = 14
    # Routing priority across lead sources (marketing, outbound and partner leads all share the
    # team's queue). Only "oldest_first" exists: the oldest queued demand is served first, and a
    # same-age class splits across lanes in proportion to its size (largest remainder).
    routing_priority: str = "oldest_first"
    # Carrying ramp, by days of AE tenure: 0 until `carry_ramp_start`, linear over `carry_ramp_days`.
    # Separate from the sourcing ramp (`ramp_days`).
    carry_ramp_start: int = 30
    carry_ramp_days: int = 60
    # When an AE leaves, open deals wait with a manager `handoff_days`, then go to the teammate
    # with the fewest deals (beyond their ceiling if need be). Each deal has `p_orphan_loss` extra
    # risk of being lost to the gap, and its stages run (1 + orphan_stretch) times as long.
    handoff_days: int = 14
    p_orphan_loss: float = 0.15
    orphan_stretch: float = 0.5
    # A seller's written expected close: segment cycle norm times optimism times lognormal noise.
    expected_close_optimism: float = 0.9
    expected_close_noise: float = (
        0.25  # demand waits this many days, then expires for capacity
    )
    segments: tuple[SegmentSpec, ...] = _t(
        SegmentSpec("SMB", "Tier 3", "AE-SMB", 30, 12000, 0.55, 35),
        SegmentSpec("Mid-Market", "Tier 2", "AE-MidMarket", 26, 34000, 0.60, 75),
        SegmentSpec("Enterprise", "Tier 1", "AE-Enterprise", 18, 140000, 0.70, 150),
    )
    # Win probability by segment and source; a lane is live where it has an entry.
    win_rate: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "SMB": {
                "Paid": 0.20,
                "Events": 0.24,
                "Inbound": 0.30,
                "Outbound": 0.17,
                "SelfSourced": 0.30,
                "Partner": 0.38,
                "Unknown": 0.15,
            },
            "Mid-Market": {
                "Paid": 0.20,
                "Events": 0.25,
                "Inbound": 0.30,
                "ABM": 0.34,
                "Outbound": 0.18,
                "SelfSourced": 0.30,
                "Partner": 0.38,
                "Unknown": 0.15,
            },
            "Enterprise": {
                "Events": 0.25,
                "ABM": 0.32,
                "Outbound": 0.20,
                "SelfSourced": 0.30,
                "Partner": 0.36,
                "Unknown": 0.15,
            },
        }
    )
    win_step: WinStep = WinStep("SMB", "Outbound", date(2024, 8, 1), 0.16, 0.27)
    source_amount_factor: dict[str, float] = field(
        default_factory=lambda: {"ABM": 1.4, "Partner": 1.1, "Paid": 0.9}
    )
    region_win_factor: dict[str, float] = field(
        default_factory=lambda: {"NA": 1.0, "EMEA": 0.9}
    )
    region_cycle_factor: dict[str, float] = field(
        default_factory=lambda: {"NA": 1.0, "EMEA": 1.15}
    )
    stages: tuple[str, ...] = ("Discovery", "Evaluation", "Proposal", "Negotiation")
    stage_shares: tuple[float, ...] = (
        0.2,
        0.3,
        0.3,
        0.2,
    )  # share of the cycle spent in each stage
    loss_stage: tuple[float, ...] = (
        0.35,
        0.30,
        0.20,
        0.15,
    )  # where a lost deal is lost
    cycle_sigma: float = 0.35
    overload_threshold: float = (
        0.7  # owner utilization above this stretches stage durations
    )
    overload_stretch: float = (
        0.6  # at full utilization a stage takes (1 + this) times as long
    )
    discount_max: float = 0.20  # wins close at list less U(0, discount_max)
    p_discount: float = 0.7
    p_amend: float = 0.06  # won amount amended after close
    amend_days: tuple[int, int] = (3, 70)
    p_close_arrears: float = 0.12  # close date entered in arrears
    close_arrears_days: tuple[int, int] = (1, 20)
    p_close_corrected: float = 0.03  # close date corrected again later
    p_reopen: float = 0.05  # a lost deal reopens (if its team has room)
    reopen_days: tuple[int, int] = (10, 60)
    p_delete: float = 0.006  # an opportunity record is deleted (never a won one)
    delete_days: tuple[int, int] = (45, 400)
    p_renewal_clutter: float = (
        0.8  # won deals spawn a Renewal opportunity (not new business)
    )
    p_tier_change: float = 0.04  # account tier edited later (a field with no history)
    reject_fit: dict[str, float] = field(
        default_factory=lambda: {
            "Paid": 0.35,
            "Events": 0.25,
            "Inbound": 0.20,
            "ABM": 0.10,
            "Outbound": 0.25,
            "Partner": 0.15,
            "Unknown": 0.40,
        }
    )
    p_reoffer: float = 0.30  # a fit-rejected lead is offered again later
    reoffer_days: tuple[int, int] = (30, 120)
    p_reoffer_fit: float = 0.6
    p_unattributed: float = (
        0.05  # marketing leads that lose their campaign: lane Unknown
    )
    p_mql_arrears: float = 0.12  # MQL date entered in arrears
    mql_arrears_days: tuple[int, int] = (3, 25)
    clutter_lead_share: float = 0.25  # extra leads that never become MQLs
    p_hubspot_mirror: float = (
        0.85  # marketing-sourced opportunities mirrored as HubSpot deals
    )
    campaigns: tuple[CampaignSpec, ...] = _t(
        CampaignSpec(
            "Paid Search SMB",
            "Paid Search",
            "Paid",
            {"SMB": 0.85, "Mid-Market": 0.15},
            14000,
            2.2,
        ),
        CampaignSpec(
            "Paid Search MM",
            "Paid Search",
            "Paid",
            {"Mid-Market": 0.9, "SMB": 0.1},
            9000,
            0.9,
        ),
        CampaignSpec(
            "Paid Social",
            "Paid Social",
            "Paid",
            {"SMB": 0.9, "Mid-Market": 0.1},
            6000,
            2.2,
            launch=date(2022, 9, 1),
        ),
        CampaignSpec(
            "Regional Trade Shows",
            "Trade Show",
            "Events",
            {"Mid-Market": 0.55, "SMB": 0.3, "Enterprise": 0.15},
            12000,
            1.0,
        ),
        CampaignSpec(
            "Webinar Series",
            "Webinar",
            "Events",
            {"SMB": 0.6, "Mid-Market": 0.4},
            4000,
            2.2,
        ),
        CampaignSpec(
            "Organic Web SMB",
            "Web Inbound",
            "Inbound",
            {"SMB": 1.0},
            1500,
            0.6,
            base=7.0,
            growth=0.30,
            plateau=date(2024, 3, 1),
        ),
        CampaignSpec(
            "Content Library",
            "Web Inbound",
            "Inbound",
            {"Mid-Market": 1.0},
            2500,
            0.6,
            base=2.5,
            growth=0.25,
        ),
        CampaignSpec(
            "ABM Named Accounts",
            "ABM Campaign",
            "ABM",
            {"Mid-Market": 1.0},
            8000,
            0.7,
            alpha=0.7,
            launch=date(2022, 8, 1),
        ),
        CampaignSpec(
            "ABM Strategic",
            "ABM Campaign",
            "ABM",
            {"Enterprise": 1.0},
            10000,
            0.12,
            alpha=0.7,
            launch=date(2022, 8, 1),
        ),
    )
    spend_growth: float = 0.25  # yearly growth of every program budget
    spend_season: dict[str, tuple[float, ...]] = field(
        default_factory=lambda: {
            "Events": (0.5, 1.4, 1.6, 1.2, 0.8, 0.6, 0.2, 0.5, 1.6, 1.8, 1.1, 0.2),
        }
    )  # calendar-month budget pattern; sources not listed are flat
    response_season: dict[str, tuple[float, ...]] = field(
        default_factory=lambda: {
            "Paid": (
                0.9,
                0.95,
                1.05,
                1.05,
                1.0,
                0.95,
                0.85,
                0.85,
                1.05,
                1.15,
                1.1,
                0.9,
            ),
            "Events": (0.8, 1.1, 1.2, 1.1, 1.0, 0.9, 0.6, 0.8, 1.2, 1.3, 1.1, 0.6),
            "Inbound": (
                0.9,
                1.0,
                1.05,
                1.05,
                1.0,
                0.95,
                0.85,
                0.85,
                1.05,
                1.15,
                1.1,
                0.9,
            ),
            "ABM": (1.0,) * 12,
        }
    )  # how strongly a given spend turns into MQLs by calendar month
    spend_steps: tuple[SpendStep, ...] = ()
    bdr_leads_per_day: dict[str, float] = field(
        default_factory=lambda: {"SMB": 0.30, "Mid-Market": 0.10, "Enterprise": 0.04}
    )  # offered outbound leads per fully ramped BDR-day, by the segment the BDR covers
    ae_self_per_day: float = (
        0.022  # opportunities a ramped AE sources per day (when not full)
    )
    partner_per_day: dict[str, float] = field(
        default_factory=lambda: {"SMB": 0.10, "Mid-Market": 0.04, "Enterprise": 0.012}
    )
    ramp_days: tuple[int, int] = (60, 180)  # individual sourcing ramp, drawn per person
    skill_sigma: float = 0.12  # individual AE win-rate multiplier spread
    attrition_annual: dict[str, float] = field(
        default_factory=lambda: {"AE": 0.12, "BDR": 0.20}
    )
    region_mix: dict[str, float] = field(
        default_factory=lambda: {"NA": 0.62, "EMEA": 0.38}
    )
    countries: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "US": ("United States", "US", "USA", "U.S."),
            "CA": ("Canada", "CA"),
            "GB": ("United Kingdom", "GB", "UK"),
            "DE": ("Germany", "DE"),
            "FR": ("France", "FR"),
            "NL": ("Netherlands", "NL", "Holland"),
        }
    )  # country code -> the spellings users type
    country_mix: dict[str, float] = field(
        default_factory=lambda: {
            "US": 0.52,
            "CA": 0.10,
            "GB": 0.17,
            "DE": 0.10,
            "FR": 0.06,
            "NL": 0.05,
        }
    )
    country_region: dict[str, str] = field(
        default_factory=lambda: {
            "US": "NA",
            "CA": "NA",
            "GB": "EMEA",
            "DE": "EMEA",
            "FR": "EMEA",
            "NL": "EMEA",
        }
    )
    p_country_code: float = (
        0.6  # accounts that also carry a standardized BillingCountryCode
    )
    initial_staff: tuple[HireSpec, ...] = _t(
        HireSpec("AE-SMB", "AE", date(2021, 6, 1)),
        HireSpec("AE-SMB", "AE", date(2021, 10, 1)),
        HireSpec("AE-SMB", "AE", date(2022, 1, 3)),
        HireSpec("AE-MidMarket", "AE", date(2021, 8, 2)),
        HireSpec("AE-MidMarket", "AE", date(2021, 12, 1)),
        HireSpec("AE-Enterprise", "AE", date(2021, 9, 1)),
        HireSpec("BDR", "BDR", date(2021, 11, 1), segment="SMB"),
        HireSpec("BDR", "BDR", date(2021, 11, 1), segment="Mid-Market"),
        HireSpec("Marketing", "Marketing", date(2021, 5, 3)),
        HireSpec("Marketing", "Marketing", date(2022, 1, 3)),
        HireSpec("CS", "Manager", date(2021, 9, 1)),
        HireSpec("CS", "Manager", date(2022, 3, 1)),
    )
    hires: tuple[HireSpec, ...] = _t(
        HireSpec("BDR", "BDR", date(2022, 5, 2), 0, "Enterprise"),
        HireSpec("AE-SMB", "AE", date(2022, 7, 1), 0),
        HireSpec("AE-MidMarket", "AE", date(2022, 10, 3), 21),
        HireSpec("BDR", "BDR", date(2023, 2, 1), 14, "SMB"),
        HireSpec("AE-SMB", "AE", date(2023, 3, 1), 30),
        HireSpec("AE-Enterprise", "AE", date(2023, 6, 1), 0),
        HireSpec("AE-MidMarket", "AE", date(2023, 9, 1), 0),
        HireSpec("AE-Enterprise", "AE", date(2023, 10, 2), 20),
        HireSpec("AE-SMB", "AE", date(2023, 12, 1), 0, cancelled=True),
        HireSpec("BDR", "BDR", date(2024, 3, 1), 0, "Mid-Market"),
        HireSpec("AE-SMB", "AE", date(2024, 4, 1), 14),
        HireSpec("AE-MidMarket", "AE", date(2024, 5, 1), 75),
        HireSpec("AE-Enterprise", "AE", date(2024, 8, 1), 90),
        HireSpec("BDR", "BDR", date(2024, 9, 3), 60, "SMB"),
        HireSpec("AE-SMB", "AE", date(2025, 3, 3), 45),
        HireSpec("AE-MidMarket", "AE", date(2025, 4, 1), 60),
        HireSpec("BDR", "BDR", date(2025, 5, 1), 30, "Mid-Market"),
        HireSpec("AE-Enterprise", "AE", date(2025, 6, 2), 30),
        HireSpec("AE-SMB", "AE", date(2025, 8, 1), 0),
        HireSpec("AE-MidMarket", "AE", date(2025, 9, 1), 0),
        HireSpec("BDR", "BDR", date(2025, 11, 3), 0, "SMB", cancelled=True),
        HireSpec("AE-SMB", "AE", date(2026, 3, 2), 0),
        HireSpec("AE-MidMarket", "AE", date(2026, 8, 17), 0),
    )
    whale_after: date = date(
        2024, 6, 1
    )  # the first Enterprise deal created from here is the very large one
    whale_amount: float = 3_000_000

    @classmethod
    def for_variant(cls, variant: str, **overrides: Any) -> "CompanyParams":
        """`demand_limited`: ceilings roomy and budgets steady. `capacity_constrained`: lower
        ceilings and budgets stepped up twice, so open deals sit at the ceiling for long stretches."""
        if variant not in VARIANTS:
            raise ValueError(f"variant must be one of {VARIANTS}, not {variant!r}")
        base = cls(variant=variant)
        if variant == "capacity_constrained":
            segments = tuple(
                dataclasses.replace(s, ceiling=round(s.ceiling * 0.5))
                for s in base.segments
            )
            steps = (
                SpendStep(date(2024, 5, 1), 1.25),
                SpendStep(date(2025, 3, 1), 1.25),
            )
            base = dataclasses.replace(base, segments=segments, spend_steps=steps)
        return dataclasses.replace(base, **overrides)

    def to_dict(self) -> dict:
        """JSON-ready form (dates as ISO text) for the manifest."""

        def plain(x):
            if isinstance(x, date):
                return x.isoformat()
            if dataclasses.is_dataclass(x):
                return {
                    f.name: plain(getattr(x, f.name)) for f in dataclasses.fields(x)
                }
            if isinstance(x, dict):
                return {str(k): plain(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [plain(v) for v in x]
            return x

        return plain(self)

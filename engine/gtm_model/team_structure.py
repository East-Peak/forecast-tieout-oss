"""
GTM Team Structure Module - Coverage Ratios and Derived Team Composition.

Models coverage ratios (AE:SE, AE:SDR, AE:Manager) and derives full team
composition from core AE headcount. Supports segment-specific ratios.

Example usage:
    from gtm_model.team_structure import CoverageRatios, derive_team

    ratios = CoverageRatios()
    team = derive_team(ae_count=40, ratios=ratios)
    print(team.summary())
    # -> DerivedTeam with SEs, SDRs, Managers, CSMs, FDEs
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import math


class GTMRole(Enum):
    """GTM role types for org planning."""

    # Individual Contributors
    AE_ENTERPRISE = "ae_enterprise"
    AE_MIDMARKET = "ae_midmarket"
    SDR = "sdr"
    SE = "se"
    CSM = "csm"
    FDE = "fde"

    # Managers
    MGR_AE_ENTERPRISE = "mgr_ae_enterprise"
    MGR_AE_MIDMARKET = "mgr_ae_midmarket"
    MGR_SE = "mgr_se"
    MGR_SDR = "mgr_sdr"
    MGR_CSM = "mgr_csm"


@dataclass
class SegmentRatios:
    """
    Coverage ratios for a single segment.

    All ratios are expressed as "X ICs per 1 support role".
    E.g., ae_to_se_ratio=2.0 means 1 SE per 2 AEs.
    """

    ae_to_se_ratio: float = 2.0       # 1 SE per 2 AEs
    ae_to_sdr_ratio: float = 2.0      # 1 SDR per 2 AEs
    ae_to_manager_ratio: float = 8.0  # 1 AE Manager per 8 AEs
    ae_to_csm_ratio: float = 4.0      # 1 CSM per 4 AEs (post-sale coverage)
    ae_to_fde_ratio: float = 3.0      # 1 FDE per 3 AEs


@dataclass
class CoverageRatios:
    """
    Coverage ratios for all segments and support roles.

    Supports segment-specific overrides for Enterprise vs Mid-Market.
    """

    # Segment-specific IC ratios
    enterprise: SegmentRatios = field(default_factory=lambda: SegmentRatios(
        ae_to_se_ratio=2.0,       # More SE support for enterprise
        ae_to_sdr_ratio=2.0,
        ae_to_manager_ratio=8.0,
        ae_to_csm_ratio=4.0,
        ae_to_fde_ratio=3.0,
    ))

    mid_market: SegmentRatios = field(default_factory=lambda: SegmentRatios(
        ae_to_se_ratio=5.0,       # Less SE support for mid-market
        ae_to_sdr_ratio=5.0,
        ae_to_manager_ratio=10.0,
        ae_to_csm_ratio=8.0,      # CSMs cover more MM accounts
        ae_to_fde_ratio=4.0,
    ))

    # Manager ratios for support roles (not segment-specific)
    se_to_manager_ratio: float = 6.0   # 1 SE Manager per 6 SEs
    sdr_to_manager_ratio: float = 8.0  # 1 SDR Manager per 8 SDRs
    csm_to_manager_ratio: float = 6.0  # 1 CSM Manager per 6 CSMs

    def get_segment_ratios(self, segment: str) -> SegmentRatios:
        """Get ratios for a specific segment."""
        if segment.lower() in ("enterprise", "ent"):
            return self.enterprise
        elif segment.lower() in ("mid_market", "midmarket", "mm"):
            return self.mid_market
        else:
            # Default to blended (average of enterprise and mid-market)
            return self.enterprise  # or could calculate weighted average


@dataclass
class DerivedTeam:
    """
    Full team composition derived from AE count.

    Contains headcount for all GTM roles including managers.
    """

    # Core input
    aes_enterprise: int = 0
    aes_midmarket: int = 0

    # Derived ICs
    ses: int = 0
    sdrs: int = 0
    csms: int = 0
    fdes: int = 0

    # Derived Managers
    ae_managers_enterprise: int = 0
    ae_managers_midmarket: int = 0
    se_managers: int = 0
    sdr_managers: int = 0
    csm_managers: int = 0

    # Segment mix used
    enterprise_pct: float = 0.0
    midmarket_pct: float = 0.0

    @property
    def total_aes(self) -> int:
        """Total AE count across segments."""
        return self.aes_enterprise + self.aes_midmarket

    @property
    def total_ics(self) -> int:
        """Total individual contributors."""
        return (
            self.aes_enterprise +
            self.aes_midmarket +
            self.ses +
            self.sdrs +
            self.csms +
            self.fdes
        )

    @property
    def total_ae_managers(self) -> int:
        """Total AE managers across segments."""
        return self.ae_managers_enterprise + self.ae_managers_midmarket

    @property
    def total_managers(self) -> int:
        """Total managers."""
        return (
            self.ae_managers_enterprise +
            self.ae_managers_midmarket +
            self.se_managers +
            self.sdr_managers +
            self.csm_managers
        )

    @property
    def total_headcount(self) -> int:
        """Total headcount (ICs + Managers)."""
        return self.total_ics + self.total_managers

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "ics": {
                "aes_enterprise": self.aes_enterprise,
                "aes_midmarket": self.aes_midmarket,
                "ses": self.ses,
                "sdrs": self.sdrs,
                "csms": self.csms,
                "fdes": self.fdes,
                "total_ics": self.total_ics,
            },
            "managers": {
                "ae_managers_enterprise": self.ae_managers_enterprise,
                "ae_managers_midmarket": self.ae_managers_midmarket,
                "se_managers": self.se_managers,
                "sdr_managers": self.sdr_managers,
                "csm_managers": self.csm_managers,
                "total_managers": self.total_managers,
            },
            "totals": {
                "total_aes": self.total_aes,
                "total_headcount": self.total_headcount,
            },
            "segment_mix": {
                "enterprise_pct": self.enterprise_pct,
                "midmarket_pct": self.midmarket_pct,
            },
        }

    def summary(self) -> str:
        """Return formatted summary of team composition."""
        lines = [
            "Derived Team Composition",
            "=" * 50,
            "",
            "INDIVIDUAL CONTRIBUTORS",
            "-" * 40,
            f"  Enterprise AEs:     {self.aes_enterprise:>4}",
            f"  Mid-Market AEs:     {self.aes_midmarket:>4}",
            f"  Total AEs:          {self.total_aes:>4}",
            "",
            f"  Sales Engineers:    {self.ses:>4}",
            f"  SDRs:               {self.sdrs:>4}",
            f"  CSMs:               {self.csms:>4}",
            f"  FDEs:               {self.fdes:>4}",
            f"  Total ICs:          {self.total_ics:>4}",
            "",
            "MANAGERS",
            "-" * 40,
            f"  AE Managers (Ent):  {self.ae_managers_enterprise:>4}",
            f"  AE Managers (MM):   {self.ae_managers_midmarket:>4}",
            f"  SE Managers:        {self.se_managers:>4}",
            f"  SDR Managers:       {self.sdr_managers:>4}",
            f"  CSM Managers:       {self.csm_managers:>4}",
            f"  Total Managers:     {self.total_managers:>4}",
            "",
            "TOTALS",
            "-" * 40,
            f"  Total Headcount:    {self.total_headcount:>4}",
            "",
            f"Segment Mix: {self.enterprise_pct:.0%} Enterprise, {self.midmarket_pct:.0%} Mid-Market",
        ]
        return "\n".join(lines)


def derive_team(
    ae_count: int,
    ratios: Optional[CoverageRatios] = None,
    enterprise_pct: float = 0.5,
    include_csm: bool = True,
    include_fde: bool = True,
) -> DerivedTeam:
    """
    Given X AEs, calculate full team needed.

    Derives SE, SDR, CSM, FDE, and Manager headcount based on coverage ratios.

    Args:
        ae_count: Total AE headcount to derive from
        ratios: Coverage ratios to use (defaults to CoverageRatios())
        enterprise_pct: Percentage of AEs that are Enterprise (0.0 to 1.0)
        include_csm: Whether to include CSMs in derived team
        include_fde: Whether to include FDEs in derived team

    Returns:
        DerivedTeam with full headcount breakdown
    """
    if ratios is None:
        ratios = CoverageRatios()

    # Split AEs by segment
    aes_enterprise = int(round(ae_count * enterprise_pct))
    aes_midmarket = ae_count - aes_enterprise

    # Get segment ratios
    ent_ratios = ratios.enterprise
    mm_ratios = ratios.mid_market

    # Derive SEs (segment-weighted)
    ses_for_ent = aes_enterprise / ent_ratios.ae_to_se_ratio if ent_ratios.ae_to_se_ratio > 0 else 0
    ses_for_mm = aes_midmarket / mm_ratios.ae_to_se_ratio if mm_ratios.ae_to_se_ratio > 0 else 0
    total_ses = math.ceil(ses_for_ent + ses_for_mm)

    # Derive SDRs (segment-weighted)
    sdrs_for_ent = aes_enterprise / ent_ratios.ae_to_sdr_ratio if ent_ratios.ae_to_sdr_ratio > 0 else 0
    sdrs_for_mm = aes_midmarket / mm_ratios.ae_to_sdr_ratio if mm_ratios.ae_to_sdr_ratio > 0 else 0
    total_sdrs = math.ceil(sdrs_for_ent + sdrs_for_mm)

    # Derive CSMs (segment-weighted, optional)
    total_csms = 0
    if include_csm:
        csms_for_ent = aes_enterprise / ent_ratios.ae_to_csm_ratio if ent_ratios.ae_to_csm_ratio > 0 else 0
        csms_for_mm = aes_midmarket / mm_ratios.ae_to_csm_ratio if mm_ratios.ae_to_csm_ratio > 0 else 0
        total_csms = math.ceil(csms_for_ent + csms_for_mm)

    # Derive FDEs (segment-weighted, optional)
    total_fdes = 0
    if include_fde:
        fdes_for_ent = aes_enterprise / ent_ratios.ae_to_fde_ratio if ent_ratios.ae_to_fde_ratio > 0 else 0
        fdes_for_mm = aes_midmarket / mm_ratios.ae_to_fde_ratio if mm_ratios.ae_to_fde_ratio > 0 else 0
        total_fdes = math.ceil(fdes_for_ent + fdes_for_mm)

    # Derive AE Managers by segment
    ae_mgrs_ent = math.ceil(aes_enterprise / ent_ratios.ae_to_manager_ratio) if aes_enterprise > 0 else 0
    ae_mgrs_mm = math.ceil(aes_midmarket / mm_ratios.ae_to_manager_ratio) if aes_midmarket > 0 else 0

    # Derive SE Managers
    se_managers = math.ceil(total_ses / ratios.se_to_manager_ratio) if total_ses > 0 else 0

    # Derive SDR Managers
    sdr_managers = math.ceil(total_sdrs / ratios.sdr_to_manager_ratio) if total_sdrs > 0 else 0

    # Derive CSM Managers
    csm_managers = math.ceil(total_csms / ratios.csm_to_manager_ratio) if total_csms > 0 else 0

    return DerivedTeam(
        aes_enterprise=aes_enterprise,
        aes_midmarket=aes_midmarket,
        ses=total_ses,
        sdrs=total_sdrs,
        csms=total_csms,
        fdes=total_fdes,
        ae_managers_enterprise=ae_mgrs_ent,
        ae_managers_midmarket=ae_mgrs_mm,
        se_managers=se_managers,
        sdr_managers=sdr_managers,
        csm_managers=csm_managers,
        enterprise_pct=enterprise_pct,
        midmarket_pct=1.0 - enterprise_pct,
    )


def derive_team_from_segments(
    aes_enterprise: int,
    aes_midmarket: int,
    ratios: Optional[CoverageRatios] = None,
    include_csm: bool = True,
    include_fde: bool = True,
) -> DerivedTeam:
    """
    Derive team from explicit segment counts.

    Alternative to derive_team() when segment counts are known directly.

    Args:
        aes_enterprise: Enterprise AE count
        aes_midmarket: Mid-Market AE count
        ratios: Coverage ratios to use
        include_csm: Whether to include CSMs
        include_fde: Whether to include FDEs

    Returns:
        DerivedTeam with full headcount breakdown
    """
    total_aes = aes_enterprise + aes_midmarket
    if total_aes == 0:
        return DerivedTeam()

    enterprise_pct = aes_enterprise / total_aes
    return derive_team(
        ae_count=total_aes,
        ratios=ratios,
        enterprise_pct=enterprise_pct,
        include_csm=include_csm,
        include_fde=include_fde,
    )


def calculate_incremental_support(
    add_aes: int,
    current_team: DerivedTeam,
    ratios: Optional[CoverageRatios] = None,
    enterprise_pct: Optional[float] = None,
) -> DerivedTeam:
    """
    Calculate incremental support roles needed when adding AEs.

    "If I add 10 AEs, how many more SEs, SDRs, Managers do I need?"

    Args:
        add_aes: Number of AEs to add
        current_team: Current team composition
        ratios: Coverage ratios to use
        enterprise_pct: Segment mix for new AEs (defaults to current mix)

    Returns:
        DerivedTeam representing the DELTA (incremental headcount needed)
    """
    if ratios is None:
        ratios = CoverageRatios()

    # Use current mix if not specified
    if enterprise_pct is None:
        enterprise_pct = current_team.enterprise_pct

    # Calculate new total team
    new_total_aes = current_team.total_aes + add_aes
    new_team = derive_team(
        ae_count=new_total_aes,
        ratios=ratios,
        enterprise_pct=enterprise_pct,
    )

    # Calculate delta
    return DerivedTeam(
        aes_enterprise=new_team.aes_enterprise - current_team.aes_enterprise,
        aes_midmarket=new_team.aes_midmarket - current_team.aes_midmarket,
        ses=new_team.ses - current_team.ses,
        sdrs=new_team.sdrs - current_team.sdrs,
        csms=new_team.csms - current_team.csms,
        fdes=new_team.fdes - current_team.fdes,
        ae_managers_enterprise=new_team.ae_managers_enterprise - current_team.ae_managers_enterprise,
        ae_managers_midmarket=new_team.ae_managers_midmarket - current_team.ae_managers_midmarket,
        se_managers=new_team.se_managers - current_team.se_managers,
        sdr_managers=new_team.sdr_managers - current_team.sdr_managers,
        csm_managers=new_team.csm_managers - current_team.csm_managers,
        enterprise_pct=enterprise_pct,
        midmarket_pct=1.0 - enterprise_pct,
    )


def team_from_headcount(
    aes_enterprise: int = 0,
    aes_midmarket: int = 0,
    ses: int = 0,
    sdrs: int = 0,
    csms: int = 0,
    fdes: int = 0,
    ae_managers: int = 0,
    se_managers: int = 0,
    sdr_managers: int = 0,
    csm_managers: int = 0,
) -> DerivedTeam:
    """
    Create DerivedTeam from explicit headcount values.

    Useful for representing current team state from Salesforce or manual input.

    Args:
        aes_enterprise: Enterprise AE count
        aes_midmarket: Mid-Market AE count
        ses: SE count
        sdrs: SDR count
        csms: CSM count
        fdes: FDE count
        ae_managers: Total AE managers (split evenly between segments)
        se_managers: SE manager count
        sdr_managers: SDR manager count
        csm_managers: CSM manager count

    Returns:
        DerivedTeam representing the provided headcount
    """
    total_aes = aes_enterprise + aes_midmarket
    enterprise_pct = aes_enterprise / total_aes if total_aes > 0 else 0.5

    # Split AE managers by segment proportionally
    ae_mgrs_ent = int(round(ae_managers * enterprise_pct))
    ae_mgrs_mm = ae_managers - ae_mgrs_ent

    return DerivedTeam(
        aes_enterprise=aes_enterprise,
        aes_midmarket=aes_midmarket,
        ses=ses,
        sdrs=sdrs,
        csms=csms,
        fdes=fdes,
        ae_managers_enterprise=ae_mgrs_ent,
        ae_managers_midmarket=ae_mgrs_mm,
        se_managers=se_managers,
        sdr_managers=sdr_managers,
        csm_managers=csm_managers,
        enterprise_pct=enterprise_pct,
        midmarket_pct=1.0 - enterprise_pct,
    )


def validate_coverage(
    team: DerivedTeam,
    ratios: Optional[CoverageRatios] = None,
) -> dict:
    """
    Validate team coverage against ratios.

    Identifies under-staffed or over-staffed roles.

    Args:
        team: Current team composition
        ratios: Target coverage ratios

    Returns:
        Dict with coverage analysis for each role
    """
    if ratios is None:
        ratios = CoverageRatios()

    # Calculate expected headcount
    expected = derive_team(
        ae_count=team.total_aes,
        ratios=ratios,
        enterprise_pct=team.enterprise_pct,
    )

    def _coverage_status(actual: int, expected: int) -> str:
        if expected == 0:
            return "N/A"
        ratio = actual / expected
        if ratio < 0.8:
            return "UNDERSTAFFED"
        elif ratio > 1.2:
            return "OVERSTAFFED"
        else:
            return "OK"

    return {
        "ses": {
            "actual": team.ses,
            "expected": expected.ses,
            "delta": team.ses - expected.ses,
            "status": _coverage_status(team.ses, expected.ses),
        },
        "sdrs": {
            "actual": team.sdrs,
            "expected": expected.sdrs,
            "delta": team.sdrs - expected.sdrs,
            "status": _coverage_status(team.sdrs, expected.sdrs),
        },
        "csms": {
            "actual": team.csms,
            "expected": expected.csms,
            "delta": team.csms - expected.csms,
            "status": _coverage_status(team.csms, expected.csms),
        },
        "fdes": {
            "actual": team.fdes,
            "expected": expected.fdes,
            "delta": team.fdes - expected.fdes,
            "status": _coverage_status(team.fdes, expected.fdes),
        },
        "ae_managers": {
            "actual": team.total_ae_managers,
            "expected": expected.total_ae_managers,
            "delta": team.total_ae_managers - expected.total_ae_managers,
            "status": _coverage_status(team.total_ae_managers, expected.total_ae_managers),
        },
        "se_managers": {
            "actual": team.se_managers,
            "expected": expected.se_managers,
            "delta": team.se_managers - expected.se_managers,
            "status": _coverage_status(team.se_managers, expected.se_managers),
        },
        "sdr_managers": {
            "actual": team.sdr_managers,
            "expected": expected.sdr_managers,
            "delta": team.sdr_managers - expected.sdr_managers,
            "status": _coverage_status(team.sdr_managers, expected.sdr_managers),
        },
    }

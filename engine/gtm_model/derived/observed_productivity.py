"""Pure-function ports of AE productivity / ramp metrics.

Ports of:
- `_get_observed_ae_productivity()` — bookings per AE per quarter
- `_get_observed_ae_ramp_curve()` — productivity by tenure month

Legacy implementations (engine/gtm_model/tieout/runtime/observed.py
and the runtime snapshot builder) tie productivity calculations to
roster + bookings + tenure heuristics. The pure functions here operate
on raw deals + team_members + a reference date.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from engine.connectors.interface import Deal, TeamMember


@dataclass
class ProductivityProfile:
    """Per-AE bookings productivity over a lookback window."""

    by_ae: dict[str, float] = field(default_factory=dict)  # ae_id -> bookings
    by_segment: dict[str, float] = field(default_factory=dict)
    overall_avg: Optional[float] = None
    lookback_days: int = 0


@dataclass
class RampCurve:
    """Productivity by tenure month (0 = first month, 1 = second, etc.)."""

    monthly_productivity: dict[int, float] = field(default_factory=dict)
    sample_size: int = 0


def compute_observed_productivity(
    deals: Iterable[Deal],
    team_members: Iterable[TeamMember],
    as_of: date,
    lookback_days: int = 180,
) -> ProductivityProfile:
    """Average bookings per AE in the trailing lookback window.

    Args:
        deals: All deals from the connector. Only is_won deals contribute.
        team_members: Team roster — used to filter "AE" role only and
            optionally segment.
        as_of: Reference date for the lookback window.
        lookback_days: Window length in days.

    Returns:
        ProductivityProfile with per-AE and per-segment totals plus an
        overall average. Bookings amounts use Year_1_ARR if available,
        else Amount.
    """
    from datetime import timedelta

    cutoff = as_of - timedelta(days=lookback_days)
    aes = {tm.id: tm for tm in team_members if tm.role == "AE"}

    by_ae: dict[str, float] = defaultdict(float)
    by_segment: dict[str, float] = defaultdict(float)

    for deal in deals:
        if not deal.is_won or deal.close_date is None:
            continue
        if not (cutoff <= deal.close_date <= as_of):
            continue
        if deal.owner_id not in aes:
            continue
        bookings = float(
            deal.year_1_arr if deal.year_1_arr is not None else (deal.amount or 0.0)
        )
        by_ae[deal.owner_id] += bookings
        ae = aes[deal.owner_id]
        if ae.segment:
            by_segment[ae.segment] += bookings

    overall_avg = (
        sum(by_ae.values()) / len(by_ae) if by_ae else None
    )

    return ProductivityProfile(
        by_ae=dict(by_ae),
        by_segment=dict(by_segment),
        overall_avg=overall_avg,
        lookback_days=lookback_days,
    )


def compute_observed_ae_ramp_curve(
    deals: Iterable[Deal],
    team_members: Iterable[TeamMember],
    as_of: date,
    lookback_days: int = 365,
) -> RampCurve:
    """Average bookings by tenure month (0-indexed from start_date).

    Args:
        deals: All deals from the connector.
        team_members: Roster — uses .start_date to compute tenure.
        as_of: Reference date.
        lookback_days: Window for which closed-won deals contribute.

    Returns:
        RampCurve with per-tenure-month productivity. Tenure month is
        computed from the AE's start_date to the deal's close_date.
    """
    from datetime import timedelta

    cutoff = as_of - timedelta(days=lookback_days)
    aes = {
        tm.id: tm for tm in team_members
        if tm.role == "AE" and tm.start_date is not None
    }

    monthly_totals: dict[int, list[float]] = defaultdict(list)

    for deal in deals:
        if not deal.is_won or deal.close_date is None:
            continue
        if not (cutoff <= deal.close_date <= as_of):
            continue
        ae = aes.get(deal.owner_id)
        if ae is None or ae.start_date is None:
            continue
        # Approximate tenure month: full months between start_date and close_date
        delta_days = (deal.close_date - ae.start_date).days
        if delta_days < 0:
            continue
        tenure_month = delta_days // 30
        bookings = float(
            deal.year_1_arr if deal.year_1_arr is not None else (deal.amount or 0.0)
        )
        monthly_totals[tenure_month].append(bookings)

    monthly_productivity = {
        month: sum(values) / len(values)
        for month, values in monthly_totals.items()
        if values
    }

    return RampCurve(
        monthly_productivity=monthly_productivity,
        sample_size=sum(len(v) for v in monthly_totals.values()),
    )

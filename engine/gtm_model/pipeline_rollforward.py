from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from connectors.field_mapping import get_stage_mapping

from .cohort_model import apply_capacity_ceiling, stack_cohorts
from .funnel_engine import classify_opportunity_source


OPEN_STAGE_ORDER = ["S0", "S1", "S2", "S3", "S4", "S5"]


@dataclass
class OpenOpportunity:
    """Single open opportunity carried into the roll-forward forecast."""

    opp_id: str
    stage: str
    amount: float = 0.0
    arr: float = 0.0
    close_date: Optional[date] = None
    created_date: Optional[date] = None
    source_stream: str = "unknown"
    opp_type: str = ""
    raw_stage_name: str = ""
    record_type_name: str = ""
    forecast_category: str = ""
    owner_name: str = ""
    metric_source: str = ""

    @property
    def metric_value(self) -> float:
        """Prefer ARR when populated, otherwise use Amount."""
        return float(self.arr or 0.0) if float(self.arr or 0.0) > 0 else float(self.amount or 0.0)

    @property
    def is_renewal(self) -> bool:
        raw = f"{self.opp_type} {self.record_type_name}".lower()
        return "renewal" in raw

    @property
    def is_open_stage(self) -> bool:
        return self.stage in OPEN_STAGE_ORDER


@dataclass
class OpenInventorySnapshot:
    """Current open inventory carried into the monthly roll-forward."""

    as_of: date
    opportunities: list[OpenOpportunity] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    @property
    def opportunity_count(self) -> int:
        return len(self.opportunities)

    @property
    def total_metric_value(self) -> float:
        return sum(opp.metric_value for opp in self.opportunities)


@dataclass
class RollforwardProjection:
    """Monthly roll-forward output consumed by the planning UI."""

    months: list[date]
    existing_inventory_wins: list[float]
    existing_inventory_losses: list[float]
    existing_inventory_remaining: list[float]
    future_pipeline_created: list[float]
    future_generation_wins: list[float]
    total_expected_wins: list[float]
    capacity_capped_wins: list[float]
    overflow_backlog: list[float]
    provenance: dict = field(default_factory=dict)


def _parse_date(value: object) -> Optional[date]:
    """Parse loose date/datetime string payloads from SF/warehouse rows."""
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "")
    if "T" in text:
        text = text.split("T", 1)[0]

    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _align(values: list[float], length: int) -> list[float]:
    series = list(values or [])
    if len(series) < length:
        series.extend([0.0] * (length - len(series)))
    return [float(v or 0.0) for v in series[:length]]


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _month_index(months: list[date], target: Optional[date]) -> Optional[int]:
    if not months:
        return None
    if target is None:
        return 0

    first = _month_start(months[0])
    last = _month_start(months[-1])
    bucket = _month_start(target)
    if bucket <= first:
        return 0
    if bucket >= last:
        return len(months) - 1
    for idx, month in enumerate(months):
        if _month_start(month) == bucket:
            return idx
    return None


def _remaining_stage_days(stage: str, stage_velocity_days: dict[str, float]) -> int:
    if stage not in OPEN_STAGE_ORDER:
        return 30
    stage_idx = OPEN_STAGE_ORDER.index(stage)
    remaining = sum(float(stage_velocity_days.get(stage_name, 0.0) or 0.0) for stage_name in OPEN_STAGE_ORDER[stage_idx:])
    return int(max(round(remaining), 1))


def _compute_overflow(expected: list[float], capacity: list[float], overflow_mode: str) -> list[float]:
    """Mirror the carry logic used by the capacity ceiling."""
    overflow = [0.0] * len(expected)
    carry = 0.0
    for idx, (exp, cap) in enumerate(zip(expected, capacity)):
        available = exp + carry if overflow_mode == "push" else exp
        if available <= cap:
            overflow[idx] = 0.0
            carry = 0.0
        else:
            overflow[idx] = available - cap
            carry = overflow[idx] if overflow_mode == "push" else 0.0
    return overflow


def build_open_inventory_snapshot_from_salesforce(
    rows: list[dict],
    *,
    as_of: date,
) -> OpenInventorySnapshot:
    """Normalize Salesforce open opportunity rows into the roll-forward contract."""
    opportunities = []
    for row in rows or []:
        opp = OpenOpportunity(
            opp_id=str(row.get("Id") or row.get("id") or ""),
            stage=get_stage_mapping(str(row.get("StageName") or "").strip()),
            amount=float(row.get("Amount") or 0.0),
            arr=float(row.get("ARR__c") or 0.0),
            close_date=_parse_date(row.get("CloseDate")),
            created_date=_parse_date(row.get("CreatedDate")),
            source_stream="unknown",
            opp_type=str(row.get("Type") or ""),
            raw_stage_name=str(row.get("StageName") or ""),
            metric_source="Salesforce",
        )
        opportunities.append(opp)

    return OpenInventorySnapshot(
        as_of=as_of,
        opportunities=opportunities,
        provenance={
            "source": "Salesforce",
            "is_live": True,
            "metric_selection": "ARR__c else Amount",
        },
    )


def build_open_inventory_snapshot_from_cdw(
    rows: list[dict],
    *,
    as_of: date,
) -> OpenInventorySnapshot:
    """Normalize warehouse open opportunity rows into the roll-forward contract."""
    opportunities = []
    for row in rows or []:
        opp = OpenOpportunity(
            opp_id=str(row.get("opp_id") or row.get("OPP_ID") or ""),
            stage=get_stage_mapping(str(row.get("stage_name") or row.get("STAGE_NAME") or "").strip()),
            amount=float(row.get("amount") or row.get("AMOUNT") or 0.0),
            arr=float(row.get("arr") or row.get("ARR") or 0.0),
            close_date=_parse_date(row.get("close_date") or row.get("CLOSE_DATE")),
            created_date=_parse_date(row.get("created_date") or row.get("CREATED_DATE")),
            source_stream=classify_opportunity_source(
                {
                    "record_type_name": row.get("record_type_name") or row.get("RECORD_TYPE_NAME"),
                    "source_category": row.get("source_category") or row.get("SOURCE_CATEGORY"),
                }
            ),
            opp_type=str(row.get("type") or row.get("TYPE") or ""),
            raw_stage_name=str(row.get("stage_name") or row.get("STAGE_NAME") or ""),
            record_type_name=str(row.get("record_type_name") or row.get("RECORD_TYPE_NAME") or ""),
            forecast_category=str(row.get("forecast_category") or row.get("FORECAST_CATEGORY") or ""),
            owner_name=str(row.get("owner_name") or row.get("OWNER_NAME") or ""),
            metric_source="warehouse",
        )
        opportunities.append(opp)

    return OpenInventorySnapshot(
        as_of=as_of,
        opportunities=opportunities,
        provenance={
            "source": "warehouse",
            "is_live": True,
            "metric_selection": "ARR else Amount",
        },
    )


def project_existing_inventory(
    snapshot: OpenInventorySnapshot,
    *,
    months: list[date],
    stage_win_rates: dict[str, float],
    stage_velocity_days: dict[str, float],
) -> dict[str, list[float]]:
    """Project current open inventory into monthly expected wins and losses."""
    existing_wins = [0.0] * len(months)
    existing_losses = [0.0] * len(months)
    starting_inventory = 0.0

    # Provenance tracking
    by_stage: dict[str, float] = {}          # stage → total inventory $
    count_by_stage: dict[str, int] = {}      # stage → deal count
    by_resolution: dict[str, int] = {"close_date": 0, "velocity": 0, "out_of_range": 0}
    by_stage_month_wins: dict[str, list[float]] = {}  # stage → monthly wins

    for opp in snapshot.opportunities:
        if not opp.is_open_stage or opp.is_renewal:
            continue
        value = opp.metric_value
        if value <= 0:
            continue

        starting_inventory += value
        stage = opp.stage or "unknown"
        by_stage[stage] = by_stage.get(stage, 0.0) + value
        count_by_stage[stage] = count_by_stage.get(stage, 0) + 1
        win_rate = float(stage_win_rates.get(stage, 0.0) or 0.0)

        if opp.close_date and opp.close_date >= snapshot.as_of:
            resolution_date = opp.close_date
            by_resolution["close_date"] += 1
        else:
            resolution_date = snapshot.as_of + timedelta(days=_remaining_stage_days(stage, stage_velocity_days))
            by_resolution["velocity"] += 1

        idx = _month_index(months, resolution_date)
        if idx is None:
            by_resolution["out_of_range"] += 1
            continue

        existing_wins[idx] += value * win_rate
        existing_losses[idx] += value * max(1.0 - win_rate, 0.0)

        # Track wins by stage
        if stage not in by_stage_month_wins:
            by_stage_month_wins[stage] = [0.0] * len(months)
        by_stage_month_wins[stage][idx] += value * win_rate

    remaining = []
    balance = starting_inventory
    for idx in range(len(months)):
        remaining.append(max(balance, 0.0))
        balance = max(balance - existing_wins[idx] - existing_losses[idx], 0.0)

    return {
        "wins": existing_wins,
        "losses": existing_losses,
        "remaining": remaining,
        "provenance": {
            "starting_inventory": starting_inventory,
            "inventory_by_stage": by_stage,
            "inventory_count_by_stage": count_by_stage,
            "resolution_method_counts": by_resolution,
            "wins_by_stage_month": by_stage_month_wins,
        },
    }


def project_future_generation(
    monthly_pipeline_created: list[float],
    *,
    months: list[date],
    close_timing_curve: list[float],
    s2_to_won_rate: float,
    monthly_win_rates: Optional[list[float]] = None,
) -> dict[str, list[float]]:
    """Project future generated pipeline into expected closed-won value."""
    aligned_creation = _align(monthly_pipeline_created, len(months))
    if monthly_win_rates is None:
        effective_win_rates = [float(s2_to_won_rate or 0.0)] * len(months)
    else:
        effective_win_rates = _align(monthly_win_rates, len(months))
    win_adjusted_creation = [
        value * rate
        for value, rate in zip(aligned_creation, effective_win_rates)
    ]
    expected = stack_cohorts(win_adjusted_creation, close_timing_curve)
    return {
        "pipeline_created": aligned_creation,
        "wins": _align(expected, len(months)),
        "win_rates": effective_win_rates,
    }


def project_pipeline_rollforward(
    *,
    inventory_snapshot: OpenInventorySnapshot,
    monthly_pipeline_created: list[float],
    months: list[date],
    stage_win_rates: dict[str, float],
    stage_velocity_days: dict[str, float],
    close_timing_curve: list[float],
    s2_to_won_rate: float,
    monthly_capacity: Optional[list[float]] = None,
    overflow_mode: str = "push",
    monthly_future_generation_win_rates: Optional[list[float]] = None,
    future_generation_basis: Optional[list[str]] = None,
) -> RollforwardProjection:
    """Combine existing inventory runoff with future generation into one monthly view."""
    existing = project_existing_inventory(
        inventory_snapshot,
        months=months,
        stage_win_rates=stage_win_rates,
        stage_velocity_days=stage_velocity_days,
    )
    future = project_future_generation(
        monthly_pipeline_created,
        months=months,
        close_timing_curve=close_timing_curve,
        s2_to_won_rate=s2_to_won_rate,
        monthly_win_rates=monthly_future_generation_win_rates,
    )
    effective_win_rates = list(future.get("win_rates", []) or [])
    if future_generation_basis is None:
        basis_series = ["s2_pipeline_created"] * len(months)
    else:
        basis_series = [str(value or "s2_pipeline_created") for value in future_generation_basis[:len(months)]]
        if len(basis_series) < len(months):
            basis_series.extend(["s2_pipeline_created"] * (len(months) - len(basis_series)))

    total_expected = [
        existing["wins"][idx] + future["wins"][idx]
        for idx in range(len(months))
    ]

    if monthly_capacity:
        capacity = _align(monthly_capacity, len(months))
        capped = apply_capacity_ceiling(total_expected, capacity, overflow=overflow_mode)
        overflow = _compute_overflow(total_expected, capacity, overflow_mode)
    else:
        capped = list(total_expected)
        overflow = [0.0] * len(total_expected)

    return RollforwardProjection(
        months=list(months),
        existing_inventory_wins=existing["wins"],
        existing_inventory_losses=existing["losses"],
        existing_inventory_remaining=existing["remaining"],
        future_pipeline_created=future["pipeline_created"],
        future_generation_wins=future["wins"],
        total_expected_wins=total_expected,
        capacity_capped_wins=capped,
        overflow_backlog=overflow,
        provenance={
            "inventory_source": inventory_snapshot.provenance.get("source", "unavailable"),
            "fallback_from": inventory_snapshot.provenance.get("fallback_from"),
            "fallback_reason": inventory_snapshot.provenance.get("fallback_reason"),
            "inventory_is_live": inventory_snapshot.provenance.get("is_live"),
            "inventory_opportunity_count": inventory_snapshot.opportunity_count,
            "inventory_metric_selection": inventory_snapshot.provenance.get("metric_selection", "ARR__c else Amount"),
            "future_generation_method": "monthly_pipeline_created x monthly_future_generation_win_rate x close_timing_curve",
            "future_generation_basis": basis_series,
            "future_generation_win_rates": effective_win_rates,
            "as_of": inventory_snapshot.as_of.isoformat(),
            "capacity_treatment": overflow_mode,
            **(existing.get("provenance", {})),
        },
    )

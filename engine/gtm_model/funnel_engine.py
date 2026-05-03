"""
Funnel Engine: Three-source pipeline model with rate fallback.

Implements the config-driven pipeline-creation helpers. Takes actual
volumes and conversion rates from a warehouse adapter (provided by
forkers) and projects pipeline creation by source (Marketing/SDR, PLG,
AE Self-Gen).

The `build_funnel_from_cdw(cdw, quarter)` entry point expects a
warehouse-adapter instance with the same query surface a forker would
write — `get_funnel_volumes(quarter)`, `get_conversion_rates_by_source()`,
`get_attribution_summary(quarter)`, `get_plg_funnel(quarter)`. No
default warehouse adapter ships with the OSS.
"""

from __future__ import annotations

import logging
from typing import Optional

from .rate_defaults import get_default_funnel_rates
from .rate_registry import RateSemantic, get_default_registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SELF_SERVE_RECORD_TYPE_NAME = "Self Serve"

# warehouse SOURCE_CATEGORY -> model stream
SOURCE_TO_STREAM_MAP: dict[str, str] = {
    "Marketing Sourced": "marketing_sdr",
    "SDR Sourced": "marketing_sdr",
    "AE Sourced": "ae_selfgen",
    "Leadership Sourced": "ae_selfgen",
    "SE Sourced": "ae_selfgen",
    "Enrichment": "ae_selfgen",
    "Unknown": "ae_selfgen",
}


def _load_plan_rates() -> dict[str, float]:
    """Load tier-3 fallback rates for funnel projections.

    Core funnel rates come from the canonical registry-backed defaults.
    PLG rates remain local legacy assumptions until they are modeled in the
    registry with clearer semantics. The legacy PLG fallback is still stored
    as PQL -> S0 so the stage-1 entry equivalent can be derived without
    changing historical throughput.
    """
    defaults = {
        **get_default_funnel_rates(),
        "plg_signup_to_pql": 0.05,
        "plg_pql_to_s0": 0.20,
    }
    return defaults


# Plan rates used as tier-3 fallback when warehouse data is insufficient.
# Core funnel rates resolve via the central registry-backed defaults.
_PLAN_RATES: dict[str, float] = _load_plan_rates()

_PLAN_RATE_SEMANTICS: dict[str, RateSemantic] = {
    "mql_to_s0": RateSemantic.ACTIVITY_RATE,
    "s0_to_s1": RateSemantic.SEQUENTIAL_TRANSITION,
    "s1_to_s2": RateSemantic.SEQUENTIAL_TRANSITION,
    "s2_to_s3": RateSemantic.SEQUENTIAL_TRANSITION,
    "s3_to_s4": RateSemantic.SEQUENTIAL_TRANSITION,
    "s4_to_s5": RateSemantic.SEQUENTIAL_TRANSITION,
    "s5_to_won": RateSemantic.SEQUENTIAL_TRANSITION,
}


def _get_plan_rate(key: str) -> float:
    """Resolve a tier-3 fallback rate, preserving the registry override seam."""
    default = float(_PLAN_RATES.get(key, 0.0) or 0.0)
    semantic = _PLAN_RATE_SEMANTICS.get(key)
    if semantic is None:
        return default
    return float(get_default_registry().try_get(key, semantic, default=default))


def _get_plan_rate_fallbacks() -> dict[str, float]:
    """Resolve all fallback plan rates used by the funnel engine."""
    return {key: _get_plan_rate(key) for key in _PLAN_RATES}


def _resolve_plg_pql_to_s1_rate(rates: dict, plan_rates: dict, s0_to_s1: float) -> float:
    """Resolve the canonical PLG PQL -> S1 rate.

    The new semantics treat PLG opportunities as entering directly at S1.
    For backwards compatibility, legacy PQL -> S0 inputs are translated into
    a stage-1-equivalent rate using the current S0 -> S1 rate.
    """
    explicit_s1 = rates.get("plg_pql_to_s1")
    if explicit_s1 is not None:
        return float(explicit_s1)

    legacy_s0 = rates.get("plg_pql_to_s0")
    if legacy_s0 is not None:
        return float(legacy_s0) * s0_to_s1

    fallback_s1 = plan_rates.get("plg_pql_to_s1")
    if fallback_s1 is not None:
        return float(fallback_s1)

    return float(plan_rates.get("plg_pql_to_s0", 0.0) or 0.0) * s0_to_s1


# ---------------------------------------------------------------------------
# 1. Source-to-stream mapping
# ---------------------------------------------------------------------------

def map_source_to_stream(source_category: Optional[str]) -> str:
    """Map a warehouse first_touch_source_category to one of three model streams.

    Args:
        source_category: warehouse source category string (e.g. "Marketing Sourced").

    Returns:
        One of "marketing_sdr", "ae_selfgen", or "plg".
        Unknown/None/unmapped values default to "ae_selfgen".
    """
    if not source_category:
        return "ae_selfgen"
    return SOURCE_TO_STREAM_MAP.get(source_category, "ae_selfgen")


# ---------------------------------------------------------------------------
# 2. Opportunity classification (PLG override)
# ---------------------------------------------------------------------------

def classify_opportunity_source(opp: dict) -> str:
    """Classify an opportunity into a model stream.

    Uses record_type_name for the PLG override (Self Serve record type), then
    falls back to attribution-based mapping via map_source_to_stream.

    Args:
        opp: Dict with optional key "record_type_name" and
             "source_category" / "first_touch_source_category".

    Returns:
        "marketing_sdr", "ae_selfgen", or "plg".
    """
    record_type_name = opp.get("record_type_name")
    if record_type_name == SELF_SERVE_RECORD_TYPE_NAME:
        return "plg"

    source = opp.get("source_category") or opp.get("first_touch_source_category")
    return map_source_to_stream(source)


# ---------------------------------------------------------------------------
# 3. Rate fallback hierarchy
# ---------------------------------------------------------------------------

def get_conversion_rate(
    stream: str,
    per_source: dict,
    blended: dict,
    plan: float,
    min_n: int = 20,
) -> dict:
    """Three-tier rate fallback: observed -> blended -> plan.

    Tier 1: Use per-source rate if stream is present with n >= min_n and
            rate is not None.
    Tier 2: Use blended rate if n >= 1 and rate is not None.
    Tier 3: Fall back to the plan rate.

    Args:
        stream: Model stream name (e.g. "marketing_sdr").
        per_source: Dict mapping stream -> {"rate": float, "n": int}.
        blended: {"rate": float|None, "n": int} for the blended population.
        plan: Plan/default rate as a float.
        min_n: Minimum sample size to trust per-source rate.

    Returns:
        {"rate": float, "n": int, "source": str} where source is
        "observed", "blended", or "plan".
    """
    # Tier 1: per-source observed rate
    if stream in per_source:
        entry = per_source[stream]
        n = entry.get("n", 0)
        rate = entry.get("rate")
        if n >= min_n and rate is not None:
            return {"rate": rate, "n": n, "source": "observed"}

    # Tier 2: blended rate
    blended_n = blended.get("n", 0)
    blended_rate = blended.get("rate")
    if blended_n >= 1 and blended_rate is not None:
        return {"rate": blended_rate, "n": blended_n, "source": "blended"}

    # Tier 3: plan rate
    return {"rate": plan, "n": 0, "source": "plan"}


# ---------------------------------------------------------------------------
# 4. Single funnel stream projection
# ---------------------------------------------------------------------------

def _split_weeks_into_months(weeks: int) -> list[int]:
    """Split a quarter's week count into three month buckets."""
    base_weeks_per_month = weeks // 3
    remainder = weeks - base_weeks_per_month * 3
    month_weeks = [base_weeks_per_month] * 3
    for i in range(remainder):
        month_weeks[2 - i] += 1
    return month_weeks


def _monthly_from_weekly(weekly_value: float, weeks: int) -> list[float]:
    """Expand a weekly metric into 3 monthly buckets using the quarter week split."""
    return [weekly_value * month_weeks for month_weeks in _split_weeks_into_months(weeks)]


def _annotate_projection(
    projection: dict,
    *,
    stream_key: str,
    display_name: str,
    input_label: str,
    weekly_input: float,
    weeks: int,
) -> dict:
    """Attach stream metadata used by drill-down views and exports."""
    annotated = dict(projection)
    annotated["stream_key"] = stream_key
    annotated["display_name"] = display_name
    annotated["input_label"] = input_label
    annotated["weekly_input"] = weekly_input
    annotated["monthly_input"] = _monthly_from_weekly(weekly_input, weeks)
    return annotated


def project_funnel(
    weekly_input: int,
    mql_to_s0: float,
    s0_to_s1: float,
    s1_to_s2: float,
    avg_s2_deal_size: float,
    weeks: int = 13,
) -> dict:
    """Project a single funnel stream from input to S2 pipeline creation.

    Applies conversion rates sequentially:
        input -> S0 -> S1 -> S2

    For Marketing/SDR, the input is MQLs and mql_to_s0 is used.
    For AE Self-Gen, set mql_to_s0=1.0 (enters at S0).
    PLG/self-serve motions that enter directly at S1 should use
    ``project_stage1_funnel()`` instead.

    Args:
        weekly_input: Weekly volume entering the funnel.
        mql_to_s0: Conversion rate from input to S0.
        s0_to_s1: Conversion rate S0 -> S1.
        s1_to_s2: Conversion rate S1 -> S2.
        avg_s2_deal_size: Average deal size at S2.
        weeks: Number of weeks in the projection period (default 13 = 1 quarter).

    Returns:
        {
            "weekly_s0_count": float,
            "weekly_s1_count": float,
            "weekly_s2_count": float,
            "total_s2_pipeline": float,
            "monthly_creation": list[float]  # 3 months (weeks split ~4/4/5)
        }
    """
    weekly_s0_count = weekly_input * mql_to_s0
    weekly_s1_count = weekly_s0_count * s0_to_s1
    weekly_s2_count = weekly_s1_count * s1_to_s2
    total_s2_count = weekly_s2_count * weeks
    total_s2_pipeline = total_s2_count * avg_s2_deal_size

    month_weeks = _split_weeks_into_months(weeks)

    monthly_creation = [
        weekly_s2_count * mw * avg_s2_deal_size
        for mw in month_weeks
    ]

    return {
        "weekly_input": weekly_input,
        "weekly_s0_count": weekly_s0_count,
        "weekly_s1_count": weekly_s1_count,
        "weekly_s2_count": weekly_s2_count,
        "total_s2_pipeline": total_s2_pipeline,
        "monthly_input": [weekly_input * mw for mw in month_weeks],
        "monthly_s0_count": [weekly_s0_count * mw for mw in month_weeks],
        "monthly_s1_count": [weekly_s1_count * mw for mw in month_weeks],
        "monthly_s2_count": [weekly_s2_count * mw for mw in month_weeks],
        "monthly_creation": monthly_creation,
    }


def project_stage1_funnel(
    weekly_input: float,
    input_to_s1: float,
    s1_to_s2: float,
    avg_s2_deal_size: float,
    weeks: int = 13,
) -> dict:
    """Project a funnel stream that enters directly at S1.

    This is used for PLG/self-serve motions where the opportunity record does
    not carry an S0 stage. The returned payload preserves the common shape used
    by exports and UI tables, with S0 counts pinned to zero.
    """
    weekly_s1_count = weekly_input * input_to_s1
    weekly_s2_count = weekly_s1_count * s1_to_s2
    total_s2_count = weekly_s2_count * weeks
    total_s2_pipeline = total_s2_count * avg_s2_deal_size

    month_weeks = _split_weeks_into_months(weeks)
    zero_months = [0.0] * len(month_weeks)
    monthly_creation = [
        weekly_s2_count * mw * avg_s2_deal_size
        for mw in month_weeks
    ]

    return {
        "weekly_input": weekly_input,
        "weekly_s0_count": 0.0,
        "weekly_s1_count": weekly_s1_count,
        "weekly_s2_count": weekly_s2_count,
        "total_s2_pipeline": total_s2_pipeline,
        "monthly_input": [weekly_input * mw for mw in month_weeks],
        "monthly_s0_count": zero_months,
        "monthly_s1_count": [weekly_s1_count * mw for mw in month_weeks],
        "monthly_s2_count": [weekly_s2_count * mw for mw in month_weeks],
        "monthly_creation": monthly_creation,
    }


def _combine_stream_projections(stream_projections: dict[str, dict]) -> dict:
    """Add aggregate funnel totals across a set of per-stream projections."""
    if not stream_projections:
        return {"total_monthly_creation": []}

    num_months = len(next(iter(stream_projections.values())).get("monthly_creation", []))
    total_monthly = [
        sum(projection["monthly_creation"][i] for projection in stream_projections.values())
        for i in range(num_months)
    ]

    combined = dict(stream_projections)
    combined["total_monthly_creation"] = total_monthly
    combined["total_weekly_s0_count"] = sum(
        projection.get("weekly_s0_count", 0.0)
        for projection in stream_projections.values()
    )
    combined["total_weekly_s1_count"] = sum(
        projection.get("weekly_s1_count", 0.0)
        for projection in stream_projections.values()
    )
    combined["total_weekly_s2_count"] = sum(
        projection.get("weekly_s2_count", 0.0)
        for projection in stream_projections.values()
    )
    return combined


# ---------------------------------------------------------------------------
# 5. Three-source pipeline computation
# ---------------------------------------------------------------------------

def compute_three_source_pipeline(
    marketing_sdr_mqls_weekly: int,
    ae_selfgen_s0_weekly: int,
    plg_signups_weekly: int,
    rates: dict,
    weeks: int = 13,
    avg_deal_size: float = 300_000,
) -> dict:
    """Compute pipeline creation from all three source streams.

    Funnel paths:
        Marketing/SDR: MQLs -> S0 -> S1 -> S2
        AE Self-Gen:   S0 -> S1 -> S2  (enters at S0)
        PLG:           Signups -> PQLs -> S1 -> S2

    Args:
        marketing_sdr_mqls_weekly: Weekly MQL volume for marketing/SDR stream.
        ae_selfgen_s0_weekly: Weekly S0 volume for AE self-gen stream.
        plg_signups_weekly: Weekly signup volume for PLG stream.
        rates: Dict of conversion rates with keys:
            mql_to_s0, s0_to_s1, s1_to_s2, plg_signup_to_pql, plg_pql_to_s1
        weeks: Number of weeks to project (default 13).
        avg_deal_size: Average deal size at S2.

    Returns:
        {
            "marketing_sdr": {weekly_s2_count, total_s2_pipeline, monthly_creation},
            "ae_selfgen": {weekly_s2_count, total_s2_pipeline, monthly_creation},
            "plg": {weekly_s2_count, total_s2_pipeline, monthly_creation},
            "total_monthly_creation": list[float],
            "total_weekly_s0_count": float,
            "total_weekly_s1_count": float,
            "total_weekly_s2_count": float,
        }
    """
    plan_rates = _get_plan_rate_fallbacks()
    mql_to_s0 = rates.get("mql_to_s0", plan_rates["mql_to_s0"])
    s0_to_s1 = rates.get("s0_to_s1", plan_rates["s0_to_s1"])
    s1_to_s2 = rates.get("s1_to_s2", plan_rates["s1_to_s2"])
    plg_signup_to_pql = rates.get("plg_signup_to_pql", plan_rates["plg_signup_to_pql"])
    plg_pql_to_s1 = _resolve_plg_pql_to_s1_rate(rates, plan_rates, s0_to_s1)

    # Marketing/SDR: MQLs -> S0 -> S1 -> S2
    mkt_result = _annotate_projection(project_funnel(
        weekly_input=marketing_sdr_mqls_weekly,
        mql_to_s0=mql_to_s0,
        s0_to_s1=s0_to_s1,
        s1_to_s2=s1_to_s2,
        avg_s2_deal_size=avg_deal_size,
        weeks=weeks,
    ), stream_key="marketing_sdr", display_name="Marketing / SDR", input_label="MQLs", weekly_input=marketing_sdr_mqls_weekly, weeks=weeks)

    # AE Self-Gen: enters at S0, so mql_to_s0 = 1.0
    ae_result = _annotate_projection(project_funnel(
        weekly_input=ae_selfgen_s0_weekly,
        mql_to_s0=1.0,
        s0_to_s1=s0_to_s1,
        s1_to_s2=s1_to_s2,
        avg_s2_deal_size=avg_deal_size,
        weeks=weeks,
    ), stream_key="ae_selfgen", display_name="AE Self-Gen", input_label="S0s", weekly_input=ae_selfgen_s0_weekly, weeks=weeks)

    # PLG: Signups -> PQLs -> S1 -> S2
    plg_result = _annotate_projection(project_stage1_funnel(
        weekly_input=plg_signups_weekly,
        input_to_s1=plg_signup_to_pql * plg_pql_to_s1,
        s1_to_s2=s1_to_s2,
        avg_s2_deal_size=avg_deal_size,
        weeks=weeks,
    ), stream_key="plg", display_name="PLG", input_label="Signups", weekly_input=plg_signups_weekly, weeks=weeks)

    return _combine_stream_projections({
        "marketing_sdr": mkt_result,
        "ae_selfgen": ae_result,
        "plg": plg_result,
    })


# ---------------------------------------------------------------------------
# 6. Build funnel from warehouse (main entry point)
# ---------------------------------------------------------------------------

def build_funnel_from_cdw(cdw, quarter: str) -> dict:
    """Orchestrate the full funnel computation from warehouse data.

    Pulls actuals from the warehouse connector, computes per-source rates with
    the three-tier fallback hierarchy, and projects forward for the quarter.

    Args:
        cdw: CDWConnector instance (or mock with same interface).
        quarter: Quarter string (e.g. "Q1FY26" or "FY26-Q1").

    Returns:
        {
            "actuals": {funnel volumes, attribution summary, plg funnel},
            "rates": {per-stage rates with provenance},
            "streams": {per-stream classification counts},
            "projections": {three-source pipeline projection}
        }
    """
    # --- Pull data from warehouse ---
    volumes = cdw.get_funnel_volumes(quarter)
    by_source_rates = cdw.get_conversion_rates_by_source(lookback_days=90)
    attribution = cdw.get_attribution_summary(quarter)
    plg_funnel = cdw.get_plg_funnel(quarter)
    plan_rates = _get_plan_rate_fallbacks()

    # --- Classify attribution into streams ---
    stream_counts: dict[str, int] = {"marketing_sdr": 0, "ae_selfgen": 0, "plg": 0}
    stream_pipeline: dict[str, float] = {"marketing_sdr": 0.0, "ae_selfgen": 0.0, "plg": 0.0}
    for source, data in attribution.items():
        stream = map_source_to_stream(source)
        stream_counts[stream] += data.get("count", 0)
        stream_pipeline[stream] += data.get("pipeline", 0.0)

    # --- Build per-source rate dicts keyed by stream ---
    # Aggregate warehouse by-source rates into stream-level rates
    stream_rates: dict[str, dict] = {}
    _stream_accum: dict[str, dict[str, dict]] = {}  # stream -> transition -> {sum_rate*n, total_n}

    for source, transitions in by_source_rates.items():
        stream = map_source_to_stream(source)
        if stream not in _stream_accum:
            _stream_accum[stream] = {}
        for transition_key, rate_data in transitions.items():
            n = rate_data.get("n", 0)
            rate = rate_data.get("rate", 0)
            if transition_key not in _stream_accum[stream]:
                _stream_accum[stream][transition_key] = {"weighted_sum": 0.0, "total_n": 0}
            _stream_accum[stream][transition_key]["weighted_sum"] += rate * n
            _stream_accum[stream][transition_key]["total_n"] += n

    for stream, transitions in _stream_accum.items():
        stream_rates[stream] = {}
        for transition_key, accum in transitions.items():
            total_n = accum["total_n"]
            avg_rate = accum["weighted_sum"] / total_n if total_n > 0 else 0.0
            stream_rates[stream][transition_key] = {"rate": avg_rate, "n": total_n}

    # --- Resolve rates with fallback ---
    # Use row-level per-source observed transition rates when sample size
    # is sufficient. Avoid quarter-bounded blended rates: they undercount
    # transitions that cross quarter boundaries and can leak same-quarter
    # velocity into bookings projections. Fall back to plan when sample
    # is insufficient.
    rate_keys = ["mql_to_s0", "s0_to_s1", "s1_to_s2"]
    resolved_rates: dict[str, dict] = {}

    for key in rate_keys:
        plan_rate = plan_rates.get(key, 0.0)

        # Build per-source dict for this transition keyed by stream
        per_source_for_key: dict[str, dict] = {}
        for stream_name, transitions in stream_rates.items():
            if key in transitions:
                per_source_for_key[stream_name] = transitions[key]

        # Resolve for each stream
        for stream_name in ["marketing_sdr", "ae_selfgen", "plg"]:
            result = get_conversion_rate(
                stream=stream_name,
                per_source=per_source_for_key,
                blended={"rate": None, "n": 0},
                plan=plan_rate,
            )
            resolved_rates.setdefault(stream_name, {})[key] = result

    # --- Compute average weekly volumes ---
    n_mql_weeks = len(volumes.get("mqls_weekly", []))
    avg_mqls_weekly = (
        sum(w.get("count", 0) for w in volumes.get("mqls_weekly", []))
        / max(n_mql_weeks, 1)
    )

    n_s0_weeks = len(volumes.get("s0_weekly", []))
    avg_s0_weekly = (
        sum(w.get("count", 0) for w in volumes.get("s0_weekly", []))
        / max(n_s0_weeks, 1)
    )

    # Estimate stream-level weekly inputs from attribution mix
    total_attr_count = sum(stream_counts.values()) or 1
    ae_pct = stream_counts["ae_selfgen"] / total_attr_count

    # MQLs are already the top-of-funnel input for marketing/SDR.
    # Do not downscale them again by downstream attribution mix.
    marketing_sdr_mqls_weekly = int(avg_mqls_weekly)
    ae_selfgen_s0_weekly = int(avg_s0_weekly * ae_pct) if ae_pct > 0 else int(avg_s0_weekly * 0.35)

    # PLG signups from PLG funnel data
    plg_weeks = len(plg_funnel.get("by_week", []))
    plg_signups_weekly = plg_funnel.get("signups", 0) // max(plg_weeks, 1) if plg_weeks > 0 else 50

    # --- Project pipeline using the resolved per-stream rates ---
    def _rate_for(stream: str, key: str) -> float:
        stream_entry = resolved_rates.get(stream, {}).get(key, {})
        if stream_entry.get("rate") is not None:
            return stream_entry["rate"]
        shared_entry = resolved_rates.get("marketing_sdr", {}).get(key, {})
        return shared_entry.get("rate", plan_rates.get(key, 0.0))

    marketing_projection = _annotate_projection(project_funnel(
        weekly_input=marketing_sdr_mqls_weekly,
        mql_to_s0=_rate_for("marketing_sdr", "mql_to_s0"),
        s0_to_s1=_rate_for("marketing_sdr", "s0_to_s1"),
        s1_to_s2=_rate_for("marketing_sdr", "s1_to_s2"),
        avg_s2_deal_size=300_000,
        weeks=13,
    ), stream_key="marketing_sdr", display_name="Marketing / SDR", input_label="MQLs", weekly_input=marketing_sdr_mqls_weekly, weeks=13)
    ae_projection = _annotate_projection(project_funnel(
        weekly_input=ae_selfgen_s0_weekly,
        mql_to_s0=1.0,
        s0_to_s1=_rate_for("ae_selfgen", "s0_to_s1"),
        s1_to_s2=_rate_for("ae_selfgen", "s1_to_s2"),
        avg_s2_deal_size=300_000,
        weeks=13,
    ), stream_key="ae_selfgen", display_name="AE Self-Gen", input_label="S0s", weekly_input=ae_selfgen_s0_weekly, weeks=13)
    plg_pql_to_s1 = _resolve_plg_pql_to_s1_rate({}, plan_rates, _rate_for("plg", "s0_to_s1"))
    plg_projection = _annotate_projection(project_stage1_funnel(
        weekly_input=plg_signups_weekly,
        input_to_s1=plan_rates["plg_signup_to_pql"] * plg_pql_to_s1,
        s1_to_s2=_rate_for("plg", "s1_to_s2"),
        avg_s2_deal_size=300_000,
        weeks=13,
    ), stream_key="plg", display_name="PLG", input_label="Signups", weekly_input=plg_signups_weekly, weeks=13)
    projections = _combine_stream_projections({
        "marketing_sdr": marketing_projection,
        "ae_selfgen": ae_projection,
        "plg": plg_projection,
    })

    return {
        "actuals": {
            "funnel_volumes": volumes,
            "attribution": attribution,
            "plg_funnel": plg_funnel,
        },
        "rates": resolved_rates,
        "streams": {
            "counts": stream_counts,
            "pipeline": stream_pipeline,
        },
        "projections": projections,
    }

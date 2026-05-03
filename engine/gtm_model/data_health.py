"""
Data Health Module — self-auditing checks for the GTM model.

All functions are pure logic: they accept pre-fetched data and return
assessment dicts. No external API calls are made here.

Four checks:
  1. assess_freshness      — Is the warehouse data recent enough to trust?
  2. reconcile_bookings    — Do warehouse and Salesforce bookings agree?
  3. validate_decay_curve  — Does our assumed close-timing curve match actuals?
  4. reconcile_targets     — Do YAML quarterly targets match the warehouse weekly sum?

Orchestrated by run_all_health_checks, which returns a combined status dict
with a top-level overall_status reflecting the worst individual result.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Status severity ordering (used to pick "worst" in run_all_health_checks)
# ---------------------------------------------------------------------------

_SEVERITY: dict[str, int] = {
    # freshness / decay / target
    "green": 0,
    "yellow": 1,
    "red": 2,
    # bookings reconciliation
    "ok": 0,
    "info": 1,
    "warning": 2,
    # target reconciliation
    "aligned": 0,
    "diverged": 2,
}


def _worst_status(*statuses: str) -> str:
    """Return the highest-severity status from the supplied list."""
    return max(statuses, key=lambda s: _SEVERITY.get(s, 0))


# ---------------------------------------------------------------------------
# 1. Freshness gate
# ---------------------------------------------------------------------------

def assess_freshness(mart_timestamps: dict[str, datetime]) -> dict[str, Any]:
    """
    Assess warehouse mart freshness based on the oldest mart timestamp.

    Args:
        mart_timestamps: Mapping of mart_name -> last_updated datetime.

    Returns:
        dict with keys:
          status    : "green" (<6h), "yellow" (6-24h), "red" (>24h)
          use_warehouse   : True for green/yellow, False for red
          hours_old : float — age of the oldest mart in hours
          message   : human-readable description
    """
    # Handle both timezone-aware and naive datetimes from warehouse
    from datetime import timezone
    now = datetime.now(timezone.utc)
    oldest_dt = min(mart_timestamps.values())
    # Make oldest_dt timezone-aware if it isn't
    if oldest_dt.tzinfo is None:
        oldest_dt = oldest_dt.replace(tzinfo=timezone.utc)
    hours_old = (now - oldest_dt).total_seconds() / 3600.0

    if hours_old < 6:
        status = "green"
        use_warehouse = True
        message = f"Data is fresh ({hours_old:.1f}h old). warehouse is the authoritative source."
    elif hours_old < 24:
        status = "yellow"
        use_warehouse = True
        message = (
            f"Data is moderately stale ({hours_old:.1f}h old). "
            "warehouse still usable; verify before high-stakes decisions."
        )
    else:
        status = "red"
        use_warehouse = False
        message = (
            f"Data is stale ({hours_old:.1f}h old, >{24}h threshold). "
            "Falling back to Salesforce as the live source."
        )

    return {
        "status": status,
        "use_warehouse": use_warehouse,
        "hours_old": hours_old,
        "message": message,
    }


# ---------------------------------------------------------------------------
# 2. Bookings reconciliation
# ---------------------------------------------------------------------------

def reconcile_bookings(cdw_bookings: float, sf_bookings: float) -> dict[str, Any]:
    """
    Compare bookings totals from warehouse and Salesforce.

    Args:
        cdw_bookings: Bookings figure from the data warehouse.
        sf_bookings:  Bookings figure from Salesforce.

    Returns:
        dict with keys:
          status       : "ok" (<1% delta), "info" (1-5%), "warning" (>5%)
          delta_pct    : absolute percentage difference (0.05 = 5%)
          cdw_bookings : echoed input
          sf_bookings  : echoed input
          message      : human-readable description
    """
    reference = max(abs(cdw_bookings), abs(sf_bookings))
    if reference == 0:
        delta_pct = 0.0
    else:
        delta_pct = abs(cdw_bookings - sf_bookings) / reference

    if delta_pct < 0.01:
        status = "ok"
        message = (
            f"Bookings are aligned. warehouse ${cdw_bookings:,.0f} vs "
            f"SF ${sf_bookings:,.0f} ({delta_pct:.2%} delta)."
        )
    elif delta_pct < 0.05:
        status = "info"
        message = (
            f"Minor bookings discrepancy ({delta_pct:.2%}). "
            f"warehouse ${cdw_bookings:,.0f} vs SF ${sf_bookings:,.0f}. "
            "Investigate timing differences."
        )
    else:
        status = "warning"
        message = (
            f"Significant bookings discrepancy ({delta_pct:.2%}). "
            f"warehouse ${cdw_bookings:,.0f} vs SF ${sf_bookings:,.0f}. "
            "Review for data pipeline errors or missing syncs."
        )

    return {
        "status": status,
        "delta_pct": delta_pct,
        "cdw_bookings": cdw_bookings,
        "sf_bookings": sf_bookings,
        "message": message,
    }


# ---------------------------------------------------------------------------
# 3. Decay curve validation
# ---------------------------------------------------------------------------

def validate_decay_curve(assumed: list[float], actual: list[float]) -> dict[str, Any]:
    """
    Measure how well the assumed close-timing distribution fits actuals.

    Uses R² (coefficient of determination) to quantify goodness of fit.
    assumed acts as the "predicted" series; actual is the "observed" series.

    Args:
        assumed: Assumed close-timing probability mass per month offset.
        actual:  Observed close-timing probability mass per month offset.

    Returns:
        dict with keys:
          r_squared : float, R² goodness of fit (1 = perfect)
          status    : "green" (R²>0.9), "yellow" (0.7-0.9), "red" (<0.7)
          assumed   : echoed input
          actual    : echoed input
          message   : human-readable description
    """
    n = min(len(assumed), len(actual))
    y = actual[:n]
    y_hat = assumed[:n]

    # Mean of actuals
    y_mean = sum(y) / n if n > 0 else 0.0

    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - fi) ** 2 for yi, fi in zip(y, y_hat))

    if ss_tot == 0:
        # All actuals are identical — perfect fit only if residuals are zero
        r_squared = 1.0 if ss_res == 0 else 0.0
    else:
        r_squared = 1.0 - ss_res / ss_tot

    if r_squared > 0.9:
        status = "green"
        message = (
            f"Decay curve is well-calibrated (R²={r_squared:.3f}). "
            "Assumed close timing matches actuals closely."
        )
    elif r_squared >= 0.7:
        status = "yellow"
        message = (
            f"Decay curve has moderate drift (R²={r_squared:.3f}). "
            "Consider recalibrating close-timing assumptions."
        )
    else:
        status = "red"
        message = (
            f"Decay curve is poorly calibrated (R²={r_squared:.3f}). "
            "Assumed close timing significantly diverges from actuals. "
            "Update the decay distribution before relying on pipeline planning outputs."
        )

    return {
        "r_squared": r_squared,
        "status": status,
        "assumed": assumed,
        "actual": actual,
        "message": message,
    }


# ---------------------------------------------------------------------------
# 4. Target reconciliation
# ---------------------------------------------------------------------------

def reconcile_targets(yaml_quarterly: float, cdw_weekly_sum: float) -> dict[str, Any]:
    """
    Check whether YAML-defined quarterly targets and warehouse weekly-sum targets agree.

    Args:
        yaml_quarterly:  Quarterly target from targets.yaml.
        cdw_weekly_sum:  Sum of weekly warehouse targets for the same period.

    Returns:
        dict with keys:
          status    : "aligned" (<10% delta), "diverged" (≥10%)
          delta_pct : absolute percentage difference (0.10 = 10%)
          message   : human-readable description
    """
    reference = max(abs(yaml_quarterly), abs(cdw_weekly_sum))
    if reference == 0:
        delta_pct = 0.0
    else:
        delta_pct = abs(yaml_quarterly - cdw_weekly_sum) / reference

    if delta_pct < 0.10:
        status = "aligned"
        message = (
            f"YAML and warehouse targets are aligned ({delta_pct:.2%} delta). "
            f"YAML ${yaml_quarterly:,.0f} vs warehouse sum ${cdw_weekly_sum:,.0f}."
        )
    else:
        status = "diverged"
        message = (
            f"Target mismatch detected ({delta_pct:.2%} delta). "
            f"YAML ${yaml_quarterly:,.0f} vs warehouse sum ${cdw_weekly_sum:,.0f}. "
            "Reconcile planning targets before running forecasts."
        )

    return {
        "status": status,
        "delta_pct": delta_pct,
        "message": message,
    }


# ---------------------------------------------------------------------------
# 5. Orchestrator
# ---------------------------------------------------------------------------

def run_all_health_checks(
    freshness: dict[str, datetime],
    cdw_bookings: float,
    sf_bookings: float,
    assumed_curve: list[float],
    actual_curve: list[float],
    yaml_quarterly: float,
    cdw_weekly_sum: float,
) -> dict[str, Any]:
    """
    Run all four health checks and return a combined status dict.

    Args:
        freshness:      mart_name -> last_updated datetime mapping.
        cdw_bookings:   Bookings from warehouse.
        sf_bookings:    Bookings from Salesforce.
        assumed_curve:  Assumed close-timing distribution.
        actual_curve:   Observed close-timing distribution.
        yaml_quarterly: Quarterly target from YAML config.
        cdw_weekly_sum: Sum of warehouse weekly targets for the period.

    Returns:
        dict with sub-dicts for each check plus a top-level overall_status
        reflecting the worst individual result.
    """
    freshness_result = assess_freshness(freshness)
    bookings_result = reconcile_bookings(cdw_bookings, sf_bookings)
    decay_result = validate_decay_curve(assumed_curve, actual_curve)
    targets_result = reconcile_targets(yaml_quarterly, cdw_weekly_sum)

    overall_status = _worst_status(
        freshness_result["status"],
        bookings_result["status"],
        decay_result["status"],
        targets_result["status"],
    )

    return {
        "freshness": freshness_result,
        "bookings_reconciliation": bookings_result,
        "decay_curve": decay_result,
        "targets": targets_result,
        "overall_status": overall_status,
    }

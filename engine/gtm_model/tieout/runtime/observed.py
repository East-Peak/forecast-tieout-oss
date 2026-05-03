"""Observed runtime signal helpers for Planning Tie-Out."""

from __future__ import annotations

from collections import defaultdict
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional

from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


def _month_windows(start_date: date, end_date: date) -> list[tuple[date, date]]:
    """Return inclusive month windows overlapping the requested period."""
    windows: list[tuple[date, date]] = []
    cursor = start_date.replace(day=1)
    while cursor <= end_date:
        next_month = cursor + relativedelta(months=1)
        month_end = next_month - timedelta(days=1)
        windows.append((max(cursor, start_date), min(month_end, end_date)))
        cursor = next_month
    return windows


def _month_fraction_in_window(start_dt: date, window_start: date, window_end: date) -> float:
    """Return the fraction of a calendar month the AE is active inside the window."""
    month_start = window_start.replace(day=1)
    next_month = month_start + relativedelta(months=1)
    month_end = next_month - timedelta(days=1)
    if start_dt > window_end:
        return 0.0
    active_start = max(start_dt, window_start)
    active_end = min(window_end, month_end)
    if active_end < active_start:
        return 0.0
    active_days = (active_end - active_start).days + 1
    total_days = (month_end - month_start).days + 1
    return max(0.0, min(1.0, active_days / total_days))


def _serialize_bucket_curve(curve: dict[int, float]) -> dict[str, float]:
    """Convert integer month buckets to stable month_N keys."""
    return {
        f"month_{int(bucket)}": float(value)
        for bucket, value in sorted((curve or {}).items())
    }


def _shrink_toward(prior: float, observed: float, weight: float, shrinkage: float) -> float:
    """Blend a noisy observed value back toward a prior using sample-weighted shrinkage."""
    if weight <= 0:
        return float(prior)
    shrink = max(0.0, min(1.0, weight / (weight + max(shrinkage, 0.0))))
    return (float(prior) * (1.0 - shrink)) + (float(observed) * shrink)


@dataclass
class TieoutObservedSignalResolver:
    """Resolve trailing observed productivity, MQL signals, and ARR movements."""

    get_cdw: Callable[[], object | None]
    get_sf: Callable[[], object | None]
    is_cdw_query_failed: Callable[[], bool]
    get_beginning_arr_snapshot: Callable[[], tuple[float, dict]]

    _arr_movements_cache: Optional[dict] = None
    _self_serve_velocity_cache: Optional[dict] = None

    def compute_trailing_ramped_ae_months(
        self,
        roster: dict,
        as_of: date,
        months: int = 6,
    ) -> float:
        """Approximate trailing ramp-weighted AE-months over a rolling window."""
        from gtm_model.roster import _get_ramp_factor, _months_since

        month_points: list[date] = []
        current_month = as_of.replace(day=1)
        for offset in range(months - 1, -1, -1):
            month_start = current_month - relativedelta(months=offset)
            if month_start.year == as_of.year and month_start.month == as_of.month:
                month_points.append(as_of)
            else:
                next_month = month_start + relativedelta(months=1)
                month_points.append(next_month - timedelta(days=1))

        total = 0.0
        for group_name in ("active", "incoming"):
            for ae in roster.get(group_name, []):
                start_str = (
                    ae.get("start_date")
                    or ae.get("expected_start")
                    or ae.get("employee_start_date")
                    or ""
                )
                if not start_str:
                    continue
                try:
                    start_dt = date.fromisoformat(str(start_str)[:10])
                except (TypeError, ValueError):
                    continue
                if start_dt > as_of:
                    continue
                segment = ae.get("segment", "enterprise")
                for point in month_points:
                    if start_dt > point:
                        continue
                    months_active = max(_months_since(start_dt, point), 0)
                    total += _get_ramp_factor(segment, months_active)
        return total

    def get_observed_ae_productivity(
        self,
        roster: dict,
        as_of: date,
        lookback_days: int = 180,
        compute_ramped_months: Optional[Callable[[dict, date, int], float]] = None,
    ) -> dict:
        """Get trailing AE-sourced S0 productivity with warehouse-first fallback."""
        from gtm_model.funnel_engine import map_source_to_stream

        start_date = as_of - timedelta(days=lookback_days)
        result = {
            "productivity": None,
            "s0_count": 0,
            "ramped_ae_months": 0.0,
            "source": "unavailable",
        }

        def _parse_rows(rows: list[dict], source_name: str) -> dict:
            ae_s0_count = 0
            for week in rows or []:
                by_source = week.get("by_source") or {}
                for source_category, count in by_source.items():
                    if map_source_to_stream(source_category) == "ae_selfgen":
                        ae_s0_count += int(count or 0)

            months = max(lookback_days // 30, 1)
            if compute_ramped_months is not None:
                ramped_ae_months = compute_ramped_months(roster, as_of, months)
            else:
                ramped_ae_months = self.compute_trailing_ramped_ae_months(
                    roster=roster,
                    as_of=as_of,
                    months=months,
                )
            productivity = ae_s0_count / ramped_ae_months if ramped_ae_months > 0 else None
            return {
                "productivity": productivity,
                "s0_count": ae_s0_count,
                "ramped_ae_months": ramped_ae_months,
                "source": source_name,
            }

        cdw = self.get_cdw()
        if cdw is not None and not self.is_cdw_query_failed():
            try:
                rows = cdw.get_weekly_s0_created(start_date, as_of)
                if rows:
                    return _parse_rows(rows, "warehouse")
            except Exception as exc:
                logger.info("Could not compute AE productivity from warehouse: %s", exc)

        sf = self.get_sf()
        if sf is not None:
            try:
                rows = sf.get_weekly_s0_created(start_date, as_of)
                if rows:
                    return _parse_rows(rows, "Salesforce")
            except Exception as exc:
                logger.info("Could not compute AE productivity from Salesforce: %s", exc)

        return result

    def get_observed_ae_ramp_curve(
        self,
        roster: dict,
        as_of: date,
        lookback_days: int = 365,
        min_bucket_ae_months: float = 1.5,
        min_steady_state_ae_months: float = 3.0,
        min_bucket_rep_count: int = 3,
        min_rep_steady_state_ae_months: float = 0.75,
        shrinkage_ae_months: float = 4.0,
    ) -> dict:
        """Estimate AE time-to-productivity from observed warehouse-created S0 detail.

        The curve is estimated from per-rep normalized S0 creation so one hot
        or mis-start-dated rep cannot make the whole early ramp look fully
        productive. Bucket-level observed values are shrunk back toward config
        when the cohort exposure is still thin.
        """
        from gtm_model.funnel_engine import map_source_to_stream
        from gtm_model.roster import _get_ramp_curve, _months_since, _normalize_key, _normalize_segment

        result = {
            "source": "config",
            "curve_by_segment": None,
            "sample_sizes": {},
            "reason": "insufficient_observed_ramp_data",
        }

        roster_index: dict[str, dict] = {}
        for ae in roster.get("active", []):
            start_str = (
                ae.get("start_date")
                or ae.get("employee_start_date")
                or ae.get("expected_start")
                or ""
            )
            if not start_str or not ae.get("name"):
                continue
            try:
                start_dt = date.fromisoformat(str(start_str)[:10])
            except (TypeError, ValueError):
                continue
            if start_dt > as_of:
                continue
            roster_index[_normalize_key(ae.get("name"))] = {
                "start_date": start_dt,
                "segment": _normalize_segment(ae.get("segment") or "enterprise"),
            }

        if not roster_index:
            result["reason"] = "no_active_roster_for_observed_ramp"
            return result

        start_date = as_of - timedelta(days=lookback_days)
        windows = _month_windows(start_date, as_of)
        ae_months_by_rep: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        s0s_by_rep: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

        for rep_key, rep in roster_index.items():
            start_dt = rep["start_date"]
            for window_start, window_end in windows:
                if start_dt > window_end:
                    continue
                bucket = _months_since(start_dt, window_end) + 1
                ae_months_by_rep[rep_key][bucket] += _month_fraction_in_window(
                    start_dt,
                    window_start,
                    window_end,
                )

        cdw = self.get_cdw()
        if cdw is None or self.is_cdw_query_failed() or not hasattr(cdw, "get_s0_created_detail"):
            result["reason"] = "warehouse_s0_detail_unavailable"
            return result

        try:
            rows = cdw.get_s0_created_detail(start_date, as_of)
        except Exception as exc:
            logger.info("Could not compute observed AE ramp from warehouse: %s", exc)
            result["reason"] = "warehouse_s0_detail_query_failed"
            return result

        for row in rows or []:
            if map_source_to_stream(row.get("source_category")) != "ae_selfgen":
                continue
            owner_key = _normalize_key(row.get("owner_name"))
            rep = roster_index.get(owner_key)
            if rep is None:
                continue
            created_raw = row.get("created_date")
            try:
                created_dt = date.fromisoformat(str(created_raw)[:10])
            except (TypeError, ValueError):
                continue
            if created_dt < rep["start_date"] or created_dt > as_of:
                continue
            bucket = _months_since(rep["start_date"], created_dt) + 1
            s0s_by_rep[owner_key][bucket] += 1

        curve_by_segment: dict[str, dict[int, float]] = {}
        sample_sizes: dict[str, dict[str, float]] = {}

        for segment in sorted({rep["segment"] for rep in roster_index.values()}):
            config_curve = _get_ramp_curve(segment)
            mature_bucket = max(config_curve.keys()) if config_curve else 4
            bucket_exposure: dict[int, float] = defaultdict(float)
            bucket_ratio_sum: dict[int, float] = defaultdict(float)
            bucket_rep_counts: dict[int, set[str]] = defaultdict(set)
            steady_state_ae_months = 0.0
            qualified_reps = 0

            for rep_key, rep in roster_index.items():
                if rep["segment"] != segment:
                    continue
                rep_ae_months = ae_months_by_rep.get(rep_key, {})
                rep_s0s = s0s_by_rep.get(rep_key, {})
                mature_ae_months = sum(
                    value for bucket, value in rep_ae_months.items()
                    if bucket >= mature_bucket
                )
                mature_s0s = sum(
                    count for bucket, count in rep_s0s.items()
                    if bucket >= mature_bucket
                )
                if mature_ae_months < min_rep_steady_state_ae_months or mature_s0s <= 0:
                    continue

                steady_state_productivity = mature_s0s / mature_ae_months
                if steady_state_productivity <= 0:
                    continue

                steady_state_ae_months += mature_ae_months
                qualified_reps += 1
                for bucket in range(1, mature_bucket + 1):
                    exposure = float(rep_ae_months.get(bucket, 0.0) or 0.0)
                    if exposure <= 0:
                        continue
                    observed_productivity = float(rep_s0s.get(bucket, 0) or 0) / exposure
                    ratio = max(
                        0.0,
                        min(1.0, observed_productivity / steady_state_productivity),
                    )
                    bucket_ratio_sum[bucket] += ratio * exposure
                    bucket_exposure[bucket] += exposure
                    bucket_rep_counts[bucket].add(rep_key)

            if steady_state_ae_months < min_steady_state_ae_months or qualified_reps <= 0:
                continue

            curve: dict[int, float] = {}
            previous = 0.0
            for bucket in range(1, mature_bucket + 1):
                exposure = float(bucket_exposure.get(bucket, 0.0) or 0.0)
                rep_count = len(bucket_rep_counts.get(bucket, set()))
                config_value = float(config_curve.get(bucket, previous))
                if exposure >= min_bucket_ae_months and rep_count >= min_bucket_rep_count:
                    observed_ratio = (
                        float(bucket_ratio_sum.get(bucket, 0.0) or 0.0) / exposure
                    )
                    candidate = _shrink_toward(
                        prior=config_value,
                        observed=observed_ratio,
                        weight=exposure,
                        shrinkage=shrinkage_ae_months,
                    )
                else:
                    candidate = config_value
                candidate = max(previous, min(1.0, candidate))
                curve[bucket] = candidate
                previous = candidate

            curve[mature_bucket] = 1.0
            curve_by_segment[segment] = curve
            sample_sizes[segment] = {
                "steady_state_ae_months": round(steady_state_ae_months, 2),
                "qualified_reps": float(qualified_reps),
                **{
                    f"month_{bucket}": round(float(bucket_exposure.get(bucket, 0.0) or 0.0), 2)
                    for bucket in range(1, mature_bucket + 1)
                },
                **{
                    f"month_{bucket}_reps": float(len(bucket_rep_counts.get(bucket, set())))
                    for bucket in range(1, mature_bucket + 1)
                },
            }

        if not curve_by_segment:
            return result

        return {
            "source": "warehouse",
            "curve_by_segment": curve_by_segment,
            "sample_sizes": sample_sizes,
            "reason": "",
            "curve_by_segment_serialized": {
                segment: _serialize_bucket_curve(curve)
                for segment, curve in curve_by_segment.items()
            },
        }

    def get_trailing_mql_weekly_signal(
        self,
        as_of: date,
        lookback_days: int = 180,
    ) -> tuple[Optional[list[float]], str]:
        """Get trailing weekly MQL volume with warehouse-first fallback."""
        start_date = as_of - timedelta(days=lookback_days)

        cdw = self.get_cdw()
        if cdw is not None and not self.is_cdw_query_failed():
            try:
                rows = cdw.get_weekly_mql_generation(start_date, as_of)
                values = [float(r.get("count", 0) or 0.0) for r in rows]
                if values:
                    return values, "warehouse"
            except Exception as exc:
                logger.info("Could not load trailing MQLs from warehouse: %s", exc)

        sf = self.get_sf()
        if sf is not None:
            try:
                rows = sf.get_weekly_mql_generation(start_date, as_of)
                values = [float(r.get("count", 0) or 0.0) for r in rows]
                if values:
                    return values, "Salesforce"
            except Exception as exc:
                logger.info("Could not load trailing MQLs from Salesforce: %s", exc)

        return None, "unavailable"

    def get_monthly_mql_actuals(
        self,
        as_of: date,
        months: int = 12,
        fy_start: date | None = None,
    ) -> tuple[list, int | None]:
        """Fetch monthly MQL counts from warehouse, aligned to the projection window.

        The projection window is ``months`` months starting from the month
        containing ``as_of``.  Completed months before ``as_of`` are filled
        with observed values; the ``as_of`` month is pro-rated; future months
        are ``None``.

        If ``fy_start`` is provided, the warehouse query starts from ``fy_start``
        so earlier months can be captured.  Otherwise the query starts 12
        months before ``as_of``.

        Returns:
            (actuals_list, partial_month_index)
            - actuals_list: length ``months``, aligned to projection indices.
              ``0.0`` for completed months with zero MQLs (not ``None``).
            - partial_month_index: index of the current (pro-rated) month, or
              ``None`` if no partial month is present.
        """
        from calendar import monthrange

        result: list = [None] * months
        partial_idx: int | None = None
        as_of_month_start = as_of.replace(day=1)

        # Query window: from fy_start (or 12 months back) to as_of
        query_start = fy_start if fy_start is not None else (
            date(as_of.year - 1, as_of.month, 1)
        )

        # Reuse the same weekly-granularity MQL query then bucket by month.
        # Track whether a source was successfully queried (even if it returned
        # zero rows) vs whether all sources failed / were unavailable.
        cdw = self.get_cdw()
        rows: list[dict] = []
        query_succeeded = False
        if cdw is not None and not self.is_cdw_query_failed():
            try:
                rows = cdw.get_weekly_mql_generation(query_start, as_of)
                query_succeeded = True  # warehouse responded, even if rows is []
            except Exception:
                pass
        if not query_succeeded:
            sf = self.get_sf()
            if sf is not None:
                try:
                    rows = sf.get_weekly_mql_generation(query_start, as_of)
                    query_succeeded = True  # SF responded, even if rows is []
                except Exception:
                    pass

        # If no source responded successfully, we have no evidence.
        # Leave everything as None so the projection falls back to EWMA.
        if not query_succeeded:
            return result, partial_idx

        # Aggregate weekly rows into calendar-month buckets
        monthly_counts: dict[date, float] = {}
        for row in rows:
            week_start_str = row.get("week_start") or ""
            count = float(row.get("count", 0) or 0)
            try:
                week_start = date.fromisoformat(str(week_start_str)[:10])
            except (ValueError, TypeError):
                continue
            month_key = week_start.replace(day=1)
            monthly_counts[month_key] = monthly_counts.get(month_key, 0.0) + count

        all_queried_months: set[date] = set()
        m = query_start.replace(day=1)
        while m <= as_of_month_start:
            all_queried_months.add(m)
            if m.month == 12:
                m = date(m.year + 1, 1, 1)
            else:
                m = date(m.year, m.month + 1, 1)

        # Map calendar months to projection indices.
        # Index 0 = as_of month, index 1 = next month, etc.
        for month_idx in range(months):
            raw_month = as_of_month_start.month + month_idx - 1
            month_date = date(
                as_of_month_start.year + raw_month // 12,
                raw_month % 12 + 1,
                1,
            )
            _, days_in_month = monthrange(month_date.year, month_date.month)
            month_end = month_date.replace(day=days_in_month)

            if month_end < as_of:
                # Fully completed month
                if month_date in monthly_counts:
                    result[month_idx] = monthly_counts[month_date]
                elif month_date in all_queried_months:
                    # Queried but zero rows — real zero, not missing
                    result[month_idx] = 0.0
            elif month_date.year == as_of.year and month_date.month == as_of.month:
                # Current partial month — pro-rate
                days_elapsed = (as_of - month_date).days + 1
                if days_elapsed > 0 and month_date in monthly_counts:
                    result[month_idx] = (
                        monthly_counts[month_date] / days_elapsed * days_in_month
                    )
                    partial_idx = month_idx
                elif month_date in all_queried_months:
                    result[month_idx] = 0.0
                    partial_idx = month_idx
            # Future months: leave as None

        return result, partial_idx

    def get_observed_arr_movements(self) -> dict:
        """Fetch trailing-12-month ARR movements with warehouse-first fallback."""
        if self._arr_movements_cache is not None:
            return self._arr_movements_cache

        cdw = self.get_cdw()
        if cdw is not None and not self.is_cdw_query_failed():
            try:
                movements = cdw.get_arr_movements(
                    start_date=date.today() - relativedelta(months=12),
                    end_date=date.today(),
                )
                beginning_arr, _ = self.get_beginning_arr_snapshot()
                if beginning_arr and beginning_arr > 0:
                    observed_churn_rate = movements.get("churned_arr", 0) / beginning_arr
                    observed_expansion_rate = movements.get("expansion_arr", 0) / beginning_arr
                else:
                    observed_churn_rate = 0.0
                    observed_expansion_rate = 0.0

                result = {
                    **movements,
                    "source": movements.get("source", "warehouse"),
                    "observed_annual_churn_rate": observed_churn_rate,
                    "observed_annual_expansion_rate": observed_expansion_rate,
                    "beginning_arr_used": beginning_arr,
                }
                self._arr_movements_cache = result
                return result
            except Exception as exc:
                logger.info("warehouse ARR movements unavailable: %s", exc)

        sf = self.get_sf()
        if sf:
            try:
                movements = sf.get_arr_movements(
                    start_date=date.today() - relativedelta(months=12),
                    end_date=date.today(),
                )
                beginning_arr, _ = self.get_beginning_arr_snapshot()
                if beginning_arr and beginning_arr > 0:
                    observed_churn_rate = movements.get("churned_arr", 0) / beginning_arr
                    observed_expansion_rate = movements.get("expansion_arr", 0) / beginning_arr
                else:
                    observed_churn_rate = 0.0
                    observed_expansion_rate = 0.0

                result = {
                    **movements,
                    "source": "Salesforce",
                    "provenance": "connectors.salesforce.get_arr_movements",
                    "observed_annual_churn_rate": observed_churn_rate,
                    "observed_annual_expansion_rate": observed_expansion_rate,
                    "beginning_arr_used": beginning_arr,
                }
                self._arr_movements_cache = result
                return result
            except Exception as exc:
                logger.info("SF ARR movements unavailable: %s", exc)

        result = {"source": "unavailable"}
        self._arr_movements_cache = result
        return result

    def get_self_serve_velocity(self, lookback_days: int = 180) -> dict:
        """Fetch trailing self-serve opportunity velocity with warehouse-first fallback."""
        if self._self_serve_velocity_cache is not None:
            return self._self_serve_velocity_cache

        cdw = self.get_cdw()
        if cdw is not None and not self.is_cdw_query_failed():
            try:
                velocity = dict(cdw.get_self_serve_velocity(lookback_days=lookback_days) or {})
                velocity.setdefault("source", "warehouse")
                velocity.setdefault(
                    "provenance",
                    f"{getattr(cdw, 'DATABASE', '')}.{getattr(cdw, 'MART_SCHEMA', '')}".strip("."),
                )
                self._self_serve_velocity_cache = velocity
                return velocity
            except Exception as exc:
                logger.info("warehouse self-serve velocity unavailable: %s", exc)

        sf = self.get_sf()
        if sf is not None:
            try:
                velocity = dict(sf.get_self_serve_velocity(lookback_days=lookback_days) or {})
                velocity["source"] = "Salesforce"
                velocity.setdefault("provenance", "connectors.salesforce.get_self_serve_velocity")
                self._self_serve_velocity_cache = velocity
                return velocity
            except Exception as exc:
                logger.info("Salesforce self-serve velocity unavailable: %s", exc)

        result = {"weekly_creation": [], "source": "unavailable"}
        self._self_serve_velocity_cache = result
        return result

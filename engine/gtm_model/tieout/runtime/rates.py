"""Rate and decay resolution helpers for Planning Tie-Out runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Optional

from gtm_model.rate_registry import (
    RateNotFoundError,
    RateRegistry,
    RateSemantic,
    SemanticMismatchError,
)

logger = logging.getLogger(__name__)

_FUNNEL_RATE_SEMANTICS: dict[str, RateSemantic] = {
    "mql_to_s0": RateSemantic.ACTIVITY_RATE,
    "s0_to_s1": RateSemantic.SEQUENTIAL_TRANSITION,
    "s1_to_s2": RateSemantic.SEQUENTIAL_TRANSITION,
}


@dataclass
class TieoutRuntimeRateResolver:
    """Resolve canonical runtime rates, win rates, and decay curves.

    Per ARCHITECTURE.md: when get_backend yields a ProfileBackend, its
    compute_observed_velocity() output is consulted before warehouse/SF for
    rolling S2-to-Won rate. Backends with sufficient sample (>= 10
    closed deals) override config defaults.
    """

    get_assumptions: Callable[[], dict]
    get_rate_registry: Callable[[], Optional[RateRegistry]]
    get_sf: Callable[[], object | None]
    get_cdw: Callable[[], object | None]
    try_closed_won_timing: Callable[[], Optional[list[dict]]]
    get_closed_won_timing_source: Callable[[], Optional[str]]
    get_backend: Optional[Callable[[], object | None]] = None  # ProfileBackend 

    _rolling_s2_rate_cache: Optional[dict] = None
    _decay_curve_cache: Optional[dict] = None
    _weighted_blend_cache: Optional[dict] = None

    def _try_weighted_blend_rates(self) -> Optional[dict]:
        """Try to get recency-weighted blend conversion rates.

        Priority: warehouse cohort mart first, Salesforce fallback.

        Returns dict keyed by transition (s0_to_s1, s1_to_s2) with rate,
        sample size, and provenance — or None if unavailable.

        See ARCHITECTURE.md for methodology.
        """
        if self._weighted_blend_cache is not None:
            return self._weighted_blend_cache

        blend = self._try_cdw_cohort_rates()
        if blend is None:
            blend = self._try_sf_cohort_rates()
        if not blend:
            return None

        result: dict[str, dict] = {}
        for key in ("s0_to_s1", "s1_to_s2"):
            entry = blend.get(key, {})
            rate = entry.get("blended_rate")
            n = entry.get("blended_n", 0)
            qualifying = entry.get("qualifying_months", 0)
            if rate is not None and rate > 0 and n >= 10:
                result[key] = {
                    "value": float(rate),
                    "source": "blended_cohort",
                    "n": int(n),
                    "methodology": entry.get("methodology", "weighted_blend_mature_cohort"),
                    "qualifying_months": qualifying,
                    "monthly": entry.get("monthly", []),
                }

        self._weighted_blend_cache = result if result else None
        return self._weighted_blend_cache

    def _try_cdw_cohort_rates(self) -> Optional[dict]:
        """Try warehouse mart_stage_cohort_conversion for weighted blend rates."""
        cdw = self.get_cdw()
        if not cdw:
            return None
        try:
            blend = cdw.get_cohort_conversion_rates()
            if blend and any(blend.get(k, {}).get("blended_n", 0) > 0 for k in ("s0_to_s1", "s1_to_s2")):
                logger.info("Using warehouse cohort mart for weighted blend rates")
                return blend
        except Exception as exc:
            logger.info("warehouse cohort conversion rates unavailable: %s", exc)
        return None

    def _try_sf_cohort_rates(self) -> Optional[dict]:
        """Salesforce fallback for weighted blend rates."""
        sf = self.get_sf()
        if not sf:
            return None
        try:
            return sf.get_monthly_cohort_conversion_rates(
                lookback_days=365,
                min_age_days=90,
            )
        except Exception as exc:
            logger.info("SF weighted blend conversion rates unavailable: %s", exc)
            return None

    def _try_salesforce_mql_to_s0_rate(self) -> Optional[dict]:
        """Resolve MQL→S0 from trailing Salesforce activity, not quarter marts.

        MQL→S0 is an activity-throughput metric, not a mature cohort rate.
        We intentionally avoid the quarter-bounded warehouse velocity mart here
        because it can undercount leads that cross the quarter boundary.
        """
        sf = self.get_sf()
        if not sf:
            return None

        today = date.today()
        windows = (
            (90, 100),
            (180, 200),
            (365, 400),
        )
        for lookback_days, min_mql_count in windows:
            start_date = today - timedelta(days=lookback_days)
            try:
                observed = sf.get_funnel_conversion_rates(start_date, today)
            except Exception as exc:
                logger.info("SF MQL→S0 activity rate unavailable: %s", exc)
                return None

            rate = observed.get("mql_to_s0")
            counts = observed.get("counts", {}) or {}
            mql_count = int(counts.get("mql", 0) or 0)
            s0_count = int(counts.get("s0", 0) or 0)
            if rate is None or float(rate) <= 0:
                continue
            if mql_count < min_mql_count or s0_count <= 0:
                continue

            return {
                "value": float(rate),
                "source": "Salesforce",
                "n": mql_count,
                "methodology": "salesforce_trailing_activity_rate",
                "lookback_days": lookback_days,
                "s0_count": s0_count,
            }

        return None

    def _try_salesforce_s2_rate(
        self,
        lookback_days: int,
        min_age_days: int = 0,
    ) -> Optional[dict]:
        """Resolve an S2→Won rate from Salesforce history when available."""
        sf = self.get_sf()
        if not sf:
            return None

        try:
            if min_age_days > 0:
                hist = sf.calculate_historical_rates(
                    lookback_days=lookback_days,
                    min_age_days=min_age_days,
                )
            else:
                hist = sf.calculate_historical_rates(lookback_days=lookback_days)
        except TypeError:
            if min_age_days > 0:
                logger.debug(
                    "Salesforce connector does not support mature cohort filtering; "
                    "falling back to uncensored rolling rate."
                )
                return None
            raise

        s2_entry = (hist or {}).get("S2", {})
        rate = s2_entry.get("rate")
        sample = int(s2_entry.get("sample", 0) or 0)
        if rate is None or float(rate) <= 0:
            return None

        result = {
            "rate": float(rate),
            "source": "Salesforce",
            "sample": sample,
            "lookback_days": lookback_days,
            "min_age_days": int(min_age_days or 0),
            "method": "mature_cohort" if min_age_days > 0 else "rolling",
        }
        return result

    def _try_backend_s2_rate(self) -> Optional[dict]:
        """Compute S2-to-Won rate from ProfileBackend.

        Returns None when no backend is configured or the backend produced
        no rate. Otherwise returns the legacy {rate, source, sample,
        lookback_days} shape so the caller treats it identically to warehouse/SF.

        Sample semantics matter for the downstream `sample >= 20` gate:
        derived/observed_velocity computes the rate as won_S2_entered /
        closed_S2_entered, so `sample` MUST be closed_S2_entered (not
        raw S2 entries). Otherwise the gate would let through rates
        based on still-open deals.
        """
        if self.get_backend is None:
            return None
        try:
            backend = self.get_backend()
        except Exception:
            return None
        if backend is None:
            return None
        try:
            profile = backend.compute_observed_velocity(as_of=date.today())
        except Exception as exc:
            logger.info("ProfileBackend rolling s2_to_won unavailable: %s", exc)
            return None
        if profile.s2_to_won_rate is None:
            return None
        # Compute closed_S2_entered: deals that entered S2 AND are now closed.
        # Matches the denominator of derived/observed_velocity's rate so the
        # downstream sample-size gate is well-calibrated.
        sample = 0
        try:
            transitions = backend.fetch_stage_history()
            s2_entered_ids = {t.deal_id for t in transitions if t.to_stage == "S2"}
            if s2_entered_ids:
                deals = backend.fetch_deals()
                sample = sum(
                    1 for d in deals if d.id in s2_entered_ids and d.is_closed
                )
        except Exception:
            pass
        return {
            "rate": float(profile.s2_to_won_rate),
            "source": "ProfileBackend",
            "sample": sample,
            "lookback_days": 0,  # full history; backend computes lifetime
        }

    def _try_cdw_s2_rate(self) -> Optional[dict]:
        """Try warehouse cohort mart for S2→Won mature cohort rate."""
        cdw = self.get_cdw()
        if not cdw:
            return None
        try:
            blend = cdw.get_cohort_conversion_rates()
            s2_entry = (blend or {}).get("s2_to_won", {})
            rate = s2_entry.get("blended_rate")
            n = s2_entry.get("blended_n", 0)
            if rate is not None and rate > 0:
                logger.info("Using warehouse cohort mart for S2→Won rate: %.1f%% (n=%d)", rate * 100, n)
                return {
                    "rate": float(rate),
                    "source": "warehouse",
                    "sample": int(n),
                    "lookback_days": 0,
                    "min_age_days": 90,
                    "method": "cdw_mature_cohort",
                }
        except Exception as exc:
            logger.info("warehouse S2→Won rate unavailable: %s", exc)
        return None

    def get_registered_funnel_rate(self, key: str, default: float) -> float:
        """Resolve a funnel rate via the registry, falling back to config defaults."""
        semantic = _FUNNEL_RATE_SEMANTICS.get(key)
        rate_registry = self.get_rate_registry()
        if semantic is None or rate_registry is None:
            return default

        try:
            return float(rate_registry.get_value(key, semantic))
        except (RateNotFoundError, SemanticMismatchError, TypeError, ValueError) as exc:
            logger.debug("Falling back to raw assumptions for %s: %s", key, exc)
            return default

    def describe_runtime_funnel_rates(self) -> dict[str, dict]:
        """Return runtime funnel rates with lightweight provenance.

        Priority:
            mql_to_s0:
                1. Salesforce trailing activity rate
                2. Rate registry (if available)
                3. Config assumption fallback
            s0_to_s1 / s1_to_s2 :
                1. Salesforce weighted blend of mature monthly cohorts
                2. Rate registry (if available)
                3. Config assumption fallback
        """
        funnel_cfg = self.get_assumptions().get("funnel", {}) or {}
        descriptors: dict[str, dict] = {}
        defaults = {
            "mql_to_s0": float(funnel_cfg.get("mql_to_s0", 0.15) or 0.15),
            "s0_to_s1": float(funnel_cfg.get("s0_to_s1", 0.55) or 0.55),
            "s1_to_s2": float(funnel_cfg.get("s1_to_s2", 0.25) or 0.25),
        }
        rate_registry = self.get_rate_registry()

        # Try weighted blend from Salesforce for s0_to_s1, s1_to_s2
        blend = self._try_weighted_blend_rates() or {}
        sf_mql_to_s0 = self._try_salesforce_mql_to_s0_rate()

        for key, default in defaults.items():
            if key == "mql_to_s0" and sf_mql_to_s0 is not None:
                descriptors[key] = dict(sf_mql_to_s0)
                continue

            # Check weighted blend first (s0_to_s1, s1_to_s2 only)
            blend_entry = blend.get(key)
            if blend_entry is not None:
                descriptors[key] = {
                    "value": blend_entry["value"],
                    "source": "blended_cohort",
                    "n": blend_entry["n"],
                    "methodology": blend_entry.get("methodology", "weighted_blend_mature_cohort"),
                    "qualifying_months": blend_entry.get("qualifying_months", 0),
                }
                continue

            # Fallback: rate registry
            semantic = _FUNNEL_RATE_SEMANTICS.get(key)
            source = "config"
            value = default
            if semantic is not None and rate_registry is not None:
                try:
                    value = float(rate_registry.get_value(key, semantic))
                    source = "registry"
                except (RateNotFoundError, SemanticMismatchError, TypeError, ValueError) as exc:
                    logger.debug("Falling back to raw assumptions for %s: %s", key, exc)
            descriptors[key] = {"value": value, "source": source}

        descriptors["plg_signup_to_pql"] = {"value": 0.05, "source": "static"}
        s0_to_s1_value = float(descriptors.get("s0_to_s1", {}).get("value", 0.0) or 0.0)
        descriptors["plg_pql_to_s1"] = {
            "value": 0.20 * s0_to_s1_value,
            "source": "static",
            "methodology": "legacy_plg_pql_to_s0 * s0_to_s1",
        }
        return descriptors

    def get_runtime_funnel_rates(self) -> dict[str, float]:
        """Return the canonical runtime funnel rates for tieout math."""
        described = self.describe_runtime_funnel_rates()
        return {key: float(entry.get("value", 0.0) or 0.0) for key, entry in described.items()}

    def get_decay_curve(self) -> list[float]:
        """Load the configured close timing curve."""
        rate_registry = self.get_rate_registry()
        if rate_registry is not None:
            try:
                return [float(v) for v in rate_registry.get_timing_curve("close_timing_curve")]
            except (RateNotFoundError, SemanticMismatchError, TypeError, ValueError) as exc:
                logger.debug("Falling back to raw close timing curve: %s", exc)

        dist = self.get_assumptions().get("close_rate_distribution", {})
        if dist and "month_1" in dist:
            return [dist.get(f"month_{i}", 0.0) for i in range(1, 10)]
        return [0.16, 0.26, 0.17, 0.15, 0.11, 0.06, 0.04, 0.03, 0.02]

    def get_rolling_s2_to_won_rate(self) -> dict:
        """Try ProfileBackend → warehouse → SF → static config."""
        if self._rolling_s2_rate_cache is not None:
            return self._rolling_s2_rate_cache

        # Backend-first path
        backend_result = self._try_backend_s2_rate()
        if backend_result is not None and backend_result.get("sample", 0) >= 10:
            self._rolling_s2_rate_cache = backend_result
            return backend_result

        # Try warehouse cohort mart first (S2→Won mature cohort)
        cdw_result = self._try_cdw_s2_rate()
        if cdw_result is not None and cdw_result.get("sample", 0) >= 10:
            self._rolling_s2_rate_cache = cdw_result
            return cdw_result

        for lookback_days, min_age_days in ((540, 180), (365, 120), (180, 0)):
            try:
                sf_result = self._try_salesforce_s2_rate(
                    lookback_days=lookback_days,
                    min_age_days=min_age_days,
                )
            except Exception as exc:
                logger.info("SF historical rates unavailable: %s", exc)
                sf_result = None
            if sf_result is None:
                continue
            if sf_result["sample"] >= 20 or min_age_days == 0:
                self._rolling_s2_rate_cache = sf_result
                return sf_result

        from gtm_model.stages import calculate_s2_to_won_rate

        funnel_cfg = self.get_assumptions().get("funnel", {})
        static_rate = float(funnel_cfg.get("s2_to_won", 0.0) or 0.0)
        if static_rate <= 0:
            static_rate = float(calculate_s2_to_won_rate(
                s2_to_s3=float(funnel_cfg.get("s2_to_s3", 0.40) or 0.40),
                s3_to_s4=float(funnel_cfg.get("s3_to_s4", 0.50) or 0.50),
                s4_to_s5=float(funnel_cfg.get("s4_to_s5", 0.60) or 0.60),
                s5_to_won=float(funnel_cfg.get("s5_to_won", 0.80) or 0.80),
            ))
        result = {"rate": static_rate, "source": "config", "sample": 0, "lookback_days": 0}
        self._rolling_s2_rate_cache = result
        return result

    def get_s2_to_won_rate(self) -> float:
        """Return the composite S2-to-Won conversion rate."""
        rolling = self.get_rolling_s2_to_won_rate()
        if rolling["source"] != "config" and rolling.get("sample", 0) >= 20:
            return rolling["rate"]

        from gtm_model.stages import calculate_s2_to_won_rate

        funnel_cfg = self.get_assumptions().get("funnel", {})
        explicit = float(funnel_cfg.get("s2_to_won", 0.0) or 0.0)
        if explicit > 0:
            return explicit
        return float(calculate_s2_to_won_rate(
            s2_to_s3=float(funnel_cfg.get("s2_to_s3", 0.40) or 0.40),
            s3_to_s4=float(funnel_cfg.get("s3_to_s4", 0.50) or 0.50),
            s4_to_s5=float(funnel_cfg.get("s4_to_s5", 0.60) or 0.60),
            s5_to_won=float(funnel_cfg.get("s5_to_won", 0.80) or 0.80),
        ))

    def get_stage_win_rates(
        self,
        resolve_s2_to_won: Optional[Callable[[], float]] = None,
    ) -> dict[str, float]:
        """Return stage-to-Won probabilities for open opportunity runoff."""
        assumptions = self.get_assumptions()
        stage_cfg = assumptions.get("forecast", {}).get("stage_conversion", {}) or {}
        funnel_cfg = assumptions.get("funnel", {})
        s5_to_won = float(stage_cfg.get("s5_to_won", funnel_cfg.get("s5_to_won", 0.80)) or 0.80)
        s4_to_won = float(stage_cfg.get("s4_to_won", 0.0) or 0.0)
        s3_to_won = float(stage_cfg.get("s3_to_won", 0.0) or 0.0)
        s2_to_won = float(stage_cfg.get("s2_to_won", funnel_cfg.get("s2_to_won", 0.0)) or 0.0)
        s4_to_s5 = float(funnel_cfg.get("s4_to_s5", 0.60) or 0.60)
        s3_to_s4 = float(funnel_cfg.get("s3_to_s4", 0.50) or 0.50)
        s1_to_s2 = float(funnel_cfg.get("s1_to_s2", 0.25) or 0.25)
        s0_to_s1 = float(funnel_cfg.get("s0_to_s1", 0.55) or 0.55)

        if s4_to_won <= 0:
            s4_to_won = s4_to_s5 * s5_to_won
            logger.warning(
                "s4_to_won fell back to sequential: %.3f (s4_to_s5=%.2f * s5_to_won=%.2f)",
                s4_to_won,
                s4_to_s5,
                s5_to_won,
            )
        if s3_to_won <= 0:
            s3_to_won = s3_to_s4 * s4_to_won
            logger.warning("s3_to_won fell back to sequential: %.3f", s3_to_won)
        if s2_to_won <= 0:
            s2_to_won = resolve_s2_to_won() if resolve_s2_to_won is not None else self.get_s2_to_won_rate()

        return {
            "S0": s0_to_s1 * s1_to_s2 * s2_to_won,
            "S1": s1_to_s2 * s2_to_won,
            "S2": s2_to_won,
            "S3": s3_to_won,
            "S4": s4_to_won,
            "S5": s5_to_won,
        }

    def get_actual_decay_from_cdw(
        self,
        config_curve: Optional[list[float]] = None,
    ) -> list[float]:
        """Build actual decay distribution from warehouse closed-won timing data."""
        timing = self.try_closed_won_timing()
        if not timing:
            return list(config_curve) if config_curve is not None else self.get_decay_curve()

        total = sum(entry["count"] for entry in timing)
        if total == 0:
            return list(config_curve) if config_curve is not None else self.get_decay_curve()

        actual = [0.0] * 9
        for entry in timing:
            bucket = min(entry["months_from_s2"], 8)
            if 0 <= bucket < 9:
                actual[bucket] += entry["count"]

        return [bucket_count / total for bucket_count in actual]

    def get_observed_decay_curve(
        self,
        config_curve: Optional[list[float]] = None,
    ) -> dict:
        """Return close-timing decay curve with source-specific sample thresholds."""
        if self._decay_curve_cache is not None:
            return self._decay_curve_cache

        timing = self.try_closed_won_timing()
        if timing:
            source = self.get_closed_won_timing_source() or "warehouse"
            min_sample = 30 if source == "warehouse" else 10 if source == "Salesforce" else 30
            total = sum(entry["count"] for entry in timing)
            if total >= min_sample:
                curve = [0.0] * 9
                for entry in timing:
                    bucket = min(entry["months_from_s2"], 8)
                    if 0 <= bucket < 9:
                        curve[bucket] += entry["count"]
                curve = [bucket_count / total for bucket_count in curve]
                result = {
                    "curve": curve,
                    "source": source,
                    "sample": total,
                    "minimum_sample": min_sample,
                    "sample_quality": "strong" if total >= 30 else "usable",
                }
                self._decay_curve_cache = result
                return result

        curve = list(config_curve) if config_curve is not None else self.get_decay_curve()
        result = {"curve": curve, "source": "config", "sample": 0}
        self._decay_curve_cache = result
        return result

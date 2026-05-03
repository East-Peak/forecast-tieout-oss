"""Stage-velocity runtime helpers for Planning Tie-Out."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional

from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


@dataclass
class TieoutStageVelocityResolver:
    """Resolve observed stage timing with warehouse/Salesforce fallbacks.

    Per ARCHITECTURE.md: when get_backend yields a ProfileBackend, the
    backend's compute_observed_velocity() is consulted before warehouse/SF.
    For OSS profiles without a warehouse, this is the only path that
    produces observed (vs config-assumed) stage velocity.
    """

    get_cdw: Callable[[], object | None]
    get_sf: Callable[[], object | None]
    is_cdw_query_failed: Callable[[], bool]
    get_backend: Optional[Callable[[], object | None]] = None  # ProfileBackend

    _stage_velocity_cache: Optional[dict] = None

    def get_observed_stage_velocity(self) -> dict:
        """Try ProfileBackend → warehouse → SF → config assumptions."""
        if self._stage_velocity_cache is not None:
            return self._stage_velocity_cache

        min_sample_per_stage = 10

        # Backend-first path
        if self.get_backend is not None:
            try:
                backend = self.get_backend()
            except Exception:
                backend = None
            if backend is not None:
                try:
                    profile = backend.compute_observed_velocity(
                        as_of=date.today(),
                    )
                    if profile.stage_velocity_days:
                        # Wrap derived/* shape into legacy
                        # {stage_days, source, sample_sizes} dict
                        from gtm_model.velocity import get_assumed_stage_velocity

                        assumed = get_assumed_stage_velocity()
                        merged_days = {}
                        for stage in ("S0", "S1", "S2", "S3", "S4", "S5"):
                            if stage in profile.stage_velocity_days:
                                merged_days[stage] = profile.stage_velocity_days[stage]
                            else:
                                merged_days[stage] = assumed.stage_days.get(stage, 14)
                        result = {
                            "stage_days": merged_days,
                            "source": "ProfileBackend",
                            "sample_sizes": {},  # derived module doesn't expose; ok
                        }
                        self._stage_velocity_cache = result
                        return result
                except Exception as exc:
                    logger.info("ProfileBackend stage velocity unavailable: %s", exc)

        cdw = self.get_cdw()
        if cdw and not self.is_cdw_query_failed():
            try:
                result = self.get_stage_velocity_from_cdw(min_sample_per_stage)
                if result:
                    self._stage_velocity_cache = result
                    return result
            except Exception as exc:
                logger.info("warehouse stage velocity unavailable: %s", exc)

        sf = self.get_sf()
        if sf:
            try:
                from gtm_model.velocity import calculate_stage_velocity_from_history, get_assumed_stage_velocity

                history = sf.get_stage_history(
                    start_date=date.today() - relativedelta(months=12),
                    end_date=date.today(),
                )
                if history:
                    velocity = calculate_stage_velocity_from_history(history)
                    max_sample = max(velocity.sample_sizes.values()) if velocity.sample_sizes else 0
                    if max_sample >= min_sample_per_stage:
                        assumed = get_assumed_stage_velocity()
                        merged_days = {}
                        for stage in ("S0", "S1", "S2", "S3", "S4", "S5"):
                            if velocity.sample_sizes.get(stage, 0) >= min_sample_per_stage:
                                merged_days[stage] = velocity.stage_days[stage]
                            else:
                                merged_days[stage] = assumed.stage_days.get(stage, 14)
                        result = {
                            "stage_days": merged_days,
                            "source": "Salesforce",
                            "sample_sizes": dict(velocity.sample_sizes),
                        }
                        self._stage_velocity_cache = result
                        return result
            except Exception as exc:
                logger.info("SF stage velocity unavailable: %s", exc)

        from gtm_model.velocity import get_assumed_stage_velocity

        assumed = get_assumed_stage_velocity()
        result = {
            "stage_days": dict(assumed.stage_days),
            "source": "config",
            "sample_sizes": {},
        }
        self._stage_velocity_cache = result
        return result

    def get_stage_velocity_from_cdw(self, min_sample: int) -> Optional[dict]:
        """Query the warehouse's per-deal stage-velocity mart.

        Default implementation returns None (no warehouse adapter shipped).
        Subclass and provide your own SQL when wiring a warehouse backend.
        Expected return shape: {stage_days: {S0: float, ...},
        sample_sizes: {S0: int, ...}}.
        """
        cdw = self.get_cdw()
        if not cdw:
            return None

        stage_cols = {
            "S0": "DAYS_S0_TO_S1",
            "S1": "DAYS_S1_TO_S2",
            "S2": "DAYS_S2_TO_S3",
            "S3": "DAYS_S3_TO_S4",
            "S4": "DAYS_S4_TO_S5",
            "S5": "DAYS_S5_TO_S6",
        }
        select_parts = []
        for stage, col in stage_cols.items():
            select_parts.append(
                f"COALESCE(AVG(CASE WHEN {col} > 0 THEN {col} END), 0)::FLOAT AS avg_{stage.lower()}"
            )
            select_parts.append(f"COUNT(CASE WHEN {col} > 0 THEN 1 END)::INTEGER AS n_{stage.lower()}")

        # Warehouse-specific code path — runs only when a warehouse
        # adapter is provided by a forker. Replace the table name with
        # whatever your warehouse uses for per-deal stage timing.
        table_name = getattr(cdw, "OPPORTUNITY_DETAIL_TABLE", "your_opp_detail_table")
        sql = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM {cdw.DATABASE}.{cdw.MART_SCHEMA}.{table_name} "
            f"WHERE CREATED_DATE >= DATEADD(month, -12, CURRENT_DATE())"
        )
        rows = cdw._run_snow_query(sql)
        if not rows:
            return None

        row = rows[0]
        stage_days = {}
        sample_sizes = {}

        from gtm_model.velocity import get_assumed_stage_velocity

        assumed = get_assumed_stage_velocity()
        any_sufficient = False
        for stage in ("S0", "S1", "S2", "S3", "S4", "S5"):
            key_avg = f"AVG_{stage}"
            key_n = f"N_{stage}"
            avg_val = row.get(key_avg) or row.get(key_avg.lower())
            n_val = row.get(key_n) or row.get(key_n.lower()) or 0
            n_val = int(n_val)
            sample_sizes[stage] = n_val

            if n_val >= min_sample and avg_val and float(avg_val) > 0:
                stage_days[stage] = float(avg_val)
                any_sufficient = True
            else:
                stage_days[stage] = assumed.stage_days.get(stage, 14)

        if not any_sufficient:
            return None

        return {
            "stage_days": stage_days,
            "source": "warehouse",
            "sample_sizes": sample_sizes,
        }

    def get_stage_velocity_days(self) -> dict[str, float]:
        """Return stage-by-stage timing for inventory runoff."""
        return self.get_observed_stage_velocity()["stage_days"]

"""Roster build: ProfileBackend team data → warehouse active AEs → YAML; plus phantom-AE staggered start dates and override merging."""

from __future__ import annotations

import copy
import logging
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

from gtm_model.tieout.infra.data_access._helpers import (
    _parse_month_target_key,
    _stable_override_cache_key,
)

logger = logging.getLogger(__name__)


class RosterMixin:
    def generate_staggered_start_dates(self, count: int) -> list[str]:
        """Generate staggered start dates for phantom AEs."""
        from gtm_model.roster import load_roster_data

        planned_dates: list[str] = []
        try:
            roster_data = load_roster_data(self.load_config_yaml("roster.yaml"))
            for entry in roster_data.get("planned", []):
                dt = entry.get("expected_start")
                if dt:
                    planned_dates.append(str(dt))
        except Exception:
            pass

        planned_dates.sort()
        today = date.today()
        future_planned = [entry for entry in planned_dates if date.fromisoformat(entry) >= today]

        if count <= len(future_planned):
            if count == 1:
                indices = [0]
            else:
                indices = [
                    round(i * (len(future_planned) - 1) / (count - 1))
                    for i in range(count)
                ]
            return [future_planned[idx] for idx in indices]

        result = list(future_planned)
        remaining = count - len(result)
        if remaining > 0:
            fy_end = date(2027, 1, 31)
            if future_planned:
                last_planned = date.fromisoformat(future_planned[-1])
                spread_start = (last_planned + relativedelta(months=1)).replace(day=1)
            else:
                spread_start = (today + relativedelta(months=1)).replace(day=1)

            if spread_start > fy_end:
                spread_start = fy_end.replace(day=1)

            months_available = max(
                (fy_end.year - spread_start.year) * 12
                + (fy_end.month - spread_start.month) + 1,
                1,
            )

            for index in range(remaining):
                month_offset = int(index * months_available / remaining)
                hire_date = spread_start + relativedelta(months=month_offset)
                if hire_date > fy_end:
                    hire_date = fy_end.replace(day=1)
                result.append(hire_date.isoformat())

        result.sort()
        return result

    def try_roster(self, ae_overrides: Optional[dict] = None) -> Optional[list[dict]]:
        """Build a full roster from warehouse plus YAML, or return `None` on failure.

        Per ARCHITECTURE.md: when a ProfileBackend is configured, its
        fetch_team_members() output is used as the active-AE input
        (replacing warehouse's get_active_aes). YAML augmentation
        (roster.yaml's planned hires + overrides) still applies on top.
        """
        cache_key = _stable_override_cache_key(ae_overrides)
        roster_cache = self.get_roster_cache()
        if cache_key in roster_cache:
            return copy.deepcopy(roster_cache[cache_key])
        try:
            from gtm_model.roster import get_full_roster_from_data, project_capacity_timeline

            sf_active_aes = []

            # Backend-first path: prefer ProfileBackend's team data over warehouse
            if self.get_backend is not None:
                try:
                    backend = self.get_backend()
                except Exception:
                    backend = None
                if backend is not None:
                    try:
                        members = backend.fetch_team_members()
                        sf_active_aes = [
                            {
                                "id": tm.id,
                                "name": tm.name,
                                "role": tm.role,
                                "segment": tm.segment,
                                "start_date": (
                                    tm.start_date.isoformat() if tm.start_date else None
                                ),
                                "is_active": tm.is_active,
                                "manager_id": tm.manager_id,
                            }
                            for tm in members
                            if tm.is_active
                        ]
                    except Exception as exc:
                        logger.warning(
                            "ProfileBackend.fetch_team_members() failed: %s", exc
                        )
                        sf_active_aes = []

            if not sf_active_aes:
                cdw = self.get_cdw()
                if cdw is not None and not self.is_cdw_query_failed():
                    try:
                        sf_active_aes = cdw.get_active_aes()
                    except Exception as exc:
                        logger.warning("warehouse active AEs query failed: %s", exc)

            roster = get_full_roster_from_data(
                sf_active_aes,
                self.load_config_yaml("roster.yaml"),
            )
            if not roster:
                return None

            if ae_overrides and "month_targets" in ae_overrides:
                normalized_targets = {
                    _parse_month_target_key(month): int(target)
                    for month, target in (ae_overrides.get("month_targets") or {}).items()
                    if int(target or 0) > 0
                }

                if normalized_targets:
                    start_month = min(normalized_targets)
                    end_month = max(normalized_targets)
                    span_months = (
                        (end_month.year - start_month.year) * 12
                        + (end_month.month - start_month.month)
                        + 1
                    )
                    next_override_index = (
                        sum(1 for entry in roster if str(entry.get("name", "")).startswith("Override AE "))
                        + 1
                    )

                    for target_month, target_total in sorted(normalized_targets.items()):
                        timeline = project_capacity_timeline(
                            roster=roster,
                            start_month=start_month,
                            months=span_months,
                        )
                        current_total = next(
                            (row.get("total_count", 0) for row in timeline if row.get("month") == target_month),
                            0,
                        )
                        shortfall = max(int(target_total) - int(current_total), 0)
                        for _ in range(shortfall):
                            roster.append({
                                "name": f"Override AE {next_override_index}",
                                "segment": "enterprise",
                                "start_date": target_month.isoformat(),
                                "tier": "planned",
                            })
                            next_override_index += 1
            elif ae_overrides and "add_aes" in ae_overrides:
                add_count = ae_overrides["add_aes"]
                staggered_dates = self.generate_staggered_start_dates(add_count)
                for index in range(add_count):
                    roster.append({
                        "name": f"Override AE {index + 1}",
                        "segment": "enterprise",
                        "start_date": staggered_dates[index],
                        "tier": "planned",
                    })
            elif ae_overrides and "total_aes" in ae_overrides:
                target = ae_overrides["total_aes"]
                current = len(roster)
                if target > current:
                    add_count = target - current
                    staggered_dates = self.generate_staggered_start_dates(add_count)
                    for index in range(add_count):
                        roster.append({
                            "name": f"Override AE {index + 1}",
                            "segment": "enterprise",
                            "start_date": staggered_dates[index],
                            "tier": "planned",
                        })

            roster_cache[cache_key] = copy.deepcopy(roster)
            return roster
        except Exception as exc:
            logger.warning("Roster build failed: %s", exc)
            roster_cache[cache_key] = None
            return None


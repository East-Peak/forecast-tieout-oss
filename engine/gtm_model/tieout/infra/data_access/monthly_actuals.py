"""Monthly actuals resolution: ProfileBackend → bookings summary → empty rail."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from gtm_model.tieout.infra.data_access._helpers import _monthly_series_to_rows

logger = logging.getLogger(__name__)


class MonthlyActualsMixin:
    def get_monthly_actuals(
        self,
        as_of: date,
        months: int = 12,
        fy_start: date | None = None,
    ) -> dict:
        """Return canonical monthly actuals for the saved snapshot artifact.

        The generator and any audit-grade consumers should read these series
        through the shared runtime snapshot instead of issuing ad hoc
        connector-specific queries.

        Resolution order (per ARCHITECTURE.md): ProfileBackend first, then
        warehouse per-series fallbacks, then SF, then empty.
        """
        del months  # The current artifact only serializes completed months through as_of.
        start_date = fy_start or date(as_of.year - 1, as_of.month, 1)
        end_date = as_of

        # Backend-first path
        backend_result = self._monthly_actuals_from_backend(start_date, end_date)
        if backend_result is not None:
            return backend_result

        bookings_by_month, bookings_provenance = self._resolve_monthly_amount_series(
            start_date=start_date,
            end_date=end_date,
            cdw_loader=lambda cdw, start, end: cdw.get_monthly_bookings(start, end),
            sf_loader=lambda sf, start, end: sf.get_monthly_bookings(start, end),
            cdw_method="monthly_closed_won_close_date_amount",
            sf_method="monthly_closed_won_close_date_amount",
            unavailable_warning="Monthly bookings actuals unavailable.",
        )

        losses_by_month, losses_provenance = self._resolve_monthly_amount_series(
            start_date=start_date,
            end_date=end_date,
            cdw_loader=lambda cdw, start, end: cdw.get_monthly_closed_lost(start, end),
            sf_loader=lambda sf, start, end: sf.get_monthly_closed_lost(start, end),
            cdw_method="monthly_closed_lost_closed_at_amount",
            sf_method="monthly_closed_lost_closed_at_amount",
            unavailable_warning="Monthly losses actuals unavailable.",
        )

        pipeline_created_by_month, pipeline_provenance = self._resolve_monthly_amount_series(
            start_date=start_date,
            end_date=end_date,
            cdw_loader=lambda cdw, start, end: cdw.get_monthly_pipeline_creation(start, end),
            sf_loader=lambda sf, start, end: sf.get_monthly_pipeline_creation(start, end),
            cdw_method="monthly_opp_created_amount_for_s2_plus_or_closed",
            sf_method="monthly_opp_created_amount_for_s2_plus_or_closed",
            unavailable_warning="Monthly opportunity creation actuals unavailable.",
        )

        pipeline_entered_s2_by_month, pipeline_entered_s2_provenance = self._resolve_monthly_amount_series(
            start_date=start_date,
            end_date=end_date,
            cdw_loader=lambda cdw, start, end: cdw.get_monthly_s2_created(start, end),
            sf_loader=lambda sf, start, end: sf.get_monthly_s2_created(start, end),
            cdw_method="monthly_entered_s2_amount",
            sf_method="monthly_entered_s2_amount",
            unavailable_warning="Monthly S2-entry actuals unavailable.",
        )

        return {
            "bookings_by_month": _monthly_series_to_rows(bookings_by_month),
            "losses_by_month": _monthly_series_to_rows(losses_by_month),
            "pipeline_created_by_month": _monthly_series_to_rows(pipeline_created_by_month),
            "pipeline_entered_s2_by_month": _monthly_series_to_rows(pipeline_entered_s2_by_month),
            "provenance": {
                "bookings_by_month": bookings_provenance,
                "losses_by_month": losses_provenance,
                "pipeline_created_by_month": pipeline_provenance,
                "pipeline_entered_s2_by_month": pipeline_entered_s2_provenance,
            },
        }

    def _monthly_actuals_from_backend(
        self, start_date: date, end_date: date
    ) -> Optional[dict]:
        """Compute monthly actuals from a ProfileBackend.

        Returns None when no backend is configured (legacy mode falls
        through to the warehouse/SF chain). Returns the legacy-shape dict
        with all four series populated when the backend has data.
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
            actuals = backend.compute_monthly_actuals(start_date, end_date)
        except Exception as exc:
            logger.warning("ProfileBackend monthly actuals failed: %s", exc)
            return None

        provenance = {
            "source": "ProfileBackend",
            "method": "backend_compute_monthly_actuals",
            "is_live": True,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        rows = actuals.as_rows()
        return {
            "bookings_by_month": rows["monthly_bookings"],
            "losses_by_month": rows["monthly_closed_lost"],
            "pipeline_created_by_month": rows["monthly_pipeline_creation"],
            "pipeline_entered_s2_by_month": rows["monthly_entered_s2"],
            "provenance": {
                "bookings_by_month": dict(provenance, series="bookings"),
                "losses_by_month": dict(provenance, series="losses"),
                "pipeline_created_by_month": dict(provenance, series="creation"),
                "pipeline_entered_s2_by_month": dict(provenance, series="entered_s2"),
            },
        }

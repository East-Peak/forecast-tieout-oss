"""Paired counterfactuals: the same company and seed with one intervention changed.

Common random numbers: every random quantity is drawn from a stream keyed by the
entity it belongs to (rng.py) and all of an entity's draws are made once, at its
creation. Delaying a hire or changing a program's budget therefore changes only
what depends on it: a lead exists at (campaign, day, k) in both runs, and its
segment, fit, deal size, win draw and cycle are identical; extra spend only adds
leads, because the daily count is an inverse-CDF Poisson draw from one uniform per
campaign-day, which is monotone in the rate. What differs is what the mechanism
makes of them (who has room, how long a queue waits, which deals are admitted).
"""

from dataclasses import dataclass
from datetime import date

import numpy as np

from ..contract.snapshot import Snapshot
from .params import CompanyParams, Intervention
from .run import Company, run_company


def slip_hire(req_id: str, days: int) -> Intervention:
    """The hire on requisition `req_id` starts `days` later than it otherwise would."""
    return Intervention(slip_hire=(req_id, days))


def change_spend(campaign: str, from_month: date, factor: float) -> Intervention:
    """The program's monthly budget is multiplied by `factor` from `from_month` on."""
    return Intervention(spend_change=(campaign, from_month, factor))


@dataclass
class Pair:
    base: Company
    alt: Company

    @property
    def truths(self) -> tuple[Snapshot, Snapshot]:
        return self.base.truth, self.alt.truth


def paired_counterfactual(
    params: CompanyParams,
    seed: int,
    intervention: Intervention,
    extract_days: tuple[int, ...] = (),
) -> Pair:
    return Pair(
        run_company(params, seed, None, extract_days),
        run_company(params, seed, intervention, extract_days),
    )


def fiscal_year_total(truth: Snapshot, measure: str, fiscal_year: int) -> int:
    """Sum of a (lane, month) measure over a fiscal year (named by its starting year, Feb to Jan)."""
    first, last = f"{fiscal_year}-02", f"{fiscal_year + 1}-01"
    cols = [i for i, m in enumerate(truth.months) if first <= m <= last]
    return int(np.asarray(getattr(truth, measure).values)[:, cols].sum())

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
from .people import day_of
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
    params: CompanyParams, seed: int, intervention: Intervention
) -> Pair:
    """ONE realization of the difference an intervention makes, on one seed's single future.

    It is not an expected value: after the first diverging admission the two runs drift apart
    by chance (a demand-limited company shows "effects" of either sign). Use `expected_effect`
    to benchmark a forecaster's sensitivity."""
    return Pair(
        run_company(params, seed, None), run_company(params, seed, intervention)
    )


def fiscal_year_total(truth: Snapshot, measure: str, fiscal_year: int) -> int:
    """Sum of a (lane, month) measure over a fiscal year (named by its starting year, Feb to Jan)."""
    first, last = f"{fiscal_year}-02", f"{fiscal_year + 1}-01"
    cols = [i for i, m in enumerate(truth.months) if first <= m <= last]
    return int(np.asarray(getattr(truth, measure).values)[:, cols].sum())


@dataclass(frozen=True)
class Effect:
    """Mean difference (intervention minus base) of a truth measure over replicated futures."""

    mean: float
    se: float
    diffs: tuple[float, ...]
    replicates: int
    fork_date: date
    measure: str
    fiscal_year: int


def _replicate(args):
    params, seed, interventions, fork_day, r, measure, fy = args
    base = fiscal_year_total(
        run_company(params, seed, None, r, fork_day).truth, measure, fy
    )
    return {
        name: fiscal_year_total(
            run_company(params, seed, iv, r, fork_day).truth, measure, fy
        )
        - base
        for name, iv in interventions.items()
    }


def expected_effects(
    params: CompanyParams,
    seed: int,
    interventions: dict[str, Intervention],
    fork_date: date | None = None,
    replicates: int = 40,
    measure: str = "bookings_cents",
    fiscal_year: int = 2025,
    workers: int = 1,
) -> dict[str, Effect]:
    """Expected effect of each intervention, conditional on the company as it stands at `fork_date`.

    The company is identical up to the fork (default: the plan date). For replicate r, every
    entity created on or after the fork (leads, deals, hires, budgets, and the post-fork
    departure of people already employed) is re-keyed by r, giving an independent future; base
    and intervention then run as a common-random-number pair. Deals already open at the fork
    keep the latent fates they were drawn with, so the answer is conditional on them.
    The mean over replicates estimates the expected change, `se` its standard error."""
    fork = fork_date or params.plan_date
    jobs = [
        (params, seed, interventions, day_of(fork), r, measure, fiscal_year)
        for r in range(replicates)
    ]
    if workers > 1:
        import multiprocessing

        with multiprocessing.get_context("fork").Pool(workers) as pool:
            rows = pool.map(_replicate, jobs)
    else:
        rows = [_replicate(j) for j in jobs]
    out = {}
    for name in interventions:
        diffs = np.array([row[name] for row in rows], dtype=float)
        se = (
            float(diffs.std(ddof=1) / np.sqrt(len(diffs)))
            if len(diffs) > 1
            else float("nan")
        )
        out[name] = Effect(
            float(diffs.mean()),
            se,
            tuple(diffs),
            replicates,
            fork,
            measure,
            fiscal_year,
        )
    return out


def expected_effect(
    params: CompanyParams,
    seed: int,
    intervention: Intervention,
    fork_date: date | None = None,
    replicates: int = 40,
    measure: str = "bookings_cents",
    fiscal_year: int = 2025,
    workers: int = 1,
) -> Effect:
    return expected_effects(
        params,
        seed,
        {"x": intervention},
        fork_date,
        replicates,
        measure,
        fiscal_year,
        workers,
    )["x"]

"""Score the Goal 2A candidates on the three demo companies' frozen data.

The recency candidate is decided per company inside every report. The ranges
candidate is decided once, pooled across the demo companies, by the declared
rule in ``backtest.ranges_decision``; ``fit.DEFAULT_PARAMS.ranges`` records
the outcome and a test holds it to this computation.

    python -m engine.tieout_core candidates     # print both before-and-after tables
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from .backtest import (
    Comparison,
    HorizonScore,
    RangesDecision,
    backtest,
    choose_fit,
    coverage_label,
    ranges_decision,
)
from .fit import DEFAULT_PARAMS, OUTCOME_RANGES, PARAMETER_RANGES
from .load import load_company, load_profile
from .reconcile import reconcile

DEMO_COMPANIES = ("sprout-labs", "sapling-industries", "mighty-oak-holdings")
PROFILES = Path("engine/config/profiles")
DATA = Path("engine/data-v2")
AS_OF = date(2026, 8, 31)
DRAWS = 1000  # the report's back-test draws at its default of 2000


@dataclass(frozen=True)
class Scored:
    recency: dict[str, Comparison]
    fit_in_use: dict[str, str]
    before: dict[tuple[str, int], HorizonScore]  # outcome-only ranges
    after: dict[tuple[str, int], HorizonScore]  # with rate uncertainty
    decision: RangesDecision


def _population(slug: str):
    profile = load_profile(PROFILES / slug)
    rec = reconcile(DATA / slug, load_company(DATA / slug, profile), profile, AS_OF)
    return profile, rec.population


def score_ranges(companies=DEMO_COMPANIES, draws: int = DRAWS, seed: int = 0) -> Scored:
    recency, in_use, before, after = {}, {}, {}, {}
    base = replace(DEFAULT_PARAMS, ranges=OUTCOME_RANGES)
    for slug in companies:
        profile, pop = _population(slug)
        params, _, cmp = choose_fit(pop, AS_OF, profile, base, draws, seed)
        recency[slug], in_use[slug] = cmp, params.estimator
        for ranges, out in ((OUTCOME_RANGES, before), (PARAMETER_RANGES, after)):
            bt = backtest(
                pop, AS_OF, profile, replace(params, ranges=ranges), draws, seed
            )
            for s in bt.scores:
                out[(slug, s.horizon)] = s
    decision = ranges_decision(
        {k: (s.inside80, s.range_folds) for k, s in before.items()},
        {k: (s.inside80, s.range_folds) for k, s in after.items()},
    )
    return Scored(recency, in_use, before, after, decision)


def render(scored: Scored) -> str:
    def pct(x):
        return "n/a" if x is None else f"{x:.0%}"

    def usd(x):
        return "n/a" if x is None else f"${x:,.0f}"

    out = [
        "Recency (per company, same folds; adopted if lower at 1 and 3 months):",
        "",
        "| Company | 1m matured | 1m recency | 3m matured | 3m recency | Folds 1m/3m | Adopted |",
        "|---|---|---|---|---|---|---|",
    ]
    for slug, c in scored.recency.items():
        (a1, b1), (a3, b3) = c.mae[1], c.mae[3]
        out.append(
            f"| {slug} | {usd(a1)} | {usd(b1)} | {usd(a3)} | {usd(b3)} | "
            f"{c.folds[1]}/{c.folds[3]} | {'yes' if c.adopted else 'no'} |"
        )
    out += [
        "",
        "Ranges (80% coverage, median 80% width, folds; fit in use per company):",
        "",
        (
            "| Company | Horizon | Folds | Coverage before | Coverage after | Width before | "
            "Width after | Label before | Label after |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (slug, h), b in scored.before.items():
        a = scored.after[(slug, h)]
        out.append(
            f"| {slug} ({scored.fit_in_use[slug]}) | {h}m | {b.range_folds} | {pct(b.coverage80)} | "
            f"{pct(a.coverage80)} | {usd(b.median_width80)} | {usd(a.median_width80)} | "
            f"{coverage_label(b.inside80, b.range_folds)} | {coverage_label(a.inside80, a.range_folds)} |"
        )
    d = scored.decision
    pooled = "; ".join(f"{h}m {pct(b)} -> {pct(a)}" for h, (b, a) in d.pooled.items())
    out += [
        "",
        f"Pooled 80% coverage: {pooled}.",
        f"Decision: {'adopted' if d.adopted else 'not adopted'}: {d.reason}.",
    ]
    return "\n".join(out) + "\n"

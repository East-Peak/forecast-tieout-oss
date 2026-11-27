"""The capacity half of the report: roster and capacity (section 8) and quota
against observed productivity (section 9). Presentation of numbers computed by
``roster``, ``ramp``, ``capacity`` and ``adoption``; the forward function stays
in ``forecast``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np

from . import capacity_rules as rules
from .adoption import ADOPTED, Adoption, adoption_test
from .backtest import CreationFor
from .capacity import CapacityFit, fit_capacity, project
from .capacity_config import (
    CapacityConfig,
    RosterLoad,
    load_capacity,
    load_headcount_targets,
    load_roster,
)
from .figures import exact, money, number
from .fiscal import Window, add_months, month_windows
from .fit import FitParams
from .forecast import Creation
from .plan import DEFAULT_PROGRAMME_RAMP_MONTHS
from .rates import DEFAULT, ENTERED, FITTED, Rate
from .records import Check, Dataset
from .roster import (
    Member,
    employed,
    heads_on,
    ramped_ae_months,
    ramped_heads_on,
    roster_at,
)

SPREAD_MIN_DAYS = (
    180  # reps employed fewer days than this are in totals, not in the spread
)
ASSOCIATION = (
    "An association in the history, not a promise: that a new hire adds pipeline at this rate "
    "is an assumption."
)
LIMITS = (
    (
        "team_members.csv records no history of role, segment, quota or deal ownership: today's "
        "values stand in for every past date"
    ),
    "a deal's owner is its current owner, not necessarily the person who created it",
    "people who left the company before the first deal in the files are not on the roster",
)


@dataclass(frozen=True)
class Capacity:
    cfg: CapacityConfig | None
    roster: RosterLoad
    adoption: Adoption
    fit: CapacityFit | None  # fitted at the as-of; None when it cannot be
    projection: Creation | None  # the roster's expected creation, as signed
    horizon_days: int
    since: date | None

    @property
    def adopted(self) -> bool:
        return self.adoption.outcome == ADOPTED and self.projection is not None

    @property
    def creation(self) -> Creation | None:
        """The creation the forward function uses: the capacity term only when adopted."""
        return self.projection if self.adopted else None

    @property
    def members(self) -> tuple[Member, ...]:
        return self.roster.members


def prepare(
    profile_dir: Path,
    data_dir: Path,
    pop: Dataset,
    as_of: date,
    horizon_days: int,
    params: FitParams,
) -> Capacity:
    cfg = load_capacity(profile_dir)
    roster = load_roster(Path(data_dir) / "team_members.csv", cfg)
    adoption = adoption_test(
        pop, roster.members, cfg, as_of, params, roster.unavailable
    )
    fit = projection = since = None
    if cfg is not None and roster.members and pop.deals:
        since = min(d.created for d in pop.deals)
        fit = fit_capacity(pop.deals, roster.members, as_of, since, cfg)
        if fit.unavailable:
            fit = None
        else:
            projection = project(fit, roster.members, as_of, horizon_days)
    return Capacity(cfg, roster, adoption, fit, projection, horizon_days, since)


def creation_for(cap: Capacity) -> CreationFor | None:
    """The capacity term at a past cutoff, from the roster known then: starts
    and departures after the cutoff are invisible. None unless adopted."""
    if not cap.adopted:
        return None
    cache: dict[date, CapacityFit] = {}

    def for_cutoff(cutoff: date, known: Dataset, horizon_days: int) -> Creation | None:
        if cutoff not in cache:
            cache[cutoff] = fit_capacity(
                known.deals, cap.members, cutoff, cap.since, cap.cfg
            )
        fit = cache[cutoff]
        if fit.unavailable:
            return None
        return project(fit, roster_at(cap.members, cutoff), cutoff, horizon_days)

    return for_cutoff


# ---------------------------------------------------------------- rates


def rates(cap: Capacity) -> list[Rate]:
    """The capacity rates, for the one rate book."""
    out: list[Rate] = []
    fit, cfg = cap.fit, cap.cfg
    if fit is not None:
        curve, ramp_rate = fit.curve, fit.ramp
        for k, w in enumerate(curve.weights, start=1):
            rng = curve.ranges[k - 1] if curve.ranges else (None, None)
            out.append(
                Rate(
                    f"ramp_weight:{k}", w,
                    f"share of a tenured rep's created deals in tenure month {k}",
                    "deals created by reps in this tenure month",
                    "deals the same reps would have created at the tenured reps' rate in the same calendar months",
                    f"reps observed {cap.since} to {fit.cutoff}", "per tenure month",
                    ramp_rate.reps_observed, curve.source, rng[0], rng[1],
                )
            )  # fmt: skip
        a = fit.attrition
        out.append(
            Rate(
                "attrition_per_ae_month", a.rate,
                "departures per AE-month (monthly attrition)",
                f"{a.departures} departures", f"{a.ae_months:.1f} AE-months employed",
                f"{cap.since} to {fit.cutoff}", "per AE-month", a.departures, a.source,
                a.low95, a.high95,
            )
        )  # fmt: skip
        out.append(
            Rate(
                "created_deals_per_ramped_ae_month", fit.rate,
                "new-business deals created per ramped AE-month",
                f"{fit.trailing_deals} deals created",
                f"{fit.trailing_ramped_months:.2f} ramped AE-months",
                f"trailing {rules.TRAILING_DAYS} days to {fit.cutoff}", "per ramped AE-month",
                fit.trailing_deals, FITTED if fit.trailing_deals else DEFAULT,
            )
        )  # fmt: skip
    if cfg is not None:
        entered = (
            ("loaded_cost_per_ae_month", cfg.loaded_cost_per_ae_month,
             "cash cost of one AE for one month (capacity.yaml)"),
            ("programme_cost_per_dollar_of_pipeline", cfg.programme_cost_per_dollar,
             "cash cost per dollar of programme pipeline created (capacity.yaml)"),
        )  # fmt: skip
        for name, value, definition in entered:
            if value is not None:
                out.append(
                    Rate(
                        name,
                        value,
                        definition,
                        "",
                        "",
                        "capacity.yaml",
                        "unstated",
                        0,
                        ENTERED,
                    )
                )
        ramp_months = cfg.programme_ramp_months
        out.append(
            Rate(
                "programme_ramp_months",
                Decimal(DEFAULT_PROGRAMME_RAMP_MONTHS if ramp_months is None else ramp_months),
                "months a programme takes to reach its full monthly pipeline",
                "", "", "capacity.yaml", "unstated", 0,
                DEFAULT if ramp_months is None else ENTERED,
            )
        )  # fmt: skip
    for name, value, definition in (
        ("capacity_min_staffing_variation", rules.MIN_STAFFING_VARIATION,
         "ramped AE-months must vary by this much across the scored period for capacity to be testable"),
        ("capacity_min_improvement", rules.MIN_IMPROVEMENT,
         "capacity's created-pipeline error must be this much lower than the flat rate's at both horizons"),
        ("capacity_min_folds", Decimal(rules.MIN_FOLDS), "folds needed at each scored horizon"),
        ("days_per_ae_month", rules.DAYS_PER_AE_MONTH, "days in one AE-month"),
    ):  # fmt: skip
        out.append(Rate(name, value, definition, "", "", "", "", 0, DEFAULT))
    return out


# ---------------------------------------------------------------- section 8


def roster_capacity(
    cap: Capacity,
    as_of: date,
    windows: list[Window],
    profile_dir: Path,
    diagnostic: dict | None,
    plan_projection: Creation | None = None,
) -> dict:
    ad = cap.adoption
    out: dict = {
        "decision": {
            "outcome": ad.outcome,
            "reason": ad.reason,
            "scored_on": "created-pipeline dollars at 3 and 6 months on the back-test's folds; the "
            "per-rep rate is fitted only from data before each cutoff and applied to the ramped "
            "AE-months that actually occurred",
            "label": "conditional on realised staffing: it asks whether headcount explains pipeline, "
            "not how well it forecasts",
            "declared_rule": f"adopted only if ramped AE-months varied by at least "
            f"{rules.MIN_STAFFING_VARIATION:.0%} across the scored period, the capacity rate's mean "
            f"absolute error is at least {rules.MIN_IMPROVEMENT:.0%} lower than the flat trailing "
            f"rate's at both 3 and 6 months, and there are at least {rules.MIN_FOLDS} folds at each",
            "staffing_variation": None
            if ad.variation is None
            else number(ad.variation),
            "scored_period": None
            if ad.period is None
            else [d.isoformat() for d in ad.period],
            "horizons": [
                {
                    "horizon_months": h,
                    "folds": s.folds,
                    "mean_absolute_error_flat": money(s.mae_flat),
                    "mean_absolute_error_capacity": money(s.mae_capacity),
                    "improvement": number(s.improvement),
                }
                for h, s in sorted(ad.scores.items())
            ],
            "forecast_uses": "the capacity term (ramped AE-months times created deals per ramped "
            "AE-month)"
            if cap.adopted
            else "the flat trailing creation rate",
            "association": ASSOCIATION,
        },
        "roster": _roster_summary(cap, as_of, profile_dir),
        "limitations": list(LIMITS),
    }
    if cap.fit is not None:
        out["ramp"] = _ramp(cap)
        out["attrition"] = _attrition(cap)
        out["creation_rate"] = {
            "deals_per_ramped_ae_month": number(cap.fit.rate, 6),
            "trailing_deals": cap.fit.trailing_deals,
            "trailing_ramped_ae_months": number(cap.fit.trailing_ramped_months, 2),
            "window": f"trailing {rules.TRAILING_DAYS} days to {as_of}",
        }
    if cap.projection is not None:
        out["months"] = _months(cap, as_of, windows, profile_dir, plan_projection)
    if diagnostic is not None:
        out["diagnostic"] = diagnostic
    return out


def _roster_summary(cap: Capacity, as_of: date, profile_dir: Path) -> dict:
    r = cap.roster
    if r.unavailable:
        return {"unavailable": r.unavailable, "rows": r.rows}
    members = cap.members
    curve = cap.fit.curve if cap.fit else None
    employed_now = [m for m in members if employed(m, as_of)]
    signed = [m for m in members if m.start > as_of]
    targets = load_headcount_targets(profile_dir)
    this_month = f"{as_of.year:04d}-{as_of.month:02d}"
    return {
        "rows": r.rows,
        "quota_carrying_rows": len(members),
        "other_roles_counted_no_capacity": dict(sorted(r.other_roles.items())),
        "excluded": [
            {"id": e.id, "role": e.role, "reason": e.reason} for e in r.excluded
        ],
        "heads_at_as_of": len(employed_now),
        "ramped_equivalents_at_as_of": None
        if curve is None
        else number(ramped_heads_on(members, curve, as_of), 2),
        "headcount_target_this_month": targets.get(this_month),
        "headcount_target_note": "monthly_ae_targets in targets.yaml: a comparison line only; it "
        "never creates a hire",
        "signed_hires": [
            {"id": m.id, "segment": m.segment, "start": m.start.isoformat()}
            for m in signed
        ],
        "departed_to_date": sum(
            1 for m in members if m.end is not None and m.end <= as_of
        ),
    }


def _ramp(cap: Capacity) -> dict:
    fit = cap.fit.ramp
    c = fit.curve
    return {
        "source": c.source,
        "sample": f"{fit.reps_observed} reps observed from hire through their sixth month; "
        f"{fit.tenured_reps} tenured reps alongside",
        "why_not_fitted": fit.reason,
        "weights": [
            {
                "tenure_month": k,
                "weight": number(w),
                "range95": None
                if not c.ranges
                else [number(c.ranges[k - 1][0]), number(c.ranges[k - 1][1])],
            }
            for k, w in enumerate(c.weights, start=1)
        ],
        "after": "1 from the next tenure month on",
        "definition": "created deals per rep by tenure month, relative to reps with twelve or more "
        "months' tenure in the same calendar month",
    }


def _attrition(cap: Capacity) -> dict:
    a = cap.fit.attrition
    return {
        "monthly_rate": number(a.rate, 5),
        "source": a.source,
        "sample": f"{a.departures} departures over {number(a.ae_months, 1)} AE-months",
        "range95": None
        if a.low95 is None
        else [number(a.low95, 5), number(a.high95, 5)],
        "why_not_fitted": a.reason,
        "forward": "an expectation in the headline (a constant daily hazard from this monthly "
        "rate); a random draw in the ranges; nobody is back-filled unless the plan says so",
    }


def _months(cap, as_of, windows, profile_dir, plan_projection) -> list[dict]:
    curve = cap.fit.curve
    targets = load_headcount_targets(profile_dir)
    rows = []
    for w in month_windows(add_months(as_of, -12), as_of):
        rows.append(
            {
                "month": w.label,
                "kind": "past",
                "heads": heads_on(cap.members, w.end),
                "ramped": number(_average(ramped_ae_months(cap.members, curve, w.start, w.end), w), 2),
                "departures": sum(
                    1 for m in cap.members if m.end is not None and w.contains(m.end)
                ),
                "headcount_target": targets.get(w.label),
                "heads_with_plan": None,
            }
        )  # fmt: skip
    p = cap.projection
    for w in windows:
        a, b = (w.start - as_of).days, (w.end - as_of).days
        rows.append(
            {
                "month": w.label,
                "kind": "forward",
                "heads": number(p.heads[b - 1], 1),
                "ramped": number(sum(p.ramped_ae_months[a:b], Decimal(0)) * rules.DAYS_PER_AE_MONTH / (b - a), 2),
                "departures": number(sum(p.departures[a:b], Decimal(0)), 2),
                "headcount_target": targets.get(w.label),
                "heads_with_plan": None
                if plan_projection is None
                else number(plan_projection.heads[b - 1], 1),
            }
        )  # fmt: skip
    return rows


def _average(ae_months: Decimal, w: Window) -> Decimal:
    """Average ramped heads over a window, from its ramped AE-months."""
    return ae_months * rules.DAYS_PER_AE_MONTH / Decimal(w.days)


# ---------------------------------------------------------------- section 9


def quota_productivity(
    cap: Capacity, pop: Dataset, as_of: date, fy_target: Decimal
) -> dict:
    """Observed, never model output: wins credited to the owner on deals.csv and
    closed while that person was employed, over quota prorated by days employed
    in the trailing year."""
    limits = [
        (
            "the owner is the deal's current owner and the quota is today's annual quota, "
            "standing in for their history"
        ),
        "quota is a full-ramp annual figure; ramp is not prorated out of it",
    ]
    if cap.roster.unavailable or not cap.members:
        return {"unavailable": cap.roster.unavailable or "no roster", "limits": limits}
    start = as_of - timedelta(days=rules.TRAILING_DAYS)
    window = Window("trailing", start, as_of)
    won = [d for d in pop.deals if d.is_won and window.contains(d.close)]
    by_id = {m.id: m for m in cap.members}
    credited: dict[str, Decimal] = {}
    unattributed = Decimal(0)
    for d in won:
        m = by_id.get(d.owner_id)
        if m is not None and employed(m, d.close):
            credited[m.id] = credited.get(m.id, Decimal(0)) + d.arr
        else:
            unattributed += d.arr
    reps, no_quota = [], 0  # (member, days employed in the window, prorated quota)
    for m in cap.members:
        lo, hi = max(m.start, start + timedelta(days=1)), min(m.end or as_of, as_of)
        days = (hi - lo).days + 1 if lo <= hi else 0
        if not days:
            continue
        if m.annual_quota is None:
            no_quota += 1
            continue
        reps.append((m, days, m.annual_quota * days / Decimal(rules.TRAILING_DAYS)))
    days_in = {m.id: days for m, days, _ in reps}
    segments: dict[str, list] = {}
    for m, days, quota in reps:
        segments.setdefault(m.segment or "(no segment)", []).append(
            (m, quota, credited.get(m.id, Decimal(0)))
        )

    def block(rows):
        quota = sum((q for _, q, _ in rows), Decimal(0))
        wins = sum((w for _, _, w in rows), Decimal(0))
        att = [
            float(w / q)
            for m, q, w in rows
            if q > 0 and days_in[m.id] >= SPREAD_MIN_DAYS
        ]
        spread = (
            None
            if not att
            else {
                "min": number(min(att), 3),
                "p25": number(np.percentile(att, 25), 3),
                "median": number(np.percentile(att, 50), 3),
                "p75": number(np.percentile(att, 75), 3),
                "max": number(max(att), 3),
            }
        )
        return {
            "reps": len(rows),
            "prorated_quota": money(quota),
            "wins_credited": money(wins),
            "attainment": None if not quota else number(wins / quota, 3),
            "spread_across_reps": spread,
            "spread_reps": len(att),
        }

    all_rows = [r for rows in segments.values() for r in rows]
    employed_now = [m for m in cap.members if employed(m, as_of) and m.annual_quota]
    quota_now = sum((m.annual_quota for m in employed_now), Decimal(0))
    credited_total = sum(credited.values(), Decimal(0))
    return {
        "window": f"trailing {rules.TRAILING_DAYS} days to {as_of}",
        "definition": "wins credited to the owner on deals.csv and closed while that person was "
        "employed, over annual quota prorated by days employed in the window",
        "spread_min_days": SPREAD_MIN_DAYS,
        "by_segment": {s: block(rows) for s, rows in sorted(segments.items())},
        "all_reps": block(all_rows),
        "wins_in_window": money(sum((d.arr for d in won), Decimal(0))),
        "wins_credited": money(credited_total),
        "wins_unattributed": money(unattributed),
        "unattributed_note": "wins whose owner is not on the roster, or who had left or not yet "
        "started on the close date",
        "reps_without_quota": no_quota,
        "total_quota": {
            "annual_quota_of_people_employed_at_as_of": exact(quota_now),
            "fiscal_year_target": exact(fy_target),
            "quota_over_target": None
            if not fy_target
            else number(quota_now / fy_target, 2),
            "people": len(employed_now),
            "note": "full-ramp annual quotas of the quota-carrying people employed on the as-of "
            "date (signed hires excluded) over the fiscal year's bookings target",
        },
        "limits": limits,
    }


# ---------------------------------------------------------------- checks


def checks(cap: Capacity, productivity: dict, fitted) -> list[Check]:
    """Runtime self-checks on the capacity half's own numbers."""
    r = cap.roster
    out = []
    if r.unavailable:
        out.append(
            Check("roster rows partition", True, f"not applicable: {r.unavailable}")
        )
    else:
        parts = len(r.members) + sum(r.other_roles.values()) + len(r.excluded)
        out.append(
            Check(
                "roster rows partition",
                parts == r.rows,
                f"{len(r.members)} quota-carrying + {sum(r.other_roles.values())} other roles + "
                f"{len(r.excluded)} excluded = {parts} of {r.rows} roster rows",
            )
        )
    uses_capacity = any("ramped AE-month" in a for a in fitted.assumptions)
    if fitted.available:
        out.append(
            Check(
                "the forecast uses capacity exactly when it was adopted",
                uses_capacity == cap.adopted
                and (cap.creation is not None) == cap.adopted,
                f"capacity decision: {cap.adoption.outcome}; forecast uses the "
                f"{'capacity term' if uses_capacity else 'flat creation rate'}",
            )
        )
    if "wins_in_window" in productivity:
        total = Decimal(productivity["wins_credited"]) + Decimal(
            productivity["wins_unattributed"]
        )
        out.append(
            Check(
                "wins credited plus unattributed equal bookings in the window",
                total == Decimal(productivity["wins_in_window"]),
                f"{productivity['wins_credited']} + {productivity['wins_unattributed']} = {total} "
                f"against {productivity['wins_in_window']}",
            )
        )
    return out

"""The swimlane grid's figures: one row per lane, five periods, eight columns, three numbers each.

Rows are keyed by a path (the company, then a segment; owners slot in beneath a segment later).
Periods are the fiscal year and its four quarters, on the closing basis: a period's wins are the
wins from pipeline carried in plus the wins from pipeline created in it, and the Won and
Bookings cells show that split. Every figure is built from atoms that add (deals, dollars, win
days, a rate's numerator and denominator), segment by segment, and a parent is the sum of its
children; a rate or a size is then the sum of numerators over the sum of denominators. The
forecast is the pooled model's: an open deal belongs to its own segment, future creation is split
by capacity exposure where that term is adopted and by the frozen creation shares otherwise, and
segment deal sizes only share the pooled forecast out, so the company row is the report's
figure to the cent. Goals are read from the frozen plan basis and nothing else. The core writes
each cell's status; the screen does no arithmetic.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal

from . import driver_actions
from . import lanes_flows as flows
from . import lanes_owners as owners
from . import lanes_rules as rules
from .actions import Scenario
from .figures import CENT, cents
from .lanes_basis import CAVEAT, OWNER_CAVEAT, POOLED, Basis, Sizes, sizes_now
from .lanes_cells import QUANTUM, RATIOS, SPLIT, add, part, quotient, text
from .lanes_contract import SCHEMA_VERSION, reported
from .lanes_facts import (
    Period,
    by_lane,
    facts,
    group,
    modes,
    owner_of,
    periods,
    segment_of,
    standing,
)
from .lanes_flows import Calendar, Flow, Leaf
from .lanes_rules import COUNT
from .plan import REST_OF_FY, segment_words
from .records import Check
from .report import Prepared

ZERO = Decimal(0)
TOLERANCE = Decimal("0.000001")
DATED_BENCHMARK = (
    "The win-rate column is a dated benchmark, not a multiplier for the same period's created "
    "deals: it is the rate of the creation cohort old enough to have had its whole year, "
    "measured at the period's end (or the as-of date)."
)
POOLED_MODEL = (
    "Segment forecasts share one pooled model out; no model is fitted to a slice, so the "
    "company back-test's credibility does not transfer to a segment. A behind cell is a "
    "planning discrepancy, not proof of a cause."
)
ACTIONS_CAVEAT = (
    "Where the plan carries a win-rate action, the forecast win rate of the lane it touches is "
    "the resulting rate: the pooled rate plus the change the action makes, weighted by the deals "
    "that lane is expected to create in the period. It is an entered change to a pooled rate, "
    "not a rate fitted to the slice; creation, goals and recorded actuals do not move."
)
CAVEATS = (CAVEAT, DATED_BENCHMARK, POOLED_MODEL)


# ---------------------------------------------------------------- what is expected


def _series(state: Prepared, basis: Basis, cal: Calendar, hires, inflows, segments):
    """Deals created on each day to the year's end, by segment: organic creation and programs."""
    g = state.ground
    share = {s.key: s.creation_share for s in basis.segments}
    horizon = (cal.year.end - g.as_of).days
    return driver_actions.creation_series(g, share, hires, inflows, segments, horizon)


def _remainder(
    state, basis, cal, hires, inflows, segments, sizes, scenario, effect=None
):
    """The expected wins and created deals after the as-of date, by lane, with bookings tied to
    the cent to what the report shows for each quarter. The plan's win-rate actions (``effect``)
    add their wins to the no-action plan's, which stay priced as they were."""
    g = state.ground
    model = g.model
    series = _series(state, basis, cal, hires, inflows, segments)
    leaves = flows.existing_flows(model, g.pop.deals, g.as_of, cal)
    stray = {k[0] for k in leaves} - set(segments)
    if stray:  # a contribution with no lane would silently leave the company row short
        raise ValueError(f"expected wins belong to no lane: {sorted(stray)}")
    new_wins, new_created = flows.new_flows(model, series, g.as_of, cal)
    priced = flows.price(new_wins, sizes, model.new_pipeline.mean_won_arr)
    lift = None
    if effect is not None:
        lift = effect.lift
        for k, f in driver_actions.action_flows(g, effect, cal).items():
            priced[k] = priced.get(k, flows.ZERO_FLOW) + f
    for k, f in priced.items():
        leaves[k] = leaves.get(k, flows.ZERO_FLOW) + f
    forecast = scenario.forecast(tuple(hires), tuple(inflows), lift)
    shown = [
        sum(
            (
                cents(forecast.window_total(w.label))
                for w in g.windows
                if q.contains(w.end)
            ),
            ZERO,
        )
        for q in cal.quarters
    ]
    tied: dict[Leaf, Flow] = {}
    for q, total in enumerate(shown):
        mine = [k for k in leaves if k[1] == q]
        for k, b in zip(
            mine, flows.apportion(total, [leaves[k].bookings for k in mine])
        ):
            tied[k] = Flow(
                leaves[k].wins.quantize(COUNT), b, leaves[k].days.quantize(CENT)
            )
    made: dict[tuple[str, int], tuple[Decimal, Decimal]] = {}
    for j in range(1, 5):
        mine = [s for s in segments if (s, j) in new_created]
        total = sum((new_created[(s, j)] for s in mine), ZERO)
        pieces = flows.apportion(
            (total * model.new_pipeline.mean_created_arr).quantize(CENT),
            [new_created[(s, j)] * sizes[s].created for s in mine],
        )
        for s, arr in zip(mine, pieces):
            made[(s, j)] = (new_created[(s, j)].quantize(COUNT), arr)
    in_year = [
        w.label for w in g.windows if any(q.contains(w.end) for q in cal.quarters)
    ]
    modeled = sum((forecast.window_total(m) for m in in_year), ZERO)
    exact = sum((f.bookings for f in leaves.values()), ZERO)
    checks = [
        Check(
            "lane contributions replay the forward function",
            abs(exact - modeled) <= TOLERANCE,
            f"existing and modeled wins at their size book {exact:.2f} in the year's remaining "
            f"months; the forward function gives {modeled:.2f}",
        )
    ]
    if effect is not None:
        days = len(next(iter(series.values()), []))
        checks.append(
            Check(
                "segment creation is the creation the actions were valued over",
                all(
                    list(effect.frame.series[s][:days]) == list(series[s])
                    for s in segments
                ),
                f"{days} days of creation in each of {len(segments)} segments",
            )
        )
    creation = scenario.creation(tuple(hires))
    if creation is not None:
        days = len(next(iter(series.values()), []))
        extra = flows.inflow_series(inflows, model.new_pipeline.mean_created_arr, days)
        split = [sum((s[t] for s in series.values()), ZERO) for t in range(days)]
        whole = [c + e for c, e in zip(creation.per_day[:days], extra)]
        checks.append(
            Check(
                "segment creation adds to the roster's expected creation",
                all(abs(a - b) <= TOLERANCE for a, b in zip(split, whole)),
                f"{days} days of creation by segment sum to the capacity term's",
            )
        )
    return tied, made, checks, series, priced


# ---------------------------------------------------------------- atoms and cells


def _win_rate(g, effect, segments, seg: str, period) -> Decimal:
    """The forecast win rate of ``seg`` (the company when it is blank) in ``period``: the
    pooled rate, or with actions the rate they leave on the period's new pipeline."""
    if effect is None:
        return g.model.new_pipeline.win_rate
    mine = segments if seg == "" else (seg,)
    return driver_actions.period_rate(effect, mine, period.window, g.as_of)


def _marks(col: rules.Column, values: dict) -> dict | None:
    """The strip's marks of a rate, a duration or a size, written to two places."""
    if col.key not in RATIOS:
        return None
    placed = rules.marks(values["actual"], values["forecast"], values["goal"])
    return (
        None
        if placed is None
        else {k: text(v, rules.MARK_PLACES) for k, v in placed.items()}
    )


def _cell(col: rules.Column, atoms: dict, pooled_rate, goal_rate, range80):
    """One cell from the three modes' atoms. Everything the status needs is read back from the
    figures as written, so a reader recomputes the same status from the file."""
    places = Decimal(1).scaleb(-col.places)
    parts = split = None
    if col.key in RATIOS:
        num, den = RATIOS[col.key]
        parts = {m: part(atoms[m], num, den) for m in ("actual", "forecast", "goal")}
        values = {m: quotient(parts[m], col.places) for m in parts}
        if col.key == "win_rate":
            values["forecast"] = pooled_rate.quantize(places)
            values["goal"] = goal_rate.quantize(places)
            parts["forecast"] = parts["goal"] = None
    else:
        values = {m: atoms[m].get(col.key) for m in ("actual", "forecast", "goal")}
        values = {
            m: None if v is None else v.quantize(places) for m, v in values.items()
        }
        if col.key in SPLIT:
            split = {
                m: dict(
                    zip(
                        ("carried_in", "created_in_period"),
                        (text(atoms[m][k], QUANTUM[k]) for k in SPLIT[col.key]),
                    )
                )
                for m in ("actual", "forecast")
            }
    shown = {m: text(v, places) for m, v in values.items()}
    held = values[col.compared]
    denominator = None
    if col.minimum is not None and parts and parts[col.compared]:
        denominator = Decimal(parts[col.compared]["denominator"])
    status, why, ratio = rules.status(col, held, values["goal"], denominator)
    inside = None
    if range80 and values["goal"] is not None:
        inside = Decimal(range80[0]) <= values["goal"] <= Decimal(range80[1])
    return {
        **shown,
        "parts": parts,
        "split": split,
        "compared": col.compared,
        "ratio": None if ratio is None else str(ratio),
        "status": status,
        "none_because": why,
        "denominator": None
        if denominator is None
        else parts[col.compared]["denominator"],
        "range80": range80,
        "goal_inside_range80": inside,
        "marks": _marks(col, values),
    }


# ---------------------------------------------------------------- the document


def _merge(a: Mapping, b: Mapping) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = v if k not in out else _plus(out[k], v)
    return out


def _plus(x, y):
    return x + y if isinstance(x, Flow) else (x[0] + y[0], x[1] + y[1])


def lanes_document(
    state: Prepared,
    basis: Basis,
    report: dict,
    hires,
    inflows,
    company: str,
    scenario: str,
    digest: str,
    effect=None,
) -> dict:
    """The lanes for one scenario: ``hires`` and ``inflows`` are what its plan puts into the
    forward function, ``report`` its report (the figures the company row must equal) and
    ``effect`` the plan's win-rate actions (``driver_actions.effect_for``), None without any.
    Goals and recorded actuals are never moved by them."""
    g, cal = state.ground, Calendar(state.profile.fiscal_year)
    fy = cal.year
    segments = driver_actions.segments_of(g, [s.key for s in basis.segments], hires)
    new = g.model.new_pipeline
    pooled = Sizes(new.mean_won_arr, POOLED, new.mean_created_arr, POOLED)
    sizes = sizes_now(g, state.params.trailing_days, segments)
    plan_sizes = {s.key: s.sizes for s in basis.segments}
    scenario_model = Scenario(g)
    wins_a, created_a = facts(state, cal)
    wins_r, created_r, checks, whole, priced = _remainder(
        state, basis, cal, hires, inflows, segments, sizes, scenario_model, effect
    )
    if effect is not None:
        gained = sum(
            (f.bookings for f in driver_actions.action_flows(g, effect, cal).values()),
            ZERO,
        )
        joint = Decimal(report["driver_actions"]["joint_gain"][REST_OF_FY])
        slack = CENT * len(
            g.rest_labels
        )  # the report's months are each rounded to the cent
        checks.append(
            Check(
                "lane action bookings reproduce the report's joint gain",
                abs(gained - joint) <= slack,
                f"the lanes' actions book {gained:.2f} in the year's remaining months; the "
                f"report's joint gain is {joint:.2f}",
            )
        )
    wins_f, created_f = _merge(wins_a, wins_r), _merge(created_a, created_r)
    # the owners: the segments' expected wins and creation shared out
    lane_series = owners.series(state, basis, cal, hires, inflows, segments)
    wins_ro, created_ro = owners.remainder(
        state, cal, lane_series, priced, wins_r, created_r
    )
    owner_a = facts(state, cal, owner_of)
    owner_f = (
        _merge(owner_a[0], wins_ro),
        _merge(owner_a[1], created_ro),
    )
    record, forecast_ = (
        (by_lane(wins_a), by_lane(created_a)),
        (by_lane(wins_f), by_lane(created_f)),
    )
    o_record, o_forecast = (
        tuple(map(by_lane, owner_a)),
        tuple(map(by_lane, owner_f)),
    )
    deals_by_segment = group(g.pop.deals, segment_of)
    deals_by_owner = group(g.pop.deals, owner_of)
    entries = {(o.segment, o.id): o for o in basis.owners}
    names = {m.id: m.name for m in g.cap.members if m.name}
    names.update({d.owner_id: d.owner_name for d in g.pop.deals if d.owner_name})
    lane_keys = (
        set(deals_by_owner)
        | set(lane_series)
        | set(entries)
        | {(s, rules.UNASSIGNED) for s in segments}
    )
    by_period = reported(report)
    opening = {s.key: s.opening for s in basis.segments}

    def goal_atoms(period: Period, seg: str) -> dict:
        mine = [basis.goals.get((fy.quarter_keys[q], seg)) for q in period.quarters]
        mine = [x for x in mine if x is not None]
        total = lambda name: sum((getattr(x, name) for x in mine), ZERO)
        return {
            "created": total("created"),
            "created_arr": total("created_arr"),
            "won": total("won"),
            "bookings": total("bookings"),
            "days": total("days"),
            "open": Decimal(opening.get(seg, 0))
            if period.window.start == cal.start
            else None,
        }

    grid = {}
    for period in periods(cal):
        by_seg = {
            seg: modes(
                state,
                period,
                deals_by_segment.get(seg, ()),
                seg,
                record,
                forecast_,
                goal_atoms(period, seg),
            )
            for seg in segments
        }
        by_seg[""] = {
            m: add(by_seg[s][m] for s in segments)
            for m in ("actual", "forecast", "goal")
        }
        by_owner = {
            lane: modes(
                state,
                period,
                deals_by_owner.get(lane, ()),
                lane,
                o_record,
                o_forecast,
                owners.goal_atoms(
                    basis, entries, cal.start, period, fy.quarter_keys, *lane
                ),
            )
            for lane in lane_keys
        }
        grid[period.key] = (by_seg, by_owner)
    shown = owners.ordered(
        owners.present({k: v[1] for k, v in grid.items()}),
        grid[fy.label][1],
        segments,
        names,
    )
    out_periods = []
    for period in periods(cal):
        by_seg, by_owner = grid[period.key]
        expected, range80 = by_period[period.key if period.kind == "quarter" else ""]
        stand = standing(period.window, g.as_of)
        rows = []
        for rank, seg in enumerate(("", *segments)):
            total = seg == ""
            marker = range80 if total and stand != "closed" else None
            cells = {
                c.key: _cell(
                    c,
                    by_seg[seg],
                    _win_rate(g, effect, segments, seg, period),
                    basis.win_rate,
                    marker if c.key == "bookings" else None,
                )
                for c in rules.COLUMNS
            }
            rows.append(
                {
                    "path": ["total"] if total else ["segment", seg],
                    "label": "Company total" if total else segment_words(seg),
                    "parent": None if total else ["total"],
                    "kind": "company" if total else "segment",
                    "rank": rank or 1,
                    "allocation": "the sum of its segments"
                    if total
                    else _allocation(seg, basis),
                    "sizes": None
                    if total
                    else {
                        "plan_start": _sizes(plan_sizes.get(seg, pooled)),
                        "forecast": _sizes(sizes[seg]),
                    },
                    "cells": cells,
                }
            )
            for rank_, lane in enumerate((x for x in shown if x[0] == seg), 1):
                name = names.get(lane[1], lane[1])
                rows.append(
                    owners.row(
                        lane,
                        rank_,
                        by_owner[lane],
                        name,
                        owners.allocation(lane, entries.get(lane), name),
                    )
                )
        out_periods.append(
            {
                "key": period.key,
                "kind": period.kind,
                "standing": stand,
                "start": str(period.window.start + timedelta(days=1)),
                "end": str(period.window.end),
                "reported_bookings": expected,
                "rows": rows,
            }
        )
    checks += _ties(state, out_periods)
    checks.append(owners.series_check(lane_series, whole))
    return {
        "schema_version": SCHEMA_VERSION,
        "company": company,
        "scenario": scenario,
        "as_of": str(g.as_of),
        "fiscal_year": fy.label,
        "plan_basis": {
            "label": basis.label,
            "cutoff": str(basis.cutoff),
            "digest": digest,
            "file": "lanes-basis.json",
        },
        "columns": [
            {
                "key": c.key,
                "title": c.title,
                "unit": c.unit,
                "goal_label": c.goal_label,
                "places": c.places,
                "compared": c.compared,
                "reversed": c.reversed,
                "minimum": c.minimum,
                "definition": c.definition,
            }
            for c in rules.COLUMNS
        ],
        "reasons": rules.REASONS,
        "caveats": [*CAVEATS, *([ACTIONS_CAVEAT] if effect else []), OWNER_CAVEAT],
        "periods": out_periods,
        "checks": [
            {"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks
        ],
    }


def _allocation(seg: str, basis: Basis) -> str:
    mine = next((s for s in basis.segments if s.key == seg), None)
    if mine is None:
        return "no goal: the segment has no bookings in the year before the plan start"
    return f"{mine.share:.1%} of the trailing year's bookings at the plan start"


def _sizes(s: Sizes) -> dict:
    return {
        "won": text(s.won, CENT),
        "won_basis": s.won_basis,
        "created": text(s.created, CENT),
        "created_basis": s.created_basis,
    }


def _ties(state: Prepared, periods_out: list[dict]) -> list[Check]:
    """The year's actuals against the reconciliation, and every quarter's company bookings
    against the report's own expected figure."""
    year = periods_out[0]["rows"][0]["cells"]
    flow = state.rec.flow
    facts_ = {
        "created deals": (year["created"]["actual"], flow.created.count),
        "won deals": (year["won"]["actual"], flow.won.count),
        "open at the start": (year["open"]["actual"], flow.open_at_start.count),
        "bookings": (year["bookings"]["actual"], state.rec.bookings_fytd),
    }
    drift = [k for k, (mine, theirs) in facts_.items() if Decimal(mine) != theirs]
    paired = [
        (
            p["key"],
            p["rows"][0]["cells"]["bookings"]["forecast"],
            p["reported_bookings"],
        )
        for p in periods_out
    ]
    off = [k for k, mine, theirs in paired if mine != theirs]
    return [
        Check(
            "lane actuals tie to the reconciliation",
            not drift,
            "the year's created, won, opening and bookings match the report's flow"
            if not drift
            else "differs: " + ", ".join(drift),
        ),
        Check(
            "company bookings equal the report's expected bookings",
            not off,
            "the year and each quarter match to the cent"
            if not off
            else "differs: " + ", ".join(off),
        ),
    ]


def unavailable_document(company: str, scenario: str, reason: str) -> dict:
    """The lanes file when there is no plan basis to build them on: the reason, never a zero."""
    return {
        "schema_version": SCHEMA_VERSION,
        "company": company,
        "scenario": scenario,
        "unavailable": reason,
    }

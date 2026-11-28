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
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from . import lanes_flows as flows
from . import lanes_rules as rules
from .actions import Scenario
from .capacity import project
from .figures import CENT, cents
from .fiscal import Window
from .history import creation_amounts
from .lanes_basis import CAVEAT, POOLED, Basis, Sizes, segment_sizes
from .lanes_contract import SCHEMA_VERSION, reported
from .lanes_flows import Calendar, Flow, Leaf
from .lanes_rules import COUNT
from .plan import segment_words
from .records import Check
from .report import Prepared

ZERO = Decimal(0)
TOLERANCE = Decimal("0.000001")
ATOMS = (
    "open",
    "created",
    "created_arr",
    "won",
    "won_carried",
    "won_new",
    "bookings",
    "bookings_carried",
    "bookings_new",
    "days",
    "cohort_wins",
    "cohort_n",
)
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
CAVEATS = (CAVEAT, DATED_BENCHMARK, POOLED_MODEL)


@dataclass(frozen=True)
class Period:
    key: str
    kind: str  # year or quarter
    window: Window
    quarters: tuple[int, ...]  # the quarters whose wins and creation the period holds
    carried_through: (
        int  # a win whose deal was created in this origin or earlier is carried in
    )

    @property
    def buckets(self) -> tuple[int, ...]:
        return tuple(q + 1 for q in self.quarters)


def periods(cal: Calendar) -> tuple[Period, ...]:
    year = cal.year
    whole = Period(
        year.label, "year", Window(year.label, cal.start, year.end), (0, 1, 2, 3), 0
    )
    return (whole,) + tuple(
        Period(key, "quarter", w, (q,), q)
        for q, (key, w) in enumerate(zip(year.quarter_keys, cal.quarters))
    )


def _standing(window: Window, as_of: date) -> str:
    if window.end <= as_of:
        return "closed"
    return "not started" if window.start >= as_of else "in progress"


# ---------------------------------------------------------------- what has happened


def facts(state: Prepared, cal: Calendar):
    """Wins by (segment, quarter, origin) and created deals by (segment, quarter), as recorded
    through the as-of date; the first recorded amount is a created deal's pipeline."""
    amounts = creation_amounts(state.pop)
    wins: dict[Leaf, Flow] = {}
    created: dict[tuple[str, int], tuple[Decimal, Decimal]] = {}
    for d in state.pop.deals:
        seg = rules.segment_key(d.segment)
        if cal.start < d.created <= state.as_of:
            n, arr = created.get((seg, cal.bucket(d.created)), (ZERO, ZERO))
            created[(seg, cal.bucket(d.created))] = (
                n + 1,
                arr + (amounts[d.id] or ZERO),
            )
        if d.is_won and cal.start < d.close <= state.as_of:
            leaf = (seg, cal.bucket(d.close) - 1, cal.bucket(d.created))
            days = Decimal((d.close - d.created).days)
            wins[leaf] = wins.get(leaf, flows.ZERO_FLOW) + Flow(Decimal(1), d.arr, days)
    return wins, created


def _open_on(deals, seg: str, day: date) -> int:
    return sum(
        1
        for d in deals
        if rules.segment_key(d.segment) == seg
        and d.created <= day
        and (not d.is_closed or d.close > day)
    )


def _cohort(deals, seg: str, end: date, horizon: int) -> tuple[int, int]:
    """(won within the horizon, created) among the deals created in the year ending
    ``horizon`` days before ``end``."""
    last = end - timedelta(days=horizon)
    mine = [
        d
        for d in deals
        if rules.segment_key(d.segment) == seg
        and last - timedelta(days=horizon) < d.created <= last
    ]
    return sum(
        1 for d in mine if d.is_won and (d.close - d.created).days <= horizon
    ), len(mine)


# ---------------------------------------------------------------- what is expected


def _series(state: Prepared, basis: Basis, cal: Calendar, hires, inflows, segments):
    """Deals created on each day to the year's end, by segment: organic creation and programs."""
    g = state.ground
    horizon = (cal.year.end - g.as_of).days
    share = {s.key: s.creation_share for s in basis.segments}
    if g.cap.adopted:
        people = [*g.cap.members, *hires]
        organic = {
            seg: list(
                project(
                    g.cap.fit,
                    [m for m in people if rules.segment_key(m.segment) == seg],
                    g.as_of,
                    g.horizon_days,
                ).per_day[:horizon]
            )
            for seg in segments
        }
    else:
        rate = g.model.new_pipeline.created_per_day
        organic = {seg: [rate * share.get(seg, ZERO)] * horizon for seg in segments}
    extra = flows.inflow_series(inflows, g.model.new_pipeline.mean_created_arr, horizon)
    return flows.segment_series(organic, extra, share)


def _price(won: Mapping[Leaf, Flow], sizes, pooled_size: Decimal) -> dict[Leaf, Flow]:
    """Modeled wins priced per segment: each (quarter, origin) cell's pooled bookings shared out
    in proportion to wins times the segment's size, so the segments add to the pooled figure."""
    out = dict(won)
    cells: dict[tuple[int, int], list[Leaf]] = {}
    for leaf in won:
        cells.setdefault(leaf[1:], []).append(leaf)
    for leaves in cells.values():
        pooled = sum((won[k].wins for k in leaves), ZERO) * pooled_size
        weights = [won[k].wins * sizes[k[0]].won for k in leaves]
        for k, b in zip(leaves, _share(pooled, weights)):
            out[k] = Flow(won[k].wins, b, won[k].days)
    return out


def _share(total: Decimal, weights) -> list[Decimal]:
    """``total`` in proportion to ``weights`` exactly (no rounding), or evenly if none weigh."""
    weight = sum(weights, ZERO)
    if not weight:
        return [total / len(weights)] * len(weights)
    return [total * w / weight for w in weights]


def _remainder(state, basis, cal, hires, inflows, segments, sizes, scenario):
    """The expected wins and created deals after the as-of date, by lane, with bookings tied to
    the cent to what the report shows for each quarter."""
    g = state.ground
    model = g.model
    series = _series(state, basis, cal, hires, inflows, segments)
    new_wins, new_created = flows.new_flows(model, series, g.as_of, cal)
    priced = _price(new_wins, sizes, model.new_pipeline.mean_won_arr)
    leaves = flows.existing_flows(model, g.pop.deals, g.as_of, cal)
    for k, f in priced.items():
        leaves[k] = leaves.get(k, flows.ZERO_FLOW) + f
    forecast = scenario.forecast(tuple(hires), tuple(inflows))
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
    return tied, made, checks


# ---------------------------------------------------------------- atoms and cells

QUANTUM = {
    "open": Decimal(1),
    "cohort_wins": Decimal(1),
    "cohort_n": Decimal(1),
    "created": COUNT,
    "won": COUNT,
    "won_carried": COUNT,
    "won_new": COUNT,
    "created_arr": CENT,
    "bookings": CENT,
    "bookings_carried": CENT,
    "bookings_new": CENT,
    "days": CENT,
}
FLOW_ATOMS = tuple(k for k in ATOMS if k not in ("open", "cohort_wins", "cohort_n"))
RATIOS = {  # a ratio column: the atoms it is a quotient of
    "win_rate": ("cohort_wins", "cohort_n"),
    "avg_won_arr": ("bookings", "won"),
    "cycle": ("days", "won"),
}
SPLIT = {
    "won": ("won_carried", "won_new"),
    "bookings": ("bookings_carried", "bookings_new"),
}


def _flow_atoms(period: Period, seg: str, wins, created) -> dict[str, Decimal]:
    out = dict.fromkeys(FLOW_ATOMS, ZERO)
    for (s, q, origin), f in wins.items():
        if s == seg and q in period.quarters:
            part = "carried" if origin <= period.carried_through else "new"
            for name, value in (("won", f.wins), ("bookings", f.bookings)):
                out[name] += value
                out[f"{name}_{part}"] += value
            out["days"] += f.days
    for (s, j), (n, arr) in created.items():
        if s == seg and j in period.buckets:
            out["created"] += n
            out["created_arr"] += arr
    return out


def _add(parts) -> dict[str, Decimal | None]:
    """The sum of atom dicts; an atom that is missing everywhere stays missing."""
    parts = list(parts)
    keys = {k for p in parts for k in p}
    return {
        k: None
        if all(p.get(k) is None for p in parts)
        else sum((p[k] for p in parts if p.get(k) is not None), ZERO)
        for k in keys
    }


def _text(value: Decimal | None, quantum: Decimal) -> str | None:
    return None if value is None else str(value.quantize(quantum))


def _part(atoms: Mapping[str, Decimal | None], num: str, den: str) -> dict | None:
    n, d = atoms.get(num), atoms.get(den)
    if n is None or d is None:
        return None
    return {"numerator": _text(n, QUANTUM[num]), "denominator": _text(d, QUANTUM[den])}


def _quotient(part: dict | None, places: int) -> Decimal | None:
    if part is None or not Decimal(part["denominator"]):
        return None
    return (Decimal(part["numerator"]) / Decimal(part["denominator"])).quantize(
        Decimal(1).scaleb(-places)
    )


def _cell(col: rules.Column, atoms: dict, pooled_rate, goal_rate, range80):
    """One cell from the three modes' atoms. Everything the status needs is read back from the
    figures as written, so a reader recomputes the same status from the file."""
    places = Decimal(1).scaleb(-col.places)
    parts = split = None
    if col.key in RATIOS:
        num, den = RATIOS[col.key]
        parts = {m: _part(atoms[m], num, den) for m in ("actual", "forecast", "goal")}
        values = {m: _quotient(parts[m], col.places) for m in parts}
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
                        (_text(atoms[m][k], QUANTUM[k]) for k in SPLIT[col.key]),
                    )
                )
                for m in ("actual", "forecast")
            }
    shown = {m: _text(v, places) for m, v in values.items()}
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
) -> dict:
    """The lanes for one scenario: ``hires`` and ``inflows`` are what its plan puts into the
    forward function, ``report`` its report (the figures the company row must equal)."""
    g, cal = state.ground, Calendar(state.profile.fiscal_year)
    fy = cal.year
    people = [*g.cap.members, *hires]
    known = [s.key for s in basis.segments]
    extra = sorted(
        {rules.segment_key(d.segment) for d in g.pop.deals}
        | {rules.segment_key(m.segment) for m in people}
    )
    segments = known + [s for s in extra if s not in known]
    new = g.model.new_pipeline
    pooled = Sizes(new.mean_won_arr, POOLED, new.mean_created_arr, POOLED)
    now = segment_sizes(
        g.pop.deals,
        creation_amounts(g.pop),
        g.as_of,
        new.mean_won_arr,
        new.mean_created_arr,
        state.params.trailing_days,
    )
    sizes = {s: now.get(s, pooled) for s in segments}
    plan_sizes = {s.key: s.sizes for s in basis.segments}
    scenario_model = Scenario(g)
    wins_a, created_a = facts(state, cal)
    wins_r, created_r, checks = _remainder(
        state, basis, cal, hires, inflows, segments, sizes, scenario_model
    )
    wins_f, created_f = _merge(wins_a, wins_r), _merge(created_a, created_r)
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

    out_periods = []
    for period in periods(cal):
        begun = period.window.start <= g.as_of
        end = min(period.window.end, g.as_of)
        by_seg = {}
        for seg in segments:
            held = (
                Decimal(_open_on(g.pop.deals, seg, period.window.start))
                if begun
                else None
            )
            won, n = _cohort(g.pop.deals, seg, end, state.params.horizon_days)
            actual = {
                **_flow_atoms(period, seg, wins_a, created_a),
                "open": held,
                "cohort_wins": Decimal(won),
                "cohort_n": Decimal(n),
            }
            forecast = {**_flow_atoms(period, seg, wins_f, created_f), "open": held}
            by_seg[seg] = {
                "actual": actual,
                "forecast": forecast,
                "goal": goal_atoms(period, seg),
            }
        by_seg[""] = {
            m: _add(by_seg[s][m] for s in segments)
            for m in ("actual", "forecast", "goal")
        }
        expected, range80 = by_period[period.key if period.kind == "quarter" else ""]
        standing = _standing(period.window, g.as_of)
        rows = []
        for seg in ("", *segments):
            total = seg == ""
            marker = range80 if total and standing != "closed" else None
            cells = {
                c.key: _cell(
                    c,
                    by_seg[seg],
                    g.model.new_pipeline.win_rate,
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
        out_periods.append(
            {
                "key": period.key,
                "kind": period.kind,
                "standing": standing,
                "start": str(period.window.start + timedelta(days=1)),
                "end": str(period.window.end),
                "reported_bookings": expected,
                "rows": rows,
            }
        )
    checks += _ties(state, out_periods)
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
            }
            for c in rules.COLUMNS
        ],
        "reasons": rules.REASONS,
        "caveats": list(CAVEATS),
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
        "won": _text(s.won, CENT),
        "won_basis": s.won_basis,
        "created": _text(s.created, CENT),
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

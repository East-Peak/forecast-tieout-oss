"""Reconciliation: the population, its exclusions and the tie to the source file."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from .fiscal import month_windows
from .load import LoadedCompany, parse_date, parse_flag, parse_money
from .records import LOST, WON, Check, Dataset, Deal, Exclusion, Profile

NEW_BUSINESS = "new_business"


@dataclass(frozen=True)
class Tally:
    count: int
    arr: Decimal


@dataclass(frozen=True)
class Flow:
    """New-business pipeline from the fiscal-year start to the as-of date, at
    each deal's current amount."""

    open_at_start: Tally
    created: Tally
    won: Tally
    lost: Tally
    open_at_end: Tally


@dataclass(frozen=True)
class Motion:
    rows: int
    arr: Decimal
    won_fytd_arr: Decimal


@dataclass(frozen=True)
class Reconciliation:
    population: Dataset
    exclusions: tuple[Exclusion, ...]
    source_rows: int
    source_arr_total: Decimal
    excluded_motions: dict[str, Motion]
    bookings_by_month: dict[str, Decimal]
    bookings_fytd: Decimal
    flow: Flow
    checks: tuple[Check, ...]


def reconcile(
    company_dir: Path, loaded: LoadedCompany, profile: Profile, as_of: date
) -> Reconciliation:
    fy = profile.fiscal_year
    if not fy.contains(as_of):
        raise ValueError(
            f"as-of {as_of} is outside the fiscal year in targets.yaml ({fy.start} to {fy.end})"
        )

    def fytd(d: date | None) -> bool:
        return d is not None and fy.start <= d <= as_of

    kept: list[Deal] = []
    exclusions = list(loaded.exclusions)
    motions: dict[str, list[Deal]] = {}
    for d in loaded.dataset.deals:
        reason = None
        if d.type != NEW_BUSINESS:
            motions.setdefault(d.type or "(blank)", []).append(d)
            reason = f"excluded motion: {d.type or '(blank)'}"
        elif d.created > as_of:
            reason = "created after the as-of date"
        if reason:
            exclusions.append(Exclusion(d.row, d.id, reason, d.arr))
        else:
            kept.append(d)
    exclusions.sort(key=lambda e: e.row)

    ids = {d.id for d in kept}
    later = [d.close for d in kept if d.is_closed and d.close > as_of]
    later += [
        t.on for t in loaded.dataset.transitions if t.deal_id in ids and t.on > as_of
    ]
    later += [
        o.on
        for o in loaded.dataset.observations or ()
        if o.deal_id in ids and o.on > as_of
    ]
    if later:
        raise ValueError(
            f"the files have close dates, stage history or observations dated up to {max(later)}, "
            f"after the as-of date {as_of}; the as-of date must be the export date or later "
            "(past dates are rebuilt only inside the back-test)"
        )
    population = Dataset(
        tuple(kept),
        tuple(t for t in loaded.dataset.transitions if t.deal_id in ids),
        None
        if loaded.dataset.observations is None
        else tuple(o for o in loaded.dataset.observations if o.deal_id in ids),
    )

    months = month_windows(fy.start - timedelta(days=1), as_of)
    by_month = {w.label: Decimal(0) for w in months}
    for d in kept:
        if d.is_won and fytd(d.close):
            by_month[f"{d.close.year:04d}-{d.close.month:02d}"] += d.arr
    fytd_total = sum(by_month.values(), Decimal(0))

    flow = Flow(
        open_at_start=_tally(
            d
            for d in kept
            if d.created < fy.start and (not d.is_closed or d.close >= fy.start)
        ),
        created=_tally(d for d in kept if fytd(d.created)),
        won=_tally(d for d in kept if d.stage == WON and fytd(d.close)),
        lost=_tally(d for d in kept if d.stage == LOST and fytd(d.close)),
        open_at_end=_tally(d for d in kept if not d.is_closed),
    )

    checks = (
        _rows_partition(loaded, kept, exclusions),
        _arr_partition(loaded, kept, exclusions),
        _bookings_tie(company_dir, exclusions, fytd_total, fytd),
        _flow_check(flow),
    )
    return Reconciliation(
        population=population,
        exclusions=tuple(exclusions),
        source_rows=loaded.source_rows,
        source_arr_total=loaded.source_arr_total,
        excluded_motions={
            k: Motion(
                len(v),
                _sum(d.arr for d in v),
                _sum(d.arr for d in v if d.is_won and fytd(d.close)),
            )
            for k, v in sorted(motions.items())
        },
        bookings_by_month=by_month,
        bookings_fytd=fytd_total,
        flow=flow,
        checks=checks,
    )


def _sum(values) -> Decimal:
    return sum(values, Decimal(0))


def _tally(deals) -> Tally:
    deals = list(deals)
    return Tally(len(deals), _sum(d.arr for d in deals))


def _rows_partition(loaded, kept, exclusions) -> Check:
    total = len(kept) + len(exclusions)
    return Check(
        "rows partition",
        total == loaded.source_rows,
        f"{len(kept)} included + {len(exclusions)} excluded = {total} of {loaded.source_rows} source rows",
    )


def _arr_partition(loaded, kept, exclusions) -> Check:
    total = _sum(d.arr for d in kept) + _sum(
        e.arr for e in exclusions if e.arr is not None
    )
    return Check(
        "arr partition",
        total == loaded.source_arr_total,
        f"included + excluded arr = {total} against source total {loaded.source_arr_total}"
        f" ({loaded.unparseable_arr_rows} rows had no readable arr)",
    )


def _bookings_tie(company_dir, exclusions, fytd_total, fytd) -> Check:
    """Recompute FYTD new-business bookings straight from the raw file, without
    the loader, and account for every excluded row the raw filter counts."""
    raw_total = Decimal(0)
    counted_rows = set()
    with (Path(company_dir) / "deals.csv").open(newline="") as fh:
        for row_number, raw in enumerate(csv.DictReader(fh), start=2):
            arr = parse_money(raw.get("arr", ""))
            try:
                close = parse_date(raw["close_date"]) if raw.get("close_date") else None
            except ValueError:
                close = None
            if (
                (raw.get("type") or "").strip() == NEW_BUSINESS
                and parse_flag(raw.get("is_won", ""))
                and arr is not None
                and fytd(close)
            ):
                raw_total += arr
                counted_rows.add(row_number)
    excluded_part = _sum(e.arr for e in exclusions if e.row in counted_rows)
    return Check(
        "bookings tie to source",
        raw_total == fytd_total + excluded_part,
        f"source file new-business won FYTD {raw_total} = included {fytd_total}"
        f" + excluded rows {excluded_part}",
    )


def _flow_check(flow: Flow) -> Check:
    ok = all(
        getattr(flow.open_at_start, f) + getattr(flow.created, f)
        == getattr(flow.won, f) + getattr(flow.lost, f) + getattr(flow.open_at_end, f)
        for f in ("count", "arr")
    )
    return Check(
        "pipeline flow",
        ok,
        f"open at FY start {flow.open_at_start.arr} + created {flow.created.arr}"
        f" = won {flow.won.arr} + lost {flow.lost.arr} + open now {flow.open_at_end.arr}",
    )

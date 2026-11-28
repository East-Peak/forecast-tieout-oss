"""The lanes files' contract: a versioned JSON Schema for each, and the rules a schema cannot say.

Two files are written for a company: the frozen plan basis (``lanes-basis.json``), which no
scenario can change, and one lanes file per scenario. The schema fixes every shape. The rules
recompute what a reader would otherwise have to take on trust: every parent is the sum of its
children, a year is the sum of its quarters, a rate is its numerator over its denominator, a
status is what the written figures give, every goal is the basis's, and the company's bookings
are the report's, to the cent.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from jsonschema import Draft202012Validator

from . import lanes_rules as rules
from .contract import (
    BOOL,
    DATE,
    DECIMAL,
    DECIMAL_OR_NULL,
    INT,
    MONEY,
    TEXT,
    arr,
    const,
    enum,
    maybe,
    obj,
    one_of,
    ref,
)
from .contract import (
    DEFS as REPORT_DEFS,
)

SCHEMA_VERSION = "1.0.0"
DEFS = {
    k: REPORT_DEFS[k]
    for k in ("Text", "Money", "Decimal", "Date", "Quarter", "MoneyRange", "Check")
}
CHECK = ref("Check")
MONEY_RANGE = ref("MoneyRange")
PART = obj({"numerator": DECIMAL, "denominator": DECIMAL})
SPLIT = obj({"carried_in": DECIMAL, "created_in_period": DECIMAL})
SIZES = obj({"won": MONEY, "won_basis": TEXT, "created": MONEY, "created_basis": TEXT})
CELL = obj(
    {
        "actual": DECIMAL_OR_NULL,
        "forecast": DECIMAL_OR_NULL,
        "goal": DECIMAL_OR_NULL,
        "parts": maybe(
            obj({"actual": maybe(PART), "forecast": maybe(PART), "goal": maybe(PART)})
        ),
        "split": maybe(obj({"actual": SPLIT, "forecast": SPLIT})),
        "compared": enum("actual", "forecast"),
        "ratio": DECIMAL_OR_NULL,
        "status": enum(rules.BEHIND, rules.ON_TRACK, rules.NONE),
        "none_because": maybe(enum(*rules.REASONS)),
        "denominator": DECIMAL_OR_NULL,
        "range80": maybe(MONEY_RANGE),
        "goal_inside_range80": maybe(BOOL),
    }
)
ROW = obj(
    {
        "path": arr(TEXT, minItems=1, maxItems=2),
        "label": TEXT,
        "parent": maybe(arr(TEXT, minItems=1, maxItems=1)),
        "allocation": TEXT,
        "sizes": maybe(obj({"plan_start": SIZES, "forecast": SIZES})),
        "cells": obj({c.key: CELL for c in rules.COLUMNS}),
    }
)
PERIOD = obj(
    {
        "key": TEXT,
        "kind": enum("year", "quarter"),
        "standing": enum("closed", "in progress", "not started"),
        "start": DATE,
        "end": DATE,
        "reported_bookings": MONEY,
        "rows": arr(ROW, minItems=1),
    }
)
COLUMN = obj(
    {
        "key": enum(*(c.key for c in rules.COLUMNS)),
        "title": TEXT,
        "unit": enum("deals", "ARR", "rate", "days"),
        "goal_label": TEXT,
        "places": INT,
        "compared": enum("actual", "forecast"),
        "reversed": BOOL,
        "minimum": maybe(INT),
    }
)
HEADER = {
    "schema_version": const(SCHEMA_VERSION),
    "company": TEXT,
    "scenario": TEXT,
}
AVAILABLE = obj(
    {
        **HEADER,
        "as_of": DATE,
        "fiscal_year": TEXT,
        "plan_basis": obj(
            {"label": TEXT, "cutoff": DATE, "digest": TEXT, "file": TEXT}
        ),
        "columns": arr(COLUMN, minItems=8, maxItems=8),
        "reasons": obj({k: TEXT for k in rules.REASONS}),
        "caveats": arr(TEXT, minItems=1),
        "periods": arr(PERIOD, minItems=5, maxItems=5),
        "checks": arr(CHECK, minItems=1),
    }
)
UNAVAILABLE = obj({**HEADER, "unavailable": TEXT})
GOAL = obj(
    {
        "bookings": MONEY,
        "won": DECIMAL,
        "created": DECIMAL,
        "created_arr": MONEY,
        "days": DECIMAL,
    }
)
BASIS = obj(
    {
        "schema_version": const(SCHEMA_VERSION),
        "company": TEXT,
        "label": TEXT,
        "cutoff": DATE,
        "capacity_at_plan_start": obj({"decision": TEXT, "reason": TEXT}),
        "fit": obj(
            {
                "win_rate": DECIMAL,
                "cohort_size": INT,
                "mean_won_arr": MONEY,
                "mean_created_arr": MONEY,
                "created_per_day": DECIMAL,
            }
        ),
        "opening": INT,
        "segments": arr(
            obj(
                {
                    "key": TEXT,
                    "trailing_bookings": MONEY,
                    "share": DECIMAL,
                    "creation_share": DECIMAL,
                    "opening": INT,
                    "won_size": MONEY,
                    "won_size_basis": TEXT,
                    "created_size": MONEY,
                    "created_size_basis": TEXT,
                }
            ),
            minItems=1,
        ),
        "schedule": arr(
            obj(
                {
                    "quarter": ref("Quarter"),
                    "target": MONEY,
                    "outcome": TEXT,
                    "created": DECIMAL,
                    "created_arr": MONEY,
                    "wins": DECIMAL,
                    "bookings": MONEY,
                    "days": DECIMAL,
                }
            ),
            minItems=4,
            maxItems=4,
        ),
        "goals": {
            "type": "object",
            "additionalProperties": {"type": "object", "additionalProperties": GOAL},
        },
        "caveat": TEXT,
        "checks": arr(CHECK, minItems=1),
    }
)


def _schema(title: str, name: str, body: dict) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://forecast-tieout.example/schema/{name}-{SCHEMA_VERSION}.json",
        "title": title,
        "description": f"{name}.json written by the core's generator: the swimlane grid's figures.",
        **body,
        "$defs": DEFS,
    }


def schema() -> dict:
    return _schema("TieoutLanes", "lanes", one_of(AVAILABLE, UNAVAILABLE))


def basis_schema() -> dict:
    return _schema("TieoutLanesBasis", "lanes-basis", BASIS)


def schema_text(schema_: dict) -> str:
    return json.dumps(schema_, indent=2, sort_keys=True) + "\n"


def digest(basis_doc: dict) -> str:
    """The identity of a basis file as written: lanes name the basis they were read from."""
    text = json.dumps(basis_doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return hashlib.sha256(text.encode()).hexdigest()


def _errors(schema_: dict, doc) -> list[str]:
    return [
        f"{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}"
        for e in Draft202012Validator(schema_).iter_errors(doc)
    ]


def reported(report: dict) -> dict[str, tuple[str, list | None]]:
    """The report's own expected bookings and 80% range for the year ("") and each quarter."""
    plan = report.get("plan")
    gap = report["gap"]
    year = (
        plan["ranges"]["fiscal_year_expected_range80"]
        if plan
        else gap["fiscal_year"]["expected_range80"]
    )
    expected = plan["expected_fiscal_year"] if plan else gap["fiscal_year"]["expected"]
    quarters = plan["with_plan_quarters"] if plan else gap["quarters"]
    out = {"": (expected, year)}
    out.update({q["quarter"]: (q["expected"], q["expected_range80"]) for q in quarters})
    return out


# ---------------------------------------------------------------- the rules

ADDITIVE = ("created", "created_arr", "won", "bookings")
MODES = ("actual", "forecast", "goal")
FLOWS = {"avg_won_arr", "cycle"}  # ratio columns whose parts add across quarters


def _d(x: str | None) -> Decimal | None:
    return None if x is None else Decimal(x)


def _quotient(part: dict | None, places: int) -> Decimal | None:
    if part is None or not Decimal(part["denominator"]):
        return None
    return (Decimal(part["numerator"]) / Decimal(part["denominator"])).quantize(
        Decimal(1).scaleb(-places)
    )


def validate_basis(doc: dict) -> list[str]:
    """Every problem with a basis file: the schema's, then the rules."""
    found = _errors(basis_schema(), doc)
    if found:
        return found
    for q in doc["schedule"]:
        mine = [g["bookings"] for g in doc["goals"][q["quarter"]].values()]
        if sum(Decimal(b) for b in mine) != Decimal(q["target"]):
            found.append(
                f"basis: {q['quarter']}'s segment goals do not share its target exactly"
            )
    if abs(sum(Decimal(s["share"]) for s in doc["segments"]) - 1) > Decimal("0.00001"):
        found.append("basis: the segment shares do not add to one")
    found += [
        f"basis check failed: {c['name']}" for c in doc["checks"] if not c["passed"]
    ]
    return found


def validate(doc: dict, basis: dict | None, report: dict) -> list[str]:
    """Every problem with a lanes file: the schema's, then the rules. ``basis`` is the company's
    basis file as parsed and ``report`` the scenario's report."""
    found = _errors(schema(), doc)
    if found or "unavailable" in doc:
        return found
    problems: list[str] = []

    def rule(ok: bool, message: str) -> None:
        if not ok:
            problems.append(message)

    _shape(doc, rule)
    _cells(doc, rule)
    _sums(doc, rule)
    _against_basis(doc, basis, rule)
    _against_report(doc, report, rule)
    problems += [f"check failed: {c['name']}" for c in doc["checks"] if not c["passed"]]
    return problems


def _shape(doc, rule) -> None:
    first = [r["path"] for r in doc["periods"][0]["rows"]]
    rule(first[0] == ["total"], "the first row of every period is the company total")
    rule(len(set(map(tuple, first))) == len(first), "row paths must be unique")
    for p in doc["periods"]:
        paths = [r["path"] for r in p["rows"]]
        rule(
            paths == first,
            f"{p['key']}: every period holds the same rows in the same order",
        )
        for r in p["rows"][1:]:
            rule(
                r["parent"] == ["total"],
                f"{p['key']}: {r['path']} must sit under the total",
            )


def _cells(doc, rule) -> None:
    """Each cell on its own: a split adds up, a ratio is its parts, a status is the figures'."""
    for p in doc["periods"]:
        for r in p["rows"]:
            for col in rules.COLUMNS:
                c, where = r["cells"][col.key], f"{p['key']} {r['path']} {col.key}"
                if c["split"]:
                    for m in ("actual", "forecast"):
                        s = c["split"][m]
                        rule(
                            Decimal(s["carried_in"]) + Decimal(s["created_in_period"])
                            == _d(c[m]),
                            f"{where}: the {m} split does not add to the figure",
                        )
                if col.key in ("avg_won_arr", "cycle"):
                    for m in MODES:
                        rule(
                            _quotient(c["parts"][m], col.places) == _d(c[m]),
                            f"{where}: the {m} figure is not its numerator over its denominator",
                        )
                if col.key == "win_rate":
                    rule(
                        _quotient(c["parts"]["actual"], col.places) == _d(c["actual"]),
                        f"{where}: the actual rate is not its numerator over its denominator",
                    )
                held = c["parts"][c["compared"]] if c["parts"] else None
                den = (
                    None
                    if held is None or col.minimum is None
                    else Decimal(held["denominator"])
                )
                rule(
                    _d(c["denominator"]) == den,
                    f"{where}: the denominator is not the compared figure's",
                )
                want = rules.status(col, _d(c[c["compared"]]), _d(c["goal"]), den)
                got = (c["status"], c["none_because"], _d(c["ratio"]))
                rule(
                    got == want,
                    f"{where}: the status {got} is not what the figures give, {want}",
                )


def _sums(doc, rule) -> None:
    year, quarters = doc["periods"][0], doc["periods"][1:]
    for p in doc["periods"]:
        total, kids = p["rows"][0], p["rows"][1:]
        for col in ("open", *ADDITIVE, *rules.RATIO_COLUMNS):
            for m in MODES:
                _add_up(
                    rule,
                    f"{p['key']} {col} {m}: the company",
                    total["cells"][col],
                    [k["cells"][col] for k in kids],
                    m,
                    True,
                )
    for r in range(len(year["rows"])):
        mine = year["rows"][r]["cells"]
        for col in ADDITIVE:
            for m in MODES:
                _add_up(
                    rule,
                    f"{year['key']} {col} {m} {year['rows'][r]['path']}: the year over its quarters",
                    mine[col],
                    [q["rows"][r]["cells"][col] for q in quarters],
                    m,
                )
        for col in FLOWS:
            for m in MODES:
                _add_up(
                    rule,
                    f"{year['key']} {col} {m} {year['rows'][r]['path']}: the year over its quarters",
                    mine[col],
                    [q["rows"][r]["cells"][col] for q in quarters],
                    m,
                )


def _add_up(
    rule, where: str, parent: dict, children: list[dict], mode: str, split: bool = False
) -> None:
    """``parent`` is the sum of ``children`` in one mode: its figure where the column adds, and
    its numerator and denominator where it is a ratio, and each part of a split."""
    if parent["parts"]:
        part = parent["parts"][mode]
        if part is not None:
            for key in ("numerator", "denominator"):
                rule(
                    Decimal(part[key])
                    == sum(Decimal(c["parts"][mode][key]) for c in children),
                    f"{where} {key} is not the sum of its parts",
                )
        return
    values = [_d(c[mode]) for c in children]
    if parent[mode] is None:
        rule(
            all(v is None for v in values), f"{where} is missing but its parts are not"
        )
        return
    rule(
        _d(parent[mode]) == sum(v for v in values if v is not None),
        f"{where} is not the sum of its parts",
    )
    if split and mode != "goal" and parent["split"]:
        for k in ("carried_in", "created_in_period"):
            rule(
                Decimal(parent["split"][mode][k])
                == sum(Decimal(c["split"][mode][k]) for c in children),
                f"{where} split {k} is not the sum of its parts",
            )


def _against_basis(doc, basis, rule) -> None:
    rule(
        doc["plan_basis"]["digest"] == digest(basis),
        "the lanes' digest is not the basis file's",
    )
    rule(
        doc["plan_basis"]["label"] == basis["label"]
        and doc["plan_basis"]["cutoff"] == basis["cutoff"],
        "the lanes' plan basis is not the basis file's label and date",
    )
    goals = basis["goals"]
    segments = {s["key"]: s for s in basis["segments"]}
    for p in doc["periods"][1:]:
        for r in p["rows"][1:]:
            seg = r["path"][1]
            mine = goals[p["key"]].get(seg)
            want = (
                {
                    "created": mine["created"],
                    "created_arr": mine["created_arr"],
                    "won": mine["won"],
                    "bookings": mine["bookings"],
                }
                if mine
                else dict.fromkeys(ADDITIVE, "0")
            )
            for col, value in want.items():
                rule(
                    _d(r["cells"][col]["goal"]) == Decimal(value),
                    f"{p['key']} {r['path']} {col}: the goal is not the basis's",
                )
            days = r["cells"]["cycle"]["parts"]["goal"]["numerator"]
            rule(
                Decimal(days) == (Decimal(mine["days"]) if mine else 0),
                f"{p['key']} {r['path']} cycle: the goal is not the basis's",
            )
    for p in doc["periods"]:
        for r in p["rows"][1:]:
            opening = segments.get(r["path"][1], {}).get("opening", 0)
            want = (
                Decimal(opening)
                if p["key"] in (doc["fiscal_year"], f"Q1{doc['fiscal_year']}")
                else None
            )
            rule(
                _d(r["cells"]["open"]["goal"]) == want,
                f"{p['key']} {r['path']} open: the goal is not the basis's",
            )
        for r in p["rows"]:
            rule(
                _d(r["cells"]["win_rate"]["goal"]) == Decimal(basis["fit"]["win_rate"]),
                f"{p['key']} {r['path']} win_rate: the goal is not the basis's",
            )


def _against_report(doc, report, rule) -> None:
    expected = reported(report)
    gap = report["gap"]
    targets = {q["quarter"]: q["target"] for q in gap["quarters"]}
    targets[doc["fiscal_year"]] = gap["fiscal_year"]["target"]
    for p in doc["periods"]:
        key = "" if p["kind"] == "year" else p["key"]
        total = p["rows"][0]["cells"]["bookings"]
        rule(
            total["forecast"] == expected[key][0] == p["reported_bookings"],
            f"{p['key']}: the company's bookings forecast is not the report's",
        )
        rule(
            _d(total["goal"]) == Decimal(targets[p["key"]]),
            f"{p['key']}: the company's bookings goal is not the report's target",
        )
        want = expected[key][1] if p["standing"] != "closed" else None
        rule(total["range80"] == want, f"{p['key']}: the range is not the report's")
        for r in p["rows"][1:]:
            rule(
                r["cells"]["bookings"]["range80"] is None,
                f"{p['key']} {r['path']}: only the company row carries the range",
            )
    rule(
        _d(doc["periods"][0]["rows"][0]["cells"]["bookings"]["actual"])
        == Decimal(gap["fiscal_year"]["actual_to_date"]),
        "the year's actual bookings are not the report's",
    )

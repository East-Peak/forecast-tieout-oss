"""The worksheet section's schema and the rules a schema cannot say.

A figure that exists elsewhere in the report is carried as ``{value, source}`` where ``source`` is
a JSON pointer into the report; the rules here check that the value is exactly what the pointer
finds, so the section can never hold a second, different number for the same thing. The
historical settings are recomputed from the observations printed beside them, the bridge is added
up, and the sentences are checked for digits (a sentence may only say what its fields carry).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal

from . import worksheet as ws
from . import worksheet_drivers as wd
from . import worksheet_rules as rules
from .contract import (
    BOOL,
    CHECK,
    DATE,
    DECIMAL,
    DECIMAL_OR_NULL,
    INT,
    MONEY,
    MONEY_OR_NULL,
    OUTCOME_OF_LEVER,
    PER_WINDOW,
    TEXT,
    arr,
    const,
    enum,
    maybe,
    obj,
    one_of,
    pair,
    ref,
)
from .plan import NEXT_12, REST_OF_FY

SENTENCE_KEYS = frozenset(
    {
        "outcome_label", "reason_label", "history_label", "limitation", "applies_to", "gate",
        "rule", "definition", "expectation_note", "sensitivity_note", "history_note",
        "historical_unavailable_because", "not_eligible_because", "no_plan_note",
        "closes_alone_label", "measured_around", "order", "measure", "unit_label",
    }
)  # fmt: skip
CENT = Decimal(
    "0.01"
)  # a target in fractions of a cent can differ from a displayed figure by one
STEP_KINDS = ("as_signed", "hires", "program", "working_plan", "remaining_gap")


def _ref_of(value: dict) -> dict:
    return obj({"value": value, "source": TEXT})


def _setting() -> dict:
    return obj({"setting": DECIMAL, "change": PER_WINDOW})


def _driver() -> dict:
    quarter = obj(
        {
            "quarter": ref("Quarter"),
            "start": DATE,
            "end": DATE,
            "value": DECIMAL_OR_NULL,
            "created": INT,
            "wins": INT,
            "exposure": DECIMAL_OR_NULL,
            "mature": BOOL,
            "eligible": BOOL,
            "not_eligible_because": maybe(TEXT),
        }
    )
    needed = obj(
        {
            "outcome": enum(wd.SOLVES, wd.CANNOT, wd.COVERED),
            "outcome_label": TEXT,
            "reason": maybe(enum(wd.BOUNDED_AT_ONE, wd.NO_EFFECT, wd.ZERO_DAYS_SHORT)),
            "reason_label": maybe(TEXT),
            "value": DECIMAL_OR_NULL,
            "achieved_fiscal_year_bookings": MONEY,
            "target": MONEY,
            "overshoot": MONEY_OR_NULL,
            "stepped": BOOL,
            "scale": maybe({"type": "string", "pattern": r"^\d+/\d+$"}),
            "inside_observed_range": maybe(BOOL),
            "history_label": maybe(TEXT),
        }
    )
    return obj(
        {
            "driver": enum(*rules.DRIVERS),
            "label": TEXT,
            "applies_to": TEXT,
            "unit": TEXT,
            "unit_label": TEXT,
            "display": enum("percent", "money", "decimal"),
            "current": obj(
                {
                    "value": DECIMAL,
                    "fit_in_use": TEXT,
                    "creation_from": DATE,
                    "creation_to": DATE,
                }
            ),
            "evidence": obj(
                {
                    "gate": TEXT,
                    "required_quarters": INT,
                    "eligible_quarters": INT,
                    "gate_passed": BOOL,
                    "quarters": arr(quarter),
                }
            ),
            "historical": maybe(
                obj(
                    {
                        "low": _setting(),
                        "high": _setting(),
                        "minimum": DECIMAL,
                        "maximum": DECIMAL,
                        "rule": TEXT,
                    }
                )
            ),
            "historical_unavailable_because": maybe(TEXT),
            "needed_alone": needed,
            "limitation": maybe(TEXT),
        }
    )


def schema() -> dict:
    step = obj(
        {
            "kind": enum(*STEP_KINDS),
            "label": TEXT,
            "change": MONEY_OR_NULL,
            "from": MONEY_OR_NULL,
            "to": MONEY,
            "valued": BOOL,
            "note": maybe(TEXT),
            "source": TEXT,
        }
    )
    contribution = obj(
        {
            "label": TEXT,
            "kind": enum("hires", "program"),
            "valued": BOOL,
            REST_OF_FY: MONEY_OR_NULL,
            NEXT_12: MONEY_OR_NULL,
        }
    )
    bridge = obj(
        {
            "order": TEXT,
            "measure": TEXT,
            "target": _ref_of(DECIMAL),
            "steps": arr(step),
            "contributions": arr(contribution),
        }
    )
    summary = obj(
        {
            "fiscal_year_target": _ref_of(DECIMAL),
            "as_signed": _ref_of(MONEY),
            "working_plan": _ref_of(MONEY),
            "remaining_gap": _ref_of(MONEY),
            "twelve_month_gain": maybe(_ref_of(MONEY)),
            "cash_cost_in_twelve_months": maybe(_ref_of(MONEY_OR_NULL)),
            "no_plan_note": maybe(TEXT),
        }
    )
    action_row = obj(
        {
            "kind": enum("hire", "program"),
            "action": _ref_of(TEXT),
            "status": _ref_of(TEXT),
            "bookings_gained": _ref_of(maybe(PER_WINDOW)),
            "closes_alone_outcome": _ref_of(TEXT),
            "closes_alone_label": TEXT,
        }
    )
    actions = obj({"basis": const("as signed"), "note": TEXT, "rows": arr(action_row)})
    chain_quarter = obj(
        {
            "quarter": ref("Quarter"),
            "status": _ref_of(enum("closed", "in progress", "not started")),
            "bookings": obj(
                {
                    "target": _ref_of(DECIMAL),
                    "expected": _ref_of(MONEY_OR_NULL),
                    "gap": _ref_of(MONEY_OR_NULL),
                }
            ),
            "created_pipeline": obj(
                {
                    "required": _ref_of(MONEY_OR_NULL),
                    "required_note": _ref_of(maybe(TEXT)),
                    "expected": _ref_of(MONEY),
                    "created_between": _ref_of(pair(DATE)),
                    "outcome": _ref_of(OUTCOME_OF_LEVER),
                    "headline": _ref_of(TEXT),
                }
            ),
            "per_ramped_ae_month": obj(
                {
                    "required": _ref_of(MONEY_OR_NULL),
                    "expected": _ref_of(MONEY_OR_NULL),
                    "decides": _ref_of(BOOL),
                    "note": _ref_of(maybe(TEXT)),
                }
            ),
            "timing": obj(
                {
                    "applies": _ref_of(BOOL),
                    "label": _ref_of(maybe(TEXT)),
                    "reasons": _ref_of(arr(TEXT)),
                }
            ),
        }
    )
    chain = obj(
        {
            "basis": const("as signed"),
            "note": TEXT,
            "unavailable": maybe(TEXT),
            "quarters": arr(chain_quarter),
        }
    )
    full = obj(
        {
            "definition": TEXT,
            "plan_in_force": BOOL,
            "measured_around": TEXT,
            "windows": arr(TEXT),
            "expectation_note": TEXT,
            "sensitivity_note": TEXT,
            "history_note": TEXT,
            "drivers": arr(_driver()),
            "actions": actions,
            "bridge": bridge,
            "summary": summary,
            "chain": chain,
            "checks": arr(CHECK),
        }
    )
    return one_of(obj({"unavailable": TEXT}), full)


# ---------------------------------------------------------------- the rules


def _resolve(doc, pointer: str):
    """The value a JSON pointer finds in ``doc``; a missing path is a ``KeyError``."""
    node = doc
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _walk(node, path=""):
    yield path, node
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}/{i}")


def _is_ref(node) -> bool:
    return (
        isinstance(node, dict)
        and set(node) == {"value", "source"}
        and isinstance(node["source"], str)
    )


def rules_for(r: dict, rule: Callable[[bool, str], None]) -> None:
    w = r.get("worksheet")
    if w is None:
        return
    if "unavailable" in w:
        return
    where = "worksheet"
    # every referenced figure is what the report holds at its source
    for path, node in _walk(w):
        if _is_ref(node):
            try:
                found = _resolve(r, node["source"])
            except (KeyError, IndexError, ValueError):
                rule(
                    False,
                    f"{where}{path}: its source {node['source']} is not in the report",
                )
                continue
            rule(
                found == node["value"],
                f"{where}{path}: {node['value']!r} is not what {node['source']} holds ({found!r})",
            )
        elif isinstance(node, dict):
            for k, v in node.items():
                if k in SENTENCE_KEYS and isinstance(v, str):
                    rule(
                        not re.search(r"\d", v),
                        f"{where}{path}/{k}: a sentence carries a digit its fields do not",
                    )
    rule(
        all(c["passed"] for c in w["checks"]),
        "worksheet: a self-check of the section failed: "
        + "; ".join(c["name"] for c in w["checks"] if not c["passed"]),
    )
    in_force = "plan" in r and "unavailable" not in r["plan"]
    rule(
        w["plan_in_force"] == in_force,
        "worksheet.plan_in_force disagrees with the report's plan section",
    )
    rule(
        [d["driver"] for d in w["drivers"]] == list(rules.DRIVERS),
        "worksheet.drivers must be the four drivers in the declared order",
    )
    target = r["gap"]["fiscal_year"]["target"]
    for d in w["drivers"]:
        _driver_rules(d, Decimal(target), rule)
    _actions_rules(r, w["actions"], rule)
    _bridge_rules(r, w, rule)
    _summary_rules(r, w, rule)
    _chain_rules(r, w["chain"], rule)


def _places(driver: str) -> Decimal:
    return (
        Decimal("0.01")
        if driver in (rules.WON_ARR, rules.CYCLE_DAYS)
        else Decimal("0.0001")
    )


def _driver_rules(d: dict, target: Decimal, rule) -> None:
    name = d["driver"]
    where = f"worksheet.drivers[{name}]"
    ev = d["evidence"]
    used = [Decimal(q["value"]) for q in ev["quarters"] if q["eligible"]]
    rule(
        all(q["value"] is not None for q in ev["quarters"] if q["eligible"]),
        f"{where}: an eligible quarter must have a value",
    )
    rule(
        ev["eligible_quarters"] == len(used),
        f"{where}: eligible_quarters is not the count of eligible quarters",
    )
    rule(
        ev["required_quarters"] == rules.REQUIRED_QUARTERS,
        f"{where}: the gate is {rules.REQUIRED_QUARTERS} quarters",
    )
    rule(
        ev["gate_passed"] == (len(used) >= rules.REQUIRED_QUARTERS),
        f"{where}: gate_passed disagrees with the count",
    )
    rule(
        all(
            q["eligible"] == (q["not_eligible_because"] is None) for q in ev["quarters"]
        ),
        f"{where}: a quarter is refused exactly when it carries a reason",
    )
    h = d["historical"]
    rule(
        (h is None) == (not ev["gate_passed"]),
        f"{where}: historical settings exist exactly when the gate passes",
    )
    rule(
        (d["historical_unavailable_because"] is None) == (h is not None),
        f"{where}: a missing historical range must say why, and a present one must not",
    )
    if h is not None:
        low, high = rules.halves(used)
        tol = _places(name)
        rule(
            abs(Decimal(h["low"]["setting"]) - low) <= tol,
            f"{where}: the low setting is not the mean of the lower half",
        )
        rule(
            abs(Decimal(h["high"]["setting"]) - high) <= tol,
            f"{where}: the high setting is not the mean of the upper half",
        )
        rule(
            Decimal(h["minimum"]) == min(used) and Decimal(h["maximum"]) == max(used),
            f"{where}: minimum and maximum are not the observed extremes",
        )
    n = d["needed_alone"]
    value = None if n["value"] is None else Decimal(n["value"])
    reached = Decimal(n["achieved_fiscal_year_bookings"])
    rule(
        Decimal(n["target"]) == target.quantize(Decimal("0.01")),
        f"{where}: needed alone is measured against the year's target",
    )
    if n["outcome"] == wd.SOLVES:
        rule(
            reached >= target - CENT,
            f"{where}: a solve must reach the target",
        )
        rule(n["reason"] is None, f"{where}: a solve has no reason")
        rule(
            n["stepped"] == (n["overshoot"] is not None),
            f"{where}: only a stepped solve has an overshoot",
        )
        if n["overshoot"] is not None:
            rule(
                abs(Decimal(n["overshoot"]) - (reached - target)) <= CENT,
                f"{where}: overshoot is the bookings reached less the target",
            )
    elif n["outcome"] == wd.CANNOT:
        rule(
            reached < target,
            f"{where}: cannot close alone, yet the bookings reach the target",
        )
        rule(
            n["reason"] is not None and n["reason_label"] is not None,
            f"{where}: cannot close alone must say why",
        )
    else:
        rule(
            reached >= target - CENT,
            f"{where}: already at or ahead of target, yet the bookings are short",
        )
    inside = n["inside_observed_range"]
    if h is None or n["outcome"] != wd.SOLVES or value is None:
        rule(
            inside is None,
            f"{where}: inside_observed_range needs a historical range and a value to set beside it",
        )
    else:
        rule(
            inside == (Decimal(h["minimum"]) <= value <= Decimal(h["maximum"])),
            f"{where}: inside_observed_range disagrees with the value and the observed range",
        )
    if n["outcome"] != wd.SOLVES:
        rule(
            n["history_label"] is None,
            f"{where}: only a solve is set beside the history",
        )
    else:
        want = (
            ws.NO_HISTORY_LABEL
            if inside is None
            else ws.INSIDE_LABEL
            if inside
            else ws.BEYOND_LABEL
        )
        rule(
            n["history_label"] == want,
            f"{where}: history_label disagrees with inside_observed_range",
        )


def _actions_rules(r: dict, a: dict, rule) -> None:
    rule(
        len(a["rows"]) == len(r["actions"]["comparison"]),
        "worksheet.actions restates every row of the actions section",
    )


def _bridge_rules(r: dict, w: dict, rule) -> None:
    steps = w["bridge"]["steps"]
    kinds = [s["kind"] for s in steps]
    rule(
        kinds[0] == "as_signed"
        and kinds[-2:] == ["working_plan", "remaining_gap"]
        and all(k in ("hires", "program") for k in kinds[1:-2]),
        "worksheet.bridge: as signed, then each plan item, then the working plan and the remaining gap",
    )
    items = [s for s in steps if s["kind"] in ("hires", "program")]
    plan = r.get("plan")
    rule(
        len(items) == (len(plan["items"]) if plan and "items" in plan else 0),
        "worksheet.bridge has a step for each plan item",
    )
    running = Decimal(steps[0]["to"])
    for s in items:
        rule(
            Decimal(s["from"]) == running,
            "worksheet.bridge: each step starts where the last one ended",
        )
        running += Decimal(s["change"])
        rule(
            Decimal(s["to"]) == running,
            "worksheet.bridge: a step ends at its start plus its change",
        )
        try:
            rule(
                _resolve(r, s["source"]) == s["change"] or not s["valued"],
                f"worksheet.bridge: {s['label']} is not its plan contribution",
            )
        except (KeyError, IndexError, TypeError):
            rule(
                not s["valued"], f"worksheet.bridge: {s['source']} is not in the report"
            )
    working = next(s for s in steps if s["kind"] == "working_plan")
    gap = next(s for s in steps if s["kind"] == "remaining_gap")
    rule(
        running == Decimal(working["to"]),
        "worksheet.bridge: the steps do not sum to the working plan",
    )
    rule(
        abs(
            Decimal(w["bridge"]["target"]["value"])
            - Decimal(working["to"])
            - Decimal(gap["to"])
        )
        <= CENT,
        "worksheet.bridge: target less the working plan is not the remaining gap",
    )
    for s in (steps[0], working, gap):
        rule(
            _resolve(r, s["source"]) == s["to"],
            f"worksheet.bridge: {s['label']} is not what {s['source']} holds",
        )


def _summary_rules(r: dict, w: dict, rule) -> None:
    s, steps = w["summary"], w["bridge"]["steps"]
    by_kind = {
        x["kind"]: x
        for x in steps
        if x["kind"] in ("as_signed", "working_plan", "remaining_gap")
    }
    rule(
        s["as_signed"]["value"] == by_kind["as_signed"]["to"],
        "worksheet.summary: as signed is not the bridge's",
    )
    rule(
        s["working_plan"]["value"] == by_kind["working_plan"]["to"],
        "worksheet.summary: the working plan is not the bridge's",
    )
    rule(
        s["remaining_gap"]["value"] == by_kind["remaining_gap"]["to"],
        "worksheet.summary: the remaining gap is not the bridge's",
    )
    rule(
        (s["twelve_month_gain"] is not None) == w["plan_in_force"]
        and (s["cash_cost_in_twelve_months"] is not None) == w["plan_in_force"]
        and (s["no_plan_note"] is None) == w["plan_in_force"],
        "worksheet.summary: the plan's gain and cost are present exactly when a plan is in force",
    )


def _chain_rules(r: dict, chain: dict, rule) -> None:
    rp = r["required_pipeline"]
    if "unavailable" in rp:
        rule(
            chain["unavailable"] is not None and not chain["quarters"],
            "worksheet.chain: unavailable exactly as the requirement is",
        )
        return
    remaining = [q["quarter"] for q in rp["quarters"] if q["status"] != "closed"]
    rule(
        [q["quarter"] for q in chain["quarters"]] == remaining,
        "worksheet.chain: one entry for each remaining target quarter",
    )

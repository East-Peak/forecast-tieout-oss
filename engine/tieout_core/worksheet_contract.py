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
from datetime import date, timedelta
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
from .fiscal import add_months
from .fit import FitParams
from .plan import NEXT_12, REST_OF_FY

SENTENCE_KEYS = frozenset(
    {
        "outcome_label", "reason_label", "history_label", "limitation", "applies_to", "gate",
        "rule", "definition", "expectation_note", "sensitivity_note", "history_note",
        "historical_unavailable_because", "not_eligible_because", "no_plan_note",
        "closes_alone_label", "measured_around", "order", "measure", "unit_label",
    }
)  # fmt: skip
WINDOWS = (REST_OF_FY, NEXT_12)
STEP_KINDS = (
    "as_signed",
    "hires",
    "program",
    "actions",
    "working_plan",
    "remaining_gap",
)


def _ref_of(value: dict) -> dict:
    return obj({"value": value, "source": TEXT})


def _setting() -> dict:
    return obj({"setting": DECIMAL, "change": PER_WINDOW})


RANK = obj({REST_OF_FY: maybe(INT), NEXT_12: maybe(INT)})


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
            "reaches_target": BOOL,
            "precision_note": maybe(TEXT),
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
            "places": INT,
            "cannot_scale_because": maybe(TEXT),
            "rank": RANK,
            "current": obj(
                {
                    "value": DECIMAL_OR_NULL,
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
            "needed_alone": maybe(needed),
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
            "kind": enum("hires", "program", "actions"),
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
            "steps": arr(step, minItems=3),
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
            "rank": RANK,
        }
    )
    actions = obj(
        {"basis": const("as signed"), "note": TEXT, "rows": arr(action_row, maxItems=2)}
    )
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
            "drivers": arr(_driver(), minItems=4, maxItems=4),
            "actions": actions,
            "bridge": bridge,
            "summary": summary,
            "chain": chain,
            "checks": arr(CHECK),
        }
    )
    return one_of(obj({"unavailable": TEXT}), full)


# ---------------------------------------------------------------- the rules
#
# The validator never trusts a figure because it parses. What the report holds elsewhere (the
# restated actions, the summary, the bridge, the chain) is rebuilt from those sections and must
# equal the worksheet's copy, pointers included, so a valid number from the wrong path is refused.
# Every sentence must equal what its structured fields produce. What cannot be recomputed from
# the report alone (the change in bookings at a setting) is checked structurally here, and by the
# generator, which replays every committed sensitivity through the model (``worksheet_replay``).


def _digits(text) -> bool:
    return isinstance(text, str) and re.search(r"\d", text) is not None


def _walk_sentences(node, path, rule) -> None:
    """No sentence carries a digit its fields do not."""
    if isinstance(node, dict):
        if set(node) == {"value", "source"}:
            return
        for k, v in node.items():
            if k in SENTENCE_KEYS and _digits(v):
                rule(
                    False,
                    f"worksheet{path}/{k}: a sentence carries a digit its fields do not",
                )
            _walk_sentences(v, f"{path}/{k}", rule)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_sentences(v, f"{path}/{i}", rule)


def rules_for(r: dict, rule: Callable[[bool, str], None]) -> None:
    w = r.get("worksheet")
    if w is None or "unavailable" in w:
        return
    try:
        _check(r, w, rule)
    except (
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        AttributeError,
        ArithmeticError,
    ) as e:
        rule(False, f"worksheet: the section is malformed ({type(e).__name__}: {e})")


def _check(r: dict, w: dict, rule) -> None:
    plan = r.get("plan")
    in_force = plan is not None and "unavailable" not in plan
    plan_section = plan if in_force else None
    with_actions = ws.has_actions(plan if in_force else None)
    for key, want in ws.static_texts(in_force, with_actions).items():
        rule(w[key] == want, f"worksheet.{key} is not what the report writes")
    _walk_sentences(w, "", rule)
    # restated and referenced figures: rebuilt from the report's own sections
    rule(
        w["actions"] == ws._action_rows(r["actions"]),
        "worksheet.actions is not the actions section restated, pointers and ranks included",
    )
    rule(
        w["summary"] == ws._summary(plan_section, r["gap"]),
        "worksheet.summary is not the report's own figures, by the right pointers",
    )
    rule(
        w["chain"] == ws._chain(r["gap"], r["required_pipeline"]),
        "worksheet.chain is not the as-signed requirement, by the right pointers",
    )
    bridge, _ = ws._bridge(plan_section, r["gap"])
    rule(
        w["bridge"] == bridge,
        "worksheet.bridge is not the plan's contributions in order, by the right pointers",
    )
    # the section's own checks pass, and the verdict counts them
    rule(
        all(c["passed"] for c in w["checks"]),
        "worksheet: a self-check of the section failed: "
        + "; ".join(c["name"] for c in w["checks"] if not c["passed"]),
    )
    verdict = {c["name"] for c in r["verdicts"]["software_correct"]["checks"]}
    rule(
        {c["name"] for c in w["checks"]} <= verdict,
        "worksheet: its self-checks are not in the software-correct verdict",
    )
    rule(
        [d["driver"] for d in w["drivers"]] == list(rules.DRIVERS),
        "worksheet.drivers must be the four drivers in the declared order",
    )
    for d in w["drivers"]:
        _driver_rules(r, d, rule)
    magnitudes = [ws._driver_magnitudes(d) for d in w["drivers"]]
    rule(
        [d["rank"] for d in w["drivers"]] == ws.rank_by_window(magnitudes),
        "worksheet.drivers: the rank per window is not the order of the largest absolute change",
    )


def _tol(driver: str) -> Decimal:
    """One unit in the last place a driver is written to."""
    return Decimal(1).scaleb(-rules.PRECISION[driver])


def _money(x: str) -> Decimal:
    return Decimal(x)


def _quarter_rules(r: dict, d: dict, rule, where: str) -> list[Decimal]:
    """The observations, each recomputed from its own fields; returns the eligible values."""
    name, ev = d["driver"], d["evidence"]
    as_of = date.fromisoformat(r["inputs"]["as_of"])
    fy_start = date.fromisoformat(r["inputs"]["fiscal_year_start"])
    horizon = FitParams().horizon_days
    used: list[Decimal] = []
    previous_end = None
    quarters = ev["quarters"]
    for q in quarters:
        start, end = date.fromisoformat(q["start"]), date.fromisoformat(q["end"])
        rule(
            q["quarter"] == rules.quarter_label(start, fy_start),
            f"{where}: {q['quarter']} is not the name of the quarter starting {q['start']}",
        )
        rule(
            end == add_months(start, 3) - timedelta(days=1),
            f"{where}: {q['quarter']} is not three months long",
        )
        rule(
            previous_end is None or start == previous_end + timedelta(days=1),
            f"{where}: the quarters are not consecutive",
        )
        rule(end <= as_of, f"{where}: {q['quarter']} is not complete by the as-of date")
        previous_end = end
        mature = end + timedelta(days=horizon) <= as_of
        rule(
            q["mature"] == mature,
            f"{where}: {q['quarter']}: maturity is not what its dates say",
        )
        has_exposure = q["exposure"] is not None
        rule(
            has_exposure == (name == rules.PRODUCTIVITY),
            f"{where}: {q['quarter']}: exposure belongs to productivity alone",
        )
        exposure = Decimal(q["exposure"]) if has_exposure else Decimal(1)
        probe = rules.Quarter(
            q["quarter"],
            start,
            end,
            q["created"],
            q["wins"],
            mature,
            exposure,
            None,
            None,
            None,
            None,
        )
        ok, why = rules.eligible(probe, name)
        rule(
            q["eligible"] == ok and q["not_eligible_because"] == why,
            f"{where}: {q['quarter']}: eligibility is not what its own counts give",
        )
        value = None if q["value"] is None else Decimal(q["value"])
        tol = _tol(name)
        if name == rules.WIN_RATE:
            want_none = q["created"] == 0
            ok_value = (
                value is None
                if want_none
                else value is not None
                and abs(value - Decimal(q["wins"]) / q["created"]) <= tol
            )
        elif name == rules.PRODUCTIVITY:
            ok_value = (
                (value is None)
                if exposure <= 0
                else value is not None
                and abs(value - Decimal(q["created"]) / exposure)
                <= Decimal(q["created"]) * Decimal("0.0051") / (exposure * exposure)
                + tol
            )
        else:
            ok_value = (value is None) == (q["wins"] == 0)
        rule(
            ok_value,
            f"{where}: {q['quarter']}: its value does not follow from its own counts",
        )
        if q["eligible"]:
            rule(
                value is not None,
                f"{where}: {q['quarter']} is eligible but has no value",
            )
            if value is not None:
                used.append(value)
    if quarters:
        last = date.fromisoformat(quarters[-1]["start"])
        rule(
            add_months(last, 6) - timedelta(days=1) > as_of,
            f"{where}: a complete quarter was left out",
        )
    return used


def _driver_rules(r: dict, d: dict, rule) -> None:
    name = d["driver"]
    plan = r.get("plan")
    acted = r.get("driver_actions") or {}
    if "unavailable" in acted or "items" not in acted:
        stacked = ws.has_actions(
            plan if plan is not None and "unavailable" not in plan else None
        )
    else:  # the win rate stacks only where an action is on it
        stacked = any(i["driver"] == rules.WIN_RATE for i in acted["items"])
    stacked = stacked and name == rules.WIN_RATE
    where = f"worksheet.drivers[{name}]"
    inputs = r["inputs"]
    adopted = inputs["capacity"]["decision"] == "adopted"
    params = FitParams(estimator=inputs["fit"])
    as_of = date.fromisoformat(inputs["as_of"])
    unit, unit_label, display, applies = ws.unit_for(adopted, name)
    for key, want in (
        ("label", ws.LABELS[name]), ("applies_to", applies), ("unit", unit),
        ("unit_label", unit_label), ("display", display), ("places", rules.PRECISION[name]),
    ):  # fmt: skip
        rule(d[key] == want, f"{where}.{key} is not what the report writes")
    ev, cur = d["evidence"], d["current"]
    rule(
        ev["gate"] == ws.GATE_WORDS[name],
        f"{where}.evidence.gate is not what the report writes",
    )
    rule(
        ev["required_quarters"] == rules.REQUIRED_QUARTERS,
        f"{where}: the gate is {rules.REQUIRED_QUARTERS} quarters",
    )
    start, end = ws.fit_window(name, params, as_of)
    rule(
        (cur["fit_in_use"], cur["creation_from"], cur["creation_to"])
        == (params.estimator, start.isoformat(), end.isoformat()),
        f"{where}.current names a fit window the fit in use does not have",
    )
    used = _quarter_rules(r, d, rule, where)
    rule(
        ev["eligible_quarters"] == len(used),
        f"{where}: eligible_quarters is not the count of eligible quarters",
    )
    gate = len(used) >= rules.REQUIRED_QUARTERS
    rule(ev["gate_passed"] == gate, f"{where}: gate_passed disagrees with the count")
    # what cannot be scaled
    current = None if cur["value"] is None else Decimal(cur["value"])
    if name == rules.CYCLE_DAYS:
        want_why = (
            ws.NO_WIN_TIMES
            if current is None
            else ws.ZERO_CYCLE
            if current == 0
            else None
        )
    else:
        want_why = None
        rule(current is not None, f"{where}: a current value is required")
    rule(
        d["cannot_scale_because"] == want_why,
        f"{where}: cannot_scale_because is not what the current value says",
    )
    h = d["historical"]
    offered = gate and want_why is None
    rule(
        (h is not None) == offered,
        f"{where}: historical settings exist exactly when the gate passes and the driver can be scaled",
    )
    rule(
        d["historical_unavailable_because"]
        == (None if offered else want_why or ws.GATE_FAILED),
        f"{where}: the reason a range is missing is not what the gate and the driver say",
    )
    rule(
        d["limitation"]
        == ws.limitation_text(name, gate, params.estimator, adopted, stacked),
        f"{where}.limitation is not what the report writes",
    )
    if h is not None and used and current is not None:
        _settings_rules(name, h, used, current, rule, where, stacked)
    n = d["needed_alone"]
    rule(
        (n is None) == (current is None or stacked),
        f"{where}: needed alone exists exactly when there is a current value and no action "
        "sits on the win rate",
    )
    if n is not None and current is not None:
        _needed_rules(r, name, n, h, current, rule, where)


def _settings_rules(name, h, used, current, rule, where, stacked=False) -> None:
    low, high = rules.halves(used)
    tol = _tol(name)
    lo, hi = Decimal(h["low"]["setting"]), Decimal(h["high"]["setting"])
    rule(
        abs(lo - low) <= tol,
        f"{where}: the low setting is not the mean of the lower half",
    )
    rule(
        abs(hi - high) <= tol,
        f"{where}: the high setting is not the mean of the upper half",
    )
    rule(
        Decimal(h["minimum"]) == min(used) and Decimal(h["maximum"]) == max(used),
        f"{where}: minimum and maximum are not the observed extremes",
    )
    rule(
        h["rule"] == ws.SETTINGS_RULE,
        f"{where}.historical.rule is not what the report writes",
    )
    rule(
        Decimal(h["minimum"]) <= lo <= hi <= Decimal(h["maximum"]),
        f"{where}: the settings are not inside the observed range",
    )
    # structure of the sensitivities: both windows, on the right side of zero, and (for the three
    # drivers that scale new-pipeline bookings in proportion) on one line through the current value
    if (
        stacked
    ):  # actions on the rate make bookings in it bend where a day's rate is held
        return
    sign = -1 if name == rules.CYCLE_DAYS else 1
    changes = {}
    for side, setting in (("low", lo), ("high", hi)):
        for window in WINDOWS:
            change = Decimal(h[side]["change"][window])
            changes[side, window] = change
            move = (setting - current) * sign
            ok = change == 0 if move == 0 else change * move >= 0
            rule(
                ok,
                f"{where}: the {side} setting's change in {window} is on the wrong side of zero",
            )
    if name != rules.CYCLE_DAYS:
        e = _tol(name) * 2
        for window in WINDOWS:
            cl, ch = changes["low", window], changes["high", window]
            cross = cl * (hi - current) - ch * (lo - current)
            bound = (
                (abs(cl) + abs(ch)) * e
                + Decimal("0.01") * (abs(hi - current) + abs(lo - current))
                + Decimal("0.01")
            )
            rule(
                abs(cross) <= bound,
                f"{where}: the changes in {window} do not lie on one line through the current value",
            )


def _needed_rules(r, name, n, h, current, rule, where) -> None:
    tol = _tol(name)
    target = Decimal(r["gap"]["fiscal_year"]["target"]).quantize(Decimal("0.01"))
    rule(
        Decimal(n["target"]) == target,
        f"{where}: needed alone is measured against the year's target",
    )
    reached = Decimal(n["achieved_fiscal_year_bookings"])
    outcome, reason = n["outcome"], n["reason"]
    rule(
        n["stepped"] == (name == rules.CYCLE_DAYS),
        f"{where}: only the cycle solve is stepped",
    )
    rule(
        n["reaches_target"] == (outcome != wd.CANNOT),
        f"{where}: reaches_target disagrees with the outcome",
    )
    value = None if n["value"] is None else Decimal(n["value"])
    rule(value is not None, f"{where}: a needed-alone figure carries its value")
    if value is not None:
        rule(
            len(n["value"].split(".")[-1]) == rules.PRECISION[name],
            f"{where}: the value is not written to the driver's places",
        )
    inside = n["inside_observed_range"]
    rule(
        n["reason_label"] == (ws.REASON_LABELS.get(reason) if reason else None),
        f"{where}: the reason is not worded as the report words it",
    )
    if outcome == wd.SOLVES:
        rule(reason is None, f"{where}: a solve has no reason")
        rule(
            reached >= target,
            f"{where}: a solve must reach the target when its own value is entered",
        )
        rule(
            n["overshoot"] is not None
            and abs(Decimal(n["overshoot"]) - (reached - target)) <= Decimal("0.01"),
            f"{where}: overshoot is the bookings reached less the target",
        )
        rule(
            n["overshoot"] is None or Decimal(n["overshoot"]) >= 0,
            f"{where}: a solve cannot overshoot below zero",
        )
        rule(
            n["precision_note"] is None,
            f"{where}: only a sub-cent shortfall carries a precision note",
        )
        rule(
            n["outcome_label"]
            == (
                ws.STEPPED_LABEL
                if name == rules.CYCLE_DAYS
                else ws.OUTCOME_LABELS[wd.SOLVES]
            ),
            f"{where}: the outcome is not worded as the report words it",
        )
        rule(
            (n["scale"] is not None) == (name == rules.CYCLE_DAYS),
            f"{where}: only the cycle solve has a scale",
        )
        if value is not None and name != rules.CYCLE_DAYS:
            rule(
                value >= current,
                f"{where}: a solve must not lower a driver that is short of target",
            )
        if name == rules.CYCLE_DAYS and value is not None:
            rule(value <= current, f"{where}: closing on cycle means shortening it")
        want_inside = (
            None
            if h is None or value is None
            else Decimal(h["minimum"]) <= value <= Decimal(h["maximum"])
        )
        rule(
            inside == want_inside,
            f"{where}: inside_observed_range does not follow from the value and the observed range",
        )
        want_label = (
            ws.NO_HISTORY_LABEL
            if want_inside is None
            else ws.INSIDE_LABEL
            if want_inside
            else ws.BEYOND_LABEL
        )
        rule(
            n["history_label"] == want_label,
            f"{where}: history_label disagrees with inside_observed_range",
        )
        if name == rules.WIN_RATE:
            rule(value is None or value <= 1, f"{where}: a win rate cannot pass one")
    elif outcome == wd.COVERED:
        rule(
            reason is None
            and n["overshoot"] is None
            and n["scale"] is None
            and n["precision_note"] is None,
            f"{where}: already ahead carries no reason, overshoot or scale",
        )
        rule(
            reached >= target,
            f"{where}: already at or ahead of target, yet the bookings are short",
        )
        rule(
            value == current or abs((value or 0) - current) < tol,
            f"{where}: already ahead leaves the value where it is",
        )
        rule(
            n["outcome_label"] == ws.OUTCOME_LABELS[wd.COVERED],
            f"{where}: the outcome is not worded as the report words it",
        )
        rule(
            inside is None and n["history_label"] is None,
            f"{where}: only a solve is set beside the history",
        )
    elif outcome == wd.CANNOT:
        allowed = {
            rules.WIN_RATE: (wd.BOUNDED_AT_ONE, wd.NO_EFFECT),
            rules.CYCLE_DAYS: (wd.ZERO_DAYS_SHORT,),
        }.get(name, (wd.NO_EFFECT,))
        rule(reason in allowed, f"{where}: that reason does not belong to this driver")
        rule(
            reached <= target,
            f"{where}: cannot close alone, yet the bookings reach the target",
        )
        rule(
            n["overshoot"] is None,
            f"{where}: a figure that does not reach the target has no overshoot",
        )
        rule(
            n["precision_note"] == (ws.SUB_CENT_NOTE if reached == target else None),
            f"{where}: a sub-cent shortfall must be explained, and only then",
        )
        rule(
            n["outcome_label"] == ws.OUTCOME_LABELS[wd.CANNOT],
            f"{where}: the outcome is not worded as the report words it",
        )
        rule(
            (n["scale"] is not None) == (name == rules.CYCLE_DAYS),
            f"{where}: only the cycle solve has a scale",
        )
        rule(
            inside is None and n["history_label"] is None,
            f"{where}: only a solve is set beside the history",
        )
        if reason == wd.BOUNDED_AT_ONE:
            rule(value == 1, f"{where}: bounded at one means the value written is one")
    else:
        rule(False, f"{where}: unknown outcome {outcome!r}")

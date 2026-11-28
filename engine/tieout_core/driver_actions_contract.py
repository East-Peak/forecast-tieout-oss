"""The driver actions section's schema and the rules a schema cannot say.

A figure the section shares with the plan section or the worksheet (the joint gain, the expected
fiscal year, a quarter, the baseline rate, the worksheet's low and high) must be what that section
holds; the reconciliation line is the joint gain less the sum of the removal values as written,
its sentence is the one its sign and its rounding allowance call for, and the evidence label is
the one the target's place against the worksheet's settings calls for.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from . import driver_actions as da
from .contract import (
    BOOL,
    DECIMAL,
    DECIMAL_OR_NULL,
    INT,
    MONEY,
    MONTH,
    PER_WINDOW,
    TEXT,
    arr,
    const,
    enum,
    maybe,
    obj,
    one_of,
    ref,
)
from .fiscal import month_end
from .plan import NEXT_12, REST_OF_FY

WINDOWS = (REST_OF_FY, NEXT_12)
CENT = Decimal("0.01")


def schema() -> dict:
    placed = {
        "historical_low": DECIMAL_OR_NULL,
        "historical_high": DECIMAL_OR_NULL,
        "position": enum("inside", "below", "above", "none"),
        "label": TEXT,
    }
    evidence = one_of(
        obj(
            {
                "baseline_rate": DECIMAL,
                "change_points": DECIMAL,
                "resulting_rate": DECIMAL,
                **placed,
            }
        ),
        obj(
            {
                "baseline": DECIMAL,
                "change_percent": DECIMAL,
                "resulting": DECIMAL,
                **placed,
            }
        ),
    )
    item = obj(
        {
            "id": TEXT,
            "name": TEXT,
            "driver": enum("win_rate", "won_arr", "productivity"),
            "slice": obj(
                {
                    "kind": enum("company", "segment"),
                    "key": maybe(TEXT),
                    "label": TEXT,
                }
            ),
            "start": MONTH,
            "ramp_months": {**INT, "minimum": 0},
            "target": DECIMAL,
            "affects": TEXT,
            "removal_value": PER_WINDOW,
            "evidence": evidence,
        }
    )
    figures = obj(
        {
            "bookings": PER_WINDOW,
            "expected_fiscal_year": MONEY,
            "quarters": arr(
                obj(
                    {
                        "quarter": ref("Quarter"),
                        "status": enum("closed", "in progress", "not started"),
                        "forecast": MONEY,
                        "expected": MONEY,
                    }
                )
            ),
        }
    )
    full = obj(
        {
            "definition": TEXT,
            "line": TEXT,
            "removal_label": const(da.REMOVAL_LABEL),
            "removal_note": TEXT,
            "items": arr(item, minItems=1),
            "joint_gain": PER_WINDOW,
            "reconciliation": obj(
                {
                    "values": PER_WINDOW,
                    "tolerance": PER_WINDOW,
                    "sentences": obj({REST_OF_FY: TEXT, NEXT_12: TEXT}),
                    "material": obj({REST_OF_FY: BOOL, NEXT_12: BOOL}),
                }
            ),
            "without_actions": figures,
            "with_actions": figures,
            "range_note": TEXT,
            "rounding_note": TEXT,
        }
    )
    return one_of(
        obj({"items": arr(item, maxItems=0), "definition": TEXT, "line": TEXT}),
        obj({"unavailable": TEXT}),
        full,
    )


def rules_for(r: dict, rule: Callable[[bool, str], None]) -> None:
    section = r.get("driver_actions")
    plan = r.get("plan")
    in_plan = (
        []
        if plan is None or "unavailable" in plan
        else [i for i in plan["items"] if i["kind"] == "actions"]
    )
    if section is None or "unavailable" in section:
        rule(
            not in_plan,
            "an unavailable actions section cannot sit beside a valued step",
        )
        return
    rule(
        bool(section["items"]) == bool(in_plan),
        "the plan has an actions step exactly when the actions section lists actions",
    )
    if not section["items"]:
        for text, want in (("definition", da.DEFINITION), ("line", da.LINE)):
            rule(
                section[text] == want,
                f"driver_actions.{text} is not what the report writes",
            )
        return
    try:
        _check(r, section, plan, in_plan[0], rule)
    except (KeyError, IndexError, TypeError, ValueError, ArithmeticError) as e:
        rule(
            False, f"driver_actions: the section is malformed ({type(e).__name__}: {e})"
        )


def _check(r: dict, s: dict, plan: dict, step: dict, rule) -> None:
    items = s["items"]
    ids = [i["id"] for i in items]
    rule(len(set(ids)) == len(ids), "driver_actions: action ids are not unique")
    acts = [_Driver(i["driver"]) for i in items]
    for text, want in (
        ("definition", da.definition_for(acts)),
        ("line", da.line_for(acts)),
        ("removal_note", da.REMOVAL_NOTE),
        ("range_note", da.RANGE_NOTE),
        ("rounding_note", da.ROUNDING_NOTE),
    ):
        rule(s[text] == want, f"driver_actions.{text} is not what the report writes")
    windows = r["forecasts"]["windows"]
    fy_end = date.fromisoformat(r["inputs"]["fiscal_year_end"])
    months = {
        REST_OF_FY: sum(
            1 for m in windows if month_end(date.fromisoformat(f"{m}-01")) <= fy_end
        ),
        NEXT_12: len(windows),
    }
    joint = {w: Decimal(s["joint_gain"][w]) for w in WINDOWS}
    summed = {
        w: sum((Decimal(i["removal_value"][w]) for i in items), Decimal(0))
        for w in WINDOWS
    }
    rec = s["reconciliation"]
    for w in WINDOWS:
        want = joint[w] - summed[w]
        rule(
            Decimal(rec["values"][w]) == want,
            f"driver_actions: the reconciliation in {w} is not the joint gain less the removal values",
        )
        allowed = CENT * months[w] * (1 + len(items))
        rule(
            Decimal(rec["tolerance"][w]) == allowed,
            f"driver_actions: the rounding allowance in {w} is not a cent a month for each forecast",
        )
        rule(
            rec["sentences"][w]
            == da.reconciliation_sentence(joint[w], summed[w], allowed),
            f"driver_actions: the reconciliation sentence in {w} does not say what its figure does",
        )
        rule(
            rec["material"][w] == da.is_material(want),
            f"driver_actions: the reconciliation in {w} is not marked material exactly where it rounds to a dollar or more",
        )
    rule(
        step["contribution"] == s["joint_gain"],
        "driver_actions: the joint gain is not the plan's actions step",
    )
    without, with_ = s["without_actions"], s["with_actions"]
    rule(
        with_["bookings"] == plan["with_plan"],
        "driver_actions: the with-actions bookings are not the plan's",
    )
    rule(
        with_["expected_fiscal_year"] == plan["expected_fiscal_year"],
        "driver_actions: the with-actions expected fiscal year is not the plan's",
    )
    for w in WINDOWS:
        rule(
            Decimal(with_["bookings"][w]) - Decimal(without["bookings"][w]) == joint[w],
            f"driver_actions: with less without is not the joint gain in {w}",
        )
    rule(
        Decimal(with_["expected_fiscal_year"])
        - Decimal(without["expected_fiscal_year"])
        == joint[REST_OF_FY],
        "driver_actions: the expected fiscal year with and without differ by more than the joint gain",
    )
    rule(
        [q["quarter"] for q in with_["quarters"]]
        == [q["quarter"] for q in without["quarters"]]
        == [q["quarter"] for q in plan["with_plan_quarters"]],
        "driver_actions: the quarters are not the plan's",
    )
    for mine, theirs in zip(with_["quarters"], plan["with_plan_quarters"]):
        rule(
            (mine["status"], mine["forecast"], mine["expected"])
            == (theirs["status"], theirs["forecast"], theirs["expected"]),
            f"driver_actions: {mine['quarter']} with actions is not the plan's",
        )
    rows = {d["driver"]: d for d in r["worksheet"]["drivers"]}
    as_of = date.fromisoformat(r["inputs"]["as_of"])
    for i in items:
        _item(i, rows[i["driver"]], as_of, rule)


class _Driver:
    """An action as the report names it: only its driver is read by the wording rules."""

    def __init__(self, driver: str) -> None:
        self.driver = driver


def _item(i: dict, row: dict, as_of: date, rule) -> None:
    where = f"driver_actions {i['id']}"
    ev = i["evidence"]
    driver = i["driver"]
    target = Decimal(i["target"])
    rule(
        date.fromisoformat(i["start"] + "-01") > as_of,
        f"{where}: it starts on or before the as-of date",
    )
    rule(
        (i["slice"]["kind"] == "company") == (i["slice"]["key"] is None),
        f"{where}: the slice's kind and key disagree",
    )
    if driver == "win_rate":
        rule(0 <= target <= 1, f"{where}: the target is not a probability")
        rule(
            ev["resulting_rate"] == i["target"],
            f"{where}: the resulting rate is not the target",
        )
        rule(
            ev["baseline_rate"] == row["current"]["value"],
            f"{where}: the baseline is not the worksheet's pooled win rate",
        )
        rule(
            abs(
                (Decimal(ev["resulting_rate"]) - Decimal(ev["baseline_rate"])) * 100
                - Decimal(ev["change_points"])
            )
            <= CENT,
            f"{where}: the change in points is not the resulting rate less the baseline",
        )
    else:
        rule(target >= 0, f"{where}: the target is negative")
        rule(
            ev["resulting"] == i["target"],
            f"{where}: the resulting value is not the target",
        )
        base = row["current"]["value"]
        rule(
            ev["baseline"] == base,
            f"{where}: the baseline is not the worksheet's pooled value",
        )
        rule(
            bool(Decimal(base))
            and abs(
                (Decimal(ev["resulting"]) / Decimal(base) - 1) * 100
                - Decimal(ev["change_percent"])
            )
            <= CENT,
            f"{where}: the change in percent is not the resulting value over the baseline",
        )
    h = row["historical"]
    rule(
        (ev["historical_low"], ev["historical_high"])
        == ((None, None) if h is None else (h["low"]["setting"], h["high"]["setting"])),
        f"{where}: the low and high are not the worksheet's",
    )
    position, label = da.placing(target, row, driver)
    rule(
        (ev["position"], ev["label"]) == (position, label),
        f"{where}: the label does not say where the target sits against the worksheet's settings",
    )
    rule(
        i["affects"]
        == da.affects_text(i["slice"]["label"], i["start"], i["ramp_months"], driver),
        f"{where}: the sentence on what it affects is not what the report writes",
    )

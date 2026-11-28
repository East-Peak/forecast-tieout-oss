"""The change in percent is written from the exact baseline and target, and the contract checks
it from the two figures as displayed, so it must allow for what their rounding hides."""

from datetime import date
from decimal import Decimal

import pytest

from engine.tieout_core import driver_actions as da
from engine.tieout_core import driver_actions_contract as dac

D = Decimal


def findings(driver, baseline, target, percent):
    row = {"current": {"value": baseline}, "historical": None}
    item = {
        "id": "x", "name": "x", "driver": driver, "start": "2026-10", "ramp_months": 0,
        "slice": {"kind": "company", "key": None, "label": "Company"},
        "target": target, "affects": da.affects_text("Company", "2026-10", 0, driver),
        "removal_value": {},
        "evidence": {
            "baseline": baseline, "change_percent": percent, "resulting": target,
            "historical_low": None, "historical_high": None,
            "position": "none", "label": da.not_offered(driver),
        },
    }  # fmt: skip
    out = []
    dac._item(
        item,
        row,
        date(2026, 8, 31),
        lambda ok, why: out.append(why) if not ok else None,
    )
    return out


def written(base: str, target: str, places: int) -> tuple[str, str, str]:
    """What the report writes for an exact baseline and target."""
    b, t = D(base), D(target)
    shown = lambda x: f"{float(x):.{places}f}"
    return shown(b), shown(t), f"{(t / b - 1) * 100:.2f}"


def test_a_repeating_decimal_baseline_that_doubles_is_not_refused_for_its_rounding():
    base, target, percent = written("0.123456", "0.246912", 4)
    assert (base, target, percent) == ("0.1235", "0.2469", "100.00")
    assert findings("productivity", base, target, percent) == []


def test_a_baseline_that_displays_as_zero_is_not_refused():
    base, target, percent = written("0.00004", "0.0001", 4)
    assert base == "0.0000" and percent == "150.00"
    assert findings("productivity", base, target, percent) == []


@pytest.mark.parametrize("wrong", ["99.00", "101.00", "-5.00"])
def test_a_figure_the_rounding_cannot_explain_is_still_refused(wrong):
    assert findings("productivity", "0.1235", "0.2469", wrong) != []


def test_dollars_to_the_cent_follow_the_same_rule():
    base, target, percent = written("413835.733", "827671.4659", 2)
    assert findings("won_arr", base, target, percent) == []
    assert findings("won_arr", base, target, "50.00") != []

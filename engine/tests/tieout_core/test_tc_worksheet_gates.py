"""When a gate fails there are no historical settings and no bars: the fields are null with a
reason. Six eligible quarters turn them on."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from engine.tests.tieout_core.test_tc_worksheet_drivers import AS_OF, ground
from engine.tieout_core import (
    worksheet,
)
from engine.tieout_core import (
    worksheet_drivers as wd,
)
from engine.tieout_core import (
    worksheet_rules as rules,
)
from engine.tieout_core.fit import FitParams
from engine.tieout_core.worksheet_rules import Quarter

D = Decimal


def quarters(n, immature=0, created=30, wins=8):
    out = []
    start = date(2024, 2, 1)
    for i in range(n):
        end = start + timedelta(days=89)
        out.append(
            Quarter(
                f"Q{i}", start, end, created, wins, i < n - immature, D(10),
                D("0.20") + D(i) / 100, D(1000) + i, D(90) + i, D(3) + D(i) / 10,
            )
        )  # fmt: skip
        start = end + timedelta(days=1)
    return out


def row(qs, name, params=None, **kw):
    g = ground(target=D(10**9), **kw)
    c = worksheet.Context(g, wd.Probe(g), qs, params or FitParams(), g.fy_target)
    return worksheet.driver_row(c, name)


def test_five_eligible_quarters_give_no_settings_and_a_reason():
    d = row(quarters(5), rules.WIN_RATE)
    assert d["historical"] is None
    assert d["historical_unavailable_because"] == worksheet.GATE_FAILED
    assert (
        d["evidence"]["gate_passed"] is False
        and d["evidence"]["eligible_quarters"] == 5
    )
    assert d["needed_alone"]["inside_observed_range"] is None
    assert worksheet.GATE_FAILED in d["limitation"]
    assert len(d["evidence"]["quarters"]) == 5  # the observations are still shown


def test_six_eligible_quarters_give_settings_and_no_reason():
    d = row(quarters(6), rules.WIN_RATE)
    assert d["historical"] is not None and d["historical_unavailable_because"] is None
    assert d["evidence"]["gate_passed"] is True


def test_immature_quarters_do_not_count_toward_the_six():
    d = row(quarters(7, immature=1), rules.WIN_RATE)
    assert d["evidence"]["eligible_quarters"] == 6
    last = d["evidence"]["quarters"][-1]
    assert last["eligible"] is False and "horizon" in last["not_eligible_because"]


def test_too_few_wins_fail_size_and_cycle_but_not_win_rate():
    qs = quarters(8, wins=4)
    assert row(qs, rules.WIN_RATE)["evidence"]["gate_passed"] is True
    for name in (rules.WON_ARR, rules.CYCLE_DAYS):
        assert row(qs, name)["evidence"]["gate_passed"] is False


def test_productivity_is_counted_without_waiting_for_maturity():
    qs = quarters(6, immature=3)
    assert row(qs, rules.PRODUCTIVITY)["evidence"]["gate_passed"] is True
    assert row(qs, rules.WIN_RATE)["evidence"]["gate_passed"] is False


def test_a_recency_fit_names_its_limitation():
    d = row(
        quarters(6), rules.WIN_RATE, replace(FitParams(), estimator=worksheet.RECENCY)
    )
    assert "older than that fit" in d["limitation"]
    assert row(quarters(6), rules.WIN_RATE)["limitation"] is None


def test_the_current_value_is_the_fits_not_a_historical_one():
    d = row(quarters(6), rules.WIN_RATE)
    assert (
        d["current"]["value"] == "0.5000"
        and AS_OF.isoformat() >= d["current"]["creation_to"]
    )


def test_a_company_with_no_win_time_evidence_has_no_cycle_to_move_and_says_so():
    d = row(quarters(6), rules.CYCLE_DAYS, timing=())
    assert d["current"]["value"] is None and d["needed_alone"] is None
    assert d["historical"] is None
    assert d["cannot_scale_because"] == worksheet.NO_WIN_TIMES
    assert d["historical_unavailable_because"] == worksheet.NO_WIN_TIMES
    # the other drivers still work, and their win rate has no effect to speak of only if it has none
    assert row(quarters(6), rules.WIN_RATE, timing=())["needed_alone"] is not None


def test_a_cycle_of_zero_days_cannot_be_scaled_and_cannot_close_on_cycle():
    d = row(quarters(6), rules.CYCLE_DAYS, timing=(0,))
    assert d["current"]["value"] == "0.00"
    assert d["historical"] is None
    assert d["cannot_scale_because"] == worksheet.ZERO_CYCLE
    n = d["needed_alone"]
    assert (n["outcome"], n["reason"]) == (
        "cannot_close_alone",
        "short_even_at_zero_days",
    )
    assert n["reaches_target"] is False and n["inside_observed_range"] is None


def test_a_cycle_of_zero_days_already_ahead_needs_nothing():
    g = ground(timing=(0,), target=D(1))
    c = worksheet.Context(g, wd.Probe(g), quarters(6), FitParams(), g.fy_target)
    n = worksheet.driver_row(c, rules.CYCLE_DAYS)["needed_alone"]
    assert n["outcome"] == "already_at_or_ahead" and n["reaches_target"] is True


def test_scaling_a_cycle_that_has_no_days_is_refused_loudly():
    import pytest

    for timing in ((), (0,)):
        with pytest.raises(ValueError):
            wd.with_setting(ground(timing=timing), rules.CYCLE_DAYS, D(10))


def test_a_sub_cent_shortfall_is_explained_in_words():
    from engine.tests.tieout_core.test_tc_worksheet_drivers import ground as g0

    base = wd.Probe(g0(win_rate=D(1)))
    fy = base.fiscal_year(base.base)
    g = g0(win_rate=D(1), target=fy + D("0.0004"))
    c = worksheet.Context(g, wd.Probe(g), quarters(6), FitParams(), g.fy_target)
    n = worksheet.driver_row(c, rules.WIN_RATE)["needed_alone"]
    assert n["outcome"] == "cannot_close_alone" and n["reaches_target"] is False
    assert n["achieved_fiscal_year_bookings"] == n["target"]
    assert n["precision_note"] == worksheet.SUB_CENT_NOTE

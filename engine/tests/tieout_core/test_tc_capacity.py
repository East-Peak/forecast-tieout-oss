"""Goal 2B: the capacity term. Created deals per ramped AE-month times the
ramped AE-months a roster is expected to supply, feeding Goal 1's deal size,
conversion and timing unchanged."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from engine.tests.tieout_core.builders import write_profile
from engine.tests.tieout_core.test_tc_backtest import AS_OF, regular_history
from engine.tieout_core.capacity import CapacityFit, fit_capacity, project
from engine.tieout_core.capacity_config import CapacityConfig
from engine.tieout_core.capacity_rules import DAYS_PER_AE_MONTH
from engine.tieout_core.fiscal import month_windows
from engine.tieout_core.fit import fit
from engine.tieout_core.forecast import model_forecast, simulate
from engine.tieout_core.history import as_known_at
from engine.tieout_core.load import load_profile
from engine.tieout_core.rates import ENTERED
from engine.tieout_core.roster import Member

CFG = CapacityConfig(
    quota_roles=("ae",), ramp=(Decimal("0.5"),), attrition=Decimal(0)
)  # a half-weight first month; nobody leaves


def ae(id, start, end=None):
    return Member(id, "ae", "mm", date.fromisoformat(start),
                  date.fromisoformat(end) if end else None, None)  # fmt: skip


@pytest.fixture(scope="module")
def profile(tmp_path_factory):
    return load_profile(write_profile(tmp_path_factory.mktemp("p")))


@pytest.fixture(scope="module")
def setup(profile):
    data = regular_history()
    model = fit(as_known_at(data, AS_OF), AS_OF, profile)
    windows = month_windows(AS_OF, date(2027, 6, 30))
    return data, model, windows


def capacity(members, cfg=CFG, cutoff=AS_OF, data=None):
    data = data or regular_history()
    return fit_capacity(data.deals, members, cutoff, data.deals[0].created, cfg)


def horizon(windows):
    return (windows[-1].end - AS_OF).days


def test_a_roster_that_reproduces_history_gives_exactly_the_flat_forecast(setup):
    # Five tenured reps, nobody leaving, the same roster through the trailing year
    # and the forecast year: the 365 trailing days held N deals over
    # 5 x 365 / 30.4375 ramped AE-months, so a ramped AE-month yields
    # N x 30.4375 / (5 x 365); five reps for a day yield 5 / 30.4375 of it: N / 365 a day.
    data, model, windows = setup
    members = [ae(f"A{i}", "2020-01-01") for i in range(5)]
    cap = capacity(members)
    assert cap.ramp.curve.source == ENTERED
    creation = project(cap, members, AS_OF, horizon(windows))
    assert all(
        abs(d - model.new_pipeline.created_per_day) < Decimal("1e-20")
        for d in creation.per_day
    )
    flat = model_forecast(model, data, AS_OF, windows)
    driven = model_forecast(model, data, AS_OF, windows, creation=creation)
    for w in windows:
        assert abs(driven.window_total(w.label) - flat.window_total(w.label)) < Decimal(
            "1e-9"
        )
    assert abs(driven.total() - flat.total()) < Decimal("1e-8")


def test_fewer_ramped_reps_gives_a_lower_forecast_and_more_a_higher_one(setup):
    data, model, windows = setup
    five = [ae(f"A{i}", "2020-01-01") for i in range(5)]
    cap = capacity(five)
    h = horizon(windows)

    def total(members):
        return model_forecast(
            model, data, AS_OF, windows, creation=project(cap, members, AS_OF, h)
        ).window_total("2026-12")

    base = total(five)
    one_leaves = [*five[:4], ae("A4", "2020-01-01", "2026-07-15")]  # a signed departure
    one_more = [*five, ae("NEW", "2026-07-01")]  # a signed hire
    assert total(one_leaves) < base < total(one_more)


def test_expected_attrition_decays_the_forward_roster_daily():
    # One tenured rep, 2% of an AE-month's heads leave per AE-month: the daily
    # survival is 0.98 ** (1 / 30.4375) and day t's creation is rate x s**t / 30.4375.
    members = [ae("A", "2020-01-01")]
    cfg = replace(CFG, attrition=Decimal("0.02"))
    cap = capacity(members, cfg)
    creation = project(cap, members, AS_OF, 400)
    s = Decimal(
        0.98 ** (1 / float(DAYS_PER_AE_MONTH))
    )  # computed independently, in floats
    for t in (1, 31, 365):
        expect = cap.rate * s**t / DAYS_PER_AE_MONTH
        assert abs(creation.per_day[t - 1] - expect) < Decimal("1e-12"), t
    assert creation.per_day[0] > creation.per_day[-1] > 0


def test_a_signed_hire_contributes_from_its_start_day_at_its_ramp_weight():
    # A hire signed to start 2026-07-16 (15 days after the as-of): nothing before
    # day 16, then tenure month 1 at weight 0.5 for a month, then 1.
    members = [ae("A", "2020-01-01"), ae("H", "2026-07-16")]
    cap = capacity(members[:1])
    creation = project(cap, members, AS_OF, 100)
    one = cap.rate / DAYS_PER_AE_MONTH  # one fully ramped rep for a day
    tol = Decimal("1e-20")
    assert abs(creation.per_day[14] - one) < tol  # 2026-07-15: just the tenured rep
    assert (
        abs(creation.per_day[15] - (one + one / 2)) < tol
    )  # 2026-07-16: the hire at 0.5
    assert abs(creation.per_day[15 + 31] - 2 * one) < tol  # 2026-08-16: ramped


def test_ramped_ae_months_beside_the_creation_are_the_expected_ones():
    members = [ae("A", "2020-01-01"), ae("H", "2026-07-16")]
    cap = capacity(members[:1])
    creation = project(cap, members, AS_OF, 40)
    tol = Decimal("1e-20")
    assert abs(creation.ramped_ae_months[0] - Decimal(1) / DAYS_PER_AE_MONTH) < tol
    assert abs(creation.ramped_ae_months[15] - Decimal("1.5") / DAYS_PER_AE_MONTH) < tol


def test_with_no_ramped_months_in_the_trailing_year_capacity_is_unavailable():
    cap = capacity([ae("A", "2027-01-01")])  # starts after everything
    assert isinstance(cap, CapacityFit) and cap.unavailable
    assert "no ramped AE-months" in cap.unavailable


def test_random_departures_in_the_ranges_are_centred_on_the_expectation():
    members = [ae(f"A{i}", "2020-01-01") for i in range(6)]
    cfg = replace(CFG, attrition=Decimal("0.05"))
    cap = capacity(members, cfg)
    creation = project(cap, members, AS_OF, 365)
    mat = creation.draws(np.random.default_rng(3), 4000)
    assert mat.shape == (4000, 365)
    expected = np.array([float(x) for x in creation.per_day])
    assert np.allclose(mat.mean(axis=0), expected, rtol=0.03)
    assert mat.std(axis=0)[-1] > 0  # the draws differ: departures are random


def test_the_simulation_with_capacity_stays_centred_on_its_expectation(setup):
    data, model, windows = setup
    members = [ae(f"A{i}", "2020-01-01") for i in range(5)]
    cap = capacity(members, replace(CFG, attrition=Decimal("0.03")))
    creation = project(cap, members, AS_OF, horizon(windows))
    expected = float(
        model_forecast(model, data, AS_OF, windows, creation=creation).total()
    )
    sim = simulate(model, data, AS_OF, windows, draws=3000, seed=1, creation=creation)
    assert abs(sim.total.mean - expected) < 0.04 * expected


# ---------------------------------------------------------------- review round: a plan with its error


def test_the_simulation_with_programme_inflows_is_centred_on_the_forecast_with_them(
    setup,
):
    from engine.tieout_core.forecast import Inflow

    data, model, windows = setup
    flows = (Inflow(0, 90, Decimal(2_000_000)), Inflow(90, 180, Decimal(1_000_000)))
    expected = float(model_forecast(model, data, AS_OF, windows, inflows=flows).total())
    plain = float(model_forecast(model, data, AS_OF, windows).total())
    assert expected > plain
    sim = simulate(model, data, AS_OF, windows, draws=4000, seed=2, inflows=flows)
    assert abs(sim.total.mean - expected) < 0.04 * expected
    base = simulate(model, data, AS_OF, windows, draws=4000, seed=2)
    assert sim.total.mean > base.total.mean  # the inflows are in the draws


# ---------------------------------------------------------------- heads and departures count the whole stay


def test_forward_heads_are_never_below_the_expected_ramped_weight_sum():
    # B started ten days before the as-of date and is still ramping: heads count the person for every
    # day of the stay, not only the days after the ramp ends.
    members = [ae("A", "2020-01-01"), ae("B", "2026-06-20")]
    cfg = replace(CFG, attrition=Decimal("0.02"))
    cap = capacity(members, cfg)
    creation = project(cap, members, AS_OF, 120)
    for day in range(120):
        assert creation.heads[day] >= creation.ramped_ae_months[
            day
        ] * DAYS_PER_AE_MONTH - Decimal("1e-20"), day


def test_heads_on_the_first_forward_day_are_the_roster_less_one_day_of_survival():
    members = [ae("A", "2020-01-01"), ae("B", "2026-06-20")]
    cfg = replace(CFG, attrition=Decimal("0.02"))
    cap = capacity(members, cfg)
    creation = project(cap, members, AS_OF, 60)
    s = Decimal(0.98 ** (1 / float(DAYS_PER_AE_MONTH)))
    assert abs(creation.heads[0] - 2 * s) < Decimal("1e-12")


def test_a_member_still_ramping_who_leaves_on_a_known_day_is_a_head_until_then():
    members = [ae("A", "2020-01-01"), ae("B", "2026-06-20", "2026-07-10")]
    cap = capacity(members, CFG)
    creation = project(cap, members, AS_OF, 30)
    assert creation.heads[0] == 2  # 2026-07-01
    assert creation.heads[9] == 2  # 2026-07-10, the last day
    assert creation.heads[10] == 1  # 2026-07-11


def test_departures_of_a_member_still_ramping_are_counted_over_the_whole_horizon():
    members = [ae("B", "2026-06-20")]
    cfg = replace(CFG, attrition=Decimal("0.02"))
    cap = capacity(members, cfg)
    days = 90
    creation = project(cap, members, AS_OF, days)
    s = Decimal(0.98 ** (1 / float(DAYS_PER_AE_MONTH)))
    assert abs(sum(creation.departures) - (1 - s**days)) < Decimal("1e-12")

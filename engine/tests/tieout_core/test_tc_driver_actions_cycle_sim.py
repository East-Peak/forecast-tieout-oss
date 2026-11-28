"""The paths of a plan with a cycle action: each win's lag and amount are drawn once, priced where
the win was to land, then moved. So under a change in cycle alone the same dollars are drawn on every
path, only booked in other months; the mean of the paths is the forward function's expectation; and
no path books below zero."""

from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, forecast
from engine.tieout_core import driver_actions as da
from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core.forecast import model_forecast, simulate
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import prepare
from engine.tieout_core.worksheet_rules import CYCLE_DAYS

D = Decimal
HIRES = [{"segment": "mid_market", "start": "2026-10", "count": 2}]
PROGRAMS = [{"name": "P", "pipeline": 3_000_000, "start": "2026-10"}]


@pytest.fixture(scope="module")
def state():
    with gen.in_repo():
        yield prepare(
            gen.PROFILES / "sapling-industries",
            gen.DATA / "sapling-industries",
            gen.AS_OF,
            400,
            0,
        )


@pytest.fixture(scope="module")
def flat():
    with gen.in_repo():
        yield prepare(
            gen.PROFILES / "mighty-oak-holdings",
            gen.DATA / "mighty-oak-holdings",
            gen.AS_OF,
            400,
            0,
        )


def lift_of(st, percent_of_cycle, slice="company", extra=(), **plan_kw):
    g = st.ground
    target = (wd.current_value(g, CYCLE_DAYS) * D(percent_of_cycle)).quantize(
        D("0.0001")
    )
    acts = [
        {"id": "c", "name": "c", "driver": "cycle_days", "slice": slice, "start": "2026-09",
         "ramp_months": 1, "target": str(target)},
        *extra,
    ]  # fmt: skip
    plan = parse_plan({"actions": acts, **plan_kw}, st.as_of, st.cap.members, "p")
    h, i = actions.plan_inputs(g, plan)
    return da.effect_for(st, plan, h, i).lift, h, i


def paths(st, lift, h, i, seed=1, draws=4000):
    g = st.ground
    creation = actions.Scenario(g).creation(h)
    return simulate(
        g.model, g.pop, g.as_of, g.windows, draws=draws, seed=seed,
        creation=creation, inflows=i, lift=lift,
    ).samples_total  # fmt: skip


def expected(st, lift, h, i):
    g = st.ground
    creation = actions.Scenario(g).creation(h)
    return model_forecast(
        g.model, g.pop, g.as_of, g.windows, creation=creation, inflows=i, lift=lift
    ).total()


def z_of(xs, want):
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
    return (m - float(want)) / (sd / len(xs) ** 0.5)


@pytest.mark.parametrize("ratio", ["0.5", "0.8", "1.25", "2"])
@pytest.mark.parametrize("slice", ["company", "enterprise"])
def test_the_mean_of_four_thousand_paths_is_the_expectation_where_the_capacity_term_is_adopted(
    state, ratio, slice
):
    lift, h, i = lift_of(state, ratio, slice, hires=HIRES, programs=PROGRAMS)
    assert abs(z_of(paths(state, lift, h, i), expected(state, lift, h, i))) <= 3.5


@pytest.mark.parametrize("ratio", ["0.5", "2"])
def test_and_where_creation_is_a_flat_rate(flat, ratio):
    lift, h, i = lift_of(flat, ratio)
    assert abs(z_of(paths(flat, lift, h, i), expected(flat, lift, h, i))) <= 3.5


def test_four_drivers_at_once_have_the_expected_mean(state):
    g = state.ground
    extra = [
        {"id": "w", "name": "w", "driver": "win_rate", "slice": "enterprise", "start": "2026-09",
         "ramp_months": 0, "target": str(g.model.new_pipeline.win_rate * D("1.3"))},
        {"id": "s", "name": "s", "driver": "won_arr", "slice": "company", "start": "2026-09",
         "ramp_months": 0, "target": str(g.model.new_pipeline.mean_won_arr * D("0.7"))},
        {"id": "p", "name": "p", "driver": "productivity", "slice": "mid_market", "start": "2026-10",
         "ramp_months": 0, "target": str(wd.current_value(g, "productivity") * D("1.8"))},
    ]  # fmt: skip
    lift, h, i = lift_of(state, "0.6", extra=extra, hires=HIRES, programs=PROGRAMS)
    assert abs(z_of(paths(state, lift, h, i), expected(state, lift, h, i))) <= 3.5


def test_no_path_books_below_zero_whatever_the_cycle(state):
    for ratio in ("0.5", "2"):
        lift, h, i = lift_of(state, ratio, hires=HIRES, programs=PROGRAMS)
        assert min(paths(state, lift, h, i, draws=1500)) >= 0


def test_under_a_change_in_cycle_alone_every_path_books_the_same_dollars_through_simulate(
    state,
):
    """Through the public route, with the same seed: two plans that both move landings (a cycle
    of 55% and of 90% of the pooled one) draw the same lags and amounts, so on every path the dollars
    booked are the same. The cohorts are the first twenty days' creation and the cycles only get
    shorter, so every win lands inside the twelve months and none is left out of the total; the
    existing pipeline is the same in both."""
    g = state.ground
    h, i = (), ()
    per_day = tuple(D("2") if t < 20 else D(0) for t in range(len(g.windows) * 31))
    creation = forecast.Creation(per_day, "twenty days of creation")

    def totals(ratio):
        lift, _, _ = lift_of(state, ratio)
        assert lift.cycle["enterprise"][20] != 0  # a real effect, landings do move
        return np.asarray(
            simulate(
                g.model, g.pop, g.as_of, g.windows, draws=300, seed=5,
                creation=creation, inflows=i, lift=lift,
            ).samples_total
        )  # fmt: skip

    short, shorter = totals("0.9"), totals("0.55")
    assert np.allclose(short, shorter, rtol=1e-12, atol=1e-6)
    assert short.min() > 0 and h == ()


def test_a_cycle_only_plan_and_the_same_plan_with_a_later_start_draw_the_same_dollars(
    state,
):
    g = state.ground
    per_day = tuple(D("2") if t < 20 else D(0) for t in range(len(g.windows) * 31))
    creation = forecast.Creation(per_day, "twenty days of creation")

    def totals(start):
        lift, _, _ = lift_of(state, "0.7")
        shifted = replace(
            lift,
            cycle={
                s: tuple(c if t >= start else 0 for t, c in enumerate(v))
                for s, v in lift.cycle.items()
            },
        )
        return np.asarray(
            simulate(
                g.model, g.pop, g.as_of, g.windows, draws=300, seed=5,
                creation=creation, inflows=(), lift=shifted,
            ).samples_total
        )  # fmt: skip

    assert np.allclose(totals(0), totals(10), rtol=1e-12, atol=1e-6)


def test_a_longer_cycle_leaves_dollars_beyond_the_months_a_shorter_one_brings_in(state):
    longer, _, _ = lift_of(state, "2", hires=HIRES)
    shorter, _, _ = lift_of(state, "0.5", hires=HIRES)
    assert (
        sum(longer.moved(k) for k in range(12))
        < 0
        < sum(shorter.moved(k) for k in range(12))
    )

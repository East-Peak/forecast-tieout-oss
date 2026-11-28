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


def test_under_a_change_in_cycle_alone_every_path_draws_the_same_dollars_and_only_books_them_elsewhere(
    state,
):
    """The same seed with and without the cycle change: the draws are coupled, so on every path the
    amounts drawn (before any is placed in a month, or beyond them) add up to the same dollars."""
    lift, h, _ = lift_of(state, "0.55", hires=HIRES, programs=PROGRAMS)
    g = state.ground
    new = g.model.new_pipeline
    span = len(lift.landing)
    creation = actions.Scenario(g).creation(h)
    organic = np.tile(np.asarray([float(x) for x in creation.per_day[:span]]), (60, 1))
    extra = np.zeros(span)
    deals = organic + extra

    def drawn(with_cycle):
        totals = np.zeros(60)
        placed = {"beyond": 0}
        the = lift if with_cycle else replace(lift, cycle={})

        def book(rows, landing, amounts):
            np.add.at(totals, rows, amounts)
            placed["beyond"] += int((landing > span + 400).sum())

        forecast._draw_lifted(
            np.random.default_rng(7), new, the, deals, span, book, organic, extra
        )
        return totals

    still, moved = drawn(False), drawn(True)
    assert np.allclose(
        still, moved, rtol=1e-12, atol=1e-6
    )  # the same dollars on every path
    assert still.sum() > 0


def test_a_longer_cycle_leaves_dollars_beyond_the_months_a_shorter_one_brings_in(state):
    longer, _, _ = lift_of(state, "2", hires=HIRES)
    shorter, _, _ = lift_of(state, "0.5", hires=HIRES)
    assert (
        sum(longer.moved(k) for k in range(12))
        < 0
        < sum(shorter.moved(k) for k in range(12))
    )

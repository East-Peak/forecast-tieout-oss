"""The fast placement of priced cohorts (cached rows, cuts of the plan's own timing kept across the
worksheet's flex) is the straightforward one: the same figures on the four-driver fixture plan, for
the plan's own timing and for the timings the worksheet's flex of the cycle makes."""

from decimal import Decimal
from fractions import Fraction

import pytest

from engine.scripts import generate_app_reports as gen
from engine.scripts.generate_editor_fixture import PLAN_WITH_FOUR
from engine.tieout_core import actions
from engine.tieout_core import driver_actions as da
from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core.editor import DATA, PROFILES
from engine.tieout_core.forecast import model_forecast
from engine.tieout_core.plan import parse_plan
from engine.tieout_core.report import prepare

D = Decimal
COMPANY = "sapling-industries"


@pytest.fixture(scope="module")
def world():
    with gen.in_repo():
        state = prepare(PROFILES / COMPANY, DATA / COMPANY, gen.AS_OF, 100, 0)
        plan = parse_plan(PLAN_WITH_FOUR, state.as_of, state.cap.members, "p")
        h, i = actions.plan_inputs(state.ground, plan)
        yield state, h, i, da.effect_for(state, plan, h, i).lift


def reference_cycle_units(lift, segment):
    """The placement worked out the plain way: every piece priced and placed one at a time."""
    transport = lift.transport
    out = [D(0)] * (len(transport.edges) + 1)
    price = lift.price.get(segment, {})
    count, organic = lift.counts(segment), lift.organic[segment]
    for t in lift.moved_days(segment):
        made, was = lift.day_units_of(segment, t, count[t], organic[t])
        cycle = lift.cycle.get(segment)
        f = (Fraction(cycle[t]) if cycle else Fraction(0)) + 1
        origin = lift.origin[t]
        for piece in transport.pieces(t + 1, f):
            out[piece.moved] += (
                made * piece.weight * price.get((piece.original, origin), D(1))
            )
        for piece in transport.pieces(t + 1, Fraction(1)):
            at = D(1) if transport.flexed else price.get((piece.original, origin), D(1))
            out[piece.flexed] -= was * piece.weight * at
    return out


@pytest.mark.parametrize(
    "scale", [None, Fraction(7, 10), Fraction(9, 10), Fraction(13, 10), Fraction(2)]
)
def test_the_fast_placement_is_the_plain_one_for_the_plans_timing_and_for_each_flex(
    world, scale
):
    state, _, _, lift = world
    g = state.ground
    if scale is not None:
        flexed = wd.with_cycle_scale(g, scale).model.new_pipeline.timing
        lift = lift.with_timing(flexed)
        assert lift.transport.flexed
    for segment in lift.changes:
        fast, plain = lift.cycle_units(segment), reference_cycle_units(lift, segment)
        assert all(abs(a - b) < D("1e-12") for a, b in zip(fast, plain)), segment


def test_the_forecast_of_a_flexed_plan_is_the_same_to_the_cent(world):
    state, h, i, lift = world
    g = state.ground
    creation = actions.Scenario(g).creation(h)
    for scale in (Fraction(8, 10), Fraction(15, 10)):
        adjusted = wd.with_cycle_scale(g, scale)
        flexed = lift.with_timing(adjusted.model.new_pipeline.timing)
        fast = model_forecast(
            adjusted.model,
            g.pop,
            g.as_of,
            g.windows,
            creation=creation,
            inflows=i,
            lift=flexed,
        )
        for (
            segment
        ) in flexed.changes:  # replace each segment's memoized units by the plain ones
            flexed._memo[("cycle", segment)] = reference_cycle_units(flexed, segment)
        plain = model_forecast(
            adjusted.model,
            g.pop,
            g.as_of,
            g.windows,
            creation=creation,
            inflows=i,
            lift=flexed,
        )
        for w in g.windows:
            a = sum(c[w.label] for c in fast.components.values())
            b = sum(c[w.label] for c in plain.components.values())
            assert abs(a - b) < D("0.001"), (scale, w.label)

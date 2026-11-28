"""A cycle action under the worksheet's own flex of the cycle. A win keeps the price of the atom it
was to land in with no action and no flex; the flex and the action each move where it lands. So the
months it adds up to come from the same priced cohorts the baseline does, and none goes below zero.

The case is small enough to do by hand. As of March 31; one lag of 20 days; every deal is won, at a
pooled size of 100; segment A's own size is three times B's. Deals created: April 15, A 0.1 and B 0.3;
May 15, A 1. Segment A's lag is doubled for deals created from May 1, then the worksheet flexes the
pooled lag to 10 days."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

import pytest

from engine.tieout_core import driver_actions as da
from engine.tieout_core.cycle import Transport
from engine.tieout_core.fiscal import FiscalYear, month_windows
from engine.tieout_core.fit import FitParams, Model, NewPipeline, Timing
from engine.tieout_core.forecast import Creation, Lift, model_forecast
from engine.tieout_core.lanes_basis import Sizes
from engine.tieout_core.rates import RateBook
from engine.tieout_core.records import Dataset

D = Decimal
CUT = date(2026, 3, 31)
WINDOWS = month_windows(
    CUT, date(2026, 6, 30)
)  # April, May, June: ends at days 30, 61, 91
DAYS = 91


def model(timing):
    return Model(
        cutoff=CUT, params=FitParams(), rates=RateBook(), cells={}, stage_rates={}, timings={},
        new_pipeline=NewPipeline(
            win_rate=D(1), timing=Timing(timing, "t"), mean_won_arr=D(100), mean_created_arr=D(100),
            created_per_day=D(0), won_arr_samples=(D(100),), cohort_size=10,
        ),
        unknown_stage_observations=0,
    )  # fmt: skip


def series(**by_day):
    out = [D(0)] * DAYS
    for day, n in by_day.items():
        out[int(day[1:]) - 1] = D(n)
    return out


A = series(d15="0.1", d45="1")
B = series(d15="0.3")
ZERO = [D(0)] * DAYS


def lift(cycle_a=True):
    g = SimpleNamespace(model=model((20,)), as_of=CUT, windows=WINDOWS)
    sizes = {"A": Sizes(D(300), "", D(100), ""), "B": Sizes(D(100), "", D(100), "")}
    landing, origin = da.day_cells(g, FiscalYear(date(2026, 1, 1)).start, DAYS)
    price = da.price_index(g, {"A": A, "B": B}, sizes, origin)
    start = (date(2026, 5, 1) - CUT).days - 1  # the index of May 1
    moves = [Fraction(0)] * start + [Fraction(1)] * (DAYS - start)
    return Lift(
        D(1), {"A": A, "B": B}, {"A": ZERO, "B": ZERO}, {"A": ZERO, "B": ZERO}, price,
        landing, origin, {}, {}, {"A": moves if cycle_a else [Fraction(0)] * DAYS, "B": [Fraction(0)] * DAYS},
        Transport(Timing((20,), "t"), [30, 61, 91]),
    )  # fmt: skip


def months(timing, with_lift):
    creation = Creation(tuple(a + b for a, b in zip(A, B)), "by hand")
    f = model_forecast(
        model(timing),
        Dataset((), (), None),
        CUT,
        WINDOWS,
        creation=creation,
        lift=with_lift,
    )
    return [sum((c[w.label] for c in f.components.values()), D(0)) for w in WINDOWS]


def test_with_no_flex_the_action_changes_nothing_a_month_here_the_lag_of_40_still_lands_in_june():
    assert months((20,), None) == [0, 40, 100]
    assert months((20,), lift()) == [0, 40, 100]


def test_under_a_flex_to_10_days_every_month_is_the_priced_cohorts_and_none_is_negative():
    """The flex alone lands the April 15 deals on April 25 (40) and the May 15 deal on May 25 (100).
    With the action, A's May 15 deal's lag is 10 doubled to 20 and it lands on June 4, still at the
    price of the June atom it was to land in (A alone there, so the pooled price): April 40, May 0,
    June 100 (not April 40, May -100, June 200)."""
    flexed = Timing((10,), "t")
    got = months((10,), lift().with_timing(flexed))
    assert months((10,), None) == [40, 100, 0]
    assert got == [40, 0, 100]


@pytest.mark.parametrize("lag", [1, 5, 10, 20, 40, 80])
@pytest.mark.parametrize("scale", [Fraction(1, 2), Fraction(3, 2), Fraction(2)])
def test_no_month_goes_negative_under_any_flex_with_a_cycle_action(lag, scale):
    flexed = Timing((lag,), "t")
    start = (date(2026, 5, 1) - CUT).days - 1
    moves = [Fraction(0)] * start + [scale - 1] * (DAYS - start)
    action = replace(lift(), cycle={"A": moves, "B": [Fraction(0)] * DAYS})
    got = months((lag,), action.with_timing(flexed))
    assert all(m >= 0 for m in got), (lag, scale, got)
    # the dollars are the cohorts' dollars: moved, not made or lost (the horizon aside)
    assert sum(got) <= D(100) * sum(A) + D(100) * sum(B) + D("1e-20")


def test_the_worksheets_own_step_hands_the_action_the_flexed_timing_and_keeps_the_prices():
    """``lift_under`` is what the worksheet's probe calls for every flex: the lift it returns places
    each sample by the flexed timing and prices it by the plan's own."""
    from engine.tieout_core import worksheet_drivers as wd

    def ground(timing):
        return SimpleNamespace(cap=SimpleNamespace(adopted=False), model=model(timing))

    plan_lift = lift()
    flexed = wd.lift_under(plan_lift, ground((20,)), ground((10,)))
    assert flexed.transport.flexed and flexed.transport.original.samples == (20,)
    assert flexed.price == plan_lift.price
    same = ground((20,))
    assert not wd.lift_under(plan_lift, same, same).transport.flexed

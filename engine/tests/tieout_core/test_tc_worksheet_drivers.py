"""The four operating drivers as pure overrides of the fitted records, and the solves behind
"needed alone", on a hand-built company whose answers can be written down."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core import worksheet_rules as rules
from engine.tieout_core.actions import Ground, Scenario
from engine.tieout_core.adoption import UNAVAILABLE, Adoption
from engine.tieout_core.capacity_config import RosterLoad
from engine.tieout_core.capacity_report import Capacity
from engine.tieout_core.fiscal import month_windows
from engine.tieout_core.fit import FitParams, Model, NewPipeline, Timing
from engine.tieout_core.forecast import Inflow, model_forecast
from engine.tieout_core.plan import NEXT_12, REST_OF_FY
from engine.tieout_core.rates import RateBook
from engine.tieout_core.records import Dataset, Deal

D = Decimal
AS_OF = date(2026, 8, 31)
FY_END = date(2026, 12, 31)
WINDOWS = month_windows(AS_OF, date(2027, 8, 31))
HORIZON = (WINDOWS[-1].end - AS_OF).days
SAMPLES = (30, 60)
OPEN = Deal(0, "X", "new_business", "mm", "S1", D(4000), date(2026, 8, 1), date(2026, 10, 15), False, False)  # fmt: skip


def ground(target=None, timing=SAMPLES, win_rate=None, won=None, created=None):
    target = D(10**9) if target is None else target
    win_rate = D("0.5") if win_rate is None else win_rate
    won = D(1000) if won is None else won
    created = D("0.1") if created is None else created
    new = NewPipeline(
        win_rate=win_rate, timing=Timing(timing, "t"), mean_won_arr=won, mean_created_arr=D(2000),
        created_per_day=created, won_arr_samples=(won,), cohort_size=10,
    )  # fmt: skip
    model = Model(
        cutoff=AS_OF, params=FitParams(), rates=RateBook(), cells={},
        stage_rates={"S1": D("0.5")}, timings={"S1": Timing((10, 40), "t")},
        new_pipeline=new, unknown_stage_observations=0,
    )  # fmt: skip
    cap = Capacity(None, RosterLoad((), (), {}, 0, "none"), Adoption(UNAVAILABLE, "none"), None, None, HORIZON, None)  # fmt: skip
    rest = [w.label for w in WINDOWS if w.end <= FY_END]
    labels = [w.label for w in WINDOWS]
    return Ground(
        cap, model, Dataset((OPEN,), (), None), AS_OF, WINDOWS, rest, labels, rest,
        D(0), target, date(2026, 2, 1), FY_END, None, D(0), D(10**9), HORIZON,
    )  # fmt: skip


def new_components(g, inflows=()):
    f = Scenario(g).forecast(inflows=inflows)
    return {
        w: f.components["future pipeline"][w]
        + f.components.get("added pipeline", {}).get(w, 0)
        for w in g.twelve_labels
    }


def by_hand(samples, created, per_deal, upto):
    """New-pipeline bookings booked by day offset ``upto``: each creation day t in 1..H
    creates ``created`` deals, each win lands t + sample days later."""
    n = len(samples)
    return sum(
        (created * per_deal / n) * sum(1 for d in samples if t + d <= upto)
        for t in range(1, HORIZON + 1)
    )  # fmt: skip


FY_DAYS = (FY_END - AS_OF).days


def test_the_baseline_matches_a_closed_form_by_hand():
    g = ground()
    got = sum(
        Scenario(g).forecast().components["future pipeline"][m] for m in g.rest_labels
    )
    assert got == by_hand(SAMPLES, D("0.1"), D("0.5") * 1000, FY_DAYS)


@pytest.mark.parametrize("driver", rules.DRIVERS)
def test_a_zero_change_reproduces_the_baseline_exactly(driver):
    g = ground()
    same = wd.with_setting(g, driver, wd.current_value(g, driver))
    assert Scenario(same).forecast() == Scenario(g).forecast()


@pytest.mark.parametrize(
    "driver,r",
    [
        (rules.WIN_RATE, D("1.4")),
        (rules.WON_ARR, D("0.8")),
        (rules.PRODUCTIVITY, D("1.5")),
    ],
)
def test_a_relative_change_moves_new_pipeline_bookings_by_exactly_that_much(driver, r):
    g = ground()
    changed = wd.with_setting(g, driver, wd.current_value(g, driver) * r)
    before, after = new_components(g), new_components(changed)
    for w in g.twelve_labels:
        assert after[w] == before[w] * r
    # open deals and actuals are untouched
    assert (
        Scenario(changed).forecast().components["existing pipeline"]
        == Scenario(g).forecast().components["existing pipeline"]
    )


def test_a_relative_change_applies_to_program_pipeline_too():
    g = ground()
    flows = (Inflow(10, 100, D(400_000)),)
    changed = wd.with_setting(g, rules.WIN_RATE, D("0.25"))
    before, after = new_components(g, flows), new_components(changed, flows)
    # (program dollars become deals by division, so equal to the last decimal place carried)
    assert all(abs(after[w] - before[w] / 2) < D("1e-18") for w in before)
    assert sum(before.values()) > 0


def test_win_rate_is_clipped_at_one():
    g = ground()
    assert wd.with_setting(g, rules.WIN_RATE, D(7)).model.new_pipeline.win_rate == D(1)
    assert wd.with_setting(g, rules.WIN_RATE, D(-1)).model.new_pipeline.win_rate == D(0)


def test_overrides_return_copies_and_never_touch_the_original():
    g = ground()
    snapshot = (g.model.new_pipeline, g.cap)
    for driver in rules.DRIVERS:
        wd.with_setting(g, driver, wd.current_value(g, driver) / 2)
    assert (g.model.new_pipeline, g.cap) == snapshot


def test_productivity_without_the_capacity_term_is_organic_deals_per_day():
    g = ground(created=D("0.1"))
    assert wd.current_value(g, rules.PRODUCTIVITY) == D("0.1")
    assert wd.with_setting(
        g, rules.PRODUCTIVITY, D("0.3")
    ).model.new_pipeline.created_per_day == D("0.3")


def test_cycle_is_the_weighted_mean_and_a_setting_scales_every_sample_up_to_whole_days():
    g = ground(timing=(30, 60, 60))
    assert wd.current_value(g, rules.CYCLE_DAYS) == D(50)
    half = wd.with_cycle_scale(g, Fraction(1, 2)).model.new_pipeline.timing
    assert half.samples == (15, 30, 30)
    by_setting = wd.with_setting(g, rules.CYCLE_DAYS, D(25)).model.new_pipeline.timing
    assert by_setting.samples == (15, 30, 30)
    assert wd.with_cycle_scale(
        ground(timing=(30, 61)), Fraction(1, 2)
    ).model.new_pipeline.timing.samples == (15, 31)


def test_cycle_mean_follows_the_weights():
    t = Timing((10, 20), "t", (D(3), D(1)))
    assert wd.timing_mean(t) == D("12.5")


def test_cycle_shortening_pulls_bookings_earlier_and_lengthening_pushes_them_out():
    g = ground()
    base = sum(new_components(g)[m] for m in g.rest_labels)
    faster = sum(
        new_components(wd.with_cycle_scale(g, Fraction(1, 2)))[m] for m in g.rest_labels
    )
    slower = sum(
        new_components(wd.with_cycle_scale(g, Fraction(3, 2)))[m] for m in g.rest_labels
    )
    assert faster > base > slower
    assert faster == by_hand((15, 30), D("0.1"), D(500), FY_DAYS)


def test_a_probe_measures_around_the_scenario_in_force():
    g = ground()
    hire_flows = (Inflow(10, 100, D(400_000)),)
    alone, planned = wd.Probe(g), wd.Probe(g, inflows=hire_flows)
    change = lambda p: p.change(
        p.forecast(wd.with_setting(g, rules.WIN_RATE, D("0.6")))
    )
    assert change(planned)[REST_OF_FY] > change(alone)[REST_OF_FY] > 0
    assert set(change(alone)) == {REST_OF_FY, NEXT_12}


def test_the_probes_figures_are_what_a_shown_total_is_in_the_report():
    g = ground()
    p = wd.Probe(g)
    f = Scenario(g).forecast()
    assert p.shown(f) == Scenario(g).bookings(f)
    assert p.fiscal_year(f) == Scenario(g).fiscal_year(f)


# ----------------------------------------------------------------- the solves


def affine(a, b):
    return lambda v: a + b * v


def test_the_linear_solve_finds_the_exact_value():
    # fy(v) = 100 + 50 v; target 400 needs v = 6
    r = wd.solve_linear(affine(D(100), D(50)), D(2), D(400), upper=None)
    assert (r.outcome, r.value, r.achieved) == (wd.SOLVES, D(6), D(400))


def test_the_linear_solve_works_from_a_current_of_zero():
    r = wd.solve_linear(affine(D(100), D(50)), D(0), D(400), upper=None)
    assert (r.outcome, r.value) == (wd.SOLVES, D(6))


def test_already_at_or_ahead_of_target_needs_nothing():
    r = wd.solve_linear(affine(D(500), D(50)), D(2), D(400), upper=None)
    assert (r.outcome, r.value, r.achieved) == (wd.COVERED, D(2), D(600))


def test_a_bounded_driver_that_cannot_reach_the_target_says_so_with_what_it_does_reach():
    # a win rate: fy(v) = 100 + 300 v, v at most 1, target 1000 needs v = 3
    r = wd.solve_linear(affine(D(100), D(300)), D("0.2"), D(1000), upper=D(1))
    assert (r.outcome, r.reason, r.value, r.achieved) == (
        wd.CANNOT,
        wd.BOUNDED_AT_ONE,
        D(1),
        D(400),
    )


def test_a_bounded_driver_that_can_reach_the_target_solves():
    r = wd.solve_linear(affine(D(100), D(300)), D("0.2"), D(250), upper=D(1))
    assert (r.outcome, r.value, r.achieved) == (wd.SOLVES, D("0.5"), D(250))


def test_a_driver_already_at_its_bound_cannot_close_alone():
    r = wd.solve_linear(affine(D(100), D(300)), D(1), D(1000), upper=D(1))
    assert (r.outcome, r.reason) == (wd.CANNOT, wd.BOUNDED_AT_ONE)


def test_a_driver_with_no_effect_in_the_year_cannot_close_alone():
    r = wd.solve_linear(affine(D(100), D(0)), D(2), D(400), upper=None)
    assert (r.outcome, r.reason, r.achieved) == (wd.CANNOT, wd.NO_EFFECT, D(100))


def test_the_linear_solve_on_the_real_forward_function_lands_on_the_target():
    g = ground()
    p = wd.Probe(g)
    base = p.fiscal_year(p.base)
    target = base + D(5000)
    for driver in (rules.WON_ARR, rules.PRODUCTIVITY):
        cur = wd.current_value(g, driver)
        r = wd.solve_linear(
            lambda v, d=driver: p.fiscal_year(p.forecast(wd.with_setting(g, d, v))),
            cur,
            target,
            None,
        )
        assert r.outcome == wd.SOLVES and abs(r.achieved - target) < D("0.000001")


def steps_for(samples):
    """Every scale at which a rounded day changes, found the long way: all k / d."""
    return sorted(
        {Fraction(k, d) for d in samples for k in range(d + 1)}
        | {Fraction(0), Fraction(1)}
    )


def fy_by_scale(g, scale):
    p = wd.Probe(g)
    return p.fiscal_year(p.forecast(wd.with_cycle_scale(g, scale)))


def test_the_cycle_solve_returns_the_largest_scale_that_reaches_the_target_and_its_overshoot():
    g = ground(timing=(30, 60))
    p = wd.Probe(g)
    steps = steps_for(SAMPLES)
    values = {s: fy_by_scale(g, s) for s in steps}
    # choose a target that the 1/2 scale reaches and nothing larger does
    target = values[Fraction(1, 2)] - D("0.01")
    best = max(s for s, v in values.items() if v >= target)
    r = wd.solve_cycle(
        lambda s: p.fiscal_year(p.forecast(wd.with_cycle_scale(g, s))), SAMPLES, target
    )
    assert (r.outcome, r.scale) == (wd.SOLVES, best)
    assert r.achieved == values[best] and r.overshoot == values[best] - target
    # the next scale up misses
    assert values[min(s for s in steps if s > best)] < target


def test_a_target_met_at_zero_days_only_is_still_a_solve_at_scale_zero():
    g = ground(timing=(30, 60))
    p = wd.Probe(g)
    target = fy_by_scale(g, Fraction(0))
    r = wd.solve_cycle(
        lambda s: p.fiscal_year(p.forecast(wd.with_cycle_scale(g, s))), SAMPLES, target
    )
    assert r.outcome == wd.SOLVES and r.scale == Fraction(0)


def test_a_company_that_cannot_close_on_cycle_even_at_zero_days_says_so():
    g = ground(timing=(30, 60))
    p = wd.Probe(g)
    zero = fy_by_scale(g, Fraction(0))
    r = wd.solve_cycle(
        lambda s: p.fiscal_year(p.forecast(wd.with_cycle_scale(g, s))),
        SAMPLES,
        zero + 1,
    )
    assert (r.outcome, r.reason, r.scale, r.achieved) == (
        wd.CANNOT,
        wd.ZERO_DAYS_SHORT,
        Fraction(0),
        zero,
    )


def test_cycle_already_ahead_needs_nothing():
    g = ground(timing=(30, 60))
    p = wd.Probe(g)
    base = p.fiscal_year(p.base)
    r = wd.solve_cycle(
        lambda s: p.fiscal_year(p.forecast(wd.with_cycle_scale(g, s))),
        SAMPLES,
        base - 1,
    )
    assert (r.outcome, r.scale) == (wd.COVERED, Fraction(1))


def test_model_forecast_is_what_the_probe_runs():
    g = ground()
    assert Scenario(g).forecast() == model_forecast(g.model, g.pop, g.as_of, g.windows)
    assert replace(g).model is g.model


def test_a_probe_gives_what_the_whole_forward_function_gives_for_every_driver():
    g = ground()
    flows = (Inflow(10, 100, D(400_000)),)
    p = wd.Probe(g, inflows=flows)
    for driver in rules.DRIVERS:
        adjusted = wd.with_setting(g, driver, wd.current_value(g, driver) * D("0.7"))
        assert p.forecast(adjusted) == Scenario(adjusted).forecast(inflows=flows)


def test_the_cycle_solve_agrees_with_a_search_of_every_step_for_many_targets():
    """The expected values come from first principles (``by_hand`` in the first-principles
    tests), never through ``Probe`` or ``Scenario``; only the solve itself runs the model."""
    from engine.tests.tieout_core import test_tc_worksheet_first_principles as fp

    samples = (30, 45, 60, 90)
    g = fp.build(samples)
    rest = {w.label for w in WINDOWS if w.end <= FY_END}

    def hand(s):
        days = rules.scaled_days(samples, s)
        out = fp.by_hand(days, None, lambda t: Fraction(1, 5), 1000, Fraction(1, 2))
        return sum((v for k, v in out.items() if k in rest), Fraction(0))

    values = {s: hand(s) for s in steps_for(samples)}
    low, high = min(values.values()), max(values.values())
    p = wd.Probe(g)
    for k in range(1, 12):
        target = low + (high - low) * k / 12
        best = max(s for s, v in values.items() if v >= target)
        r = wd.solve_cycle(
            lambda s: p.fiscal_year(p.forecast(wd.with_cycle_scale(g, s))),
            samples,
            D(target.numerator) / D(target.denominator),
        )
        assert r.outcome in (wd.SOLVES, wd.COVERED)
        assert r.scale == best


def test_a_solution_is_rounded_up_to_the_places_the_driver_is_written_to_and_reaches_the_target():
    # fy(v) = 100 + 300 v; the exact root for a target of 250 is 0.5, for 251 it is 0.50333..
    fy = affine(D(100), D(300))
    exact = wd.solve_linear(fy, D("0.2"), D(251), upper=D(1))
    r = wd.round_solution(fy, exact, rules.WIN_RATE, D(251), D(1))
    assert r.value == D("0.5034") and r.achieved == D(100) + D(300) * D("0.5034")
    assert r.achieved >= 251 and r.overshoot == r.achieved - 251
    # entering the number as written reaches the target; entering it rounded down would not
    assert fy(D("0.5033")) < 251


def test_a_solution_that_is_already_on_its_places_is_not_moved():
    fy = affine(D(100), D(50))
    r = wd.round_solution(
        fy, wd.solve_linear(fy, D(2), D(400), None), rules.WON_ARR, D(400)
    )
    assert r.value == D(6) and r.overshoot == 0


def test_dollars_round_up_to_the_cent_and_ratios_to_four_places():
    fy = affine(D(0), D(1))
    r = wd.round_solution(
        fy, wd.Needed(wd.SOLVES, D("12.3401"), D(0)), rules.WON_ARR, D("12.3401")
    )
    assert r.value == D("12.35")
    r = wd.round_solution(
        fy, wd.Needed(wd.SOLVES, D("2.12341"), D(0)), rules.PRODUCTIVITY, D("2.12341")
    )
    assert r.value == D("2.1235")


def test_other_outcomes_pass_through_a_rounding_untouched():
    cannot = wd.Needed(wd.CANNOT, D(1), D(5), wd.BOUNDED_AT_ONE)
    assert wd.round_solution(lambda v: v, cannot, rules.WIN_RATE, D(9), D(1)) is cannot


def test_a_driver_that_moves_bookings_by_less_than_rounding_has_no_effect_not_a_huge_solve():
    """With actions in force a driver's effect can cancel to the last digits; the solve must not
    divide the gap by that noise."""
    from decimal import Decimal

    from engine.tieout_core import worksheet_drivers as wd

    noise = Decimal("1e-20")
    got = wd.solve_linear(
        lambda v: Decimal(100) + noise * v, Decimal(2), Decimal(200), None
    )
    assert (got.outcome, got.reason) == (wd.CANNOT, wd.NO_EFFECT)

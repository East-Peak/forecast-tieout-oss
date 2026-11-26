from decimal import Decimal

from engine.tests.tieout_core.test_tc_forecast import CUT, MODEL, ONLY_X, WINDOWS
from engine.tieout_core.forecast import model_forecast
from engine.tieout_core.lever import (
    COVERED,
    FEASIBLE,
    UNREACHABLE,
    solve_added_pipeline,
)


def linear(base, slope):
    return lambda x: Decimal(base) + Decimal(slope) * x


def test_target_already_covered():
    r = solve_added_pipeline(linear(100, "0.25"), Decimal(90), cap=Decimal(1000))
    assert (r.outcome, r.required) == (COVERED, Decimal(0))


def test_feasible_target_is_hit_to_the_cent():
    r = solve_added_pipeline(linear(100, "0.25"), Decimal(200), cap=Decimal(1000))
    assert (r.outcome, r.required, r.achieved) == (
        FEASIBLE,
        Decimal("400.00"),
        Decimal(200),
    )


def test_required_pipeline_rounds_up_to_the_next_cent():
    r = solve_added_pipeline(linear(100, "0.25"), Decimal("100.003"), cap=Decimal(1000))
    assert r.required == Decimal("0.02")
    assert Decimal(0) <= r.achieved - Decimal("100.003") <= Decimal("0.01")


def test_beyond_the_cap_is_unreachable():
    r = solve_added_pipeline(linear(100, "0.25"), Decimal(200), cap=Decimal(300))
    assert r.outcome == UNREACHABLE
    assert r.required == Decimal("400.00")  # what it would take, shown for context
    assert r.achieved == Decimal(175)  # what the cap reaches


def test_no_time_left_is_unreachable():
    r = solve_added_pipeline(linear(100, 0), Decimal(200), cap=Decimal(300))
    assert (r.outcome, r.required) == (UNREACHABLE, None)


def test_forward_and_inverse_agree_to_the_cent_through_the_model():
    def forward(x):
        return model_forecast(MODEL, ONLY_X, CUT, WINDOWS, added_pipeline=x).total()

    target = forward(Decimal(0)) + Decimal("123.45")
    r = solve_added_pipeline(forward, target, cap=Decimal(10**6))
    assert r.outcome == FEASIBLE
    assert abs(forward(r.required) - target) <= Decimal("0.01")
    assert abs(forward(r.required - Decimal("0.01")) - target) <= Decimal("0.01")

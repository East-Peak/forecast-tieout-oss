"""Goal 2B section 10: required against expected pipeline, by quarter.

One deterministic solve in quarter order. For each remaining quarter with a
target: the extra pipeline that must be created, spread evenly from the as-of
date (or the previous quarter's end) to that quarter's end, to meet its target
given actuals, existing pipeline and what earlier quarters were already
assigned. Covered, required $X, or unreachable within the cap; an unreachable
quarter is assigned nothing and the next is solved from there."""

from datetime import date
from decimal import Decimal

import pytest

from engine.tests.tieout_core.builders import write_profile
from engine.tests.tieout_core.test_tc_backtest import AS_OF, regular_history
from engine.tieout_core.fiscal import FiscalYear, month_windows
from engine.tieout_core.fit import fit
from engine.tieout_core.forecast import model_forecast
from engine.tieout_core.history import as_known_at
from engine.tieout_core.lever import COVERED, FEASIBLE, UNREACHABLE
from engine.tieout_core.load import load_profile
from engine.tieout_core.requirement import solve_quarters, summarise_history

FY = FiscalYear(date(2026, 2, 1))
CENT = Decimal("0.01")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    profile = load_profile(write_profile(tmp_path_factory.mktemp("p")))
    data = regular_history()
    model = fit(as_known_at(data, AS_OF), AS_OF, profile)
    windows = month_windows(AS_OF, date(2027, 6, 30))
    return data, model, windows


def quarters(**targets):
    return {q: (FY.quarter_window(q), Decimal(t)) for q, t in targets.items()}


def solve(world, targets, cap=Decimal(10**9), actual=None):
    data, model, windows = world
    return solve_quarters(
        model, data, AS_OF, windows, quarters(**targets), actual or {}, None, cap
    )


def quarter_bookings(world, label_months, inflows):
    data, model, windows = world
    f = model_forecast(model, data, AS_OF, windows, inflows=inflows)
    return sum((f.window_total(m) for m in label_months), Decimal(0))


def test_a_quarter_the_forecast_already_meets_is_covered_and_assigned_nothing(world):
    r = solve(world, {"Q3FY26": 1})
    assert r[0].outcome == COVERED and r[0].required == 0


def test_the_current_quarter_cannot_be_helped_by_pipeline_that_books_after_it_ends(
    world,
):
    # As of 2026-06-30 Q2 ends 2026-07-31. Pipeline created in July books 45 days
    # later, in mid-August to mid-September: nothing can land inside Q2.
    r = solve(world, {"Q2FY26": 10**12})
    assert r[0].outcome == UNREACHABLE and r[0].required is None


def test_the_inverse_by_hand_the_share_of_the_pipeline_that_lands_in_the_quarter(world):
    # Q3FY26 is 2026-08-01..2026-10-31. Each deal books exactly 45 days after it is
    # created (win rate 1, size unchanged), and the piece is spread in equal thirds
    # over the August, September and October windows. Created in August: booked
    # 2026-09-15 to 2026-10-15, all inside. Created in September: booked
    # 2026-10-16 to 2026-11-14, inside up to 2026-10-31: the first 16 of 30 days.
    # October's pipeline books after the quarter. So the share landing in Q3 is
    # 1/3 + (1/3)(16/30) = 46/90 of the dollars added.
    target = Decimal(10**6)
    q2, q3 = solve(
        world, {"Q2FY26": 1, "Q3FY26": target}
    )  # Q2 is covered: it ends at 07-31
    assert q2.outcome == COVERED and q3.piece == (date(2026, 7, 31), date(2026, 10, 31))
    base = quarter_bookings(world, ["2026-08", "2026-09", "2026-10"], [])
    assert q3.outcome == FEASIBLE
    assert abs(q3.required * Decimal(46) / Decimal(90) - (target - base)) <= CENT
    assert abs(q3.forecast_without - base) < Decimal("1e-9")
    assert abs(q3.forecast_with - target) <= CENT


def test_forward_and_inverse_agree_to_the_cent_for_every_feasible_quarter(world):
    r = solve(world, {"Q3FY26": 3 * 10**6, "Q4FY26": 6 * 10**6})
    assert [x.outcome for x in r] == [FEASIBLE, FEASIBLE]
    inflows = [f for x in r for f in x.inflows]
    for x, labels in zip(
        r, (["2026-08", "2026-09", "2026-10"], ["2026-11", "2026-12", "2027-01"])
    ):
        assert abs(quarter_bookings(world, labels, inflows) - x.target) <= CENT


def test_an_earlier_quarters_pipeline_lowers_what_the_next_quarter_needs(world):
    both = solve(world, {"Q3FY26": 3 * 10**6, "Q4FY26": 6 * 10**6})
    alone = solve(world, {"Q4FY26": 6 * 10**6})
    assert both[1].required < alone[0].required  # Q3's pipeline also books in Q4


def test_an_unreachable_quarter_is_assigned_nothing_and_the_next_is_solved_from_there(
    world,
):
    # Q3 cannot be met within the cap, so it is assigned nothing; Q4 is then solved
    # exactly as if Q3 had been covered with no pipeline of its own: its pipeline is
    # spread from Q3's end, and nothing from Q3 books in it.
    unreachable = solve(
        world, {"Q3FY26": 10**12, "Q4FY26": 6 * 10**6}, cap=Decimal(10**9)
    )
    covered = solve(world, {"Q3FY26": 1, "Q4FY26": 6 * 10**6}, cap=Decimal(10**9))
    assert [x.outcome for x in unreachable] == [UNREACHABLE, FEASIBLE]
    assert unreachable[0].assigned == 0 and covered[0].assigned == 0
    assert unreachable[1].required == covered[1].required
    assert (
        unreachable[1].piece
        == covered[1].piece
        == (date(2026, 10, 31), date(2027, 1, 31))
    )
    assert all(x.assigned == 0 for x in solve(world, {"Q3FY26": 10**9}, cap=Decimal(1)))


def test_the_cap_is_one_cap_across_quarters(world):
    r = solve(world, {"Q3FY26": 3 * 10**6, "Q4FY26": 6 * 10**6})
    cap = r[0].required + Decimal(1)  # room for the first quarter and a dollar more
    tight = solve(world, {"Q3FY26": 3 * 10**6, "Q4FY26": 6 * 10**6}, cap=cap)
    assert tight[0].outcome == FEASIBLE and tight[1].outcome == UNREACHABLE


def test_actual_bookings_to_date_count_toward_the_quarter(world):
    without = solve(world, {"Q3FY26": 3 * 10**6})
    with_actual = solve(world, {"Q3FY26": 3 * 10**6}, actual={"Q3FY26": Decimal(10**6)})
    assert with_actual[0].required < without[0].required


def test_closed_quarters_are_left_out(world):
    r = solve(world, {"Q1FY26": 10**6, "Q3FY26": 10**6})
    assert [x.quarter for x in r] == ["Q3FY26"]


def test_history_by_ramped_ae_month_gives_the_median_and_the_best_four_quarter_average():
    # Created dollars and ramped AE-months per quarter: 10, 20, 30, 40, 5, 6 a month.
    # Median of 5, 6, 10, 20, 30, 40 = (10 + 20) / 2 = 15.
    # Four-quarter averages: (100+200+300+400)/40 = 25; (200+300+400+50)/40 = 23.75;
    # (300+400+50+60)/40 = 20.25. The best is 25.
    quarters_ = [(Decimal(c), Decimal(10)) for c in (100, 200, 300, 400, 50, 60)]
    s = summarise_history(quarters_)
    assert s.quarters == 6 and s.median == Decimal(15) and s.best_four == Decimal(25)


def test_fewer_than_four_quarters_has_a_median_but_no_best_four():
    s = summarise_history([(Decimal(10), Decimal(1)), (Decimal(30), Decimal(1))])
    assert s.median == Decimal(20) and s.best_four is None
    assert summarise_history([]).median is None

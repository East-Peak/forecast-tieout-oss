"""Goal 2B section 10: required against expected pipeline, by quarter.

One deterministic solve in quarter order. For each remaining quarter with a
target: the extra pipeline that must be created, spread evenly from the day
after the as-of date (Goal 2C: creation starts now, not at the previous
quarter's end) to that quarter's end, to meet its target given actuals,
existing pipeline and what earlier quarters were already assigned. Covered,
required $X, or unreachable within the cap; an unreachable quarter is assigned
nothing and the next is solved from there."""

from datetime import date
from decimal import Decimal

import pytest

from engine.tests.tieout_core.builders import write_profile
from engine.tests.tieout_core.test_tc_backtest import AS_OF, regular_history
from engine.tieout_core.fiscal import FiscalYear, month_windows
from engine.tieout_core.fit import fit
from engine.tieout_core.forecast import EXISTING, Inflow, model_forecast
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


def test_the_schedule_by_hand_creation_starts_the_day_after_the_as_of(world):
    # As of 2026-06-30, Q3FY26 is 2026-08-01..2026-10-31. Its pipeline is created
    # evenly on every day from 2026-07-01 to 2026-10-31: 31 + 31 + 30 + 31 = 123
    # days. Each deal books exactly 45 days after creation (win rate 1, size
    # unchanged), so it lands in Q3 when created on 2026-06-17..2026-09-16; of the
    # creation days that is 07-01..09-16 = 31 + 31 + 16 = 78 of 123. So 78/123 of
    # the dollars created book in the quarter. To close a shortfall of $780,000 the
    # quarter needs 780,000 * 123 / 78 = $1,230,000 of pipeline.
    base = quarter_bookings(world, ["2026-08", "2026-09", "2026-10"], [])
    q2, q3 = solve(world, {"Q2FY26": 1, "Q3FY26": base + 780_000})
    assert q2.outcome == COVERED
    assert q3.outcome == FEASIBLE and q3.piece == (AS_OF, date(2026, 10, 31))
    assert abs(q3.required - Decimal(1_230_000)) <= CENT
    assert abs(q3.forecast_without - base) < Decimal("1e-9")
    assert abs(q3.forecast_with - (base + 780_000)) <= CENT
    assert abs(q3.yield_per_dollar - Decimal(78) / Decimal(123)) < Decimal("1e-12")
    assert q3.inflows == (Inflow(0, 123, q3.required),)  # one even schedule, day 1..123


def test_two_quarters_by_hand_an_earlier_assignment_is_counted_once(world):
    # Q3 as above: $1,230,000 created 07-01..10-31 (123 days).
    # Q4FY26 is 2026-11-01..2027-01-31; a deal created on d lands in it when d is
    # 2026-09-17..2026-12-17. Q3's schedule puts 1,230,000 / 123 = $10,000 a day on
    # 09-17..10-31 = 14 + 31 = 45 days, so $450,000 of Q3's pipeline books in Q4,
    # once. Q4's own pipeline is created on every day 07-01..01-31 = 31 + 31 + 30 +
    # 31 + 30 + 31 + 31 = 215 days, of which 09-17..12-17 = 14 + 31 + 30 + 17 = 92
    # land in Q4: 92/215 of it. A Q4 target $450,000 + $920,000 over its base
    # therefore needs 920,000 * 215 / 92 = $2,150,000 of its own.
    q3_labels, q4_labels = (
        ["2026-08", "2026-09", "2026-10"],
        ["2026-11", "2026-12", "2027-01"],
    )
    base3 = quarter_bookings(world, q3_labels, [])
    base4 = quarter_bookings(world, q4_labels, [])
    q3, q4 = solve(
        world, {"Q3FY26": base3 + 780_000, "Q4FY26": base4 + 450_000 + 920_000}
    )
    assert abs(q3.required - Decimal(1_230_000)) <= CENT
    assert abs(q4.required - Decimal(2_150_000)) <= CENT
    assert abs(q4.forecast_without - (base4 + 450_000)) <= CENT  # counted once
    assert q4.piece == (AS_OF, date(2027, 1, 31))
    assert abs(q4.yield_per_dollar - Decimal(92) / Decimal(215)) < Decimal("1e-12")
    assert q4.inflows == (Inflow(0, 215, q4.required),)


def test_the_yield_is_shown_for_a_quarter_nothing_can_help(world):
    # Q2FY26 ends 2026-07-31; pipeline created from 07-01 books from 08-15.
    r = solve(world, {"Q2FY26": 10**12})
    assert r[0].outcome == UNREACHABLE and r[0].yield_per_dollar == 0


def test_the_open_pipeline_and_what_it_is_expected_to_book(world):
    # Four open deals of $100 (created 05-26, 06-05, 06-15 and 06-25) = $400.
    data, model, windows = world
    r = solve(world, {"Q3FY26": 10**6})[0]
    assert r.open_arr == Decimal(400)
    f = model_forecast(model, data, AS_OF, windows)
    in_q3 = sum(
        (f.components[EXISTING][m] for m in ("2026-08", "2026-09", "2026-10")),
        Decimal(0),
    )
    assert r.open_expected == in_q3 and 0 < in_q3 < 400


def test_forward_and_inverse_agree_to_the_cent_for_every_feasible_quarter(world):
    # Each quarter is solved after the ones before it, so its target is met by the
    # schedules up to and including its own; a later quarter's pipeline, created
    # from the same as-of date, also books in it and can only add.
    r = solve(world, {"Q3FY26": 3 * 10**6, "Q4FY26": 6 * 10**6})
    assert [x.outcome for x in r] == [FEASIBLE, FEASIBLE]
    labels = (["2026-08", "2026-09", "2026-10"], ["2026-11", "2026-12", "2027-01"])
    for i, (x, months) in enumerate(zip(r, labels)):
        so_far = [f for y in r[: i + 1] for f in y.inflows]
        assert abs(quarter_bookings(world, months, so_far) - x.target) <= CENT
    everything = [f for y in r for f in y.inflows]
    assert quarter_bookings(world, labels[0], everything) > r[0].target + CENT


def test_an_earlier_quarters_pipeline_lowers_what_the_next_quarter_needs(world):
    both = solve(world, {"Q3FY26": 3 * 10**6, "Q4FY26": 6 * 10**6})
    alone = solve(world, {"Q4FY26": 6 * 10**6})
    assert both[1].required < alone[0].required  # Q3's pipeline also books in Q4


def test_an_unreachable_quarter_is_assigned_nothing_and_the_next_is_solved_from_there(
    world,
):
    # Q3 cannot be met within the cap, so it is assigned nothing; Q4 is then solved
    # exactly as if Q3 had been covered with no pipeline of its own: nothing from
    # Q3 books in it.
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
        == (AS_OF, date(2027, 1, 31))  # creation starts now, not at Q3's end
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


# ---------------------------------------------------------------- review round: one total, honestly named


def _fake(quarter, outcome, required, target=1000):
    from engine.tieout_core.requirement import QuarterResult

    return QuarterResult(
        quarter, "not started", Decimal(target), Decimal(0), outcome, required,
        required or Decimal(0), Decimal(10**9), Decimal(0), Decimal(0),
        (date(2026, 7, 31), date(2026, 10, 31)), (), Decimal(0), None,
    )  # fmt: skip


def test_the_total_is_for_every_quarter_when_all_are_solvable():
    from engine.tieout_core.pipeline_report import summarise_fiscal_year

    s = summarise_fiscal_year(
        [_fake("Q3FY26", COVERED, Decimal(0)), _fake("Q4FY26", FEASIBLE, Decimal(500))],
        ("Q3FY26", "Q4FY26"),
    )
    assert s["solvable_total"] == "500.00" and s["unreachable_quarters"] == []
    assert s["headline"].startswith(
        "$500.00 of extra pipeline to meet every remaining quarter"
    )


def test_a_partial_total_names_the_unreachable_quarters_and_never_reads_as_solved():
    from engine.tieout_core.pipeline_report import summarise_fiscal_year

    s = summarise_fiscal_year(
        [_fake("Q3FY26", UNREACHABLE, None), _fake("Q4FY26", FEASIBLE, Decimal(500))],
        ("Q3FY26", "Q4FY26"),
    )
    assert s["headline"].startswith(
        "partial: 1 of 2 quarters solvable (unreachable: Q3FY26)"
    )
    none = summarise_fiscal_year(
        [
            _fake("Q3FY26", UNREACHABLE, None),
            _fake("Q4FY26", UNREACHABLE, Decimal(10**12)),
        ],
        ("Q3FY26", "Q4FY26"),
    )
    assert none["solvable_total"] is None
    assert none["headline"].startswith("partial: 0 of 2 quarters solvable")


def test_the_check_catches_a_schedule_that_does_not_meet_its_target(world):
    import dataclasses

    from engine.tieout_core.pipeline_report import quarter_checks

    data, model, windows = world
    targets = quarters(Q2FY26=1, Q3FY26=3 * 10**6, Q4FY26=6 * 10**6)
    results = solve_quarters(
        model, data, AS_OF, windows, targets, {}, None, Decimal(10**9)
    )
    good = quarter_checks(
        results, model, data, AS_OF, windows, None, {}, targets, Decimal(10**9)
    )
    assert good[0].passed, good[0].detail
    # halve one quarter's pipeline: the schedule no longer meets its stated target
    broken = [
        dataclasses.replace(r, inflows=tuple(dataclasses.replace(i, dollars=i.dollars / 2) for i in r.inflows))
        if r.quarter == "Q3FY26" else r
        for r in results
    ]  # fmt: skip
    bad = quarter_checks(
        broken, model, data, AS_OF, windows, None, {}, targets, Decimal(10**9)
    )
    assert not bad[0].passed and "Q3FY26" in bad[0].detail


def test_an_unreachable_label_is_checked_against_the_cap_and_the_selling_window(world):
    import dataclasses

    from engine.tieout_core.pipeline_report import quarter_checks

    data, model, windows = world
    cap = Decimal(10**9)
    targets = quarters(Q2FY26=10**12, Q3FY26=3 * 10**6)
    results = solve_quarters(model, data, AS_OF, windows, targets, {}, None, cap)
    assert (
        results[0].outcome == UNREACHABLE and results[0].required is None
    )  # beyond the selling window
    assert quarter_checks(results, model, data, AS_OF, windows, None, {}, targets, cap)[
        0
    ].passed
    # claim Q3 is unreachable although a small amount reaches it and the cap is ample
    wrong = [
        results[0],
        dataclasses.replace(results[1], outcome=UNREACHABLE, required=None, inflows=()),
    ]
    bad = quarter_checks(wrong, model, data, AS_OF, windows, None, {}, targets, cap)
    assert not bad[0].passed and "Q3FY26" in bad[0].detail


# ---------------------------------------------------------------- Goal 2C: too late, and the open pipeline


def _quarter(outcome, required, *, expected=1000, months=10, **more):
    from engine.tieout_core.requirement import QuarterResult

    fields = {
        "quarter": "Q4FY26", "status": "not started", "target": Decimal(10_000), "actual": Decimal(0),
        "outcome": outcome, "required": None if required is None else Decimal(required),
        "assigned": Decimal(required or 0) if outcome == FEASIBLE else Decimal(0),
        "cap_left": Decimal(10**9), "forecast_without": Decimal(7_000),
        "forecast_with": Decimal(10_000), "piece": (AS_OF, date(2027, 1, 31)), "inflows": (),
        "expected_created": Decimal(expected), "ramped_ae_months": Decimal(months),
        "yield_per_dollar": Decimal("0.2"), "open_arr": Decimal(12_000), "open_expected": Decimal(3_000),
    }  # fmt: skip
    return QuarterResult(**{**fields, **more})


def test_too_late_by_the_cap_rule_alone_when_no_per_rep_comparison_applies():
    from engine.tieout_core.requirement import too_late

    over_cap = _quarter(UNREACHABLE, 10**12)  # needs more than the cap
    nothing_helps = _quarter(UNREACHABLE, None)  # no amount books inside the quarter
    fine = _quarter(FEASIBLE, 500)
    covered = _quarter(COVERED, 0)
    assert too_late(over_cap, None, False) == ("over the cap",)
    assert too_late(nothing_helps, None, False) == (
        "no pipeline created in time books inside it",
    )
    assert too_late(fine, None, False) == () and too_late(covered, None, False) == ()


def test_too_late_by_the_per_rep_rule_exactly_when_the_requirement_is_above_the_teams_best():
    from engine.tieout_core.requirement import too_late

    # (expected 1,000 + required 500) over 10 ramped AE-months = 150 per month.
    q = _quarter(FEASIBLE, 500)
    assert too_late(q, Decimal(149), True) != ()  # 150 > 149
    assert too_late(q, Decimal(150), True) == ()  # equal is not above
    assert too_late(q, Decimal(151), True) == ()
    reason = too_late(q, Decimal(149), True)[0]
    assert "150" in reason and "149" in reason
    # a covered quarter asks nothing of the team, however its expected pipeline compares
    assert too_late(_quarter(COVERED, 0), Decimal(1), True) == ()


def test_the_per_rep_leg_is_off_when_not_applicable_or_there_is_no_best_or_no_roster():
    from engine.tieout_core.requirement import too_late

    q = _quarter(FEASIBLE, 500)
    assert (
        too_late(q, Decimal(1), False) == ()
    )  # capacity not adopted: a diagnostic only
    assert too_late(q, None, True) == ()  # fewer than four complete quarters on record
    assert (
        too_late(_quarter(FEASIBLE, 500, ramped_ae_months=None), Decimal(1), True) == ()
    )
    assert (
        too_late(_quarter(FEASIBLE, 500, ramped_ae_months=Decimal(0)), Decimal(1), True)
        == ()
    )


def test_the_win_rate_that_would_close_the_quarter_is_arithmetic_on_existing_figures():
    from engine.tieout_core.requirement import close_with_open_pipeline

    # Target 10,000; the forecast without its own pipeline gives 7,000, of which the
    # open pipeline's expected contribution is 3,000 out of 12,000 open ARR. The
    # open pipeline would have to book 3,000 + (10,000 - 7,000) = 6,000 inside the
    # quarter: 50% of its dollars against the 25% expected.
    c = close_with_open_pipeline(_quarter(UNREACHABLE, 10**12))
    assert (c.expected, c.needed, c.open_arr) == (
        Decimal(3000),
        Decimal(6000),
        Decimal(12000),
    )
    assert (c.expected_share, c.needed_share) == (Decimal("0.25"), Decimal("0.5"))
    assert c.possible
    # More than the whole open pipeline is needed: no win rate closes it.
    big = close_with_open_pipeline(
        _quarter(UNREACHABLE, 10**12, open_arr=Decimal(5000))
    )
    assert big.needed == 6000 and not big.possible
    none = close_with_open_pipeline(
        _quarter(UNREACHABLE, 10**12, open_arr=Decimal(0), open_expected=Decimal(0))
    )
    assert none.needed_share is None and not none.possible


# ---------------------------------------------------------------- Goal 2C: the lead-time table


def march_quarters(as_of=AS_OF):
    from engine.tieout_core.requirement import next_quarters

    return next_quarters(FiscalYear(date(2026, 3, 1)), as_of)


def test_the_next_four_quarters_are_the_ones_that_end_after_the_as_of():
    # FY starting 2026-03-01 (FY26): Q1 ends 05-31, Q2 08-31, Q3 11-30, Q4 02-28.
    q = march_quarters()
    assert [k for k, _ in q] == ["Q2FY26", "Q3FY26", "Q4FY26", "Q1FY27"]
    assert q[0][1].end == date(2026, 8, 31) and q[3][1].end == date(2027, 5, 31)
    # a quarter that ended on the as-of is behind us
    assert march_quarters(date(2026, 8, 31))[0][0] == "Q3FY26"


def test_lead_time_by_hand_a_dollar_created_next_month_straddling_a_quarter_end(world):
    from engine.tieout_core.requirement import lead_times

    # Created evenly through July 2026 (as-of 06-30); every deal books 45 days later,
    # on 08-15..09-14. Quarter ends 2026-08-31 and 2026-11-30: a dollar created on
    # July d books by 08-31 when d <= 07-17: 17 of the 31 days. The other 14 of 31
    # book in the second quarter. Win rate 1: nothing is lost and nothing is later.
    data, model, _ = world
    lt = lead_times(model, data, AS_OF, march_quarters())
    assert lt.created_between == (AS_OF, date(2026, 7, 31))
    tol = Decimal("1e-12")
    assert [k for k, _ in lt.booked] == ["Q2FY26", "Q3FY26", "Q4FY26", "Q1FY27"]
    got = [v for _, v in lt.booked]
    assert abs(got[0] - Decimal(17) / 31) < tol and abs(got[1] - Decimal(14) / 31) < tol
    assert got[2] == 0 and got[3] == 0
    assert abs(lt.later) < tol and abs(lt.never) < tol
    assert abs(sum(got) + lt.later + lt.never - 1) < tol
    assert (
        abs(lt.cumulative[0][1] - Decimal(17) / 31) < tol
        and abs(lt.cumulative[1][1] - 1) < tol
    )


def test_lead_time_with_losses_never_booked_is_the_dollars_that_do_not_win(
    world, tmp_path
):
    from dataclasses import replace

    from engine.tieout_core.records import Dataset, Transition
    from engine.tieout_core.requirement import lead_times

    data, _, _ = world
    # Every second closed deal is lost instead of won: 18 of the 37 deals in the
    # matured cohort win, so 19/37 of a created dollar never books.
    lost = {d.id for i, d in enumerate(data.deals) if d.is_closed and i % 2 == 1}
    deals = tuple(
        replace(d, stage="Lost", is_won=False) if d.id in lost else d
        for d in data.deals
    )
    moves = tuple(
        t for t in data.transitions if not (t.deal_id in lost and t.stage == "Won")
    ) + tuple(Transition(d.id, "Lost", d.close) for d in deals if d.id in lost)
    ds = Dataset(deals, moves, data.observations)
    model = fit(as_known_at(ds, AS_OF), AS_OF, load_profile(write_profile(tmp_path)))
    lt = lead_times(model, ds, AS_OF, march_quarters())
    tol = Decimal("1e-12")
    assert abs(lt.never - Decimal(19) / 37) < tol
    assert (
        abs(sum((v for _, v in lt.booked), Decimal(0)) + lt.later + lt.never - 1) < tol
    )
    assert abs(sum((v for _, v in lt.booked), Decimal(0)) - Decimal(18) / 37) < tol

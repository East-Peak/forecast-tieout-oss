"""Goal 2B: fitting ramp and attrition from the company's own history.

Ramp is created deals per rep by tenure month relative to reps with twelve or
more months' tenure in the same calendar month. Attrition is departures over
AE-months. Each is labelled fitted, entered or default, with its sample."""

from datetime import date, timedelta
from decimal import Decimal
from statistics import median

import pytest

from engine.tests.tieout_core.capgen import make_world
from engine.tieout_core import capacity_rules as rules
from engine.tieout_core.ramp import fit_attrition, fit_ramp
from engine.tieout_core.rates import DEFAULT, ENTERED, FITTED
from engine.tieout_core.records import Deal
from engine.tieout_core.roster import Member


def member(id, start, end=None):
    return Member(id, "ae", "mm", date.fromisoformat(start),
                  date.fromisoformat(end) if end else None, None)  # fmt: skip


def deal(n, owner, on):
    return Deal(0, f"D{n}", "new_business", "mm", "S1", Decimal(100), on, None, False,
                False, owner)  # fmt: skip


def hand_world(new_reps=8):
    """3 tenured reps and ``new_reps`` hired together on 2025-02-01, so tenure
    month k is exactly calendar month k from February 2025. Every tenured rep
    creates 4 deals a month; a new rep creates 2 in tenure month 1 and 4 after."""
    members = [member(f"T{i}", "2020-01-01") for i in range(3)]
    members += [member(f"N{i}", "2025-02-01") for i in range(new_reps)]
    deals, n = [], 0
    for y, m in [(2025, k) for k in range(1, 13)] + [(2026, k) for k in range(1, 4)]:
        for who in members:
            if who.start > date(y, m, 28):
                continue
            first_month = who.start.year == y and who.start.month == m
            for day in (1, 8, 15, 22) if not first_month else (1, 15):
                n += 1
                deals.append(deal(n, who.id, date(y, m, day)))
    return members, deals


CUTOFF = date(2026, 3, 31)


def test_ramp_by_hand_tenure_month_one_is_half_a_tenured_rep():
    # February 2025: 8 new reps x 28 days of tenure month 1; the 3 tenured reps made
    # 12 deals in 84 rep-days, so a tenured rep makes 12/84 = 1/7 a day; the new
    # reps would have made 8 x 28 x 1/7 = 32 deals and made 16 (2 each): 16/32 = 1/2.
    # Every later tenure month: 32 expected, 32 made, weight 1.
    members, deals = hand_world()
    fit = fit_ramp(deals, members, CUTOFF, entered=None)
    assert fit.curve.source == FITTED
    assert fit.curve.weights == (Decimal("0.5"),) + (Decimal(1),) * 10
    assert fit.reps_observed == 8 and fit.tenured_reps == 3
    lo, hi = fit.curve.ranges[0]
    assert lo < 0.5 < hi


def test_too_few_reps_observed_from_hire_falls_back_to_the_entered_curve():
    members, deals = hand_world(new_reps=7)
    entered = (Decimal("0.2"), Decimal("0.6"))
    fit = fit_ramp(deals, members, CUTOFF, entered=entered)
    assert fit.curve.source == ENTERED and fit.curve.weights == entered
    assert fit.reps_observed == 7
    assert "7 reps" in fit.reason and "8" in fit.reason


def test_too_few_tenured_reps_falls_back_and_with_nothing_entered_uses_the_default():
    members, deals = hand_world()
    members = [m for m in members if m.id not in ("T0", "T1")]  # one tenured rep left
    deals = [d for d in deals if d.owner_id not in ("T0", "T1")]
    fit = fit_ramp(deals, members, date(2026, 1, 31), entered=None)
    assert fit.curve.source == DEFAULT and fit.curve.weights == rules.DEFAULT_RAMP
    assert "tenured" in fit.reason


def test_the_ramp_fit_cannot_see_the_future():
    members, deals = hand_world()
    base = fit_ramp(deals, members, CUTOFF, entered=None)
    future = [
        deal(10_000 + i, "N0", CUTOFF + timedelta(days=1 + i)) for i in range(500)
    ]
    rewritten = [
        member(m.id, m.start.isoformat(), "2026-06-01") if m.id == "T0" else m
        for m in members
    ] + [member("LATE", "2026-04-15")]
    again = fit_ramp(deals + future, rewritten, CUTOFF, entered=None)
    assert again.curve == base.curve and again.reps_observed == base.reps_observed


# ---------------------------------------------------------------- attrition


def test_attrition_by_hand_is_departures_over_ae_months():
    # Observed 2025-01-01 to 2025-12-31 (365 days). Ten reps; five leave with a
    # last day of 2025-06-30 (181 days each), five stay (365 days each):
    # 5 x 181 + 5 x 365 = 2,730 rep-days = 2,730 / 30.4375 AE-months.
    # 5 departures / that = 5 x 30.4375 / 2,730 per AE-month.
    members = [member(f"L{i}", "2024-01-01", "2025-06-30") for i in range(5)]
    members += [member(f"S{i}", "2024-01-01") for i in range(5)]
    a = fit_attrition(members, date(2025, 12, 31), since=date(2025, 1, 1), entered=None)
    assert a.source == FITTED and a.departures == 5
    assert a.ae_months == Decimal(2730) / Decimal("30.4375")
    assert a.rate == Decimal(5) / a.ae_months
    assert a.low95 < float(a.rate) < a.high95


def test_fewer_than_five_departures_is_entered_or_default_and_says_so():
    members = [member(f"L{i}", "2024-01-01", "2025-06-30") for i in range(4)]
    members += [member(f"S{i}", "2024-01-01") for i in range(6)]
    cutoff, since = date(2025, 12, 31), date(2025, 1, 1)
    entered = fit_attrition(members, cutoff, since, entered=Decimal("0.02"))
    assert (entered.source, entered.rate, entered.departures) == (
        ENTERED,
        Decimal("0.02"),
        4,
    )
    default = fit_attrition(members, cutoff, since, entered=None)
    assert (default.source, default.rate) == (DEFAULT, rules.DEFAULT_MONTHLY_ATTRITION)
    assert "4 departures" in default.reason and "5" in default.reason


def test_a_later_departure_is_hidden_from_the_attrition_fit():
    members = [member(f"L{i}", "2024-01-01", "2025-06-30") for i in range(5)]
    members += [member("LATER", "2024-01-01", "2026-02-10")]  # leaves after the cutoff
    a = fit_attrition(members, date(2025, 12, 31), since=date(2025, 1, 1), entered=None)
    assert a.departures == 5


# ---------------------------------------------------------------- recovery


@pytest.fixture(scope="module")
def ramp_runs():
    runs = []
    for seed in range(rules.RECOVERY_SEEDS):
        w = make_world(seed, tenured=8, hires=40, deals_per_month=8.0, ramp_months=6)
        fit = fit_ramp(w.deals, w.members, w.cutoff, entered=None)
        runs.append((fit, w.true_ramp))
    return runs


def test_every_seed_has_enough_reps_to_fit(ramp_runs):
    assert all(f.curve.source == FITTED for f, _ in ramp_runs)


@pytest.mark.parametrize("month", range(1, 12))
def test_true_ramp_weight_is_inside_the_95_range_in_at_least_90_percent_of_seeds(
    ramp_runs, month
):
    inside = sum(
        f.curve.ranges[month - 1][0] <= truth[month - 1] <= f.curve.ranges[month - 1][1]
        for f, truth in ramp_runs
    )
    assert inside / len(ramp_runs) >= rules.RECOVERY_MIN_COVERAGE, (month, inside)


def test_the_ramp_point_estimate_is_close_not_just_the_range_wide(ramp_runs):
    errors = [
        sum(abs(float(w) - t) for w, t in zip(f.curve.weights, truth)) / len(truth)
        for f, truth in ramp_runs
    ]
    assert median(errors) < rules.RAMP_POINT_TOLERANCE, median(errors)


@pytest.fixture(scope="module")
def attrition_runs():
    runs = []
    for seed in range(rules.RECOVERY_SEEDS):
        w = make_world(seed, tenured=8, hires=32, deals_per_month=1.0, months=30,
                       monthly_attrition=0.02, hire_window_months=15)  # fmt: skip
        a = fit_attrition(w.members, w.cutoff, w.history_start, entered=None)
        runs.append((a, w.true_attrition))
    return runs


def test_true_attrition_is_inside_the_95_range_in_at_least_90_percent_of_seeds(
    attrition_runs,
):
    fitted = [(a, t) for a, t in attrition_runs if a.source == FITTED]
    assert len(fitted) >= 0.95 * len(attrition_runs)
    inside = sum(a.low95 <= t <= a.high95 for a, t in fitted)
    assert inside / len(attrition_runs) >= rules.RECOVERY_MIN_COVERAGE


def test_the_attrition_point_estimate_is_close(attrition_runs):
    errors = [abs(float(a.rate) - t) for a, t in attrition_runs if a.source == FITTED]
    assert median(errors) < rules.ATTRITION_POINT_TOLERANCE, median(errors)

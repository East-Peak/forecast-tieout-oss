"""Goal 2B section 12: two actions compared, and the smallest whole number of
hires that closes the fiscal-year gap."""

from datetime import date
from decimal import Decimal

from engine.tieout_core.actions import (
    FEASIBLE_HIRES,
    employed_months,
    hires_bound,
    rank,
    solve_hires,
)
from engine.tieout_core.fiscal import month_windows
from engine.tieout_core.roster import Member

AS_OF = date(2026, 8, 31)
WINDOWS = month_windows(AS_OF, date(2027, 8, 31))


def line(n):
    """A forecast of 100 plus 30 a hire, to be hand-checked."""
    return Decimal(100 + 30 * n)


def test_the_smallest_whole_number_of_hires_that_reaches_the_target():
    # 100 + 30n >= 250 first holds at n = 5 (250); n = 4 gives 220.
    r = solve_hires(line, Decimal(250), bound=10)
    assert (r.outcome, r.count, r.overshoot) == (FEASIBLE_HIRES, 5, Decimal(0))
    assert r.forecast_with == 250 and r.forecast_one_fewer == 220


def test_the_overshoot_is_shown_when_a_whole_hire_goes_past_the_gap():
    r = solve_hires(line, Decimal(251), bound=10)  # n = 6 gives 280
    assert (r.count, r.overshoot) == (6, Decimal(29))
    assert r.forecast_one_fewer == 250  # one fewer reaches 250, one short of 251


def test_nothing_to_close_means_zero_hires():
    r = solve_hires(line, Decimal(90), bound=10)
    assert r.outcome == "already covered" and r.count == 0


def test_past_the_bound_the_gap_is_unreachable_and_the_best_case_is_shown():
    r = solve_hires(line, Decimal(1000), bound=4)  # 4 hires give 220
    assert r.outcome == "unreachable" and r.count is None and r.forecast_with == 220


def test_a_bound_of_zero_is_unreachable():
    assert solve_hires(line, Decimal(250), bound=0).outcome == "unreachable"


def test_the_bound_is_the_most_hires_started_in_one_fiscal_quarter_or_an_entered_bound():
    def m(i, start):
        return Member(f"A{i}", "ae", "mm", date.fromisoformat(start), None, None)

    # Fiscal year starts 2026-02-01. Q1 (Feb-Apr 2026) starts: 3; Q2 (May-Jul): 1.
    members = [m(1, "2026-02-10"), m(2, "2026-03-01"), m(3, "2026-04-30"), m(4, "2026-06-01"),
               m(5, "2026-09-15")]  # fmt: skip
    assert hires_bound(members, date(2026, 2, 1), AS_OF, entered=None) == (
        3,
        "the most the company has started in one fiscal quarter",
    )
    assert hires_bound(members, date(2026, 2, 1), AS_OF, entered=7) == (
        7,
        "entered in capacity.yaml",
    )


def test_employed_months_count_calendar_months_by_days_in_the_month():
    # A hire from 2026-09-16 with nobody leaving, over the twelve months to 2027-08-31:
    # September is 15 of 30 days = 0.5, then eleven whole months (October to
    # August): 0.5 + 11 = 11.5.
    assert employed_months(date(2026, 9, 16), WINDOWS, AS_OF, Decimal(1)) == Decimal(
        "11.5"
    )
    assert employed_months(date(2026, 9, 1), WINDOWS, AS_OF, Decimal(1)) == Decimal(12)


def test_expected_attrition_shortens_the_employed_months():
    s = Decimal("0.999")  # a daily chance of staying
    assert employed_months(date(2026, 9, 1), WINDOWS, AS_OF, s) < Decimal(12)


def test_actions_rank_by_gain_per_dollar_and_unvalued_ones_are_not_ranked():
    rows = [
        {"action": "a", "gain_per_dollar": Decimal(2), "not_ranked_because": None},
        {"action": "b", "gain_per_dollar": Decimal(5), "not_ranked_because": None},
        {
            "action": "c",
            "gain_per_dollar": None,
            "not_ranked_because": "cost not entered",
        },
    ]
    ranked = rank(rows)
    assert [(r["action"], r["rank"]) for r in ranked] == [
        ("b", 1),
        ("a", 2),
        ("c", None),
    ]

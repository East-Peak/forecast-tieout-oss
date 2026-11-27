"""What the company's own past shows, one fiscal creation quarter at a time."""

from datetime import date, timedelta
from decimal import Decimal

from engine.tieout_core import worksheet_rules as rules
from engine.tieout_core.records import Deal
from engine.tieout_core.worksheet_evidence import observe

D = Decimal
FY_START = date(2026, 2, 1)
AS_OF = date(2026, 8, 31)


def deal(i, created, won_after=None, arr="1000", lost=False):
    created = date.fromisoformat(created)
    close = (
        None
        if won_after is None and not lost
        else created + timedelta(days=won_after or 30)
    )
    return Deal(
        i, f"d{i}", "new_business", "mm", "Closed Won" if won_after is not None else "Closed Lost" if lost else "Discovery",
        D(arr), created, close, won_after is not None or lost, won_after is not None,
    )  # fmt: skip


def days_exposure(start, end):
    return D((end - start).days + 1)


def test_the_first_quarter_is_the_first_whole_one_after_the_first_deal():
    # The first deal is 2024-03-15, inside Q1FY24 (Feb-Apr 2024), so that quarter is partial
    # and the first observed quarter is Q2FY24 (May-Jul 2024).
    deals = [deal(1, "2024-03-15"), deal(2, "2024-05-01")]
    q = observe(deals, AS_OF, FY_START, 365, days_exposure)
    assert q[0].label == "Q2FY24" and q[0].start == date(2024, 5, 1)


def test_a_first_deal_on_the_first_day_of_a_quarter_keeps_that_quarter():
    q = observe([deal(1, "2024-02-01")], AS_OF, FY_START, 365, days_exposure)
    assert q[0].label == "Q1FY24" and q[0].start == date(2024, 2, 1)


def test_only_complete_quarters_are_observed():
    # as-of 2026-08-31 falls inside Q3FY26 (Aug-Oct 2026); the last complete one is Q2FY26
    q = observe([deal(1, "2024-02-01")], AS_OF, FY_START, 365, days_exposure)
    assert q[-1].label == "Q2FY26" and q[-1].end == date(2026, 7, 31)
    assert [x.label for x in q][:3] == ["Q1FY24", "Q2FY24", "Q3FY24"]


def test_a_quarter_matures_when_the_horizon_has_passed_since_it_ended():
    q = {
        x.label: x
        for x in observe([deal(1, "2024-02-01")], AS_OF, FY_START, 365, days_exposure)
    }
    # Q2FY25 ends 2025-07-31; +365 days = 2026-07-31 <= as-of: mature. Q3FY25 ends 2025-10-31: not.
    assert q["Q2FY25"].mature and not q["Q3FY25"].mature


def test_values_of_a_quarter_by_hand():
    deals = [
        deal(1, "2024-05-01", won_after=100, arr="1000"),
        deal(2, "2024-05-10", won_after=200, arr="3000"),
        deal(3, "2024-06-01", lost=True),
        deal(4, "2024-06-02"),  # still open, created in Q2FY24
        deal(
            5, "2024-06-03", won_after=400, arr="9999"
        ),  # won after the 365-day horizon? no: 400 > 365
    ]
    q = {x.label: x for x in observe(deals, AS_OF, FY_START, 365, days_exposure)}[
        "Q2FY24"
    ]
    assert q.created == 5 and q.wins == 2
    assert q.win_rate == D(2) / D(5)
    assert q.won_arr == D(2000)
    assert q.cycle_days == D(150)
    assert q.exposure == D(92) and q.productivity == D(5) / D(92)


def test_a_quarter_with_no_wins_has_no_size_or_cycle_and_a_zero_win_rate():
    q = observe([deal(1, "2024-05-01", lost=True)], AS_OF, FY_START, 365, days_exposure)
    first = q[0]
    assert (first.win_rate, first.won_arr, first.cycle_days) == (D(0), None, None)


def test_a_win_that_closes_after_the_as_of_date_is_not_counted():
    deals = [
        deal(1, "2026-05-01", won_after=200)
    ]  # would close 2026-11-17, after as-of
    q = {
        x.label: x
        for x in observe(
            [deal(0, "2026-02-01"), *deals], AS_OF, FY_START, 365, days_exposure
        )
    }
    assert q["Q2FY26"].wins == 0


def test_exposure_comes_from_the_function_given():
    q = observe([deal(1, "2024-02-01")], AS_OF, FY_START, 365, lambda a, b: D(7))
    assert {x.exposure for x in q} == {D(7)}
    assert q[0].productivity == D(1) / D(7)


def test_no_exposure_means_no_productivity():
    q = observe([deal(1, "2024-02-01")], AS_OF, FY_START, 365, lambda a, b: D(0))
    assert q[0].productivity is None


def test_no_deals_no_quarters():
    assert observe([], AS_OF, FY_START, 365, days_exposure) == []


def test_observations_feed_the_rules():
    deals = [deal(1, "2024-02-01", won_after=50)]
    q = observe(deals, AS_OF, FY_START, 365, days_exposure)
    assert rules.eligible(q[0], rules.WIN_RATE)[0] is False  # one created deal

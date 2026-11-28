"""Owner allocations: the plan-start roster shares each segment's goal, and nothing later moves it."""

from datetime import date
from decimal import Decimal

from engine.tieout_core import lanes_alloc as alloc
from engine.tieout_core.fiscal import FiscalYear
from engine.tieout_core.lanes_basis import Goal
from engine.tieout_core.roster import Member

D = Decimal
FY = FiscalYear(date(2026, 2, 1))  # runs to 2027-01-31, 365 days
PLAN = date(2026, 1, 31)


def member(id, segment="a", quota="1000", start=date(2024, 1, 1), end=None):
    return Member(id, "ae", segment, start, end, None if quota is None else D(quota), id.upper())  # fmt: skip


def test_a_persons_weight_is_their_quota_over_the_days_employed_in_the_year():
    got = alloc.weights([member("x"), member("y", start=date(2026, 8, 2))], PLAN, FY)
    assert got[("a", "x")] == alloc.Weight(D(1000), 365, D(365000))
    assert ("a", "y") not in got  # hired after the plan date: no original allocation


def test_a_departure_after_the_plan_date_is_not_known_and_one_before_it_leaves_no_days():
    got = alloc.weights(
        [member("x", end=date(2026, 6, 1)), member("y", end=date(2025, 12, 31))],
        PLAN,
        FY,
    )
    assert got[("a", "x")].days == 365
    assert got[("a", "y")] == alloc.Weight(D(1000), 0, D(0))


def test_a_person_with_no_quota_is_allocated_nothing_but_is_still_on_the_roster():
    got = alloc.weights([member("x", quota=None), member("y", quota="0")], PLAN, FY)
    assert got[("a", "x")].weight == got[("a", "y")].weight == 0


GOAL = Goal(D("100.00"), D("1.0000"), D("10.0000"), D("5.00"), D("30.00"))


def test_a_goal_is_shared_by_weight_to_the_last_unit_and_adds_back_exactly():
    got = alloc.split_goal(GOAL, {"x": D(1), "y": D(1), "z": D(1)})
    assert sum(g.bookings for g in got.values()) == GOAL.bookings
    assert sum(g.won for g in got.values()) == GOAL.won
    assert sum(g.created for g in got.values()) == GOAL.created
    assert sum(g.created_arr for g in got.values()) == GOAL.created_arr
    assert sum(g.days for g in got.values()) == GOAL.days
    shared = sorted(g.bookings for k, g in got.items() if k != alloc.UNASSIGNED)
    assert shared == [D("33.33"), D("33.33"), D("33.34")]


def test_a_segment_with_nobody_to_share_to_gives_its_whole_goal_to_the_unassigned_bucket():
    got = alloc.split_goal(GOAL, {"x": D(0), "y": D(0)})
    assert got["x"].bookings == got["y"].bookings == 0
    assert got[alloc.UNASSIGNED] == GOAL
    assert alloc.split_goal(GOAL, {"x": D(2)})[alloc.UNASSIGNED].bookings == 0


def test_the_owners_and_their_shares_do_not_depend_on_the_order_people_are_listed_in():
    people = [member(f"p{i}", quota=str(900 + i)) for i in range(7)]
    goals = {("Q1FY26", "a"): Goal(D("100.00"), D("1.0000"), D("10.0000"), D("5.00"), D("30.00"))}  # fmt: skip
    run = lambda ms: alloc.owner_basis([], ms, PLAN, FY, 365, goals, ["a"])
    assert run(people) == run(people[::-1]) == run(people[3:] + people[:3])
    owners, shared = run(people)
    assert [o.id for o in owners][-1] == alloc.UNASSIGNED
    assert sum(g.bookings for g in shared.values()) == D("100.00")

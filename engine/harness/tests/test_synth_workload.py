"""The routing and queue core, and its reproduction of golden fixture B.

The daily simulation and this test both drive `synth.workload.RoutingQueue`; the
test configures it monthly (one period is a month, one retry) and supplies the
fixture's deterministic closing and outcome rules around it.
"""

from fractions import Fraction

import pytest

from engine.harness.contract.workload import load_workload_b
from engine.harness.synth.workload import RoutingQueue, largest_remainder, route


def test_largest_remainder_gives_leftovers_to_biggest_fractions_then_earlier_lane():
    assert largest_remainder(4, [4, 2]) == [3, 1]  # 2.67 and 1.33
    assert largest_remainder(2, [3, 2]) == [1, 1]  # 1.2 and 0.8
    assert largest_remainder(1, [4, 2]) == [1, 0]
    assert largest_remainder(1, [1, 1]) == [1, 0]  # tie goes to the earlier lane
    assert largest_remainder(9, [3, 2]) == [3, 2]  # undersubscribed: everyone fits
    assert largest_remainder(0, [3, 2]) == [0, 0]


def test_route_serves_the_oldest_class_first():
    takes = route(5, [[3, 2], [4, 4]])  # old class has 5, nothing left for the new
    assert takes == [[3, 2], [0, 0]]
    assert route(6, [[3, 2], [4, 4]]) == [[3, 2], [1, 0]]


def test_queue_expires_after_max_age_and_keeps_item_identity():
    q = RoutingQueue(2, max_age=1)
    admitted, expired = q.step(1, [["a1", "a2"], ["b1"]])
    assert admitted == [["a1"], []] and expired == [[], []]
    admitted, expired = q.step(0, [[], []])  # the retry month, no room
    assert admitted == [[], []] and expired == [["a2"], ["b1"]]
    assert q.sizes() == [0, 0]


def test_a_queue_may_not_admit_more_than_the_room():
    q = RoutingQueue(1, max_age=3)
    admitted, _ = q.step(2, [list("abcde")])
    assert admitted == [["a", "b"]] and q.sizes() == [3]


def run_fixture_b(inputs):
    """Drive the core month by month under the fixture's closing and outcome rules."""
    lanes, months = inputs["lanes"], inputs["months"]
    spec = inputs["lane_inputs"]
    queue = RoutingQueue(len(lanes), max_age=1)  # one retry month, then expiry
    is_open = [spec[k]["initial_open"] for k in lanes]
    admitted_hist = []  # admissions per lane per month (deals close two months on)
    cum_closed, cum_wins = [0] * len(lanes), [0] * len(lanes)
    out = {k: {} for k in lanes}
    for m, month in enumerate(months):
        ramped = sum(
            1 for r in inputs["roster"] if r["role"] == "AE" and r["start"][:7] < month
        )
        closings = [
            spec[k]["initial_closings"][m] + (admitted_hist[m - 2][i] if m >= 2 else 0)
            for i, k in enumerate(lanes)
        ]
        wins = []
        for i, k in enumerate(lanes):
            cum_closed[i] += closings[i]
            target = int(Fraction(spec[k]["win_rate"]) * cum_closed[i] + Fraction(1, 2))
            wins.append(target - cum_wins[i])
            cum_wins[i] = target
        room = ramped * inputs["carrying_ceiling"] - sum(is_open) + sum(closings)
        queue_start = queue.sizes()
        arrivals = [
            list(range(spec[k]["arrivals"][m] - spec[k]["rejected_fit"][m]))
            for k in lanes
        ]
        admitted, expired = queue.step(room, arrivals)
        admitted_hist.append([len(a) for a in admitted])
        for i, k in enumerate(lanes):
            row = out[k]
            for name, value in (
                ("open_start", is_open[i]),
                ("queue_start", queue_start[i]),
                ("admissions", len(admitted[i])),
                ("expired", len(expired[i])),
                ("queue_end", queue.sizes()[i]),
                ("wins", wins[i]),
                ("losses", closings[i] - wins[i]),
            ):
                row.setdefault(name, []).append(value)
            is_open[i] += len(admitted[i]) - closings[i]
            row.setdefault("open_end", []).append(is_open[i])
    return out


def test_fixture_b_is_reproduced_exactly_by_the_shared_core():
    _, inputs, expected = load_workload_b()
    got = run_fixture_b(inputs)
    for lane, table in expected["lane_tables"].items():
        for field in (
            "open_start",
            "queue_start",
            "admissions",
            "queue_end",
            "wins",
            "losses",
            "open_end",
        ):
            assert got[lane][field] == table[field], (lane, field)
        assert got[lane]["expired"] == table["exits"]["expired_no_capacity"], lane


@pytest.mark.parametrize("slots", range(9))
def test_largest_remainder_always_conserves_slots(slots):
    sizes = [4, 3, 2]
    assert sum(largest_remainder(slots, sizes)) == min(slots, sum(sizes))

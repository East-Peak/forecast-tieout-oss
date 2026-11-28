"""Golden fixture B: the hand-computed workload. The expected table loads into
a Snapshot, both identities and the capacity inequality hold exactly, and an
independent reference simulation of the stated rules reproduces every number."""

from fractions import Fraction

import numpy as np

from engine.harness.contract.snapshot import flow_violations
from engine.harness.contract.workload import load_workload_b


def split(slots, sizes):
    """Largest remainder: floor of each exact share, leftovers to the largest fractions, ties to the earlier lane."""
    total = sum(sizes)
    if total <= slots:
        return list(sizes)
    exact = [Fraction(slots * s, total) for s in sizes]
    out = [int(x) for x in exact]
    order = sorted(range(len(sizes)), key=lambda i: (-(exact[i] - out[i]), i))
    for i in order[: slots - sum(out)]:
        out[i] += 1
    return out


def simulate(inputs):
    """Reference model of the rules in inputs.yaml, in exact integer and Fraction arithmetic."""
    lanes, n = inputs["lanes"], len(inputs["months"])
    lane = inputs["lane_inputs"]
    ceiling = inputs["carrying_ceiling"]
    out = {
        k: {
            x: []
            for x in (
                "open_start",
                "queue_start",
                "admissions",
                "rejected",
                "expired",
                "queue_end",
                "closings",
                "wins",
                "losses",
                "open_end",
            )
        }
        for k in lanes
    }
    open_now = {k: lane[k]["initial_open"] for k in lanes}
    queue_now = {k: 0 for k in lanes}
    cum_closed = {k: 0 for k in lanes}
    cum_wins = {k: 0 for k in lanes}
    team_room, capacity = [], []
    for m in range(n):
        ramped = sum(
            1 for r in inputs["roster"] if r["start"][:7] < inputs["months"][m]
        )
        capacity.append(ramped * ceiling)
        closings, wins = {}, {}
        for k in lanes:
            admitted_then = out[k]["admissions"][m - 2] if m >= 2 else 0
            closings[k] = lane[k]["initial_closings"][m] + admitted_then
            cum_closed[k] += closings[k]
            target = int(Fraction(lane[k]["win_rate"]) * cum_closed[k] + Fraction(1, 2))
            wins[k], cum_wins[k] = target - cum_wins[k], target
        room = capacity[m] - sum(open_now.values()) + sum(closings.values())
        team_room.append(room)
        old = [queue_now[k] for k in lanes]
        new = [lane[k]["arrivals"][m] - lane[k]["rejected_fit"][m] for k in lanes]
        take_old = split(room, old)
        take_new = split(room - sum(take_old), new)
        for i, k in enumerate(lanes):
            adm = take_old[i] + take_new[i]
            row = out[k]
            row["open_start"].append(open_now[k])
            row["queue_start"].append(queue_now[k])
            row["admissions"].append(adm)
            row["rejected"].append(lane[k]["rejected_fit"][m])
            row["expired"].append(old[i] - take_old[i])
            queue_now[k] = new[i] - take_new[i]
            row["queue_end"].append(queue_now[k])
            row["closings"].append(closings[k])
            row["wins"].append(wins[k])
            row["losses"].append(closings[k] - wins[k])
            open_now[k] += adm - closings[k]
            row["open_end"].append(open_now[k])
    return out, capacity, team_room


def test_fixture_loads_into_a_snapshot_and_identities_hold():
    snapshot, _, _ = load_workload_b()
    assert snapshot.lanes == ("source=Paid", "source=Outbound")
    assert snapshot.months[0] == "2025-02" and len(snapshot.months) == 6
    assert flow_violations(snapshot) == []


def test_identities_hold_exactly_in_the_raw_table():
    _, _, expected = load_workload_b()
    for lane in expected["lane_tables"].values():
        for m in range(6):
            assert (
                lane["open_start"][m]
                + lane["admissions"][m]
                - lane["wins"][m]
                - lane["losses"][m]
                == lane["open_end"][m]
            )
            exits = sum(v[m] for v in lane["exits"].values())
            assert (
                lane["queue_start"][m] + lane["arrivals"][m]
                == lane["admissions"][m] + exits + lane["queue_end"][m]
            )
            assert lane["wins"][m] + lane["losses"][m] == lane["closings"][m]


def test_capacity_inequality_holds_and_binds_each_month():
    snapshot, _, expected = load_workload_b()
    team = expected["team_tables"]["AE-SMB"]
    admissions = snapshot.by_team(snapshot.admissions).values[0]
    assert admissions.tolist() == team["room"]  # equality: the team is full every month
    assert np.all(admissions <= team["room"])


def test_capacity_is_ramped_heads_times_the_ceiling():
    snapshot, inputs, expected = load_workload_b()
    team = expected["team_tables"]["AE-SMB"]
    ceiling = inputs["carrying_ceiling"]
    assert team["carrying_capacity"] == [h * ceiling for h in team["ramped_heads"]]
    assert snapshot.carrying_capacity.values[0].tolist() == team["carrying_capacity"]


def test_the_slipped_hire_costs_capacity_in_three_months():
    _, _, expected = load_workload_b()
    team = expected["team_tables"]["AE-SMB"]
    lost = [
        a - b
        for a, b in zip(
            team["capacity_if_hire_did_not_slip"],
            team["carrying_capacity"],
            strict=True,
        )
    ]
    assert lost == [0, 0, 0, 4, 4, 0]


def test_bookings_are_wins_times_deal_size():
    snapshot, inputs, _ = load_workload_b()
    for i, name in enumerate(snapshot.lanes):
        size = inputs["lane_inputs"][name]["deal_size_cents"]
        assert snapshot.bookings_cents.values[i].tolist() == [
            w * size for w in snapshot.wins.values[i]
        ]


def test_masks_mark_unmeasured_inputs():
    snapshot, _, _ = load_workload_b()
    assert snapshot.leads.missing[1].all() and snapshot.mqls.missing[1].all()
    assert not snapshot.leads.missing[0].any()


def test_every_number_is_reproduced_by_the_reference_simulation():
    _, inputs, expected = load_workload_b()
    sim, capacity, room = simulate(inputs)
    for name, table in expected["lane_tables"].items():
        got = sim[name]
        for field in (
            "open_start",
            "queue_start",
            "admissions",
            "queue_end",
            "closings",
            "wins",
            "losses",
            "open_end",
        ):
            assert got[field] == table[field], (name, field)
        assert got["rejected"] == table["exits"]["rejected_fit"], name
        assert got["expired"] == table["exits"]["expired_no_capacity"], name
    assert capacity == expected["team_tables"]["AE-SMB"]["carrying_capacity"]
    assert room == expected["team_tables"]["AE-SMB"]["room"]


def test_split_resolves_fractions_by_largest_remainder_then_lane_order():
    assert split(4, [4, 2]) == [3, 1]  # 2.67 and 1.33
    assert split(2, [3, 2]) == [1, 1]  # 1.2 and 0.8
    assert split(1, [3, 3]) == [1, 0]  # equal fractions: earlier lane
    assert split(9, [3, 3]) == [3, 3]  # enough slots: everyone admitted

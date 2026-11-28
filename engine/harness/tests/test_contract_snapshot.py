import numpy as np
import pytest

from engine.harness.contract.snapshot import (
    LOST,
    OPEN,
    WON,
    DealObservations,
    Measure,
    PendingRequisition,
    Snapshot,
    flow_violations,
)

LANES = ("source=Paid", "source=Outbound")
MONTHS = ("2025-02", "2025-03")


def m(axes, values, missing=None):
    return Measure(
        axes, np.array(values), None if missing is None else np.array(missing)
    )


def lm(rows):  # (lane, month) measure
    return m(("lane", "month"), rows)


def make(**over):
    """Two lanes sharing one team, two months, flows that satisfy every identity."""
    parts = {
        "lanes": LANES,
        "teams": ("AE",),
        "months": MONTHS,
        "exit_reasons": ("rejected_fit", "expired_no_capacity"),
        "lane_team": ("AE", "AE"),
        "leads": lm([[0, 0], [0, 0]]),
        "mqls": lm([[3, 3], [0, 0]]),
        "arrivals": lm([[3, 3], [2, 2]]),
        "queue_start": lm([[0, 1], [0, 0]]),
        "admissions": lm([[2, 3], [2, 2]]),
        "exits": m(("lane", "month", "reason"), [[[0, 0], [0, 0]], [[0, 0], [0, 0]]]),
        "queue_end": lm([[1, 1], [0, 0]]),
        "opportunities_created": lm([[2, 3], [2, 2]]),
        "open_start": lm([[1, 2], [1, 3]]),
        "wins": lm([[0, 1], [0, 0]]),
        "losses": lm([[1, 0], [0, 1]]),
        "open_end": lm([[2, 4], [3, 4]]),
        "bookings_cents": lm([[0, 100], [0, 0]]),
        "spend_cents": lm([[50, 50], [0, 0]]),
        "heads": m(("team", "month"), [[2, 2]]),
        "ramped_heads": m(("team", "month"), [[2, 2]]),
        "ramp_exposure": m(("team", "month"), [[2.0, 2.0]]),
        "carrying_capacity": m(("team", "month"), [[10, 10]]),
        "pending_requisitions": (),
    }
    parts.update(over)
    return Snapshot(**parts)


def test_measure_is_write_protected_and_copied():
    src = np.array([1, 2])
    meas = Measure(("month",), src)
    assert not meas.values.flags.writeable and not meas.missing.flags.writeable
    src[0] = 9
    assert meas.values[0] == 1
    with pytest.raises(ValueError):
        meas.values[0] = 5


def test_measure_rejects_misaligned_inputs():
    with pytest.raises(ValueError, match="axes"):
        Measure(("lane", "month"), np.zeros(3, dtype=int))
    with pytest.raises(ValueError, match="mask"):
        Measure(("month",), np.zeros(3, dtype=int), np.zeros(2, dtype=bool))
    with pytest.raises(ValueError, match="zero"):
        Measure(("month",), np.array([1, 2]), np.array([True, False]))


def test_valid_snapshot_has_no_violations():
    s = make()
    assert flow_violations(s) == []
    assert s.by_team(s.open_end).values.tolist() == [[5, 8]]


def test_snapshot_arrays_are_write_protected():
    with pytest.raises(ValueError):
        make().wins.values[0, 0] = 7


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"months": ("2025-02", "2025-04")}, "consecutive"),
        ({"months": ("2025-02", "Mar")}, "month label"),
        ({"lane_team": ("AE", "Nope")}, "lane_team"),
        ({"wins": m(("month", "lane"), [[0, 0], [0, 0]])}, "wins: axes"),
        ({"wins": lm([[0, 1, 0], [0, 0, 0]])}, "wins: shape"),
        ({"wins": lm([[0.0, 1.0], [0.0, 0.0]])}, "wins: expected an integer"),
        (
            {"ramp_exposure": m(("team", "month"), [[2, 2]])},
            "ramp_exposure: expected a float",
        ),
        ({"wins": lm([[0, -1], [0, 0]])}, "wins: negative"),
        (
            {"ramped_heads": m(("team", "month"), [[3, 2]])},
            "ramped_heads exceeds heads",
        ),
        ({"lanes": ("a", "a")}, "duplicate lane"),
    ],
)
def test_shape_and_type_errors_raise(over, message):
    with pytest.raises(ValueError, match=message):
        make(**over)


def test_open_identity_violation_is_named():
    s = make(open_end=lm([[2, 4], [3, 9]]))
    (problem,) = flow_violations(s)
    assert "open_start + admissions - wins - losses" in problem
    assert "source=Outbound" in problem and "2025-03" in problem


def test_queue_identity_violation_is_named():
    s = make(queue_end=lm([[1, 1], [0, 5]]))
    problems = flow_violations(s)
    assert any("queue_start + arrivals" in p for p in problems)


def test_exits_count_in_the_queue_identity():
    exits = np.zeros((2, 2, 2), dtype=int)
    exits[0, 0, 0] = 1  # one rejected_fit from Paid in 2025-02
    ok = make(
        exits=Measure(("lane", "month", "reason"), exits),
        queue_start=lm([[0, 0], [0, 0]]),
        queue_end=lm([[0, 0], [0, 0]]),
    )
    # Paid 2025-02: 0 + 3 arrivals = 2 admitted + 1 exit + 0 queued
    assert flow_violations(ok) == []


def test_continuity_violation_is_named():
    s = make(open_start=lm([[1, 3], [1, 2]]), open_end=lm([[2, 5], [3, 3]]))
    assert any("continuity" in p for p in flow_violations(s))


def test_capacity_inequality_is_checked_per_team():
    # team admits 5 in 2025-03; room = capacity - open_start + wins + losses
    s = make(carrying_capacity=m(("team", "month"), [[10, 6]]))  # 6 - 5 + 2 = 3 < 5
    (problem,) = flow_violations(s)
    assert "capacity" in problem and "2025-03" in problem and "AE" in problem


def test_missing_cells_are_skipped_not_failed():
    broken = make(open_end=lm([[2, 4], [3, 9]]))
    masked = Measure(
        ("lane", "month"),
        np.array([[2, 4], [3, 0]]),
        np.array([[False, False], [False, True]]),
    )
    assert flow_violations(broken) != []
    assert flow_violations(make(open_end=masked)) == []


def test_pending_requisitions_are_typed():
    req = PendingRequisition(
        req_id="REQ-1", team="AE", role="AE", planned_start="2025-05-01"
    )
    assert make(pending_requisitions=(req,)).pending_requisitions == (req,)
    with pytest.raises(ValueError, match="team"):
        make(
            pending_requisitions=(PendingRequisition("R", "Nope", "AE", "2025-05-01"),)
        )


# ---- DealObservations -------------------------------------------------

D = np.datetime64


def deals(**over):
    parts = {
        "lanes": LANES,
        "stages": ("Discovery", "Proposal", "Closed Won", "Closed Lost"),
        "deal_ids": np.array(["d1", "d2"]),
        "lane": np.array([0, 1]),
        "created": np.array(["2025-01-10", "2025-02-01"], dtype="datetime64[D]"),
        "outcome": np.array([WON, OPEN], dtype=np.int8),
        "outcome_date": np.array(["2025-03-01", "NaT"], dtype="datetime64[D]"),
        "reopened": np.array([False, False]),
        "observed_from": np.array(["2025-01-01", "2025-01-01"], dtype="datetime64[D]"),
        "observed_to": np.array(["2025-03-31", "2025-03-31"], dtype="datetime64[D]"),
        "stage_history_complete": np.array([True, False]),
        "transition_deal": np.array([0, 0, 0, 1]),
        "transition_stage": np.array([0, 1, 2, 1]),
        "transition_date": np.array(
            ["2025-01-10", "2025-02-05", "2025-03-01", "2025-02-20"],
            dtype="datetime64[D]",
        ),
        "amount_deal": np.array([0, 0, 1]),
        "amount_date": np.array(
            ["2025-01-10", "2025-02-05", "2025-02-01"], dtype="datetime64[D]"
        ),
        "amount_cents": np.array([1000000, 1200000, 500000]),
    }
    parts.update(over)
    return DealObservations(**parts)


def test_valid_observations_and_slices():
    obs = deals()
    assert obs.n_deals == 2
    stages, dates = obs.transitions(0)
    assert stages.tolist() == [0, 1, 2] and dates[-1] == D("2025-03-01")
    assert obs.amounts(1)[1].tolist() == [500000]
    assert obs.transitions(1)[0].tolist() == [1]
    assert LOST not in obs.outcome


def test_observation_arrays_are_write_protected():
    with pytest.raises(ValueError):
        deals().outcome[0] = LOST


def test_policies_are_declared():
    obs = deals()
    assert obs.reopened_policy == "latest_outcome"
    assert obs.missing_first_stage_policy == "unknown_until_first_transition"


@pytest.mark.parametrize(
    ("over", "message"),
    [
        (
            {
                "outcome_date": np.array(
                    ["2025-03-01", "2025-03-02"], dtype="datetime64[D]"
                )
            },
            "open deal d2 has an outcome date",
        ),
        (
            {"outcome_date": np.array(["NaT", "NaT"], dtype="datetime64[D]")},
            "closed deal d1 has no outcome date",
        ),
        (
            {"outcome_date": np.array(["2025-01-01", "NaT"], dtype="datetime64[D]")},
            "outcome before creation",
        ),
        ({"lane": np.array([0, 5])}, "lane index"),
        ({"transition_stage": np.array([0, 1, 9, 1])}, "stage index"),
        ({"transition_deal": np.array([0, 1, 0, 1])}, "sorted"),
        ({"amount_cents": np.array([1, 2])}, "amount_cents"),
        ({"deal_ids": np.array(["d1", "d1"])}, "duplicate deal id"),
        (
            {
                "observed_to": np.array(
                    ["2024-12-01", "2025-03-31"], dtype="datetime64[D]"
                )
            },
            "observed_from",
        ),
        ({"outcome": np.array([7, OPEN], dtype=np.int8)}, "outcome code"),
    ],
)
def test_observation_errors_raise(over, message):
    with pytest.raises(ValueError, match=message):
        deals(**over)

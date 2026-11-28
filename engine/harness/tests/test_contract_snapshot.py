import numpy as np
import pytest

from engine.harness.contract.snapshot import (
    DELETED,
    LOST,
    OPEN,
    WON,
    DealObservations,
    Measure,
    OutstandingEpisode,
    PendingRequisition,
    RosterObservation,
    RosterObservations,
    Snapshot,
    flow_check,
)

LANES = ("source=Paid", "source=Outbound")
MONTHS = ("2025-02", "2025-03")


def m(axes, values, missing=None, bound="exact"):
    return Measure(
        axes,
        np.array(values),
        None if missing is None else np.array(missing),
        bound,
    )


def lm(rows, **kw):  # (lane, month) measure
    return m(("lane", "month"), rows, **kw)


BDR = RosterObservation(
    person_id="BDR-1",
    role="BDR",
    team="BDR",
    segment=None,
    start_date="2024-03-01",
    end_date=None,
    planned_start=None,
    effective_at="2024-03-01T00:00:00Z",
    recorded_at="2024-03-01T00:00:00Z",
)


def make(**over):
    """Two lanes sharing one team, two months, flows that satisfy every identity."""
    parts = {
        "lanes": LANES,
        "teams": ("AE",),
        "months": MONTHS,
        "exit_reasons": ("rejected_fit", "expired_no_capacity"),
        "lane_team": ("AE", "AE"),
        "persons": ("BDR-1",),
        "leads": lm([[0, 0], [0, 0]]),
        "mqls": lm([[3, 3], [0, 0]]),
        "arrivals": lm([[3, 3], [2, 2]]),
        "queue_start": lm([[0, 1], [0, 0]]),
        "admissions": lm([[2, 3], [2, 2]]),
        "reopened": lm([[0, 0], [0, 0]]),
        "exits": m(("lane", "month", "reason"), np.zeros((2, 2, 2), dtype=int)),
        "queue_end": lm([[1, 1], [0, 0]]),
        "opportunities_created": lm([[2, 3], [2, 2]]),
        "open_start": lm([[1, 2], [1, 3]]),
        "wins": lm([[0, 1], [0, 0]]),
        "losses": lm([[1, 0], [0, 1]]),
        "deleted": lm([[0, 0], [0, 0]]),
        "open_end": lm([[2, 4], [3, 4]]),
        "bookings_cents": lm([[0, 100], [0, 0]]),
        "spend_cents": lm([[50, 50], [0, 0]]),
        "sourced_by_person": m(("person", "month"), [[2, 2]]),
        "bdr_exposure": lm([[0.0, 0.0], [1.0, 1.0]]),
        "heads": m(("team", "month"), [[2, 2]]),
        "ramped_heads": m(("team", "month"), [[2, 2]]),
        "ramp_exposure": m(("team", "month"), [[2.0, 2.0]]),
        "carrying_capacity": m(("team", "month"), [[10, 10]]),
        "roster": RosterObservations((BDR,)),
        "outstanding_episodes": (
            OutstandingEpisode("source=Paid", "lead-9", 1, "2025-03-04", 0),
        ),
        "pending_requisitions": (),
    }
    parts.update(over)
    return Snapshot(**parts)


def test_measure_is_write_protected_and_copied():
    src = np.array([1, 2])
    meas = Measure(("month",), src)
    assert not meas.values.flags.writeable
    assert not meas.missing.flags.writeable
    src[0] = 9
    assert meas.values[0] == 1
    with pytest.raises(ValueError, match="read-only"):
        meas.values[0] = 5


def test_measure_rejects_misaligned_inputs():
    with pytest.raises(ValueError, match="axes"):
        Measure(("lane", "month"), np.zeros(3, dtype=int))
    with pytest.raises(ValueError, match="mask"):
        Measure(("month",), np.zeros(3, dtype=int), np.zeros(2, dtype=bool))
    with pytest.raises(ValueError, match="zero"):
        Measure(("month",), np.array([1, 2]), np.array([True, False]))


def test_measure_bound_is_exact_or_lower_bound():
    assert m(("month",), [1]).bound == "exact"
    assert m(("month",), [1], bound="lower_bound").bound == "lower_bound"
    with pytest.raises(ValueError, match="bound"):
        m(("month",), [1], bound="approximately")


def test_valid_snapshot_checks_cleanly():
    s = make()
    report = flow_check(s)
    assert report.violations == [] and report.unavailable == []
    assert report.checked > 0 and report.ok
    assert s.by_team(s.open_end).values.tolist() == [[5, 8]]


def test_snapshot_arrays_are_write_protected():
    with pytest.raises(ValueError, match="read-only"):
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
        ({"persons": ("nobody",)}, "persons.*roster"),
        ({"sourced_by_person": m(("person", "month"), [[1, 1], [1, 1]])}, "shape"),
    ],
)
def test_shape_and_type_errors_raise(over, message):
    with pytest.raises(ValueError, match=message):
        make(**over)


def test_open_identity_violation_is_named():
    report = flow_check(make(open_end=lm([[2, 4], [3, 9]])))
    (problem,) = report.violations
    assert "open_start + admissions + reopened - wins - losses - deleted" in problem
    assert "source=Outbound" in problem and "2025-03" in problem


def test_open_identity_includes_reopened_and_deleted():
    # Paid 2025-02: 1 + 2 + reopened 1 - wins 0 - losses 1 - deleted 1 = 2
    ok = make(reopened=lm([[1, 0], [0, 0]]), deleted=lm([[1, 0], [0, 0]]))
    assert flow_check(ok).violations == []
    bad = make(reopened=lm([[1, 0], [0, 0]]))  # forgot the deletion
    assert any("source=Paid 2025-02" in p for p in flow_check(bad).violations)


def test_queue_identity_violation_is_named():
    report = flow_check(make(arrivals=lm([[3, 3], [2, 9]])))
    assert any("queue_start + arrivals" in p for p in report.violations)


def test_exits_count_in_the_queue_identity():
    exits = np.zeros((2, 2, 2), dtype=int)
    exits[0, 0, 0] = 1  # one rejected_fit from Paid in 2025-02
    ok = make(
        exits=Measure(("lane", "month", "reason"), exits),
        queue_start=lm([[0, 0], [0, 0]]),
        queue_end=lm([[0, 0], [0, 0]]),
        outstanding_episodes=(),
    )
    assert flow_check(ok).violations == []


def test_continuity_violation_is_named():
    s = make(open_start=lm([[1, 3], [1, 3]]), open_end=lm([[2, 5], [3, 4]]))
    assert any("continuity" in p for p in flow_check(s).violations)


def test_capacity_inequality_counts_reopened_and_is_checked_per_team():
    # team admits 5 in 2025-03; room = capacity - open_start + wins + losses + deleted
    s = make(carrying_capacity=m(("team", "month"), [[10, 6]]))  # 6 - 5 + 2 = 3 < 5
    (problem,) = flow_check(s).violations
    assert "capacity" in problem and "2025-03" in problem and "AE" in problem
    # reopened deals also take slots: room is 8 - 5 + 2 = 5, 5 admissions fit, plus 1 reopened do not
    tight = make(
        carrying_capacity=m(("team", "month"), [[10, 8]]),
        reopened=lm([[0, 1], [0, 0]]),
        open_end=lm([[2, 5], [3, 4]]),
        open_start=lm([[1, 2], [1, 3]]),
    )
    assert any("capacity" in p for p in flow_check(tight).violations)
    assert (
        flow_check(make(carrying_capacity=m(("team", "month"), [[10, 8]]))).violations
        == []
    )


def test_a_team_above_capacity_after_a_departure_is_not_a_violation_unless_it_admits():
    over = {
        "arrivals": lm([[3, 0], [2, 0]]),
        "admissions": lm([[2, 0], [2, 0]]),
        "opportunities_created": lm([[2, 0], [2, 0]]),
        "open_end": lm([[2, 1], [3, 2]]),
        "carrying_capacity": m(("team", "month"), [[10, 1]]),  # stock 5 > capacity 1
    }
    assert flow_check(make(**over)).violations == []
    admits = dict(over, arrivals=lm([[3, 1], [2, 0]]), admissions=lm([[2, 1], [2, 0]]))
    admits.update(queue_end=lm([[1, 1], [0, 0]]), open_end=lm([[2, 2], [3, 2]]))
    admits.update(opportunities_created=lm([[2, 1], [2, 0]]))
    (problem,) = flow_check(make(**admits)).violations
    assert "capacity" in problem


def test_missing_cells_are_unavailable_with_a_reason_not_failed():
    masked = Measure(
        ("lane", "month"),
        np.array([[2, 4], [3, 0]]),
        np.array([[False, False], [False, True]]),
    )
    assert flow_check(make(open_end=lm([[2, 4], [3, 9]]))).violations != []
    report = flow_check(make(open_end=masked))
    assert report.violations == []
    reasons = dict(report.unavailable)
    assert "source=Outbound 2025-03 open identity" in reasons
    assert "missing: open_end" in reasons["source=Outbound 2025-03 open identity"]


def test_one_masked_exit_reason_does_not_crash_the_aggregate():
    exits = np.zeros((2, 2, 2), dtype=int)
    exits[0, 0, 0] = 1  # reason 0 known and nonzero
    mask = np.zeros((2, 2, 2), dtype=bool)
    mask[0, 0, 1] = True  # reason 1 masked in the same cell
    s = make(exits=Measure(("lane", "month", "reason"), exits, mask))
    report = flow_check(s)  # must not raise
    assert any("exits" in why for _, why in report.unavailable)


def test_lower_bound_measures_cannot_pass_as_exact():
    s = make(arrivals=lm([[3, 3], [2, 2]], bound="lower_bound"))
    report = flow_check(s)
    assert report.violations == []
    assert report.unavailable
    assert all("lower_bound: arrivals" in why for _, why in report.unavailable)
    assert s.by_team(s.arrivals).bound == "lower_bound"


def test_counts_cover_every_check_made():
    clean = flow_check(make())
    lower = flow_check(make(arrivals=lm([[3, 3], [2, 2]], bound="lower_bound")))
    assert lower.checked < clean.checked
    assert clean.checked - lower.checked == len(lower.unavailable)


def test_pending_requisitions_are_typed():
    req = PendingRequisition("REQ-1", "AE", "AE", "2025-05-01")
    assert make(pending_requisitions=(req,)).pending_requisitions == (req,)
    with pytest.raises(ValueError, match="team"):
        make(
            pending_requisitions=(PendingRequisition("R", "Nope", "AE", "2025-05-01"),)
        )


def test_pending_requisitions_may_carry_a_non_ae_role_on_a_team_outside_the_snapshot():
    bdr = PendingRequisition("REQ-2", "BDR", "BDR", "2025-05-01")
    assert make(pending_requisitions=(bdr,)).pending_requisitions == (bdr,)
    with pytest.raises(
        ValueError, match="team"
    ):  # an AE requisition still needs an AE team
        make(
            pending_requisitions=(PendingRequisition("R", "Nope", "AE", "2025-05-01"),)
        )


def test_outstanding_episodes_must_reproduce_the_queue_at_the_last_month():
    with pytest.raises(ValueError, match="outstanding"):
        make(outstanding_episodes=())  # queue_end Paid is 1
    too_many = (
        OutstandingEpisode("source=Paid", "lead-9", 1, "2025-03-04", 0),
        OutstandingEpisode("source=Paid", "lead-8", 2, "2025-02-04", 1),
    )
    with pytest.raises(ValueError, match="outstanding"):
        make(outstanding_episodes=too_many)


def test_outstanding_episode_age_is_months_to_the_last_month():
    with pytest.raises(ValueError, match="age"):
        make(
            outstanding_episodes=(
                OutstandingEpisode("source=Paid", "lead-9", 1, "2025-02-04", 0),
            )
        )
    ok = make(
        queue_end=lm([[1, 1], [0, 0]]),
        outstanding_episodes=(
            OutstandingEpisode("source=Paid", "lead-9", 2, "2025-02-04", 1),
        ),
    )
    assert ok.outstanding_episodes[0].age_months == 1


def test_lower_bound_queue_skips_the_outstanding_reconciliation():
    s = make(
        queue_end=lm([[1, 1], [0, 0]], bound="lower_bound"),
        outstanding_episodes=(),
    )
    assert s.outstanding_episodes == ()


def test_roster_observations_are_typed_and_validated():
    with pytest.raises(ValueError, match="role"):
        RosterObservations(
            (
                RosterObservation(
                    "x",
                    "Chef",
                    "T",
                    None,
                    "2024-01-01",
                    None,
                    None,
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:00:00Z",
                ),
            )
        )
    with pytest.raises(ValueError, match="end_date"):
        RosterObservations(
            (
                RosterObservation(
                    "x",
                    "AE",
                    "T",
                    None,
                    "2024-01-01",
                    "2023-01-01",
                    None,
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:00:00Z",
                ),
            )
        )
    ae = RosterObservation(
        "AE-3",
        "AE",
        "AE",
        None,
        "2025-06-01",
        None,
        "2025-04-01",
        "2025-02-01T00:00:00Z",
        "2025-02-01T00:00:00Z",
    )
    moved = RosterObservation(
        "AE-3",
        "AE",
        "AE",
        None,
        "2025-06-01",
        None,
        "2025-04-01",
        "2025-05-02T00:00:00Z",
        "2025-05-02T00:00:00Z",
    )
    roster = RosterObservations((ae, moved))
    assert roster.persons() == ("AE-3",)
    assert roster.latest("AE-3", known_at="2025-03-01T00:00:00Z") == ae
    assert roster.latest("AE-3", known_at="2025-06-01T00:00:00Z") == moved
    assert roster.latest("AE-3", known_at="2025-01-01T00:00:00Z") is None


# ---- DealObservations -------------------------------------------------

S = "datetime64[s]"
D = "datetime64[D]"


def deals(**over):
    """d1: lost, reopened, won (two spells). d2: open, moved lane on 02-20 (learned 02-25)."""
    parts = {
        "lanes": LANES,
        "stages": ("Discovery", "Proposal", "Closed Won", "Closed Lost"),
        "deal_ids": np.array(["d1", "d2"]),
        "created": np.array(["2025-01-10", "2025-02-01"], dtype=D),
        "observed_from": np.array(["2025-01-01", "2025-01-01"], dtype=D),
        "observed_to": np.array(["2025-05-31", "2025-05-31"], dtype=D),
        "stage_history_complete": np.array([True, False]),
        "lane_deal": np.array([0, 1, 1]),
        "lane_index": np.array([0, 1, 0]),
        "lane_valid_from": np.array(
            ["2025-01-10", "2025-02-01", "2025-02-20"], dtype=D
        ),
        "lane_recorded_at": np.array(
            ["2025-01-10T09:00:00", "2025-02-01T09:00:00", "2025-02-25T09:00:00"],
            dtype=S,
        ),
        "transition_deal": np.array([0, 0, 0, 0, 1]),
        "transition_stage": np.array([0, 3, 1, 2, 1]),
        "transition_effective": np.array(
            [
                "2025-01-10T09:00:00",
                "2025-03-01T10:00:00",
                "2025-04-01T10:00:00",
                "2025-04-20T10:00:00",
                "2025-02-20T09:00:00",
            ],
            dtype=S,
        ),
        "transition_recorded": np.array(
            [
                "2025-01-10T09:00:00",
                "2025-03-01T10:00:00",
                "2025-04-01T10:00:00",
                "2025-04-20T10:00:00",
                "2025-02-25T09:00:00",
            ],
            dtype=S,
        ),
        "amount_deal": np.array([0, 0, 1]),
        "amount_cents": np.array([1000000, 1200000, 500000]),
        "amount_effective": np.array(
            ["2025-01-10T09:00:00", "2025-02-05T09:00:00", "2025-02-01T09:00:00"],
            dtype=S,
        ),
        "amount_recorded": np.array(
            ["2025-01-10T09:00:00", "2025-02-05T09:00:00", "2025-02-01T09:00:00"],
            dtype=S,
        ),
        "spell_deal": np.array([0, 0, 1]),
        "spell_seq": np.array([1, 2, 1]),
        "spell_start": np.array(["2025-01-10", "2025-04-01", "2025-02-01"], dtype=D),
        "spell_end": np.array(["2025-03-01", "2025-04-20", "NaT"], dtype=D),
        "spell_outcome": np.array([LOST, WON, OPEN], dtype=np.int8),
        "spell_close_date": np.array(["2025-03-01", "2025-04-18", "NaT"], dtype=D),
        "spell_end_recorded_at": np.array(
            ["2025-03-01T10:00:00", "2025-04-20T10:00:00", "NaT"], dtype=S
        ),
    }
    parts.update(over)
    return DealObservations(**parts)


def test_valid_observations_slices_and_spells():
    obs = deals()
    assert obs.n_deals == 2
    assert obs.n_spells(0) == 2 and obs.n_spells(1) == 1
    assert obs.reopened(0) and not obs.reopened(1)
    assert obs.spells(0)[1] == (
        2,
        np.datetime64("2025-04-01"),
        np.datetime64("2025-04-20"),
        WON,
        np.datetime64("2025-04-18"),
    )
    stages, effective = obs.transitions(0)
    assert stages.tolist() == [0, 3, 1, 2]
    assert effective[-1] == np.datetime64("2025-04-20T10:00:00")
    assert obs.amounts(1)[1].tolist() == [500000]


def test_knowledge_time_filters_predictors():
    obs = deals()
    known = np.datetime64("2025-03-15T00:00:00")
    assert obs.transitions(0, known_at=known)[0].tolist() == [0, 3]
    assert obs.amounts(0, known_at=np.datetime64("2025-02-01T00:00:00"))[
        1
    ].tolist() == [1000000]
    # the lane change effective 02-20 was only learned 02-25
    assert (
        obs.lane_at(
            1,
            np.datetime64("2025-03-01"),
            known_at=np.datetime64("2025-02-22T00:00:00"),
        )
        == 1
    )
    assert obs.lane_at(1, np.datetime64("2025-03-01")) == 0
    assert obs.lane_at(1, np.datetime64("2025-02-10")) == 1


def test_a_deleted_spell_is_a_censoring_outcome_without_a_close_date():
    obs = deals(
        spell_outcome=np.array([LOST, WON, DELETED], dtype=np.int8),
        spell_end=np.array(["2025-03-01", "2025-04-20", "2025-05-30"], dtype=D),
        spell_end_recorded_at=np.array(
            ["2025-03-01T10:00:00", "2025-04-20T10:00:00", "2025-05-30T23:00:00"],
            dtype=S,
        ),
    )
    assert obs.spells(1)[0][3] == DELETED


def test_observation_arrays_are_write_protected():
    with pytest.raises(ValueError, match="read-only"):
        deals().spell_outcome[0] = WON


def test_policies_are_declared():
    obs = deals()
    assert obs.reopen_policy == "selling_spells"
    assert obs.missing_first_stage_policy == "unknown_until_first_transition"
    assert (
        "recorded_at" in DealObservations.__doc__
        and "CloseDate" in DealObservations.__doc__
    )


@pytest.mark.parametrize(
    ("over", "message"),
    [
        (
            {
                "spell_end": np.array(
                    ["2025-03-01", "2025-04-20", "2025-05-01"], dtype=D
                )
            },
            "open spell",
        ),
        (
            {"spell_end": np.array(["2025-03-01", "NaT", "NaT"], dtype=D)},
            "closed spell",
        ),
        (
            {"spell_end": np.array(["2025-01-01", "2025-04-20", "NaT"], dtype=D)},
            "ends before it starts",
        ),
        ({"spell_seq": np.array([1, 3, 1])}, "spell_seq"),
        (
            {
                "spell_start": np.array(
                    ["2025-01-10", "2025-02-15", "2025-02-01"], dtype=D
                )
            },
            "overlap",
        ),
        (
            {"spell_deal": np.array([0, 0, 0]), "spell_seq": np.array([1, 2, 3])},
            "has no spell",
        ),
        ({"spell_outcome": np.array([LOST, 9, OPEN], dtype=np.int8)}, "outcome code"),
        (
            {"spell_close_date": np.array(["2025-03-01", "NaT", "NaT"], dtype=D)},
            "close date",
        ),
        (
            {
                "spell_end_recorded_at": np.array(
                    ["NaT", "2025-04-20T10:00:00", "NaT"], dtype=S
                )
            },
            "recorded",
        ),
        ({"lane_index": np.array([0, 5, 0])}, "lane index"),
        ({"lane_deal": np.array([0, 0, 0])}, "has no lane"),
        ({"transition_stage": np.array([0, 3, 1, 9, 1])}, "stage index"),
        ({"transition_deal": np.array([0, 1, 0, 0, 1])}, "sorted"),
        ({"amount_cents": np.array([1, 2])}, "amount_cents"),
        ({"deal_ids": np.array(["d1", "d1"])}, "duplicate deal id"),
        (
            {"observed_to": np.array(["2024-12-01", "2025-05-31"], dtype=D)},
            "observed_from",
        ),
        ({"created": np.array(["2025-02-10", "2025-02-01"], dtype=D)}, "precedes"),
    ],
)
def test_observation_errors_raise(over, message):
    with pytest.raises(ValueError, match=message):
        deals(**over)

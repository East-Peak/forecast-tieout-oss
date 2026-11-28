"""Loader for golden fixture B (the workload): its expected table as a `Snapshot`."""

from pathlib import Path

import numpy as np
import yaml

from .snapshot import Measure, RosterObservation, RosterObservations, Snapshot

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "workload_b"


def admissions_of(expected: dict, lane: str) -> list[int]:
    return expected["lane_tables"][lane]["admissions"]


def snapshot_from_tables(inputs: dict, expected: dict) -> Snapshot:
    lanes = tuple(inputs["lanes"])
    team = inputs["team"]
    months = tuple(inputs["months"])
    reasons = tuple(expected["exit_reasons"])
    tables = [expected["lane_tables"][k] for k in lanes]
    lane_inputs = [inputs["lane_inputs"][k] for k in lanes]

    def lane_measure(rows):
        return Measure(("lane", "month"), np.array(rows, dtype=np.int64))

    def lane_measure_or_masked(key):
        rows = [li[key] for li in lane_inputs]
        missing = np.array([r is None for r in rows])[:, None] & np.ones(
            (1, len(months)), dtype=bool
        )
        values = np.array(
            [[0] * len(months) if r is None else r for r in rows], dtype=np.int64
        )
        return Measure(("lane", "month"), values, missing)

    def from_tables(field):
        return lane_measure([t[field] for t in tables])

    exits = np.array(
        [
            [[t["exits"][r][m] for r in reasons] for m in range(len(months))]
            for t in tables
        ],
        dtype=np.int64,
    )
    team_table = expected["team_tables"][team]
    n_lane, n_month = len(lanes), len(months)
    roster = RosterObservations(
        tuple(
            RosterObservation(
                person_id=r["name"],
                role=r["role"],
                team=r["team"],
                segment=None,
                start_date=r["start"],
                end_date=None,
                planned_start=r.get("planned_start"),
                effective_at=f"{r['start']}T00:00:00Z",
                recorded_at=f"{r['start']}T00:00:00Z",
            )
            for r in inputs["roster"]
        )
    )
    bdrs = [r for r in inputs["roster"] if r.get("sources_lane")]
    sourced = [admissions_of(expected, r["sources_lane"]) for r in bdrs]
    exposure = np.zeros((n_lane, n_month))
    for r in bdrs:  # a BDR counts 1.0 in every month here
        exposure[lanes.index(r["sources_lane"])] += 1.0
    zeros = np.zeros((n_lane, n_month), dtype=np.int64)

    def team_measure(field, dtype=np.int64):
        return Measure(("team", "month"), np.array([team_table[field]], dtype=dtype))

    return Snapshot(
        lanes=lanes,
        teams=(team,),
        months=months,
        exit_reasons=reasons,
        lane_team=(team,) * len(lanes),
        leads=lane_measure_or_masked("leads"),
        mqls=lane_measure_or_masked("mqls"),
        arrivals=lane_measure([li["arrivals"] for li in lane_inputs]),
        queue_start=from_tables("queue_start"),
        admissions=from_tables("admissions"),
        exits=Measure(("lane", "month", "reason"), exits),
        queue_end=from_tables("queue_end"),
        opportunities_created=from_tables("admissions"),  # each admission creates one
        reopened=lane_measure(zeros),
        deleted=lane_measure(zeros),
        persons=tuple(r["name"] for r in bdrs),
        sourced_by_person=Measure(
            ("person", "month"),
            np.array(sourced, dtype=np.int64).reshape(len(bdrs), n_month),
        ),
        bdr_exposure=Measure(("lane", "month"), exposure),
        roster=roster,
        outstanding_episodes=(),
        open_start=from_tables("open_start"),
        wins=from_tables("wins"),
        losses=from_tables("losses"),
        open_end=from_tables("open_end"),
        bookings_cents=from_tables("bookings_cents"),
        spend_cents=lane_measure([li["spend_cents"] for li in lane_inputs]),
        heads=team_measure("heads"),
        ramped_heads=team_measure("ramped_heads"),
        ramp_exposure=team_measure("ramp_exposure", np.float64),
        carrying_capacity=team_measure("carrying_capacity"),
    )


def load_workload_b() -> tuple[Snapshot, dict, dict]:
    """(snapshot, inputs, expected) for golden fixture B."""
    inputs = yaml.safe_load((FIXTURE_DIR / "inputs.yaml").read_text())
    expected = yaml.safe_load((FIXTURE_DIR / "expected.yaml").read_text())
    return snapshot_from_tables(inputs, expected), inputs, expected

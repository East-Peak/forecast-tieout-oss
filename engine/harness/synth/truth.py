"""The ground truth: the simulation's own monthly stock-and-flow account as a contract `Snapshot`.

Lanes are `segment=<segment>;source=<source>`, where source is the attribution
the business recorded (a lead whose campaign was lost is in `source=Unknown`).
Wins and losses are dated by the closing transition (when the record changed),
bookings by the final effective close date and amount. Truth is for judging; no
evidence or planning code may read it.
"""

import json
from datetime import date
from pathlib import Path

import numpy as np

from ..contract.snapshot import (
    Measure,
    OutstandingEpisode,
    PendingRequisition,
    RosterObservation,
    RosterObservations,
    Snapshot,
)
from .people import day_of
from .sim import EXIT_REASONS, Simulation, iso

MEASURE_NAMES = [
    "leads",
    "mqls",
    "arrivals",
    "queue_start",
    "admissions",
    "reopened",
    "exits",
    "queue_end",
    "opportunities_created",
    "open_start",
    "wins",
    "losses",
    "deleted",
    "open_end",
    "bookings_cents",
    "spend_cents",
    "sourced_by_person",
    "bdr_exposure",
    "heads",
    "ramped_heads",
    "ramp_exposure",
    "carrying_capacity",
]


def split_cents(total: int, weights: list[float]) -> list[int]:
    """Integer shares of `total` in proportion to `weights` (largest remainder, ties to the earlier)."""
    scale = sum(weights)
    exact = [total * w / scale for w in weights]
    out = [int(x) for x in exact]
    order = sorted(range(len(out)), key=lambda i: (-(exact[i] - out[i]), i))
    for i in order[: total - sum(out)]:
        out[i] += 1
    return out


def _shift(a: np.ndarray) -> np.ndarray:
    return np.concatenate([np.zeros_like(a[:, :1]), a[:, :-1]], axis=1)


def month_label(sim: Simulation, mi: int) -> str:
    y, m = divmod(sim.m0 + mi, 12)
    return f"{y}-{m + 1:02d}"


def build_truth(sim: Simulation) -> Snapshot:
    p, F, n = sim.p, sim.F, sim.n_months
    lanes, teams = sim.lane_keys, tuple(sim.teams)
    months = tuple(month_label(sim, i) for i in range(n))
    started = [x for x in sim.people if x.start <= sim.d1]
    # bookings: the final amount of every won new-business deal, in its final effective close month
    bookings = np.zeros((len(lanes), n), dtype=np.int64)
    for o in sim.opps:
        if o.status == "won" and sim.mon(o.close_day) >= 0:
            bookings[o.lane, sim.mon(o.close_day)] += o.cents
    spend = np.zeros((len(lanes), n), dtype=np.int64)
    for ci, c in enumerate(p.campaigns):
        lane_of = [sim.lane_ix[(s, c.source)] for s in c.segment_mix]
        for mi in range(n):
            spend[lane_of, mi] += split_cents(
                sim.campaign_spend[ci][mi], list(c.segment_mix.values())
            )
    exposure = np.zeros((len(lanes), n))
    heads, ramped, ramp_exp = (np.zeros((len(teams), n)) for _ in range(3))
    for mi in range(n):
        y, m = divmod(sim.m0 + mi, 12)
        mid, eom = (
            day_of(date(y, m + 1, 15)),
            day_of(date(y + (m == 11), (m + 1) % 12 + 1, 1)) - 1,
        )
        for b in sim.bdrs:
            exposure[sim.lane_ix[(b.segment, "Outbound")], mi] += b.ramp_factor(mid)
        for ti, t in enumerate(teams):
            for ae in sim.aes[t]:
                if ae.start <= eom < ae.leave_day:
                    heads[ti, mi] += 1
                    ramped[ti, mi] += ae.ramp_from <= eom
                ramp_exp[ti, mi] += ae.ramp_factor(mid)
    persons = [x for x in started if x.role in ("AE", "BDR")]
    ceiling = np.array([sim.ceiling[t] for t in teams])[:, None]
    ints = {
        "leads": F["leads"],
        "mqls": F["mqls"],
        "arrivals": F["arrivals"],
        "queue_start": _shift(F["queue_end"]),
        "admissions": F["admissions"],
        "reopened": F["reopened"],
        "queue_end": F["queue_end"],
        "opportunities_created": F["opp_created"],
        "open_start": _shift(F["open_end"]),
        "wins": F["wins"],
        "losses": F["losses"],
        "deleted": F["deleted"],
        "open_end": F["open_end"],
        "bookings_cents": bookings,
        "spend_cents": spend,
    }
    measures = {k: Measure(("lane", "month"), v) for k, v in ints.items()}
    measures["exits"] = Measure(("lane", "month", "reason"), sim.exits)
    measures["sourced_by_person"] = Measure(
        ("person", "month"),
        np.array([sim.sourced[sim.pix[x.pid]] for x in persons]).reshape(
            len(persons), n
        ),
    )
    measures["bdr_exposure"] = Measure(("lane", "month"), exposure)
    measures["heads"] = Measure(("team", "month"), heads.astype(np.int64))
    measures["ramped_heads"] = Measure(("team", "month"), ramped.astype(np.int64))
    measures["ramp_exposure"] = Measure(("team", "month"), ramp_exp)
    measures["carrying_capacity"] = Measure(
        ("team", "month"), (ramped * ceiling).astype(np.int64)
    )
    seg_of_team = {s.team: s.name for s in p.segments}
    rows = []
    for x in started:
        planned = iso(x.planned) if x.planned else None
        seg = x.segment or seg_of_team.get(x.team)
        rows.append(
            RosterObservation(
                x.pid,
                x.role,
                x.team,
                seg,
                iso(x.start),
                None,
                planned,
                f"{iso(x.start)}T00:00:00Z",
                f"{iso(x.start)}T00:00:00Z",
            )
        )
        if x.end is not None:
            rows.append(
                RosterObservation(
                    x.pid,
                    x.role,
                    x.team,
                    seg,
                    iso(x.start),
                    iso(x.end),
                    planned,
                    f"{iso(x.end)}T00:00:00Z",
                    f"{iso(x.end)}T00:00:00Z",
                )
            )
    pending = tuple(
        PendingRequisition(x.req_id, x.team, x.role, iso(x.planned))
        for x in sim.people
        if x.start > sim.d1
        and x.req_id
        and x.team in teams  # TODO: the contract only holds AE-team requisitions
    )
    last = n - 1
    episodes = []
    for t, queue in sim.queues.items():
        for lane_pos, age, lead in queue.items():
            episodes.append(
                OutstandingEpisode(
                    lanes[sim.team_lanes[t][lane_pos]],
                    f"00QSY{lead.n:010d}",
                    lead.offers,
                    iso(lead.offer_day),
                    last - sim.mon(lead.offer_day),
                )
            )
    return Snapshot(
        lanes=tuple(lanes),
        teams=teams,
        months=months,
        exit_reasons=EXIT_REASONS,
        lane_team=tuple(sim.seg_spec[s].team for s, _ in sim.lane_defs),
        persons=tuple(x.pid for x in persons),
        roster=RosterObservations(tuple(rows)),
        outstanding_episodes=tuple(episodes),
        pending_requisitions=pending,
        **measures,
    )


def save_truth(truth: Snapshot, path: Path) -> None:
    body = {
        "lanes": truth.lanes,
        "teams": truth.teams,
        "months": truth.months,
        "exit_reasons": truth.exit_reasons,
        "lane_team": truth.lane_team,
        "persons": truth.persons,
        "measures": {k: getattr(truth, k).values.tolist() for k in MEASURE_NAMES},
        "roster": [vars(r) for r in truth.roster.rows],
        "outstanding_episodes": [vars(e) for e in truth.outstanding_episodes],
        "pending_requisitions": [vars(r) for r in truth.pending_requisitions],
    }
    Path(path).write_text(json.dumps(body))


def load_truth(path: Path) -> Snapshot:
    """The truth file as a contract `Snapshot`."""
    b = json.loads(Path(path).read_text())
    axes = {
        "exits": ("lane", "month", "reason"),
        "sourced_by_person": ("person", "month"),
    }
    team_axes = ("heads", "ramped_heads", "ramp_exposure", "carrying_capacity")
    floats = ("bdr_exposure", "ramp_exposure")
    measures = {}
    for name, values in b["measures"].items():
        ax = axes.get(
            name, ("team", "month") if name in team_axes else ("lane", "month")
        )
        measures[name] = Measure(
            ax, np.array(values, dtype=float if name in floats else np.int64)
        )
    return Snapshot(
        lanes=tuple(b["lanes"]),
        teams=tuple(b["teams"]),
        months=tuple(b["months"]),
        exit_reasons=tuple(b["exit_reasons"]),
        lane_team=tuple(b["lane_team"]),
        persons=tuple(b["persons"]),
        roster=RosterObservations(tuple(RosterObservation(**r) for r in b["roster"])),
        outstanding_episodes=tuple(
            OutstandingEpisode(**e) for e in b["outstanding_episodes"]
        ),
        pending_requisitions=tuple(
            PendingRequisition(**r) for r in b["pending_requisitions"]
        ),
        **measures,
    )

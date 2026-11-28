"""The observable truth: what a perfect reader of the extracts could know at the final extract.

Built from the simulation's event log and the extract dates, never by reading written
extracts back. Rules (design R1 to R8 and the contract rulings), at K = the final extract:

- a record that appears in no extract does not exist in it. The one exception that keeps
  the books balanced: a lead-derived opportunity created and deleted between two extracts
  is a ghost: its lead says Admitted, so it counts as admitted and deleted (in the month of
  the first extract lacking it). A directly created ghost does not exist at all;
- a deleted record exists until the first extract lacking it, then has outcome `deleted`;
  it leaves the open stock then, if its history as of the last extract containing it is open;
- a record's transitions are its history as of the last extract containing it, so a closing
  after the last extract that showed the record is unseen;
- amounts, close dates and bookings are as known at K: later amendments and corrections are
  absent; MQL and offer dates count when their rows were recorded by K;
- a lane is the segment of the account tier as first observed (assumed since creation; a
  re-tier before the first sighting moves the deal) by the recorded source; an admitted
  episode follows its opportunity's lane;
- outstanding episodes are those unresolved by rows recorded by K.

Latent quantities are masked: lane spend (kept by program in a side table), ramp exposure,
BDR exposure, carrying capacity and ramped heads.
"""

import numpy as np

from ..contract.snapshot import (
    Measure,
    OutstandingEpisode,
    RosterObservations,
    Snapshot,
)
from .sim import CLOSED_WON, EXIT_REASONS, Simulation, sfid, ts
from .truth import _shift, month_label, pending_requisitions, roster_rows

MASK_REASONS = {
    "spend_cents": "lane spend is not recorded: the spend sheet has programs, not lanes (see observable_spend_by_program.json)",
    "bdr_exposure": "BDR ramp exposure depends on the latent individual ramp",
    "ramped_heads": "ramped heads depend on the latent carrying ramp",
    "ramp_exposure": "ramp exposure depends on the latent carrying ramp",
    "carrying_capacity": "carrying capacity depends on the latent ceiling and carrying ramp",
}


def _closed(stage: str) -> bool:
    return stage.startswith("Closed")


def build_observable(sim: Simulation, extract_days: list[int]):
    """(Snapshot, notes, spend by program) as known at the last of `extract_days`."""
    E = [ts(d, 23 * 3600) for d in sorted(extract_days)]
    K, kday = E[-1], day_of_ts(E[-1])
    n = sim.mon(kday) + 1
    L = len(sim.lane_defs)
    z = lambda: np.zeros((L, n), dtype=np.int64)
    a = {
        k: z()
        for k in (
            "leads",
            "mqls",
            "arrivals",
            "adm",
            "reo",
            "wins",
            "losses",
            "deleted",
            "bookings",
        )
    }
    exits = np.zeros((L, n, 2), dtype=np.int64)
    sourced = np.zeros((len(sim.people), n), dtype=np.int64)
    notes = dict.fromkeys(
        (
            "never_observed_records",
            "ghost_lead_derived_opportunities",
            "observed_deletions",
            "opportunities_closing_after_final_extract",
            "amendments_or_corrections_after_final_extract",
            "accounts_retiered_before_first_sighting",
            "opportunities_with_retiered_accounts",
            "mql_dates_recorded_after_final_extract",
            "opportunities_in_a_different_lane_than_at_creation",
        ),
        0,
    )

    def month(stamp: str) -> int:
        return (int(stamp[:4]) * 12 + int(stamp[5:7]) - 1) - sim.m0

    seg_of_tier = {sp.tier: sp.name for sp in sim.p.segments}

    def first_observed_lane(o):
        """Lane with the segment of the account tier as first observed (None: never observed)."""
        seen = next(
            (e for e in E if e >= o.created and (o.dead is None or o.dead > e)), None
        )
        if seen is None:
            return None
        tier = ([o.account.tier] + [t for w, t in o.account.tier_changes if w <= seen])[
            -1
        ]
        return sim.lane_ix.get((seg_of_tier[tier], o.source), o.lane)

    opp_lane = {o.n: first_observed_lane(o) for o in sim.opps if o.created <= K}
    # episodes: (lead, seq, offered month, outcome, outcome month); the lane of an admitted
    # episode is the lane of the opportunity it became, otherwise the lead's own
    episodes, outstanding = [], []
    for lead in sim.leads:
        if lead.created > K:
            continue
        if sim.mon(day_of_ts(lead.created)) >= 0:
            a["leads"][lead.lane, sim.mon(day_of_ts(lead.created))] += 1
        current, seq = None, 0
        for _, when, name, new, _by in sorted(lead.rows, key=lambda r: (r[1], r[0])):
            if when > K:
                if name == "MQL_Date__c":
                    notes["mql_dates_recorded_after_final_extract"] += 1
                continue
            if name == "MQL_Date__c":
                a["mqls"][lead.lane, month(new)] += 1
            elif name == "Sales_Offered_Date__c":
                seq += 1
                current = [lead, seq, month(when), None, None, new]
                episodes.append(current)
            elif (
                name == "Disposition__c"
                and new is not None
                and current
                and current[3] is None
            ):
                current[3], current[4] = new, month(when)
        if current and current[3] is None:
            outstanding.append((lead, (current[1], current[5])))
    for lead, seq, m_offer, outcome, m_out, _on in episodes:
        lane = lead.lane
        if (
            outcome == "Admitted"
            and lead.conv
            and opp_lane.get(lead.conv[2]) is not None
        ):
            lane = opp_lane[lead.conv[2]]
        a["arrivals"][lane, m_offer] += 1
        if outcome == "Admitted":
            a["adm"][lane, m_out] += 1
        elif outcome:
            exits[lane, m_out, 0 if outcome == "Rejected" else 1] += 1
    outstanding_lane = {lead.n: lead.lane for lead, _ in outstanding}

    for o in sim.opps:
        if o.created > K:
            continue
        seen = [e for e in E if e >= o.created and (o.dead is None or o.dead > e)]
        deleted_at = next((e for e in E if o.dead and e >= o.dead), None)
        lane = opp_lane[o.n] if opp_lane[o.n] is not None else o.lane
        if lane != o.lane:
            notes["opportunities_in_a_different_lane_than_at_creation"] += 1
        if not seen and o.lead is None:
            notes["never_observed_records"] += 1
            continue
        if not seen:
            notes["never_observed_records"] += 1
            notes["ghost_lead_derived_opportunities"] += 1
        shown = [i for i in o.images if seen and i[1] <= seen[-1]]
        if o.lead is None:
            m = month(o.created)
            a["arrivals"][lane, m] += 1
            a["adm"][lane, m] += 1
        if seen and o.sourcing is not None:
            sourced[sim.pix[o.sourcing.pid], month(o.created)] += 1
        is_open, prev = True, None
        for _, when, stage, _c, _cl in shown:
            if prev is not None and _closed(stage) != _closed(prev):
                if _closed(stage):
                    a["wins" if stage == CLOSED_WON else "losses"][
                        lane, month(when)
                    ] += 1
                else:
                    a["reo"][lane, month(when)] += 1
            is_open = not _closed(stage)
            prev = stage
        if deleted_at:
            notes["observed_deletions"] += 1
            if is_open:  # a ghost is admitted and deleted in the same month: it never holds a slot
                a["deleted"][lane, month(deleted_at) if seen else month(o.created)] += 1
        if shown and shown[-1][2] == CLOSED_WON and sim.mon(shown[-1][4]) >= 0:
            a["bookings"][lane, sim.mon(shown[-1][4])] += shown[-1][3]
        if o.dead is None:
            for j, i in enumerate(o.images):
                if i[1] > K and j:
                    kind = (
                        "opportunities_closing_after_final_extract"
                        if _closed(i[2]) != _closed(o.images[j - 1][2])
                        else "amendments_or_corrections_after_final_extract"
                    )
                    notes[kind] += 1
    for acct in sim.accounts:
        if acct.tier_changes:
            first = next((e for e in E if e >= acct.created), None)
            if first and acct.tier_changes[0][0] <= first:
                notes["accounts_retiered_before_first_sighting"] += 1
    notes["opportunities_with_retiered_accounts"] = sum(
        1
        for o in sim.opps
        if o.created <= K
        and o.account.tier_changes
        and o.account.tier_changes[0][0] <= K
    )

    q_end = np.cumsum(a["arrivals"] - a["adm"] - exits.sum(axis=2), axis=1)
    o_end = np.cumsum(
        a["adm"] + a["reo"] - a["wins"] - a["losses"] - a["deleted"], axis=1
    )
    started, rows = roster_rows(sim, kday)
    persons = [x for x in started if x.role in ("AE", "BDR")]
    heads = np.zeros((len(sim.teams), n), dtype=np.int64)
    for mi in range(n):
        eom = min(kday, day_of_month_end(sim, mi))
        for ti, t in enumerate(sim.teams):
            heads[ti, mi] = sum(
                1
                for ae in sim.aes[t]
                if ae.start <= eom
                and (ae.end is None or ae.end >= eom or ae.end > kday)
            )
    masked = {}

    def lane(values):
        return Measure(("lane", "month"), values)

    def hidden(name, axes, shape, dtype):
        masked[name] = MASK_REASONS[name]
        return Measure(axes, np.zeros(shape, dtype=dtype), np.ones(shape, dtype=bool))

    measures = {
        "leads": lane(a["leads"]),
        "mqls": lane(a["mqls"]),
        "arrivals": lane(a["arrivals"]),
        "queue_start": lane(_shift(q_end)),
        "admissions": lane(a["adm"]),
        "reopened": lane(a["reo"]),
        "exits": Measure(("lane", "month", "reason"), exits),
        "queue_end": lane(q_end),
        "opportunities_created": lane(a["adm"]),
        "open_start": lane(_shift(o_end)),
        "wins": lane(a["wins"]),
        "losses": lane(a["losses"]),
        "deleted": lane(a["deleted"]),
        "open_end": lane(o_end),
        "bookings_cents": lane(a["bookings"]),
        "spend_cents": hidden("spend_cents", ("lane", "month"), (L, n), np.int64),
        "sourced_by_person": Measure(
            ("person", "month"),
            np.array([sourced[sim.pix[x.pid]] for x in persons]).reshape(
                len(persons), n
            ),
        ),
        "bdr_exposure": hidden("bdr_exposure", ("lane", "month"), (L, n), float),
        "heads": Measure(("team", "month"), heads),
        "ramped_heads": hidden(
            "ramped_heads", ("team", "month"), heads.shape, np.int64
        ),
        "ramp_exposure": hidden("ramp_exposure", ("team", "month"), heads.shape, float),
        "carrying_capacity": hidden(
            "carrying_capacity", ("team", "month"), heads.shape, np.int64
        ),
    }
    last = n - 1
    episodes = [
        OutstandingEpisode(
            sim.lane_keys[outstanding_lane[lead.n]],
            sfid("lead", lead.n),
            seq,
            on,
            last - month(on),
        )
        for lead, (seq, on) in outstanding
    ]
    snapshot = Snapshot(
        lanes=tuple(sim.lane_keys),
        teams=tuple(sim.teams),
        months=tuple(month_label(sim, i) for i in range(n)),
        exit_reasons=EXIT_REASONS,
        lane_team=tuple(sim.seg_spec[s].team for s, _ in sim.lane_defs),
        persons=tuple(x.pid for x in persons),
        roster=RosterObservations(tuple(rows)),
        outstanding_episodes=tuple(episodes),
        pending_requisitions=pending_requisitions(sim, kday),
        **measures,
    )
    program_spend = {
        c.name: {
            month_label(sim, mi)[:7]: sim.campaign_spend[ci][mi]
            for mi in range(n)
            if sim.campaign_spend[ci][mi]
        }
        for ci, c in enumerate(sim.p.campaigns)
    }
    notes["masked"] = masked
    notes["known_at"] = K
    return snapshot, notes, program_spend


def day_of_ts(stamp: str) -> int:
    from datetime import date

    return date.fromisoformat(stamp[:10]).toordinal()


def day_of_month_end(sim: Simulation, mi: int) -> int:
    from datetime import date

    y, m = divmod(sim.m0 + mi, 12)
    nxt = date(y + (m == 11), (m + 1) % 12 + 1, 1)
    return nxt.toordinal() - 1

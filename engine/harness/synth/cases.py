"""Named cases: the situations the later tranches must find, located by name in the manifest."""

from datetime import date

from .people import day_of
from .run import Company
from .sim import CLOSED_LOST, CLOSED_WON, iso, sfid, ts

FY25_START = date(2025, 2, 1)


def _win_rate(opps) -> float | None:
    done = [o for o in opps if o.status in ("won", "lost")]
    return round(sum(o.status == "won" for o in done) / len(done), 4) if done else None


def _trailing_win_rate(opps, as_of: str, since: str) -> float | None:
    """Win rate of deals whose closing was on the books in (since, as_of], from history cut at `as_of`."""
    won = lost = 0
    for o in opps:
        shown = [i for i in o.images if i[1] <= as_of]
        if len(shown) < 2 or not shown[-1][2].startswith("Closed"):
            continue
        closing = next(
            (i for i in reversed(shown) if not i[2].startswith("Closed")), None
        )
        when = (
            next(i[1] for i in shown[shown.index(closing) + 1 :])
            if closing
            else shown[0][1]
        )
        if when > since:
            won += shown[-1][2] == CLOSED_WON
            lost += shown[-1][2] == CLOSED_LOST
    return round(won / (won + lost), 4) if won + lost else None


def named_cases(company: Company) -> dict:
    sim, p = company.sim, company.params
    lane = lambda seg, src: sim.lane_keys[sim.lane_ix[(seg, src)]]
    plan = day_of(p.plan_date)
    fy24 = (day_of(date(2024, 2, 1)), day_of(FY25_START))
    thin_lane = sim.lane_ix[("Enterprise", "Partner")]
    thin = [
        o
        for o in sim.opps
        if o.lane == thin_lane and fy24[0] <= o.created_day < fy24[1]
    ]

    ws = p.win_step
    step_lane = sim.lane_ix[(ws.segment, ws.source)]
    step_day = day_of(ws.on)
    in_lane = [o for o in sim.opps if o.lane == step_lane]
    plan_ts = ts(plan, 23 * 3600)
    trailing = _trailing_win_rate(in_lane, plan_ts, ts(plan - 365, 23 * 3600))

    young = [o for o in sim.opps if plan - 60 < o.created_day <= plan]
    closed = [
        o
        for o in young
        if any(i[2] in (CLOSED_WON, CLOSED_LOST) and i[1] <= plan_ts for i in o.images)
    ]

    unknown_mqls = sum(1 for x in sim.leads if x.kind == "mql" and x.campaign is None)
    mqls = sum(1 for x in sim.leads if x.kind == "mql")
    unknown = [o for o in sim.opps if sim.lane_defs[o.lane][1] == "Unknown"]

    whale = sim.whale
    reqs = [
        {
            "req_id": x.req_id,
            "team": x.team,
            "role": x.role,
            "planned_start": iso(x.planned),
            "actual_start": iso(x.start),
            "slip_days": x.start - x.planned,
        }
        for x in sim.people
        if x.req_id and x.start > x.planned
    ]
    plateau = next(c for c in p.campaigns if c.plateau)
    ci = p.campaigns.index(plateau)
    pm = (plateau.plateau.year * 12 + plateau.plateau.month - 1) - sim.m0
    lo, hi = max(pm - 6, 0), min(pm + 6, sim.n_months)
    benchmark = {}
    for team in sim.teams:
        i, spec = next(
            (i, h)
            for i, h in enumerate(p.hires, start=1)
            if h.team == team
            and h.role == "AE"
            and not h.cancelled
            and h.planned_start >= FY25_START
        )
        benchmark[team] = {
            "req_id": f"REQ-{i:03d}",
            "planned_start": spec.planned_start.isoformat(),
            "default_slip_days": 120,
        }
    return {
        "thin_slice": {
            "lane": lane("Enterprise", "Partner"),
            "window": "FY24",
            "opportunities": len(thin),
            "wins": sum(o.status == "won" for o in thin),
        },
        "improvement_understated": {
            "lane": sim.lane_keys[step_lane],
            "step_on": ws.on.isoformat(),
            "win_probability_before": ws.before,
            "win_probability_after": ws.after,
            "win_rate_before": _win_rate(
                [o for o in in_lane if step_day - 365 <= o.created_day < step_day]
            ),
            "win_rate_after": _win_rate(
                [o for o in in_lane if o.created_day >= step_day]
            ),
            "trailing_12m_win_rate_at_plan_date": trailing,
        },
        "immature_cohort": {
            "created_from": iso(plan - 59),
            "created_to": iso(plan),
            "extract": p.plan_date.isoformat(),
            "opportunities": len(young),
            "share_closed_at_plan_date": round(len(closed) / len(young), 3)
            if young
            else None,
        },
        "missing_attribution": {
            "lane_suffix": "source=Unknown",
            "unattributed_mqls": unknown_mqls,
            "share_of_mqls": round(unknown_mqls / max(mqls, 1), 4),
            "opportunities": len(unknown),
        },
        "very_large_deal": None
        if whale is None
        else {
            "opportunity_id": sfid("opp", whale.n),
            "lane": sim.lane_keys[whale.lane],
            "amount_cents": whale.cents,
            "created": iso(whale.created_day),
            "close_date": iso(whale.close_day) if whale.close_day else None,
            "status": whale.status,
        },
        "slipping_hires": reqs,
        "plateaued_lane": {
            "campaign": plateau.name,
            "lane": lane(next(iter(plateau.segment_mix)), plateau.source),
            "plateau_from": plateau.plateau.isoformat(),
            "expected_mqls_before": round(sum(sim.lam[ci][lo:pm]) / max(pm - lo, 1), 2),
            "expected_mqls_after": round(sum(sim.lam[ci][pm:hi]) / max(hi - pm, 1), 2),
        },
        "benchmark_hires": benchmark,
    }

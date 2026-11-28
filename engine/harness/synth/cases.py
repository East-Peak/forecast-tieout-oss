"""Named cases: the situations the later tranches must find, located by name in the manifest."""

from datetime import date

from .people import day_of
from .run import Company
from .sim import CLOSED_LOST, CLOSED_WON, iso, sfid, ts

FY25_START = date(2025, 2, 1)


def _win_rate(opps) -> float | None:
    done = [o for o in opps if o.status in ("won", "lost")]
    return round(sum(o.status == "won" for o in done) / len(done), 4) if done else None


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
    closing_days = {
        o.n: day_of(date.fromisoformat(o.images[-1][1][:10])) for o in in_lane
    }
    trailing = [
        o
        for o in in_lane
        if plan - 365 <= closing_days[o.n] <= plan and o.status in ("won", "lost")
    ]

    young = [o for o in sim.opps if plan - 60 < o.created_day <= plan]
    plan_ts = ts(plan, 23 * 3600)
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
    pick = next(
        (i, s)
        for i, s in enumerate(p.hires, start=1)
        if s.role == "AE" and not s.cancelled and s.planned_start >= FY25_START
    )
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
            "trailing_12m_win_rate_at_plan_date": _win_rate(trailing),
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
            "close_date": iso(whale.close_day),
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
        "counterfactual_hire": {
            "req_id": f"REQ-{pick[0]:03d}",
            "team": pick[1].team,
            "role": "AE",
            "planned_start": pick[1].planned_start.isoformat(),
            "default_slip_days": 120,
        },
    }

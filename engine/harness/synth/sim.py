"""The daily agent simulation.

People act day by day: marketing programs turn spend into MQLs, BDRs and AEs
source opportunities, a team's queue admits demand only while its AEs have room
under the carrying ceiling, and each deal runs out a fate drawn once at creation.
Nothing here forecasts: outcomes come from per-lead and per-deal latent draws,
queues and ceilings. Every random quantity is drawn from the stream of the entity
it belongs to (see rng.py), so paired runs share fates.

Accounting rule that makes the workload identities hold by construction: every
change to the open stock or the queue goes through one of the methods below, and
each of them counts its flow.
"""

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from math import ceil, exp

import numpy as np

from ..contract.keys import lane_key
from .params import SEGMENTS, SOURCES, CompanyParams, Intervention
from .people import Person, build_people, day_of
from .rng import Streams, poisson_quantile
from .workload import RoutingQueue

HOUR = 3600
T_MQL, T_OFFER, T_ADMIT, T_ADV, T_CLOSE, T_EXPIRE, T_SHED, T_EDIT = (
    9 * HOUR,
    9 * HOUR + 60,
    11 * HOUR,
    14 * HOUR,
    15 * HOUR,
    17 * HOUR,
    7 * HOUR,
    10 * HOUR,
)  # fixed times of day (seconds); every event happens before 18:00 so a 23:00 extract sees its own day
EXIT_REASONS = ("rejected_fit", "expired_no_capacity")
ADJ = (
    "Fakeco",
    "Mockly",
    "Sampleton",
    "Testbed",
    "Dummy",
    "Stubbly",
    "Mimic",
    "Pretend",
)
NOUN = (
    "Foundry",
    "Logistics",
    "Works",
    "Partners",
    "Labs",
    "Supply",
    "Freight",
    "Systems",
)
PREFIX = {
    "opp": "006",
    "lead": "00Q",
    "acct": "001",
    "camp": "701",
    "member": "00v",
    "ohist": "008",
    "ofield": "017",
    "lhist": "00L",
    "user": "005",
}
CLOSED_WON, CLOSED_LOST = "Closed Won", "Closed Lost"


@cache
def iso(day: int) -> str:
    return date.fromordinal(day).isoformat()


def ts(day: int, sec: int) -> str:
    return f"{iso(day)}T{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}Z"


def sfid(kind: str, n: int) -> str:
    return f"{PREFIX[kind]}SY{n:010d}"


def pick(weights: dict[str, float], u: float) -> str:
    total, acc = sum(weights.values()), 0.0
    for name, w in weights.items():
        acc += w / total
        if u < acc:
            return name
    return name


def month_days(day: int) -> int:
    d = date.fromordinal(day)
    return calendar.monthrange(d.year, d.month)[1]


@dataclass(slots=True)
class Account:
    n: int
    name: str
    tier: str
    country: str
    code: str | None
    created: str
    tier_changes: (
        list  # [(ts, tier)] later edits with no history; a later extract shows them
    )


@dataclass(slots=True)
class Lead:
    n: int
    key: tuple
    lane: int
    tier: str
    kind: str  # mql, outbound or clutter
    created: str
    campaign: int | None
    leadsource: str | None
    owner: str  # initial owner uid
    r: tuple
    bdr: Person | None = None
    mql_day: int | None = None
    rows: list = field(default_factory=list)  # (n, ts, field, new, by_uid)
    offers: int = 0
    offer_day: int = 0
    conv: tuple | None = None  # (ts, day, opp sfid, account sfid)


@dataclass(slots=True)
class Opp:
    n: int
    lane: int
    seg: str
    source: str
    account: Account
    owner: Person
    sourcing: Person | None
    creator_uid: str
    campaign: int | None
    leadsource: str | None
    created_day: int
    created: str
    list_cents: int
    cents: int
    base_days: tuple
    will_win: bool
    last_stage: int
    r: object
    owner0: str
    lead: Lead | None = None
    type: str = "New Business"
    images: list = field(
        default_factory=list
    )  # (n, ts, stage, amount_cents, close_day)
    owner_rows: list = field(default_factory=list)  # (n, ts, old_uid, new_uid, by_uid)
    status: str = "open"
    stage_i: int = 0
    version: int = 0
    dead: str | None = None
    reopened: bool = False
    whale: bool = False
    close_day: int = 0
    mirror: int | None = None


class Simulation:
    def __init__(
        self,
        params: CompanyParams,
        seed: int,
        intervention: Intervention,
        extract_days: tuple[int, ...] = (),
    ):
        self.p, self.streams, self.iv = params, Streams(seed), intervention
        self.d0, self.d1 = day_of(params.start), day_of(params.end)
        self.m0 = params.start.year * 12 + params.start.month - 1
        self.n_months = params.end.year * 12 + params.end.month - self.m0
        self.people = build_people(params, self.streams, intervention, self.d1)
        self.pix = {x.pid: i for i, x in enumerate(self.people)}
        self.seg_spec = {s.name: s for s in params.segments}
        self.ceiling = {s.team: s.ceiling for s in params.segments}
        self.lane_defs = [
            (s, src)
            for s in SEGMENTS
            for src in SOURCES
            if src in params.win_rate.get(s, {})
        ]
        self.lane_keys = [
            lane_key({"segment": s, "source": src}) for s, src in self.lane_defs
        ]
        self.lane_ix = {d: i for i, d in enumerate(self.lane_defs)}
        self.teams = [s.team for s in params.segments]
        self.team_lanes = {
            t: [
                i
                for i, (s, _) in enumerate(self.lane_defs)
                if self.seg_spec[s].team == t
            ]
            for t in self.teams
        }
        self.queues = {
            t: RoutingQueue(len(ls), params.queue_max_days)
            for t, ls in self.team_lanes.items()
        }
        self.aes = {
            t: [x for x in self.people if x.role == "AE" and x.team == t]
            for t in self.teams
        }
        self.bdrs = [x for x in self.people if x.role == "BDR"]
        self.cs = [x for x in self.people if x.team == "CS"]
        self.mkt = next(x for x in self.people if x.role == "Marketing")
        for c in params.campaigns:
            for s in c.segment_mix:
                assert (s, c.source) in self.lane_ix, (
                    f"{c.name}: no {c.source} lane for {s}"
                )
        shape = (len(self.lane_defs), self.n_months)
        self.F = {
            n: np.zeros(shape, dtype=np.int64)
            for n in [
                "leads",
                "mqls",
                "arrivals",
                "admissions",
                "reopened",
                "opp_created",
                "wins",
                "losses",
                "deleted",
                "queue_end",
                "open_end",
            ]
        }
        self.exits = np.zeros((*shape, 2), dtype=np.int64)
        self.sourced = np.zeros((len(self.people), self.n_months), dtype=np.int64)
        self.open_n = [0] * len(self.lane_defs)
        self.team_open = dict.fromkeys(self.teams, 0)
        self.ae_open: dict[str, list[Opp]] = {x.pid: [] for x in self.people}
        self.ev: dict[int, list] = defaultdict(list)
        self.reoffers: dict[int, list[Lead]] = defaultdict(list)
        self.leaves: dict[int, list[Person]] = defaultdict(list)
        for x in self.people:
            if x.role == "AE" and x.end is not None:
                self.leaves[x.leave_day].append(x)
        self.leads: list[Lead] = []
        self.opps: list[Opp] = []
        self.accounts: list[Account] = []
        self.counter: dict[str, int] = defaultdict(int)
        self.turned_away = 0
        self.whale: Opp | None = None
        self.campaign_spend, self.lam = self._schedules()
        self.no_delete = [
            (a + 1, day_of(_month_end(a)))
            for a in extract_days
            if a != day_of(_month_end(a))
        ]
        self.arr: dict[str, list[list[Lead]]] = {}

    # ---- bookkeeping ---------------------------------------------------
    def nid(self, kind: str) -> int:
        self.counter[kind] += 1
        return self.counter[kind]

    def mon(self, day: int) -> int:
        d = date.fromordinal(day)
        return d.year * 12 + d.month - 1 - self.m0

    def ramped(self, team: str, day: int) -> list[Person]:
        return [x for x in self.aes[team] if x.ramp_from <= day < x.leave_day]

    def room(self, team: str, day: int) -> int:
        return self.ceiling[team] * len(self.ramped(team, day)) - self.team_open[team]

    def best_ae(self, team: str, day: int) -> Person | None:
        pool = [
            x
            for x in self.ramped(team, day)
            if len(self.ae_open[x.pid]) < self.ceiling[team]
        ]
        return min(pool, key=lambda x: (len(self.ae_open[x.pid]), x.idx), default=None)

    def _schedules(self):
        p, spend, lam = self.p, [], []
        for ci, c in enumerate(p.campaigns):
            sp, lm = [], []
            for mi in range(self.n_months):
                y, m0 = divmod(self.m0 + mi, 12)
                first = day_of(date(y, m0 + 1, 1))
                live = (c.launch is None or first >= day_of(c.launch)) and (
                    c.end is None or first <= day_of(c.end)
                )
                amount = 0.0
                if live:
                    amount = (
                        c.spend
                        * (1 + p.spend_growth) ** ((first - self.d0) / 365.25)
                        * p.spend_season.get(c.source, (1.0,) * 12)[m0]
                    )
                    amount *= exp(
                        0.05 * self.streams.rng("spend", ci, mi).standard_normal()
                    )
                    for step in p.spend_steps if c.source != "Inbound" else ():
                        if first >= day_of(step.on):
                            amount *= step.factor
                    ch = self.iv.spend_change
                    if ch and ch[0] == c.name and first >= day_of(ch[1]):
                        amount *= ch[2]
                    amount = float(round(amount))
                trend_to = min(first, day_of(c.plateau)) if c.plateau else first
                trend = 1 + c.growth * max(trend_to - self.d0, 0) / 365.25
                buys = c.k * (amount / 1000) ** c.alpha if amount else 0.0
                sp.append(int(amount) * 100)
                lm.append(
                    (buys + c.base)
                    * trend
                    * p.response_season.get(c.source, (1.0,) * 12)[m0]
                    if live
                    else 0.0
                )
            spend.append(sp)
            lam.append(lm)
        return spend, lam

    # ---- the day loop --------------------------------------------------
    def run(self) -> "Simulation":
        for day in range(self.d0, self.d1 + 1):
            self.arr = {t: [[] for _ in ls] for t, ls in self.team_lanes.items()}
            for person in self.leaves.pop(day, []):
                self.depart(person, day)
            for kind, opp, ver, arg in self.ev.pop(day, []):
                if (ver < 0 or opp.version == ver) and not opp.dead:
                    getattr(self, "on_" + kind)(opp, day, arg)
            for lead in self.reoffers.pop(day, []):
                self.offer(lead, day, rejected=lead.r[8] >= self.p.p_reoffer_fit)
            self.marketing(day)
            self.outbound(day)
            self.direct(day)
            self.route(day)
            if date.fromordinal(day + 1).day == 1 or day == self.d1:
                m = self.mon(day)
                self.F["open_end"][:, m] = self.open_n
                for t, ls in self.team_lanes.items():
                    self.F["queue_end"][ls, m] = self.queues[t].sizes()
        return self

    # ---- demand --------------------------------------------------------
    def _new_lead(
        self, key, lane, kind, created_day, campaign, leadsource, owner, r, bdr=None
    ) -> Lead:
        lead = Lead(
            self.nid("lead"),
            key,
            lane,
            self.seg_spec[self.lane_defs[lane][0]].tier,
            kind,
            ts(max(created_day, self.d0 - 30), T_MQL - HOUR),
            campaign,
            leadsource,
            owner.uid,
            tuple(r),
            bdr,
        )
        self.leads.append(lead)
        if created_day >= self.d0:
            self.F["leads"][lane, self.mon(created_day)] += 1
        return lead

    def _row(self, lead: Lead, day: int, sec: int, name: str, new, by: str) -> None:
        lead.rows.append((self.nid("lhist"), ts(day, sec), name, new, by))

    def marketing(self, day: int) -> None:
        p, mi, dim = self.p, self.mon(day), month_days(day)
        for ci, c in enumerate(p.campaigns):
            lam = self.lam[ci][mi] / dim
            if lam <= 0:
                continue
            n = poisson_quantile(self.streams.rng("arr", ci, day).random(), lam)
            n_clutter = poisson_quantile(
                self.streams.rng("clut", ci, day).random(), lam * p.clutter_lead_share
            )
            for k in range(n + n_clutter):
                kind = "mql" if k < n else "clutter"
                key = ("lead", ci, day, k, kind)
                r = self.streams.rng(*key).random(12)
                seg = pick(c.segment_mix, r[0])
                lost_attribution = kind == "mql" and r[3] < p.p_unattributed
                lane = self.lane_ix[(seg, "Unknown" if lost_attribution else c.source)]
                created = day - int(r[9] * 10) if kind == "mql" else day
                lead = self._new_lead(
                    key,
                    lane,
                    kind,
                    created,
                    None if lost_attribution else ci,
                    None
                    if lost_attribution
                    else ("Web" if c.source == "Inbound" else c.type),
                    self.mkt,
                    r,
                )
                if kind == "clutter":
                    continue
                self.F["mqls"][lane, mi] += 1
                lead.mql_day = day
                lo, hi = p.mql_arrears_days
                recorded = day + (
                    int(lo + r[5] * (hi - lo)) if r[4] < p.p_mql_arrears else 0
                )
                self._row(lead, recorded, T_MQL, "MQL_Date__c", iso(day), self.mkt.uid)
                self.offer(
                    lead,
                    day,
                    rejected=r[2] < p.reject_fit.get(self.lane_defs[lane][1], 0.0),
                )

    def outbound(self, day: int) -> None:
        for b in self.bdrs:
            lam = self.p.bdr_leads_per_day[b.segment] * b.ramp_factor(day)
            for k in range(
                poisson_quantile(self.streams.rng("barr", b.pid, day).random(), lam)
            ):
                key = ("blead", b.pid, day, k)
                r = self.streams.rng(*key).random(12)
                lane = self.lane_ix[(b.segment, "Outbound")]
                lead = self._new_lead(
                    key, lane, "outbound", day, None, "Outbound", b, r, bdr=b
                )
                self.offer(lead, day, rejected=r[2] < self.p.reject_fit["Outbound"])

    def offer(self, lead: Lead, day: int, rejected: bool) -> None:
        """One offer of a lead to sales: a demand episode. A fit rejection leaves at once."""
        lead.offers += 1
        lead.offer_day = day
        self._row(lead, day, T_OFFER, "Sales_Offered_Date__c", iso(day), self.mkt.uid)
        if lead.offers > 1:  # a re-offer resets the disposition
            self._row(lead, day, T_OFFER + 1, "Disposition__c", None, self.mkt.uid)
            self._row(
                lead, day, T_OFFER + 2, "Disposition_Reason__c", None, self.mkt.uid
            )
        mi = self.mon(day)
        self.F["arrivals"][lead.lane, mi] += 1
        team = self.seg_spec[self.lane_defs[lead.lane][0]].team
        if not rejected:
            self.arr[team][self.team_lanes[team].index(lead.lane)].append(lead)
            return
        by = self.aes[team][0].uid
        self._row(lead, day, T_ADV, "Disposition__c", "Rejected", by)
        self._row(lead, day, T_ADV + 1, "Disposition_Reason__c", "not_a_fit", by)
        self.exits[lead.lane, mi, 0] += 1
        if lead.offers == 1 and lead.r[6] < self.p.p_reoffer:
            lo, hi = self.p.reoffer_days
            self.reoffers[day + int(lo + lead.r[7] * (hi - lo))].append(lead)

    def route(self, day: int) -> None:
        for team in self.team_lanes:
            admitted, expired = self.queues[team].step(
                self.room(team, day), self.arr[team]
            )
            for pos, leads in enumerate(admitted):
                for lead in leads:
                    self.admit(lead, day)
            for pos, leads in enumerate(expired):
                for lead in leads:
                    by = self.mkt.uid
                    self._row(lead, day, T_EXPIRE, "Disposition__c", "Expired", by)
                    self._row(
                        lead,
                        day,
                        T_EXPIRE + 1,
                        "Disposition_Reason__c",
                        "no_capacity",
                        by,
                    )
                    self.exits[lead.lane, self.mon(day), 1] += 1

    def admit(self, lead: Lead, day: int) -> None:
        team = self.seg_spec[self.lane_defs[lead.lane][0]].team
        ae = self.best_ae(team, day)
        assert ae is not None, "room without an AE who can carry another deal"
        opp = self.create_opp(
            day, lead.lane, ae, lead.bdr, lead.key, lead.campaign, lead.leadsource, lead
        )
        self._row(lead, day, T_ADMIT, "Disposition__c", "Admitted", ae.uid)
        self._row(lead, day, T_ADMIT + 1, "OwnerId", ae.uid, ae.uid)
        lead.conv = (ts(day, T_ADMIT + 2), day, opp.n, opp.account.n)

    def direct(self, day: int) -> None:
        """Partner referrals and AE self-sourcing become opportunities at once, if someone has room."""
        p = self.p
        for si, spec in enumerate(p.segments):
            lam = p.partner_per_day[spec.name] * (1 + 0.2 * (day - self.d0) / 365.25)
            for k in range(
                poisson_quantile(self.streams.rng("parr", si, day).random(), lam)
            ):
                ae = self.best_ae(spec.team, day)
                if ae is None:
                    self.turned_away += 1
                    continue
                self.direct_opp(
                    day,
                    self.lane_ix[(spec.name, "Partner")],
                    ae,
                    None,
                    ("partner", si, day, k),
                    "Partner",
                )
            for ae in self.ramped(spec.team, day):
                lam = p.ae_self_per_day * ae.ramp_factor(day)
                for k in range(
                    poisson_quantile(
                        self.streams.rng("sarr", ae.pid, day).random(), lam
                    )
                ):
                    if len(self.ae_open[ae.pid]) < spec.ceiling:
                        self.direct_opp(
                            day,
                            self.lane_ix[(spec.name, "SelfSourced")],
                            ae,
                            ae,
                            ("self", ae.pid, day, k),
                            "Self-Sourced",
                        )

    def direct_opp(self, day, lane, owner, sourcing, key, leadsource) -> None:
        self.F["arrivals"][lane, self.mon(day)] += 1
        self.create_opp(day, lane, owner, sourcing, key, None, leadsource, None)

    # ---- deals ---------------------------------------------------------
    def create_opp(
        self,
        day,
        lane,
        owner: Person,
        sourcing: Person | None,
        key,
        campaign,
        leadsource,
        lead: Lead | None,
    ) -> Opp:
        p = self.p
        seg, source = self.lane_defs[lane]
        spec = self.seg_spec[seg]
        rng = self.streams.rng("deal", *key)
        r, z = rng.random(24), rng.standard_normal(2)
        country = pick(p.country_mix, r[20])
        forms = p.countries[country]
        tier = lead.tier if lead else spec.tier
        changes = []
        if r[18] < p.p_tier_change:
            near = {
                "Tier 1": "Tier 2",
                "Tier 2": "Tier 3" if r[19] < 0.5 else "Tier 1",
                "Tier 3": "Tier 2",
            }
            changes = [(ts(day + 60 + int(r[19] * 540), T_EDIT), near[tier])]
        n_acct = self.nid("acct")
        acct = Account(
            n_acct,
            f"{ADJ[n_acct % 8]} {NOUN[n_acct // 8 % 8]} Example {n_acct}",
            tier,
            forms[int(r[23] * len(forms))],
            country if r[22] < p.p_country_code else None,
            ts(day, T_ADMIT + 2),
            changes,
        )
        self.accounts.append(acct)
        region = p.country_region[country]
        win_rate = p.win_rate[seg][source]
        ws = p.win_step
        if (ws.segment, ws.source) == (seg, source):
            win_rate = ws.before if day < day_of(ws.on) else ws.after
        win_rate = min(
            0.95, max(0.02, win_rate * p.region_win_factor[region] * owner.skill)
        )
        amount = (
            spec.amount_median
            * p.source_amount_factor.get(source, 1.0)
            * exp(spec.amount_sigma * z[0])
        )
        cents = max(1000, round(amount / 100) * 100) * 100
        will_win = bool(r[0] < win_rate)
        whale = (
            self.whale is None and seg == "Enterprise" and day >= day_of(p.whale_after)
        )
        if whale:
            cents, will_win = round(p.whale_amount) * 100, True
        total = (
            spec.cycle_days
            * exp(p.cycle_sigma * (0.0 if whale else z[1]))
            * p.region_cycle_factor[region]
        )
        last = (
            3
            if will_win
            else int(
                np.searchsorted(
                    np.cumsum(p.loss_stage), r[1] * sum(p.loss_stage), side="right"
                )
            )
        )
        opp = Opp(
            self.nid("opp"),
            lane,
            seg,
            source,
            acct,
            owner,
            sourcing,
            (sourcing or owner).uid,
            campaign,
            leadsource,
            day,
            ts(day, T_ADMIT + 2),
            cents,
            cents,
            tuple(total * s for s in p.stage_shares),
            will_win,
            min(last, 3),
            r,
            owner.uid,
            lead,
            whale=whale,
        )
        if (
            campaign is not None
            and lead is not None
            and lead.kind == "mql"
            and r[17] < p.p_hubspot_mirror
        ):
            opp.mirror = self.nid("hs")
        self.opps.append(opp)
        if whale:
            self.whale = opp
        self.take_slot(opp, owner)
        mi = self.mon(day)
        self.F["admissions"][lane, mi] += 1
        self.F["opp_created"][lane, mi] += 1
        if sourcing is not None:
            self.sourced[self.pix[sourcing.pid], mi] += 1
        self.enter(opp, day, T_ADMIT + 2)
        delete_on = day + int(
            p.delete_days[0] + r[16] * (p.delete_days[1] - p.delete_days[0])
        )
        for lo, hi in self.no_delete:
            if lo <= delete_on <= hi:
                delete_on = hi + 1
        if r[15] < p.p_delete and delete_on <= self.d1:
            self.ev[delete_on].append(("delete", opp, -1, None))
        return opp

    def take_slot(self, opp: Opp, ae: Person) -> None:
        opp.owner = ae
        self.open_n[opp.lane] += 1
        self.team_open[ae.team] += 1
        self.ae_open[ae.pid].append(opp)

    def release_slot(self, opp: Opp) -> None:
        self.open_n[opp.lane] -= 1
        self.team_open[opp.owner.team] -= 1
        self.ae_open[opp.owner.pid].remove(opp)

    def enter(self, opp: Opp, day: int, sec: int) -> None:
        """Enter the current stage: an image, and the day it ends (stretched when the owner is overloaded)."""
        p = self.p
        load = len(self.ae_open[opp.owner.pid]) / self.ceiling[opp.owner.team]
        stretch = 1 + p.overload_stretch * max(
            0.0, (load - p.overload_threshold) / (1 - p.overload_threshold)
        )
        rest = sum(opp.base_days[opp.stage_i : opp.last_stage + 1]) * stretch
        dur = max(
            1,
            round(
                opp.base_days[opp.stage_i]
                * stretch
                * (0.6 if opp.stage_i == opp.last_stage and not opp.will_win else 1.0)
            ),
        )
        opp.images.append(
            (
                self.nid("ohist"),
                ts(day, sec),
                p.stages[opp.stage_i],
                opp.cents,
                day + ceil(rest),
            )
        )
        self.ev[day + dur].append(("advance", opp, opp.version, None))

    def on_advance(self, opp: Opp, day: int, _) -> None:
        if opp.stage_i >= opp.last_stage:
            self.close(opp, day, opp.will_win)
        else:
            opp.stage_i += 1
            self.enter(opp, day, T_ADV)

    def close(self, opp: Opp, day: int, won: bool, sec: int = T_CLOSE) -> None:
        p, r = self.p, opp.r
        self.release_slot(opp)
        opp.version += 1
        self.F["wins" if won else "losses"][opp.lane, self.mon(day)] += 1
        if won and not opp.whale and r[2] < p.p_discount:
            opp.cents = (
                round(opp.list_cents * (1 - r[3] * p.discount_max) / 10000) * 10000
            )
        lag = (
            int(
                p.close_arrears_days[0]
                + r[8] * (p.close_arrears_days[1] - p.close_arrears_days[0])
            )
            if r[7] < p.p_close_arrears
            else 0
        )
        opp.close_day = max(opp.created_day, day - lag)
        opp.status = "won" if won else "lost"
        opp.images.append(
            (
                self.nid("ohist"),
                ts(day, sec),
                CLOSED_WON if won else CLOSED_LOST,
                opp.cents,
                opp.close_day,
            )
        )
        if opp.reopened:
            return
        ver = opp.version
        if won and r[4] < p.p_amend:
            self.ev[
                day + int(p.amend_days[0] + r[5] * (p.amend_days[1] - p.amend_days[0]))
            ].append(("amend", opp, ver, None))
        if r[9] < p.p_close_corrected:
            self.ev[day + 5 + int(r[10] * 55)].append(("correct", opp, ver, None))
        if not won and r[12] < p.p_reopen:
            self.ev[
                day
                + int(p.reopen_days[0] + r[13] * (p.reopen_days[1] - p.reopen_days[0]))
            ].append(("reopen", opp, ver, None))

    def _image(self, opp: Opp, day: int, close_day: int | None = None) -> None:
        stage = CLOSED_WON if opp.status == "won" else CLOSED_LOST
        opp.close_day = opp.close_day if close_day is None else close_day
        opp.images.append(
            (self.nid("ohist"), ts(day, T_EDIT), stage, opp.cents, opp.close_day)
        )

    def on_amend(self, opp: Opp, day: int, _) -> None:
        opp.cents = max(
            100, round(opp.cents * (0.85 + 0.30 * opp.r[6]) / 10000) * 10000
        )
        self._image(opp, day)

    def on_correct(self, opp: Opp, day: int, _) -> None:
        shift = int((opp.r[11] - 0.5) * 30) or 3
        new = min(day, max(opp.created_day, opp.close_day + shift))
        if new != opp.close_day:
            self._image(opp, day, new)

    def on_reopen(self, opp: Opp, day: int, _) -> None:
        team = opp.owner.team
        owner = (
            opp.owner
            if opp.owner in self.ramped(team, day)
            and len(self.ae_open[opp.owner.pid]) < self.ceiling[team]
            else self.best_ae(team, day)
        )
        if owner is None or self.room(team, day) <= 0:
            return
        opp.reopened, opp.status, opp.stage_i = True, "open", 1
        opp.will_win = bool(opp.r[14] < 0.45)
        opp.last_stage = 3 if opp.will_win else 2
        opp.version += 1
        self.take_slot(opp, owner)
        self.F["reopened"][opp.lane, self.mon(day)] += 1
        self.enter(opp, day, T_EDIT)

    def on_delete(self, opp: Opp, day: int, _) -> None:
        if opp.status == "won":
            return  # a booked deal is never deleted: bookings and the workload both stand
        if opp.status == "open":
            self.release_slot(opp)
            self.F["deleted"][opp.lane, self.mon(day)] += 1
            opp.version += 1
        opp.dead = ts(day, T_EDIT)

    def depart(self, person: Person, day: int) -> None:
        """An AE leaves: deals go to teammates with room; the rest are lost with the departure."""
        for opp in sorted(self.ae_open[person.pid], key=lambda o: o.n):
            ae = self.best_ae(person.team, day)
            if ae is None:
                self.close(opp, day, False, T_SHED)
                continue
            self.ae_open[person.pid].remove(opp)
            self.ae_open[ae.pid].append(opp)
            by = self.cs[0].uid
            opp.owner_rows.append(
                (self.nid("ofield"), ts(day, T_SHED), person.uid, ae.uid, by)
            )
            opp.owner = ae


def _month_end(day: int) -> date:
    d = date.fromordinal(day)
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])

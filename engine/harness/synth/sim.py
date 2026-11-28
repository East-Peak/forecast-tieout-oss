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
from math import exp, floor

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
    seller: float
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
    orphan: bool = False
    orphaned: bool = False
    key: tuple = ()


class Simulation:
    def __init__(
        self,
        params: CompanyParams,
        seed: int,
        intervention: Intervention,
        replicate: int = 0,
        fork_day: int | None = None,
    ):
        """`replicate` and `fork_day` re-key the randomness of everything created on or
        after `fork_day` (see rng.py); with no fork day the company is the plain seed."""
        if params.routing_priority != "oldest_first":
            raise ValueError("routing_priority: only 'oldest_first' is implemented")
        self.p, self.iv = params, intervention
        self.streams = Streams(seed, replicate, fork_day)
        self.d0, self.d1 = day_of(params.start), day_of(params.end)
        self.m0 = params.start.year * 12 + params.start.month - 1
        self.n_months = params.end.year * 12 + params.end.month - self.m0
        self.people = build_people(
            params, self.streams, intervention, self.d1, fork_day
        )
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
        team_shape = (len(self.teams), self.n_months)
        # per team and month: the peak daily carrying capacity, peak effective and employed AEs, summed effective AEs
        self.cap_max = np.zeros(team_shape, dtype=np.int64)
        self.emp_max = np.zeros(team_shape, dtype=np.int64)
        self.eff_max = np.zeros(team_shape)
        self.eff_sum = np.zeros(team_shape)
        self.open_n = [0] * len(self.lane_defs)
        self.team_open = dict.fromkeys(self.teams, 0)
        self.ae_open: dict[str, list[Opp]] = {x.pid: [] for x in self.people}
        self.orphans: dict[str, list[Opp]] = {t: [] for t in self.teams}
        self.limit: dict[str, float] = {}
        self.cap: dict[str, int] = {}
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
        self.whale: Opp | None = None
        self.whale_key: tuple | None = None
        self.campaign_spend, self.lam = self._schedules()
        self.arr: dict[str, list[list[Lead]]] = {}

    # ---- bookkeeping ---------------------------------------------------
    def nid(self, kind: str) -> int:
        self.counter[kind] += 1
        return self.counter[kind]

    def mon(self, day: int) -> int:
        d = date.fromordinal(day)
        return d.year * 12 + d.month - 1 - self.m0

    def team_of(self, opp: Opp) -> str:
        return self.seg_spec[opp.seg].team

    def room(self, team: str) -> int:
        return self.cap[team] - self.team_open[team]

    def ramped(self, team: str) -> list[Person]:
        """AEs carrying deals today (employed and past the start of their carrying ramp)."""
        return [x for x in self.aes[team] if x.pid in self.limit]

    def best_ae(self, team: str) -> Person | None:
        pool = [
            x for x in self.ramped(team) if len(self.ae_open[x.pid]) < self.limit[x.pid]
        ]
        return min(pool, key=lambda x: (len(self.ae_open[x.pid]), x.idx), default=None)

    def lightest_ae(self, team: str) -> Person | None:
        """Whoever carries the fewest deals: an inheritor may go beyond their ceiling."""
        return min(
            self.ramped(team),
            key=lambda x: (len(self.ae_open[x.pid]), x.idx),
            default=None,
        )

    def _day_state(self, day: int) -> None:
        """Carrying capacity today: each AE's ceiling scaled by their tenure-based carrying ramp."""
        p, m = self.p, self.mon(day)
        self.limit = {}
        for ti, team in enumerate(self.teams):
            eff, emp = 0.0, 0
            for ae in self.aes[team]:
                if ae.start <= day < ae.leave_day:
                    emp += 1
                    c = ae.carry_factor(day, p.carry_ramp_start, p.carry_ramp_days)
                    if c > 0:
                        self.limit[ae.pid] = self.ceiling[team] * c
                        eff += c
            self.cap[team] = floor(self.ceiling[team] * eff + 1e-9)
            self.cap_max[ti, m] = max(self.cap_max[ti, m], self.cap[team])
            self.emp_max[ti, m] = max(self.emp_max[ti, m], emp)
            self.eff_max[ti, m] = max(self.eff_max[ti, m], eff)
            self.eff_sum[ti, m] += eff

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
                        0.05
                        * self.streams.rng("spend", ci, mi, day=first).standard_normal()
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
            self._day_state(day)
            for person in self.leaves.pop(day, []):
                self.depart(person, day)
            for kind, opp, ver, arg in self.ev.pop(day, []):
                if (ver < 0 or opp.version == ver) and not opp.dead:
                    getattr(self, "on_" + kind)(opp, day, arg)
            for lead in self.reoffers.pop(day, []):
                self.offer(lead, day, rejected=lead.r[8] >= self.p.p_reoffer_fit)
            self.marketing(day)
            self.outbound(day)
            self.partners(day)
            self.route(day)
            self.self_source(day)
            if date.fromordinal(day + 1).day == 1 or day == self.d1:
                m = self.mon(day)
                self.F["open_end"][:, m] = self.open_n
                for t, ls in self.team_lanes.items():
                    self.F["queue_end"][ls, m] = self.queues[t].sizes()
        return self

    def fingerprint(self) -> str:
        """A hash of every event the run produced, for the causal-inertness test."""
        import hashlib

        h = hashlib.sha256()
        for lead in self.leads:
            h.update(repr((lead.key, lead.rows, lead.conv)).encode())
        for o in self.opps:
            h.update(repr((o.n, o.images, o.owner_rows, o.dead)).encode())
        for name in sorted(self.F):
            h.update(self.F[name].tobytes())
        h.update(self.exits.tobytes())
        return h.hexdigest()

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

    def _consider_whale(self, key: tuple, lane: int, day: int) -> None:
        """The very large deal is the first Enterprise demand that fits, whoever ends up selling it."""
        if (
            self.whale_key is None
            and self.lane_defs[lane][0] == "Enterprise"
            and day >= day_of(self.p.whale_after)
        ):
            self.whale_key = key

    def marketing(self, day: int) -> None:
        p, mi, dim = self.p, self.mon(day), month_days(day)
        for ci, c in enumerate(p.campaigns):
            lam = self.lam[ci][mi] / dim
            if lam <= 0:
                continue
            n = poisson_quantile(self.streams.uniform("arr", ci, day, day=day), lam)
            n_clutter = poisson_quantile(
                self.streams.uniform("clut", ci, day, day=day),
                lam * p.clutter_lead_share,
            )
            numbered = [("mql", k) for k in range(n)] + [
                ("clutter", k) for k in range(n_clutter)
            ]
            for kind, k in numbered:
                key = ("lead", ci, day, k, kind)
                r = self.streams.rng(*key, day=day).random(12)
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
                poisson_quantile(self.streams.uniform("barr", b.pid, day, day=day), lam)
            ):
                key = ("blead", b.pid, day, k)
                r = self.streams.rng(*key, day=day).random(12)
                lane = self.lane_ix[(b.segment, "Outbound")]
                lead = self._new_lead(
                    key, lane, "outbound", day, None, "Outbound", b, r, bdr=b
                )
                self.offer(lead, day, rejected=r[2] < self.p.reject_fit["Outbound"])

    def partners(self, day: int) -> None:
        """Partner referrals are leads offered to sales like any other demand (no MQL date)."""
        p = self.p
        for si, spec in enumerate(p.segments):
            lam = p.partner_per_day[spec.name] * (1 + 0.2 * (day - self.d0) / 365.25)
            for k in range(
                poisson_quantile(self.streams.uniform("parr", si, day, day=day), lam)
            ):
                key = ("plead", si, day, k)
                r = self.streams.rng(*key, day=day).random(12)
                lane = self.lane_ix[(spec.name, "Partner")]
                lead = self._new_lead(
                    key, lane, "partner", day, None, "Partner", self.mkt, r
                )
                self.offer(lead, day, rejected=r[2] < p.reject_fit["Partner"])

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
            if lead.offers == 1:
                self._consider_whale(lead.key, lead.lane, day)
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
            admitted, expired = self.queues[team].step(self.room(team), self.arr[team])
            for leads in admitted:
                for lead in leads:
                    self.admit(lead, day)
            for leads in expired:
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
        ae = self.best_ae(team)
        assert ae is not None, "room without an AE who can carry another deal"
        opp = self.create_opp(
            day, lead.lane, ae, lead.bdr, lead.key, lead.campaign, lead.leadsource, lead
        )
        self._row(lead, day, T_ADMIT, "Disposition__c", "Admitted", ae.uid)
        self._row(lead, day, T_ADMIT + 1, "OwnerId", ae.uid, ae.uid)
        lead.conv = (ts(day, T_ADMIT + 2), day, opp.n, opp.account.n)

    def self_source(self, day: int) -> None:
        """AEs find their own deals, after the day's queued demand is routed, only with room.

        The rate falls as the AE fills up: lambda = rate * sourcing ramp * (1 - load)."""
        p = self.p
        for spec in p.segments:
            for ae in self.ramped(spec.team):
                load = len(self.ae_open[ae.pid]) / self.limit[ae.pid]
                lam = p.ae_self_per_day * ae.ramp_factor(day) * max(0.0, 1.0 - load)
                key0 = ("sarr", ae.pid, day)
                for k in range(
                    poisson_quantile(self.streams.uniform(*key0, day=day), lam)
                ):
                    if (
                        len(self.ae_open[ae.pid]) < self.limit[ae.pid]
                        and self.room(spec.team) > 0
                    ):
                        lane = self.lane_ix[(spec.name, "SelfSourced")]
                        key = ("self", ae.pid, day, k)
                        self._consider_whale(key, lane, day)
                        self.F["arrivals"][lane, self.mon(day)] += 1
                        self.create_opp(
                            day, lane, ae, ae, key, None, "Self-Sourced", None
                        )

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
        rng = self.streams.rng("deal", *key, day=key[2])
        r, z = rng.random(28), rng.standard_normal(3)
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
        # declared mechanisms: region and the owner's individual skill shift the win probability
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
        whale = key == self.whale_key and self.whale is None
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
        # what the seller writes down as the expected close: optimism and noise, never the outcome
        seller = p.expected_close_optimism * exp(p.expected_close_noise * z[2])
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
            seller,
            will_win,
            min(last, 3),
            r,
            owner.uid,
            lead,
            whale=whale,
            key=key,
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
        self.take_slot(opp)
        mi = self.mon(day)
        self.F["admissions"][lane, mi] += 1
        self.F["opp_created"][lane, mi] += 1
        if sourcing is not None:
            self.sourced[self.pix[sourcing.pid], mi] += 1
        self.enter(opp, day, T_ADMIT + 2)
        delete_on = day + int(
            p.delete_days[0] + r[16] * (p.delete_days[1] - p.delete_days[0])
        )
        if r[15] < p.p_delete and delete_on <= self.d1:
            self.ev[delete_on].append(("delete", opp, -1, None))
        return opp

    def take_slot(self, opp: Opp) -> None:
        self.open_n[opp.lane] += 1
        self.team_open[self.team_of(opp)] += 1
        self.ae_open[opp.owner.pid].append(opp)

    def release_slot(self, opp: Opp) -> None:
        self.open_n[opp.lane] -= 1
        team = self.team_of(opp)
        self.team_open[team] -= 1
        if opp.orphan:
            self.orphans[team].remove(opp)
            opp.orphan = False
        else:
            self.ae_open[opp.owner.pid].remove(opp)

    def set_owner(self, opp: Opp, new: Person, day: int, sec: int, by: str) -> None:
        """The one place an opportunity changes hands; every change writes an OwnerId history row."""
        if new.uid != opp.owner.uid:
            opp.owner_rows.append(
                (self.nid("ofield"), ts(day, sec), opp.owner.uid, new.uid, by)
            )
        opp.owner = new

    def enter(self, opp: Opp, day: int, sec: int, image: bool = True) -> None:
        """Enter the current stage; its length is stretched when the owner is overloaded."""
        p = self.p
        spec = self.seg_spec[opp.seg]
        load = len(self.ae_open[opp.owner.pid]) / self.ceiling[spec.team]
        stretch = 1 + p.overload_stretch * max(
            0.0, (load - p.overload_threshold) / (1 - p.overload_threshold)
        )
        if opp.orphaned:
            stretch *= 1 + p.orphan_stretch
        dur = max(
            1,
            round(
                opp.base_days[opp.stage_i]
                * stretch
                * (0.6 if opp.stage_i == opp.last_stage and not opp.will_win else 1.0)
            ),
        )
        if image:
            # expected close: segment norm with the seller's optimism and noise, pushed out as it passes
            norm = spec.cycle_days * opp.seller
            remaining = (
                spec.cycle_days * sum(p.stage_shares[opp.stage_i :]) * opp.seller
            )
            expected = max(
                opp.created_day + round(norm), day + max(3, round(0.5 * remaining))
            )
            opp.images.append(
                (
                    self.nid("ohist"),
                    ts(day, sec),
                    p.stages[opp.stage_i],
                    opp.cents,
                    expected,
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
        team = self.team_of(opp)
        if self.room(team) <= 0:
            return
        o = opp.owner
        owner = (
            o
            if o.pid in self.limit and len(self.ae_open[o.pid]) < self.limit[o.pid]
            else self.best_ae(team)
        )
        if owner is None:
            return
        self.set_owner(opp, owner, day, T_EDIT, owner.uid)
        opp.reopened, opp.status, opp.stage_i = True, "open", 1
        opp.will_win = bool(opp.r[14] < 0.45)
        opp.last_stage = 3 if opp.will_win else 2
        opp.version += 1
        self.take_slot(opp)
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
        """An AE leaves. Open deals sit with a manager for a handoff delay (some are lost to the
        gap), then pass to the teammate with the fewest deals, beyond their ceiling if need be."""
        p, holder = self.p, self.cs[0]
        for opp in sorted(self.ae_open[person.pid], key=lambda o: o.n):
            opp.version += 1  # the stage clock stops
            self.set_owner(opp, holder, day, T_SHED, holder.uid)
            opp.orphan = opp.orphaned = True
            self.orphans[self.team_of(opp)].append(opp)
            if (
                opp.r[24] < p.p_orphan_loss
            ):  # the gap costs the deal: it will be lost soon
                opp.will_win = False
                opp.last_stage = min(opp.last_stage, opp.stage_i + int(opp.r[25] * 2))
            self.ev[day + p.handoff_days].append(("handoff", opp, opp.version, None))
        self.ae_open[person.pid] = []

    def on_handoff(self, opp: Opp, day: int, _) -> None:
        ae = self.lightest_ae(self.team_of(opp))
        if ae is None:
            self.ev[day + 7].append(("handoff", opp, opp.version, None))
            return
        self.orphans[self.team_of(opp)].remove(opp)
        opp.orphan = False
        self.set_owner(opp, ae, day, T_EDIT, self.cs[0].uid)
        self.ae_open[ae.pid].append(opp)
        self.enter(opp, day, T_EDIT, image=False)

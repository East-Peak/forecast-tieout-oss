"""The extract writer: what each source system would hold on an extract date.

Every extract is a complete snapshot (one folder per source system): current values
are replayed from the append-only histories, and nothing recorded after the extract
instant (23:00 UTC on the date) appears. A record deleted before the extract is
absent from it, with its history.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ..contract.manifest import build_manifest, write_manifest
from ..contract.schemas import SYSTEMS
from .people import day_of, requisition_rows
from .run import Company
from .sim import CLOSED_LOST, CLOSED_WON, Opp, Simulation, iso, sfid, ts

HS_STAGE = {
    "Discovery": "appointmentscheduled",
    "Evaluation": "qualifiedtobuy",
    "Proposal": "presentationscheduled",
    "Negotiation": "contractsent",
    CLOSED_WON: "closedwon",
    CLOSED_LOST: "closedlost",
}


def extract_folder(out: Path, when: date) -> Path:
    return Path(out) / "extracts" / f"extract_{when.isoformat()}"


def default_extract_dates(params) -> list[date]:
    """The plan date, then each month end from the month after it to the end of its fiscal year."""
    dates, d = (
        [params.plan_date],
        date(params.plan_date.year, params.plan_date.month, 28) + timedelta(days=4),
    )
    while d <= date(params.plan_date.year + 1, 1, 31):
        end = date(d.year, d.month, 1) + timedelta(days=32)
        dates.append(date(end.year, end.month, 1) - timedelta(days=1))
        d = dates[-1] + timedelta(days=1)
        d = date(d.year, d.month, 28) + timedelta(days=4)
    return [x for x in dates if params.start <= x <= params.end]


def _up_to(rows: list, at: str, key=lambda r: r[1]) -> list:
    return [r for r in rows if key(r) <= at]


def _history(rows, at, make) -> list[dict]:
    """Rows recorded by `at`, with each field's previous value as OldValue."""
    last: dict = {}
    out = []
    for n, when, name, new, by in sorted(_up_to(rows, at), key=lambda r: (r[1], r[0])):
        out.append(make(n, when, name, last.get(name), new, by))
        last[name] = new
    return out


class _Renewal:
    """A Renewal opportunity spawned by a won deal: clutter outside new-business bookings."""

    def __init__(
        self, n: int, won: Opp, owner_uid: str, day: int, factor: float, image_id: int
    ):
        self.n, self.account, self.owner0, self.creator_uid = (
            n,
            won.account,
            owner_uid,
            owner_uid,
        )
        self.sourcing = self.campaign = self.leadsource = self.dead = None
        self.type, self.created, self.owner_rows = "Renewal", ts(day, 11 * 3600), []
        cents = round(won.cents * factor / 10000) * 10000
        close = day + 60
        self.images = [
            (image_id, ts(day, 11 * 3600), "Discovery", cents, close),
            (image_id + 1, ts(day + 30, 14 * 3600), "Negotiation", cents, close),
            (image_id + 2, ts(close, 15 * 3600), CLOSED_WON, cents, close),
        ]


class Writer:
    def __init__(self, sim: Simulation):
        self.sim = sim
        for lead in sim.leads:
            lead.rows.sort(key=lambda r: (r[1], r[0]))
        self.opp_by_n = {o.n: o for o in sim.opps}
        self.renewals = self._renewals()

    def _renewals(self) -> list[_Renewal]:
        sim, out = self.sim, []
        base = len(sim.opps) + 1
        for o in sim.opps:
            if o.status == "won" and o.r[21] < sim.p.p_renewal_clutter:
                won_day = day_of(
                    date.fromisoformat(
                        next(i[1][:10] for i in o.images if i[2] == CLOSED_WON)
                    )
                )
                day = won_day + 300
                if day + 60 <= sim.d1:
                    out.append(
                        _Renewal(
                            base + len(out),
                            o,
                            sim.cs[o.n % len(sim.cs)].uid,
                            day,
                            0.9 + 0.2 * o.r[19],
                            sim.counter["ohist"] + 1 + 3 * len(out),
                        )
                    )
        return out

    # ---- Salesforce ------------------------------------------------------
    def salesforce(self, at: str) -> dict[str, list[dict]]:
        sim, p = self.sim, self.sim.p
        day = day_of(date.fromisoformat(at[:10]))
        users = [
            {
                "Id": x.uid,
                "Name": x.name,
                "Email": x.email,
                "Title": _title(x),
                "IsActive": not (x.end is not None and ts(x.leave_day, 0) <= at),
                "CreatedDate": ts(x.start, 9 * 3600),
                "SystemModstamp": ts(x.leave_day, 0)
                if x.end is not None and ts(x.leave_day, 0) <= at
                else ts(x.start, 9 * 3600),
            }
            for x in sim.people
            if ts(x.start, 9 * 3600) <= at
        ]
        campaigns, members = [], []
        for ci, c in enumerate(p.campaigns):
            made = ts((day_of(c.launch) if c.launch else sim.d0) - 14, 9 * 3600)
            if made > at:
                continue
            over = c.end is not None and ts(day_of(c.end), 17 * 3600) <= at
            campaigns.append(
                {
                    "Id": sfid("camp", ci + 1),
                    "Name": c.name,
                    "Type": c.type,
                    "StartDate": iso(day_of(c.launch)) if c.launch else None,
                    "EndDate": iso(day_of(c.end)) if over else None,
                    "IsActive": not over,
                    "CreatedDate": made,
                    "SystemModstamp": ts(day_of(c.end), 17 * 3600) if over else made,
                }
            )
        leads, lead_hist = [], []
        for lead in sim.leads:
            if lead.created > at:
                continue
            state = {r[2]: r[3] for r in lead.rows if r[1] <= at}
            conv = lead.conv if lead.conv and lead.conv[0] <= at else None
            touched = (
                [lead.created]
                + [r[1] for r in lead.rows if r[1] <= at]
                + ([lead.conv[0]] if conv else [])
            )
            leads.append(
                {
                    "Id": sfid("lead", lead.n),
                    "OwnerId": state.get("OwnerId", lead.owner),
                    "CreatedById": lead.owner,
                    "LeadSource": lead.leadsource,
                    "Tier__c": lead.tier,
                    "Sales_Offered_Date__c": state.get("Sales_Offered_Date__c"),
                    "MQL_Date__c": state.get("MQL_Date__c"),
                    "Disposition__c": state.get("Disposition__c"),
                    "Disposition_Reason__c": state.get("Disposition_Reason__c"),
                    "IsConverted": bool(conv),
                    "ConvertedDate": iso(conv[1]) if conv else None,
                    "ConvertedOpportunityId": sfid("opp", conv[2]) if conv else None,
                    "ConvertedAccountId": sfid("acct", conv[3]) if conv else None,
                    "CreatedDate": lead.created,
                    "SystemModstamp": max(touched),
                }
            )
            lead_hist += _history(
                lead.rows,
                at,
                lambda n, when, name, old, new, by, lead=lead: {
                    "Id": sfid("lhist", n),
                    "LeadId": sfid("lead", lead.n),
                    "Field": name,
                    "OldValue": old,
                    "NewValue": new,
                    "CreatedDate": when,
                    "CreatedById": by,
                },
            )
            if lead.campaign is not None:
                responded = (
                    lead.mql_day is not None and ts(lead.mql_day, 9 * 3600) <= at
                )
                members.append(
                    {
                        "Id": sfid("member", lead.n),
                        "CampaignId": sfid("camp", lead.campaign + 1),
                        "LeadId": sfid("lead", lead.n),
                        "Status": "Responded" if responded else "Sent",
                        "FirstRespondedDate": iso(lead.mql_day) if responded else None,
                        "CreatedDate": lead.created,
                        "SystemModstamp": lead.created,
                    }
                )
        accounts, opps, opp_hist, opp_field = [], [], [], []
        for a in sim.accounts:
            if a.created <= at:
                tier = ([a.tier] + [new for when, new in a.tier_changes if when <= at])[
                    -1
                ]
                touched = [a.created] + [
                    when for when, _ in a.tier_changes if when <= at
                ]
                accounts.append(
                    {
                        "Id": sfid("acct", a.n),
                        "Name": a.name,
                        "Tier__c": tier,
                        "BillingCountry": a.country,
                        "BillingCountryCode": a.code,
                        "CreatedDate": a.created,
                        "SystemModstamp": max(touched),
                    }
                )
        for o in [*sim.opps, *self.renewals]:
            if o.created > at or (o.dead and o.dead <= at):
                continue
            a = o.account
            shown = [i for i in o.images if i[1] <= at]
            owner_rows = [r for r in o.owner_rows if r[1] <= at]
            _, last_ts, stage, cents, close = shown[-1]
            opps.append(
                {
                    "Id": sfid("opp", o.n),
                    "AccountId": sfid("acct", a.n),
                    "OwnerId": owner_rows[-1][3] if owner_rows else o.owner0,
                    "CreatedById": o.creator_uid,
                    "Sourcing_User__c": o.sourcing.uid if o.sourcing else None,
                    "CampaignId": sfid("camp", o.campaign + 1)
                    if o.campaign is not None
                    else None,
                    "LeadSource": o.leadsource,
                    "Type": o.type,
                    "StageName": stage,
                    "Amount": cents / 100,
                    "CloseDate": iso(close),
                    "IsClosed": stage.startswith("Closed"),
                    "IsWon": stage == CLOSED_WON,
                    "CreatedDate": o.created,
                    "SystemModstamp": max([last_ts] + [r[1] for r in owner_rows]),
                }
            )
            opp_hist += [
                {
                    "Id": sfid("ohist", n),
                    "OpportunityId": sfid("opp", o.n),
                    "StageName": st,
                    "Amount": c / 100,
                    "CloseDate": iso(cl),
                    "CreatedDate": w,
                }
                for n, w, st, c, cl in shown
            ]
            opp_field += [
                {
                    "Id": sfid("ofield", n),
                    "OpportunityId": sfid("opp", o.n),
                    "Field": "OwnerId",
                    "OldValue": old,
                    "NewValue": new,
                    "CreatedDate": w,
                    "CreatedById": by,
                }
                for n, w, old, new, by in owner_rows
            ]
        return {
            "User": users,
            "Account": accounts,
            "Campaign": campaigns,
            "CampaignMember": members,
            "Lead": leads,
            "LeadHistory": sorted(lead_hist, key=lambda r: r["Id"]),
            "Opportunity": opps,
            "OpportunityHistory": sorted(opp_hist, key=lambda r: r["Id"]),
            "OpportunityFieldHistory": opp_field,
            "_day": day,
        }

    # ---- the other systems ---------------------------------------------
    def hubspot(self, at: str) -> dict[str, list[dict]]:
        sim, contacts, deals = self.sim, [], []
        for lead in sim.leads:
            if lead.kind == "outbound" or lead.created > at:
                continue
            mql = next((r[1] for r in lead.rows if r[2] == "MQL_Date__c"), None)
            mql = mql if mql and mql <= at else None
            conv = lead.conv if lead.conv and lead.conv[0] <= at else None
            won = None
            if conv:
                opp = self.opp_by_n[conv[2]]
                won = next(
                    (i[1] for i in opp.images if i[2] == CLOSED_WON and i[1] <= at),
                    None,
                )
            stage = (
                "customer"
                if won
                else "opportunity"
                if conv
                else "marketingqualifiedlead"
                if mql
                else "lead"
            )
            contacts.append(
                {
                    "hs_object_id": str(100000 + lead.n),
                    "email": f"lead{lead.n}@example.com",
                    "lifecyclestage": stage,
                    "createdate": lead.created,
                    "hs_lifecyclestage_marketingqualifiedlead_date": ts(
                        lead.mql_day, 9 * 3600
                    )
                    if mql
                    else None,
                    "lastmodifieddate": max(
                        x
                        for x in (lead.created, mql, conv[0] if conv else None, won)
                        if x
                    ),
                    "salesforce_lead_id": sfid("lead", lead.n)
                    if lead.r[10] < 0.95
                    else None,
                }
            )
        for o in sim.opps:
            if o.mirror is None or o.created > at or (o.dead and o.dead <= at):
                continue
            shown = [i for i in o.images if i[1] <= at]
            _, last_ts, stage, cents, close = shown[-1]
            deals.append(
                {
                    "hs_object_id": str(900000 + o.mirror),
                    "dealname": f"{o.account.name} - new business",
                    "dealstage": HS_STAGE[stage],
                    "amount": cents / 100,
                    "closedate": f"{iso(close)}T00:00:00Z"
                    if stage.startswith("Closed")
                    else None,
                    "createdate": o.created,
                    "hs_lastmodifieddate": last_ts,
                    "salesforce_opportunity_id": sfid("opp", o.n),
                }
            )
        return {"contacts": contacts, "deals": deals}

    def people_system(self, when: date) -> dict[str, list[dict]]:
        sim, at = self.sim, day_of(when)
        people = [
            {
                "person_id": x.pid,
                "name": x.name,
                "email": x.email,
                "role": x.role,
                "team": x.team,
                "segment": x.segment or _team_segment(sim, x.team),
                "region": x.region,
                "start_date": iso(x.start),
                "end_date": iso(x.end) if x.end is not None and x.end <= at else None,
            }
            for x in sim.people
            if x.start <= at
        ]
        return {
            "people": people,
            "requisitions": requisition_rows(sim.p, sim.people, when),
        }

    def spend_sheet(self, when: date) -> dict[str, list[dict]]:
        sim, rows = self.sim, []
        for ci in range(len(sim.p.campaigns)):
            for mi, cents in enumerate(sim.campaign_spend[ci]):
                y, m = divmod(sim.m0 + mi, 12)
                first = date(y, m + 1, 1)
                if (
                    cents
                    and (date(y + (m == 11), (m + 1) % 12 + 1, 1) - timedelta(days=1))
                    <= when
                ):
                    rows.append(
                        {
                            "spend_id": f"SP-{ci + 1:02d}-{y}{m + 1:02d}",
                            "campaign_id": sfid("camp", ci + 1),
                            "month": first.isoformat(),
                            "amount_cents": cents,
                        }
                    )
        return {"spend": rows}


def _title(person) -> str:
    return {
        "AE": "Account Executive",
        "BDR": "Business Development Rep",
        "Marketing": "Marketing Manager",
        "Manager": "Customer Success Manager",
    }[person.role]


def _team_segment(sim: Simulation, team: str) -> str | None:
    return next((s.name for s in sim.p.segments if s.team == team), None)


def _write(
    folder: Path, system: str, at: datetime, objects: dict[str, list[dict]]
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in objects.items():
        if name.startswith("_"):
            continue
        (folder / f"{name}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows)
        )
    write_manifest(folder, build_manifest(folder, system, at))


def write_extracts(company: Company, out: Path, dates: list[date]) -> list[Path]:
    """One folder per source system per date, each a complete snapshot as of 23:00 UTC that day."""
    writer, folders = Writer(company.sim), []
    for when in dates:
        at = datetime(when.year, when.month, when.day, 23, 0, 0, tzinfo=UTC)
        stamp = at.strftime("%Y-%m-%dT%H:%M:%SZ")
        base = extract_folder(out, when)
        parts = {
            "salesforce": writer.salesforce(stamp),
            "hubspot": writer.hubspot(stamp),
            "people_system": writer.people_system(when),
            "spend_sheet": writer.spend_sheet(when),
        }
        assert set(parts) == set(SYSTEMS) - {"plan_file"}
        for system, objects in parts.items():
            _write(base / system, system, at, objects)
        folders.append(base)
    return folders

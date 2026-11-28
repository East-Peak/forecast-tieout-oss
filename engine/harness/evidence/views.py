"""Canonical views as parameterized relations: DuckDB table macros `asof_<table>(t, k)`.

`t` is a business date and `k` a knowledge instant. Two readings of an attribute coexist, never mixed:

- as of T: the latest assertion effective by the end of day T and recorded by K (attributes);
- restating: the latest assertion recorded by K whatever its effective time (measures: amount,
  close date, stage, MQL date), so a late correction restates a closed period for K at or after it.
"""

from ..contract.keys import DELETED_FIELD
from ..contract.schemas import SCHEMAS
from .sql import ISO, ident, lit

CLOSED = "('Closed Won', 'Closed Lost')"
TS = f"strptime({{x}}, '{ISO}')"

SCALARS = [
    "CREATE OR REPLACE MACRO day_end(t) AS CAST(t AS TIMESTAMP) + INTERVAL 86399 SECOND",
    "CREATE OR REPLACE MACRO cents(txt) AS CAST(CAST(txt AS DECIMAL(18, 2)) * 100 AS BIGINT)",
    f"CREATE OR REPLACE MACRO ts(txt) AS strptime(txt, '{ISO}')",
    f"""CREATE OR REPLACE MACRO known_asof(e, t, k) AS TABLE
        SELECT id, field,
               arg_max_null(value, (effective_at, recorded_at, source)) AS value,
               arg_max_null(source, (effective_at, recorded_at, source)) AS source,
               arg_max_null(extract_id, (effective_at, recorded_at, source)) AS extract_id,
               arg_max_null(recorded_at, (effective_at, recorded_at, source)) AS recorded_at,
               arg_max_null(assumed_since_creation, (effective_at, recorded_at, source)) AS assumed_since_creation
        FROM assertion
        WHERE entity = e AND field <> '{DELETED_FIELD}' AND recorded_at <= k AND effective_at <= day_end(t)
        GROUP BY id, field""",
    f"""CREATE OR REPLACE MACRO known_latest(e, k) AS TABLE
        SELECT id, field,
               arg_max_null(value, (recorded_at, effective_at, source)) AS value,
               arg_max_null(source, (recorded_at, effective_at, source)) AS source,
               arg_max_null(extract_id, (recorded_at, effective_at, source)) AS extract_id,
               max(recorded_at) AS recorded_at, CAST(NULL AS BOOLEAN) AS assumed_since_creation
        FROM assertion
        WHERE entity = e AND field <> '{DELETED_FIELD}' AND recorded_at <= k
        GROUP BY id, field""",
]


def _cast(expr: str, kind: str) -> str:
    return {"text": expr, "ts": f"ts({expr})", "cents": f"cents({expr})"}.get(
        kind, f"CAST({expr} AS {kind})"
    )


def _pivot(obj: str, source: str, columns: list[tuple[str, str, str]]) -> str:
    """One row per record with the listed fields as typed columns, plus lineage lists."""
    cols = ", ".join(
        f"{_cast(f'max(value) FILTER (WHERE field = {lit(field)})', kind)} AS {alias}"
        for alias, field, kind in columns
    )
    for _, field, _ in columns:
        SCHEMAS[obj].field(field)
    return f"""SELECT id, {cols}, list_distinct(list(source)) AS _src, list_distinct(list(extract_id)) AS _xs
        FROM {source} GROUP BY id"""


def _entity_macro(
    name: str,
    obj: str,
    key: str,
    asof: list,
    latest: list = (),
    *,
    extra_select: str = "",
    extra_join: str = "",
    extra_where: str = "",
) -> str:
    """A view of one object: `asof` columns read as of T, `latest` columns restate. Both lists hold
    (alias, raw field, kind). With no creation time on the object the first set also restates."""
    first_source = (
        f"known_asof({lit(obj)}, t, k)" if asof else f"known_latest({lit(obj)}, k)"
    )
    sets = [(_pivot(obj, first_source, asof or list(latest)), asof or list(latest))]
    if asof and latest:
        sets.append(
            (_pivot(obj, f"known_latest({lit(obj)}, k)", list(latest)), list(latest))
        )
    joins = "".join(
        f" LEFT JOIN ({sql}) b{i} ON b{i}.id = rec.id"
        for i, (sql, _) in enumerate(sets[1:], 1)
    )
    prefix = ["a0"] + [f"b{i}" for i in range(1, len(sets))]
    selected = ", ".join(
        f"{p}.{alias}"
        for p, (_, cols) in zip(prefix, sets, strict=True)
        for alias, _, _ in cols
    )
    lineage_src = " || ".join(f"COALESCE({p}._src, [])" for p in prefix)
    lineage_x = " || ".join(f"COALESCE({p}._xs, [])" for p in prefix)
    return f"""CREATE OR REPLACE MACRO asof_{name}(t, k) AS TABLE
        SELECT rec.id AS {key}, {selected}, rec.created_at, d.deleted_at{extra_select},
               list_distinct({lineage_src}) AS source_record_ids, list_distinct({lineage_x}) AS extract_ids
        FROM record rec
        JOIN ({sets[0][0]}) a0 ON a0.id = rec.id{joins}{extra_join}
        LEFT JOIN (SELECT id, min(effective_at) AS deleted_at FROM assertion
                   WHERE entity = {lit(obj)} AND field = '{DELETED_FIELD}' AND recorded_at <= k
                     AND effective_at <= day_end(t) GROUP BY id) d ON d.id = rec.id
        WHERE rec.entity = {lit(obj)} AND rec.known_since <= k
          AND (rec.created_at IS NULL OR rec.created_at <= day_end(t)){extra_where}"""


def _cols(spec: str) -> list[tuple[str, str, str]]:
    """`alias=Field[:kind]` words to (alias, raw field, kind); kind is text unless stated."""
    out = []
    for word in spec.split():
        alias, _, rest = word.partition("=")
        field, _, kind = rest.partition(":")
        out.append((alias, field, kind or "text"))
    return out


def _entity_macros() -> list[str]:
    def macro(name, obj, key, asof, latest="", **extra):
        return _entity_macro(name, obj, key, _cols(asof), _cols(latest), **extra)

    return [
        macro(
            "account",
            "Account",
            "account_id",
            "name=Name tier=Tier__c billing_country=BillingCountry billing_country_code=BillingCountryCode",
        ),
        macro(
            "campaign",
            "Campaign",
            "campaign_id",
            "name=Name type=Type start_date=StartDate:DATE end_date=EndDate:DATE is_active=IsActive:BOOLEAN",
        ),
        macro(
            "touch",
            "CampaignMember",
            "touch_id",
            "campaign_id=CampaignId lead_id=LeadId status=Status first_responded_date=FirstRespondedDate:DATE",
        ),
        macro(
            "lead",
            "Lead",
            "lead_id",
            "owner_id=OwnerId created_by_id=CreatedById lead_source=LeadSource tier=Tier__c is_converted=IsConverted:BOOLEAN"
            " converted_date=ConvertedDate:DATE converted_opportunity_id=ConvertedOpportunityId converted_account_id=ConvertedAccountId",
            "mql_date=MQL_Date__c:DATE sales_offered_date=Sales_Offered_Date__c:DATE",
        ),
        macro(
            "opportunity",
            "Opportunity",
            "opportunity_id",
            "account_id=AccountId created_by_id=CreatedById campaign_id=CampaignId lead_source=LeadSource type=Type"
            " owner_id=OwnerId sourcing_user_id=Sourcing_User__c",
            "stage=StageName amount_cents=Amount:cents close_date=CloseDate:DATE",
        ),
        macro(
            "person",
            "people",
            "person_id",
            "",
            "name=name email=email role=role team=team segment=segment region=region start_date=start_date:DATE end_date=end_date:DATE",
            extra_select=", u.user_id",
            extra_join=""" LEFT JOIN (SELECT lower(max(value) FILTER (WHERE field = 'Email')) AS em, min(id) AS user_id
                 FROM known_latest('User', k) GROUP BY id HAVING em IS NOT NULL) u ON u.em = lower(a0.email)""",
        ),
        macro(
            "requisition",
            "requisitions",
            "req_id",
            "",
            "team=team role=role planned_start=planned_start:DATE status=status person_id=person_id"
            " opened_date=opened_date:DATE closed_date=closed_date:DATE",
            extra_select=", CASE WHEN a0.closed_date IS NOT NULL AND a0.closed_date <= t THEN a0.status ELSE 'open' END AS status_at_t",
            extra_where=" AND a0.opened_date <= t",
        ),
    ]


OTHER = [
    f"""CREATE OR REPLACE MACRO asof_spend(t, k) AS TABLE
        WITH a AS ({_pivot("spend", "known_latest('spend', k)", [("campaign_id", "campaign_id", "text"), ("month", "month", "DATE"), ("amount_cents", "amount_cents", "BIGINT")])})
        SELECT campaign_id, month, sum(amount_cents) AS amount_cents,
               list_distinct(flatten(list(_src))) AS source_record_ids, list_distinct(flatten(list(_xs))) AS extract_ids
        FROM a WHERE month <= t GROUP BY campaign_id, month""",
    """CREATE OR REPLACE MACRO asof_extract(t, k) AS TABLE
        SELECT e.extract_id, e.source_system, e.extracted_at, e.content_hash,
               list(o.object ORDER BY o.object) AS objects
        FROM extract e JOIN extract_object o USING (extract_id) WHERE e.extracted_at <= k
        GROUP BY ALL""",
    # operational state: one row per interval of constant stage, amount, close date and owner
    """CREATE OR REPLACE MACRO asof_opportunity_state(t, k) AS TABLE
        WITH c AS (
            SELECT id, effective_at AS valid_from, max(recorded_at) AS recorded_at,
                   arg_max_null(value, (recorded_at, source)) FILTER (WHERE field = 'StageName') AS stage,
                   arg_max_null(value, (recorded_at, source)) FILTER (WHERE field = 'Amount') AS amount,
                   arg_max_null(value, (recorded_at, source)) FILTER (WHERE field = 'CloseDate') AS close_date,
                   arg_max_null(value, (recorded_at, source)) FILTER (WHERE field = 'OwnerId') AS owner,
                   bool_or(field = 'StageName') AS has_stage, bool_or(field = 'Amount') AS has_amount,
                   bool_or(field = 'CloseDate') AS has_close, bool_or(field = 'OwnerId') AS has_owner,
                   list_distinct(list(source)) AS source_record_ids, list_distinct(list(extract_id)) AS extract_ids
            FROM assertion
            WHERE entity = 'Opportunity' AND field IN ('StageName', 'Amount', 'CloseDate', 'OwnerId')
              AND recorded_at <= k AND effective_at <= day_end(t)
            GROUP BY id, effective_at),
        f AS (
            SELECT id, valid_from, recorded_at, source_record_ids, extract_ids,
                   last_value(CASE WHEN has_stage THEN {'v': stage} END IGNORE NULLS) OVER w AS st,
                   last_value(CASE WHEN has_amount THEN {'v': amount} END IGNORE NULLS) OVER w AS am,
                   last_value(CASE WHEN has_close THEN {'v': close_date} END IGNORE NULLS) OVER w AS cd,
                   last_value(CASE WHEN has_owner THEN {'v': owner} END IGNORE NULLS) OVER w AS ow,
                   lead(valid_from) OVER w AS valid_to
            FROM c WINDOW w AS (PARTITION BY id ORDER BY valid_from))
        SELECT id AS opportunity_id, valid_from, valid_to, st.v AS stage, cents(am.v) AS amount_cents,
               CAST(cd.v AS DATE) AS close_date, ow.v AS owner_id, recorded_at, source_record_ids, extract_ids
        FROM f""",
    # selling spells as known by K (all of them); the T-aware views below filter this
    f"""CREATE OR REPLACE MACRO spells_known(k) AS TABLE
        WITH st AS (
            SELECT id, value AS stage, effective_at AS eff, recorded_at AS rec, source, extract_id,
                   value IN {CLOSED} AS closed
            FROM assertion WHERE entity = 'Opportunity' AND field = 'StageName' AND recorded_at <= k),
        lab AS (SELECT *, lag(closed) OVER w AS prev_closed FROM st WINDOW w AS (PARTITION BY id ORDER BY eff, source)),
        num AS (
            SELECT *, 1 + sum(CASE WHEN COALESCE(prev_closed, FALSE) AND NOT closed THEN 1 ELSE 0 END)
                          OVER (PARTITION BY id ORDER BY eff, source) AS spell_no
            FROM lab),
        sp AS (
            SELECT id, spell_no, min(eff) AS first_eff, min(rec) AS first_rec,
                   arg_max(closed, (eff, source)) AS is_closed, arg_max(stage, (eff, source)) AS final_stage,
                   min(eff) FILTER (WHERE closed) AS closed_at, min(rec) FILTER (WHERE closed) AS closed_rec,
                   list_distinct(list(source)) AS src, list_distinct(list(extract_id)) AS xs
            FROM num GROUP BY id, spell_no),
        sp2 AS (SELECT *, lead(first_eff) OVER (PARTITION BY id ORDER BY spell_no) AS reopened_at FROM sp),
        vals AS (
            SELECT sp2.id, sp2.spell_no,
                   arg_max_null(a.value, (a.effective_at, a.recorded_at, a.source)) FILTER (WHERE a.field = 'CloseDate') AS close_txt,
                   arg_max_null(a.recorded_at, (a.effective_at, a.recorded_at, a.source)) FILTER (WHERE a.field = 'CloseDate') AS close_rec,
                   arg_max_null(a.value, (a.effective_at, a.recorded_at, a.source)) FILTER (WHERE a.field = 'Amount') AS amount_txt,
                   list_distinct(list(a.source)) AS asrc
            FROM sp2 JOIN assertion a
              ON a.entity = 'Opportunity' AND a.id = sp2.id AND a.field IN ('CloseDate', 'Amount')
             AND a.recorded_at <= k AND a.effective_at < COALESCE(sp2.reopened_at, TIMESTAMP 'infinity')
            GROUP BY sp2.id, sp2.spell_no),
        dl AS (SELECT id, min(effective_at) AS deleted_at, min(source) AS dsrc FROM assertion
               WHERE entity = 'Opportunity' AND field = '{DELETED_FIELD}' AND recorded_at <= k GROUP BY id)
        SELECT sp2.id AS opportunity_id, sp2.spell_no,
               CASE WHEN sp2.spell_no = 1 THEN r.created_at ELSE sp2.first_eff END AS start_at,
               CASE WHEN sp2.spell_no = 1 THEN r.known_since ELSE sp2.first_rec END AS start_recorded_at,
               CASE WHEN sp2.is_closed THEN sp2.closed_at
                    WHEN sp2.reopened_at IS NULL THEN dl.deleted_at END AS end_at,
               CASE WHEN sp2.is_closed THEN sp2.closed_rec
                    WHEN sp2.reopened_at IS NULL THEN dl.deleted_at END AS end_recorded_at,
               CASE WHEN sp2.is_closed THEN CAST(vals.close_txt AS DATE) END AS close_date,
               CASE WHEN sp2.is_closed THEN vals.close_rec END AS close_date_recorded_at,
               cents(vals.amount_txt) AS amount_cents,
               CASE WHEN sp2.is_closed THEN CASE WHEN sp2.final_stage = 'Closed Won' THEN 'won' ELSE 'lost' END
                    WHEN sp2.reopened_at IS NULL AND dl.deleted_at IS NOT NULL THEN 'deleted'
                    ELSE 'open' END AS outcome,
               sp2.reopened_at,
               list_distinct(sp2.src || COALESCE(vals.asrc, []) || CASE WHEN dl.dsrc IS NULL THEN [] ELSE [dl.dsrc] END) AS source_record_ids,
               sp2.xs AS extract_ids
        FROM sp2 JOIN record r ON r.entity = 'Opportunity' AND r.id = sp2.id
        LEFT JOIN vals ON vals.id = sp2.id AND vals.spell_no = sp2.spell_no
        LEFT JOIN dl ON dl.id = sp2.id""",
    """CREATE OR REPLACE MACRO asof_opportunity_spell(t, k) AS TABLE
        SELECT * FROM spells_known(k) WHERE start_at <= day_end(t)""",
    # commercial: known by K, created by T, not deleted by T, not closed by T (R2)
    f"""CREATE OR REPLACE MACRO asof_opportunity_open(t, k) AS TABLE
        WITH s AS (SELECT DISTINCT opportunity_id FROM spells_known(k)
                   WHERE outcome IN ('won', 'lost') AND close_date <= t
                     AND (reopened_at IS NULL OR reopened_at > day_end(t))),
        d AS (SELECT DISTINCT id FROM assertion WHERE entity = 'Opportunity' AND field = '{DELETED_FIELD}'
                AND recorded_at <= k AND effective_at <= day_end(t))
        SELECT r.id AS opportunity_id, (s.opportunity_id IS NULL AND d.id IS NULL) AS is_open
        FROM record r LEFT JOIN s ON s.opportunity_id = r.id LEFT JOIN d ON d.id = r.id
        WHERE r.entity = 'Opportunity' AND r.known_since <= k AND r.created_at <= day_end(t)""",
    # R8: each non-null Sales_Offered_Date__c recorded by K starts an episode
    """CREATE OR REPLACE MACRO asof_demand_episode(t, k) AS TABLE
        WITH off AS (
            SELECT id AS lead_id, value AS offered_on, effective_at AS off_eff, recorded_at AS off_rec, source, extract_id,
                   row_number() OVER (PARTITION BY id ORDER BY effective_at, source) AS offer_seq
            FROM assertion WHERE entity = 'Lead' AND field = 'Sales_Offered_Date__c' AND value IS NOT NULL
              AND recorded_at <= k),
        w AS (SELECT *, lead(off_eff) OVER (PARTITION BY lead_id ORDER BY offer_seq) AS next_eff FROM off),
        o AS (
            SELECT w.lead_id, w.offer_seq,
                   arg_max_null(a.value, (a.effective_at, a.source)) FILTER (WHERE a.field = 'Disposition__c') AS disposition,
                   arg_max_null(a.effective_at, (a.effective_at, a.source)) FILTER (WHERE a.field = 'Disposition__c') AS outcome_at,
                   arg_max_null(a.value, (a.effective_at, a.source)) FILTER (WHERE a.field = 'Disposition_Reason__c') AS reason,
                   list_distinct(list(a.source)) AS osrc
            FROM w JOIN assertion a
              ON a.entity = 'Lead' AND a.id = w.lead_id AND a.field IN ('Disposition__c', 'Disposition_Reason__c')
             AND a.recorded_at <= k AND a.effective_at <= day_end(t)
             AND a.effective_at >= w.off_eff AND a.effective_at < COALESCE(w.next_eff, TIMESTAMP 'infinity')
            GROUP BY w.lead_id, w.offer_seq),
        m AS (SELECT id, arg_max_null(value, (recorded_at, effective_at, source)) AS mql FROM assertion
              WHERE entity = 'Lead' AND field = 'MQL_Date__c' AND recorded_at <= k GROUP BY id)
        SELECT w.lead_id, w.offer_seq, CAST(w.offered_on AS DATE) AS offered_on, w.off_rec AS offered_recorded_at,
               (w.offer_seq = 1 AND m.mql IS NOT NULL) AS mql_linked,
               COALESCE(lower(o.disposition), 'open') AS outcome, o.outcome_at,
               CASE WHEN o.disposition IS NULL THEN NULL ELSE o.reason END AS reason,
               CASE WHEN o.disposition IS NULL OR o.reason IS NULL THEN NULL
                    WHEN o.reason = 'no_capacity' THEN 'capacity' ELSE 'fit' END AS reason_class,
               list_distinct([w.source] || COALESCE(o.osrc, [])) AS source_record_ids, [w.extract_id] AS extract_ids
        FROM w LEFT JOIN o ON o.lead_id = w.lead_id AND o.offer_seq = w.offer_seq LEFT JOIN m ON m.id = w.lead_id""",
    """CREATE OR REPLACE MACRO asof_lead_event(t, k) AS TABLE
        WITH ka AS (SELECT * FROM known_asof('Lead', t, k)),
        kl AS (SELECT * FROM known_latest('Lead', k))
        SELECT r.id AS lead_id, 'created' AS event, r.created_at AS effective_at, r.known_since AS recorded_at,
               ['salesforce/Lead/' || r.id] AS source_record_ids
        FROM record r WHERE r.entity = 'Lead' AND r.known_since <= k AND r.created_at <= day_end(t)
        UNION ALL
        SELECT id, 'mql', CAST(CAST(value AS DATE) AS TIMESTAMP), recorded_at, [source]
        FROM kl WHERE field = 'MQL_Date__c' AND value IS NOT NULL AND CAST(value AS DATE) <= t
        UNION ALL
        SELECT lead_id, outcome, outcome_at, outcome_at, source_record_ids
        FROM asof_demand_episode(t, k) WHERE outcome <> 'open' AND outcome_at IS NOT NULL
        UNION ALL
        SELECT a.id, 'converted', CAST(CAST(a.value AS DATE) AS TIMESTAMP), a.recorded_at, [a.source]
        FROM ka a JOIN ka c ON c.id = a.id AND c.field = 'IsConverted' AND c.value = 'true'
        WHERE a.field = 'ConvertedDate' AND a.value IS NOT NULL""",
    # roster intervals: start_date opens the first interval; later changes open at the extract that showed them
    """CREATE OR REPLACE MACRO asof_assignment(t, k) AS TABLE
        WITH p AS (SELECT id, CAST(max(value) FILTER (WHERE field = 'start_date') AS DATE) AS sd,
                          CAST(max(value) FILTER (WHERE field = 'end_date') AS DATE) AS ed
                   FROM known_latest('people', k) GROUP BY id),
        c AS (
            SELECT a.id,
                   CASE WHEN a.effective_at = r.first_extract_at THEN least(p.sd, CAST(r.first_extract_at AS DATE))
                        ELSE CAST(a.effective_at AS DATE) END AS valid_from,
                   a.field, a.value, a.recorded_at, a.source, a.extract_id, p.ed
            FROM assertion a JOIN record r ON r.entity = 'people' AND r.id = a.id JOIN p ON p.id = a.id
            WHERE a.entity = 'people' AND a.field IN ('role', 'team', 'segment', 'region') AND a.recorded_at <= k),
        g AS (
            SELECT id, valid_from, max(ed) AS ed, max(recorded_at) AS recorded_at,
                   arg_max_null(value, (recorded_at, source)) FILTER (WHERE field = 'role') AS role,
                   arg_max_null(value, (recorded_at, source)) FILTER (WHERE field = 'team') AS team,
                   arg_max_null(value, (recorded_at, source)) FILTER (WHERE field = 'segment') AS segment,
                   arg_max_null(value, (recorded_at, source)) FILTER (WHERE field = 'region') AS region,
                   bool_or(field = 'role') AS has_role, bool_or(field = 'team') AS has_team,
                   bool_or(field = 'segment') AS has_segment, bool_or(field = 'region') AS has_region,
                   list_distinct(list(source)) AS source_record_ids, list_distinct(list(extract_id)) AS extract_ids
            FROM c GROUP BY id, valid_from),
        f AS (
            SELECT id, valid_from, ed, recorded_at, source_record_ids, extract_ids,
                   last_value(CASE WHEN has_role THEN {'v': role} END IGNORE NULLS) OVER w AS ro,
                   last_value(CASE WHEN has_team THEN {'v': team} END IGNORE NULLS) OVER w AS te,
                   last_value(CASE WHEN has_segment THEN {'v': segment} END IGNORE NULLS) OVER w AS se,
                   last_value(CASE WHEN has_region THEN {'v': region} END IGNORE NULLS) OVER w AS re,
                   lead(valid_from) OVER w AS next_from
            FROM g WINDOW w AS (PARTITION BY id ORDER BY valid_from))
        SELECT id AS person_id, valid_from, COALESCE(next_from, ed + 1) AS valid_to, ro.v AS role, te.v AS team,
               se.v AS segment, re.v AS region, recorded_at, source_record_ids, extract_ids
        FROM f WHERE valid_from <= t""",
]

# Names that need no further validation: the contract's canonical tables plus two helpers.
VIEW_NAMES = (
    "account", "person", "assignment", "requisition", "lead", "lead_event", "opportunity",
    "opportunity_state", "opportunity_spell", "opportunity_open", "campaign", "touch", "spend",
    "demand_episode", "extract",
)  # fmt: skip


def install_views(con) -> None:
    for statement in [*SCALARS, *_entity_macros(), *OTHER]:
        con.execute(statement)


__all__ = ["VIEW_NAMES", "ident", "install_views"]

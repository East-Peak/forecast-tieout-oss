"""Canonical views as parameterized relations: DuckDB table macros `asof_<table>(t, k)`.

`t` is a business date and `k` a knowledge instant. Two readings of an attribute coexist, never mixed:

- as of T: the latest assertion effective by the end of day T and recorded by K (attributes);
- restating: the latest assertion recorded by K whatever its effective time (measures: amount,
  close date, stage, MQL date), so a late correction restates a closed period for K at or after it.
"""

from ..contract.keys import DELETED_FIELD
from ..contract.schemas import SCHEMAS
from .sql import ISO, created_field, ident, lit

CLOSED = "('Closed Won', 'Closed Lost')"
TS = f"strptime({{x}}, '{ISO}')"

ASOF_KEY = "(effective_at, prec(assumed_since_creation), recorded_at, source)"
LATEST_KEY = "(recorded_at, effective_at, prec(assumed_since_creation), source)"

SCALARS = [
    "CREATE OR REPLACE MACRO day_end(t) AS CAST(t AS TIMESTAMP) + INTERVAL 86399 SECOND",
    "CREATE OR REPLACE MACRO cents(txt) AS CAST(CAST(txt AS DECIMAL(18, 2)) * 100 AS BIGINT)",
    f"CREATE OR REPLACE MACRO ts(txt) AS strptime(txt, '{ISO}')",
    # inferred evidence (a value assumed since creation) loses every tie against a real assertion
    "CREATE OR REPLACE MACRO prec(inferred) AS CASE WHEN COALESCE(inferred, FALSE) THEN 0 ELSE 1 END",
    f"""CREATE OR REPLACE MACRO known_asof(e, t, k) AS TABLE
        SELECT id, field,
               arg_max_null(value, {ASOF_KEY}) AS value,
               arg_max_null(source, {ASOF_KEY}) AS source,
               arg_max_null(extract_id, {ASOF_KEY}) AS extract_id,
               arg_max_null(recorded_at, {ASOF_KEY}) AS recorded_at,
               arg_max_null(assumed_since_creation, {ASOF_KEY}) AS assumed_since_creation
        FROM assertion
        WHERE entity = e AND field NOT IN ('{DELETED_FIELD}', '_restored') AND recorded_at <= k AND effective_at <= day_end(t)
        GROUP BY id, field""",
    f"""CREATE OR REPLACE MACRO known_latest(e, k) AS TABLE
        SELECT id, field,
               arg_max_null(value, {LATEST_KEY}) AS value,
               arg_max_null(source, {LATEST_KEY}) AS source,
               arg_max_null(extract_id, {LATEST_KEY}) AS extract_id,
               max(recorded_at) AS recorded_at, CAST(NULL AS BOOLEAN) AS assumed_since_creation
        FROM assertion
        WHERE entity = e AND field NOT IN ('{DELETED_FIELD}', '_restored') AND recorded_at <= k
        GROUP BY id, field""",
    # the records known by K with the creation time evidence gives (known-since for a record no
    # snapshot shows); `f` is the creation field, '' for objects that have none
    """CREATE OR REPLACE MACRO records_known(e, f, k) AS TABLE
        SELECT r.id, r.system, r.known_since, r.partial,
               COALESCE(c.created_at, CASE WHEN f = '' THEN NULL ELSE r.known_since END) AS created_at
        FROM record r
        LEFT JOIN (SELECT id, ts(arg_max_null(value, (recorded_at, source))) AS created_at FROM assertion
                   WHERE entity = e AND field = f AND recorded_at <= k GROUP BY id) c ON c.id = r.id
        WHERE r.entity = e AND r.known_since <= k""",
    f"""CREATE OR REPLACE MACRO deleted_state(e, t, k) AS TABLE
        SELECT id, obs AS deleted_at FROM (
            SELECT id, arg_max(field, (effective_at, field)) AS last, max(effective_at) AS obs FROM assertion
            WHERE entity = e AND field IN ('{DELETED_FIELD}', '_restored') AND recorded_at <= k AND effective_at <= day_end(t)
            GROUP BY id) WHERE last = '{DELETED_FIELD}'""",
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
        FROM records_known({lit(obj)}, '{created_field(obj) or ""}', k) rec
        JOIN ({sets[0][0]}) a0 ON a0.id = rec.id{joins}{extra_join}
        LEFT JOIN deleted_state({lit(obj)}, t, k) d ON d.id = rec.id
        WHERE (rec.created_at IS NULL OR rec.created_at <= day_end(t)){extra_where}"""


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
    # operational state: one row per interval of constant stage, amount, close date and owner,
    # each value with its own recorded time, source and extract
    """CREATE OR REPLACE MACRO asof_opportunity_state(t, k) AS TABLE
        WITH c AS (
            SELECT id, effective_at AS valid_from,
                   arg_max_null({'v': value, 'r': recorded_at, 's': source, 'x': extract_id}, (prec(assumed_since_creation), recorded_at, source)) FILTER (WHERE field = 'StageName') AS stage,
                   arg_max_null({'v': value, 'r': recorded_at, 's': source, 'x': extract_id}, (prec(assumed_since_creation), recorded_at, source)) FILTER (WHERE field = 'Amount') AS amount,
                   arg_max_null({'v': value, 'r': recorded_at, 's': source, 'x': extract_id}, (prec(assumed_since_creation), recorded_at, source)) FILTER (WHERE field = 'CloseDate') AS close_date,
                   arg_max_null({'v': value, 'r': recorded_at, 's': source, 'x': extract_id}, (prec(assumed_since_creation), recorded_at, source)) FILTER (WHERE field = 'OwnerId') AS owner,
                   bool_or(field = 'StageName') AS has_stage, bool_or(field = 'Amount') AS has_amount,
                   bool_or(field = 'CloseDate') AS has_close, bool_or(field = 'OwnerId') AS has_owner
            FROM assertion
            WHERE entity = 'Opportunity' AND field IN ('StageName', 'Amount', 'CloseDate', 'OwnerId')
              AND recorded_at <= k AND effective_at <= day_end(t)
            GROUP BY id, effective_at),
        f AS (
            SELECT id, valid_from,
                   last_value(CASE WHEN has_stage THEN stage END IGNORE NULLS) OVER w AS st,
                   last_value(CASE WHEN has_amount THEN amount END IGNORE NULLS) OVER w AS am,
                   last_value(CASE WHEN has_close THEN close_date END IGNORE NULLS) OVER w AS cd,
                   last_value(CASE WHEN has_owner THEN owner END IGNORE NULLS) OVER w AS ow,
                   lead(valid_from) OVER w AS valid_to
            FROM c WINDOW w AS (PARTITION BY id ORDER BY valid_from))
        SELECT id AS opportunity_id, valid_from, valid_to,
               st.v AS stage, st.r AS stage_recorded_at, st.s AS stage_source,
               cents(am.v) AS amount_cents, am.r AS amount_recorded_at, am.s AS amount_source,
               CAST(cd.v AS DATE) AS close_date, cd.r AS close_date_recorded_at, cd.s AS close_date_source,
               ow.v AS owner_id, ow.r AS owner_recorded_at, ow.s AS owner_source,
               greatest(st.r, am.r, cd.r, ow.r) AS recorded_at,
               list_filter([st.s, am.s, cd.s, ow.s], lambda x: x IS NOT NULL) AS source_record_ids,
               list_filter([st.x, am.x, cd.x, ow.x], lambda x: x IS NOT NULL) AS extract_ids
        FROM f""",
    # selling spells by their stage rows (observed): the evidence, before any commercial reading
    f"""CREATE OR REPLACE MACRO spells_core(k) AS TABLE
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
            SELECT id, spell_no, min(eff) AS first_eff, arg_min(source, (eff, source)) AS first_src, min(rec) AS first_rec,
                   arg_max(closed, (eff, source)) AS is_closed, arg_max(stage, (eff, source)) AS final_stage,
                   min(eff) FILTER (WHERE closed) AS closed_at, min(rec) FILTER (WHERE closed) AS closed_rec,
                   list_distinct(list(source)) AS src, list_distinct(list(extract_id)) AS xs
            FROM num GROUP BY id, spell_no),
        sp2 AS (
            SELECT *, lead(first_eff) OVER w AS reopened_at, lead(first_src) OVER w AS reopen_src
            FROM sp WINDOW w AS (PARTITION BY id ORDER BY spell_no)),
        vals AS (
            SELECT sp2.id, sp2.spell_no,
                   arg_max_null({{'v': a.value, 'r': a.recorded_at, 's': a.source}}, (a.effective_at, prec(a.assumed_since_creation), a.recorded_at, a.source))
                       FILTER (WHERE a.field = 'CloseDate') AS cd,
                   arg_max_null({{'v': a.value, 'r': a.recorded_at, 's': a.source}}, (a.effective_at, prec(a.assumed_since_creation), a.recorded_at, a.source))
                       FILTER (WHERE a.field = 'Amount') AS am
            FROM sp2 JOIN assertion a
              ON a.entity = 'Opportunity' AND a.id = sp2.id AND a.field IN ('CloseDate', 'Amount') AND a.recorded_at <= k
             AND (a.effective_at, a.source) < (COALESCE(sp2.reopened_at, TIMESTAMP 'infinity'), COALESCE(sp2.reopen_src, ''))
            GROUP BY sp2.id, sp2.spell_no)
        SELECT sp2.id AS opportunity_id, sp2.spell_no,
               CASE WHEN sp2.spell_no = 1 THEN r.created_at ELSE sp2.first_eff END AS start_at,
               CASE WHEN sp2.spell_no = 1 THEN r.known_since ELSE sp2.first_rec END AS start_recorded_at,
               sp2.is_closed, sp2.final_stage, sp2.closed_at, sp2.closed_rec,
               CASE WHEN sp2.is_closed THEN CAST(struct_extract(vals.cd, 'v') AS DATE) END AS close_date,
               CASE WHEN sp2.is_closed THEN struct_extract(vals.cd, 'r') END AS close_date_recorded_at,
               CASE WHEN sp2.is_closed THEN struct_extract(vals.cd, 's') END AS close_date_source,
               cents(struct_extract(vals.am, 'v')) AS amount_cents,
               struct_extract(vals.am, 'r') AS amount_recorded_at, struct_extract(vals.am, 's') AS amount_source,
               sp2.reopened_at,
               list_distinct(sp2.src || list_filter([struct_extract(vals.cd, 's'), struct_extract(vals.am, 's')], lambda x: x IS NOT NULL)) AS source_record_ids,
               sp2.xs AS extract_ids
        FROM sp2 JOIN records_known('Opportunity', 'CreatedDate', k) r ON r.id = sp2.id
        LEFT JOIN vals ON vals.id = sp2.id AND vals.spell_no = sp2.spell_no""",
    # ONE representation of the commercial open stock: facts (creation, closing by effective close
    # date, reopening, deletion, restoration) become events with a delta; the stock is their sum.
    # A fact that cannot change the stock keeps delta 0 and is flagged, never shown as clean.
    f"""CREATE OR REPLACE MACRO flow_known(k) AS TABLE
        WITH sp AS (SELECT * FROM spells_core(k)),
        cr AS (SELECT id, CAST(created_at AS DATE) AS cd, created_at, known_since
               FROM records_known('Opportunity', 'CreatedDate', k)),
        ci AS (
            SELECT opportunity_id AS id, spell_no, close_date AS cs, CAST(reopened_at AS DATE) AS ce, final_stage,
                   closed_at AS obs, greatest(closed_rec, close_date_recorded_at) AS rec, source_record_ids AS src
            FROM sp WHERE is_closed AND close_date IS NOT NULL),
        di AS (
            SELECT d.id, CAST(d.effective_at AS DATE) AS ds, d.effective_at AS obs, d.recorded_at AS rec, d.source AS src,
                   (SELECT min(CAST(q.effective_at AS DATE)) FROM assertion q
                    WHERE q.entity = 'Opportunity' AND q.id = d.id AND q.field = '_restored'
                      AND q.recorded_at <= k AND q.effective_at > d.effective_at) AS de
            FROM assertion d WHERE d.entity = 'Opportunity' AND d.field = '{DELETED_FIELD}' AND d.recorded_at <= k),
        facts AS (
            SELECT id, cd AS d, 'admission' AS kind, 1 AS spell_no, created_at AS obs, known_since AS rec,
                   ['salesforce/Opportunity/' || id] AS src, 0 AS pri, '' AS detail FROM cr
            UNION ALL
            SELECT id, cs, 'close', spell_no, obs, rec, src, 2, final_stage FROM ci
            UNION ALL
            SELECT opportunity_id, CAST(start_at AS DATE), 'reopen', spell_no, start_at, start_recorded_at, source_record_ids, 2, ''
            FROM sp WHERE spell_no > 1
            UNION ALL
            SELECT id, ds, 'delete',
                   COALESCE((SELECT max(spell_no) FROM sp WHERE sp.opportunity_id = di.id AND CAST(sp.start_at AS DATE) <= di.ds), 1),
                   obs, rec, [src], 1, '' FROM di
            UNION ALL
            SELECT q.id, CAST(q.effective_at AS DATE), 'restore',
                   COALESCE((SELECT max(spell_no) FROM sp WHERE sp.opportunity_id = q.id AND CAST(sp.start_at AS DATE) <= CAST(q.effective_at AS DATE)), 1),
                   q.effective_at, q.recorded_at, [q.source], 1, ''
            FROM assertion q WHERE q.entity = 'Opportunity' AND q.field = '_restored' AND q.recorded_at <= k),
        days AS (SELECT DISTINCT id, d FROM facts),
        stt AS (
            SELECT days.id, days.d, cr.cd,
                   (days.d >= cr.cd
                    AND NOT EXISTS (SELECT 1 FROM ci WHERE ci.id = days.id AND ci.cs <= days.d AND (ci.ce IS NULL OR ci.ce > days.d))
                    AND NOT EXISTS (SELECT 1 FROM di WHERE di.id = days.id AND di.ds <= days.d AND (di.de IS NULL OR di.de > days.d))
                   ) AS is_open
            FROM days JOIN cr ON cr.id = days.id),
        dd AS (
            SELECT id, d, CAST(is_open AS INTEGER)
                   - CASE WHEN d = cd THEN 1 ELSE COALESCE(CAST(lag(is_open) OVER (PARTITION BY id ORDER BY d) AS INTEGER), 0) END AS dday
            FROM stt),
        ev AS (
            SELECT f.*, dd.dday,
                   row_number() OVER (PARTITION BY f.id, f.d, CASE WHEN f.kind IN ('delete', 'close') THEN 'out' ELSE 'in' END
                                      ORDER BY f.pri, f.spell_no) AS rk
            FROM facts f JOIN dd ON dd.id = f.id AND dd.d = f.d WHERE f.kind <> 'admission'),
        fin AS (
            SELECT *, CASE WHEN rk = 1 AND dday = -1 AND kind IN ('delete', 'close') THEN -1
                           WHEN rk = 1 AND dday = 1 AND kind IN ('restore', 'reopen') THEN 1 ELSE 0 END AS delta
            FROM ev)
        SELECT id AS opportunity_id, spell_no, 'admission' AS event, d AS business_date, 1 AS delta, obs AS observed_at,
               rec AS recorded_at, CAST([] AS VARCHAR[]) AS flags, src AS source_record_ids
        FROM facts WHERE kind = 'admission'
        UNION ALL
        SELECT id, spell_no,
               CASE kind WHEN 'close' THEN CASE WHEN detail = 'Closed Won' THEN 'win' ELSE 'loss' END
                         WHEN 'delete' THEN 'deleted' ELSE 'reopened' END,
               d, delta, obs, rec,
               list_filter([
                   CASE WHEN kind = 'delete' THEN 'deletion_time_upper_bound' END,
                   CASE WHEN kind = 'restore' THEN 'restoration_time_upper_bound' END,
                   CASE WHEN kind = 'restore' THEN 'restored' END,
                   CASE WHEN kind IN ('close', 'reopen') AND delta = 0 THEN 'contradictory_boundary' END,
                   CASE WHEN kind = 'delete' AND delta <> 0
                         AND EXISTS (SELECT 1 FROM ci WHERE ci.id = fin.id AND ci.cs > fin.d) THEN 'contradictory_boundary' END,
                   CASE WHEN kind IN ('delete', 'restore') AND delta = 0 THEN 'not_in_open_stock' END
               ], lambda x: x IS NOT NULL),
               src
        FROM fin""",
    """CREATE OR REPLACE MACRO asof_opportunity_flow(t, k) AS TABLE
        SELECT * FROM flow_known(k) WHERE business_date <= t""",
    # selling spells: the observed stage evidence read through the flow (outcome, exit and flags)
    """CREATE OR REPLACE MACRO spells_known(k) AS TABLE
        WITH fl AS (SELECT * FROM flow_known(k)),
        lf AS (
            SELECT opportunity_id, spell_no,
                   arg_max(event, (business_date, observed_at, CASE event WHEN 'admission' THEN 0 WHEN 'reopened' THEN 1 ELSE 2 END)) FILTER (WHERE delta <> 0) AS event,
                   arg_max(observed_at, (business_date, observed_at, CASE event WHEN 'admission' THEN 0 WHEN 'reopened' THEN 1 ELSE 2 END)) FILTER (WHERE delta <> 0) AS obs,
                   arg_max(recorded_at, (business_date, observed_at, CASE event WHEN 'admission' THEN 0 WHEN 'reopened' THEN 1 ELSE 2 END)) FILTER (WHERE delta <> 0) AS rec,
                   list_distinct(flatten(list(flags))) AS flags, list_distinct(flatten(list(source_record_ids))) AS src
            FROM fl GROUP BY opportunity_id, spell_no)
        SELECT sp.opportunity_id, sp.spell_no, sp.start_at, sp.start_recorded_at,
               CASE WHEN lf.event IN ('win', 'loss', 'deleted') THEN lf.obs WHEN sp.is_closed THEN sp.closed_at END AS end_at,
               CASE WHEN lf.event IN ('win', 'loss', 'deleted') THEN lf.rec WHEN sp.is_closed THEN sp.closed_rec END AS end_recorded_at,
               sp.close_date, sp.close_date_recorded_at, sp.close_date_source,
               sp.amount_cents, sp.amount_recorded_at, sp.amount_source,
               CASE WHEN lf.event = 'win' THEN 'won' WHEN lf.event = 'loss' THEN 'lost' WHEN lf.event = 'deleted' THEN 'deleted'
                    WHEN sp.is_closed THEN CASE WHEN sp.final_stage = 'Closed Won' THEN 'won' ELSE 'lost' END
                    ELSE 'open' END AS outcome,
               CASE WHEN sp.is_closed THEN CASE WHEN sp.final_stage = 'Closed Won' THEN 'won' ELSE 'lost' END ELSE 'open' END AS observed_outcome,
               sp.reopened_at, COALESCE(lf.flags, CAST([] AS VARCHAR[])) AS flags,
               list_distinct(sp.source_record_ids || COALESCE(lf.src, CAST([] AS VARCHAR[]))) AS source_record_ids,
               sp.extract_ids
        FROM spells_core(k) sp LEFT JOIN lf ON lf.opportunity_id = sp.opportunity_id AND lf.spell_no = sp.spell_no""",
    """CREATE OR REPLACE MACRO asof_opportunity_spell(t, k) AS TABLE
        SELECT * FROM spells_known(k) WHERE start_at <= day_end(t)""",
    # commercial: the stock at T is the sum of the flow's deltas to T
    """CREATE OR REPLACE MACRO asof_opportunity_open(t, k) AS TABLE
        WITH f AS (SELECT opportunity_id, sum(delta) AS n FROM flow_known(k) WHERE business_date <= t GROUP BY 1)
        SELECT r.id AS opportunity_id, COALESCE(f.n, 0) = 1 AS is_open
        FROM records_known('Opportunity', 'CreatedDate', k) r LEFT JOIN f ON f.opportunity_id = r.id
        WHERE CAST(r.created_at AS DATE) <= t""",
    # R8: each non-null Sales_Offered_Date__c recorded by K starts an episode, numbered over all of
    # them; only offers dated on or before T are demand at T
    f"""CREATE OR REPLACE MACRO asof_demand_episode(t, k) AS TABLE
        WITH off AS (
            SELECT id AS lead_id, value AS offered_on, effective_at AS off_eff, recorded_at AS off_rec, source, extract_id,
                   row_number() OVER (PARTITION BY id ORDER BY effective_at, source) AS offer_seq
            FROM assertion WHERE entity = 'Lead' AND field = 'Sales_Offered_Date__c' AND value IS NOT NULL
              AND recorded_at <= k),
        w AS (SELECT *, lead(off_eff) OVER (PARTITION BY lead_id ORDER BY offer_seq) AS next_eff FROM off),
        o AS (
            SELECT w.lead_id, w.offer_seq,
                   arg_max_null(a.value, (a.effective_at, prec(a.assumed_since_creation), a.source)) FILTER (WHERE a.field = 'Disposition__c') AS disposition,
                   arg_max_null(a.effective_at, (a.effective_at, prec(a.assumed_since_creation), a.source)) FILTER (WHERE a.field = 'Disposition__c') AS outcome_at,
                   arg_max_null(a.value, (a.effective_at, prec(a.assumed_since_creation), a.source)) FILTER (WHERE a.field = 'Disposition_Reason__c') AS reason,
                   list_distinct(list(a.source)) AS osrc
            FROM w JOIN assertion a
              ON a.entity = 'Lead' AND a.id = w.lead_id AND a.field IN ('Disposition__c', 'Disposition_Reason__c')
             AND a.recorded_at <= k AND a.effective_at <= day_end(t)
             AND a.effective_at >= w.off_eff AND a.effective_at < COALESCE(w.next_eff, TIMESTAMP 'infinity')
            GROUP BY w.lead_id, w.offer_seq),
        m AS (SELECT id, arg_max_null(value, {LATEST_KEY}) AS mql FROM assertion
              WHERE entity = 'Lead' AND field = 'MQL_Date__c' AND recorded_at <= k GROUP BY id)
        SELECT w.lead_id, w.offer_seq, CAST(w.offered_on AS DATE) AS offered_on, w.off_rec AS offered_recorded_at,
               (w.offer_seq = 1 AND m.mql IS NOT NULL) AS mql_linked,
               COALESCE(lower(o.disposition), 'open') AS outcome, o.outcome_at,
               CASE WHEN o.disposition IS NULL THEN NULL ELSE o.reason END AS reason,
               CASE WHEN o.disposition IS NULL OR o.reason IS NULL THEN NULL
                    WHEN o.reason = 'no_capacity' THEN 'capacity' ELSE 'fit' END AS reason_class,
               list_distinct([w.source] || COALESCE(o.osrc, [])) AS source_record_ids, [w.extract_id] AS extract_ids
        FROM w LEFT JOIN o ON o.lead_id = w.lead_id AND o.offer_seq = w.offer_seq LEFT JOIN m ON m.id = w.lead_id
        WHERE CAST(w.offered_on AS DATE) <= t""",
    """CREATE OR REPLACE MACRO asof_lead_event(t, k) AS TABLE
        WITH ka AS (SELECT * FROM known_asof('Lead', t, k)),
        kl AS (SELECT * FROM known_latest('Lead', k))
        SELECT r.id AS lead_id, 'created' AS event, r.created_at AS effective_at, r.known_since AS recorded_at,
               ['salesforce/Lead/' || r.id] AS source_record_ids
        FROM records_known('Lead', 'CreatedDate', k) r WHERE r.created_at <= day_end(t)
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
    "opportunity_state", "opportunity_spell", "opportunity_open", "opportunity_flow", "campaign", "touch", "spend",
    "demand_episode", "extract",
)  # fmt: skip


def install_views(con) -> None:
    for statement in [*SCALARS, *_entity_macros(), *OTHER]:
        con.execute(statement)


__all__ = ["VIEW_NAMES", "ident", "install_views"]

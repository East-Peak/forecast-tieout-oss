"""The as-of API: one small typed surface over the store, for a business date T and a knowledge instant K.

Two named modes: `reconstructed` (K = the latest extract time: today's best account of T) and
`contemporaneous` (K = the end of day T: what the business believed then).
`stage_at` is operational (transitions as observed); `open_at` is commercial (as known by K,
by effective close date). They are different questions and are never mixed.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..contract.keys import AS_OF_MODES, CONTEMPORANEOUS, DELETED_FIELD, RECONSTRUCTED
from ..contract.schemas import SCHEMAS
from .derive import RESTORED_FIELD
from .sql import created_field
from .store import Store
from .views import ASOF_KEY, VIEW_NAMES

NO_EXTRACT = "no_extract_at_or_before_known_at"
NOT_EXTRACTED = "object_not_extracted"
NOT_IN_SNAPSHOT = "record_not_in_snapshot"  # history shows the record, no extract does


@dataclass(frozen=True)
class FieldValue:
    value: str | None
    flags: tuple[str, ...] = ()
    unavailable: str | None = None


@dataclass(frozen=True)
class Availability:
    available: bool
    unavailable: str | None = None
    rows_in_first_extract: int | None = None


@dataclass(frozen=True)
class Closing:
    close_date: date | None  # the CloseDate field as known by K (commercial)
    observed_closed_recorded_at: (
        datetime | None
    )  # when the closing transition was recorded; None if not closed


@dataclass(frozen=True)
class Status:
    status: str  # present, deleted, or unknown (the record is not known by K or not created by T)
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Episode:
    lead_id: str
    offer_seq: int
    offered_on: date
    mql_linked: bool
    outcome: str  # admitted, rejected, expired or open
    reason: str | None
    reason_class: str | None  # fit or capacity


@dataclass(frozen=True)
class AsOf:
    """The store as of business date `t` and knowledge instant `k` (naive UTC)."""

    store: Store
    t: date
    k: datetime
    mode: str = "custom"

    @classmethod
    def at(cls, store: Store, t: date, mode: str) -> "AsOf":
        if mode == RECONSTRUCTED:
            k = store.latest_extract_at
            if k is None:
                raise ValueError("the store has no extracts")
        elif mode == CONTEMPORANEOUS:
            k = datetime.combine(t, datetime.min.time()) + timedelta(days=1, seconds=-1)
        else:
            raise ValueError(f"mode must be one of {AS_OF_MODES}, not {mode!r}")
        return cls(store, t, k, mode)

    @classmethod
    def reconstructed(cls, store: Store, t: date) -> "AsOf":
        return cls.at(store, t, RECONSTRUCTED)

    @classmethod
    def contemporaneous(cls, store: Store, t: date) -> "AsOf":
        return cls.at(store, t, CONTEMPORANEOUS)

    # -- plumbing ---------------------------------------------------------
    @property
    def day_end(self) -> datetime:
        return datetime.combine(self.t, datetime.min.time()) + timedelta(
            days=1, seconds=-1
        )

    def _rows(self, sql: str, *params) -> list[tuple]:
        return self.store.con.execute(sql, list(params)).fetchall()

    def relation(self, name: str):
        """A canonical view as of (T, K), as a DuckDB relation to select from."""
        if name not in VIEW_NAMES:
            raise ValueError(f"unknown view {name!r}; choose from {VIEW_NAMES}")
        return self.store.con.cursor().sql(
            f"SELECT * FROM asof_{name}(?, ?)", params=[self.t, self.k]
        )

    # -- fields -----------------------------------------------------------
    def availability(self, system: str, object_name: str) -> Availability:
        """Was the object extracted by an extract of the system at or before K? (R7)"""
        if (
            self._rows(
                "SELECT 1 FROM extract WHERE source_system = ? AND extracted_at <= ? LIMIT 1",
                system,
                self.k,
            )
            == []
        ):
            return Availability(False, NO_EXTRACT)
        listed = self._rows(
            """SELECT row_count FROM listing WHERE system = ? AND object = ? AND extracted_at <= ?
               ORDER BY extracted_at LIMIT 1""",
            system,
            object_name,
            self.k,
        )
        if not listed:
            return Availability(False, NOT_EXTRACTED)
        return Availability(True, None, listed[0][0])

    def field_at(self, entity: str, record_id: str, field: str) -> FieldValue:
        """The value of a field at T as known by K: latest effective, ties to the later record (R2).

        A field without history needs an extract at or before K (R5, R7); history and immutable fields
        carry their own knowledge time.
        """
        if entity not in SCHEMAS:
            raise ValueError(f"unknown object {entity!r}")
        coverage = self.store.coverage
        if field not in coverage.history_fields(
            entity
        ) and field not in coverage.immutable.get(entity, ()):
            gate = self.availability(SCHEMAS[entity].system, entity)
            if not gate.available:
                return FieldValue(None, (), gate.unavailable)
        rows = self._rows(
            f"""SELECT arg_max_null(value, {ASOF_KEY}), arg_max_null(assumed_since_creation, {ASOF_KEY})
               FROM assertion WHERE entity = ? AND id = ? AND field = ? AND recorded_at <= ?
                 AND effective_at <= ? HAVING count(*) > 0""",
            entity,
            record_id,
            field,
            self.k,
            self.day_end,
        )
        if not rows:
            partial = self._rows(
                """SELECT 1 FROM record WHERE entity = ? AND id = ? AND known_since <= ?
                   AND (first_extract_at IS NULL OR first_extract_at > ?)""",
                entity,
                record_id,
                self.k,
                self.k,
            )
            return FieldValue(None, (), NOT_IN_SNAPSHOT if partial else None)
        value, assumed = rows[0]
        return FieldValue(value, ("assumed_since_creation",) if assumed else ())

    def stage_at(self, opportunity_id: str) -> str | None:
        """Operational: the stage most recently observed by T (transitions are never backdated)."""
        return self.field_at("Opportunity", opportunity_id, "StageName").value

    def owner_at(self, opportunity_id: str) -> str | None:
        return self.field_at("Opportunity", opportunity_id, "OwnerId").value

    def status_at(self, entity: str, record_id: str) -> Status:
        """Existence: deleted from the first extract that lacks the record (an upper bound, R4)."""
        last = self._rows(
            """SELECT arg_max(field, (effective_at, field)) FROM assertion
               WHERE entity = ? AND id = ? AND field IN (?, ?) AND recorded_at <= ? AND effective_at <= ?
               HAVING count(*) > 0""",
            entity,
            record_id,
            DELETED_FIELD,
            RESTORED_FIELD,
            self.k,
            self.day_end,
        )
        if last and last[0][0] == DELETED_FIELD:
            return Status("deleted", ("deletion_time_upper_bound",))
        known = self._rows(
            "SELECT 1 FROM records_known(?, ?, ?) WHERE id = ? AND (created_at IS NULL OR created_at <= ?)",
            entity,
            created_field(entity) or "",
            self.k,
            record_id,
            self.day_end,
        )
        flags = ("restoration_time_upper_bound",) if last else ()
        return Status("present" if known else "unknown", flags if known else ())

    # -- opportunities ----------------------------------------------------
    def open_at(self, opportunity_id: str) -> bool:
        """Commercial: known, created, not deleted and not closed by effective CloseDate, as known by K (R2)."""
        rows = self._rows(
            "SELECT is_open FROM asof_opportunity_open(?, ?) WHERE opportunity_id = ?",
            self.t,
            self.k,
            opportunity_id,
        )
        return bool(rows and rows[0][0])

    def open_ids(self) -> list[str]:
        rows = self._rows(
            "SELECT opportunity_id FROM asof_opportunity_open(?, ?) WHERE is_open ORDER BY 1",
            self.t,
            self.k,
        )
        return [r[0] for r in rows]

    def closing(self, opportunity_id: str) -> Closing:
        """The commercial close date and the observed closing transition, kept apart."""
        close = self._rows(
            """SELECT CAST(arg_max_null(value, (recorded_at, effective_at, prec(assumed_since_creation), source)) AS DATE) FROM assertion
               WHERE entity = 'Opportunity' AND id = ? AND field = 'CloseDate' AND recorded_at <= ?""",
            opportunity_id,
            self.k,
        )
        last = self._rows(
            """SELECT outcome, end_recorded_at FROM spells_known(?) WHERE opportunity_id = ?
               ORDER BY spell_no DESC LIMIT 1""",
            self.k,
            opportunity_id,
        )
        observed = last[0][1] if last and last[0][0] in ("won", "lost") else None
        return Closing(close[0][0] if close else None, observed)

    # -- demand -----------------------------------------------------------
    def episodes(self, lead_id: str | None = None) -> list[Episode]:
        """Demand episodes keyed by (lead, offer number), with outcomes as of T and K (R8)."""
        where, params = ("WHERE lead_id = ?", [lead_id]) if lead_id else ("", [])
        rows = self._rows(
            f"""SELECT lead_id, offer_seq, offered_on, mql_linked, outcome, reason, reason_class
                FROM asof_demand_episode(?, ?) {where} ORDER BY lead_id, offer_seq""",
            self.t,
            self.k,
            *params,
        )
        return [Episode(*r) for r in rows]


@dataclass(frozen=True)
class DemandOutcomes:
    counts: dict[str, int]
    reason_classes: dict[str, int]


def _month_start(month: str) -> date:
    return date.fromisoformat(f"{month}-01")


@dataclass(frozen=True)
class Bookings:
    """New-business bookings of a month: known cents plus what could not be priced."""

    total_cents: int  # sum of the known amounts
    deals: int  # closed-won deals in the month, priced or not
    unknown_amount: int  # of those, deals whose amount is not known
    unknown_type: int  # closed-won deals whose Type is not known (no snapshot shows them): not in the total
    bound: str  # "exact", or "lower_bound" when anything above is unknown


def bookings_by_month(asof: AsOf, month: str) -> Bookings:
    """New-business bookings with an effective close date in `month` ("2025-03"), restated by K."""
    (total, deals, no_amount, no_type) = asof._rows(
        """SELECT COALESCE(sum(amount_cents) FILTER (WHERE type = 'New Business'), 0),
                  count(*) FILTER (WHERE type = 'New Business'),
                  count(*) FILTER (WHERE type = 'New Business' AND amount_cents IS NULL),
                  count(*) FILTER (WHERE type IS NULL)
           FROM asof_opportunity(?, ?)
           WHERE stage = 'Closed Won' AND date_trunc('month', close_date) = ?""",
        asof.t,
        asof.k,
        _month_start(month),
    )[0]
    return Bookings(
        int(total),
        deals,
        no_amount,
        no_type,
        "exact" if no_amount + no_type == 0 else "lower_bound",
    )


def mql_count(asof: AsOf, month: str) -> int:
    """Leads whose MQL date, as known by K, falls in `month`."""
    return asof._rows(
        "SELECT count(*) FROM asof_lead(?, ?) WHERE date_trunc('month', mql_date) = ?",
        asof.t,
        asof.k,
        _month_start(month),
    )[0][0]


def demand_outcomes(asof: AsOf, offered_month: str) -> DemandOutcomes:
    """Outcomes at (T, K) of the episodes offered in `offered_month`, with reason classes."""
    rows = asof._rows(
        """SELECT outcome, reason_class, count(*) FROM asof_demand_episode(?, ?)
           WHERE date_trunc('month', offered_on) = ? GROUP BY ALL""",
        asof.t,
        asof.k,
        _month_start(offered_month),
    )
    counts: dict[str, int] = {}
    classes: dict[str, int] = {}
    for outcome, reason_class, n in rows:
        counts[outcome] = counts.get(outcome, 0) + n
        if reason_class:
            classes[reason_class] = classes.get(reason_class, 0) + n
    return DemandOutcomes(counts, classes)

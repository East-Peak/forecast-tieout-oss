"""Canonical keys: the fixed tables of the grid, their keys and grain, and the assertion tuple.

The evidence package builds each table as a view over assertions as of (T, K).
Nothing here is SQL. Every canonical row also carries LINEAGE_COLUMN, the raw
record ids it came from.
"""

from dataclasses import dataclass
from typing import NamedTuple

LINEAGE_COLUMN = "source_record_ids"

# The two as-of modes (design section 1). `known_at` K is the knowledge cutoff.
RECONSTRUCTED = "reconstructed"  # K = now: today's best account of what was true at T
CONTEMPORANEOUS = "contemporaneous"  # K = T: what the business believed then
AS_OF_MODES = (RECONSTRUCTED, CONTEMPORANEOUS)

DEMAND_OUTCOMES = (
    "admitted",
    "rejected",
    "expired",
    "open",
)  # terminal outcome of an episode
REASON_CLASSES = (
    "fit",
    "capacity",
)  # capacity reasons stay distinguishable from fit reasons

DELETED_FIELD = "_deleted"  # pseudo-field of the assertion that records a deletion


@dataclass(frozen=True)
class CanonicalTable:
    name: str
    key: tuple[str, ...]
    grain: str


def _t(name, key, grain):
    return CanonicalTable(name, tuple(key.split()), grain)


CANONICAL_TABLES = {
    t.name: t
    for t in (
        _t("account", "account_id", "one row per Salesforce Account"),
        _t(
            "person",
            "person_id",
            "one row per person in the people system, matched to User",
        ),
        _t(
            "assignment",
            "person_id valid_from",
            "one row per person per interval of constant role, team, segment and region",
        ),
        _t("requisition", "req_id", "one row per hiring requisition"),
        _t("lead", "lead_id", "one row per Salesforce Lead"),
        _t(
            "lead_event",
            "lead_id event effective_at",
            "one row per lead lifecycle event (created, mql, admitted, rejected, expired, converted)",
        ),
        _t(
            "opportunity",
            "opportunity_id",
            "one row per Salesforce Opportunity, with creator and sourcing person",
        ),
        _t(
            "opportunity_state",
            "opportunity_id valid_from",
            "one row per opportunity per interval of constant stage, amount, close date and owner",
        ),
        _t("campaign", "campaign_id", "one row per Campaign"),
        _t(
            "touch", "touch_id", "one row per CampaignMember (one lead in one campaign)"
        ),
        _t("spend", "campaign_id month", "one row per campaign per month"),
        _t(
            "demand_episode",
            "lead_id offered_on",
            "one row per offer of qualified demand to sales: identity, offered date, routing history, terminal outcome and reason class",
        ),
        _t("extract", "extract_id", "one row per extract folder (manifest)"),
    )
}


class Assertion(NamedTuple):
    """One append-only fact. The loader writes these from history and snapshot differences.

    entity       raw object name ("Opportunity"); for a composite key the parts joined by "|"
    id           record key within the entity
    field        raw field name, or DELETED_FIELD
    value        canonical text of the value (dates ISO, money as written in the raw record); None is null
    effective_at business time, ISO datetime UTC
    recorded_at  knowledge time, ISO datetime UTC
    source       "<source_system>/<Object>/<record key>" of the row that stated it, or
                 "<source_system>/<Object>/<record key>#snapshot" for a snapshot difference
    extract_id   the first extract that showed the row or value
    """

    entity: str
    id: str
    field: str
    value: str | None
    effective_at: str
    recorded_at: str
    source: str
    extract_id: str


ASSERTION_FIELDS = Assertion._fields


def lane_key(members: dict[str, str]) -> str:
    """Lane key: `dimension=member` pairs sorted by dimension, joined by `;`; `*` for all."""
    if not members:
        return "*"
    return ";".join(f"{d}={m}" for d, m in sorted(members.items()))


def parse_lane_key(key: str) -> dict[str, str]:
    if key == "*":
        return {}
    members: dict[str, str] = {}
    for part in key.split(";"):
        dimension, sep, member = part.partition("=")
        if not (sep and dimension and member) or dimension in members:
            raise ValueError(f"bad lane key {key!r}")
        members[dimension] = member
    return members

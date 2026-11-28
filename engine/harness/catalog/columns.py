"""The canonical columns a catalog may name. Fixed by the harness; the catalog only selects among them.

A column is reached from an entity directly or through a declared relationship; a few derived columns
(cycle days, creation date, the commercial open flag, the amount as of T) are defined here, in code.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class View:
    name: str
    key: str
    columns: dict[str, str]  # base columns of asof_<name>(t, k): name to type
    simple: dict[str, tuple[str, str]] = field(
        default_factory=dict
    )  # derived, no join: name to (type, SQL)
    joined: dict[str, str] = field(
        default_factory=dict
    )  # derived with a join, main entity only: name to type
    created: str | None = (
        None  # SQL date of the row's creation, for attribute time at_creation
    )
    close: str | None = None  # SQL date of the row's close, for at_close
    label: str = ""

    def typed(self, main: bool = False) -> dict[str, str]:
        out = dict(self.columns)
        out.update({n: t for n, (t, _) in self.simple.items()})
        if main:
            out.update(self.joined)
        return out


def _cols(spec: str) -> dict[str, str]:
    return {w.split(":")[0]: w.split(":")[1] for w in spec.split()}


VIEWS = {
    v.name: v
    for v in (
        View(
            "opportunity", "opportunity_id",
            _cols("opportunity_id:text account_id:text created_by_id:text campaign_id:text lead_source:text type:text"
                  " owner_id:text sourcing_user_id:text stage:text amount_cents:int close_date:date created_at:ts deleted_at:ts"),
            simple={
                "created_date": ("date", "CAST(created_at AS DATE)"),
                "closed_by_t": ("bool", "COALESCE(close_date <= $t, FALSE)"),
                "cycle_days": ("int", "date_diff('day', CAST(created_at AS DATE), close_date)"),
            },
            joined={"is_open": "bool", "amount_at_t_cents": "int"},
            created="CAST(created_at AS DATE)", close="close_date",
        ),
        View(
            "lead", "lead_id",
            _cols("lead_id:text owner_id:text created_by_id:text lead_source:text tier:text is_converted:bool"
                  " converted_date:date converted_opportunity_id:text converted_account_id:text mql_date:date"
                  " sales_offered_date:date created_at:ts deleted_at:ts"),
            simple={"created_date": ("date", "CAST(created_at AS DATE)")},
            created="CAST(created_at AS DATE)",
        ),
        View(
            "demand_episode", "episode_id",
            _cols("lead_id:text offer_seq:int offered_on:date mql_linked:bool outcome:text outcome_at:ts reason:text reason_class:text"),
            simple={
                "episode_id": ("text", "lead_id || '#' || CAST(offer_seq AS VARCHAR)"),
                "outcome_date": ("date", "CAST(outcome_at AS DATE)"),
            },
            created="offered_on",
        ),
        View("account", "account_id", _cols("account_id:text name:text tier:text billing_country:text billing_country_code:text created_at:ts deleted_at:ts")),
        View("campaign", "campaign_id", _cols("campaign_id:text name:text type:text start_date:date end_date:date is_active:bool")),
        View("touch", "touch_id", _cols("touch_id:text campaign_id:text lead_id:text status:text first_responded_date:date")),
        View("person", "person_id", _cols("person_id:text name:text email:text role:text team:text segment:text region:text user_id:text start_date:date end_date:date")),
    )
}  # fmt: skip

SOURCES = ("source_record_ids", "extract_ids")

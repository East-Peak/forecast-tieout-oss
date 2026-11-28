"""The records shard's contract: a JSON Schema, and the rules a schema cannot say.

The rules recompute every cell the shard backs from the shard's own records: a set's count is its
cell's count, its recorded amounts sum to the cell's ARR, its days to the cell's cycle, and each
record sits where its own dates, status, segment and owner say it does. Nothing here calls the
code that built the shard, and each scenario's lanes file is held to it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from jsonschema import Draft202012Validator

from .contract import (
    DATE,
    INT,
    MONEY,
    TEXT,
    arr,
    const,
    enum,
    maybe,
    obj,
    record,
)
from .lanes_contract import DEFS, SCHEMA_VERSION
from .lanes_records import SETS, WON

IDS = arr(TEXT)
RECORD = obj(
    {
        "id": TEXT,
        "name": TEXT,
        "segment": TEXT,
        "owner": TEXT,
        "owner_name": TEXT,
        "created": DATE,
        "close": maybe(DATE),
        "stage": TEXT,
        "status": enum("open", "won", "lost"),
        "arr_first": maybe(MONEY),
        "arr": maybe(MONEY),
    }
)
SHARD = obj(
    {
        "schema_version": const(SCHEMA_VERSION),
        "company": TEXT,
        "as_of": DATE,
        "fiscal_year": TEXT,
        "horizon_days": INT,
        "periods": arr(
            obj({"key": TEXT, "start": DATE, "end": DATE}), minItems=5, maxItems=5
        ),
        "sets": record(arr(TEXT, minItems=1)),
        "caveat": TEXT,
        "records": record(RECORD),
        "rows": arr(
            obj(
                {
                    "path": arr(TEXT, minItems=1, maxItems=4),
                    "periods": record(
                        obj(
                            {
                                name: maybe(IDS) if name == "open" else IDS
                                for name in SETS
                            }
                        )
                    ),
                }
            ),
            minItems=1,
        ),
    }
)


def schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://forecast-tieout.example/schema/lanes-records-{SCHEMA_VERSION}.json",
        "title": "TieoutLanesRecords",
        "description": "lanes-records.json written by the core's generator: the deals behind the grid's cells.",
        **SHARD,
        "$defs": {k: DEFS[k] for k in ("Text", "Money", "Decimal", "Date")},
    }


def _d(x) -> Decimal | None:
    return None if x is None else Decimal(x)


def validate(shard: dict, doc: dict) -> list[str]:
    """Every problem with the shard, held against one scenario's lanes file ``doc``."""
    found = [
        f"{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}"
        for e in Draft202012Validator(schema()).iter_errors(shard)
    ]
    if found or "unavailable" in doc:
        return found
    problems: list[str] = []

    def rule(ok: bool, message: str) -> None:
        if not ok:
            problems.append(message)

    records = shard["records"]
    horizon = timedelta(days=shard["horizon_days"])
    as_of = date.fromisoformat(shard["as_of"])
    rows = {tuple(r["path"]): r["periods"] for r in shard["rows"]}
    on_doc = {tuple(r["path"]) for r in doc["periods"][0]["rows"]}
    rule(shard["company"] == doc["company"], "the shard is another company's")
    rule(
        set(rows) <= on_doc,
        f"the shard names rows the lanes do not have: {sorted(set(rows) - on_doc)}",
    )
    rule(
        [(p["key"], p["start"], p["end"]) for p in shard["periods"]]
        == [(p["key"], p["start"], p["end"]) for p in doc["periods"]],
        "the shard's periods are not the lanes' periods",
    )
    for p in doc["periods"]:
        first, last = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        end = min(last, as_of)
        begun = first - timedelta(days=1) <= as_of
        for r in p["rows"]:
            path = tuple(r["path"])
            sets = rows.get(path, {}).get(p["key"]) or {
                k: None if k == "open" and not begun else [] for k in SETS
            }
            where = f"{p['key']} {list(path)}"
            seen: dict[str, dict] = {}
            for name in SETS:
                ids = sets[name]
                if ids is None:
                    rule(
                        name == "open" and not begun,
                        f"{where}: {name} is missing for a period that has begun",
                    )
                    continue
                rule(len(ids) == len(set(ids)), f"{where}: {name} lists a deal twice")
                for i in ids:
                    rec = records.get(i)
                    rule(
                        rec is not None,
                        f"{where}: {name} names a record ({i}) the shard does not hold",
                    )
                    if rec is not None:
                        _placed(rule, where, name, rec, path, first, end, horizon)
                seen[name] = {i: records[i] for i in ids if i in records}
            rule(
                not set(seen.get("won_carried_in", ()))
                & set(seen.get("won_created_in_period", ())),
                f"{where}: a win is both carried in and created in the period",
            )
            rule(
                set(seen.get("cohort_won", ())) <= set(seen.get("cohort", ())),
                f"{where}: a cohort win is not in its cohort",
            )
            _cells(rule, where, r["cells"], seen)
    return problems


def _placed(rule, where, name, rec, path, first, end, horizon) -> None:
    """One record in one set: its own dates, status, segment and owner agree."""
    created = date.fromisoformat(rec["created"])
    close = None if rec["close"] is None else date.fromisoformat(rec["close"])
    rule(
        path == ("total",)
        or (rec["segment"] == path[1] and (len(path) == 2 or rec["owner"] == path[3])),
        f"{where}: {name} holds {rec['id']}, whose segment or owner (today's) is not this row's",
    )
    if name == "open":
        rule(
            created < first and (rec["status"] == "open" or close >= first),
            f"{where}: {rec['id']} was not open at the start",
        )
    elif name == "created":
        rule(
            first <= created <= end,
            f"{where}: {rec['id']} was not created in the period",
        )
    elif name in WON:
        rule(
            rec["status"] == "won" and first <= close <= end,
            f"{where}: {rec['id']} was not won in the period",
        )
        rule(
            (created < first) == (name == "won_carried_in"),
            f"{where}: {rec['id']} is in the wrong half of the carried-in split",
        )
    else:
        last = end - horizon
        rule(
            last - horizon < created <= last,
            f"{where}: {rec['id']} is not in the creation cohort",
        )
        if name == "cohort_won":
            rule(
                rec["status"] == "won" and (close - created) <= horizon,
                f"{where}: {rec['id']} did not win within the horizon",
            )


def _sum(recs: dict, key: str = "arr") -> Decimal:
    """The recorded amounts of ``recs`` added up; a deal with none recorded adds nothing."""
    return sum((_d(r[key]) or Decimal(0) for r in recs.values()), Decimal(0))


def _cells(rule, where, cells, seen) -> None:
    """Each cell's actual against the sums of the records its sets name."""
    won = {**seen.get("won_carried_in", {}), **seen.get("won_created_in_period", {})}
    days = sum(
        (date.fromisoformat(r["close"]) - date.fromisoformat(r["created"])).days
        for r in won.values()
    )
    want = {
        ("created", "actual"): len(seen.get("created", ())),
        ("created_arr", "actual"): _sum(seen.get("created", {}), "arr_first"),
        ("won", "actual"): len(won),
        ("bookings", "actual"): _sum(won),
    }
    if seen.get("open") is not None and "open" in seen:
        want[("open", "actual")] = len(seen["open"])
    for (col, mode), value in want.items():
        got = _d(cells[col][mode])
        rule(got == value, f"{where}: {col} {mode} is {got}, its records give {value}")
    for part, recs in zip(
        ("carried_in", "created_in_period"),
        (seen.get("won_carried_in", {}), seen.get("won_created_in_period", {})),
    ):
        for col, value in (("won", len(recs)), ("bookings", _sum(recs))):
            got = _d(cells[col]["split"]["actual"][part])
            rule(
                got == value,
                f"{where}: {col} {part} is {got}, its records give {value}",
            )
    if cells["open"]["actual"] is None:
        rule(
            seen.get("open") is None,
            f"{where}: open is listed for a period that has not begun",
        )
    for col, num, den in (
        ("win_rate", len(seen.get("cohort_won", ())), len(seen.get("cohort", ()))),
        ("avg_won_arr", _sum(won), len(won)),
        ("cycle", days, len(won)),
    ):
        parts = cells[col]["parts"]["actual"]
        rule(
            (_d(parts["numerator"]), _d(parts["denominator"])) == (num, den),
            f"{where}: {col} is {parts}, its records give {num} over {den}",
        )


def schema_text() -> str:
    return json.dumps(schema(), indent=2, sort_keys=True) + "\n"

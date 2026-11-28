"""The lanes of a scenario are several files: the company and its segments, and for each segment
the owners beneath it. Owner rows are most of the rows and most of the bytes, and a screen needs
them only when a segment is opened, so they are written and fetched apart, a file to a segment so
that none grows past what a page should fetch at once. The builder makes one document; this
module splits it for writing and merges the files back for the contract, which holds them
together (a segment's owners must add to it across the files).
"""

from __future__ import annotations

import re

from . import lanes_rules as rules

HEADER = ("schema_version", "company", "scenario", "as_of", "fiscal_year", "plan_basis")


def is_owner(row: dict) -> bool:
    return len(row["path"]) == 4


def slug(segment: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", segment.lower()).strip("-") or "segment"


def name(scenario: str, segment: str) -> str:
    return f"lanes-owners-{scenario}-{slug(segment)}.json"


def split(doc: dict) -> tuple[dict, dict[str, dict]]:
    """(the lanes file, the owners file of each segment) of a full document."""
    mine = [c for c in doc["checks"] if not c["name"].startswith("owner ")]
    lanes = {
        **doc,
        "reasons": {k: doc["reasons"][k] for k in rules.SEGMENT_REASONS},
        "caveats": [c for c in doc["caveats"] if c != rules.OWNER_CAVEAT],
        "checks": mine,
        "periods": [
            {**p, "rows": [r for r in p["rows"] if not is_owner(r)]}
            for p in doc["periods"]
        ],
    }
    segments = [r["path"][1] for r in doc["periods"][0]["rows"] if r["kind"] == "segment"]  # fmt: skip
    owners = {
        seg: {
            **{k: doc[k] for k in HEADER},
            "segment": seg,
            "lanes": f"lanes-{doc['scenario']}.json",
            "reasons": doc["reasons"],
            "caveats": [rules.OWNER_CAVEAT],
            "periods": [
                {
                    "key": p["key"],
                    "rows": [
                        r for r in p["rows"] if is_owner(r) and r["path"][1] == seg
                    ],
                }
                for p in doc["periods"]
            ],
            "checks": [c for c in doc["checks"] if c not in mine],
        }
        for seg in segments
    }
    return lanes, owners


def merge(lanes: dict, owners: list[dict]) -> dict:
    """The full document (or, given some segments' files, the lanes with those segments' owners
    directly beneath them)."""
    under: dict[tuple, list] = {}
    for o in owners:
        for p in o["periods"]:
            under.setdefault((p["key"], o["segment"]), []).extend(p["rows"])
    periods = []
    for p in lanes["periods"]:
        rows = []
        for r in p["rows"]:
            rows.append(r)
            if r["kind"] == "segment":
                rows += under.get((p["key"], r["path"][1]), [])
        periods.append({**p, "rows": rows})
    return {
        **lanes,
        "reasons": owners[0]["reasons"] if owners else lanes["reasons"],
        "caveats": [*lanes["caveats"], *(owners[0]["caveats"] if owners else [])],
        "checks": [*lanes["checks"], *(owners[0]["checks"] if owners else [])],
        "periods": periods,
    }

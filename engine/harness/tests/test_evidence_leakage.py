"""Tranche 1, part E: no future leakage.

For several (T, K) pairs, build a mutated copy of estate A in which everything recorded after K
is corrupted or removed, and show that every as-of answer at (T, K) is unchanged. The mutations
touch only what was recorded after K: history rows with CreatedDate > K and the snapshot values
of extracts taken after K (immutable fields, which the estate declares never change, are left
alone). The reverse check shows the test has teeth: corrupting something recorded before K
changes an answer.
"""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from engine.harness.contract.schemas import SCHEMAS
from engine.harness.evidence import AsOf, Coverage, load
from engine.harness.evidence.views import VIEW_NAMES
from engine.harness.tests.test_evidence_support import (
    ESTATE_YAML,
    copy_estate,
    read_rows,
    rewrite_manifest,
    write_rows,
)

COVERAGE = Coverage.from_yaml(ESTATE_YAML)
HISTORY = ("OpportunityHistory", "OpportunityFieldHistory", "LeadHistory")
PAIRS = [
    (date(2025, 3, 31), datetime(2025, 3, 31, 23, 59, 59)),
    (
        date(2025, 2, 28),
        datetime(2025, 5, 6, 15, 59, 59),
    ),  # just before O2's closing row
    (date(2025, 4, 30), datetime(2025, 4, 30, 23, 59, 59)),
    (date(2025, 4, 30), datetime(2025, 5, 20, 12, 0, 0)),
    (date(2025, 5, 31), datetime(2025, 5, 31, 23, 59, 59)),
    (date(2025, 5, 31), datetime(2025, 6, 10, 0, 0, 0)),
    (date(2025, 6, 30), datetime(2025, 6, 30, 23, 59, 59)),
]


def junk(field, value):
    """A schema-valid value that is wrong."""
    kind = field.type
    if value is None:
        return None
    if field.choices:
        return next(c for c in field.choices if c != value)
    if kind in ("int", "cents"):
        return value + 7
    if kind == "number":
        return value + 7.0
    if kind == "bool":
        return not value
    fixed = {
        "id": "JUNK-ID",
        "string": "scrambled",
        "dollars": 999999.99,
        "date": "2031-01-01",
        "datetime": "2031-01-01T00:00:00Z",
    }
    return fixed[kind]


def scramble_history(row: dict, name: str) -> dict:
    row = dict(row)
    if name == "OpportunityHistory":
        row.update(StageName="Closed Won", Amount=999999.99, CloseDate="2031-01-01")
    else:
        for side in ("OldValue", "NewValue"):
            row[side] = (
                "2031-01-01"
                if row["Field"].endswith("Date__c")
                else "Admitted"
                if row["Field"] == "Disposition__c"
                else "scrambled"
            )
    return row


def mutate(dest: Path, k: datetime, variant: str) -> list[Path]:
    """A copy of estate A with everything recorded after K destroyed (variant) or, for the reverse
    check, everything recorded at or before K corrupted."""
    folders = copy_estate(dest)
    k_text = k.strftime("%Y-%m-%dT%H:%M:%SZ")
    by_system: dict[str, list[Path]] = {}
    for folder in folders:
        by_system.setdefault(folder.name, []).append(folder)
    for ordered in by_system.values():
        previous_rows: dict[str, dict] = {}
        for folder in ordered:  # extract folders sort by date
            manifest = json.loads((folder / "manifest.json").read_text())
            after = manifest["extracted_at"] > k_text
            for name in manifest["objects"]:
                rows = read_rows(folder, name)
                schema = SCHEMAS[name]
                if name in HISTORY:
                    if variant == "scramble_history":
                        rows = [
                            scramble_history(r, name)
                            if r["CreatedDate"] > k_text
                            else r
                            for r in rows
                        ]
                    elif variant == "delete_history":
                        rows = [r for r in rows if r["CreatedDate"] <= k_text]
                    elif variant == "scramble_before":
                        rows = [
                            scramble_history(r, name)
                            if r["CreatedDate"] <= k_text
                            else r
                            for r in rows
                        ]
                elif (
                    (variant == "scramble_snapshots" and after)
                    or (variant == "scramble_snapshots_before" and not after)
                ) and name != "plan_lines":
                    keep = (
                        set(schema.key)
                        | set(COVERAGE.immutable.get(name, ()))
                        | {"CreatedDate", "createdate"}
                    )
                    rows = [
                        {f.name: (r[f.name] if f.name in keep else junk(f, r[f.name])) for f in schema.fields}
                        for r in rows
                    ]  # fmt: skip
                elif (
                    variant == "fake_membership"
                    and after
                    and name == "Opportunity"
                    and previous_rows
                ):
                    merged = {
                        **previous_rows,
                        **{r["Id"]: r for r in rows},
                    }  # undelete what vanished
                    del merged[min(merged)]  # and delete a record that is there
                    rows = list(merged.values())
                if name == "Opportunity":
                    previous_rows = {r["Id"]: r for r in rows}
                write_rows(folder, name, rows)
            rewrite_manifest(folder)
    return folders


def plain(value):
    if isinstance(value, list):
        return tuple(sorted(map(plain, value)))
    return value


def probes(store) -> dict:
    """What to ask: every record and field of the original estate, the same for both worlds."""
    con = store.con
    return {
        "opps": [r[0] for r in con.execute("SELECT DISTINCT id FROM record WHERE entity = 'Opportunity' ORDER BY 1").fetchall()],
        "leads": [r[0] for r in con.execute("SELECT DISTINCT id FROM record WHERE entity = 'Lead' ORDER BY 1").fetchall()],
        "fields": con.execute("SELECT DISTINCT entity, id, field FROM assertion ORDER BY 1, 2, 3").fetchall(),
    }  # fmt: skip


def fingerprint(store, t: date, k: datetime, ask: dict) -> dict:
    """Every as-of answer at (T, K): all views, and the point queries of the API."""
    asof = AsOf(store, t, k)
    out = {}
    for name in VIEW_NAMES:
        relation = asof.relation(name)
        out[name] = sorted(
            repr(tuple(plain(v) for v in row)) for row in relation.fetchall()
        )
    for opp in ask["opps"]:
        out[opp] = (
            asof.stage_at(opp), asof.open_at(opp), asof.owner_at(opp), asof.closing(opp), asof.status_at("Opportunity", opp),
        )  # fmt: skip
    for lead in ask["leads"]:
        out[lead] = asof.episodes(lead)
    out["fields"] = {tr: asof.field_at(*tr) for tr in ask["fields"]}
    from engine.harness.evidence import bookings_by_month, mql_count

    months = [f"2025-{m:02d}" for m in range(1, 9)]
    out["measures"] = [
        (bookings_by_month(asof, m).total_cents, mql_count(asof, m)) for m in months
    ]
    out["availability"] = [
        asof.availability(s, o) for s, o in (("people_system", "requisitions"), ("hubspot", "contacts"), ("salesforce", "OpportunityFieldHistory"))
    ]  # fmt: skip
    return out


@pytest.fixture(scope="module")
def original():
    from engine.harness.tests.test_evidence_support import estate_dirs

    return load(estate_dirs(), COVERAGE)


@pytest.mark.parametrize("t, k", PAIRS, ids=lambda v: v.isoformat())
@pytest.mark.parametrize(
    "variant",
    ["scramble_history", "delete_history", "scramble_snapshots", "fake_membership"],
)
def test_nothing_recorded_after_k_changes_an_answer_at_k(
    original, tmp_path, t, k, variant
):
    mutated = load(mutate(tmp_path / "m", k, variant), COVERAGE)
    ask = probes(original)
    assert fingerprint(mutated, t, k, ask) == fingerprint(original, t, k, ask)


@pytest.mark.parametrize("variant", ["scramble_before", "scramble_snapshots_before"])
@pytest.mark.parametrize("t, k", PAIRS[3:5], ids=lambda v: v.isoformat())
def test_corrupting_what_was_recorded_before_k_does_change_answers(
    original, tmp_path, t, k, variant
):
    mutated = load(mutate(tmp_path / "m", k, variant), COVERAGE)
    ask = probes(original)
    assert fingerprint(mutated, t, k, ask) != fingerprint(original, t, k, ask)


def test_the_reverse_check_changes_at_least_the_measures(original, tmp_path):
    t, k = PAIRS[4]
    mutated = load(mutate(tmp_path / "m", k, "scramble_before"), COVERAGE)
    ask = probes(original)
    assert (
        fingerprint(mutated, t, k, ask)["measures"]
        != fingerprint(original, t, k, ask)["measures"]
    )

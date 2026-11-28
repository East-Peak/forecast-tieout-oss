"""Tranche 1, part E: no future leakage.

For several (T, K) pairs, build a mutated copy of estate A in which everything recorded after K
is corrupted or removed, and show that every as-of answer at (T, K) is unchanged. The mutations
touch only what was recorded after K: history rows with CreatedDate > K and the snapshot values
of extracts taken after K (immutable fields, which the estate declares never change, are left
alone). The reverse check shows the test has teeth: corrupting something recorded before K
changes an answer.
"""

import json
import shutil
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


def copy_folders(source: list[Path], dest: Path) -> list[Path]:
    out = []
    for folder in source:
        target = dest / folder.parent.name / folder.name
        shutil.copytree(folder, target)
        out.append(target)
    return sorted(out)


def mutate(
    dest: Path, k: datetime, variant: str, source: list[Path] | None = None
) -> list[Path]:
    """A copy of an estate (default: estate A) with everything recorded after K destroyed (variant)
    or, for the reverse check, everything recorded at or before K corrupted. Variant `vanish` also
    removes every snapshot row of a record first shown by an extract after K."""
    folders = copy_estate(dest) if source is None else copy_folders(source, dest)
    k_text = k.strftime("%Y-%m-%dT%H:%M:%SZ")
    by_system: dict[str, list[Path]] = {}
    for folder in folders:
        by_system.setdefault(folder.name, []).append(folder)
    for ordered in by_system.values():
        previous_rows: dict[str, dict] = {}
        seen: dict[str, set] = {}
        for folder in ordered:  # extract folders sort by date
            manifest = json.loads((folder / "manifest.json").read_text())
            after = manifest["extracted_at"] > k_text
            for name in manifest["objects"]:
                rows = read_rows(folder, name)
                schema = SCHEMAS[name]
                keys = {tuple(r[c] for c in schema.key) for r in rows}
                if variant == "vanish" and name not in HISTORY and name != "plan_lines":
                    if after:
                        rows = [
                            r
                            for r in rows
                            if tuple(r[c] for c in schema.key) in seen.get(name, set())
                        ]
                    else:
                        seen.setdefault(name, set()).update(keys)
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


MASKED_VIEWS = (
    "opportunity_state",
    "opportunity_spell",
    "opportunity_open",
    "opportunity_flow",
    "demand_episode",
    "extract",
)


_CACHE: dict = {}


def reference_fingerprint(store, t, k, ask, masked=False):
    """The original estate's fingerprint, computed once per (T, K)."""
    key = (id(store), t, k, masked)
    if key not in _CACHE:
        _CACHE[key] = fingerprint(store, t, k, ask, masked)
    return _CACHE[key]


def fingerprint(store, t: date, k: datetime, ask: dict, masked: bool = False) -> dict:
    """Every as-of answer at (T, K): all views, and the point queries of the API.

    `masked` drops what depends on declared-immutable attributes (the estate says they never change,
    so a later snapshot may supply them for an earlier K): the entity views, those fields, bookings.
    """
    asof = AsOf(store, t, k)
    out = {}
    for name in MASKED_VIEWS if masked else VIEW_NAMES:
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
    out["fields"] = {
        tr: asof.field_at(*tr)
        for tr in ask["fields"]
        if not (masked and tr[2] in COVERAGE.immutable.get(tr[0], ()))
    }
    from engine.harness.evidence import bookings_by_month, mql_count

    months = [f"2025-{m:02d}" for m in range(1, 9)]
    out["measures"] = [
        (None if masked else bookings_by_month(asof, m).total_cents, mql_count(asof, m))
        for m in months
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
    [
        "scramble_history",
        "delete_history",
        "scramble_snapshots",
        "fake_membership",
        "vanish",
    ],
)
def test_nothing_recorded_after_k_changes_an_answer_at_k(
    original, tmp_path, t, k, variant
):
    mutated = load(mutate(tmp_path / "m", k, variant), COVERAGE)
    ask = probes(original)
    masked = variant == "vanish"
    assert fingerprint(mutated, t, k, ask, masked) == reference_fingerprint(
        original, t, k, ask, masked
    )


def small_estates(tmp_path):
    """The counterexample estates of the review (items 1, 2 and 3), each with its (T, K) pairs."""
    from engine.harness.tests.test_evidence_review import (
        clocks_estate,
        history_only_estate,
        two_snapshots,
    )

    def pair(t, k):
        return date.fromisoformat(t), datetime.fromisoformat(k)

    return {
        "history_only": (
            history_only_estate(tmp_path / "ho", snapshot_in_second=True),
            [pair("2025-05-01", "2025-05-01T23:59:59"), pair("2025-04-15", "2025-04-15T00:00:00"), pair("2025-06-02", "2025-06-02T00:00:00")],
        ),
        "two_snapshots": (two_snapshots(tmp_path / "ts"), [pair("2025-03-31", "2025-03-31T23:59:59"), pair("2025-06-02", "2025-06-02T00:00:00")]),
        "clocks": (clocks_estate(tmp_path / "ck"), [pair("2025-04-01", "2025-04-01T00:00:00"), pair("2025-05-20", "2025-05-20T00:00:00"), pair("2025-06-01", "2025-06-01T23:59:59")]),
    }  # fmt: skip


@pytest.mark.parametrize("name", ["history_only", "two_snapshots", "clocks"])
@pytest.mark.parametrize(
    "variant",
    [
        "scramble_history",
        "delete_history",
        "scramble_snapshots",
        "fake_membership",
        "vanish",
    ],
)
def test_the_review_estates_leak_nothing_either(tmp_path, name, variant):
    source, pairs = small_estates(tmp_path / "src")[name]
    reference = load(source, COVERAGE)
    ask = probes(reference)
    masked = variant == "vanish"
    for index, (t, k) in enumerate(pairs):
        mutated = load(mutate(tmp_path / f"m{index}", k, variant, source), COVERAGE)
        assert fingerprint(mutated, t, k, ask, masked) == reference_fingerprint(
            reference, t, k, ask, masked
        ), (name, variant, t, k)


def test_a_record_first_shown_after_k_vanishes_from_the_mutated_estate(tmp_path):
    from engine.harness.tests.test_evidence_review import history_only_estate

    source = history_only_estate(tmp_path / "src", snapshot_in_second=True)
    k = datetime(2025, 5, 1, 23, 59, 59)
    mutated = load(mutate(tmp_path / "m", k, "vanish", source), COVERAGE)
    assert mutated.con.execute(
        "SELECT count(*) FROM raw_Opportunity WHERE Id = '006X2'"
    ).fetchall() == [(0,)]
    (partial,) = mutated.con.execute(
        "SELECT partial FROM record WHERE id = '006X2'"
    ).fetchone()
    assert partial is True  # known only through its history rows


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

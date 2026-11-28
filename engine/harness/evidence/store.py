"""The store: a DuckDB database of registered extracts, raw rows, records and assertions."""

import json
import os
import subprocess
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import duckdb

from ..contract.keys import ASSERTION_FIELDS, Assertion
from ..contract.manifest import content_hash, validate_extract
from ..contract.schemas import SCHEMAS
from . import derive
from .coverage import Coverage
from .derive import ExtractError
from .sql import ISO, RAW_TYPES, ident, lit, raw_table

_FIXED_DDL = """
CREATE TABLE IF NOT EXISTS extract (
    extract_id VARCHAR PRIMARY KEY, source_system VARCHAR, extracted_at TIMESTAMP, content_hash VARCHAR);
CREATE TABLE IF NOT EXISTS extract_object (
    extract_id VARCHAR, object VARCHAR, row_count BIGINT, PRIMARY KEY (extract_id, object));
CREATE TABLE IF NOT EXISTS coverage (kind VARCHAR, entity VARCHAR, field VARCHAR, via VARCHAR);
CREATE TABLE IF NOT EXISTS record (
    entity VARCHAR, id VARCHAR, system VARCHAR, created_at TIMESTAMP, first_extract_id VARCHAR,
    first_extract_at TIMESTAMP, known_since TIMESTAMP, first_ord BIGINT, last_ord BIGINT, n_shown BIGINT);
CREATE TABLE IF NOT EXISTS assertion (
    entity VARCHAR, id VARCHAR, field VARCHAR, value VARCHAR, effective_at TIMESTAMP,
    recorded_at TIMESTAMP, source VARCHAR, extract_id VARCHAR,
    assumed_since_creation BOOLEAN, deletion_time_upper_bound BOOLEAN);
CREATE OR REPLACE VIEW listing AS
SELECT o.extract_id, e.source_system AS system, o.object, e.extracted_at, o.row_count,
       row_number() OVER (PARTITION BY e.source_system, o.object ORDER BY e.extracted_at, e.extract_id) AS ord
FROM extract_object o JOIN extract e USING (extract_id);
"""


def _raw_ddl(obj: str) -> str:
    cols = ", ".join(
        f"{ident(f.name)} {RAW_TYPES[f.type]}" for f in SCHEMAS[obj].fields
    )
    return f"CREATE TABLE IF NOT EXISTS {raw_table(obj)} (extract_id VARCHAR, {cols})"


def _read_json_columns(obj: str) -> str:
    return ", ".join(f"'{f.name}': '{RAW_TYPES[f.type]}'" for f in SCHEMAS[obj].fields)


class Store:
    """A DuckDB evidence store, in memory or at `path`."""

    def __init__(self, path: str | Path | None = None):
        self.con = duckdb.connect(str(path) if path else ":memory:")
        self.con.execute(_FIXED_DDL)
        for obj in SCHEMAS:
            self.con.execute(_raw_ddl(obj))
        from .views import install_views

        install_views(self.con)

    # -- coverage ---------------------------------------------------------
    @property
    def coverage(self) -> Coverage:
        rows = self.con.execute(
            "SELECT kind, entity, field, via FROM coverage ORDER BY 1, 2, 3"
        ).fetchall()
        if not rows:
            return Coverage.standard()
        history = tuple((e, f, v) for k, e, f, v in rows if k == "history")
        immutable: dict[str, tuple[str, ...]] = {}
        for k, e, f, _ in rows:
            if k == "immutable":
                immutable[e] = (*immutable.get(e, ()), f)
        return Coverage(history, immutable)

    def _set_coverage(self, coverage: Coverage) -> None:
        self.con.execute("DELETE FROM coverage")
        rows = [("history", e, f, v) for e, f, v in coverage.history]
        rows += [
            ("immutable", e, f, None)
            for e, fs in coverage.immutable.items()
            for f in fs
        ]
        if rows:
            self.con.executemany("INSERT INTO coverage VALUES (?, ?, ?, ?)", rows)

    # -- reading ----------------------------------------------------------
    def flagged_assertions(self) -> list[tuple[Assertion, tuple[str, ...]]]:
        """Every assertion in a fixed order, with the flags the engine attaches."""
        iso = f"'{ISO}'"
        rows = self.con.execute(
            f"""SELECT entity, id, field, value, strftime(effective_at, {iso}), strftime(recorded_at, {iso}),
                       source, extract_id, assumed_since_creation, deletion_time_upper_bound
            FROM assertion ORDER BY entity, id, field, effective_at, recorded_at, source, value NULLS FIRST"""
        ).fetchall()
        return [
            (
                Assertion(*r[:8]),
                tuple(
                    n
                    for n, on in zip(
                        ("assumed_since_creation", "deletion_time_upper_bound"),
                        r[8:],
                        strict=True,
                    )
                    if on
                ),
            )
            for r in rows
        ]

    def assertions(self) -> list[Assertion]:
        return [a for a, _ in self.flagged_assertions()]

    @property
    def latest_extract_at(self) -> datetime | None:
        return self.con.execute("SELECT max(extracted_at) FROM extract").fetchone()[0]


def _loaded(store: Store, manifest: dict) -> bool:
    """True when this very content is already registered (a repeat load validates nothing)."""
    try:
        digest = content_hash(manifest)
        extract_id = manifest["extract_id"]
    except (KeyError, TypeError, AttributeError):
        return False
    return (
        store.con.execute(
            "SELECT 1 FROM extract WHERE extract_id = ? AND content_hash = ?",
            [extract_id, digest],
        ).fetchone()
        is not None
    )


def _register(store: Store, folder: Path, manifest: dict) -> bool:
    """Add one extract's raw rows. Returns False when the same content is already loaded."""
    digest = content_hash(manifest)
    known = store.con.execute(
        "SELECT content_hash FROM extract WHERE extract_id = ?",
        [manifest["extract_id"]],
    ).fetchone()
    if known:
        if known[0] != digest:
            raise ExtractError(
                f"{manifest['extract_id']} is already loaded with different content"
            )
        return False
    store.con.execute(
        "INSERT INTO extract VALUES (?, ?, ?, ?)",
        [
            manifest["extract_id"],
            manifest["source_system"],
            manifest["extracted_at"].replace("Z", ""),
            digest,
        ],
    )
    for obj, entry in manifest["objects"].items():
        store.con.execute(
            "INSERT INTO extract_object VALUES (?, ?, ?)",
            [manifest["extract_id"], obj, entry["count"]],
        )
        if entry["count"]:
            store.con.execute(
                f"""INSERT INTO {raw_table(obj)} SELECT ?, * FROM read_json(?, format = 'newline_delimited',
                    columns = {{{_read_json_columns(obj)}}})""",
                [manifest["extract_id"], str(folder / f"{obj}.jsonl")],
            )
    return True


PARALLEL_FROM = (
    4  # folders; below this, starting interpreters costs more than validating
)
_VALIDATE = "import json,sys;from pathlib import Path;from engine.harness.contract.manifest import validate_extract;print(json.dumps(validate_extract(Path(sys.argv[1]))))"
_ROOT = Path(__file__).resolve().parents[3]


def _validate_all(folders: list[Path]) -> list[list[str]]:
    """The contract's validate_extract for each folder, in worker interpreters when there are many.

    Validation is pure Python, so threads would not help; fresh interpreters (not forked or spawned
    workers) keep this safe to call from any script or notebook.
    """
    if len(folders) < PARALLEL_FROM:
        return [validate_extract(f) for f in folders]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(_ROOT), os.environ.get("PYTHONPATH", "")]),
    }

    def run(folder: Path) -> list[str]:
        done = subprocess.run(
            [sys.executable, "-c", _VALIDATE, str(folder)],
            capture_output=True,
            check=False,
            env=env,
            text=True,
        )
        if done.returncode:
            raise ExtractError(
                f"validation worker failed for {folder}: {done.stderr[-300:]}"
            )
        return json.loads(done.stdout)

    with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 8)) as pool:
        return list(pool.map(run, folders))


def load(
    extract_dirs: Iterable[Path | str],
    coverage: Coverage | None = None,
    store: Store | None = None,
) -> Store:
    """Validate and register extract folders (one per source system), then derive assertions.

    Loading is idempotent by content hash and independent of order: the assertions are
    recomputed from every registered extract. Nothing is loaded if any folder is invalid.
    """
    store = store or Store()
    folders = [Path(d) for d in extract_dirs]
    manifests = [
        json.loads((f / "manifest.json").read_text())
        if (f / "manifest.json").exists()
        else None
        for f in folders
    ]
    fresh = [
        f
        for f, m in zip(folders, manifests, strict=True)
        if m is None or not _loaded(store, m)
    ]
    for folder, problems in zip(fresh, _validate_all(fresh), strict=True):
        if problems:
            raise ExtractError(f"{folder}: " + "; ".join(problems[:5]))
    con = store.con
    con.execute("BEGIN")
    try:
        changed = [
            _register(store, f, m) for f, m in zip(folders, manifests, strict=True)
        ]
        wanted = coverage or store.coverage
        if coverage is not None and coverage != store.coverage:
            store._set_coverage(coverage)
            changed.append(True)
        if any(changed):
            derive.rebuild(con, wanted)
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return store


__all__ = ["ASSERTION_FIELDS", "ExtractError", "Store", "lit", "load"]

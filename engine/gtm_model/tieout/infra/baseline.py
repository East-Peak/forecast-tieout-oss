"""Persisted baseline snapshot for Planning Tie-Out.

Saves and loads a precomputed TieoutResult so the app can skip
compute_full() on normal page loads.  Includes version metadata
so stale artifacts are rejected when the model changes.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import pickle
import re
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from gtm_model.tieout.runtime.env import (
    get_active_snowflake_session,
    get_baseline_table,
    get_default_baseline_dir,
)
from gtm_model.tieout.types import TieoutResult

logger = logging.getLogger(__name__)

DEFAULT_BASELINE_DIR = get_default_baseline_dir()
DEFAULT_BASELINE_TABLE = get_baseline_table()


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _parse_computed_at(value: str) -> datetime:
    """Parse persisted timestamps, tolerating legacy naive values as UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _schema_hash() -> str:
    """Compute a stable hash of the TieoutResult field structure.

    Changes whenever fields are added, removed, or reordered.
    """
    field_sig = "|".join(f"{f.name}:{f.type}" for f in fields(TieoutResult))
    return hashlib.sha256(field_sig.encode()).hexdigest()[:12]


def _build_envelope(
    result: TieoutResult,
    plan_case_id: str,
    overflow_mode: str,
    cache_version: str,
) -> dict:
    """Build the persisted metadata envelope for a baseline result."""
    now = _utc_now()
    return {
        "cache_version": cache_version,
        "schema_hash": _schema_hash(),
        "plan_case_id": plan_case_id,
        "overflow_mode": overflow_mode,
        "as_of": now.date().isoformat(),
        "computed_at": now.isoformat(timespec="seconds"),
        "result": result,
    }


def _baseline_path(
    plan_case_id: str,
    overflow_mode: str = "push",
    baseline_dir: Optional[Path] = None,
) -> Path:
    """Return the canonical file path for a baseline artifact."""
    d = baseline_dir or DEFAULT_BASELINE_DIR
    return d / f"baseline_{plan_case_id}_{overflow_mode}.pkl"


def _serialize_result_payload(result: TieoutResult) -> str:
    """Encode a TieoutResult into a portable base64 payload."""
    raw = pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
    return base64.b64encode(raw).decode("ascii")


def _deserialize_result_payload(payload_b64: str) -> TieoutResult:
    """Decode a base64 payload into a TieoutResult."""
    raw = base64.b64decode(payload_b64.encode("ascii"))
    return pickle.loads(raw)


def _table_store_enabled(session: Any | None, baseline_dir: Optional[Path]) -> bool:
    """Return True when hosted baseline persistence should use Snowflake."""
    return baseline_dir is None and session is not None


def _validate_table_name(table_name: str) -> str:
    """Allow only simple Snowflake identifiers in db.schema.table form."""
    if not re.fullmatch(r"[A-Za-z0-9_$]+(?:\.[A-Za-z0-9_$]+){0,2}", table_name):
        raise ValueError(f"Invalid Snowflake table name: {table_name}")
    return table_name


def _ensure_baseline_table(session: Any, table_name: str) -> None:
    """Create the hosted baseline table if it does not already exist."""
    safe_table = _validate_table_name(table_name)
    session.sql(
        f"""
        CREATE TABLE IF NOT EXISTS {safe_table} (
            PLAN_CASE_ID STRING,
            OVERFLOW_MODE STRING,
            CACHE_VERSION STRING,
            SCHEMA_HASH STRING,
            AS_OF STRING,
            COMPUTED_AT STRING,
            PAYLOAD_B64 STRING
        )
        """
    ).collect()


def _save_local_envelope(
    envelope: dict,
    plan_case_id: str,
    overflow_mode: str,
    baseline_dir: Optional[Path],
) -> Path:
    """Persist an envelope to a local pickle file."""
    path = _baseline_path(plan_case_id, overflow_mode, baseline_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(envelope, f, protocol=pickle.HIGHEST_PROTOCOL)
    logger.info("Saved baseline to %s (schema=%s)", path, envelope["schema_hash"])
    return path


def _load_local_envelope(
    plan_case_id: str,
    overflow_mode: str,
    baseline_dir: Optional[Path],
) -> Optional[dict]:
    """Load a baseline envelope from local pickle storage."""
    path = _baseline_path(plan_case_id, overflow_mode, baseline_dir)
    if not path.exists():
        logger.debug("No baseline at %s", path)
        return None

    try:
        with open(path, "rb") as f:
            envelope = pickle.load(f)
    except Exception as exc:
        logger.warning("Could not read baseline %s: %s", path, exc)
        return None

    if not isinstance(envelope, dict):
        logger.warning("Baseline %s has unexpected format", path)
        return None
    return envelope


def _save_table_envelope(
    session: Any,
    envelope: dict,
    plan_case_id: str,
    overflow_mode: str,
    baseline_table: str,
) -> str:
    """Persist an envelope to the hosted Snowflake baseline table."""
    table_name = _validate_table_name(baseline_table)
    _ensure_baseline_table(session, table_name)
    session.sql(
        f"DELETE FROM {table_name} WHERE PLAN_CASE_ID = ? AND OVERFLOW_MODE = ?",
        params=[plan_case_id, overflow_mode],
    ).collect()
    session.sql(
        f"""
        INSERT INTO {table_name}
            (PLAN_CASE_ID, OVERFLOW_MODE, CACHE_VERSION, SCHEMA_HASH, AS_OF, COMPUTED_AT, PAYLOAD_B64)
        SELECT ?, ?, ?, ?, ?, ?, ?
        """,
        params=[
            envelope["plan_case_id"],
            envelope["overflow_mode"],
            envelope["cache_version"],
            envelope["schema_hash"],
            envelope["as_of"],
            envelope["computed_at"],
            _serialize_result_payload(envelope["result"]),
        ],
    ).collect()
    location = f"snowflake://{table_name}/{plan_case_id}/{overflow_mode}"
    logger.info("Saved baseline to %s (schema=%s)", location, envelope["schema_hash"])
    return location


def _row_to_dict(row: Any) -> dict:
    """Normalize a Snowpark Row into a plain dictionary."""
    if hasattr(row, "as_dict"):
        return row.as_dict(recursive=True)
    return dict(row)


def _load_table_envelope(
    session: Any,
    plan_case_id: str,
    overflow_mode: str,
    baseline_table: str,
) -> Optional[dict]:
    """Load a baseline envelope from the hosted Snowflake table."""
    table_name = _validate_table_name(baseline_table)
    try:
        rows = session.sql(
            f"""
            SELECT PLAN_CASE_ID, OVERFLOW_MODE, CACHE_VERSION, SCHEMA_HASH, AS_OF, COMPUTED_AT, PAYLOAD_B64
            FROM {table_name}
            WHERE PLAN_CASE_ID = ? AND OVERFLOW_MODE = ?
            ORDER BY COMPUTED_AT DESC
            LIMIT 1
            """,
            params=[plan_case_id, overflow_mode],
        ).collect()
    except Exception as exc:
        logger.info("Could not load hosted baseline from %s: %s", table_name, exc)
        return None

    if not rows:
        return None

    row = _row_to_dict(rows[0])
    try:
        result = _deserialize_result_payload(str(row.get("PAYLOAD_B64") or ""))
    except Exception as exc:
        logger.warning("Could not decode hosted baseline from %s: %s", table_name, exc)
        return None

    return {
        "plan_case_id": row.get("PLAN_CASE_ID"),
        "overflow_mode": row.get("OVERFLOW_MODE"),
        "cache_version": row.get("CACHE_VERSION"),
        "schema_hash": row.get("SCHEMA_HASH"),
        "as_of": row.get("AS_OF"),
        "computed_at": row.get("COMPUTED_AT"),
        "result": result,
    }


def _load_table_metadata(
    session: Any,
    plan_case_id: str,
    overflow_mode: str,
    baseline_table: str,
) -> Optional[dict]:
    """Load hosted baseline metadata without deserializing the full payload."""
    table_name = _validate_table_name(baseline_table)
    try:
        rows = session.sql(
            f"""
            SELECT PLAN_CASE_ID, OVERFLOW_MODE, CACHE_VERSION, SCHEMA_HASH, AS_OF, COMPUTED_AT
            FROM {table_name}
            WHERE PLAN_CASE_ID = ? AND OVERFLOW_MODE = ?
            ORDER BY COMPUTED_AT DESC
            LIMIT 1
            """,
            params=[plan_case_id, overflow_mode],
        ).collect()
    except Exception:
        return None

    if not rows:
        return None

    row = _row_to_dict(rows[0])
    return {
        "plan_case_id": row.get("PLAN_CASE_ID"),
        "overflow_mode": row.get("OVERFLOW_MODE"),
        "cache_version": row.get("CACHE_VERSION"),
        "schema_hash": row.get("SCHEMA_HASH"),
        "as_of": row.get("AS_OF"),
        "computed_at": row.get("COMPUTED_AT"),
    }


def save_baseline(
    result: TieoutResult,
    plan_case_id: str,
    overflow_mode: str = "push",
    cache_version: str = "",
    baseline_dir: Optional[Path] = None,
    baseline_table: Optional[str] = None,
    session: Any | None = None,
) -> Path | str:
    """Serialize a TieoutResult with metadata.

    Returns the path the artifact was written to.
    """
    active_session = session or get_active_snowflake_session()
    envelope = _build_envelope(result, plan_case_id, overflow_mode, cache_version)

    if _table_store_enabled(active_session, baseline_dir):
        try:
            return _save_table_envelope(
                active_session,
                envelope,
                plan_case_id=plan_case_id,
                overflow_mode=overflow_mode,
                baseline_table=baseline_table or DEFAULT_BASELINE_TABLE,
            )
        except Exception as exc:
            logger.warning("Hosted baseline save failed; falling back to local file: %s", exc)

    return _save_local_envelope(
        envelope,
        plan_case_id=plan_case_id,
        overflow_mode=overflow_mode,
        baseline_dir=baseline_dir,
    )


def load_baseline(
    plan_case_id: str,
    overflow_mode: str = "push",
    cache_version: str = "",
    max_age_hours: float = 4.0,
    baseline_dir: Optional[Path] = None,
    baseline_table: Optional[str] = None,
    session: Any | None = None,
) -> Optional[TieoutResult]:
    """Load a persisted baseline if it exists, is compatible, and is fresh.

    Returns None when:
    - File does not exist
    - Schema hash mismatch (TieoutResult structure changed)
    - Cache version mismatch (model logic changed)
    - Baseline is older than max_age_hours
    - Deserialization error
    """
    active_session = session or get_active_snowflake_session()
    location = None
    envelope = None
    if _table_store_enabled(active_session, baseline_dir):
        location = baseline_table or DEFAULT_BASELINE_TABLE
        try:
            envelope = _load_table_envelope(
                active_session,
                plan_case_id=plan_case_id,
                overflow_mode=overflow_mode,
                baseline_table=location,
            )
        except Exception as exc:
            logger.warning("Hosted baseline load failed; falling back to local file: %s", exc)
            envelope = None
    if envelope is None:
        location = _baseline_path(plan_case_id, overflow_mode, baseline_dir)
        envelope = _load_local_envelope(
            plan_case_id=plan_case_id,
            overflow_mode=overflow_mode,
            baseline_dir=baseline_dir,
        )
    if envelope is None:
        return None

    # Version checks
    expected_schema = _schema_hash()
    if envelope.get("schema_hash") != expected_schema:
        logger.info(
            "Baseline schema mismatch at %s (got %s, expected %s)",
            location,
            envelope.get("schema_hash"),
            expected_schema,
        )
        return None

    if cache_version and envelope.get("cache_version") != cache_version:
        logger.info(
            "Baseline cache version mismatch at %s (got %s, expected %s)",
            location,
            envelope.get("cache_version"),
            cache_version,
        )
        return None

    # Freshness check
    if max_age_hours > 0:
        computed_at_str = envelope.get("computed_at", "")
        if computed_at_str:
            try:
                computed_at = _parse_computed_at(computed_at_str)
                age_hours = (_utc_now() - computed_at).total_seconds() / 3600
                if age_hours > max_age_hours:
                    logger.info(
                        "Baseline too old at %s (%.1fh > %.1fh max)",
                        location, age_hours, max_age_hours,
                    )
                    return None
            except (ValueError, TypeError):
                logger.warning("Could not parse computed_at in %s", location)
                return None
        else:
            logger.info("Baseline %s has no computed_at timestamp, rejecting", location)
            return None

    result = envelope.get("result")
    if not isinstance(result, TieoutResult):
        logger.warning("Baseline %s does not contain a TieoutResult", location)
        return None

    logger.info(
        "Loaded baseline from %s (as_of=%s, computed_at=%s)",
        location,
        envelope.get("as_of"),
        envelope.get("computed_at"),
    )
    return result


def baseline_metadata(
    plan_case_id: str,
    overflow_mode: str = "push",
    baseline_dir: Optional[Path] = None,
    baseline_table: Optional[str] = None,
    session: Any | None = None,
) -> Optional[dict]:
    """Peek at baseline metadata without loading the full result.

    Returns dict with cache_version, schema_hash, plan_case_id,
    overflow_mode, as_of, computed_at — or None if unavailable.
    """
    active_session = session or get_active_snowflake_session()
    if _table_store_enabled(active_session, baseline_dir):
        try:
            metadata = _load_table_metadata(
                active_session,
                plan_case_id=plan_case_id,
                overflow_mode=overflow_mode,
                baseline_table=baseline_table or DEFAULT_BASELINE_TABLE,
            )
        except Exception as exc:
            logger.warning("Hosted baseline metadata load failed; falling back to local file: %s", exc)
            metadata = None
        if metadata is not None:
            return metadata

    envelope = _load_local_envelope(
        plan_case_id=plan_case_id,
        overflow_mode=overflow_mode,
        baseline_dir=baseline_dir,
    )
    if envelope is None:
        return None

    return {
        k: envelope.get(k)
        for k in ("cache_version", "schema_hash", "plan_case_id",
                   "overflow_mode", "as_of", "computed_at")
    }

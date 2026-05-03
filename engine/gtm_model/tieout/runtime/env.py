"""Runtime environment helpers for Planning Tie-Out.

This module centralizes the small set of environment-sensitive decisions
the app needs while we support both:

1. local development on a workstation with filesystem-backed config/baselines
2. hosted mode with an active warehouse session (optional)

The goal is to keep the rest of the model code ignorant of whether queries,
config reads, and persisted artifacts come from local disk or a warehouse.

Runtime modes
-------------
- **Local**: No warehouse session. Config from local filesystem. Baselines as
  pickle files.
- **Hosted**: Active warehouse session. Queries via ``session.sql()``. Config from
  warehouse stage. Baselines in warehouse table. Subprocess calls are forbidden.

Environment variables
---------------------
GTM_TIEOUT_CONFIG_DIR
    Override local config directory (default: ``<repo>/config/``).
GTM_TIEOUT_PROFILE_ID / GTM_TIEOUT_PROFILE
    Select the active org profile manifest under ``config/profiles/<id>/profile.yaml``.
    Defaults to ``default``. When unset, the engine still works via the
    synthesized legacy-default profile contract.
GTM_TIEOUT_BASELINE_DIR
    Override local baseline directory (default: ``<repo>/data/baseline/``).
GTM_TIEOUT_BASELINE_TABLE
    Override warehouse table for hosted baselines.
GTM_TIEOUT_CONFIG_STAGE
    warehouse stage path for hosted config files. Only used when no local config
    file is found.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

import yaml

from gtm_model.tieout.runtime.profile import (
    load_org_profile,
    resolve_profile_resource_location,
    resolve_profile_resource_path,
)

logger = logging.getLogger(__name__)

# env.py lives at gtm_model/tieout/runtime/env.py — repo root is 4 levels up
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_CONFIG_DIR = _REPO_ROOT / "config"
_DEFAULT_BASELINE_DIR = _REPO_ROOT / "data" / "baseline"
_DEFAULT_BASELINE_TABLE = "FORECAST_TIEOUT.APP_STATE.BASELINE_SNAPSHOTS"


def get_default_config_dir() -> Path:
    """Return the default local config directory."""
    override = os.getenv("GTM_TIEOUT_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_CONFIG_DIR


def get_default_baseline_dir() -> Path:
    """Return the default local baseline directory."""
    override = os.getenv("GTM_TIEOUT_BASELINE_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_BASELINE_DIR


def get_config_stage() -> Optional[str]:
    """Return the configured Snowflake stage for read-only config files."""
    stage = os.getenv("GTM_TIEOUT_CONFIG_STAGE", "").strip()
    return stage or None


def get_active_org_profile(
    config_dir: Optional[Path] = None,
    profile_id: Optional[str] = None,
):
    """Return the active org profile manifest."""
    return load_org_profile(config_dir=config_dir, profile_id=profile_id)


def resolve_config_resource_path(
    filename: str,
    config_dir: Optional[Path] = None,
    profile_id: Optional[str] = None,
) -> Path:
    """Resolve a local config resource path through the active org profile."""
    return resolve_profile_resource_path(
        filename,
        config_dir=config_dir,
        profile_id=profile_id,
    )


def get_baseline_table() -> str:
    """Return the Snowflake table used for persisted hosted baselines."""
    table = os.getenv("GTM_TIEOUT_BASELINE_TABLE", "").strip()
    return table or _DEFAULT_BASELINE_TABLE


def get_active_snowflake_session() -> Any | None:
    """Return the active Snowpark session when running inside Snowflake."""
    try:
        from snowflake.snowpark.context import get_active_session
    except Exception:
        return None

    try:
        return get_active_session()
    except Exception:
        return None


def detect_snow_cli_command() -> Optional[str]:
    """Detect the Snowflake CLI command for local development."""
    try:
        subprocess.run(
            ["snow", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "snow"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        subprocess.run(
            ["python3", "-m", "snowflake.cli.app.__main__", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "python3 -m snowflake.cli.app.__main__"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def is_hosted_mode() -> bool:
    """Return True when running inside Streamlit in Snowflake (active Snowpark session).

    In hosted mode, subprocess-based CLI queries are forbidden — all queries
    must go through the native Snowpark session.
    """
    return get_active_snowflake_session() is not None


def has_native_snowflake_runtime() -> bool:
    """Return True when either a Snowpark session or local Snow CLI exists."""
    return get_active_snowflake_session() is not None or detect_snow_cli_command() is not None


def load_text_resource(
    filename: str,
    config_dir: Optional[Path] = None,
    config_stage: Optional[str] = None,
    profile_id: Optional[str] = None,
) -> Optional[str]:
    """Load a config text resource from local disk or a Snowflake stage."""
    local_dir = config_dir or get_default_config_dir()
    local_path = resolve_config_resource_path(
        filename,
        config_dir=local_dir,
        profile_id=profile_id,
    )
    if local_path.exists():
        return local_path.read_text()

    stage = config_stage or get_config_stage()
    if not stage:
        return None

    session = get_active_snowflake_session()
    if session is None:
        return None

    try:
        from snowflake.snowpark.files import SnowflakeFile

        normalized_stage = stage if stage.startswith("@") else f"@{stage}"
        resource_location = resolve_profile_resource_location(
            filename,
            config_dir=local_dir,
            profile_id=profile_id,
        )
        location = f"{normalized_stage.rstrip('/')}/{resource_location}"
        with SnowflakeFile.open(location, "r", require_scoped_url=False) as handle:
            contents = handle.readall() if hasattr(handle, "readall") else handle.read()
        if isinstance(contents, bytes):
            return contents.decode("utf-8")
        return str(contents)
    except Exception as exc:
        logger.info("Could not load %s from config stage %s: %s", filename, stage, exc)
        return None


def load_yaml_resource(
    filename: str,
    config_dir: Optional[Path] = None,
    config_stage: Optional[str] = None,
    profile_id: Optional[str] = None,
) -> dict:
    """Load a YAML config resource from local disk or a Snowflake stage."""
    raw = load_text_resource(
        filename,
        config_dir=config_dir,
        config_stage=config_stage,
        profile_id=profile_id,
    )
    if not raw:
        return {}
    loaded = yaml.safe_load(raw)
    return loaded or {}

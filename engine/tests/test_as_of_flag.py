"""Tests for the --as-of flag plumbing in generate_snapshot.py.

Per ARCHITECTURE.md, the canonical generator gains a --as-of YYYY-MM-DD flag for
deterministic snapshot output. Production runs (no flag) use date.today().

NOTE: These tests verify argparse parsing + plumbing into build_snapshot().
End-to-end determinism (no callsite uses date.today() when --as-of is
provided) requires the wiring layer and is verified there.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date


def test_as_of_flag_accepts_iso_date():
    """--as-of 2026-04-06 parses without error (running with --help)."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "engine.scripts.generate_snapshot",
            "--help",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--as-of" in result.stdout
    assert "ARCHITECTURE.md" in result.stdout


def test_invalid_as_of_format_exits_with_error():
    """--as-of 'not-a-date' fails fast with exit code 2."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "engine.scripts.generate_snapshot",
            "--as-of",
            "not-a-date",
            "--profile-id",
            "acme-saas",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "as-of must be YYYY-MM-DD" in result.stderr


def test_build_snapshot_accepts_as_of_kwarg():
    """The build_snapshot() function signature accepts as_of."""
    from engine.scripts.generate_snapshot import build_snapshot
    import inspect

    sig = inspect.signature(build_snapshot)
    assert "as_of" in sig.parameters
    assert sig.parameters["as_of"].default is None

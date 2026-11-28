"""Shared helpers for the evidence tests (no tests live here)."""

import json
import shutil
from pathlib import Path

import yaml

from engine.harness.contract.manifest import build_manifest, write_manifest

ROOT = Path(__file__).resolve().parents[1] / "contract" / "fixtures" / "estate_a"
ESTATE_YAML = ROOT / "estate.yaml"
ESTATE = yaml.safe_load(ESTATE_YAML.read_text())
EXPECTED = yaml.safe_load((ROOT / "expected.yaml").read_text())
CASES = EXPECTED["cases"]
MODES = ("reconstructed", "contemporaneous")


def estate_dirs() -> list[Path]:
    """Every system folder of every extract of estate A."""
    return sorted(p for p in ROOT.glob("extract_*/*") if p.is_dir())


def copy_estate(dest: Path) -> list[Path]:
    """A writable copy of estate A; returns its system folders."""
    shutil.copytree(ROOT, dest)
    return sorted(p for p in dest.glob("extract_*/*") if p.is_dir())


def read_rows(folder: Path, name: str) -> list[dict]:
    path = folder / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def write_rows(folder: Path, name: str, rows: list[dict]) -> None:
    (folder / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def rewrite_manifest(folder: Path) -> None:
    """Rebuild a folder's manifest after its files changed (same system and time)."""
    old = json.loads((folder / "manifest.json").read_text())
    from datetime import datetime

    when = datetime.fromisoformat(old["extracted_at"])
    write_manifest(folder, build_manifest(folder, old["source_system"], when))

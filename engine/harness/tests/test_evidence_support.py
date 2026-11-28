"""Shared helpers for the evidence tests (no tests live here)."""

import json
import re
import shutil
from datetime import UTC, datetime
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
    when = datetime.fromisoformat(old["extracted_at"])
    write_manifest(folder, build_manifest(folder, old["source_system"], when))


# ---- a scaled-up estate -------------------------------------------------

_ID = re.compile(r"^(?:[0-9A-Za-z]{3}FX\d{10}|[A-Z]+-\d+|\d{3})$")
EXTRA_EXTRACT_DATES = [
    datetime(2025 + (6 + i) // 12, (6 + i) % 12 + 1, 28, 23, tzinfo=UTC)
    for i in range(1, 12)
]  # eleven more monthly extracts after estate A's second


def _clone(value, copy: int):
    if isinstance(value, str):
        if value.endswith("@example.com"):
            local, _, domain = value.partition("@")
            return f"{local}.c{copy}@{domain}"
        return f"{value}-c{copy}" if _ID.match(value) else value
    return value


def scaled_estate(dest: Path, copies: int, extracts: int = 13) -> list[Path]:
    """Estate A replicated `copies` times with distinct ids, extracted `extracts` times per system.

    The extra extracts repeat the second extract's content at later monthly dates.
    Plan lines are left out (their key would repeat). Returns every system folder.
    """
    sources = [f for f in estate_dirs() if f.name != "plan_file"]
    out: list[Path] = []
    latest: dict[str, Path] = {}
    for src in sources:
        target = dest / src.parent.name / src.name
        target.mkdir(parents=True)
        manifest = json.loads((src / "manifest.json").read_text())
        for name in manifest["objects"]:
            lines = []
            for line in (src / f"{name}.jsonl").read_text().splitlines():
                record = json.loads(line)
                lines += [
                    json.dumps({k: _clone(v, c) for k, v in record.items()})
                    for c in range(copies)
                ]
            (target / f"{name}.jsonl").write_text("".join(x + "\n" for x in lines))
        write_manifest(
            target,
            build_manifest(
                target,
                manifest["source_system"],
                datetime.fromisoformat(manifest["extracted_at"]),
            ),
        )
        out.append(target)
        latest[src.name] = target
    for i, when in enumerate(EXTRA_EXTRACT_DATES[: extracts - 2]):
        for system, base in latest.items():
            if "06-30" not in base.parent.name:
                continue  # only systems whose last extract is estate A's second
            target = dest / f"extract_extra_{i:02d}" / system
            target.mkdir(parents=True)
            for file in base.glob("*.jsonl"):
                shutil.copy(file, target / file.name)
            write_manifest(target, build_manifest(target, system, when))
            out.append(target)
    return sorted(out)

"""The extract manifest: what one extraction of one source system contains.

An extract is a folder holding `manifest.json` and one `<Object>.jsonl` per
object. Semantics (design section 1):

- Each listed object is a complete snapshot of that object at `extracted_at`.
- An object that is not listed was not extracted. Its state is unavailable,
  never empty. A listed object with `count` 0 is genuinely empty.
- A record present in an earlier complete snapshot of the same source system
  and absent from a later one was deleted as of the later extract.
- Loading is idempotent by content hash (`content_hash`).

Manifest shape (JSON):

    {"manifest_version": 1,
     "extract_id": "salesforce-20250430T230000Z",
     "source_system": "salesforce",
     "extracted_at": "2025-04-30T23:00:00Z",
     "objects": {"Opportunity": {"count": 5, "sha256": "<hex of the file bytes>"}}}
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from .schema import parse_datetime, validate_lines
from .schemas import SCHEMAS, SYSTEMS

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1


def extract_id(source_system: str, extracted_at: datetime) -> str:
    stamp = extracted_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{source_system}-{stamp}"


def _count(path: Path) -> int:
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def build_manifest(folder: Path, source_system: str, extracted_at: datetime) -> dict:
    """Describe the object files in `folder` that belong to `source_system`."""
    objects = {}
    for name in SYSTEMS[source_system]:
        path = folder / f"{name}.jsonl"
        if path.exists():
            objects[name] = {
                "count": _count(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    return {
        "manifest_version": MANIFEST_VERSION,
        "extract_id": extract_id(source_system, extracted_at),
        "source_system": source_system,
        "extracted_at": extracted_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "objects": objects,
    }


def write_manifest(folder: Path, manifest: dict) -> None:
    (folder / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")


def content_hash(manifest: dict) -> str:
    """Hash of the extract's content alone: same files, same hash, whenever taken."""
    lines = [f"{n}:{o['sha256']}" for n, o in sorted(manifest["objects"].items())]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def validate_manifest(manifest: dict) -> list[str]:
    errors = []
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        errors.append(f"manifest_version must be {MANIFEST_VERSION}")
    system = manifest.get("source_system")
    if system not in SYSTEMS:
        errors.append(f"unknown source_system {system!r}")
    try:
        when = parse_datetime(manifest.get("extracted_at"))
    except (TypeError, ValueError):
        errors.append("extracted_at must be YYYY-MM-DDTHH:MM:SSZ")
    else:
        if system in SYSTEMS and manifest.get("extract_id") != extract_id(system, when):
            errors.append(f"extract_id must be {extract_id(system, when)}")
    objects = manifest.get("objects")
    if not isinstance(objects, dict) or not objects:
        return [*errors, "objects must list at least one object"]
    for name, entry in objects.items():
        if name not in SCHEMAS:
            errors.append(f"unknown object {name}")
        elif system in SYSTEMS and name not in SYSTEMS[system]:
            errors.append(f"{name} is not served by {system}")
        count, digest = entry.get("count"), entry.get("sha256")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"{name}: count must be a non-negative integer")
        if not (
            isinstance(digest, str)
            and len(digest) == 64
            and set(digest) <= set("0123456789abcdef")
        ):
            errors.append(f"{name}: sha256 must be 64 hex characters")
    return errors


def validate_extract(folder: Path) -> list[str]:
    """Manifest structure, file presence, counts, hashes and every record."""
    folder = Path(folder)
    path = folder / MANIFEST_NAME
    if not path.exists():
        return [f"{MANIFEST_NAME} is missing"]
    manifest = json.loads(path.read_text())
    errors = validate_manifest(manifest)
    objects = (
        manifest.get("objects") if isinstance(manifest.get("objects"), dict) else {}
    )
    for file in sorted(folder.glob("*.jsonl")):
        if file.stem not in objects:
            errors.append(f"{file.name} is not listed in the manifest")
    for name, entry in objects.items():
        file = folder / f"{name}.jsonl"
        if not file.exists():
            errors.append(f"{name}: listed in the manifest but {file.name} is missing")
            continue
        if name not in SCHEMAS:
            continue
        lines = file.read_text().splitlines()
        records = sum(1 for line in lines if line.strip())
        if entry.get("count") != records:
            errors.append(
                f"{name}: count {entry.get('count')} in manifest but {records} records"
            )
        if entry.get("sha256") != hashlib.sha256(file.read_bytes()).hexdigest():
            errors.append(f"{name}: sha256 does not match {file.name}")
        errors.extend(f"{file.name} {e}" for e in validate_lines(SCHEMAS[name], lines))
    return errors

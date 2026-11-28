import json
from datetime import UTC, datetime

import pytest

from engine.harness.contract.manifest import (
    build_manifest,
    content_hash,
    extract_id,
    validate_extract,
    validate_manifest,
    write_manifest,
)

USER = {
    "Id": "005FX0000000001",
    "Name": "Alex Fixture",
    "Email": "alex.fixture@example.com",
    "Title": "Account Executive",
    "IsActive": True,
    "CreatedDate": "2024-01-02T09:00:00Z",
    "SystemModstamp": "2024-01-02T09:00:00Z",
}
WHEN = datetime(2025, 4, 30, 23, 0, 0, tzinfo=UTC)


def make_extract(folder, users=(USER,), account_lines=()):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "User.jsonl").write_text("".join(json.dumps(u) + "\n" for u in users))
    (folder / "Account.jsonl").write_text("".join(account_lines))
    manifest = build_manifest(folder, "salesforce", WHEN)
    write_manifest(folder, manifest)
    return manifest


def test_extract_id_is_derived_from_system_and_time():
    assert extract_id("salesforce", WHEN) == "salesforce-20250430T230000Z"


def test_built_manifest_has_counts_and_hashes(tmp_path):
    m = make_extract(tmp_path / "e")
    assert m["source_system"] == "salesforce"
    assert m["extracted_at"] == "2025-04-30T23:00:00Z"
    assert m["extract_id"] == "salesforce-20250430T230000Z"
    assert m["objects"]["User"]["count"] == 1
    assert m["objects"]["Account"]["count"] == 0  # present and empty, not missing
    assert len(m["objects"]["User"]["sha256"]) == 64
    assert validate_extract(tmp_path / "e") == []


def test_unlisted_object_means_not_extracted(tmp_path):
    folder = tmp_path / "e"
    folder.mkdir()
    (folder / "User.jsonl").write_text(json.dumps(USER) + "\n")
    m = build_manifest(folder, "salesforce", WHEN)
    assert set(m["objects"]) == {"User"}


def test_content_hash_ignores_when_it_was_taken(tmp_path):
    a = make_extract(tmp_path / "a")
    b = build_manifest(tmp_path / "a", "salesforce", datetime(2025, 5, 1, tzinfo=UTC))
    assert a["extract_id"] != b["extract_id"]
    assert content_hash(a) == content_hash(b)


def test_tampered_file_fails_hash_and_count(tmp_path):
    folder = tmp_path / "e"
    make_extract(folder)
    with (folder / "User.jsonl").open("a") as f:
        f.write(json.dumps({**USER, "Id": "005FX0000000002"}) + "\n")
    errors = validate_extract(folder)
    assert any("User: count 1 in manifest but 2 records" in e for e in errors)
    assert any("User: sha256 does not match" in e for e in errors)


def test_record_errors_name_file_and_line(tmp_path):
    folder = tmp_path / "e"
    make_extract(folder, users=({**USER, "IsActive": "yes"},))
    assert any(
        e.startswith("User.jsonl line 1: IsActive") for e in validate_extract(folder)
    )


def test_file_without_manifest_entry_is_an_error(tmp_path):
    folder = tmp_path / "e"
    make_extract(folder)
    (folder / "Lead.jsonl").write_text("")
    assert any(
        "Lead.jsonl is not listed in the manifest" in e
        for e in validate_extract(folder)
    )


def test_listed_object_without_file_is_an_error(tmp_path):
    folder = tmp_path / "e"
    make_extract(folder)
    (folder / "Account.jsonl").unlink()
    assert any(
        "Account: listed in the manifest but Account.jsonl is missing" in e
        for e in validate_extract(folder)
    )


def test_missing_manifest(tmp_path):
    assert validate_extract(tmp_path) == ["manifest.json is missing"]


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"source_system": "oracle"}, "unknown source_system"),
        ({"extracted_at": "2025-04-30"}, "extracted_at"),
        ({"extract_id": "x"}, "extract_id must be"),
        ({"manifest_version": 2}, "manifest_version"),
        (
            {
                "objects": {"Opportunity": {"count": 0, "sha256": "0" * 64}},
                "extract_id": "salesforce-20250430T230000Z",
            },
            None,
        ),
        (
            {"objects": {"people": {"count": 0, "sha256": "0" * 64}}},
            "people is not served by salesforce",
        ),
        ({"objects": {"User": {"count": -1, "sha256": "0" * 64}}}, "count"),
        ({"objects": {"User": {"count": 0, "sha256": "abc"}}}, "sha256"),
        ({"objects": {}}, "at least one object"),
    ],
)
def test_manifest_structure(tmp_path, change, fragment):
    manifest = {**make_extract(tmp_path / "e"), **change}
    errors = validate_manifest(manifest)
    if fragment is None:
        assert errors == []
    else:
        assert any(fragment in e for e in errors), errors


def test_deletion_semantics_keep_prior_existence():
    from engine.harness.contract import manifest as module

    doc = " ".join(module.__doc__.split())
    assert "existed" in doc and "upper bound" in doc
    assert "never existed" not in doc

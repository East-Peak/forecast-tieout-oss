"""Owner rows live in their own file beside the lanes: split, merged back, and held to one contract."""

import copy
import json
from pathlib import Path

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import lanes_basis, lanes_contract, lanes_files


def pair(built, scenario="demo-plan"):
    company, _, basis, docs = built
    report, doc = docs[scenario]
    lanes_doc, owners = lanes_files.split(
        copy.deepcopy(doc)
    )  # tests edit what they get
    return lanes_doc, owners, lanes_basis.document(basis, company), report, doc


def first(owners):
    return next(iter(owners.values()))


def test_the_lanes_file_holds_only_the_company_and_the_segments_and_each_segment_has_a_file(
    built,
):
    lanes_doc, owners, *_ = pair(built)
    for p in lanes_doc["periods"]:
        assert {r["kind"] for r in p["rows"]} == {"company", "segment"}
    segments = [r["path"][1] for r in lanes_doc["periods"][0]["rows"][1:]]
    assert list(owners) == segments
    for seg, doc in owners.items():
        assert doc["segment"] == seg
        for p in doc["periods"]:
            assert all(len(r["path"]) == 4 and r["path"][1] == seg for r in p["rows"])
    names = [c["name"] for c in first(owners)["checks"]]
    assert "owner creation adds to the segment's" in names
    assert "owner creation adds to the segment's" not in [c["name"] for c in lanes_doc["checks"]]  # fmt: skip


def test_the_file_names_are_the_segment_made_safe_and_do_not_collide():
    assert lanes_files.name("demo-plan", "Strategic Enterprise") == "lanes-owners-demo-plan-strategic-enterprise.json"  # fmt: skip
    assert lanes_files.slug("") == "segment"


def test_merging_the_files_gives_back_the_whole_document(built):
    *_, doc = pair(built)
    lanes_doc, owners = lanes_files.split(doc)
    assert lanes_files.merge(lanes_doc, list(owners.values())) == doc
    assert lanes_files.split(doc) == lanes_files.split(copy.deepcopy(doc))


def test_each_file_and_the_set_satisfy_the_contract(built):
    company, _, basis, docs = built
    basis_doc = lanes_basis.document(basis, company)
    for report, doc in docs.values():
        lanes_doc, owners = lanes_files.split(copy.deepcopy(doc))
        assert lanes_contract.validate(lanes_doc, basis_doc, report) == []
        for seg_doc in owners.values():
            assert lanes_contract.validate_owners(seg_doc, lanes_doc, basis_doc, report) == []  # fmt: skip
        assert lanes_contract.validate_owner_set(list(owners.values()), lanes_doc) == []  # fmt: skip


def problems(built, edit):
    lanes_doc, owners, basis_doc, report, _ = pair(built)
    edit(lanes_doc, owners)
    found = lanes_contract.validate_owner_set(list(owners.values()), lanes_doc)
    for doc in owners.values():
        found += lanes_contract.validate_owners(doc, lanes_doc, basis_doc, report)
    return found


def test_owners_that_do_not_add_to_the_segment_are_found_across_the_files(built):
    def owner(lanes_doc, owners):
        row = next(r for d in owners.values() for r in d["periods"][0]["rows"] if r["cells"]["bookings"]["forecast"])  # fmt: skip
        row["cells"]["bookings"]["forecast"] = "1.00"

    def segment(lanes_doc, owners):
        lanes_doc["periods"][0]["rows"][1]["cells"]["won"]["actual"] = "1.0000"

    assert any("segment" in p for p in problems(built, owner))
    assert problems(built, segment)


def test_an_owners_file_for_another_scenario_or_basis_or_one_missing_is_found(built):
    def scenario(lanes_doc, owners):
        first(owners)["scenario"] = "somewhere-else"

    def digest(lanes_doc, owners):
        first(owners)["plan_basis"]["digest"] = "0" * 64

    def drop(lanes_doc, owners):
        first(owners)["periods"][0]["rows"].pop()

    def missing(lanes_doc, owners):
        owners.pop(next(iter(owners)))

    assert any("scenario" in p for p in problems(built, scenario))
    assert any("basis" in p for p in problems(built, digest))
    assert problems(built, drop)
    assert any("missing" in p for p in problems(built, missing))


def test_the_owner_wording_is_in_the_owners_files(built):
    *_, basis_doc, _, _ = pair(built)
    _, owners, *_ = pair(built)
    assert all(basis_doc["owner_caveat"] in d["caveats"] for d in owners.values())


def test_no_committed_data_file_is_over_a_megabyte_and_a_half():
    root = gen.REPO / gen.REPORTS
    big = {
        p.relative_to(root).as_posix(): p.stat().st_size
        for p in root.rglob("*.json")
        if p.stat().st_size > 1_500_000
    }
    assert big == {}
    assert json.loads(Path(root / "index.json").read_text())["companies"]


def test_the_index_names_each_scenarios_owner_files_by_segment_as_an_optional_key():
    index = json.loads((gen.REPO / gen.REPORTS / "index.json").read_text())
    for company in index["companies"]:
        for sc in company["scenarios"]:
            lanes_doc = json.loads((gen.REPO / gen.REPORTS / sc["lanes"]).read_text())
            segments = [r["path"][1] for r in lanes_doc["periods"][0]["rows"][1:]]
            assert sorted(sc["lanes_owners"]) == sorted(
                segments
            )  # the index is canonical: keys sorted
            for seg, path in sc["lanes_owners"].items():
                assert path == f"{company['id']}/{lanes_files.name(sc['id'], seg)}"
                assert (gen.REPO / gen.REPORTS / path).exists()
    item = gen.INDEX_SCHEMA["properties"]["companies"]["items"]["properties"]["scenarios"]["items"]  # fmt: skip
    assert "lanes_owners" not in item["required"]

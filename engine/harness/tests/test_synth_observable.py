"""The observable truth: what a perfect reader of the extracts knows at the final extract."""

import json
import tempfile
from collections import defaultdict
from functools import cache
from pathlib import Path

import numpy as np

from engine.harness.contract.snapshot import flow_check
from engine.harness.synth.cli import generate
from engine.harness.synth.params import CompanyParams
from engine.harness.synth.records import default_extract_dates, extract_folder
from engine.harness.synth.truth import load_truth


@cache
def default_company(variant="capacity_constrained", seed=1):
    out = Path(tempfile.mkdtemp(prefix="synth_obs_"))
    params = CompanyParams.for_variant(variant)
    generate(params, seed, out)
    return out, json.loads((out / "truth" / "manifest.json").read_text())


def read(out, when, system, name):
    path = extract_folder(out, when) / system / f"{name}.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def test_observable_truth_passes_flow_check_and_reports_what_it_cannot_know():
    out, manifest = default_company()
    truth = load_truth(out / "truth" / "observable_snapshot.json")
    report = flow_check(truth)
    assert report.violations == [] and report.checked > 3000
    assert report.unavailable and all(
        "carrying_capacity" in why for _, why in report.unavailable
    )
    assert set(manifest["observable"]["masked"]) == {
        "spend_cents",
        "bdr_exposure",
        "ramped_heads",
        "ramp_exposure",
        "carrying_capacity",
    }
    assert all(manifest["observable"]["masked"].values())  # each has a reason
    for name in manifest["observable"]["masked"]:
        assert getattr(truth, name).missing.all(), name
    assert truth.months[-1] == "2026-01" and truth.heads.values.sum() > 0


def test_observable_bookings_equal_the_final_extract_exactly_on_the_default_configuration():
    out, _ = default_company()
    last = default_extract_dates(CompanyParams.for_variant("capacity_constrained"))[-1]
    by_month = defaultdict(int)
    for r in read(out, last, "salesforce", "Opportunity"):
        if r["Type"] == "New Business" and r["IsWon"]:
            by_month[r["CloseDate"][:7]] += round(r["Amount"] * 100)
    truth = load_truth(out / "truth" / "observable_snapshot.json")
    expected = {
        m: int(v)
        for m, v in zip(
            truth.months, truth.bookings_cents.values.sum(axis=0), strict=True
        )
        if v
    }
    assert dict(by_month) == expected and len(expected) > 40


def test_observable_and_omniscient_truths_differ_only_where_the_extracts_cannot_see():
    out, manifest = default_company()
    obs = load_truth(out / "truth" / "observable_snapshot.json")
    omni = load_truth(out / "truth" / "omniscient_snapshot.json")
    n = len(obs.months)
    assert (
        omni.months[:n] == obs.months and len(omni.months) > n
    )  # the simulation ran on past the last extract
    assert (obs.leads.values == omni.leads.values[:, :n]).all()
    for name in (
        "arrivals",
        "admissions",
        "wins",
    ):  # by month: lanes can differ (re-tiered accounts)
        assert (
            getattr(obs, name).values.sum(axis=0)
            == getattr(omni, name).values[:, :n].sum(axis=0)
        ).all(), name
    # a deal lost and then deleted before the next extract never shows its loss
    for name in ("losses", "reopened"):
        gap = getattr(omni, name).values[:, :n].sum() - getattr(obs, name).values.sum()
        assert 0 <= gap <= manifest["observable"]["observed_deletions"], name
    note = manifest["observable"]
    assert note["amendments_or_corrections_after_final_extract"] > 0
    assert (
        obs.bookings_cents.values.sum() != omni.bookings_cents.values[:, :n].sum()
    )  # amendments after the last extract
    gap = (
        omni.mqls.values[:, :n].sum() - obs.mqls.values.sum()
    )  # MQLs entered in arrears, after the last extract
    assert 0 < gap <= note["mql_dates_recorded_after_final_extract"]


def test_observed_deletions_match_records_that_vanish_between_extracts():
    out, manifest = default_company()
    dates = default_extract_dates(CompanyParams.for_variant("capacity_constrained"))
    seen, gone, closed_before = set(), set(), set()
    for when in dates:
        rows = {
            r["Id"]: r
            for r in read(out, when, "salesforce", "Opportunity")
            if r["Type"] == "New Business"
        }
        gone |= seen - rows.keys()
        closed_before |= {i for i, r in rows.items() if r["IsClosed"]}
        seen |= rows.keys()
    assert (
        len(gone)
        == manifest["observable"]["observed_deletions"]
        - manifest["observable"]["ghost_lead_derived_opportunities"]
    )
    truth = load_truth(out / "truth" / "observable_snapshot.json")
    assert (
        truth.deleted.values.sum()
        <= len(gone) + manifest["observable"]["ghost_lead_derived_opportunities"]
    )


def test_the_manifest_counts_explain_the_differences():
    _, manifest = default_company()
    note = manifest["observable"]
    for key in (
        "never_observed_records",
        "accounts_retiered_before_first_sighting",
        "opportunities_with_retiered_accounts",
        "amendments_or_corrections_after_final_extract",
        "opportunities_closing_after_final_extract",
        "opportunities_in_a_different_lane_than_at_creation",
        "mql_dates_recorded_after_final_extract",
    ):
        assert isinstance(note[key], int), key
    assert note["accounts_retiered_before_first_sighting"] > 0
    assert (
        note["opportunities_with_retiered_accounts"]
        >= note["opportunities_in_a_different_lane_than_at_creation"]
        > 0
    )


def test_program_spend_is_kept_by_campaign_beside_the_masked_lane_spend():
    out, _ = default_company()
    table = json.loads((out / "truth" / "observable_spend_by_program.json").read_text())
    last = default_extract_dates(CompanyParams.for_variant("capacity_constrained"))[-1]
    sheet = sum(r["amount_cents"] for r in read(out, last, "spend_sheet", "spend"))
    assert sum(v for months in table.values() for v in months.values()) == sheet
    assert np.isfinite(sheet) and "Paid Search SMB" in table

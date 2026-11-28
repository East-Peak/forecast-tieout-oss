"""Named cases are present in the generated company and findable from the manifest."""

import json
from datetime import date

import pytest

from engine.harness.contract.snapshot import flow_check
from engine.harness.synth.cases import named_cases
from engine.harness.synth.cli import generate
from engine.harness.synth.params import CompanyParams
from engine.harness.synth.run import run_company
from engine.harness.synth.truth import load_truth
from engine.harness.tests.test_synth_company import SMALL_END, SMALL_START

DATES = [date(2024, 12, 18), date(2025, 1, 31), SMALL_END]


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    out = tmp_path_factory.mktemp("company")
    generate(
        CompanyParams.for_variant(
            "capacity_constrained", start=SMALL_START, end=SMALL_END
        ),
        2,
        out,
        DATES,
    )
    return out, json.loads((out / "truth" / "manifest.json").read_text())


def test_output_layout_keeps_truth_apart_from_the_extracts(output):
    out, manifest = output
    assert sorted(p.name for p in out.iterdir()) == ["extracts", "truth"]
    assert len(list((out / "extracts").iterdir())) == len(DATES)
    assert (out / "truth" / "omniscient_snapshot.json").exists()
    assert (out / "truth" / "observable_snapshot.json").exists()
    assert (
        flow_check(load_truth(out / "truth" / "omniscient_snapshot.json")).violations
        == []
    )
    assert manifest["seed"] == 2 and manifest["variant"] == "capacity_constrained"
    assert manifest["extract_dates"] == [d.isoformat() for d in DATES]
    assert manifest["params"]["company_name"].endswith("(fictional)")
    assert manifest["params"]["segments"][0]["ceiling"] > 0


def test_every_named_case_is_in_the_manifest_and_matches_the_data(output):
    out, manifest = output
    cases = manifest["named_cases"]
    assert set(cases) == {
        "thin_slice",
        "improvement_understated",
        "immature_cohort",
        "missing_attribution",
        "very_large_deal",
        "slipping_hires",
        "plateaued_lane",
        "benchmark_hires",
    }
    lanes = load_truth(out / "truth" / "omniscient_snapshot.json").lanes
    final = out / "extracts" / f"extract_{SMALL_END.isoformat()}"
    opps = {
        json.loads(x)["Id"]: json.loads(x)
        for x in (final / "salesforce" / "Opportunity.jsonl").read_text().splitlines()
    }

    thin = cases["thin_slice"]
    assert thin["lane"] in lanes and 0 < thin["opportunities"] <= 12

    step = cases["improvement_understated"]
    assert (
        step["lane"] in lanes
        and step["win_probability_after"] > step["win_probability_before"] + 0.05
    )
    assert step["step_on"] == "2024-08-01"

    young = cases["immature_cohort"]
    assert young["opportunities"] > 0 and young["share_closed_at_plan_date"] < 0.6

    missing = cases["missing_attribution"]
    assert (
        missing["lane_suffix"] == "source=Unknown" and missing["unattributed_mqls"] > 0
    )
    assert any(lane.endswith("source=Unknown") for lane in lanes)

    whale = cases["very_large_deal"]
    assert opps[whale["opportunity_id"]]["Amount"] == whale["amount_cents"] / 100
    assert whale["amount_cents"] >= 250_000_000

    reqs = {
        json.loads(x)["req_id"]: json.loads(x)
        for x in (final / "people_system" / "requisitions.jsonl")
        .read_text()
        .splitlines()
    }
    slipped = cases["slipping_hires"]
    assert len(slipped) >= 3 and all(h["slip_days"] > 0 for h in slipped)
    assert all(
        h["req_id"] in reqs
        for h in slipped
        if h["actual_start"] <= SMALL_END.isoformat()
    )

    plateau = cases["plateaued_lane"]
    assert (
        plateau["lane"] in lanes
        and plateau["expected_mqls_after"] <= plateau["expected_mqls_before"] * 1.08
    )

    picks = cases["benchmark_hires"]
    assert set(picks) == {"AE-SMB", "AE-MidMarket", "AE-Enterprise"}
    for team, pick in picks.items():
        assert pick["req_id"] in reqs and reqs[pick["req_id"]]["team"] == team
        assert (
            pick["planned_start"] >= "2025-02-01"
            and reqs[pick["req_id"]]["role"] == "AE"
        )


def test_the_step_change_in_win_rate_shows_in_outcomes_and_a_trailing_rate_understates_it():
    before, after, trailing = [], [], []
    for seed in (1, 2, 3):
        case = named_cases(
            run_company(CompanyParams.for_variant("demand_limited"), seed)
        )["improvement_understated"]
        before.append(case["win_rate_before"])
        after.append(case["win_rate_after"])
        trailing.append(case["trailing_12m_win_rate_at_plan_date"])
    mean = lambda xs: sum(xs) / len(xs)
    assert mean(after) > mean(before) + 0.05
    assert mean(trailing) < mean(after) - 0.01


def test_extract_dates_are_causally_inert():
    """The business does not know when it will be extracted: the event log is the same for any dates."""
    import pathlib
    import tempfile

    from engine.harness.synth.cli import generate

    params = CompanyParams.for_variant(
        "demand_limited", start=SMALL_START, end=SMALL_END, p_delete=0.3
    )
    prints = []
    for dates in (
        [],
        [date(2024, 12, 18)],
        [date(2024, 12, 18), date(2025, 1, 31), SMALL_END],
    ):
        with tempfile.TemporaryDirectory() as scratch:
            company = generate(params, 1, pathlib.Path(scratch), dates)
            prints.append(
                (
                    company.sim.fingerprint(),
                    (
                        pathlib.Path(scratch) / "truth/omniscient_snapshot.json"
                    ).read_text(),
                )
            )
    assert prints[0] == prints[1] == prints[2]

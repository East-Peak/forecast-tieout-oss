"""Goal 3B: the fields the Capacity, Pipeline, Plan and Trust screens need and the report lacked.
Additions only: each is a new field beside figures that do not change."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import contract
from engine.tieout_core.markdown import render as render_markdown
from engine.tieout_core.pipeline_report import surplus_statement
from engine.tieout_core.rates import RATE_UNITS, rate_unit
from engine.tieout_core.report import build_report

AS_OF = gen.AS_OF
COMPANIES = gen.COMPANIES


@pytest.fixture(scope="module")
def reports():
    out = {}
    for company in COMPANIES:
        profile = Path(f"engine/config/profiles/{company}")
        out[company] = build_report(
            profile, Path(f"engine/data-v2/{company}"), AS_OF, draws=100
        )
    return out


# ---------------------------------------------------------------- the surplus, in words


def test_a_surplus_reads_as_ahead_a_negative_one_as_still_short():
    assert surplus_statement(Decimal("1079240.19")) == (
        "ahead of target by $1,079,240 once every quarter's schedule is created"
    )
    assert surplus_statement(Decimal("-1116243.83")) == (
        "still short of target by $1,116,244 even once every quarter's schedule is created"
    )
    assert surplus_statement(Decimal("0.00")) == (
        "exactly on target once every quarter's schedule is created"
    )
    assert surplus_statement(None) is None


def test_every_quarter_row_carries_its_surplus_in_words_and_never_a_negative_requirement(
    reports,
):
    for company, report in reports.items():
        for q in report["required_pipeline"]["quarters"]:
            said = q["surplus_statement"]
            surplus = q["surplus_over_target"]
            if surplus is None:
                assert said is None
                continue
            sign = Decimal(surplus)
            assert (
                said.startswith("ahead of")
                if sign > 0
                else said.startswith("still short of")
                if sign < 0
                else said.startswith("exactly on")
            ), (company, q["quarter"], said)
            assert "-$" not in said and "-" not in said.split("by $")[-1][:1]


# ---------------------------------------------------------------- the unit of each rate


def test_every_rate_in_every_report_has_a_declared_unit(reports):
    for company, report in reports.items():
        for rate in report["rates"]:
            assert rate["unit"] in {"share", "dollars", "number"}, (
                company,
                rate["name"],
            )
            assert rate["unit"] == rate_unit(rate["name"])


def test_only_a_share_carries_a_range(reports):
    for report in reports.values():
        for rate in report["rates"]:
            if rate["range95"] is not None:
                assert rate["unit"] == "share", rate["name"]


def test_a_share_is_between_zero_and_one_and_a_name_without_a_unit_is_refused(reports):
    for report in reports.values():
        for rate in report["rates"]:
            if rate["unit"] == "share":
                assert Decimal(0) <= Decimal(rate["value"]) <= Decimal(1)
    assert "win_within_horizon" in RATE_UNITS
    with pytest.raises(KeyError, match="no unit declared"):
        rate_unit("a_rate_nobody_declared")
    assert rate_unit("ramp_weight:3") == "share"


# ---------------------------------------------------------------- the version, the schema


def test_the_schema_version_is_bumped_and_the_schema_requires_the_new_fields(reports):
    assert contract.SCHEMA_VERSION == "2.4.0"
    report = json.loads(json.dumps(reports["sprout-labs"]))
    assert contract.validate(report) == []
    del report["backtest"]["candidates"]["ranges"]
    assert contract.validate(report)
    report = json.loads(json.dumps(reports["sprout-labs"]))
    del report["gap"]["fiscal_year"]["label_short"]
    assert contract.validate(report)
    report = json.loads(json.dumps(reports["sprout-labs"]))
    del report["required_pipeline"]["quarters"][0]["surplus_statement"]
    assert contract.validate(report)
    report = json.loads(json.dumps(reports["sprout-labs"]))
    del report["rates"][0]["unit"]
    assert contract.validate(report)


# ---------------------------------------------------------------- report.md beside report.json


def test_each_scenario_has_its_report_md_and_the_index_points_to_it():
    built = gen.build(["sprout-labs"], draws=100)
    index = json.loads(built["index.json"])
    [company] = index["companies"]
    for scenario in company["scenarios"]:
        json_path = scenario["report"]
        md_path = scenario["report_markdown"]
        assert md_path == json_path.removesuffix(".json") + ".md"
        assert built[md_path].startswith("# ")
    # the readable file is what `python -m engine.tieout_core report` writes: rendered from the
    # report as built (its sections in their order), not from the key-sorted JSON
    with gen.in_repo():
        profile = Path("engine/config/profiles/sprout-labs")
        signed = build_report(
            profile, Path("engine/data-v2/sprout-labs"), AS_OF, draws=100
        )
    assert built["sprout-labs/as-signed.md"] == render_markdown(signed)


# ---------------------------------------------------------------- the contract refuses a report that disagrees with itself


def _copy(report):
    return json.loads(json.dumps(report))


def test_a_rate_whose_unit_is_not_its_names_unit_is_refused(reports):
    report = _copy(reports["sprout-labs"])
    rate = next(x for x in report["rates"] if x["name"] == "mean_won_arr")
    rate["unit"] = "share"
    problems = contract.validate(report)
    assert any("mean_won_arr" in p and "unit" in p for p in problems), problems


def test_a_rate_with_a_name_nobody_declared_is_refused(reports):
    report = _copy(reports["sprout-labs"])
    report["rates"][0]["name"] = "a_rate_nobody_declared"
    assert any("a_rate_nobody_declared" in p for p in contract.validate(report))


def test_a_range_on_a_rate_that_is_not_a_share_is_refused(reports):
    report = _copy(reports["sprout-labs"])
    rate = next(x for x in report["rates"] if x["name"] == "mean_won_arr")
    rate["range95"] = [0.1, 0.2]
    problems = contract.validate(report)
    assert any("mean_won_arr" in p and "range" in p for p in problems), problems


def test_a_surplus_statement_that_disagrees_with_its_surplus_is_refused(reports):
    base = reports["sprout-labs"]
    quarters = base["required_pipeline"]["quarters"]
    assert any(
        q["surplus_over_target"] and Decimal(q["surplus_over_target"]) < 0
        for q in quarters
    )
    # the wrong sign: a shortfall said as a surplus
    report = _copy(base)
    q = next(
        x
        for x in report["required_pipeline"]["quarters"]
        if Decimal(x["surplus_over_target"]) < 0
    )
    q["surplus_statement"] = q["surplus_statement"].replace(
        "still short of", "ahead of"
    )
    assert any("surplus" in p for p in contract.validate(report))
    # a statement with no surplus behind it, and a surplus with no statement
    report = _copy(base)
    q = report["required_pipeline"]["quarters"][0]
    q["surplus_over_target"] = None
    assert any("surplus" in p for p in contract.validate(report))
    report = _copy(base)
    report["required_pipeline"]["quarters"][0]["surplus_statement"] = None
    assert any("surplus" in p for p in contract.validate(report))

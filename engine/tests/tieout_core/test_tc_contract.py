"""Goal 3A: the report contract. A hand-written, versioned JSON Schema for
report.json; every report the core can produce, across its variants, validates
against it, and the schema rejects the ways a report could go wrong."""

import copy
import csv
import json
import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from engine.tests.tieout_core import staffed
from engine.tests.tieout_core.builders import deal, write_company, write_profile
from engine.tieout_core import contract
from engine.tieout_core.report import build_report

AS_OF = staffed.AS_OF
DRAWS = 100
REST, TWELVE = "rest of fiscal year", "next twelve months"
DEMO_AS_OF = date(2026, 8, 31)
COMPANIES = ("sprout-labs", "sapling-industries", "mighty-oak-holdings")
PLAN = {
    "programmes": [
        {"name": "Referral programme", "pipeline": 2_000_000, "start": "2026-10"}
    ],
    "hires": [{"segment": "mid_market", "start": "2026-10", "count": 3}],
}


def errors(report) -> list[str]:
    return [
        f"{'/'.join(map(str, e.absolute_path))}: {e.message[:120]}"
        for e in contract.validator().iter_errors(report)
    ]


def plan_file(tmp_path, doc=PLAN) -> Path:
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


def demo(company, plan=False, draws=DRAWS):
    profile = Path(f"engine/config/profiles/{company}")
    return build_report(
        profile, Path(f"engine/data-v2/{company}"), DEMO_AS_OF, draws=draws,
        plan_path=profile / "plan.yaml" if plan else None,
    )  # fmt: skip


# ---------------------------------------------------------------- the schema itself


def test_the_schema_is_a_valid_draft_2020_12_schema_with_a_version():
    schema = contract.schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert contract.SCHEMA_VERSION in schema["$id"]
    assert schema["properties"]["schema_version"] == {"const": contract.SCHEMA_VERSION}


def test_the_committed_schema_file_is_the_schema():
    committed = json.loads(contract.SCHEMA_PATH.read_text())
    assert committed == contract.schema()
    assert contract.SCHEMA_PATH.read_text() == contract.schema_text()


def test_every_report_carries_the_schema_version_and_nothing_else_is_added():
    r = demo("sprout-labs")
    assert r["schema_version"] == contract.SCHEMA_VERSION
    assert list(r)[-1] == "schema_version"


# ---------------------------------------------------------------- real reports validate


def test_every_report_the_suite_builds_goes_through_the_contract_check():
    """conftest.py wraps build_report before test modules import it, so any module
    here that builds a report is also validating it."""
    assert build_report.__name__ == "checked_build_report"


@pytest.mark.parametrize("plan", [False, True])
@pytest.mark.parametrize("company", COMPANIES)
def test_the_demo_reports_validate(company, plan):
    assert errors(demo(company, plan)) == []


# ---------------------------------------------------------------- every variant, built on purpose


@pytest.fixture(scope="module")
def follows(tmp_path_factory):
    return staffed.write(tmp_path_factory.mktemp("f"), rep_rate=3.0, demand=0.5)


@pytest.fixture(scope="module")
def demand(tmp_path_factory):
    return staffed.write(tmp_path_factory.mktemp("d"), rep_rate=0.0, demand=18.0)


def _without_cost(follows, tmp_path, keys):
    profile, data = follows
    bare = tmp_path / "profile"
    shutil.copytree(profile, bare)
    doc = yaml.safe_load((bare / "capacity.yaml").read_text())
    for k in keys:
        doc["costs"].pop(k, None)
    (bare / "capacity.yaml").write_text(yaml.safe_dump(doc))
    return bare, data


def _no_capacity_file(follows, tmp_path):
    profile, data = follows
    bare = tmp_path / "profile"
    shutil.copytree(profile, bare)
    (bare / "capacity.yaml").unlink()
    return bare, data


def _no_ae(follows, tmp_path):
    profile, data = follows
    bare = tmp_path / "data"
    shutil.copytree(data, bare)
    rows = [
        r
        for r in csv.DictReader((bare / "team_members.csv").open())
        if r["role"] != "ae"
    ]
    with (bare / "team_members.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return profile, bare


def _short_history(tmp_path, plan=None):
    rows = [
        deal(f"D{i}", "Closed Won", "1000", f"2026-0{m}-01", f"2026-0{m}-20")
        for i, m in enumerate(range(3, 8))
    ]
    rows.append(deal("OPEN", "Negotiation", "5000", "2026-07-01", "2026-10-15"))
    data = write_company(tmp_path / "c", rows)
    return build_report(
        write_profile(tmp_path / "p"), data, AS_OF, draws=20, plan_path=plan
    )


def _no_target_in_window():
    return build_report(
        Path("engine/config/profiles/sprout-labs"), Path("engine/data-v2/sprout-labs"),
        date(2027, 1, 31), draws=20,
    )  # fmt: skip


def _plan_on(inputs, tmp_path, doc=PLAN):
    return build_report(*inputs, AS_OF, draws=DRAWS, plan_path=plan_file(tmp_path, doc))


def _capacity(r):
    return r["roster_capacity"]["decision"]["outcome"]


def _item_kinds(r):
    return {(i["kind"], i["valued"]) for i in r["plan"]["items"]}


# name -> (how to build it, what proves the report really is that variant)
VARIANTS = {
    "capacity adopted, no plan": (
        lambda follows, demand, tmp: build_report(*follows, AS_OF, draws=DRAWS),
        lambda r: (
            _capacity(r) == "adopted"
            and "plan" not in r
            and "months" in r["roster_capacity"]
        ),
    ),
    "capacity adopted, plan of hires and a programme": (
        lambda follows, demand, tmp: _plan_on(follows, tmp),
        lambda r: (
            _capacity(r) == "adopted"
            and _item_kinds(r) == {("hires", True), ("programme", True)}
        ),
    ),
    "capacity not shown, no plan": (
        lambda follows, demand, tmp: build_report(*demand, AS_OF, draws=DRAWS),
        lambda r: _capacity(r) == "not shown" and "diagnostic" in r["roster_capacity"],
    ),
    "capacity not shown, plan whose hires are not valued": (
        lambda follows, demand, tmp: _plan_on(demand, tmp),
        lambda r: _capacity(r) == "not shown" and ("hires", False) in _item_kinds(r),
    ),
    "capacity unavailable: no capacity.yaml": (
        lambda follows, demand, tmp: build_report(
            *_no_capacity_file(follows, tmp), AS_OF, draws=DRAWS
        ),
        lambda r: _capacity(r) == "unavailable" and "ramp" not in r["roster_capacity"],
    ),
    "capacity unavailable: no quota-carrying people, with a plan": (
        lambda follows, demand, tmp: _plan_on(
            _no_ae(follows, tmp), tmp, {"hires": PLAN["hires"]}
        ),
        lambda r: _capacity(r) == "unavailable" and "plan" in r,
    ),
    "forecast unavailable for short history": (
        lambda follows, demand, tmp: _short_history(tmp),
        lambda r: (
            not r["forecasts"]["methods"][2]["available"]
            and r["actions"] == {"unavailable": r["actions"]["unavailable"]}
        ),
    ),
    "forecast unavailable, with a plan": (
        lambda follows, demand, tmp: _short_history(tmp, plan_file(tmp, PLAN)),
        lambda r: (
            not r["forecasts"]["methods"][2]["available"]
            and list(r["plan"]) == ["unavailable"]
        ),
    ),
    "missing hire cost": (
        lambda follows, demand, tmp: build_report(
            *_without_cost(follows, tmp, ["loaded_cost_per_ae_month"]),
            AS_OF,
            draws=DRAWS,
        ),
        lambda r: any(
            a["cost_status"] == "cost not entered" for a in r["actions"]["comparison"]
        ),
    ),
    "missing costs, with a plan": (
        lambda follows, demand, tmp: _plan_on(
            _without_cost(
                follows, tmp, ["loaded_cost_per_ae_month", "programme_cost_per_dollar"]
            ),
            tmp,
        ),
        lambda r: r["plan"]["cash_cost_in_twelve_months"] is None,
    ),
    "no target in the window": (
        lambda follows, demand, tmp: _no_target_in_window(),
        lambda r: r["gap"]["next_twelve_months"]["targets_through"] is None,
    ),
}


@pytest.mark.parametrize("name", list(VARIANTS))
def test_each_declared_variant_is_built_and_validates(name, follows, demand, tmp_path):
    build, is_variant = VARIANTS[name]
    report = build(follows, demand, tmp_path)
    assert is_variant(report), (
        f"the builder for {name!r} no longer produces that variant"
    )
    assert errors(report) == []


def test_the_variants_cover_the_branches_the_contract_declares():
    declared = {
        "capacity adopted", "capacity not shown", "capacity unavailable",
        "forecast unavailable", "missing hire cost", "no target in the window",
    }  # fmt: skip
    built = " | ".join(VARIANTS)
    for word in declared:
        assert word in built
    assert any("with a plan" in v or "plan" in v for v in VARIANTS)


# ---------------------------------------------------------------- the schema refuses what it should


@pytest.fixture(scope="module")
def good():
    return demo("sprout-labs", plan=True, draws=50)


def mutated(report, path, value=None, delete=False):
    r = copy.deepcopy(report)
    node = r
    for key in path[:-1]:
        node = node[key]
    if delete:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return r


@pytest.mark.parametrize(
    "path,value",
    [
        (
            ["gap", "fiscal_year", "gap"],
            1234.5,
        ),  # a number where a decimal string belongs
        (
            ["gap", "fiscal_year", "gap"],
            "1,234.50",
        ),  # a formatted string, not a decimal
        (["gap", "fiscal_year", "gap"], "12.3"),  # money is to the cent
        (["gap", "fiscal_year", "target"], "1e7"),  # no exponent form
        (["inputs", "as_of"], "08/31/2026"),
        (["schema_version"], "0.0.1"),
        (["forecasts", "windows", 0], "Sep 2026"),
        (["verdicts", "software_correct", "verdict"], "maybe"),
        (["roster_capacity", "decision", "outcome"], "adopted-ish"),
        (["gap", "quarters", 0, "status"], "late"),
    ],
)
def test_a_malformed_value_is_refused(good, path, value):
    assert errors(mutated(good, path, value)) != []


@pytest.mark.parametrize(
    "path",
    [
        ["gap", "fiscal_year", "gap"],
        ["verdicts"],
        ["schema_version"],
        ["plan", "baseline"],
        ["forecasts", "methods", 0, "method"],
        ["roster_capacity", "decision", "reason"],
    ],
)
def test_a_missing_key_is_refused(good, path):
    assert errors(mutated(good, path, delete=True)) != []


def test_an_unknown_key_is_refused_at_every_level(good):
    for path in (
        ["extra"],
        ["gap", "extra"],
        ["gap", "fiscal_year", "extra"],
        ["plan", "items", 0, "extra"],
    ):
        assert errors(mutated(good, path, "x")) != [], path


def test_unavailable_is_not_zero(good):
    # a forecast that says it is available must carry its months; one that is not must say why
    r = copy.deepcopy(good)
    method = r["forecasts"]["methods"][2]
    method["available"] = False
    assert errors(r) != []
    method["unavailable_reason"] = "no creation cohort"
    method["by_window"] = {}
    method["horizons"] = {}
    r["forecasts"]["methods"][2]["components"] = {}
    # still invalid: the ranges, the gap and the plan still claim a fitted forecast
    assert errors(r) != []


def test_a_plan_is_unavailable_only_when_the_forecast_is_and_never_empty(good):
    # the short-history variants (above) are the only place a plan says "unavailable"
    assert errors(mutated(good, ["plan"], {"unavailable": "no creation cohort"})) != []
    assert errors(mutated(good, ["plan"], {})) != []


def test_an_adopted_hire_may_not_carry_a_note_variant_shape(good):
    r = copy.deepcopy(good)
    r["actions"]["close_the_fiscal_year_gap"]["hires"] = {"outcome": "x", "count": None}
    assert errors(r) != []


def test_the_committed_frontend_fixtures_for_an_unavailable_forecast_satisfy_the_contract():
    """frontend/src/screens/__tests__/fixtures are short-history reports (the variants
    'forecast unavailable' without and with a plan) with their paths scrubbed."""
    fixtures = Path("frontend/src/screens/__tests__/fixtures")
    for name, plan in (
        ("short-history.report.json", False),
        ("short-history-plan.report.json", True),
    ):
        r = json.loads((fixtures / name).read_text())
        assert errors(r) == []
        assert not r["forecasts"]["methods"][2]["available"]
        assert ("plan" in r) is plan

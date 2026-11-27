"""Goal 2B sections 11 and 12 end to end: the plan with ordered contributions,
two actions compared, and the solves checked by running their answers back
through the report."""

import shutil
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.tests.tieout_core import staffed
from engine.tieout_core.__main__ import main
from engine.tieout_core.report import build_report

AS_OF = staffed.AS_OF
DRAWS = 100
REST, TWELVE = "rest of fiscal year", "next twelve months"


def plan_file(tmp_path, doc, name="plan.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(doc))
    return path


PLAN = {
    "programmes": [
        {"name": "Referral programme", "pipeline": 2_000_000, "start": "2026-10"}
    ],
    "hires": [{"segment": "mid_market", "start": "2026-10", "count": 3}],
}


@pytest.fixture(scope="module")
def follows(tmp_path_factory):
    return staffed.write(tmp_path_factory.mktemp("f"), rep_rate=3.0, demand=0.5)


@pytest.fixture(scope="module")
def demand(tmp_path_factory):
    return staffed.write(tmp_path_factory.mktemp("d"), rep_rate=0.0, demand=18.0)


@pytest.fixture(scope="module")
def with_plan(follows, tmp_path_factory):
    path = plan_file(tmp_path_factory.mktemp("pl"), PLAN)
    return build_report(*follows, AS_OF, draws=DRAWS, plan_path=path)


def test_without_a_plan_there_is_no_section_11_and_the_actions_stand(follows):
    r = build_report(*follows, AS_OF, draws=DRAWS)
    assert "plan" not in r and "actions" in r and "required_pipeline" in r


def test_hires_come_first_in_the_plan_whatever_the_file_order(with_plan):
    items = with_plan["plan"]["items"]
    assert [i["kind"] for i in items] == [
        "hires",
        "programme",
    ]  # the file lists programmes first
    assert items[0]["label"] == "3 mid_market hires from 2026-10"


def test_contributions_are_incremental_and_sum_to_the_difference_exactly(with_plan):
    p = with_plan["plan"]
    for h in (REST, TWELVE):
        parts = [Decimal(i["contribution"][h]) for i in p["items"]]
        assert sum(parts) == Decimal(p["with_plan"][h]) - Decimal(p["baseline"][h])
        assert Decimal(p["difference"][h]) == sum(parts)
        assert all(x > 0 for x in parts)
    checks = {c["name"]: c for c in with_plan["verdicts"]["software_correct"]["checks"]}
    assert checks["plan contributions sum to the difference"]["passed"]


def test_the_plan_closes_part_of_the_gap_and_its_cost_is_the_entered_costs(with_plan):
    p = with_plan["plan"]
    fy = p["gap"]["fiscal_year"]
    assert Decimal(fy["gap_with_plan"]) < Decimal(fy["baseline_gap"])
    # 3 hires at 12,000 a month and 2,000,000 of pipeline at 0.05 a dollar
    hire_cost, prog_cost = (
        Decimal(i["cash_cost_in_twelve_months"]) for i in p["items"]
    )
    assert prog_cost == Decimal(100_000)
    assert (
        Decimal(30_000) * 12 * Decimal("0.9") < hire_cost <= Decimal(36_000) * 12
    )  # fewer than 36 AE-months: attrition
    assert Decimal(p["cash_cost_in_twelve_months"]) == hire_cost + prog_cost


def test_two_actions_are_compared_with_gain_per_dollar_and_rank(follows):
    r = build_report(*follows, AS_OF, draws=DRAWS)
    rows = {a["kind"]: a for a in r["actions"]["comparison"]}
    assert rows["hire"]["status"] == rows["programme"]["status"] == "valued"
    for a in rows.values():
        assert (
            Decimal(a["bookings_gained"][TWELVE])
            > Decimal(a["bookings_gained"][REST])
            > 0
        )
        assert a["starts_paying"] and Decimal(a["cash_cost_in_twelve_months"]) > 0
    assert sorted(a["rank"] for a in rows.values()) == [1, 2]
    best = max(rows.values(), key=lambda a: float(a["gain_per_dollar"]))
    assert best["rank"] == 1


def test_the_programme_solve_runs_back_through_the_report_to_the_cent(
    follows, tmp_path
):
    base = build_report(*follows, AS_OF, draws=DRAWS)
    closing = base["actions"]["close_the_fiscal_year_gap"]["programme"]
    assert closing["outcome"] == "feasible", closing
    dollars = Decimal(closing["dollars"])
    # the same programme as a plan item, starting next month through the fiscal year end
    path = plan_file(
        tmp_path,
        {
            "programmes": [
                {"name": "solve", "pipeline": str(dollars), "start": "2026-09"}
            ]
        },
    )
    again = build_report(*follows, AS_OF, draws=DRAWS, plan_path=path)
    gap = Decimal(again["plan"]["gap"]["fiscal_year"]["gap_with_plan"])
    assert abs(gap) <= Decimal(
        "0.05"
    )  # each month is shown to the cent; the solve is exact


def _with_target(tmp_path, follows, extra: Decimal):
    """The same company with its fiscal-year target moved to the baseline
    expectation plus ``extra``."""
    profile, data = follows
    base = build_report(profile, data, AS_OF, draws=DRAWS)
    fy = base["gap"]["fiscal_year"]
    target = (
        Decimal(fy["actual_to_date"]) + Decimal(fy["forecast_rest_of_year"]) + extra
    )
    out = tmp_path / "p"
    shutil.copytree(profile, out)
    doc = yaml.safe_load((out / "targets.yaml").read_text())
    for q in doc["quarterly_targets"]:
        doc["quarterly_targets"][q] = {"bookings_target": float(target / 4)}
    (out / "targets.yaml").write_text(yaml.safe_dump(doc))
    return out, data


def test_the_hires_solve_is_the_smallest_whole_number_and_one_fewer_does_not_close(
    follows, tmp_path
):
    base = build_report(*follows, AS_OF, draws=DRAWS)
    one = Decimal(
        next(a for a in base["actions"]["comparison"] if a["kind"] == "hire")[
            "bookings_gained"
        ][REST]
    )
    profile, data = _with_target(tmp_path, follows, extra=one * Decimal("1.5"))
    r = build_report(profile, data, AS_OF, draws=DRAWS)
    hires = r["actions"]["close_the_fiscal_year_gap"]["hires"]
    assert hires["outcome"] == "feasible" and hires["count"] == 2, hires
    assert Decimal(hires["overshoot"]) > 0
    assert Decimal(hires["fiscal_year_bookings_one_fewer"]) < Decimal(
        r["gap"]["fiscal_year"]["target"]
    )
    # and as plans: two hires starting next month close the gap, one does not
    for n, closes in ((2, True), (1, False)):
        path = plan_file(
            tmp_path,
            {"hires": [{"segment": "mid_market", "start": "2026-09", "count": n}]},
            f"n{n}.yaml",
        )
        gap = Decimal(
            build_report(profile, data, AS_OF, draws=DRAWS, plan_path=path)["plan"][
                "gap"
            ]["fiscal_year"]["gap_with_plan"]
        )
        assert (gap <= Decimal("0.05")) is closes, (n, gap)
    checks = {c["name"]: c for c in r["verdicts"]["software_correct"]["checks"]}
    assert checks["hires solve returns the smallest whole number that closes the gap"][
        "passed"
    ]


def test_an_unreachable_hires_bound_is_reported_with_the_best_case(follows, tmp_path):
    profile, data = _with_target(tmp_path, follows, extra=Decimal(10) ** 9)
    h = build_report(profile, data, AS_OF, draws=DRAWS)["actions"][
        "close_the_fiscal_year_gap"
    ]["hires"]
    assert h["outcome"] == "unreachable" and h["count"] is None
    assert h["bound_basis"].startswith("the most the company has started")


def test_when_capacity_is_not_shown_hiring_is_unsupported_and_not_valued(
    demand, tmp_path
):
    path = plan_file(tmp_path, PLAN)
    r = build_report(*demand, AS_OF, draws=DRAWS, plan_path=path)
    hires, programme = r["plan"]["items"]
    assert hires["valued"] is False and hires["contribution"] is None
    assert "unsupported by this history" in hires["note"]
    assert programme["valued"] and Decimal(programme["contribution"][TWELVE]) > 0
    # the plan's difference is the programme's alone
    assert r["plan"]["difference"] == r["plan"]["contributions_total"]
    rows = {a["kind"]: a for a in r["actions"]["comparison"]}
    assert rows["hire"]["status"] == "unsupported by this history"
    assert rows["hire"]["rank"] is None and rows["hire"]["bookings_gained"] is None
    assert rows["programme"]["status"] == "valued" and rows["programme"]["rank"] == 1
    assert (
        r["actions"]["close_the_fiscal_year_gap"]["hires"]["outcome"]
        == "unsupported by this history"
    )
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"


def test_a_missing_cost_is_cost_not_entered_and_the_action_is_not_ranked(
    follows, tmp_path
):
    profile, data = follows
    bare = tmp_path / "profile"
    shutil.copytree(profile, bare)
    doc = yaml.safe_load((bare / "capacity.yaml").read_text())
    del doc["costs"]["loaded_cost_per_ae_month"]
    (bare / "capacity.yaml").write_text(yaml.safe_dump(doc))
    r = build_report(bare, data, AS_OF, draws=DRAWS)
    rows = {a["kind"]: a for a in r["actions"]["comparison"]}
    assert (
        rows["hire"]["status"] == "valued"
        and rows["hire"]["cost_status"] == "cost not entered"
    )
    assert rows["hire"]["gain_per_dollar"] is None and rows["hire"]["rank"] is None
    assert rows["hire"]["not_ranked_because"] == "cost not entered"
    assert rows["programme"]["rank"] == 1


def test_a_plan_that_repeats_a_signed_hire_is_refused(follows, tmp_path):
    profile, data = follows
    signed = tmp_path / "data"
    shutil.copytree(data, signed)
    with (signed / "team_members.csv").open("a") as fh:
        fh.write("SIGNED-1,Pat,ae,mid_market,2026-10-12,,true,,1000000\n")
    path = plan_file(
        tmp_path, {"hires": [{"segment": "mid_market", "start": "2026-10", "count": 1}]}
    )
    with pytest.raises(ValueError, match="repeats a signed hire"):
        build_report(profile, signed, AS_OF, draws=DRAWS, plan_path=path)
    out = tmp_path / "out"
    assert main(["report", "--profile", str(profile), "--data", str(signed), "--as-of", AS_OF.isoformat(),
                 "--out", str(out), "--plan", str(path)]) == 2  # fmt: skip


def test_the_command_takes_a_plan_and_writes_sections_11_and_12(follows, tmp_path):
    out = tmp_path / "out"
    path = plan_file(tmp_path, PLAN)
    code = main(["report", "--profile", str(follows[0]), "--data", str(follows[1]), "--as-of",
                 AS_OF.isoformat(), "--out", str(out), "--plan", str(path), "--draws", "100"])  # fmt: skip
    assert code == 0
    md = (out / "report.md").read_text()
    assert "## 11. The plan" in md and "## 12. Two actions, compared" in md


@pytest.mark.parametrize(
    "company", ["sprout-labs", "sapling-industries", "mighty-oak-holdings"]
)
def test_every_demo_company_runs_with_and_without_its_plan(company):
    profile = Path(f"engine/config/profiles/{company}")
    data = Path(f"engine/data-v2/{company}")
    without = build_report(profile, data, AS_OF, draws=DRAWS)
    with_ = build_report(
        profile, data, AS_OF, draws=DRAWS, plan_path=profile / "plan.yaml"
    )
    for r in (without, with_):
        assert r["verdicts"]["software_correct"]["verdict"] == "yes", [
            c for c in r["verdicts"]["software_correct"]["checks"] if not c["passed"]
        ]
        for key in (
            "roster_capacity",
            "quota_productivity",
            "required_pipeline",
            "actions",
        ):
            assert key in r
    assert "plan" not in without and "plan" in with_
    assert with_["plan"]["difference"] == with_["plan"]["contributions_total"]

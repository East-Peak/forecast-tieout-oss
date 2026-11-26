import json
import shutil
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.tieout_core.report import SECTIONS, build_report, render_markdown

PROFILE = Path("engine/config/profiles/sprout-labs")
DATA = Path("engine/data-v2/sprout-labs")
AS_OF = date(2026, 8, 31)
DRAWS = 300


@pytest.fixture(scope="module")
def report():
    return build_report(PROFILE, DATA, AS_OF, draws=DRAWS)


def _profile_with_targets(tmp_path, value) -> Path:
    path = tmp_path / "profile"
    shutil.copytree(PROFILE, path)
    targets = yaml.safe_load((path / "targets.yaml").read_text())
    for q in targets["quarterly_targets"].values():
        q["bookings_target"] = value
    (path / "targets.yaml").write_text(yaml.safe_dump(targets))
    return path


def test_sections_come_in_order(report):
    assert list(report)[: len(SECTIONS) + 1] == ["inputs", *SECTIONS]
    assert SECTIONS == (
        "reconciliation", "history", "forecasts", "rates", "gap", "backtest", "verdicts")  # fmt: skip


def test_reconciliation_ties(report):
    r = report["reconciliation"]
    assert all(c["passed"] for c in r["checks"])
    assert sum(Decimal(v) for v in r["bookings_by_month"].values()) == Decimal(
        r["bookings_fytd"]
    )
    assert r["included_rows"] + len(r["exclusions"]) == r["source_rows"]


def test_three_forecasts_monthly_to_year_end_with_parts_apart(report):
    f = report["forecasts"]
    assert f["windows"] == ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01"]
    methods = {m["method"]: m for m in f["methods"]}
    assert set(methods) == {
        "trailing run-rate",
        "stage-weighted pipeline",
        "fitted model",
    }
    assert set(methods["fitted model"]["components"]) == {
        "existing pipeline",
        "future pipeline",
    }
    assert set(methods["stage-weighted pipeline"]["components"]) == {
        "existing pipeline",
        "future pipeline",
    }
    assert set(f["fitted_ranges"]["by_window"]) == set(f["windows"])


def test_every_rate_once_with_its_provenance(report):
    rates = report["rates"]
    names = [r["name"] for r in rates]
    assert len(names) == len(set(names))
    for r in rates:
        assert set(r) >= {
            "value",
            "definition",
            "numerator",
            "denominator",
            "cohort",
            "horizon",
            "sample_size",
            "source",
        }
        assert r["source"] in ("fitted", "entered", "default")
    assert {
        "stage_probability:S1",
        "win_within_horizon:S1",
        "trailing_bookings_per_day",
        "horizon_days",
    } <= set(names)


def test_gap_by_quarter_is_target_less_actual_less_forecast(report):
    quarters = report["gap"]["quarters"]
    assert [q["quarter"] for q in quarters] == ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"]
    for q in quarters:
        assert Decimal(q["gap"]) == Decimal(q["target"]) - Decimal(
            q["actual"]
        ) - Decimal(q["forecast"])
    assert quarters[0]["status"] == "closed" and Decimal(quarters[0]["forecast"]) == 0
    fy = report["gap"]["fiscal_year"]
    assert Decimal(fy["target"]) == sum(Decimal(q["target"]) for q in quarters)


def test_lever_is_one_of_three_outcomes(report):
    lever = report["gap"]["lever"]
    assert lever["outcome"] in (
        "already covered",
        "feasible",
        "unreachable within bounds",
    )
    assert "not operationally" in lever["meaning"]


def test_backtest_reports_each_horizon(report):
    b = report["backtest"]
    assert [h["horizon_months"] for h in b["horizons"]] == [1, 3, 6]
    assert all(h["folds"] > 0 for h in b["horizons"])


def test_two_verdicts_stated_separately(report):
    v = report["verdicts"]
    assert v["software_correct"]["verdict"] == "yes", [
        c for c in v["software_correct"]["checks"] if not c["passed"]
    ]
    assert v["forecast_better_than_baselines"]["verdict"] in (
        "yes",
        "no",
        "not enough history to say",
    )


def test_report_is_reproducible():
    a = build_report(PROFILE, DATA, AS_OF, draws=50)
    b = build_report(PROFILE, DATA, AS_OF, draws=50)
    assert json.dumps(a) == json.dumps(b)


def test_markdown_has_the_seven_sections(report):
    md = render_markdown(report)
    for i, title in enumerate(["Reconciliation", "What the history can support", "Three forecasts",
                               "Every rate once", "The gap", "Back-test", "Verdicts"], start=1):  # fmt: skip
        assert f"## {i}. {title}" in md


def test_infeasible_target_is_unreachable(tmp_path):
    r = build_report(_profile_with_targets(tmp_path, 10**10), DATA, AS_OF, draws=50)
    assert r["gap"]["lever"]["outcome"] == "unreachable within bounds"
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"


def test_low_target_is_already_covered(tmp_path):
    r = build_report(_profile_with_targets(tmp_path, 1), DATA, AS_OF, draws=50)
    assert r["gap"]["lever"]["outcome"] == "already covered"


def test_without_observations_the_report_says_what_it_cannot_do(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(DATA, data)
    (data / "deal_observations.csv").unlink()
    r = build_report(PROFILE, data, AS_OF, draws=50)
    assert any("deal_observations.csv" in x for x in r["history"]["limitations"])
    assert (
        r["verdicts"]["forecast_better_than_baselines"]["verdict"]
        == "not enough history to say"
    )


def test_as_of_on_the_last_day_of_the_year_leaves_nothing_to_forecast():
    r = build_report(PROFILE, DATA, date(2027, 1, 31), draws=50)
    assert r["forecasts"]["windows"] == []
    assert r["gap"]["lever"]["outcome"] in (
        "already covered",
        "unreachable within bounds",
    )


def test_as_of_before_the_files_last_entry_is_refused():
    with pytest.raises(ValueError, match="after the as-of date"):
        build_report(PROFILE, DATA, date(2026, 8, 14), draws=50)


def test_command_writes_both_files(tmp_path):
    out = tmp_path / "report"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "engine.tieout_core",
            "report",
            "--profile",
            str(PROFILE),
            "--data",
            str(DATA),
            "--as-of",
            "2026-08-31",
            "--out",
            str(out),
            "--draws",
            "50",
        ],  # fmt: skip
        check=True,
    )
    assert (
        json.loads((out / "report.json").read_text())["inputs"]["as_of"] == "2026-08-31"
    )
    assert (out / "report.md").read_text().startswith("# Forecast tieout")


@pytest.mark.parametrize(
    "company", ["sprout-labs", "sapling-industries", "mighty-oak-holdings"]
)
def test_every_demo_company_gets_a_complete_self_consistent_report(company):
    r = build_report(
        Path(f"engine/config/profiles/{company}"),
        Path(f"engine/data-v2/{company}"),
        AS_OF,
        draws=500,
    )
    failed = [c for c in r["verdicts"]["software_correct"]["checks"] if not c["passed"]]
    assert failed == []
    md = render_markdown(r)
    assert all(f"## {i}. " in md for i in range(1, 8))

"""Goal 2A, lesson 3 (horizon): every forecast, gap and action is shown for two
windows, the rest of the fiscal year and the twelve months after the as-of. A
gap is shown only where a target exists; beyond the last target the report
shows bookings alone."""

import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.tieout_core.load import load_profile
from engine.tieout_core.report import NEXT_12, REST_OF_FY, build_report

PROFILE = Path("engine/config/profiles/sprout-labs")
DATA = Path("engine/data-v2/sprout-labs")
AS_OF = date(2026, 8, 31)
FY_MONTHS = ["2026-09", "2026-10", "2026-11", "2026-12", "2027-01"]
LATER = ["2027-02", "2027-03", "2027-04", "2027-05", "2027-06", "2027-07", "2027-08"]


@pytest.fixture(scope="module")
def report():
    return build_report(PROFILE, DATA, AS_OF, draws=200)


def _with_next_year_targets(tmp_path) -> Path:
    path = tmp_path / "profile"
    shutil.copytree(PROFILE, path)
    doc = yaml.safe_load((path / "targets.yaml").read_text())
    doc["quarterly_targets"]["Q1FY27"] = {"bookings_target": 2_500_000}
    doc["quarterly_targets"]["Q2FY27"] = {"bookings_target": 2_600_000}
    (path / "targets.yaml").write_text(yaml.safe_dump(doc))
    return path


def test_months_run_twelve_months_past_the_as_of(report):
    assert report["forecasts"]["windows"] == FY_MONTHS + LATER


def test_each_method_totals_both_windows(report):
    for m in report["forecasts"]["methods"]:
        months = m["by_window"]
        h = m["horizons"]
        assert set(h) == {REST_OF_FY, NEXT_12}
        assert Decimal(h[REST_OF_FY]) == sum(Decimal(months[w]) for w in FY_MONTHS)
        assert Decimal(h[NEXT_12]) == sum(Decimal(months[w]) for w in FY_MONTHS + LATER)


def test_ranges_cover_both_windows_and_twelve_months_is_unvalidated(report):
    fr = report["forecasts"]["fitted_ranges"]
    assert set(fr["horizons"]) == {REST_OF_FY, NEXT_12}
    assert fr["horizons"][NEXT_12]["status"].startswith("unvalidated")


def test_twelve_month_gap_stops_at_the_last_target(report):
    t = report["gap"]["next_twelve_months"]
    assert t["targets_through"] == "2027-01-31"
    quarters = {q["quarter"]: q for q in report["gap"]["quarters"]}
    open_q = [quarters["Q3FY26"], quarters["Q4FY26"]]
    assert Decimal(t["target"]) == sum(Decimal(q["target"]) for q in open_q)
    assert Decimal(t["actual"]) == sum(Decimal(q["actual"]) for q in open_q)
    fitted = next(
        m for m in report["forecasts"]["methods"] if m["method"] == "fitted model"
    )
    assert Decimal(t["forecast"]) == sum(
        Decimal(fitted["by_window"][w]) for w in FY_MONTHS
    )
    assert Decimal(t["gap"]) == Decimal(t["target"]) - Decimal(t["actual"]) - Decimal(
        t["forecast"]
    )
    assert t["untargeted"]["months"] == LATER
    assert Decimal(t["untargeted"]["forecast"]) == sum(
        Decimal(fitted["by_window"][w]) for w in LATER
    )
    assert "bookings alone" in t["untargeted"]["note"]


def test_lever_reports_bookings_gained_in_both_windows(report):
    lever = report["gap"]["lever"]
    if lever["outcome"] != "feasible":
        pytest.skip("demo target not feasible here")
    gained = lever["bookings_gained"]
    assert (
        Decimal(gained[NEXT_12]) > Decimal(gained[REST_OF_FY]) > 0
    )  # late pipeline keeps booking


def test_later_targets_extend_the_gap_and_get_their_own_lever(tmp_path):
    profile = _with_next_year_targets(tmp_path)
    assert load_profile(profile).later_targets == {
        "Q1FY27": Decimal(2_500_000),
        "Q2FY27": Decimal(2_600_000),
    }
    r = build_report(profile, DATA, AS_OF, draws=100)
    quarters = [q["quarter"] for q in r["gap"]["quarters"]]
    assert quarters == ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26", "Q1FY27", "Q2FY27"]
    assert all(q["status"] == "not started" for q in r["gap"]["quarters"][4:])
    t = r["gap"]["next_twelve_months"]
    assert t["targets_through"] == "2027-07-31"
    assert t["untargeted"]["months"] == ["2027-08"]
    assert Decimal(r["gap"]["fiscal_year"]["target"]) == Decimal(
        8_000_000
    )  # FY target unchanged
    lever12 = r["gap"]["lever_next_twelve_months"]
    assert lever12["outcome"] in (
        "already covered",
        "feasible",
        "unreachable within bounds",
    )
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"
    names = {c["name"] for c in r["verdicts"]["software_correct"]["checks"]}
    assert "twelve-month lever agrees with forward function" in names


def test_year_end_as_of_still_forecasts_the_next_twelve_months():
    r = build_report(PROFILE, DATA, date(2027, 1, 31), draws=20)
    assert len(r["forecasts"]["windows"]) == 12
    fitted = next(m for m in r["forecasts"]["methods"] if m["method"] == "fitted model")
    if fitted["available"]:
        assert Decimal(fitted["horizons"][REST_OF_FY]) == 0
    t = r["gap"]["next_twelve_months"]
    assert t["targets_through"] is None
    assert r["gap"]["lever_next_twelve_months"]["outcome"] == "no target in this window"

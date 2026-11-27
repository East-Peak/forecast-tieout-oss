"""Goal 3A review: the plan section carries with-plan figures by month and by quarter, with ranges,
the expected year and the twelve-month forecast, so a screen shows a scenario without computing."""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from engine.tieout_core.report import build_report

AS_OF = __import__("datetime").date(2026, 8, 31)
REST, TWELVE = "rest of fiscal year", "next twelve months"
D = Decimal


def make(company, tmp_path, doc=None):
    profile = Path(f"engine/config/profiles/{company}")
    plan = profile / "plan.yaml"
    if doc is not None:
        plan = tmp_path / "plan.yaml"
        plan.write_text(yaml.safe_dump(doc))
    return build_report(
        profile, Path(f"engine/data-v2/{company}"), AS_OF, draws=200, plan_path=plan
    )


@pytest.fixture(scope="module", params=["sprout-labs", "mighty-oak-holdings"])
def planned(request, tmp_path_factory):
    return make(request.param, tmp_path_factory.mktemp("p"))


def test_with_plan_months_cover_every_window_and_add_up_to_the_two_totals(planned):
    p = planned["plan"]
    months = p["with_plan_by_window"]
    assert list(months) == planned["forecasts"]["windows"]
    horizons = planned["forecasts"]["horizon_windows"]
    for name, (first, last) in ((REST, horizons[REST]), (TWELVE, horizons[TWELVE])):
        span = [m for m in months if first <= m <= last]
        assert sum(D(months[m]) for m in span) == D(p["with_plan"][name])


def test_the_expected_year_is_booked_to_date_plus_the_with_plan_rest_of_year(planned):
    p, g = planned["plan"], planned["gap"]["fiscal_year"]
    assert D(p["expected_fiscal_year"]) == D(g["actual_to_date"]) + D(
        p["with_plan"][REST]
    )
    assert D(p["gap"]["fiscal_year"]["gap_with_plan"]) == D(g["target"]) - D(
        p["expected_fiscal_year"]
    )


def test_with_plan_quarters_tie_to_the_months_and_the_targets(planned):
    p = planned["plan"]
    quarters = p["with_plan_quarters"]
    assert [q["quarter"] for q in quarters] == [
        q["quarter"] for q in planned["gap"]["quarters"]
    ]
    for q, base in zip(quarters, planned["gap"]["quarters"]):
        assert (q["target"], q["actual"], q["status"]) == (
            base["target"],
            base["actual"],
            base["status"],
        )
        assert D(q["expected"]) == D(q["actual"]) + D(q["forecast"])
        assert D(q["gap"]) == D(q["target"]) - D(q["expected"])
        low, high = map(D, q["expected_range80"])
        assert low <= high
        if q["status"] == "closed":
            assert D(q["forecast"]) == 0


def test_with_plan_ranges_by_month_and_for_the_year_are_ordered(planned):
    r = planned["plan"]["ranges"]
    assert list(r["by_window"]) == planned["forecasts"]["windows"]
    for s in r["by_window"].values():
        assert (
            D(s["range95"][0])
            <= D(s["range80"][0])
            <= D(s["range80"][1])
            <= D(s["range95"][1])
        )
    lo, hi = map(D, r["fiscal_year_expected_range95"])
    lo80, hi80 = map(D, r["fiscal_year_expected_range80"])
    assert lo <= lo80 <= hi80 <= hi


def test_the_targeted_forecast_with_plan_closes_the_window_gap(planned):
    n = planned["plan"]["gap"]["next_twelve_months"]
    if n is None:
        pytest.skip("no target in the window")
    assert D(n["gap_with_plan"]) == D(n["target"]) - D(n["actual_to_date"]) - D(
        n["forecast_with_plan"]
    )


def test_a_plan_that_adds_nothing_changes_no_point_figure(tmp_path):
    r = make("sprout-labs", tmp_path, {"hires": [], "programmes": []})
    fitted = next(m for m in r["forecasts"]["methods"] if m["method"] == "fitted model")
    p = r["plan"]
    assert p["with_plan_by_window"] == fitted["by_window"]
    assert p["with_plan"] == p["baseline"]
    assert p["expected_fiscal_year"] == r["gap"]["fiscal_year"]["expected"]
    for q, base in zip(p["with_plan_quarters"], r["gap"]["quarters"]):
        assert (q["forecast"], q["expected"], q["gap"]) == (
            base["forecast"],
            base["expected"],
            base["gap"],
        )

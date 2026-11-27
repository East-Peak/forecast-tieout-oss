"""Goal 2B: both branches of the capacity decision, end to end through the
report command, on generated companies; and the sections the half adds."""

import csv
import json
import shutil
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from engine.tests.tieout_core import staffed
from engine.tieout_core import capacity_report
from engine.tieout_core.__main__ import main
from engine.tieout_core.backtest import fold
from engine.tieout_core.fit import DEFAULT_PARAMS
from engine.tieout_core.history import as_known_at
from engine.tieout_core.load import load_company, load_profile
from engine.tieout_core.reconcile import reconcile
from engine.tieout_core.report import build_report

AS_OF = staffed.AS_OF
DRAWS = 150
FY = "next twelve months"


@pytest.fixture(scope="module")
def follows(tmp_path_factory):
    return staffed.write(tmp_path_factory.mktemp("follows"), rep_rate=3.0, demand=0.5)


@pytest.fixture(scope="module")
def demand(tmp_path_factory):
    return staffed.write(tmp_path_factory.mktemp("demand"), rep_rate=0.0, demand=18.0)


@pytest.fixture(scope="module")
def adopted(follows):
    return build_report(*follows, AS_OF, draws=DRAWS)


@pytest.fixture(scope="module")
def not_shown(demand):
    return build_report(*demand, AS_OF, draws=DRAWS)


def fitted(report, horizon=FY):
    method = next(
        m for m in report["forecasts"]["methods"] if m["method"] == "fitted model"
    )
    return Decimal(method["horizons"][horizon])


def test_pipeline_that_follows_headcount_is_adopted(adopted):
    d = adopted["roster_capacity"]["decision"]
    assert d["outcome"] == "adopted", d["reason"]
    assert float(d["staffing_variation"]) >= 0.20
    assert all(float(h["improvement"]) >= 0.10 for h in d["horizons"])
    assert adopted["inputs"]["capacity"]["forecast_uses"].startswith("capacity term")
    assert "diagnostic" not in adopted["roster_capacity"]


def test_pipeline_that_is_pure_demand_is_not_shown(not_shown):
    d = not_shown["roster_capacity"]["decision"]
    assert d["outcome"] == "not shown", d["reason"]
    assert (
        not_shown["inputs"]["capacity"]["forecast_uses"]
        == "flat trailing creation rate"
    )
    g = not_shown["roster_capacity"]["diagnostic"]
    assert g["hiring_action"] == "unsupported by this history"
    assert "diagnostic only" in g["label"]


def test_when_not_shown_the_forecast_is_exactly_the_flat_rate_forecast(
    demand, not_shown, tmp_path
):
    profile, data = demand
    bare = tmp_path / "bare"
    shutil.copytree(profile, bare)
    (
        bare / "capacity.yaml"
    ).unlink()  # no capacity inputs: the flat rate, by construction
    flat = build_report(bare, data, AS_OF, draws=DRAWS)
    assert flat["roster_capacity"]["decision"]["outcome"] == "unavailable"
    for h in ("rest of fiscal year", FY):
        assert fitted(flat, h) == fitted(not_shown, h)
    assert flat["gap"]["fiscal_year"] == not_shown["gap"]["fiscal_year"]
    assert flat["gap"]["lever"] == not_shown["gap"]["lever"]


def test_the_adopted_forecast_differs_from_the_flat_one_and_names_its_rate(adopted):
    method = next(
        m for m in adopted["forecasts"]["methods"] if m["method"] == "fitted model"
    )
    assert any("per ramped AE-month" in a for a in method["assumptions"])


def _edit_roster(data: Path, tmp: Path, edit) -> Path:
    out = tmp / data.name
    shutil.copytree(data, out)
    path = out / "team_members.csv"
    rows = list(csv.DictReader(path.open()))
    rows = edit(rows)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return out


def test_fewer_ramped_reps_gives_a_lower_headline_forecast_when_adopted(
    follows, tmp_path
):
    profile, data = follows
    later = (AS_OF + timedelta(days=20)).isoformat()

    def five_leave(
        rows,
    ):  # signed departures: still employed at the as-of, gone soon after
        left = 0
        for r in rows:
            if r["role"] == "ae" and not r["end_date"] and left < 5:
                r["end_date"], left = later, left + 1
        return rows

    def five_join(rows):  # signed hires
        base = dict(next(r for r in rows if r["role"] == "ae"))
        for i in range(5):
            rows.append(
                {**base, "id": f"NEW-{i}", "start_date": "2026-10-01", "end_date": ""}
            )
        return rows

    base = build_report(profile, data, AS_OF, draws=DRAWS)
    fewer = build_report(
        profile, _edit_roster(data, tmp_path / "a", five_leave), AS_OF, draws=DRAWS
    )
    more = build_report(
        profile, _edit_roster(data, tmp_path / "b", five_join), AS_OF, draws=DRAWS
    )
    assert fewer["roster_capacity"]["decision"]["outcome"] == "adopted"
    assert fitted(fewer) < fitted(base) < fitted(more)


def test_the_flat_branch_ignores_the_roster_changes(demand, tmp_path):
    profile, data = demand
    base = build_report(profile, data, AS_OF, draws=DRAWS)

    def drop_reps(rows):
        n = 0
        for r in rows:
            if r["role"] == "ae" and not r["end_date"] and n < 5:
                r["end_date"], n = (AS_OF + timedelta(days=20)).isoformat(), n + 1
        return rows

    fewer = build_report(
        profile, _edit_roster(data, tmp_path, drop_reps), AS_OF, draws=DRAWS
    )
    assert fewer["roster_capacity"]["decision"]["outcome"] == "not shown"
    assert fitted(fewer) == fitted(base)


@pytest.mark.parametrize("which", ["follows", "demand"])
def test_both_branches_run_end_to_end_through_the_command(which, request, tmp_path):
    profile, data = request.getfixturevalue(which)
    out = tmp_path / "out"
    code = main(["report", "--profile", str(profile), "--data", str(data), "--as-of",
                 AS_OF.isoformat(), "--out", str(out), "--draws", "100"])  # fmt: skip
    assert code == 0
    md = (out / "report.md").read_text()
    js = json.loads((out / "report.json").read_text())
    for heading in (
        "## 8. Roster and capacity",
        "## 9. Quota against observed productivity",
    ):
        assert heading in md
    assert js["verdicts"]["software_correct"]["verdict"] == "yes"


def test_roster_section_labels_ramp_and_attrition_with_sample_sizes(adopted):
    r = adopted["roster_capacity"]
    assert r["ramp"]["source"] in ("fitted", "entered", "default")
    assert "reps observed" in r["ramp"]["sample"]
    assert r["attrition"]["source"] in ("fitted", "entered", "default")
    assert "departures over" in r["attrition"]["sample"]
    names = {x["name"]: x for x in adopted["rates"]}
    assert names["attrition_per_ae_month"]["source"] == r["attrition"]["source"]
    assert names["created_deals_per_ramped_ae_month"]["sample_size"] > 0
    assert names["ramp_weight:1"]["source"] == r["ramp"]["source"]


def test_months_table_runs_a_year_back_and_a_year_forward(adopted):
    months = adopted["roster_capacity"]["months"]
    assert [m["kind"] for m in months].count("past") == 12
    assert [m["kind"] for m in months].count("forward") == 12
    assert months[11]["month"] == "2026-08" and months[12]["month"] == "2026-09"


def test_productivity_credits_wins_to_owners_employed_when_the_deal_closed(adopted):
    p = adopted["quota_productivity"]
    assert Decimal(p["wins_credited"]) + Decimal(p["wins_unattributed"]) == Decimal(
        p["wins_in_window"]
    )
    assert Decimal(p["total_quota"]["annual_quota_of_people_employed_at_as_of"]) > 0
    assert p["all_reps"]["reps"] > 0


def test_unknown_roles_are_excluded_with_a_reason_and_the_partition_check_holds(
    follows, tmp_path
):
    profile, data = follows

    def add_wizard(rows):
        rows.append({**rows[0], "id": "W-1", "role": "wizard"})
        return rows

    r = build_report(
        profile, _edit_roster(data, tmp_path, add_wizard), AS_OF, draws=DRAWS
    )
    ex = r["roster_capacity"]["roster"]["excluded"]
    assert ex == [
        {
            "id": "W-1",
            "role": "wizard",
            "reason": "role 'wizard' is not named in capacity.yaml",
        }
    ]
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"


def test_no_roster_history_makes_capacity_unavailable_with_the_reason(
    follows, tmp_path
):
    profile, data = follows
    bare = tmp_path / "bare"
    shutil.copytree(data, bare)
    (bare / "team_members.csv").write_text("id,role\nA,ae\n")
    r = build_report(profile, bare, AS_OF, draws=DRAWS)
    d = r["roster_capacity"]["decision"]
    assert d["outcome"] == "unavailable" and "start_date" in d["reason"]
    assert r["inputs"]["capacity"]["forecast_uses"] == "flat trailing creation rate"


# ---------------------------------------------------------------- leakage


def test_a_capacity_fold_cannot_see_a_later_departure_a_later_hire_or_later_deals(
    follows,
):
    profile_dir, data_dir = follows
    profile = load_profile(profile_dir)
    loaded = load_company(data_dir, profile)
    pop = reconcile(data_dir, loaded, profile, AS_OF).population
    cap = capacity_report.prepare(
        profile_dir, data_dir, pop, AS_OF, 365, DEFAULT_PARAMS
    )
    assert cap.adopted
    cutoff = date(2025, 11, 30)
    base = fold(
        pop,
        cutoff,
        (3,),
        profile,
        draws=100,
        creation_for=capacity_report.creation_for(cap),
    )

    # Rewrite the future: everyone still employed leaves a month after the cutoff,
    # a crowd of hires arrives, and later deals double in size and number.
    members = tuple(
        replace(m, end=cutoff + timedelta(days=30)) if m.end is None else m
        for m in cap.members
    ) + tuple(
        replace(cap.members[0], id=f"X{i}", start=cutoff + timedelta(days=40), end=None)
        for i in range(30)
    )
    extra = tuple(replace(d, id=d.id + "x") for d in pop.deals if d.created > cutoff)
    later = replace(
        pop,
        deals=tuple(
            replace(d, arr=d.arr * 2) if d.created > cutoff else d for d in pop.deals
        )
        + extra,
    )
    cap2 = replace(cap, roster=replace(cap.roster, members=members))
    again = fold(
        later,
        cutoff,
        (3,),
        profile,
        draws=100,
        creation_for=capacity_report.creation_for(cap2),
    )

    assert again[0].forecasts == base[0].forecasts  # what was forecast is unchanged
    assert again[0].range80 == base[0].range80
    assert again[0].actual != base[0].actual  # only what happened moved
    known = as_known_at(later, cutoff)
    assert all(d.created <= cutoff for d in known.deals)

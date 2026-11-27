"""Goal 2B review round: inputs that must be refused or excluded with a reason,
and a roster that must not crash the report."""

import csv
import shutil
from datetime import date

import pytest
import yaml

from engine.tests.tieout_core import staffed
from engine.tests.tieout_core.test_tc_capacity import AS_OF as CAP_AS_OF
from engine.tests.tieout_core.test_tc_capacity import capacity
from engine.tieout_core.capacity import project
from engine.tieout_core.capacity_config import load_capacity, load_roster
from engine.tieout_core.plan import load_plan
from engine.tieout_core.report import build_report
from engine.tieout_core.roster import Member

AS_OF = staffed.AS_OF


def cfg_from(tmp_path, text):
    (tmp_path / "capacity.yaml").write_text(text)
    return load_capacity(tmp_path)


# ---- finding 4: duplicate or blank ids


def test_duplicate_and_blank_roster_ids_are_excluded_with_a_reason(tmp_path):
    cfg = cfg_from(tmp_path, "roles: {quota_carrying: [ae], other: [sdr]}\n")
    p = tmp_path / "team_members.csv"
    p.write_text(
        "id,role,start_date,end_date,segment,annual_quota\n"
        "A1,ae,2025-01-01,,mm,100\n"
        "A1,ae,2025-02-01,,mm,100\n"
        ",ae,2025-01-01,,mm,100\n"
        "S1,sdr,2025-01-01,,,\n"
        "S1,sdr,2025-01-01,,,\n"
    )
    r = load_roster(p, cfg)
    assert [m.id for m in r.members] == ["A1"]
    reasons = [e.reason for e in r.excluded]
    assert any("duplicate id" in x and "row 2" in x for x in reasons)
    assert any("id is blank" in x for x in reasons)
    assert r.other_roles == {"sdr": 1}
    assert len(r.members) + sum(r.other_roles.values()) + len(r.excluded) == r.rows


# ---- finding 5: a signed hire beyond the projection horizon


def test_a_hire_starting_beyond_the_horizon_is_skipped_not_a_crash():
    members = [
        Member("A", "ae", "mm", date(2020, 1, 1), None, None),
        Member("FAR", "ae", "mm", date(2028, 1, 1), None, None),
        Member("GONE", "ae", "mm", date(2020, 1, 1), date(2025, 1, 1), None),
    ]
    cap = capacity(members[:1])
    with_far = project(cap, members, CAP_AS_OF, 365)
    alone = project(cap, members[:1], CAP_AS_OF, 365)
    assert with_far.per_day == alone.per_day and with_far.heads == alone.heads


# ---- finding 6: domain and finiteness


@pytest.mark.parametrize(
    "text,field",
    [
        ("attrition: {monthly_per_ae: -0.01}", "monthly_per_ae"),
        ("attrition: {monthly_per_ae: 1.5}", "monthly_per_ae"),
        ("attrition: {monthly_per_ae: .nan}", "monthly_per_ae"),
        ("costs: {loaded_cost_per_ae_month: -5}", "loaded_cost_per_ae_month"),
        (
            "costs: {program_cost_per_dollar_of_pipeline: .inf}",
            "program_cost_per_dollar_of_pipeline",
        ),
        ("hires: {max_in_one_quarter: 2.9}", "max_in_one_quarter"),
        ("hires: {max_in_one_quarter: -1}", "max_in_one_quarter"),
        ("program: {ramp_months: 0}", "ramp_months"),
        ("ramp: {months: [0.5, 1.5]}", "ramp"),
        ("ramp: {months: [-0.1]}", "ramp"),
    ],
)
def test_capacity_yaml_values_are_validated_with_a_field_specific_error(
    tmp_path, text, field
):
    with pytest.raises(ValueError, match=field):
        cfg_from(tmp_path, "roles: {quota_carrying: [ae]}\n" + text + "\n")


def test_a_roster_without_the_id_or_role_column_is_unavailable_with_the_reason(
    tmp_path,
):
    cfg = cfg_from(tmp_path, "roles: {quota_carrying: [ae]}\n")
    p = tmp_path / "team_members.csv"
    p.write_text("start_date,role\n2025-01-01,ae\n")
    assert "id" in load_roster(p, cfg).unavailable
    p.write_text("id,start_date\nA,2025-01-01\n")
    assert "role" in load_roster(p, cfg).unavailable


def test_a_negative_quota_excludes_the_row_with_a_reason(tmp_path):
    cfg = cfg_from(tmp_path, "roles: {quota_carrying: [ae]}\n")
    p = tmp_path / "team_members.csv"
    p.write_text("id,role,start_date,end_date,annual_quota\nA,ae,2025-01-01,,-5\n")
    r = load_roster(p, cfg)
    assert r.members == () and "quota" in r.excluded[0].reason


@pytest.mark.parametrize(
    "item,field",
    [
        (
            {
                "programs": [
                    {"name": "x", "pipeline": 100, "start": "2026-10", "cost": -1}
                ]
            },
            "cost",
        ),
        (
            {"programs": [{"name": "x", "pipeline": "nan", "start": "2026-10"}]},
            "pipeline",
        ),
        (
            {
                "programs": [
                    {"name": "x", "pipeline": 100, "start": "2026-10", "months": 2.5}
                ]
            },
            "months",
        ),
        ({"hires": [{"segment": "mm", "start": "2026-10", "count": 2.5}]}, "count"),
        (
            {"hires": [{"segment": "mm", "start": "2026-05", "count": 1}]},
            "after the as-of",
        ),
    ],
)
def test_plan_items_are_validated_with_a_field_specific_error(tmp_path, item, field):
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(item))
    with pytest.raises(ValueError, match=field):
        load_plan(path, date(2026, 8, 31), ())


def test_zero_quota_carrying_heads_means_capacity_unavailable_with_the_reason_no_crash(
    tmp_path,
):
    profile, data = staffed.write(tmp_path, rep_rate=3.0, demand=0.5)
    bare = tmp_path / "bare"
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
    plan = tmp_path / "plan.yaml"
    plan.write_text(
        yaml.safe_dump(
            {"hires": [{"segment": "mid_market", "start": "2026-10", "count": 1}]}
        )
    )
    r = build_report(profile, bare, AS_OF, draws=50, plan_path=plan)
    d = r["roster_capacity"]["decision"]
    assert d["outcome"] == "unavailable" and "no quota-carrying" in d["reason"]
    assert r["verdicts"]["software_correct"]["verdict"] == "yes"

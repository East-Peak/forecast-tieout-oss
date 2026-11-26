"""Goal 2B: the roster, ramped AE-months, and the roster at a past cutoff.
Every expected number carries its arithmetic."""

from datetime import date
from decimal import Decimal

import pytest
import yaml

from engine.tieout_core.capacity_config import load_capacity, load_roster
from engine.tieout_core.capacity_rules import DAYS_PER_AE_MONTH
from engine.tieout_core.roster import (
    Member,
    RampCurve,
    employed,
    heads_on,
    ramped_ae_months,
    roster_at,
    tenure_month,
)

HALF = RampCurve((Decimal("0.5"),), "entered", 0)  # tenure month 1 at 0.5, then 1


def ae(id, start, end=None, segment="mm", quota=None):
    return Member(id, "ae", segment, date.fromisoformat(start),
                  date.fromisoformat(end) if end else None, quota)  # fmt: skip


def test_tenure_months_are_anniversary_months():
    m = ae("A", "2026-01-31")
    assert tenure_month(m, date(2026, 1, 30)) == 0  # not yet started
    assert tenure_month(m, date(2026, 1, 31)) == 1
    assert (
        tenure_month(m, date(2026, 2, 27)) == 1
    )  # month 1 runs to 2026-02-28 (clamped)
    assert tenure_month(m, date(2026, 2, 28)) == 2
    assert tenure_month(m, date(2027, 1, 31)) == 13


def test_a_mid_month_start_ramps_by_tenure_not_by_calendar_month():
    # Starts 2026-03-16; month 1 is 03-16..04-15 (weight 0.5), then weight 1.
    # Days in (2026-02-28, 2026-04-30]:
    #   03-16..03-31 = 16 days and 04-01..04-15 = 15 days at 0.5 = 15.5
    #   04-16..04-30 = 15 days at 1.0                              = 15.0
    # 30.5 ramped AE-days / 30.4375 days per AE-month.
    m = [ae("A", "2026-03-16")]
    got = ramped_ae_months(m, HALF, date(2026, 2, 28), date(2026, 4, 30))
    assert got == Decimal("30.5") / DAYS_PER_AE_MONTH


def test_a_departure_counts_through_its_end_date_and_not_after():
    # Tenured, ends 2026-04-10: employed 04-01..04-10 = 10 days in April.
    m = [ae("A", "2020-01-01", "2026-04-10")]
    assert employed(m[0], date(2026, 4, 10)) and not employed(m[0], date(2026, 4, 11))
    assert ramped_ae_months(m, HALF, date(2026, 3, 31), date(2026, 4, 30)) == Decimal(
        10
    ) / Decimal("30.4375")


def test_a_signed_hire_counts_from_its_start_date_and_not_before():
    # Signed on 2026-08-31 to start 2026-09-15: nothing before, 16 days of
    # September 15..30 at weight 0.5 = 8 ramped AE-days.
    m = [ae("H", "2026-09-15")]
    assert heads_on(m, date(2026, 9, 14)) == 0 and heads_on(m, date(2026, 9, 15)) == 1
    assert ramped_ae_months(m, HALF, date(2026, 8, 31), date(2026, 9, 30)) == Decimal(
        8
    ) / Decimal("30.4375")


def test_the_roster_at_a_past_cutoff_hides_later_departures_and_later_hires():
    members = [
        ae("OLD", "2025-01-01", "2026-03-01"),  # left before the cutoff: known
        ae("STAYS", "2025-01-01", "2026-07-10"),  # leaves after the cutoff: hidden
        ae("LATE", "2026-06-20"),  # hired after the cutoff: invisible
        ae("NOW", "2026-05-01"),
    ]
    seen = {m.id: m for m in roster_at(members, date(2026, 6, 15))}
    assert set(seen) == {"OLD", "STAYS", "NOW"}
    assert seen["OLD"].end == date(2026, 3, 1)
    assert seen["STAYS"].end is None  # treated as still employed
    assert heads_on(list(seen.values()), date(2026, 6, 15)) == 2
    # a cutoff after the departure sees it
    assert {m.id: m.end for m in roster_at(members, date(2026, 8, 1))}["STAYS"] == date(
        2026, 7, 10
    )


def test_changing_the_future_leaves_the_roster_at_the_cutoff_unchanged():
    base = [ae("A", "2025-01-01"), ae("B", "2026-05-01")]
    rewritten = [
        ae("A", "2025-01-01", "2026-09-01"),
        ae("B", "2026-05-01", "2026-12-31"),
        ae("C", "2026-07-01"),
        ae("D", "2026-06-16"),
    ]
    cutoff = date(2026, 6, 15)
    assert roster_at(base, cutoff) == roster_at(rewritten[:2], cutoff)
    assert roster_at(rewritten, cutoff) == roster_at(base, cutoff)


# ---------------------------------------------------------------- loading


def _write_roster(path, rows):
    cols = "id,name,role,segment,start_date,end_date,annual_quota"
    path.write_text(cols + "\n" + "\n".join(rows) + "\n")
    return path


def test_load_roster_counts_known_roles_and_excludes_unknown_ones_with_a_reason(
    tmp_path,
):
    cfg_path = tmp_path / "capacity.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"roles": {"quota_carrying": ["ae"], "other": ["sdr"]}})
    )
    cfg = load_capacity(tmp_path)
    p = _write_roster(
        tmp_path / "team_members.csv",
        [
            "AE-1,A,ae,mm,2025-01-01,,1200000",
            "AE-2,B,AE,ent,2025-06-01,2026-03-01,1800000",
            "SDR-1,C,sdr,,2025-01-01,,",
            "X-1,D,wizard,,2025-01-01,,",
            "AE-3,E,ae,mm,,,900000",
            "AE-4,F,ae,mm,2026-05-01,2026-04-01,900000",
        ],
    )
    r = load_roster(p, cfg)
    assert [m.id for m in r.members] == ["AE-1", "AE-2"]
    assert r.members[1].end == date(2026, 3, 1) and r.members[
        1
    ].annual_quota == Decimal(1800000)
    assert r.other_roles == {"sdr": 1}
    reasons = {e.id: e.reason for e in r.excluded}
    assert "not named in capacity.yaml" in reasons["X-1"]
    assert "start date" in reasons["AE-3"]
    assert "ends before it starts" in reasons["AE-4"]
    assert (
        r.rows == 6
        and len(r.members) + sum(r.other_roles.values()) + len(r.excluded) == 6
    )


def test_a_roster_without_start_dates_is_unavailable_with_the_reason(tmp_path):
    (tmp_path / "capacity.yaml").write_text(
        yaml.safe_dump({"roles": {"quota_carrying": ["ae"]}})
    )
    cfg = load_capacity(tmp_path)
    p = tmp_path / "team_members.csv"
    p.write_text("id,role\nAE-1,ae\n")
    r = load_roster(p, cfg)
    assert r.members == () and "start_date" in r.unavailable


def test_a_missing_roster_file_is_unavailable(tmp_path):
    (tmp_path / "capacity.yaml").write_text(
        yaml.safe_dump({"roles": {"quota_carrying": ["ae"]}})
    )
    r = load_roster(tmp_path / "team_members.csv", load_capacity(tmp_path))
    assert r.unavailable and r.members == ()


def test_capacity_yaml_is_optional_and_its_entries_are_exact_decimals(tmp_path):
    assert load_capacity(tmp_path) is None
    (tmp_path / "capacity.yaml").write_text(
        "roles: {quota_carrying: [ae], other: [sdr]}\n"
        "ramp: {months: [0.25, 0.5]}\n"
        "attrition: {monthly_per_ae: 0.02}\n"
        "costs: {loaded_cost_per_ae_month: 12000, programme_cost_per_dollar_of_pipeline: 0.05}\n"
        "programme: {ramp_months: 4}\n"
        "hires: {max_in_one_quarter: 7}\n"
    )
    c = load_capacity(tmp_path)
    assert c.quota_roles == ("ae",) and c.other_roles == ("sdr",)
    assert c.ramp == (Decimal("0.25"), Decimal("0.5"))
    assert c.attrition == Decimal("0.02")
    assert c.loaded_cost_per_ae_month == Decimal(12000)
    assert c.programme_cost_per_dollar == Decimal("0.05")
    assert c.programme_ramp_months == 4 and c.hires_bound == 7


def test_a_capacity_yaml_with_no_quota_roles_is_refused(tmp_path):
    (tmp_path / "capacity.yaml").write_text("roles: {other: [sdr]}\n")
    with pytest.raises(ValueError, match="quota_carrying"):
        load_capacity(tmp_path)


def test_a_deals_owner_id_is_loaded_for_the_ramp_fit(tmp_path):
    from engine.tests.tieout_core.builders import deal, write_company, write_profile
    from engine.tieout_core.load import load_company, load_profile

    d = deal("D1", created="2026-01-05")
    d["owner_id"] = " AE-7 "
    write_company(tmp_path / "c", [d, deal("D2")])
    loaded = load_company(tmp_path / "c", load_profile(write_profile(tmp_path / "p")))
    assert [x.owner_id for x in loaded.dataset.deals] == ["AE-7", ""]

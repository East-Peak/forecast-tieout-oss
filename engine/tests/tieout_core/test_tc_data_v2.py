import csv
from dataclasses import replace
from datetime import date

import pytest
import yaml

from engine.scripts.generate_data_v2 import (
    COMPANIES,
    DATA_V2,
    STATED_REP_SHARE,
    check_invariants,
    target_dir,
    verify,
    write_company_files,
)
from engine.scripts.synth_history import employed, generate, ramp
from engine.tieout_core.load import load_company, load_profile

PROFILES = "engine/config/profiles"


def test_written_files_load_back_exactly(tmp_path):
    company = replace(COMPANIES["sprout-labs"], start=date(2025, 1, 1))
    generated = generate(company)
    write_company_files(generated, tmp_path)
    loaded = load_company(tmp_path, load_profile(f"{PROFILES}/sprout-labs"))
    assert loaded.exclusions == ()
    assert [
        (d.id, d.arr, d.stage, d.created, d.close, d.type) for d in loaded.dataset.deals
    ] == [
        (d.id, d.arr, d.stage, d.created, d.close, d.type)
        for d in generated.dataset.deals
    ]
    assert loaded.dataset.transitions == generated.dataset.transitions
    assert loaded.dataset.observations == generated.dataset.observations
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "deal_observations.csv", "deals.csv", "stage_history.csv", "team_members.csv"]  # fmt: skip


@pytest.mark.parametrize("slug", sorted(COMPANIES))
def test_demo_companies_have_thirty_months_ending_at_the_as_of(slug):
    c = COMPANIES[slug]
    months = (c.as_of.year - c.start.year) * 12 + c.as_of.month - c.start.month
    assert months >= 30
    assert load_profile(f"{PROFILES}/{slug}").fiscal_year.contains(c.as_of)


@pytest.mark.parametrize("slug", sorted(COMPANIES))
def test_committed_demo_data_is_current(slug):
    assert verify(slug) == [], (
        f"engine/{DATA_V2}/{slug} is stale: run python -m engine.scripts.generate_data_v2"
    )


# ---------------------------------------------------------------- Goal 2A rosters

ROSTER_COLUMNS = ["id", "name", "role", "segment", "start_date", "end_date",
                  "is_active", "manager_id", "annual_quota"]  # fmt: skip


def _rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def generated():
    return {slug: generate(c) for slug, c in COMPANIES.items()}


@pytest.mark.parametrize("slug", sorted(COMPANIES))
def test_committed_files_pass_the_invariants(slug):
    assert check_invariants(target_dir(slug), COMPANIES[slug].as_of) == []


def test_invariants_catch_an_owner_not_yet_employed_and_a_future_date(tmp_path):
    write_company_files(generate(COMPANIES["sprout-labs"]), tmp_path)
    deals = _rows(tmp_path / "deals.csv")
    team = {r["id"]: r for r in _rows(tmp_path / "team_members.csv")}
    late = max(
        (r for r in team.values() if r["role"] == "ae"), key=lambda r: r["start_date"]
    )
    early = min(deals, key=lambda r: r["created_date"])
    early["owner_id"] = late["id"]
    deals[-1]["created_date"] = "2026-09-01"
    with open(tmp_path / "deals.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(deals[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(deals)
    problems = check_invariants(tmp_path, COMPANIES["sprout-labs"].as_of)
    assert any("not employed" in p and early["id"] in p for p in problems)
    assert any("after the cutoff" in p and "created_date" in p for p in problems)


@pytest.mark.parametrize("slug", sorted(COMPANIES))
def test_roster_has_end_dates_and_quotas(slug):
    rows = _rows(target_dir(slug) / "team_members.csv")
    assert list(rows[0]) == ROSTER_COLUMNS
    aes = [r for r in rows if r["role"] == "ae"]
    assert all(r["annual_quota"] for r in aes)
    assert all(not r["annual_quota"] for r in rows if r["role"] != "ae")
    assert any(r["end_date"] for r in aes), "nobody ever leaves"
    assert all((r["is_active"] == "true") == (not r["end_date"]) for r in rows)


@pytest.mark.parametrize("slug", sorted(COMPANIES))
def test_quotas_are_a_plausible_multiple_of_target(slug, generated):
    c = COMPANIES[slug]
    profile = load_profile(f"{PROFILES}/{slug}")
    quota = sum(m.annual_quota for m in generated[slug].roster
                if m.role == "ae" and employed(m, c.as_of))  # fmt: skip
    target = sum(profile.quarterly_targets.values())
    assert 1.1 <= quota / target <= 2.0, f"{slug}: quota {quota} / target {target}"


@pytest.mark.parametrize("slug", sorted(COMPANIES))
def test_heads_are_on_the_profile_headcount_plan(slug, generated):
    with open(f"{PROFILES}/{slug}/targets.yaml") as fh:
        plan = yaml.safe_load(fh)["monthly_ae_targets"]
    aes = [m for m in generated[slug].roster if m.role == "ae"]
    for month, planned in plan.items():
        on = date.fromisoformat(str(month)).replace(day=15)
        if on > COMPANIES[slug].as_of:
            continue
        heads = sum(employed(m, on) for m in aes)
        assert planned - max(2, planned // 20) <= heads <= planned, (slug, on, heads)


def _ramped(slug, generated, on):
    st = COMPANIES[slug].staffing
    aes = [m for m in generated[slug].roster if m.role == "ae" and employed(m, on)]
    return len(aes), sum(ramp(m, on, st.ramp_months) for m in aes)


def test_each_company_keeps_its_story(generated):
    as_of = COMPANIES["sprout-labs"].as_of
    heads, _ = _ramped("sprout-labs", generated, as_of)
    assert heads <= 8  # Sprout: few reps
    heads, ramped = _ramped("sapling-industries", generated, as_of)
    assert ramped <= 0.8 * heads  # Sapling: heads on plan, ramped capacity short
    heads, ramped = _ramped("mighty-oak-holdings", generated, as_of)
    assert heads >= 90 and ramped >= 0.9 * heads  # Mighty Oak: staffed
    assert (
        COMPANIES["mighty-oak-holdings"].conversion_change is not None
    )  # conversion is the problem


@pytest.mark.parametrize("slug", sorted(COMPANIES))
def test_creation_mix_is_the_stated_one(slug, generated):
    g = generated[slug]
    c = COMPANIES[slug]
    recent = [d for d in g.dataset.deals if d.type == "new_business"
              and (c.as_of - d.created).days < 365]  # fmt: skip
    share = sum(g.origins[d.id] == "rep" for d in recent) / len(recent)
    assert abs(share - STATED_REP_SHARE[slug]) <= 0.01, (slug, share)

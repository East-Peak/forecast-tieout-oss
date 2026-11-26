from dataclasses import replace
from datetime import date

import pytest

from engine.scripts.generate_data_v2 import COMPANIES, DATA_V2, write_company_files, verify
from engine.scripts.synth_history import generate
from engine.tieout_core.load import load_company, load_profile

PROFILES = "engine/config/profiles"


def test_written_files_load_back_exactly(tmp_path):
    company = replace(COMPANIES["sprout-labs"], start=date(2025, 1, 1))
    generated = generate(company)
    write_company_files(generated, tmp_path)
    loaded = load_company(tmp_path, load_profile(f"{PROFILES}/sprout-labs"))
    assert loaded.exclusions == ()
    assert [(d.id, d.arr, d.stage, d.created, d.close, d.type) for d in loaded.dataset.deals] == [
        (d.id, d.arr, d.stage, d.created, d.close, d.type) for d in generated.dataset.deals
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
    assert verify(slug) == [], f"engine/{DATA_V2}/{slug} is stale: run python -m engine.scripts.generate_data_v2"

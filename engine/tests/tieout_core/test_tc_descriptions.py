"""A company's one-line description in ``index.json`` is generated from its as-signed
report's statuses (engine/tieout_core/company_line.py): no figure, one plain line, and
agreeing with the report on the three things it says. Profiles carry no hand-written
description."""

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
REPORTS = ROOT / "frontend" / "public" / "data" / "reports"
PROFILES = ROOT / "engine" / "config" / "profiles"
COMPANIES = ["sprout-labs", "sapling-industries", "mighty-oak-holdings"]


def report(company: str) -> dict:
    return json.loads((REPORTS / company / "as-signed.json").read_text())


def description(company: str) -> str:
    index = json.loads((REPORTS / "index.json").read_text())
    return next(c["description"] for c in index["companies"] if c["id"] == company)


@pytest.mark.parametrize("company", COMPANIES)
def test_the_description_has_no_digit_and_is_one_plain_line(company):
    text = description(company)
    assert not any(ch.isdigit() for ch in text), text
    assert "$" not in text and "%" not in text and "\n" not in text, text
    assert len(text) <= 200, text


@pytest.mark.parametrize("company", COMPANIES)
def test_the_year_phrase_agrees_with_the_sign_of_the_gap(company):
    gap = report(company)["gap"]["fiscal_year"]["gap"]
    text = description(company)
    expected = (
        "Short of target"
        if float(gap) > 0
        else "Ahead of target"
        if float(gap) < 0
        else "On target"
    )
    assert text.startswith(expected), (gap, text)


@pytest.mark.parametrize("company", COMPANIES)
def test_the_headcount_phrase_agrees_with_the_capacity_decision(company):
    outcome = report(company)["roster_capacity"]["decision"]["outcome"]
    text = description(company)
    explains = "Headcount explains pipeline" in text
    cannot_say = "cannot say whether headcount explains pipeline" in text
    assert explains == (outcome == "adopted"), (outcome, text)
    assert cannot_say == (outcome == "not shown"), (outcome, text)


@pytest.mark.parametrize("company", COMPANIES)
def test_the_baseline_phrase_agrees_with_the_verdict(company):
    verdict = report(company)["verdicts"]["forecast_better_than_baselines"]["verdict"]
    text = description(company)
    assert ("beats the simple yardsticks" in text) == (verdict == "yes"), text
    assert ("does not yet beat the simple yardsticks" in text) == (verdict == "no"), (
        text
    )


def test_the_three_companies_read_differently():
    assert len({description(c) for c in COMPANIES}) == len(COMPANIES)


@pytest.mark.parametrize("company", COMPANIES)
def test_a_profile_carries_no_hand_written_description(company):
    doc = yaml.safe_load((PROFILES / company / "profile.yaml").read_text())
    assert "description" not in doc
    assert doc["org_name"]

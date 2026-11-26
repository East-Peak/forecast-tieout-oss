from datetime import date
from decimal import Decimal

import pytest

from engine.tests.tieout_core.builders import deal, write_company, write_profile
from engine.tieout_core.load import load_company, load_profile


@pytest.fixture
def profile(tmp_path):
    return load_profile(write_profile(tmp_path / "profile", targets={
        "Q1FY26": 100, "Q2FY26": 200, "Q3FY26": 300, "Q4FY26": 400.5}))  # fmt: skip


def test_profile_reads_stage_codes_probabilities_and_targets(profile):
    assert profile.open_codes == ("S1", "S2", "S3", "S4", "S5")
    assert profile.code_for("Business Case") == "S4"
    assert profile.probability("S4") == Decimal("0.5")
    assert profile.fiscal_year.start == date(2026, 2, 1)
    assert profile.quarterly_targets["Q4FY26"] == Decimal("400.5")


def test_profile_rejects_targets_for_another_year(tmp_path):
    path = write_profile(tmp_path / "p", targets={"Q1FY27": 1})
    with pytest.raises(ValueError, match="Q1FY26"):
        load_profile(path)


def test_money_is_exact_decimal(tmp_path, profile):
    path = write_company(tmp_path / "c", [deal("D1", arr="1234.56")])
    loaded = load_company(path, profile)
    assert loaded.dataset.deals[0].arr == Decimal("1234.56")
    assert loaded.source_rows == 1
    assert loaded.source_arr_total == Decimal("1234.56")


def test_structurally_broken_rows_are_excluded_with_reasons(tmp_path, profile):
    rows = [
        deal("OK", stage="Closed Won", close="2026-03-01"),
        deal("BADARR", arr="n/a"),
        deal("BADSTAGE", stage="Mystery"),
        deal("NOCLOSE", stage="Closed Lost", close=""),
        deal("BACKWARDS", stage="Closed Won", created="2026-03-01", close="2026-02-01"),
        {**deal("FLAGS", stage="Closed Won", close="2026-03-01"), "is_won": "false"},
    ]
    loaded = load_company(write_company(tmp_path / "c", rows), profile)
    assert [d.id for d in loaded.dataset.deals] == ["OK"]
    reasons = {e.deal_id: e.reason for e in loaded.exclusions}
    assert reasons == {
        "BADARR": "arr is missing or not a number",
        "BADSTAGE": "stage 'Mystery' is not in the profile's stage mapping",
        "NOCLOSE": "closed deal has no close date",
        "BACKWARDS": "close date is before created date",
        "FLAGS": "is_closed/is_won flags disagree with the stage",
    }
    assert {e.row for e in loaded.exclusions} == {
        3,
        4,
        5,
        6,
        7,
    }  # 1-based, header is row 1
    assert loaded.source_rows == 6


def test_stage_history_maps_to_codes_and_dates(tmp_path, profile):
    path = write_company(
        tmp_path / "c",
        [deal("D1")],
        history=[
            ("D1", "Discovery", "2026-01-01T10:00:00"),
            ("D1", "Business Case", "2026-01-05"),
        ],
    )
    transitions = load_company(path, profile).dataset.transitions
    assert [(t.deal_id, t.stage, t.on) for t in transitions] == [
        ("D1", "S1", date(2026, 1, 1)),
        ("D1", "S4", date(2026, 1, 5)),
    ]


def test_observations_are_optional(tmp_path, profile):
    bare = load_company(write_company(tmp_path / "a", [deal("D1")]), profile)
    assert bare.dataset.observations is None
    with_obs = load_company(
        write_company(
            tmp_path / "b",
            [deal("D1")],
            observations=[("D1", "2026-01-01", "90.10", "2026-04-01")],
        ),
        profile,
    )
    (obs,) = with_obs.dataset.observations
    assert (obs.deal_id, obs.on, obs.amount, obs.expected_close) == (
        "D1", date(2026, 1, 1), Decimal("90.10"), date(2026, 4, 1))  # fmt: skip


def test_roster_is_counted_by_role(tmp_path, profile):
    team = [
        {"id": "1", "role": "ae"},
        {"id": "2", "role": "AE"},
        {"id": "3", "role": "sdr"},
    ]
    loaded = load_company(
        write_company(tmp_path / "c", [deal("D1")], team=team), profile
    )
    assert loaded.roster_roles == {"ae": 2, "sdr": 1}

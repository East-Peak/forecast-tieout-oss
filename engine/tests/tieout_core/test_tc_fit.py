from datetime import date
from decimal import Decimal

import pytest

from engine.tests.tieout_core.builders import write_profile
from engine.tieout_core.fit import age_group, fit
from engine.tieout_core.load import load_profile
from engine.tieout_core.records import Dataset, Deal, Transition

CUT = date(2026, 6, 30)  # matured snapshots: 2025-06-30 and earlier


def _deal(id, created, stage, arr, close=None, won=False):
    closed = stage in ("Won", "Lost")
    return Deal(0, id, "new_business", "mm", stage, Decimal(arr), created, close, closed, won)


JUN1 = date(2025, 6, 1)
JAN1 = date(2025, 1, 1)
DATA = Dataset(
    deals=(
        # Open in S3 at the 2025-06-30 snapshot.
        _deal("A", JUN1, "Won", "100", date(2025, 8, 29), True),
        _deal("B", JUN1, "Lost", "200", date(2025, 7, 15)),
        _deal("C", JUN1, "S3", "300"),  # still open a year later: not won within horizon
        _deal("D", JUN1, "Won", "400", date(2026, 6, 29), True),
        # Open in S2 across several snapshots.
        _deal("F", JAN1, "Won", "500", date(2025, 6, 15), True),
        _deal("G", JAN1, "Lost", "600", date(2025, 3, 1)),
        # Created after the last matured snapshot: no win-rate evidence yet.
        _deal("E", date(2025, 7, 15), "Won", "700", date(2025, 9, 1), True),
    ),
    transitions=tuple(
        sorted(
            [Transition(i, "S3", JUN1) for i in "ABCD"]
            + [Transition("A", "Won", date(2025, 8, 29)), Transition("B", "Lost", date(2025, 7, 15))]
            + [Transition("D", "Won", date(2026, 6, 29))]
            + [Transition(i, "S2", JAN1) for i in "FG"]
            + [Transition("F", "Won", date(2025, 6, 15)), Transition("G", "Lost", date(2025, 3, 1))]
            + [Transition("E", "S1", date(2025, 7, 15)), Transition("E", "Won", date(2025, 9, 1))],
            key=lambda t: (t.deal_id, t.on),
        )
    ),
    observations=None,
)


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    profile = load_profile(write_profile(tmp_path_factory.mktemp("p")))
    return fit(DATA, CUT, profile)


def test_age_groups():
    assert [age_group(d) for d in (0, 90, 91, 180, 181)] == [
        "0-90d", "0-90d", "91-180d", "91-180d", "181d+"]  # fmt: skip


def test_stage_rate_counts_each_deal_once_at_its_first_matured_snapshot(model):
    r = model.rates["win_within_horizon:S3"]
    assert (r.value, r.sample_size, r.source) == (Decimal("0.5"), 4, "fitted")
    assert "2 won within 365 days" in r.numerator
    assert r.low95 == pytest.approx(0.15, abs=1e-3)


def test_cell_rates_are_shrunk_toward_their_stage(model):
    assert model.rates["win_within_horizon:S2"].value == Decimal("0.5")
    assert model.win_rate("S2", 30) == Decimal("0.5")  # (1 + 20*0.5) / (2 + 20)
    assert model.win_rate("S2", 120) == Decimal(11) / Decimal(21)  # (1 + 10) / (1 + 20)
    # A cell with no evidence is its stage rate.
    assert model.win_rate("S3", 400) == Decimal("0.5")


def test_a_stage_with_no_history_uses_the_profile_probability(model):
    r = model.rates["win_within_horizon:S4"]
    assert (r.value, r.sample_size, r.source) == (Decimal("0.5"), 0, "default")


def test_close_timing_is_the_empirical_days_to_win(model):
    # S3 has two wins (60 and 364 days after the snapshot), fewer than the
    # 20-sample minimum, so it is pooled with S2's one win (136 days).
    timing = model.timing("S3")
    assert timing.samples == (60, 136, 364)
    assert timing.source == "pooled across stages (fewer than 20 wins in S3)"
    assert timing.cdf(59) == 0 and timing.cdf(60) == Decimal(1) / 3 and timing.cdf(364) == 1


def test_new_pipeline_parameters_come_from_the_matured_creation_cohort(model):
    new = model.new_pipeline
    # Cohort: created 2024-06-30 < d <= 2025-06-30 -> A B C D F G.
    # Won within 365 days of creation: A (89 days) and F (165 days); D took 393.
    assert new.win_rate == Decimal(2) / Decimal(6)
    assert new.timing.samples == (89, 165)
    assert new.mean_won_arr == Decimal("300")
    assert new.mean_created_arr == Decimal("350")
    assert new.created_per_day == Decimal(1) / Decimal(365)  # only E in the last year
    assert model.rates["new_pipeline_win_rate"].sample_size == 6


def test_no_rate_is_defined_twice(model):
    names = [r.name for r in model.rates]
    assert len(names) == len(set(names))

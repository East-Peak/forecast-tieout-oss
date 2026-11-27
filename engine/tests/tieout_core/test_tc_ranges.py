"""Goal 2A, lesson 2 (ranges). The declared candidate: the simulation draws the
rates from their uncertainty as well as the deal outcomes. Coverage and median
range width are reported per company and horizon with fold counts. Adopted if
pooled 80% coverage at 1 and 3 months moves closer to 80% and no
company-and-horizon cell moves more than 10 points further from it; otherwise
the Goal 1 ranges stay. Each cell is labelled back-tested, too narrow or too
wide; twelve-month ranges are labelled unvalidated."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from engine.tests.tieout_core.test_tc_forecast import CUT, MODEL, WINDOWS
from engine.tieout_core.backtest import (
    BACK_TESTED,
    METHODS,
    TOO_NARROW,
    TOO_WIDE,
    UNVALIDATED,
    Fold,
    coverage_label,
    ranges_decision,
    score_horizon,
)
from engine.tieout_core.fit import OUTCOME_RANGES, PARAMETER_RANGES, FitParams
from engine.tieout_core.forecast import simulate
from engine.tieout_core.records import Dataset, Deal

CROWD = Dataset(
    tuple(
        Deal(0, f"D{i}", "new_business", "mm", "S1", Decimal(100), date(2026, 1, 1), None, False, False)
        for i in range(200)
    ),
    (),
    None,
)  # fmt: skip
# The same open-deal model, with the S1 rate resting on ten observations and the
# creation cohort on forty.
UNCERTAIN = replace(
    MODEL,
    rate_n={("S1", None): 10.0, ("S2", None): 10.0},
    new_pipeline=replace(
        MODEL.new_pipeline, win_rate_n=40.0, created_count=36, created_days=365
    ),
)


def test_parameter_draws_widen_the_range_and_keep_the_centre():
    plain = simulate(UNCERTAIN, CROWD, CUT, WINDOWS, draws=8000, seed=1)
    wide = simulate(
        UNCERTAIN, CROWD, CUT, WINDOWS, draws=8000, seed=1, parameter_uncertainty=True
    )

    def width(s):
        return s.total.p90 - s.total.p10

    assert width(wide) > 2 * width(plain)
    assert wide.total.mean == pytest.approx(plain.total.mean, rel=0.03)
    assert wide == simulate(
        UNCERTAIN, CROWD, CUT, WINDOWS, draws=8000, seed=1, parameter_uncertainty=True
    )


def test_a_rate_without_a_sample_is_held_fixed():
    fixed = replace(
        UNCERTAIN,
        rate_n={},
        new_pipeline=replace(UNCERTAIN.new_pipeline, win_rate_n=0.0, created_count=0),
    )
    a = simulate(fixed, CROWD, CUT, WINDOWS, draws=4000, seed=2)
    b = simulate(
        fixed, CROWD, CUT, WINDOWS, draws=4000, seed=2, parameter_uncertainty=True
    )
    assert b.total.p90 - b.total.p10 == pytest.approx(
        a.total.p90 - a.total.p10, rel=0.1
    )


def test_outcomes_only_is_the_goal_1_default_until_adopted():
    assert FitParams(ranges=OUTCOME_RANGES).ranges == OUTCOME_RANGES
    assert PARAMETER_RANGES != OUTCOME_RANGES


# ---------------------------------------------------------------- cells and labels


def test_coverage_labels():
    assert coverage_label(8, 10) == BACK_TESTED
    assert coverage_label(10, 10) == BACK_TESTED  # 10 of 10 is consistent with 80%
    assert coverage_label(30, 30) == TOO_WIDE
    assert coverage_label(2, 10) == TOO_NARROW
    assert coverage_label(4, 5) == UNVALIDATED  # fewer than six folds
    assert coverage_label(0, 0) == UNVALIDATED


def test_scores_carry_median_width_of_the_80_range():
    none = dict.fromkeys(METHODS)
    folds = [
        Fold(date(2025, 1, 1), 1, Decimal(10), none, (0.0, 20.0), (0.0, 30.0)),
        Fold(date(2025, 2, 1), 1, Decimal(50), none, (0.0, 40.0), (0.0, 60.0)),
        Fold(date(2025, 3, 1), 1, Decimal(5), none, (0.0, 100.0), (0.0, 120.0)),
        Fold(date(2025, 4, 1), 1, Decimal(5), none, None, None),
    ]
    s = score_horizon(1, folds)
    assert s.range_folds == 3 and s.coverage80 == pytest.approx(2 / 3)
    assert s.median_width80 == 40.0


def _cells(values):
    """{(company, horizon): (inside, folds)} from {(company, horizon): coverage over 10}."""
    return {k: (round(v * 10), 10) for k, v in values.items()}


def test_adopted_when_pooled_moves_closer_and_no_cell_moves_ten_points_away():
    before = _cells(
        {("a", 1): 0.5, ("b", 1): 0.6, ("a", 3): 0.5, ("b", 3): 0.7, ("a", 6): 0.4}
    )
    after = _cells(
        {("a", 1): 0.7, ("b", 1): 0.8, ("a", 3): 0.8, ("b", 3): 0.9, ("a", 6): 0.6}
    )
    d = ranges_decision(before, after)
    assert d.adopted, d.reason
    assert d.pooled[1] == (pytest.approx(0.55), pytest.approx(0.75))


def test_declined_when_one_cell_moves_more_than_ten_points_further():
    before = _cells({("a", 1): 0.5, ("b", 1): 0.8, ("a", 3): 0.5, ("b", 3): 0.8})
    after = _cells(
        {("a", 1): 0.8, ("b", 1): 1.0, ("a", 3): 0.8, ("b", 3): 0.8}
    )  # b,1 moves 20 away
    d = ranges_decision(before, after)
    assert not d.adopted and "b" in d.reason


def test_declined_when_pooled_is_not_closer_at_both_horizons():
    before = _cells({("a", 1): 0.5, ("a", 3): 0.8})
    after = _cells({("a", 1): 0.8, ("a", 3): 0.9})
    assert not ranges_decision(before, after).adopted


# ---------------------------------------------------------------- in the report


@pytest.fixture(scope="module")
def report():
    from engine.tieout_core.report import NEXT_12, REST_OF_FY, build_report

    r = build_report(Path("engine/config/profiles/sapling-industries"),
                     Path("engine/data-v2/sapling-industries"), date(2026, 8, 31), draws=300)  # fmt: skip
    return r, REST_OF_FY, NEXT_12


def test_report_labels_each_horizon_cell_with_its_folds_and_width(report):
    r, rest, next12 = report
    fr = r["forecasts"]["fitted_ranges"]
    assert [c["horizon_months"] for c in fr["cells"]] == [1, 3, 6]
    for c in fr["cells"]:
        assert c["label"] in (BACK_TESTED, TOO_NARROW, TOO_WIDE, UNVALIDATED)
        assert c["folds_with_a_range"] > 0 and c["median_width80"] is not None
    # The rest of the year (five months here) is judged by the six-month cell.
    six = fr["cells"][2]
    assert fr["horizons"][rest]["status"].startswith(six["label"])
    assert fr["horizons"][next12]["status"].startswith(UNVALIDATED)
    assert r["inputs"]["ranges"] in (OUTCOME_RANGES, PARAMETER_RANGES)


def test_committed_range_method_is_the_declared_decision_on_the_frozen_data():
    from engine.tieout_core.candidates import DEMO_COMPANIES, score_ranges
    from engine.tieout_core.fit import DEFAULT_PARAMS

    decision = score_ranges(DEMO_COMPANIES).decision
    assert DEFAULT_PARAMS.ranges == (
        PARAMETER_RANGES if decision.adopted else OUTCOME_RANGES
    )

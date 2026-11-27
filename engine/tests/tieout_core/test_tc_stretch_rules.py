"""Goal 2D: the thresholds and the adoption rule, committed before any code that
computes a stretched score on the demo companies exists. The rule is tested on
synthetic counts only."""

from fractions import Fraction

from engine.tieout_core import stretch_rules as r
from engine.tieout_core.stretch_rules import Counts, decide


def test_the_thresholds_are_the_specs():
    assert r.HORIZONS == (1, 3, 6)
    assert r.SCORED_HORIZONS == (1, 3)
    assert r.TARGET == Fraction(80, 100)
    assert r.SIDE_COVERAGE == Fraction(90, 100)
    assert r.MIN_ELIGIBLE_FOLDS == 5
    assert r.MIN_SCORED_FOLDS == 6
    assert r.MAX_WORSENING == Fraction(10, 100)


def test_the_fixture_tolerances_are_declared():
    assert r.FIXTURE_SEEDS == 3
    assert r.NO_SHIFT_MAX_FACTOR == 1.35
    assert r.NO_SHIFT_MEDIAN_FACTOR == 1.10
    assert r.NO_SHIFT_MAX_FACTOR_SIX == 1.75  # amended after the first fixture run
    assert r.SHIFT_FACTOR == 0.5
    assert r.SHIFT_MAX_SIMULATED == 0.60
    assert r.SHIFT_MIN_GAIN == 0.15


def test_the_side_rank_is_ninety_percent_rounded_up_exactly():
    assert [r.side_rank(n) for n in (5, 10, 11, 14, 20, 21)] == [5, 9, 10, 13, 18, 19]


def counts(h, scored, sim, stretched):
    return Counts(h, scored, sim, stretched)


def test_adopted_when_pooled_coverage_is_closer_and_nothing_worsens():
    d = decide([counts(1, 10, 5, 8), counts(3, 8, 3, 6), counts(6, 4, 0, 2)])
    assert d.outcome == r.ADOPTED
    assert d.pooled == (Fraction(8, 18), Fraction(14, 18))
    assert "8 held" in d.reason and "14 held" in d.reason


def test_fewer_than_six_scored_folds_at_one_or_three_months_is_not_enough_history():
    ok = counts(3, 8, 3, 6)
    for h in (1, 3):
        short = counts(h, 5, 2, 4)
        other = counts(3 if h == 1 else 1, 8, 3, 6)
        d = decide([short, other, counts(6, 0, 0, 0)])
        assert d.outcome == r.NOT_ENOUGH_HISTORY
        assert f"5 scored folds at {h} month(s)" in d.reason
        assert d.pooled is None
    assert decide([counts(1, 6, 2, 5), ok]).outcome == r.ADOPTED  # six is enough


def test_a_missing_horizon_is_not_enough_history():
    assert decide([counts(1, 9, 3, 7)]).outcome == r.NOT_ENOUGH_HISTORY


def test_a_tie_in_pooled_distance_is_not_adopted():
    # simulated 12 of 20 (60%), stretched 20 of 20 (100%): both 20 points from 80%
    d = decide([counts(1, 10, 6, 10), counts(3, 10, 6, 10)])
    assert d.outcome == r.NOT_ADOPTED
    assert "not closer" in d.reason


def test_pooled_coverage_that_moves_away_is_not_adopted():
    d = decide([counts(1, 10, 8, 5), counts(3, 10, 8, 5)])
    assert d.outcome == r.NOT_ADOPTED


def test_a_horizon_ten_points_further_is_allowed_and_more_is_not():
    # 6 months: simulated 8 of 10 (80%); stretched 7 of 10 (70%): exactly 10 points further
    base = [counts(1, 10, 4, 8), counts(3, 10, 4, 8)]
    at_limit = decide([*base, counts(6, 10, 8, 7)])
    assert at_limit.outcome == r.ADOPTED
    assert at_limit.worst == (6, Fraction(1, 10))
    over = decide([*base, counts(6, 20, 16, 13)])  # 80% to 65%: 15 points further
    assert over.outcome == r.NOT_ADOPTED
    assert "at 6 month(s)" in over.reason and "15 points" in over.reason


def test_ten_points_and_a_fraction_is_over_the_limit_exactly():
    base = [counts(1, 10, 4, 8), counts(3, 10, 4, 8)]
    # 3 of 7 (42.86%) to 10 of 14... use thirds: 6 months simulated 11 of 20 (55%), stretched 9 of 20 (45%): 10 points
    assert decide([*base, counts(6, 20, 11, 9)]).outcome == r.ADOPTED
    # 12 of 20 (60%) to 9 of 20 (45%): 15 points
    assert decide([*base, counts(6, 20, 12, 9)]).outcome == r.NOT_ADOPTED
    # 7 of 20 (35%) to 5 of 20 (25%) is 10; one more fold lower is 15
    assert decide([*base, counts(6, 20, 7, 5)]).outcome == r.ADOPTED
    assert decide([*base, counts(6, 20, 7, 4)]).outcome == r.NOT_ADOPTED


def test_a_horizon_with_no_scored_folds_cannot_move_and_is_skipped():
    d = decide([counts(1, 10, 4, 8), counts(3, 10, 4, 8), counts(6, 0, 0, 0)])
    assert d.outcome == r.ADOPTED
    assert d.worst is not None and d.worst[0] in (1, 3)


def test_the_one_month_or_three_month_cell_can_also_trip_the_ten_point_limit():
    # pooled improves, but the three-month cell goes from 80% to 60%: 20 points further
    d = decide([counts(1, 20, 4, 20), counts(3, 10, 8, 6)])
    assert d.outcome == r.NOT_ADOPTED
    assert "at 3 month(s)" in d.reason


def test_moving_closer_is_never_counted_as_further():
    d = decide([counts(1, 10, 2, 9), counts(3, 10, 2, 9), counts(6, 10, 0, 9)])
    assert d.outcome == r.ADOPTED
    assert d.worst is not None and d.worst[1] < 0

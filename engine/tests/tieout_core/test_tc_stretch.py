"""Goal 2D: the stretch computation and the rolling scorer, on hand-built folds.

A fold is built from a median, an 80% range and an actual; the factors each fold would
have needed, which folds are eligible when, and what the scorer counts are checked by
hand. Every function takes its as-of date as an argument."""

import math
from datetime import date
from decimal import Decimal

import pytest

from engine.tieout_core.backtest import Fold
from engine.tieout_core.forecast import Spread
from engine.tieout_core.stretch import (
    Factors,
    eligible_folds,
    factors_at,
    factors_from,
    horizon_for,
    needed,
    score_horizon,
    stretch_range,
    stretch_spread,
    stretch_spread_with_floors,
)


def make(cutoff, horizon, actual, low=90.0, median=100.0, high=110.0):
    return Fold(
        cutoff,
        horizon,
        Decimal(actual),
        {},
        (low, high),
        (low - 5, high + 5),
        median,
    )


def monthly(h, actuals, first=date(2025, 1, 31)):
    """One fold a month at horizon ``h``: the same range 90 to 110 about 100."""
    out = []
    for i, a in enumerate(actuals):
        y, m = divmod(first.year * 12 + first.month - 1 + i, 12)
        cutoff = date(y, m + 1, 28)
        out.append(make(cutoff, h, a))
    return out


# ---------------------------------------------------------------- what a fold would have needed


def test_a_fold_inside_its_range_needed_no_stretch():
    assert needed(make(date(2025, 1, 31), 1, 95)) == (1.0, 1.0)
    assert needed(make(date(2025, 1, 31), 1, 90)) == (1.0, 1.0)  # on the edge is inside
    assert needed(make(date(2025, 1, 31), 1, 110)) == (1.0, 1.0)


def test_a_fold_below_needed_the_lower_side_stretched_to_reach_it():
    # median 100, p10 90, actual 70: the 30 below the median is 3 times the 10 of the range
    assert needed(make(date(2025, 1, 31), 1, 70)) == (3.0, 1.0)


def test_a_fold_above_needed_the_upper_side_stretched_to_reach_it():
    assert needed(make(date(2025, 1, 31), 1, 125)) == (1.0, 2.5)


def test_a_range_with_no_width_on_a_side_cannot_be_reached_by_stretching():
    f = make(date(2025, 1, 31), 1, 80, low=100.0)  # p10 sits on the median
    lower, upper = needed(f)
    assert math.isinf(lower) and upper == 1.0


# ---------------------------------------------------------------- the factor in use


def test_the_factor_is_the_smallest_that_holds_ninety_percent_of_the_eligible_folds():
    # ten folds: eight inside, one needing 1.5, one needing 3: nine must be inside, so 1.5
    actuals = [100] * 8 + [85, 70]  # 85 is inside? no: p10 is 90, so 85 needs 1.5
    folds = monthly(1, actuals)
    f = factors_from(folds)
    assert f.lower == pytest.approx(1.5)
    assert f.upper == 1.0
    assert f.eligible == 10


def test_ten_percent_of_misses_can_be_left_out_but_not_more():
    # ten folds, one miss: nine inside is exactly 90%, so no stretch at all
    assert factors_from(monthly(1, [100] * 9 + [70])).lower == 1.0
    # eleven folds, two misses: ceil(9.9) = 10 must be inside, so the larger miss is not
    f = factors_from(monthly(1, [100] * 9 + [85, 70]))
    assert f.lower == pytest.approx(1.5)


def test_the_factor_is_never_below_one():
    assert factors_from(monthly(1, [100] * 6)) == Factors(1.0, 1.0, 6)


def test_fewer_than_five_eligible_folds_learn_nothing():
    f = factors_from(monthly(1, [70] * 4))
    assert f.learned is False and (f.lower, f.upper) == (1.0, 1.0)
    assert factors_from(monthly(1, [70] * 5)).learned is True


def test_each_side_has_its_own_factor():
    f = factors_from(monthly(3, [70, 70, 70, 125, 125, 100, 100, 100, 100, 100]))
    assert f.lower == pytest.approx(3.0)
    assert f.upper == pytest.approx(2.5)


def test_a_side_the_stretch_cannot_reach_is_left_alone_and_the_fold_counts_as_a_miss():
    folds = [make(date(2025, 1, 28), 1, 80, low=100.0)] * 5
    f = factors_from(folds)
    assert f.lower is None  # no finite factor would have held them
    low, _ = stretch_range(100.0, 100.0, 110.0, f)
    assert low == 100.0  # no width to stretch


# ---------------------------------------------------------------- the range


def test_the_range_stretches_away_from_its_median():
    low, high = stretch_range(90.0, 100.0, 110.0, Factors(2.0, 1.5, 10))
    assert (low, high) == (80.0, 115.0)


def test_a_stretched_lower_edge_is_never_below_zero():
    low, _ = stretch_range(40.0, 100.0, 110.0, Factors(5.0, 1.0, 10))
    assert low == 0.0


def test_a_spread_keeps_its_center_and_stretches_both_ranges():
    s = Spread(mean=101.0, p2_5=80.0, p10=90.0, p50=100.0, p90=110.0, p97_5=125.0)
    out = stretch_spread(s, Factors(2.0, 2.0, 10))
    assert (out.mean, out.p50) == (101.0, 100.0)
    assert (out.p10, out.p90) == (80.0, 120.0)
    assert (out.p2_5, out.p97_5) == (60.0, 150.0)


def test_a_range_belongs_to_the_smallest_tested_horizon_that_reaches_its_end():
    as_of = date(2026, 8, 31)
    assert horizon_for(as_of, date(2026, 9, 30)) == (1, False)
    assert horizon_for(as_of, date(2026, 10, 31)) == (3, False)
    assert horizon_for(as_of, date(2026, 11, 30)) == (3, False)
    assert horizon_for(as_of, date(2026, 12, 31)) == (6, False)
    assert horizon_for(as_of, date(2027, 2, 28)) == (6, False)
    assert horizon_for(as_of, date(2027, 3, 31)) == (6, True)  # longer than six months
    assert horizon_for(as_of, date(2027, 8, 31)) == (6, True)


# ---------------------------------------------------------------- eligibility, only the past


def test_a_fold_is_eligible_only_once_its_whole_horizon_has_ended():
    folds = [make(date(2026, 1, 31), 3, 100)]
    assert eligible_folds(folds, 3, date(2026, 4, 30)) == folds
    assert eligible_folds(folds, 3, date(2026, 4, 29)) == []
    assert eligible_folds(folds, 1, date(2026, 4, 30)) == []  # another horizon


def test_a_fold_without_a_range_is_not_eligible():
    f = Fold(date(2025, 1, 31), 1, Decimal(1), {}, None, None)
    assert eligible_folds([f], 1, date(2026, 1, 1)) == []


# ---------------------------------------------------------------- the rolling score


def test_the_first_folds_with_too_few_earlier_ones_are_not_scored():
    folds = monthly(1, [100] * 12)
    s = score_horizon(folds, 1, date(2026, 6, 30))
    # fold i has i earlier folds whose month has ended: scored from the sixth on
    assert s.scored == 7


def test_stretched_and_simulated_are_counted_on_the_same_scored_folds():
    # five folds that all fell 3 times short, then five more that do again
    folds = monthly(1, [70] * 12)
    s = score_horizon(folds, 1, date(2026, 6, 30))
    assert s.scored == 7
    assert s.inside_simulated == 0
    assert s.inside_stretched == 7  # the factor 3 reaches every one of them
    assert s.median_width_simulated == 20.0


def test_the_stretched_width_is_the_stretched_range():
    folds = monthly(1, [70] * 12)
    s = score_horizon(folds, 1, date(2026, 6, 30))
    # lower 3x the 10 below the median, upper unchanged: 30 + 10
    assert s.median_width_stretched == pytest.approx(40.0)


def test_a_fold_is_scored_with_the_factors_known_at_its_own_date_only():
    # the first misses come late: early folds see factors of 1 and keep missing
    actuals = [100] * 8 + [70] * 4
    s = score_horizon(monthly(1, actuals), 1, date(2026, 6, 30))
    assert s.scored == 7
    # folds 5, 6 and 7 are inside. Fold 8 is the first miss, with nothing yet to learn from. Fold 9
    # sees one miss among nine eligible folds, and nine of nine must be inside, so the factor
    # reaches it; folds 10 and 11 likewise.
    assert s.inside_simulated == 3
    assert s.inside_stretched == 6


def test_factors_at_a_date_ignore_folds_that_had_not_ended():
    base = monthly(1, [100] * 12)
    at = date(
        2025, 8, 28
    )  # the fold of 28 July has ended (28 August); that of 28 August has not
    poisoned = base[:-4] + [make(f.cutoff, 1, 1) for f in base[-4:]]
    assert factors_at(base, 1, at) == factors_at(poisoned, 1, at)
    assert factors_at(base, 1, at).eligible == 7


def test_the_factors_in_use_at_the_as_of_date_come_from_every_eligible_fold():
    folds = monthly(1, [100] * 6 + [70] * 6)
    s = score_horizon(folds, 1, date(2026, 6, 30))
    assert s.factors.eligible == 12
    assert s.factors.lower == pytest.approx(3.0)


def test_no_range_folds_means_nothing_scored():
    s = score_horizon([], 6, date(2026, 6, 30))
    assert (s.scored, s.inside_simulated, s.inside_stretched) == (0, 0, 0)
    assert s.median_width_simulated is None and s.median_width_stretched is None
    assert s.factors.learned is False


def test_a_factor_of_one_leaves_the_range_bit_for_bit_alone():
    # 100 - 1 * (100 - 57.123456789) is not 57.123456789 in floating point
    assert stretch_range(57.123456789, 100.0, 143.987654321, Factors(1.0, 1.0, 10)) == (
        57.123456789,
        143.987654321,
    )


def unreachable_upper(n=5):
    """Folds whose median sits on p90 (no width above it) and whose actual lay above it."""
    return [make(date(2025, 1, 28), 1, 120, high=100.0)] * n


def test_a_learned_factor_that_is_infinite_is_unavailable_not_infinity():
    f = factors_from(unreachable_upper())
    assert f.upper is None and f.lower == 1.0 and f.learned


def test_an_unavailable_factor_leaves_a_side_with_width_at_its_simulated_edge_in_both_ranges():
    f = factors_from(unreachable_upper())
    # a later range whose upper side does have width: the unavailable factor must not stretch it
    low, high = stretch_range(90.0, 100.0, 110.0, f)
    assert (low, high) == (90.0, 110.0)
    s = Spread(mean=100.0, p2_5=80.0, p10=90.0, p50=100.0, p90=110.0, p97_5=125.0)
    out = stretch_spread(s, f)
    assert (out.p90, out.p97_5) == (110.0, 125.0)
    assert all(math.isfinite(v) for v in (out.p2_5, out.p10, out.p90, out.p97_5))


def test_an_unavailable_factor_on_a_zero_width_side_also_leaves_it_alone():
    f = factors_from(unreachable_upper())
    assert stretch_range(90.0, 100.0, 100.0, f) == (90.0, 100.0)


def test_scoring_counts_a_fold_on_an_unavailable_side_as_it_falls():
    # five folds that cannot be reached above, then a sixth whose range has width and whose actual is above it
    folds = unreachable_upper(5) + [make(date(2025, 7, 28), 1, 120)]
    s = score_horizon(folds, 1, date(2026, 6, 30))
    assert s.scored == 1
    assert (s.inside_simulated, s.inside_stretched) == (0, 0)
    assert s.factors.upper is None


def test_a_range_says_when_its_lower_edge_was_floored_at_zero():
    s = Spread(mean=100.0, p2_5=20.0, p10=40.0, p50=100.0, p90=110.0, p97_5=125.0)
    out, flags = stretch_spread_with_floors(
        s, Factors(2.0, 1.0, 10)
    )  # 100 - 2 * 60 < 0 for the 80%
    assert out.p10 == 0.0 and flags == (True, True)
    _, flags = stretch_spread_with_floors(
        s, Factors(1.5, 1.0, 10)
    )  # 80% -> 10, 95% -> -20
    assert flags == (False, True)
    _, flags = stretch_spread_with_floors(s, Factors(1.0, 1.0, 10))
    assert flags == (False, False)


def test_the_scorer_keeps_each_scored_date_with_the_factors_it_used():
    s = score_horizon(monthly(1, [100] * 8 + [70] * 4), 1, date(2026, 6, 30))
    assert [d.cutoff for d in s.detail] == sorted(d.cutoff for d in s.detail)
    assert len(s.detail) == s.scored == 7
    assert sum(d.inside_simulated for d in s.detail) == s.inside_simulated
    assert sum(d.inside_stretched for d in s.detail) == s.inside_stretched
    assert s.detail[0].lower == 1.0 and s.detail[-1].lower == 3.0

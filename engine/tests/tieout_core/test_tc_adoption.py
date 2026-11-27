"""Goal 2B: the adoption test for the capacity term, declared in
``capacity_rules`` before this code existed. Scored on created-pipeline
dollars, conditional on realized staffing: the per-rep rate is fitted only from
data before each cutoff, then applied to the ramped AE-months that occurred."""

from datetime import date, timedelta
from decimal import Decimal

from engine.tieout_core import capacity_rules as rules
from engine.tieout_core.adoption import (
    ADOPTED,
    NOT_SHOWN,
    AdoptionFold,
    decide,
    score_fold,
    staffing_variation,
)
from engine.tieout_core.capacity_config import CapacityConfig
from engine.tieout_core.records import Dataset, Deal, Observation
from engine.tieout_core.roster import Member, RampCurve

CFG = CapacityConfig(quota_roles=("ae",), ramp=(Decimal(1),), attrition=Decimal(0))


def ae(id, start, end=None):
    return Member(id, "ae", "mm", date.fromisoformat(start),
                  date.fromisoformat(end) if end else None, None)  # fmt: skip


def daily_deals(first: date, last: date, per_day_after: dict[date, int]) -> Dataset:
    """$100 deals created every day; ``per_day_after`` raises the daily count from a date."""
    deals, obs, n, count = [], [], 0, 1
    day = first
    while day <= last:
        count = max([count] + [c for d, c in per_day_after.items() if day >= d])
        for _ in range(count):
            n += 1
            deals.append(Deal(0, f"D{n}", "new_business", "mm", "S1", Decimal(100), day,
                              None, False, False))  # fmt: skip
            obs.append(
                Observation(f"D{n}", day, Decimal(100), day + timedelta(days=60))
            )
        day += timedelta(days=1)
    return Dataset(tuple(deals), (), tuple(obs))


def test_a_fold_by_hand_the_capacity_rate_follows_a_second_rep_the_flat_rate_does_not():
    # One tenured rep and one deal a day ($100) for the trailing year before the
    # cutoff 2025-01-31: 365 deals = $36,500 over 365 / 30.4375 ramped AE-months,
    # so $100 x 30.4375 = $3,043.75 per ramped AE-month.
    # Then a second rep joins on 2025-02-01 (ramp is 1 from day one here) and the
    # daily count doubles. Three months from the cutoff is the 89 days to 2025-04-30.
    #   flat      = $36,500 / 365 x 89                   = $8,900
    #   capacity  = $3,043.75 x (2 x 89 / 30.4375)       = $17,800
    #   actual    = 89 x 2 x $100                        = $17,800
    cutoff = date(2025, 1, 31)
    pop = daily_deals(date(2023, 1, 1), date(2025, 6, 30), {date(2025, 2, 1): 2})
    members = [ae("A", "2020-01-01"), ae("B", "2025-02-01")]
    f = score_fold(pop, members, CFG, cutoff, 3, since=date(2023, 1, 1))
    assert f.horizon == 3 and f.cutoff == cutoff
    assert f.flat == Decimal(8900)
    assert abs(f.capacity - Decimal(17800)) < Decimal("1e-9")
    assert f.actual == Decimal(17800)


def test_the_fold_uses_only_what_was_known_at_its_cutoff_to_fit_the_rate():
    cutoff = date(2025, 1, 31)
    members = [ae("A", "2020-01-01"), ae("B", "2025-02-01")]
    base = daily_deals(date(2023, 1, 1), date(2025, 6, 30), {date(2025, 2, 1): 2})
    rewritten = daily_deals(date(2023, 1, 1), date(2025, 6, 30), {date(2025, 2, 1): 9})
    a = score_fold(base, members, CFG, cutoff, 3, since=date(2023, 1, 1))
    b = score_fold(rewritten, members, CFG, cutoff, 3, since=date(2023, 1, 1))
    assert (a.flat, a.capacity) == (b.flat, b.capacity)  # fitted before the cutoff
    assert a.actual != b.actual  # only the thing being predicted moved


def test_staffing_variation_is_the_spread_over_the_mean_of_average_ramped_heads():
    # Average ramped heads: January 2, February 2, March 1 (one tenured rep leaves
    # on 2025-02-28). Spread 2 - 1 = 1 over the mean 5/3 = 0.6.
    members = [ae("A", "2020-01-01"), ae("B", "2020-01-01", "2025-02-28")]
    v = staffing_variation(
        members, RampCurve((), "entered"), date(2024, 12, 31), date(2025, 3, 31)
    )
    assert v == Decimal("0.6")


def _f(h, flat, cap, actual=Decimal(100)):
    return AdoptionFold(date(2025, 1, 31), h, actual, Decimal(flat), Decimal(cap))


def _folds(flat_err, cap_err, n=6):
    """n folds at each horizon whose flat and capacity absolute errors are given."""
    return [
        _f(h, 100 - flat_err, 100 - cap_err)
        for h in rules.SCORED_HORIZONS
        for _ in range(n)
    ]


def test_ten_percent_better_at_both_horizons_with_twenty_percent_variation_is_adopted():
    result = decide(_folds(flat_err=100, cap_err=90), Decimal("0.20"))
    assert (
        result.outcome == ADOPTED
    )  # the thresholds are inclusive: exactly 20% and 10%
    assert all(s.improvement == Decimal("0.1") for s in result.scores.values())


def test_just_short_of_ten_percent_at_either_horizon_is_not_shown():
    ok = _folds(100, 90)
    assert decide(ok, Decimal("0.5")).outcome == ADOPTED
    # six-month folds: flat error 100, capacity error 91 (9% better, not 10%)
    short = [_f(6, 0, 9) if f.horizon == 6 else f for f in ok]
    result = decide(short, Decimal("0.5"))
    assert result.outcome == NOT_SHOWN and "at 6 months" in result.reason


def test_less_than_twenty_percent_variation_is_not_shown_however_good_the_fit():
    result = decide(_folds(100, 1), Decimal("0.199"))
    assert result.outcome == NOT_SHOWN and "varied" in result.reason


def test_fewer_than_six_folds_at_a_horizon_is_not_shown():
    folds = _folds(100, 1, n=6)[:-1]  # five folds at 6 months
    result = decide(folds, Decimal("0.5"))
    assert result.outcome == NOT_SHOWN and "5 folds" in result.reason


def test_when_the_flat_rate_is_exact_capacity_cannot_be_ten_percent_better():
    result = decide(_folds(0, 0), Decimal("0.5"))
    assert result.outcome == NOT_SHOWN

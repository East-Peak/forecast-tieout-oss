from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from engine.tests.tieout_core.builders import write_profile
from engine.tieout_core.backtest import (
    MODEL,
    RUN_RATE,
    STAGE_WEIGHTED,
    HorizonScore,
    backtest,
    comparisons,
    fold,
    verdict,
    verdict_in_words,
)
from engine.tieout_core.load import load_profile
from engine.tieout_core.records import Dataset, Deal, Observation, Transition

AS_OF = date(2026, 6, 30)
START = date(2023, 7, 1)


def regular_history(start=START, end=AS_OF, observations=True) -> Dataset:
    """A deal created every 10 days, each won 45 days later for $100."""
    deals, transitions, obs = [], [], []
    created, n = start, 0
    while created <= end:
        n += 1
        close = created + timedelta(days=45)
        won = close <= end
        deals.append(
            Deal(
                0,
                f"D{n}",
                "new_business",
                "mm",
                "Won" if won else "S1",
                Decimal(100),
                created,
                close,
                won,
                won,
            )
        )
        transitions.append(Transition(f"D{n}", "S1", created))
        if won:
            transitions.append(Transition(f"D{n}", "Won", close))
        obs.append(Observation(f"D{n}", created, Decimal(100), close))
        created += timedelta(days=10)
    transitions.sort(key=lambda t: (t.deal_id, t.on))
    return Dataset(
        tuple(deals), tuple(transitions), tuple(obs) if observations else None
    )


@pytest.fixture(scope="module")
def profile(tmp_path_factory):
    return load_profile(write_profile(tmp_path_factory.mktemp("p")))


@pytest.fixture(scope="module")
def result(profile):
    return backtest(regular_history(), AS_OF, profile, draws=200)


def test_folds_need_three_matured_snapshots_and_a_complete_horizon(result):
    counts = {s.horizon: s.folds for s in result.scores}
    assert counts == {1: 21, 3: 19, 6: 16}
    assert min(f.cutoff for f in result.folds) == date(2024, 9, 30)


def test_actuals_are_bookings_inside_the_fold_window(result):
    f = next(
        f for f in result.folds if f.horizon == 1 and f.cutoff == date(2026, 5, 30)
    )
    population = regular_history()
    expected = sum(
        (
            d.arr
            for d in population.deals
            if d.is_won and date(2026, 5, 30) < d.close <= date(2026, 6, 30)
        ),
        Decimal(0),
    )
    assert f.actual == expected


def test_every_method_is_scored(result):
    s1 = next(s for s in result.scores if s.horizon == 1)
    assert set(s1.mae) == {RUN_RATE, STAGE_WEIGHTED, MODEL}
    assert all(v is not None for v in s1.mae.values())
    assert 0 <= s1.coverage80 <= 1 and 0 <= s1.coverage95 <= 1


def test_a_fold_cannot_see_data_after_its_cutoff(profile):
    cutoff = date(2025, 3, 31)
    clean = regular_history()
    # Rewrite the future: later wins become losses at ten times the amount, and
    # a burst of extra deals appears after the cutoff.
    rewritten = []
    for d in clean.deals:
        if d.close > cutoff or d.created > cutoff:
            d = replace(
                d, arr=Decimal(1000), stage="Lost", is_won=False, is_closed=True
            )
        rewritten.append(d)
    extra = [
        Deal(
            0,
            f"X{i}",
            "new_business",
            "mm",
            "Won",
            Decimal(5000),
            cutoff + timedelta(days=i),
            cutoff + timedelta(days=i + 5),
            True,
            True,
        )
        for i in range(1, 40)
    ]
    poisoned = Dataset(tuple(rewritten + extra), clean.transitions, clean.observations)
    a = fold(clean, cutoff, (1, 3), profile, draws=100)
    b = fold(poisoned, cutoff, (1, 3), profile, draws=100)
    assert [(x.horizon, x.forecasts, x.range80) for x in a] == [
        (x.horizon, x.forecasts, x.range80) for x in b
    ]
    assert [x.actual for x in a] != [x.actual for x in b]


def test_without_past_amounts_the_dollar_backtest_is_unavailable(profile):
    r = backtest(regular_history(observations=False), AS_OF, profile, draws=50)
    s1 = next(s for s in r.scores if s.horizon == 1)
    assert s1.mae[MODEL] is None and s1.mae[RUN_RATE] is not None
    assert r.verdict == "not enough history to say"
    assert "deal_observations" in r.verdict_reason


def test_short_history_gives_zero_folds_and_says_so(profile):
    r = backtest(regular_history(start=date(2025, 5, 1)), AS_OF, profile, draws=50)
    assert all(s.folds == 0 for s in r.scores)
    assert r.verdict == "not enough history to say"


def _score(h, folds, model, rr, sw):
    mae = {MODEL: Decimal(model), RUN_RATE: Decimal(rr), STAGE_WEIGHTED: Decimal(sw)}
    return HorizonScore(h, folds, mae, {k: Decimal(0) for k in mae}, 0.8, 0.95)


def test_verdict_needs_six_folds_at_one_and_three_months():
    assert (
        verdict([_score(1, 6, 1, 2, 2), _score(3, 5, 1, 2, 2)])[0]
        == "not enough history to say"
    )


def test_verdict_yes_only_if_the_model_beats_both_baselines_at_both_horizons():
    assert verdict([_score(1, 6, 1, 2, 2), _score(3, 6, 1, 2, 2)])[0] == "yes"
    assert (
        verdict([_score(1, 6, 1, 2, 2), _score(3, 6, 2, 3, 2)])[0] == "no"
    )  # ties a baseline
    assert verdict([_score(1, 9, 3, 2, 4), _score(3, 9, 1, 2, 2)])[0] == "no"


def test_coverage_counts_only_folds_that_had_a_range():
    from engine.tieout_core.backtest import Fold, score_horizon

    def f(range80):
        forecasts = {RUN_RATE: Decimal(1), STAGE_WEIGHTED: None, MODEL: None}
        return Fold(AS_OF, 1, Decimal(5), forecasts, range80, range80)

    s = score_horizon(1, [f((0.0, 10.0))] + [f(None)] * 7)
    assert (s.folds, s.range_folds, s.coverage80) == (8, 1, 1.0)


def test_folds_are_never_scored_past_the_last_observed_date(profile):
    # An as-of months after the export would otherwise score folds against
    # bookings nobody observed (zeros).
    from engine.tieout_core.fiscal import add_months

    r = backtest(regular_history(), date(2026, 12, 31), profile, draws=20)
    assert r.folds
    assert max(add_months(f.cutoff, f.horizon) for f in r.folds) <= AS_OF


def _by(cs):
    return {
        (c.horizon, m): (c.model_error, e, o)
        for c in cs
        for m, (e, o) in c.against.items()
    }


def test_comparisons_say_per_horizon_and_baseline_which_error_is_lower():
    cs = comparisons([_score(1, 6, 1, 2, 5), _score(3, 6, 3, 2, 3)])
    assert [c.horizon for c in cs] == [1, 3]
    assert _by(cs) == {
        (1, RUN_RATE): (Decimal(1), Decimal(2), "model lower"),
        (1, STAGE_WEIGHTED): (Decimal(1), Decimal(5), "model lower"),
        (3, RUN_RATE): (Decimal(3), Decimal(2), "baseline lower"),
        (3, STAGE_WEIGHTED): (Decimal(3), Decimal(3), "tie"),
    }


def test_there_are_no_comparisons_when_the_verdict_is_not_enough_history():
    assert comparisons([_score(1, 6, 1, 2, 2), _score(3, 5, 1, 2, 2)]) == []
    unscored = HorizonScore(
        1, 9, {MODEL: None, RUN_RATE: Decimal(1), STAGE_WEIGHTED: None}, {}, None, None
    )
    assert comparisons([unscored, _score(3, 9, 1, 2, 2)]) == []


def test_a_verdict_of_no_is_exactly_a_comparison_that_is_not_model_lower():
    for scores in (
        [_score(1, 6, 1, 2, 2), _score(3, 6, 1, 2, 2)],
        [_score(1, 6, 1, 2, 2), _score(3, 6, 2, 3, 2)],
        [_score(1, 9, 3, 2, 4), _score(3, 9, 1, 2, 2)],
    ):
        all_lower = all(
            o == "model lower" for *_, o in _by(comparisons(scores)).values()
        )
        assert (verdict(scores)[0] == "yes") is all_lower


def words(scores, result=None, observed=True):
    return verdict_in_words(result or verdict(scores)[0], scores, observed)


def test_in_words_for_a_yes_names_both_horizons():
    text = words([_score(1, 6, 1, 2, 2), _score(3, 6, 1, 2, 2)])
    assert text == (
        "The fitted model's average miss is smaller than both simple yardsticks, "
        "one month ahead and three months ahead."
    )


def test_in_words_for_a_no_names_only_the_horizons_that_lost():
    assert words([_score(1, 6, 1, 2, 2), _score(3, 6, 2, 3, 2)]) == (
        "The fitted model's average miss is not smaller than both simple yardsticks "
        "three months ahead."
    )
    assert words([_score(1, 9, 3, 2, 4), _score(3, 9, 5, 2, 2)]) == (
        "The fitted model's average miss is not smaller than both simple yardsticks "
        "one month ahead and three months ahead."
    )


def test_in_words_for_too_few_past_dates_says_how_many_are_needed():
    assert words([_score(1, 6, 1, 2, 2), _score(3, 5, 1, 2, 2)]) == (
        "Not enough past forecast dates to compare: the back-test needs at least six "
        "at both one month and three months ahead."
    )


def test_in_words_for_a_method_that_cannot_be_scored_in_dollars():
    unscored = HorizonScore(
        1, 9, {MODEL: None, RUN_RATE: Decimal(1), STAGE_WEIGHTED: None}, {}, None, None
    )
    scores = [unscored, _score(3, 9, 1, 2, 2)]
    assert words(scores) == (
        "Not every method could be scored in dollars on the past, so there is nothing to compare."
    )
    assert words(scores, observed=False) == (
        "The past cannot be scored in dollars without a record of past open deals, "
        "so there is nothing to compare."
    )


def test_every_in_words_sentence_is_free_of_digits():
    unscored = HorizonScore(
        1, 9, {MODEL: None, RUN_RATE: Decimal(1), STAGE_WEIGHTED: None}, {}, None, None
    )
    for scores in (
        [_score(1, 6, 1, 2, 2), _score(3, 6, 1, 2, 2)],
        [_score(1, 6, 1, 2, 2), _score(3, 6, 2, 3, 2)],
        [_score(1, 6, 1, 2, 2), _score(3, 5, 1, 2, 2)],
        [unscored, _score(3, 9, 1, 2, 2)],
    ):
        for observed in (True, False):
            assert not any(ch.isdigit() for ch in words(scores, observed=observed))

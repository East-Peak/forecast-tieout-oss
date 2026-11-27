"""The line under a company's name says, in words and without figures, how the
company's as-signed report came out. It is built from the report's statuses by one
mapping, so it cannot go stale; each branch of the mapping is tested here."""

import itertools

import pytest

from engine.tieout_core.company_line import (
    BETTER,
    HEADCOUNT,
    YEAR,
    company_line,
    year_status,
)


def report(gap="1910275.71", capacity="adopted", better="yes"):
    return {
        "gap": {"fiscal_year": {"gap": gap}},
        "roster_capacity": {"decision": {"outcome": capacity}},
        "verdicts": {"forecast_better_than_baselines": {"verdict": better}},
    }


@pytest.mark.parametrize(
    "gap,status",
    [("1.00", "short"), ("0.00", "on"), ("-0.01", "ahead"), (None, "unknown")],
)
def test_the_year_is_short_of_on_or_ahead_of_target_by_the_sign_of_the_gap(gap, status):
    assert year_status(report(gap=gap)) == status


@pytest.mark.parametrize(
    "gap,phrase",
    [
        ("1.00", "Short of target this year."),
        ("0.00", "On target this year."),
        ("-5.00", "Ahead of target this year."),
        (None, "No full-year forecast yet."),
    ],
)
def test_each_year_branch_has_its_phrase(gap, phrase):
    assert company_line(report(gap=gap)).startswith(phrase + " ")


@pytest.mark.parametrize(
    "capacity,phrase",
    [
        ("adopted", "Headcount explains pipeline"),
        ("not shown", "The history cannot say whether headcount explains pipeline"),
        ("unavailable", "Headcount cannot be tested without a roster"),
    ],
)
def test_each_headcount_branch_has_its_phrase(capacity, phrase):
    assert phrase in company_line(report(capacity=capacity))


@pytest.mark.parametrize(
    "better,phrase",
    [
        ("yes", "the fitted forecast beats the simple yardsticks"),
        ("no", "the fitted forecast does not yet beat the simple yardsticks"),
        (
            "not enough history to say",
            "the history is too short to compare the fitted forecast with the simple yardsticks",
        ),
    ],
)
def test_each_baseline_branch_has_its_phrase(better, phrase):
    assert company_line(report(better=better)).endswith(f"; {phrase}.")


def test_the_line_has_the_shape_of_the_example():
    assert company_line(report(better="no")) == (
        "Short of target this year. Headcount explains pipeline; "
        "the fitted forecast does not yet beat the simple yardsticks."
    )


def test_every_status_has_a_phrase_and_every_combination_is_one_digit_free_line():
    assert set(YEAR) == {"short", "on", "ahead", "unknown"}
    assert set(HEADCOUNT) == {"adopted", "not shown", "unavailable"}
    assert set(BETTER) == {"yes", "no", "not enough history to say"}
    for gap, capacity, better in itertools.product(
        ("1.00", "0.00", "-1.00", None), HEADCOUNT, BETTER
    ):
        line = company_line(report(gap, capacity, better))
        assert not any(ch.isdigit() for ch in line), line
        assert "\n" not in line and line.endswith(".")


def test_an_unknown_status_is_an_error_not_a_silent_blank():
    with pytest.raises(KeyError):
        company_line(report(capacity="maybe"))

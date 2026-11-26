from decimal import Decimal

import pytest

from engine.tieout_core.rates import Rate, RateBook, wilson


def _rate(name, value="0.5"):
    return Rate(
        name, Decimal(value), "def", "num", "den", "cohort", "365 days", 4, "fitted"
    )


def test_a_rate_has_one_definition():
    book = RateBook()
    book.add(_rate("win"))
    with pytest.raises(ValueError, match="already defined"):
        book.add(_rate("win", "0.6"))


def test_rates_are_kept_in_order_and_found_by_name():
    book = RateBook()
    book.add(_rate("a"))
    book.add(_rate("b", "0.25"))
    assert [r.name for r in book] == ["a", "b"]
    assert book["b"].value == Decimal("0.25")


def test_wilson_interval_matches_the_textbook_value():
    low, high = wilson(2, 4)
    assert low == pytest.approx(0.1500, abs=1e-4)
    assert high == pytest.approx(0.8500, abs=1e-4)
    assert wilson(0, 0) == (0.0, 1.0)

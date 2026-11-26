from decimal import Decimal

from engine.tieout_core.forecast import Forecast
from engine.tieout_core.report import _components_check

THIRD, SEVENTH, ELEVENTH, NINETEENTH = (Decimal(1) / Decimal(n) for n in (3, 7, 11, 19))


def test_parts_check_ignores_rounding_in_the_28th_digit():
    # Summed by part or by month, these differ only at the last decimal digit.
    f = Forecast("x", {"p": {"m1": THIRD, "m2": SEVENTH}, "q": {"m1": ELEVENTH, "m2": NINETEENTH}})
    assert f.total() != f.window_total("m1") + f.window_total("m2")
    assert _components_check([f], ["m1", "m2"]).passed


def test_parts_check_catches_a_missing_month():
    f = Forecast("x", {"p": {"m1": Decimal(1), "m2": Decimal(2)}})
    assert not _components_check([f], ["m1"]).passed

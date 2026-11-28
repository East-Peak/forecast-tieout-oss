"""Moving a cohort's wins in time, by hand: the toy company's timing is two wins, ten and twenty
days after creation, each with half the weight. The as-of date is April 20, so April ends on day 10,
May on day 41, June on day 71."""

from decimal import Decimal
from fractions import Fraction

from engine.tieout_core.cycle import Transport
from engine.tieout_core.fit import Timing

D = Decimal
EDGES = [10, 41, 71, 102]  # April, May, June, July


def transport(timing=None):
    return Transport(timing or Timing((10, 20), "t"), EDGES)


def blocks(pieces):
    return [(p.original, p.moved, p.weight, p.moment) for p in pieces]


def test_unmoved_a_cohort_lands_where_it_was_to_in_one_block_a_month():
    # created on day 1: wins on days 11 and 21, both in May
    assert blocks(transport().pieces(1, Fraction(1))) == [(1, 1, D(2), D(30))]
    # created on day 25: wins on days 35 and 45, in May and June
    assert blocks(transport().pieces(25, Fraction(1))) == [
        (1, 1, D(1), D(10)),
        (2, 2, D(1), D(20)),
    ]


def test_a_longer_cycle_moves_the_wins_and_keeps_the_month_they_were_priced_in():
    # day 1, lags tripled to 30 and 60: days 31 (May) and 61 (June); both were to land in May
    got = blocks(transport().pieces(1, Fraction(3)))
    assert got == [(1, 1, D(1), D(30)), (1, 2, D(1), D(60))]


def test_a_cycle_so_long_that_the_wins_leave_the_months_shown_puts_them_in_the_tail():
    got = transport().pieces(1, Fraction(100))  # lags 1000 and 2000 days
    assert blocks(got) == [
        (1, 4, D(2), D(3000))
    ]  # the moved month is the tail, index 4


def test_a_shorter_cycle_pulls_in_a_win_that_was_to_land_beyond_the_months_shown():
    # day 90: lags 10 and 20 land on days 100 (July) and 110 (past July's end on day 102: the tail)
    assert blocks(transport().pieces(90, Fraction(1))) == [
        (3, 3, D(1), D(10)),
        (4, 4, D(1), D(20)),
    ]
    # halved to 5 and 10: days 95 and 100, both July; the second was priced in the tail
    assert blocks(transport().pieces(90, Fraction(1, 2))) == [
        (3, 3, D(1), D(5)),
        (4, 3, D(1), D(10)),
    ]


def test_the_ceiling_is_exact_at_the_boundaries():
    # 10 * 21/10 = 21 exactly, one more tenth makes 22; 10 * 3/2 = 15, 15 * 7/5 = 21
    assert transport().scaled(Fraction(21, 10))[0] == (21, 42)
    assert transport().scaled(Fraction(211, 100))[0] == (22, 43)
    assert transport().scaled(Fraction(1, 10))[0] == (1, 2)
    assert transport().scaled(Fraction(1, 100))[0] == (
        1,
        1,
    )  # a positive lag never rounds to zero
    assert transport().scaled(Fraction(0))[0] == (0, 0)


def test_weights_are_kept_and_the_total_weight_of_a_cohort_is_conserved_with_its_tail():
    t = transport(Timing((10, 20, 30), "t", (D("0.5"), D("0.25"), D("0.25"))))
    for day in (1, 30, 60, 100):
        for f in (Fraction(1, 2), Fraction(1), Fraction(7, 5), Fraction(2)):
            pieces = t.pieces(day, f)
            assert sum(p.weight for p in pieces) == D(
                1
            )  # nothing dropped, nothing renormalized
            assert sum(p.moment for p in pieces) == sum(
                D(l) * w for l, w in zip(t.scaled(f)[0], t.weights)
            )

"""An owner's expected wins, checked leaf by leaf against a hand computation, not only in sum."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from engine.tests.tieout_core.test_tc_lanes_flows import AS_OF, CAL, model, open_deal
from engine.tieout_core import lanes_flows as flows
from engine.tieout_core import lanes_owners as owners
from engine.tieout_core.lanes_basis import Sizes

D = Decimal
CENT = D("0.01")


def setup(segment_size):
    deal = replace(open_deal(date(2026, 3, 1), "1000"), owner_id="x")
    m = model()  # pooled won size 1000
    horizon = (CAL.year.end - AS_OF).days
    created = [D(1)] * horizon
    state = SimpleNamespace(
        ground=SimpleNamespace(model=m, pop=SimpleNamespace(deals=(deal,)), as_of=AS_OF)
    )
    seg_new, _ = flows.new_flows(m, {"a": created}, AS_OF, CAL)
    sizes = {"a": Sizes(D(segment_size), "", D(10), "")}
    priced = flows.price(seg_new, sizes, D(1000))
    existing = flows.existing_flows(m, (deal,), AS_OF, CAL)
    tied = {}
    for k in set(existing) | set(priced):
        f = existing.get(k, flows.ZERO_FLOW) + priced.get(k, flows.ZERO_FLOW)
        tied[k] = flows.Flow(f.wins.quantize(D("0.0001")), f.bookings.quantize(CENT), f.days.quantize(CENT))  # fmt: skip
    lane = {("a", "y"): created}
    return state, lane, seg_new, priced, existing, tied


def test_modeled_wins_are_priced_as_the_segment_was_normalized_to_the_pooled_size():
    """A segment whose own mean is twice the pooled size is still shared out at the pooled total,
    so an owner's modeled bookings are their wins times the segment's normalized price."""
    state, lane, seg_new, priced, existing, tied = setup(2000)
    got, _ = owners.remainder(state, CAL, lane, priced, tied, {})
    for (seg, q, origin), f in seg_new.items():
        y = got[(("a", "y"), q, origin)]
        assert abs(y.bookings - f.wins * 1000) <= CENT, (q, origin)  # not f.wins * 2000
        assert abs(y.wins - f.wins) <= D("0.0001")
        x = got.get((("a", "x"), q, origin))
        mine = existing.get((seg, q, origin), flows.ZERO_FLOW)
        assert abs((x.bookings if x else 0) - mine.bookings) <= CENT


def test_the_owners_add_back_to_the_segment_to_the_cent_in_every_leaf():
    state, lane, _, priced, _, tied = setup(2000)
    got, _ = owners.remainder(state, CAL, lane, priced, tied, {})
    for (seg, q, origin), f in tied.items():
        mine = [
            v for (ln, qq, o), v in got.items() if (ln[0], qq, o) == (seg, q, origin)
        ]
        assert sum(v.bookings for v in mine) == f.bookings
        assert sum(v.wins for v in mine) == f.wins


# ---- creation follows who is employed on each forecast day


def flat_state(ends, shares=(("x", "0.6"), ("y", "0.4"))):
    from engine.tieout_core.lanes_alloc import OwnerBasis
    from engine.tieout_core.roster import Member

    members = tuple(Member(i, "ae", "a", date(2024, 1, 1), e, D(1)) for i, e in ends.items())  # fmt: skip
    state = SimpleNamespace(
        ground=SimpleNamespace(
            cap=SimpleNamespace(adopted=False, members=members),
            model=SimpleNamespace(
                new_pipeline=SimpleNamespace(
                    created_per_day=D(2), mean_created_arr=D(1)
                )
            ),
            as_of=AS_OF,
        )
    )
    owned = tuple(OwnerBasis("a", i, i, True, D(1), 365, D(365), D(0), 0, D(s)) for i, s in shares)  # fmt: skip
    basis = SimpleNamespace(segments=(SimpleNamespace(key="a", creation_share=D(1)),), owners=owned)  # fmt: skip
    return state, basis


def test_a_rep_who_leaves_the_day_after_the_as_of_date_creates_for_one_day_only():
    from datetime import timedelta

    state, basis = flat_state({"x": AS_OF + timedelta(days=1), "y": None})
    got = owners.series(state, basis, CAL, (), (), ["a"])
    x, y = got[("a", "x")], got[("a", "y")]
    assert x[0] == D("1.2") and not any(x[1:])  # 2 deals a day, 60% share, day one only
    assert y[0] == D("0.8") and y[1] == D(2)  # day two on, the shares go to y
    assert all(a + b == D(2) for a, b in zip(x, y))  # the segment's creation is whole


def test_a_segment_whose_last_rep_leaves_mid_forecast_hands_the_rest_to_unassigned():
    from datetime import timedelta

    gone = AS_OF + timedelta(days=3)
    state, basis = flat_state({"x": gone, "y": gone})
    got = owners.series(state, basis, CAL, (), (), ["a"])
    bucket = got[("a", "unassigned")]
    assert not any(bucket[:3]) and all(v == D(2) for v in bucket[3:])
    assert all(a + b + c == D(2) for a, b, c in zip(got[("a", "x")], got[("a", "y")], bucket))  # fmt: skip


def test_the_adopted_path_already_stops_a_rep_on_their_last_day(built):
    from dataclasses import replace
    from datetime import timedelta

    _, state, basis, _ = built
    if not state.ground.cap.adopted:
        return
    g = state.ground
    m = next(m for m in g.cap.members if m.end is None and m.segment)
    left = replace(m, end=g.as_of + timedelta(days=1))
    roster = replace(g.cap.roster, members=tuple(left if x is m else x for x in g.cap.members))  # fmt: skip
    changed = replace(state, ground=replace(g, cap=replace(g.cap, roster=roster)))
    got = owners.series(changed, basis, flows.Calendar(state.profile.fiscal_year), (), (), [m.segment])  # fmt: skip
    mine = got[(m.segment, m.id)]
    assert mine[0] > 0 and not any(mine[1:])


# ---- an action's wins go to the owners whose deals it changes


def test_an_actions_wins_follow_the_deals_it_changes_not_the_owners_baseline_wins():
    """Two owners each create ten deals in the quarter: one on May 10, one on July 5. The segment
    wins at 20%, and from July 1 at 40%. The first owner's deals were created before the action
    started, so they win two; the second's win four. Sharing the segment's six by the owners'
    baseline wins (two and two) would say three and three."""
    may, july = (date(2026, 5, 10) - AS_OF).days, (date(2026, 7, 5) - AS_OF).days
    start = (date(2026, 7, 1) - AS_OF).days
    days = (CAL.year.end - AS_OF).days

    def ten_on(day):
        return [D(10) if t == day else D(0) for t in range(1, days + 1)]

    lanes = {("a", "may"): ten_on(may), ("a", "july"): ten_on(july)}
    change = [D("0.2") if t >= start else D(0) for t in range(1, days + 1)]
    effect = SimpleNamespace(changes={"a": change})
    state = SimpleNamespace(
        ground=SimpleNamespace(
            model=model(), pop=SimpleNamespace(deals=()), as_of=AS_OF
        )
    )
    # both created in the second quarter and winning ten and twenty days on, in the same quarter
    tied = {("a", 1, 2): flows.Flow(D(6), D(6000), D(90))}
    priced = {("a", 1, 2): flows.Flow(D(6), D(6000), D(90))}
    got, _ = owners.remainder(state, CAL, lanes, priced, tied, {}, effect)
    by_owner = {lane[1]: f for (lane, q, origin), f in got.items()}
    assert by_owner["may"].wins == D(2) and by_owner["july"].wins == D(4)
    assert by_owner["may"].bookings == D(2000) and by_owner["july"].bookings == D(4000)
    assert sum(f.wins for f in by_owner.values()) == D(
        6
    )  # and they add to the segment exactly
    plain, _ = owners.remainder(state, CAL, lanes, priced, tied, {})
    assert {lane[1]: f.wins for (lane, _, _), f in plain.items()} == {"may": D(3), "july": D(3)}  # fmt: skip

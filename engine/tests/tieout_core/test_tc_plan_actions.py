"""Actions on a slice: the plan item, how a plan file or the editor's plan names it, and what
it refuses."""

from datetime import date
from decimal import Decimal

import pytest

from engine.tieout_core.plan import (
    Plan,
    PlanAction,
    PlanHire,
    PlanProgram,
    parse_plan,
)
from engine.tieout_core.roster import Member

AS_OF = date(2026, 8, 31)
MEMBERS = (
    Member("A", "ae", "enterprise", date(2025, 1, 1), None, None),
    Member("B", "ae", "mid_market", date(2025, 1, 1), None, None),
)


def action(**over):
    base = {
        "id": "ent-win",
        "name": "Enterprise win rate",
        "driver": "win_rate",
        "slice": "enterprise",
        "start": "2026-10",
        "ramp_months": 2,
        "target": "0.25",
    }
    return {**base, **over}


def parse(*actions, **rest):
    return parse_plan({"actions": list(actions), **rest}, AS_OF, MEMBERS, "plan.yaml")


def refused(*actions):
    with pytest.raises(ValueError) as caught:
        parse(*actions)
    return str(caught.value)


def test_an_action_has_an_id_a_name_a_driver_a_slice_a_start_a_ramp_and_a_target():
    got = parse(action()).actions
    assert got == (
        PlanAction(
            "ent-win",
            "Enterprise win rate",
            "win_rate",
            "enterprise",
            date(2026, 10, 1),
            2,
            Decimal("0.25"),
        ),
    )


def test_the_company_is_a_slice_and_a_ramp_of_zero_is_immediate_and_the_default():
    plan = parse(action(slice="company", id="all"))
    assert plan.actions[0].segment is None and plan.actions[0].ramp_months == 2
    bare = parse({k: v for k, v in action().items() if k != "ramp_months"})
    assert bare.actions[0].ramp_months == 0
    assert parse(action(ramp_months=0)).actions[0].ramp_months == 0


def test_a_name_defaults_to_the_id():
    bare = {k: v for k, v in action().items() if k != "name"}
    assert parse(bare).actions[0].name == "ent-win"


def test_an_action_is_a_plan_item_after_hires_and_programs_and_keeps_its_place():
    plan = parse(
        action(),
        action(id="b", slice="mid_market"),
        hires=[{"segment": "enterprise", "start": "2026-09", "count": 1}],
        programs=[{"name": "P", "pipeline": 1000, "start": "2026-09"}],
    )
    kinds = [type(i) for i in plan.items()]
    assert kinds == [PlanHire, PlanProgram, PlanAction, PlanAction]
    assert [a.id for a in plan.actions] == ["ent-win", "b"]


def test_a_plan_with_no_actions_is_unchanged():
    plan = parse_plan({"hires": []}, AS_OF, MEMBERS, "plan.yaml")
    assert plan.actions == () and plan == Plan((), ())


@pytest.mark.parametrize("target", ["0", "0.0", 0, "1", 1, "0.2193", 0.5])
def test_the_probability_bounds_are_zero_and_one_inclusive(target):
    assert parse(action(target=target)).actions[0].target == Decimal(str(target))


@pytest.mark.parametrize("target", ["-0.01", "1.0001", 2, -1, "x", None, "nan"])
def test_a_target_outside_zero_and_one_or_no_number_is_refused(target):
    text = refused(action(target=target))
    assert text.startswith("plan.yaml: actions[1]: ") and "target" in text


def test_a_segment_nobody_is_in_is_refused_and_the_message_names_it():
    text = refused(action(slice="strategic"))
    assert "actions[1]" in text and "strategic" in text and "segment" in text


def test_an_unknown_driver_is_refused_and_lists_what_is_supported():
    text = refused(action(driver="won_arr"))
    assert "driver" in text and "win_rate" in text
    assert "driver" in refused({k: v for k, v in action().items() if k != "driver"})


def test_a_start_not_after_the_as_of_date_is_refused_as_every_other_item_is():
    text = refused(action(start="2026-08"))
    assert "actions[1]" in text and "not after the as-of date" in text
    assert "2026-09" not in text
    assert parse(action(start="2026-09")).actions[0].start == date(2026, 9, 1)
    assert "start" in refused(action(start="soon"))


@pytest.mark.parametrize("ramp", [-1, 1.5, "2", True])
def test_a_ramp_is_a_whole_number_of_months_not_below_zero(ramp):
    assert "ramp_months" in refused(action(ramp_months=ramp))


def test_an_action_needs_an_id_and_ids_are_unique():
    assert "id" in refused(action(id=""))
    assert "id" in refused({k: v for k, v in action().items() if k != "id"})
    text = refused(action(), action(slice="mid_market"))
    assert "actions[2]" in text and "ent-win" in text and "actions[1]" in text


def test_two_actions_on_the_same_driver_and_slice_are_refused_whatever_their_dates():
    text = refused(action(), action(id="b", start="2027-01", target="0.3"))
    assert "actions[2]" in text and "overlaps actions[1]" in text
    assert "win_rate" in text and "enterprise" in text


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_the_company_overlaps_every_segment_whichever_is_listed_first(order):
    pair = [action(slice="company", id="all"), action(id="b", slice="mid_market")]
    text = refused(*(pair[i] for i in order))
    assert "overlaps actions[1]" in text and "company" in text


def test_different_segments_do_not_overlap():
    assert len(parse(action(), action(id="b", slice="mid_market")).actions) == 2


def test_shapes_that_are_not_actions_are_refused_with_a_message_not_a_crash():
    with pytest.raises(ValueError, match="actions"):
        parse_plan({"actions": [["not", "a mapping"]]}, AS_OF, MEMBERS, "plan.yaml")


def test_a_label_names_the_action_and_a_slice_label_the_slice():
    a = parse(action()).actions[0]
    assert a.label == "Enterprise win rate"
    assert a.slice_label == "Enterprise"
    assert parse(action(slice="company")).actions[0].slice_label == "Company"


# ------------------------------------------------------------ dispatch by kind


def _ground():
    from types import SimpleNamespace

    cap = SimpleNamespace(adopted=True, cfg=None)
    return SimpleNamespace(cap=cap, windows=[], as_of=AS_OF, fy_end=date(2027, 1, 31))


def test_an_action_is_not_a_program_so_it_adds_no_hires_and_no_pipeline():
    from engine.tieout_core.actions import plan_inputs

    plan = parse(
        action(), programs=[{"name": "P", "pipeline": 1000, "start": "2026-09"}]
    )
    hires, inflows = plan_inputs(_ground(), plan)
    assert (
        hires == () and len(inflows) == 0
    )  # no windows: the program's pipeline is clipped
    with_none = plan_inputs(_ground(), Plan((), (), parse(action()).actions))
    assert with_none == ((), ())


def test_an_item_of_a_kind_nobody_handles_is_an_error_not_a_program():
    from types import SimpleNamespace

    from engine.tieout_core.actions import plan_inputs

    stray = SimpleNamespace(items=lambda: [object()], members_for=lambda i: ())
    with pytest.raises(TypeError, match="plan item"):
        plan_inputs(_ground(), stray)

"""The lanes replayed from the raw deals and through the whole forward function."""

import copy

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions, lanes_replay
from engine.tieout_core.plan import load_plan


def inputs(company, state, scenario):
    sc = next(s for s in gen.SCENARIOS if s.id == scenario)
    if sc.plan is None:
        return (), ()
    with gen.in_repo():
        plan = load_plan(gen.PROFILES / company / sc.plan, gen.AS_OF, state.cap.members)
    return actions.plan_inputs(state.ground, plan)


def test_every_committed_scenario_replays(built):
    company, state, _, docs = built
    for scenario, (_, doc) in docs.items():
        hires, inflows = inputs(company, state, scenario)
        assert lanes_replay.replay(state, doc, hires, inflows) == []


def test_a_wrong_actual_a_wrong_forecast_and_a_wrong_opening_are_each_found(built):
    company, state, _, docs = built
    _, doc = docs["demo-plan"]
    hires, inflows = inputs(company, state, "demo-plan")

    def found(column, mode, value):
        edited = copy.deepcopy(doc)
        edited["periods"][0]["rows"][0]["cells"][column][mode] = value
        return lanes_replay.replay(state, edited, hires, inflows)

    assert any("created" in p for p in found("created", "actual", "1.0000"))
    assert any("bookings" in p for p in found("bookings", "forecast", "1.00"))
    assert any("open" in p for p in found("open", "actual", "1"))
    assert any("win_rate" in p for p in found("win_rate", "actual", "0.9999"))

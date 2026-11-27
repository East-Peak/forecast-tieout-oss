"""The probe's fast path gives the very forecast the whole forward function gives, with the
capacity term adopted and with hires and program pipeline in force."""

import pytest

from engine.scripts import generate_app_reports as gen
from engine.tieout_core import actions
from engine.tieout_core import worksheet_drivers as wd
from engine.tieout_core import worksheet_rules as rules
from engine.tieout_core.actions import Scenario
from engine.tieout_core.plan import load_plan
from engine.tieout_core.report import prepare


@pytest.fixture(scope="module")
def sapling():
    company = "sapling-industries"
    with gen.in_repo():
        state = prepare(
            gen.PROFILES / company, gen.DATA / company, gen.AS_OF, gen.DRAWS, gen.SEED
        )
        path = gen.PROFILES / company / "plan.yaml"
        plan = load_plan(path, gen.AS_OF, state.cap.members)
        yield state, actions.plan_inputs(state.ground, plan)


@pytest.mark.parametrize("driver", rules.DRIVERS)
@pytest.mark.parametrize("factor", ["0.6", "1.3"])
def test_the_whole_forecast_is_equal_not_just_its_totals(sapling, driver, factor):
    from decimal import Decimal

    state, (hires, inflows) = sapling
    g = state.ground
    assert g.cap.adopted and hires and inflows
    probe = wd.Probe(g, hires, inflows)
    adjusted = wd.with_setting(g, driver, wd.current_value(g, driver) * Decimal(factor))
    assert probe.forecast(adjusted) == Scenario(adjusted).forecast(hires, inflows)

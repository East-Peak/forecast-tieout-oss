# engine/tests/test_connector_interface.py
import pytest
from datetime import date, datetime
from engine.connectors.interface import (
    Deal, Company, Contact, TeamMember, StageTransition,
    ConnectorInterface, ConnectorCapabilities,
)


def test_deal_creation():
    deal = Deal(
        id="001",
        name="Acme Corp - Enterprise",
        amount=250000.0,
        stage="Technical Evaluation",
        close_date=date(2026, 6, 30),
        owner_id="user_001",
        type="New Business",
        created_date=date(2026, 1, 15),
    )
    assert deal.id == "001"
    assert deal.amount == 250000.0


def test_deal_optional_fields():
    deal = Deal(
        id="002",
        name="Missing Data Deal",
        amount=None,
        stage="Discovery",
        close_date=None,
        owner_id="user_002",
    )
    assert deal.amount is None
    assert deal.close_date is None


def test_connector_capabilities_default():
    caps = ConnectorCapabilities()
    assert caps.has_stage_history is False
    assert caps.has_contacts is False
    assert caps.has_companies is False


def test_connector_capabilities_all_true():
    caps = ConnectorCapabilities(
        has_stage_history=True,
        has_contacts=True,
        has_companies=True,
    )
    assert caps.has_stage_history is True


def test_connector_interface_is_abstract():
    with pytest.raises(TypeError):
        ConnectorInterface()

"""Tests for engine.gtm_model.derived.self_serve_velocity.

CONTRACT NOTE: legacy `_get_self_serve_velocity()` returns weekly_creation
+ win_rate fields used by the PLG EWMA computation. The current dataclass
exposes these (via signups_per_week / activations_per_week / conversion_rate)
but future work will validate the exact field names against
runtime/observed.py:589 consumers.
"""
from __future__ import annotations

from engine.gtm_model.derived.self_serve_velocity import SelfServeVelocity


def test_default_unavailable():
    v = SelfServeVelocity()
    assert v.is_available() is False


def test_with_signups_is_available():
    v = SelfServeVelocity(signups_per_week=100.0)
    assert v.is_available() is True


def test_with_activations_only_is_available():
    v = SelfServeVelocity(activations_per_week=20.0)
    assert v.is_available() is True


def test_with_only_rates_not_available():
    """Rate fields without underlying volume aren't enough to call the
    velocity 'available' for engine consumers.
    """
    v = SelfServeVelocity(activation_rate=0.5, conversion_rate=0.1)
    assert v.is_available() is False

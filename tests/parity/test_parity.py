"""Python scenario engine parity against shared golden vectors."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from gtm_model.tieout.runtime.scenario_service import compute_snapshot_scenario

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scenario-golden-vectors.json"


def _load_vectors() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


VECTORS = _load_vectors()


def _assert_number_close(actual: float, expected: float, policy: Mapping[str, Any], path: str) -> None:
    absolute_epsilon = float(policy["floats"]["absoluteEpsilon"])
    relative_epsilon = float(policy["floats"]["relativeEpsilon"])
    scale = max(1.0, abs(expected))
    assert abs(actual - expected) <= max(absolute_epsilon, relative_epsilon * scale), (
        f"{path}: actual={actual!r} expected={expected!r}"
    )


def _requires_exact_number(path: str, policy: Mapping[str, Any]) -> bool:
    return any(f".{field}[" in path for field in policy.get("countFields", []))


def _assert_value_close(actual: Any, expected: Any, policy: Mapping[str, Any], path: str) -> None:
    if isinstance(expected, bool) or isinstance(actual, bool):
        assert actual == expected, f"{path}: actual={actual!r} expected={expected!r}"
        return
    if isinstance(expected, int) and isinstance(actual, int):
        assert actual == expected, f"{path}: actual={actual!r} expected={expected!r}"
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if _requires_exact_number(path, policy):
            assert actual == expected, f"{path}: actual={actual!r} expected={expected!r}"
            return
        _assert_number_close(float(actual), float(expected), policy, path)
        return
    if isinstance(expected, str) or expected is None:
        assert actual == expected, f"{path}: actual={actual!r} expected={expected!r}"
        return
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes, bytearray)):
        assert isinstance(actual, Sequence), f"{path}: actual is not a sequence"
        assert len(actual) == len(expected), f"{path}: actual length={len(actual)} expected={len(expected)}"
        for index, expected_value in enumerate(expected):
            _assert_value_close(actual[index], expected_value, policy, f"{path}[{index}]")
        return
    if isinstance(expected, Mapping):
        assert isinstance(actual, Mapping), f"{path}: actual is not a mapping"
        assert set(actual.keys()) == set(expected.keys()), (
            f"{path}: actual keys={sorted(actual.keys())} expected={sorted(expected.keys())}"
        )
        for key, expected_value in expected.items():
            _assert_value_close(actual[key], expected_value, policy, f"{path}.{key}")
        return
    assert actual == expected, f"{path}: actual={actual!r} expected={expected!r}"


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda case: case["id"])
def test_python_scenario_engine_matches_shared_golden_vectors(case: Mapping[str, Any]) -> None:
    result = compute_snapshot_scenario(case["input"]["snapshot"], case["input"]["overrides"]).to_dict()

    _assert_value_close(
        result,
        case["expected"]["result"],
        VECTORS["tolerancePolicy"],
        case["id"],
    )

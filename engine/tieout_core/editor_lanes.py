"""The swimlane grid for the visitor's own plan.

The editor's worker computes these after it has returned the report, from the same prepared
state and the same plan as that report (the session ties them by the Apply's revision). The
goals are not the plan's to move: the frozen plan basis is recomputed here from the company's
data as it was known at the plan start, and it must be, character for character, the basis file
committed beside the as-signed lanes (the build ships that file with the company's inputs). If
it is not, nothing is shown: a grid whose goals had moved would be worse than none.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import actions, driver_actions, lanes, lanes_basis, lanes_contract
from . import lanes_files as split
from .plan import Plan
from .report import Prepared

REPORTS = Path("frontend/public/data/reports")


def canonical(doc) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class Edited:
    """What one Apply produced that the lanes are built from: its report and its plan."""

    revision: int
    report: dict
    plan: Plan


@dataclass(frozen=True)
class FrozenBasis:
    basis: lanes_basis.Basis
    doc: dict
    digest: str


def frozen_basis(state: Prepared, company: str) -> FrozenBasis:
    """The company's plan basis, proved equal to the committed file.

    Raises ``BasisUnavailable`` where the company has none, and ``ValueError`` where the basis
    computed here is not the committed one."""
    if state.ground is None:
        raise lanes_basis.BasisUnavailable(state.forecasts[2].unavailable_reason)
    basis = lanes_basis.plan_basis(state)
    doc = lanes_basis.document(basis, company)
    path = REPORTS / company / "lanes-basis.json"
    if not path.exists() or path.read_bytes() != canonical(doc).encode("utf-8"):
        raise ValueError(
            "the plan basis computed here is not the committed one (lanes-basis.json); "
            "the goals would move, so no lanes are shown"
        )
    return FrozenBasis(basis, doc, lanes_contract.digest(doc))


def lanes_for(
    state: Prepared, frozen: FrozenBasis, edited: Edited, company: str, scenario: str
) -> dict:
    """The lanes file and each segment's owners file for ``edited``, held to the contract:
    {"lanes": ..., "owners": {segment: ...}, "problems": [...]}. Nothing comes back with a
    problem, so a grid is only ever drawn from files the contract passed."""
    hires, inflows = actions.plan_inputs(state.ground, edited.plan)
    doc = lanes.lanes_document(
        state,
        frozen.basis,
        edited.report,
        hires,
        inflows,
        company,
        scenario,
        frozen.digest,
        driver_actions.effect_for(state, edited.plan, hires, inflows),
    )
    problems = lanes_contract.validate(doc, frozen.doc, edited.report)
    if problems:
        return {"lanes": None, "owners": {}, "problems": problems}
    mine, owners = split.split(doc)
    return {"lanes": mine, "owners": owners, "problems": []}

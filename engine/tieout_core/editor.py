"""The entry the browser's plan editor calls: the same core, one company at a time.

``open_company`` prepares a company once (the slow part of a report); ``apply_plan`` finishes it
with a plan that arrives as data, checks the result against the report contract, and compares
it with the as-signed report. Paths are the generator's: repo-relative, from the working
directory, so a report written here is the report the generator would write, character for
character, but for the plan's name.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from . import contract, driver_actions, lanes_basis
from .comparison import BASELINE, comparison_rows
from .editor_lanes import Edited, FrozenBasis, frozen_basis, lanes_for
from .fiscal import add_months
from .lanes import unavailable_document
from .plan import ActionRefused, Plan, parse_plan, segment_words
from .report import Prepared, finish, prepare

AS_OF = date(2026, 8, 31)
DRAWS = 2000
SEED = 0
PROFILES = Path("engine/config/profiles")
DATA = Path("engine/data-v2")
YOUR_PLAN = "your-plan"
YOUR_PLAN_LABEL = "Your plan"
MAX_DOLLARS_OF_YEAR_TARGET = 10
_ITEM = re.compile(r"^your plan: (hires|programs|actions)\[(\d+)\]: ")


def canonical(doc) -> str:
    """Stable key order, two-space indent, one trailing newline: how every report file is written."""
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class Opened:
    company: str
    state: Prepared
    signed: dict  # the as-signed report: what a plan is compared with
    facts: dict  # what the form needs from the core: segments, months, the cap, the demo plan


@dataclass(frozen=True)
class Applied:
    report_text: (
        str | None
    )  # None when the plan was refused or the report failed its checks
    problems: list[str]  # the contract's findings and a failed software-correct verdict
    errors: list[dict]  # a plan the loader refused: {section, index, message}
    comparison: dict | None
    report: dict | None = (
        None  # the report as data, for what is built from it (the lanes)
    )
    plan: Plan | None = None  # the plan it was finished with


def open_company(company: str) -> Opened:
    state = prepare(PROFILES / company, DATA / company, AS_OF, DRAWS, SEED)
    signed = finish(state, None, None, company, BASELINE)
    return Opened(company, state, signed, _facts(company, state))


def _facts(company: str, state: Prepared) -> dict:
    year_target = sum(state.profile.quarterly_targets.values(), Decimal(0))
    segments = sorted({m.segment for m in state.cap.members})
    demo = PROFILES / company / "plan.yaml"
    return {
        "company": company,
        "segments": [{"value": s, "label": segment_words(s)} for s in segments],
        "months": [
            f"{add_months(date(AS_OF.year, AS_OF.month, 1), k):%Y-%m}"
            for k in range(1, 13)
        ],
        "max_dollars": f"{year_target * MAX_DOLLARS_OF_YEAR_TARGET:f}",
        "demo_plan": _demo_plan(demo),
    }


def _demo_plan(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def apply_plan(opened: Opened, doc) -> Applied:
    """The report for ``doc`` (a plan as parsed data), or why not."""
    state = opened.state
    try:
        plan = parse_plan(_shaped(doc), state.as_of, state.cap.members, "your plan")
    except ValueError as exc:
        return Applied(None, [], [_error(str(exc), getattr(exc, "code", None))], None)
    try:
        report = finish(state, plan, YOUR_PLAN, opened.company, YOUR_PLAN)
    except (
        ActionRefused
    ) as exc:  # a target the core could not carry, found when valuing
        return Applied(
            None,
            [],
            [_error(f"your plan: actions[{exc.index}]: {exc}", exc.code)],
            None,
        )
    except (
        driver_actions.Unavailable
    ) as exc:  # actions cannot be valued for this company
        return Applied(None, [], [_error(f"your plan: {exc}")], None)
    problems = contract.validate(report)
    verdict = report["verdicts"]["software_correct"]
    if verdict["verdict"] != "yes":
        problems.append(f"software-correct verdict is not yes: {verdict['summary']}")
    if problems:
        return Applied(None, problems, [], None)
    row = comparison_rows(
        {BASELINE: opened.signed, YOUR_PLAN: report}, {YOUR_PLAN: YOUR_PLAN_LABEL}
    )[1]
    return Applied(canonical(report), [], [], row, report, plan)


def _shaped(doc) -> dict:
    """The document's shape, which the loader assumes: a mapping of lists of mappings."""
    ok = isinstance(doc, dict) and all(
        isinstance(doc.get(k) or [], list)
        and all(isinstance(i, dict) for i in doc.get(k) or [])
        for k in ("hires", "programs", "actions")
    )
    if not ok:
        raise ValueError(
            "your plan: hires, programs and actions must each be a list of items"
        )
    return doc


def _error(message: str, code: str | None = None) -> dict:
    """An item the loader refused: where it is (section, and its place in the list as the core counts
    from one and as the list holds it from zero) and what to say. An action's message is for a person
    and carries no item number (the structured fields say which item); a hire's and a program's keep theirs."""
    found = _ITEM.match(message)
    if found is None:
        return {"section": None, "index": None, "position": None, "message": message}
    section = found.group(1)
    out = {
        "section": section,
        "index": int(found.group(2)),
        "position": int(found.group(2)) - 1,
        "message": message[len(found.group(0)) :]
        if section == "actions"
        else message[len("your plan: ") :],
    }
    if code is not None:
        out["code"] = code
    return out


class EditorSession:
    """What the worker holds: the company opened last, and text in, text out (the worker passes
    strings across the Python and JavaScript boundary and nothing else).

    Each Apply that produced a report is a revision. The lanes of an edited plan are asked for
    by revision, after the report has been returned, and only the latest Apply of the company
    open now has any: a revision from an earlier Apply, or from another company, is stale and
    answers with no lanes."""

    def __init__(self) -> None:
        self._opened: Opened | None = None
        self._revision = 0  # only ever grows, across companies
        self._edited: Edited | None = None
        self._frozen: FrozenBasis | lanes_basis.BasisUnavailable | None = None

    def open(self, company: str) -> str:
        """Prepare ``company`` (the slow step); the form's facts as JSON text."""
        self._opened = open_company(company)
        self._edited = self._frozen = None
        return json.dumps(self._opened.facts)

    def apply(self, plan_json: str) -> tuple[str, str]:
        """The report text ("" when there is none) and what else came back, as JSON text."""
        if self._opened is None:
            raise RuntimeError("open a company first")
        applied = apply_plan(self._opened, json.loads(plan_json))
        revision = None
        if applied.report is not None:
            self._revision += 1
            revision = self._revision
            self._edited = Edited(revision, applied.report, applied.plan)
        meta = {
            "problems": applied.problems,
            "errors": applied.errors,
            "comparison": applied.comparison,
            "revision": revision,
        }
        return applied.report_text or "", json.dumps(meta)

    def lanes(self, revision: int) -> str:
        """The lanes of the Apply ``revision`` as JSON text: ``stale`` when it is not the latest
        Apply of the company open; otherwise the lanes file, each segment's owners file and the
        problems that stopped them (the plan basis is the committed one, or there are none)."""
        opened, edited = self._opened, self._edited
        if opened is None or edited is None or edited.revision != revision:
            return json.dumps({"revision": revision, "stale": True})
        out: dict = {"revision": revision, "stale": False, "owners": {}}
        try:
            frozen = self._frozen_basis(opened)
        except lanes_basis.BasisUnavailable as why:
            doc = unavailable_document(opened.company, YOUR_PLAN, str(why))
            return json.dumps({**out, "lanes": doc, "problems": []})
        except ValueError as problem:
            return json.dumps({**out, "problems": [str(problem)]})
        made = lanes_for(opened.state, frozen, edited, opened.company, YOUR_PLAN)
        return json.dumps({**out, **made})

    def _frozen_basis(self, opened: Opened) -> FrozenBasis:
        """The company's basis, computed once for the company open."""
        if isinstance(self._frozen, lanes_basis.BasisUnavailable):
            raise self._frozen
        if self._frozen is None:
            try:
                self._frozen = frozen_basis(opened.state, opened.company)
            except lanes_basis.BasisUnavailable as why:
                self._frozen = why
                raise
        return self._frozen

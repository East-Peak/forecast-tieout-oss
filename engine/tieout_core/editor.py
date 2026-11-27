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

from . import contract
from .comparison import BASELINE, comparison_rows
from .fiscal import add_months
from .plan import parse_plan, segment_words
from .report import Prepared, finish, prepare

AS_OF = date(2026, 8, 31)
DRAWS = 2000
SEED = 0
PROFILES = Path("engine/config/profiles")
DATA = Path("engine/data-v2")
YOUR_PLAN = "your-plan"
YOUR_PLAN_LABEL = "Your plan"
MAX_DOLLARS_OF_YEAR_TARGET = 10
_ITEM = re.compile(r"^your plan: (hires|programs)\[(\d+)\]: ")


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
        return Applied(None, [], [_error(str(exc))], None)
    report = finish(state, plan, YOUR_PLAN, opened.company, YOUR_PLAN)
    problems = contract.validate(report)
    verdict = report["verdicts"]["software_correct"]
    if verdict["verdict"] != "yes":
        problems.append(f"software-correct verdict is not yes: {verdict['summary']}")
    if problems:
        return Applied(None, problems, [], None)
    row = comparison_rows(
        {BASELINE: opened.signed, YOUR_PLAN: report}, {YOUR_PLAN: YOUR_PLAN_LABEL}
    )[1]
    return Applied(canonical(report), [], [], row)


def _shaped(doc) -> dict:
    """The document's shape, which the loader assumes: a mapping of lists of mappings."""
    ok = isinstance(doc, dict) and all(
        isinstance(doc.get(k) or [], list)
        and all(isinstance(i, dict) for i in doc.get(k) or [])
        for k in ("hires", "programs")
    )
    if not ok:
        raise ValueError("your plan: hires and programs must each be a list of items")
    return doc


def _error(message: str) -> dict:
    found = _ITEM.match(message)
    if found is None:
        return {"section": None, "index": None, "message": message}
    return {
        "section": found.group(1),
        "index": int(found.group(2)),
        "message": message[len("your plan: ") :],
    }


class EditorSession:
    """What the worker holds: the company opened last, and text in, text out (the worker passes
    strings across the Python and JavaScript boundary and nothing else)."""

    def __init__(self) -> None:
        self._opened: Opened | None = None

    def open(self, company: str) -> str:
        """Prepare ``company`` (the slow step); the form's facts as JSON text."""
        self._opened = open_company(company)
        return json.dumps(self._opened.facts)

    def apply(self, plan_json: str) -> tuple[str, str]:
        """The report text ("" when there is none) and what else came back, as JSON text."""
        if self._opened is None:
            raise RuntimeError("open a company first")
        applied = apply_plan(self._opened, json.loads(plan_json))
        meta = {
            "problems": applied.problems,
            "errors": applied.errors,
            "comparison": applied.comparison,
        }
        return applied.report_text or "", json.dumps(meta)

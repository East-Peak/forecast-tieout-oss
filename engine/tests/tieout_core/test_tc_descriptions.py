"""Goal 3C: a company's one-line description in ``index.json`` says only what its
as-signed report says. Every number in it is a figure in that report, rounded as
the app rounds it; it names the target, the expected total and the gap; and it
carries no text from the retired app."""

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

REPORTS = (
    Path(__file__).resolve().parents[3] / "frontend" / "public" / "data" / "reports"
)
COMPANIES = ["sprout-labs", "sapling-industries", "mighty-oak-holdings"]
DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")
NUMBER = re.compile(r"(\$)?(\d[\d,]*(?:\.\d+)?)(%)?")


def leaves(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from leaves(v)
    elif isinstance(node, bool) or node is None:
        return
    else:
        yield node


def whole(text: str) -> Decimal:
    return Decimal(text).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def report(company: str) -> dict:
    return json.loads((REPORTS / company / "as-signed.json").read_text())


def description(company: str) -> str:
    index = json.loads((REPORTS / "index.json").read_text())
    return next(c["description"] for c in index["companies"] if c["id"] == company)


def numbers_in(text: str):
    """(kind, value) for each number in the text; fiscal-year labels are not figures."""
    text = re.sub(r"\bFY\d{2}\b", "", text)
    for m in NUMBER.finditer(text):
        dollar, digits, percent = m.groups()
        yield (
            ("dollar" if dollar else "percent" if percent else "count"),
            digits.replace(",", ""),
        )


def is_in_report(kind: str, value: str, r: dict) -> bool:
    flat = list(leaves(r))
    strings = [x for x in flat if isinstance(x, str)]
    if kind == "dollar":
        wanted = Decimal(value)
        return any(DECIMAL.match(s) and whole(s) == wanted for s in strings)
    if kind == "percent":
        return any(re.search(rf"(?<![\d.]){re.escape(value)}%", s) for s in strings)
    wanted = Decimal(value)
    return any(isinstance(x, int) and x == wanted for x in flat)


@pytest.mark.parametrize("company", COMPANIES)
def test_every_number_in_the_description_is_in_the_report(company):
    r, text = report(company), description(company)
    found = list(numbers_in(text))
    assert found, text
    missing = [(k, v) for k, v in found if not is_in_report(k, v, r)]
    assert missing == [], f"{company}: {text}"


@pytest.mark.parametrize("company", COMPANIES)
def test_the_description_names_the_target_the_expected_total_and_the_gap(company):
    fy = report(company)["gap"]["fiscal_year"]
    text = description(company)
    for key in ("target", "expected", "gap"):
        assert f"${whole(fy[key]):,}" in text, (key, text)
    assert text.startswith("FY26 target"), text


@pytest.mark.parametrize("company", COMPANIES)
def test_the_description_is_one_plain_line_without_old_app_text(company):
    text = description(company)
    assert "\n" not in text and len(text) <= 220, text
    for old in (
        "scale-up",
        "enterprise plan",
        "early-PMF",
        "expansion bridge",
        "ramp debt",
        "$10M",
        "$100M",
        "$800M",
    ):
        assert old not in text, (old, text)


def test_the_checker_rejects_a_figure_the_report_does_not_carry():
    r = report("sprout-labs")
    assert not is_in_report("dollar", "8000001", r)
    assert not is_in_report("percent", "99", r)
    assert is_in_report("dollar", "8000000", r)

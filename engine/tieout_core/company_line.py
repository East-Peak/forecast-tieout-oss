"""The one line under a company's name: how its as-signed report came out, in words.

It is built from the report's own statuses (the sign of the fiscal-year gap, the capacity
decision, the better-than-baselines verdict) through the phrases below, and carries no
figure, so it cannot disagree with the report or go stale.
"""

from __future__ import annotations

from decimal import Decimal

YEAR = {
    "short": "Short of target this year.",
    "on": "On target this year.",
    "ahead": "Ahead of target this year.",
    "unknown": "No full-year forecast yet.",
}
HEADCOUNT = {
    "adopted": "Headcount explains pipeline",
    "not shown": "the history cannot say whether headcount explains pipeline",
    "unavailable": "headcount cannot be tested without a roster",
}
BETTER = {
    "yes": "the fitted forecast beats the simple yardsticks",
    "no": "the fitted forecast does not yet beat the simple yardsticks",
    "not enough history to say": (
        "the history is too short to compare the fitted forecast with the simple yardsticks"
    ),
}


def year_status(report: dict) -> str:
    """short, on or ahead by the sign of the gap (target less expected); unknown with no forecast."""
    gap = report["gap"]["fiscal_year"]["gap"]
    if gap is None:
        return "unknown"
    sign = Decimal(gap)
    return "short" if sign > 0 else "ahead" if sign < 0 else "on"


def company_line(report: dict) -> str:
    headcount = HEADCOUNT[report["roster_capacity"]["decision"]["outcome"]]
    better = BETTER[report["verdicts"]["forecast_better_than_baselines"]["verdict"]]
    return (
        f"{YEAR[year_status(report)]} {headcount[0].upper()}{headcount[1:]}; {better}."
    )

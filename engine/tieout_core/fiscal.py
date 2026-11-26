"""Fiscal calendar and date windows.

A window is open at its start and closed at its end, ``(start, end]``, so a
cutoff date belongs to the past: an event dated on the cutoff is already known.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

_ONE_DAY = timedelta(days=1)


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    """Shift by whole months, clamping the day to the target month's length."""
    index = d.year * 12 + (d.month - 1) + n
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(d.day, last))


@dataclass(frozen=True)
class Window:
    """The dates in ``(start, end]``."""

    label: str
    start: date
    end: date

    def contains(self, d: date) -> bool:
        return self.start < d <= self.end

    @property
    def days(self) -> int:
        return (self.end - self.start).days


def month_windows(after: date, through: date) -> list[Window]:
    """Calendar-month windows covering ``(after, through]``.

    The first window is the remainder of ``after``'s month; it is dropped when
    empty, which happens when ``after`` is a month end.
    """
    windows: list[Window] = []
    start = after
    while start < through:
        end = min(month_end(start + _ONE_DAY), through)
        windows.append(Window(f"{end.year:04d}-{end.month:02d}", start, end))
        start = end
    return windows


@dataclass(frozen=True)
class FiscalYear:
    start: date

    @property
    def end(self) -> date:
        return add_months(self.start, 12) - _ONE_DAY

    @property
    def label(self) -> str:
        # Repository convention: the fiscal year is named for its start year
        # (FY26 runs February 2026 to January 2027).
        return f"FY{self.start.year % 100:02d}"

    @property
    def quarter_keys(self) -> tuple[str, ...]:
        return tuple(f"Q{q}{self.label}" for q in range(1, 5))

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def quarter_key(self, d: date) -> str:
        if not self.contains(d):
            raise ValueError(
                f"{d} is outside {self.label} ({self.start} to {self.end})"
            )
        months = (d.year - self.start.year) * 12 + d.month - self.start.month
        return self.quarter_keys[months // 3]

    def quarter_window(self, key: str) -> Window:
        q = self.quarter_keys.index(key)
        start = add_months(self.start, 3 * q)
        return Window(key, start - _ONE_DAY, add_months(start, 3) - _ONE_DAY)

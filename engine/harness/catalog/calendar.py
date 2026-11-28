"""The catalog's calendar: months, calendar quarters and years, and fiscal quarters and years.

A fiscal year is named by the year it starts in (FY25 begins 2025-02-01 when the fiscal year starts in
February). Labels are the member keys of the time dimensions; one place turns a day into a label, a label
into its first and last day, and a window into its periods, in Python and in SQL.
"""

from dataclasses import dataclass
from datetime import date, timedelta

GRAINS = ("month", "calendar_quarter", "calendar_year", "fiscal_quarter", "fiscal_year")


@dataclass(frozen=True)
class Calendar:
    fiscal_year_start_month: int = 1

    def fiscal_start_year(self, day: date) -> int:
        return day.year - (1 if day.month < self.fiscal_year_start_month else 0)

    def label(self, day: date, grain: str) -> str:
        if grain == "month":
            return day.strftime("%Y-%m")
        if grain == "calendar_year":
            return str(day.year)
        if grain == "calendar_quarter":
            return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
        fy = f"FY{self.fiscal_start_year(day) % 100:02d}"
        if grain == "fiscal_year":
            return fy
        return f"{fy}-Q{((day.month - self.fiscal_year_start_month) % 12) // 3 + 1}"

    def bounds(self, label: str, grain: str) -> tuple[date, date]:
        """First and last day of a period."""
        if grain == "month":
            start, months = date(int(label[:4]), int(label[5:7]), 1), 1
        elif grain == "calendar_year":
            start, months = date(int(label), 1, 1), 12
        elif grain == "calendar_quarter":
            start, months = date(int(label[:4]), (int(label[-1]) - 1) * 3 + 1, 1), 3
        else:
            year = 2000 + int(label[2:4])
            quarter = int(label[-1]) - 1 if grain == "fiscal_quarter" else 0
            offset = self.fiscal_year_start_month - 1 + quarter * 3
            start, months = (
                date(year + offset // 12, offset % 12 + 1, 1),
                3 if grain == "fiscal_quarter" else 12,
            )
        index = start.month - 1 + months
        return start, date(start.year + index // 12, index % 12 + 1, 1) - timedelta(
            days=1
        )

    def periods(self, window: tuple[date, date], grain: str) -> list[str]:
        out, day = [], window[0]
        while day <= window[1]:
            label = self.label(day, grain)
            out.append(label)
            day = self.bounds(label, grain)[1] + timedelta(days=1)
        return out

    def label_sql(self, expr: str, grain: str) -> str:
        d, fsm = f"CAST({expr} AS DATE)", self.fiscal_year_start_month
        if grain == "month":
            return f"strftime({d}, '%Y-%m')"
        if grain == "calendar_year":
            return f"strftime({d}, '%Y')"
        if grain == "calendar_quarter":
            return f"strftime({d}, '%Y') || '-Q' || CAST(quarter({d}) AS VARCHAR)"
        fy = f"'FY' || lpad(CAST((year({d}) - CASE WHEN month({d}) < {fsm} THEN 1 ELSE 0 END) % 100 AS VARCHAR), 2, '0')"
        if grain == "fiscal_year":
            return fy
        return f"{fy} || '-Q' || CAST(((month({d}) - {fsm} + 12) % 12) // 3 + 1 AS VARCHAR)"

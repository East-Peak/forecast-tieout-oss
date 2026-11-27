"""How money and quantities are written into the report dict: exact decimals as
strings, cents for displayed money."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

CENT = Decimal("0.01")


def cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_EVEN)


def money(x: Decimal) -> str:
    return str(cents(x))


def opt_money(x: Decimal | None) -> str | None:
    return None if x is None else money(x)


def exact(x: Decimal) -> str:
    return str(x)


def number(x: Decimal | float, places: int = 4) -> str:
    return f"{float(x):.{places}f}"

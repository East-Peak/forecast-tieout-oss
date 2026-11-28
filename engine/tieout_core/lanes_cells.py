"""What both kinds of lane share: the atoms a cell is made of, and how a ratio, a split and a
figure are written. An atom is something that adds (deals, dollars, win days, a rate's numerator
and denominator); a cell is built from three modes' atoms."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from .figures import CENT
from .lanes_rules import COUNT

ZERO = Decimal(0)

ATOMS = (
    "open",
    "created",
    "created_arr",
    "won",
    "won_carried",
    "won_new",
    "bookings",
    "bookings_carried",
    "bookings_new",
    "days",
    "cohort_wins",
    "cohort_n",
)
QUANTUM = {
    "open": Decimal(1),
    "cohort_wins": Decimal(1),
    "cohort_n": Decimal(1),
    "created": COUNT,
    "won": COUNT,
    "won_carried": COUNT,
    "won_new": COUNT,
    "created_arr": CENT,
    "bookings": CENT,
    "bookings_carried": CENT,
    "bookings_new": CENT,
    "days": CENT,
}
FLOW_ATOMS = tuple(k for k in ATOMS if k not in ("open", "cohort_wins", "cohort_n"))
RATIOS = {  # a ratio column: the atoms it is a quotient of
    "win_rate": ("cohort_wins", "cohort_n"),
    "avg_won_arr": ("bookings", "won"),
    "cycle": ("days", "won"),
}
SPLIT = {
    "won": ("won_carried", "won_new"),
    "bookings": ("bookings_carried", "bookings_new"),
}


def add(parts) -> dict[str, Decimal | None]:
    """The sum of atom dicts; an atom that is missing everywhere stays missing."""
    parts = list(parts)
    keys = {k for p in parts for k in p}
    return {
        k: None
        if all(p.get(k) is None for p in parts)
        else sum((p[k] for p in parts if p.get(k) is not None), ZERO)
        for k in keys
    }


def text(value: Decimal | None, quantum: Decimal) -> str | None:
    return None if value is None else str(value.quantize(quantum))


def part(atoms: Mapping[str, Decimal | None], num: str, den: str) -> dict | None:
    n, d = atoms.get(num), atoms.get(den)
    if n is None or d is None:
        return None
    return {"numerator": text(n, QUANTUM[num]), "denominator": text(d, QUANTUM[den])}


def quotient(part: dict | None, places: int) -> Decimal | None:
    if part is None or not Decimal(part["denominator"]):
        return None
    return (Decimal(part["numerator"]) / Decimal(part["denominator"])).quantize(
        Decimal(1).scaleb(-places)
    )

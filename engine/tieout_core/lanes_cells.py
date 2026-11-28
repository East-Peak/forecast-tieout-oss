"""What both kinds of lane share: the atoms a cell is made of, and how a ratio, a split and a
figure are written. An atom is something that adds (deals, dollars, win days, a rate's numerator
and denominator); a cell is built from three modes' atoms."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from . import lanes_rules as rules
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


def owner_cell(col: rules.Column, atoms: dict) -> dict:
    """One cell of an owner from the three modes' atoms (the goal's None where nothing was
    allocated). Volumes carry a goal and a status where there is a goal; a rate, a cycle or an
    average size carries what was recorded, with its numerator and denominator, and nothing to
    compare it with."""
    places = Decimal(1).scaleb(-col.places)
    parts = split = None
    compared = col.compared
    if col.key in RATIOS:
        num, den = RATIOS[col.key]
        parts = {"actual": part(atoms["actual"], num, den), "forecast": None, "goal": None}  # fmt: skip
        values = {"actual": quotient(parts["actual"], col.places), "forecast": None, "goal": None}  # fmt: skip
        compared = "actual"
    else:
        values = {
            m: (atoms[m] or {}).get(col.key) for m in ("actual", "forecast", "goal")
        }
        values = {m: None if v is None else v.quantize(places) for m, v in values.items()}  # fmt: skip
        if col.key in SPLIT:
            split = {
                m: dict(
                    zip(
                        ("carried_in", "created_in_period"),
                        (text(atoms[m][k], QUANTUM[k]) for k in SPLIT[col.key]),
                    )
                )
                for m in ("actual", "forecast")
            }
    status, why, ratio = rules.owner_status(col, values[compared], values["goal"])
    denominator = None
    if col.minimum is not None and parts and parts["actual"]:
        denominator = parts["actual"]["denominator"]
    return {
        **{m: text(v, places) for m, v in values.items()},
        "parts": parts,
        "split": split,
        "compared": compared,
        "ratio": None if ratio is None else str(ratio),
        "status": status,
        "none_because": why,
        "denominator": denominator,
    }

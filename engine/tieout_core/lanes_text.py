"""How the lanes' larger files are written: sorted keys and two-space indent, but a list of ids, a
record and a lane's row each on one line, so a file of thousands of them stays small and a diff
stays readable. Everything is still plain JSON."""

from __future__ import annotations

import json


def _flat(x) -> bool:
    return not any(
        isinstance(v, dict | list) for v in (x.values() if isinstance(x, dict) else x)
    )


def _one_line(x) -> bool:
    return (
        not isinstance(x, dict | list)
        or _flat(x)
        or (isinstance(x, dict) and "cells" in x)
    )


def _dump(x, depth: int) -> str:
    if _one_line(x):
        return json.dumps(x, sort_keys=True, ensure_ascii=False)
    pad, end = "  " * (depth + 1), "  " * depth
    if isinstance(x, list):
        body = ",\n".join(pad + _dump(v, depth + 1) for v in x)
        return f"[\n{body}\n{end}]"
    body = ",\n".join(
        f"{pad}{json.dumps(k, ensure_ascii=False)}: {_dump(v, depth + 1)}"
        for k, v in sorted(x.items())
    )
    return f"{{\n{body}\n{end}}}"


def text(doc: dict) -> str:
    return _dump(doc, 0) + "\n"

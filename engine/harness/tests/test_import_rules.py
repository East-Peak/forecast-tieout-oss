"""Import boundaries from the design: planning and contract never import
DuckDB, and the generator never imports the planning model."""

import ast
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]


def imported_modules(package: str) -> set[str]:
    """Every module name imported by any .py file under a harness package."""
    found: set[str] = set()
    for path in (HARNESS / package).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                level = "." * node.level
                found.add(level + (node.module or ""))
                found.update(f"{level}{node.module or ''}.{a.name}" for a in node.names)
    return found


def touches(modules: set[str], name: str) -> list[str]:
    """Imports of `name`, absolute (harness.name, a.b.name) or relative (..name)."""
    return sorted(
        m for m in modules if name in m.replace("..", ".").lstrip(".").split(".")
    )


def test_every_package_exists():
    for package in (
        "contract",
        "synth",
        "evidence",
        "catalog",
        "planning",
        "adapters",
        "tests",
    ):
        assert (HARNESS / package).is_dir(), package


def test_contract_never_imports_duckdb():
    assert touches(imported_modules("contract"), "duckdb") == []


def test_planning_never_imports_duckdb():
    assert touches(imported_modules("planning"), "duckdb") == []


def test_synth_never_imports_planning():
    assert touches(imported_modules("synth"), "planning") == []


def test_scanner_sees_violations(tmp_path):
    """The scanner itself: a planted import is found, a clean file is not."""
    pkg = tmp_path / "x"
    pkg.mkdir()
    (pkg / "bad.py").write_text("import duckdb\nfrom .. import planning\n")
    (pkg / "good.py").write_text("import json\n")
    global HARNESS
    saved, HARNESS = HARNESS, tmp_path
    try:
        found = imported_modules("x")
    finally:
        HARNESS = saved
    assert touches(found, "duckdb") == ["duckdb"]
    assert touches(found, "planning") != []

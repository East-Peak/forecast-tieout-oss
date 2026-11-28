"""Measurement never imports the planning model or the generator: catalog/ and query.py stand on the
evidence engine alone (design: "measurement never imports planning")."""

import ast
from pathlib import Path

from engine.harness.tests.test_import_rules import HARNESS, imported_modules, touches


def modules_of_file(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            level = "." * node.level
            found.add(level + (node.module or ""))
            found.update(f"{level}{node.module or ''}.{a.name}" for a in node.names)
    return found


def test_catalog_never_imports_planning_or_synth():
    modules = imported_modules("catalog")
    assert touches(modules, "planning") == [] and touches(modules, "synth") == []


def test_query_never_imports_planning_or_synth():
    modules = modules_of_file(HARNESS / "query.py")
    assert touches(modules, "planning") == [] and touches(modules, "synth") == []


def test_adapters_hold_data_not_code_that_reaches_the_planner():
    assert touches(imported_modules("adapters"), "planning") == []


def test_dependencies_stay_within_the_allowed_set():
    allowed = {"duckdb", "yaml", "numpy"}
    stdlib = {
        "re",
        "hashlib",
        "ast",
        "statistics",
        "calendar",
        "collections",
        "dataclasses",
        "datetime",
        "itertools",
        "pathlib",
        "typing",
    }
    seen = imported_modules("catalog") | modules_of_file(HARNESS / "query.py")
    top = {m.split(".")[0] for m in seen if not m.startswith(".")}
    assert top <= allowed | stdlib | {"engine"}, top - allowed - stdlib


def test_the_scanner_sees_a_planted_import(tmp_path):
    bad = tmp_path / "q.py"
    bad.write_text("from .planning import forecast\nimport engine.harness.synth\n")
    assert (
        touches(modules_of_file(bad), "planning") != []
        and touches(modules_of_file(bad), "synth") != []
    )

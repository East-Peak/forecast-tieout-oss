"""The product is written in American English. Spellings are built from fragments so this
file does not contain the words it forbids; the frontend has the same check on its own text."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

BRITISH = re.compile(
    "|".join(
        [
            r"\bprogram" + r"me",
            r"\brealis(e|ed|es|ing|ation)\b",
            r"\bla" + r"belled\b",
            r"\bla" + r"belling\b",
            r"\bcent" + r"re",
            r"\bdefen" + r"ce\b",
            r"\bfav" + r"our",
            r"\bjudge" + r"ment",
            r"\b(normalis|serialis|summaris|organis|recognis|prioritis|standardis|minimis|maximis|utilis|catalogu)(e|ed|es|ing|ation)\b",
            r"\banalys(e|ed|es|ing)\b",
            r"\bemphasis(e|ed|es|ing)\b",
            r"\boptimis(e|ed|es|ing|ation)\b",
            r"\bbehav" + r"iour",
            r"\bcol" + r"our",
            r"\bhon" + r"our",
            r"\bcheque",
            r"\bgrey\b",
            r"\bwhilst\b",
            r"\bamongst\b",
            r"\bper cent\b",
            r"\bageing\b",
            r"\benrol(s|led|ment)?\b",
            r"\bfulfil(s|ment)?\b",
            r"\bskilful\b",
            r"\bcancel" + r"led\b",
            r"\bmodel" + r"l(ed|ing)\b",
            r"\btravel" + r"l(ed|ing)\b",
            r"\blicen" + r"ce\b",
        ]
    ),
    re.IGNORECASE,
)

SCANNED = [
    "frontend/public/data/reports",
    "engine/tieout_core",
    "engine/config",
    "engine/scripts",
    "README.md",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
]
TEXT = {".json", ".md", ".py", ".yaml", ".yml"}


def files():
    for entry in SCANNED:
        path = REPO / entry
        found = [path] if path.is_file() else sorted(path.rglob("*"))
        yield from (
            p
            for p in found
            if p.is_file() and p.suffix in TEXT and "__pycache__" not in p.parts
        )


def test_no_british_spelling_in_the_reports_the_core_the_config_or_the_docs():
    hits = [
        f"{p.relative_to(REPO)}: {m.group(0)}"
        for p in files()
        for m in BRITISH.finditer(p.read_text(encoding="utf-8"))
    ]
    assert hits == []


def test_the_check_would_catch_a_british_spelling():
    assert BRITISH.search("a " + "program" + "me runs")
    assert BRITISH.search("the " + "cent" + "red forecast")
    assert not BRITISH.search("a program is centered; analysis; license; color; gray")

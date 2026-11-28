"""The predicate language: a small declared expression over declared columns, compiled with bound values."""

from datetime import date

import pytest

from engine.harness.catalog.expr import ExprError, Params, compile_expr

COLS = {
    "type": "text",
    "stage": "text",
    "amount_cents": "int",
    "close_date": "date",
    "is_open": "bool",
}


def sql(text, normalize=False):
    params = Params()
    out = compile_expr(text, COLS, lambda name: f"t.{name}", params, normalize)
    return out, params.values


def test_comparison_and_bound_value():
    out, values = sql("type = 'New Business'")
    assert out == "(t.type = $p0)"
    assert list(values.values()) == ["New Business"]
    assert "New Business" not in out


def test_in_list_null_checks_and_boolean_structure():
    out, values = sql(
        "stage in ('Closed Won', 'Closed Lost') and not (amount_cents is null or type != 'x')"
    )
    assert out.count("$p") == 3
    assert (
        "IN" in out
        and "IS NULL" in out
        and "NOT" in out
        and "AND" in out
        and "OR" in out
    )
    assert list(values.values()) == ["Closed Won", "Closed Lost", "x"]


def test_not_in_and_is_not_null_and_numbers_and_dates_and_bools():
    out, values = sql(
        "stage not in ('a') and amount_cents >= 100 and close_date < '2025-03-01' and is_open = true and type is not null"
    )
    assert list(values.values()) == ["a", 100, date(2025, 3, 1), True]
    assert "NOT IN" in out and "IS NOT NULL" in out


def test_precedence_and_binds_tighter_than_or():
    out, _ = sql("type = 'a' or type = 'b' and stage = 'c'")
    assert out == "((t.type = $p0) OR ((t.type = $p1) AND (t.stage = $p2)))"


def test_normalize_lowercases_both_sides():
    out, values = sql("type = 'New Business'", normalize=True)
    assert out == "(lower(trim(t.type)) = $p0)"
    assert list(values.values()) == ["new business"]


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("nope = 'x'", "nope"),  # undeclared identifier
        ("type = 'x'; DROP TABLE t", "';'"),
        ("type = 'x' -- comment", "'-'"),
        ("1 = 1", "column"),  # a literal is not a column
        ("type = 'x' or 1=1", "column"),
        ("type = 'unterminated", "unterminated"),
        ("type = (select 1)", "literal"),
        ("type = type", "literal"),  # a column is not a literal
        ("amount_cents = 'ten'", "number"),
        ("close_date = 'soon'", "date"),
        ("type > 'a'", "ordering"),  # no ordering on text
        ("type in ()", "literal"),
        ("type = 'x' and", "end of"),
        ("(type = 'x'", "')'"),
        ("type like 'x%'", "like"),
    ],
)
def test_rejections_name_the_problem(text, fragment):
    with pytest.raises(ExprError) as err:
        sql(text)
    assert fragment in str(err.value)


def test_error_carries_the_position():
    with pytest.raises(ExprError) as err:
        sql("type = 'x' and nope = 1")
    assert err.value.pos == 15

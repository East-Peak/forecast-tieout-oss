"""The predicate language: comparisons, in-lists, null checks, and/or/not over declared columns.

There is no free SQL anywhere in a catalog. A predicate is parsed here, every identifier must be
a declared column, every literal is type-checked against its column and travels as a bound
value; the only text that reaches the database is what this module emits.
"""

import re
from collections.abc import Callable
from datetime import date

TOKEN = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>-?\d+(?:\.\d+)?)|(?P<id>[A-Za-z_][A-Za-z0-9_.]*)"
    r"|(?P<op><>|!=|<=|>=|=|<|>)|(?P<punct>[(),]))"
)
KEYWORDS = {"and", "or", "not", "in", "is", "null", "true", "false"}
ORDERED = {"int", "date"}  # types that allow < <= > >=
SQL_OP = {"=": "=", "!=": "<>", "<>": "<>", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


class ExprError(ValueError):
    def __init__(self, message: str, pos: int):
        super().__init__(f"{message} (at position {pos})")
        self.message, self.pos = message, pos


class Params:
    """Bound values in order of appearance, as named parameters shared by a whole statement."""

    def __init__(self):
        self.values: dict[str, object] = {}

    def add(self, value) -> str:
        name = f"p{len(self.values)}"
        self.values[name] = value
        return f"${name}"


def tokenize(text: str) -> list[tuple[str, str, int]]:
    out, pos = [], 0
    while pos < len(text):
        if not text[pos:].strip():
            break
        m = TOKEN.match(text, pos)
        if not m:
            rest = text[pos:].lstrip()
            at = len(text) - len(rest)
            if rest[0] == "'":
                raise ExprError("unterminated string literal", at)
            raise ExprError(f"unexpected {rest[0]!r}", at)
        kind = m.lastgroup
        value = m.group(kind)
        at = m.start(kind)
        if kind == "id" and value.lower() in KEYWORDS:
            kind, value = "kw", value.lower()
        out.append((kind, value, at))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, text, columns, resolve, params, normalize):
        self.tokens, self.end = tokenize(text), len(text)
        self.i = 0
        self.columns, self.resolve, self.params, self.normalize = (
            columns,
            resolve,
            params,
            normalize,
        )

    # -- token helpers
    def peek(self):
        return (
            self.tokens[self.i] if self.i < len(self.tokens) else (None, None, self.end)
        )

    def take(self):
        tok = self.peek()
        if tok[0] is None:
            raise ExprError("unexpected end of expression", self.end)
        self.i += 1
        return tok

    def eat(self, kind, value=None) -> bool:
        k, v, _ = self.peek()
        if k == kind and (value is None or v == value):
            self.i += 1
            return True
        return False

    def expect(self, kind, value, label):
        k, _, at = self.peek()
        if not self.eat(kind, value):
            raise ExprError(
                f"expected {label}"
                + (" but the expression ended" if k is None else ""),
                at,
            )

    # -- grammar
    def parse(self) -> str:
        sql = self.or_()
        k, v, at = self.peek()
        if k is not None:
            raise ExprError(f"unexpected {v!r}", at)
        return sql

    def or_(self):
        parts = [self.and_()]
        while self.eat("kw", "or"):
            parts.append(self.and_())
        return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"

    def and_(self):
        parts = [self.not_()]
        while self.eat("kw", "and"):
            parts.append(self.not_())
        return parts[0] if len(parts) == 1 else "(" + " AND ".join(parts) + ")"

    def not_(self):
        if self.eat("kw", "not"):
            return f"(NOT {self.not_()})"
        if self.eat("punct", "("):
            inner = self.or_()
            self.expect("punct", ")", "')'")
            return inner
        return self.comparison()

    def column(self):
        kind, name, at = self.take()
        if kind != "id":
            raise ExprError(f"expected a column, found {name!r}", at)
        if name not in self.columns:
            raise ExprError(f"unknown column {name!r}", at)
        col = self.resolve(name)
        ctype = self.columns[name]
        if self.normalize and ctype == "text":
            col = f"lower(trim({col}))"
        return col, ctype

    def literal(self, ctype):
        kind, value, at = self.take()
        if kind == "kw" and value in ("true", "false") and ctype == "bool":
            return self.params.add(value == "true")
        if kind == "str":
            text = value[1:-1].replace("''", "'")
            if ctype == "text":
                return self.params.add(text.strip().lower() if self.normalize else text)
            if ctype == "date":
                try:
                    return self.params.add(date.fromisoformat(text))
                except ValueError:
                    raise ExprError(
                        f"expects a date (YYYY-MM-DD), found {value}", at
                    ) from None
        elif kind == "num" and ctype == "int":
            return self.params.add(float(value) if "." in value else int(value))
        if kind in ("str", "num", "kw") and not (
            kind == "kw" and value not in ("true", "false")
        ):
            want = {
                "text": "text",
                "int": "a number",
                "date": "a date (YYYY-MM-DD)",
                "bool": "true or false",
            }
            raise ExprError(
                f"column of type {ctype} expects {want.get(ctype, ctype)}, found {value}",
                at,
            )
        raise ExprError(f"expected a literal, found {value!r}", at)

    def comparison(self):
        col, ctype = self.column()
        kind, value, at = self.take()
        if kind == "kw" and value == "is":
            neg = self.eat("kw", "not")
            self.expect("kw", "null", "'null'")
            return f"({col} IS {'NOT ' if neg else ''}NULL)"
        neg = False
        if kind == "kw" and value == "not":
            neg = True
            kind, value, at = self.take()
        if kind == "kw" and value == "in":
            self.expect("punct", "(", "'('")
            items = [self.literal(ctype)]
            while self.eat("punct", ","):
                items.append(self.literal(ctype))
            self.expect("punct", ")", "')'")
            return f"({col} {'NOT ' if neg else ''}IN ({', '.join(items)}))"
        if kind == "op" and not neg:
            if value not in ("=", "!=", "<>") and ctype not in ORDERED:
                raise ExprError(f"ordering not allowed on {ctype} column", at)
            return f"({col} {SQL_OP[value]} {self.literal(ctype)})"
        raise ExprError(f"expected an operator, found {value!r}", at)


def compile_expr(
    text: str,
    columns: dict[str, str],
    resolve: Callable[[str], str],
    params: Params,
    normalize: bool = False,
) -> str:
    """Parse, validate against `columns` (name to type) and emit SQL with bound values."""
    return _Parser(text, columns, resolve, params, normalize).parse()

"""Static guard: code in src/ must use ORM models with their real columns.

The `db`-marked tests are skipped by default, so a wrong column name only
shows up on the server. This test catches that class of bug without a
database: every `Model(...)` call, `Model.attr` access and attribute read on
an instance loaded with `session.get(Model, ...)` or built with `Model(...)`
is checked against the mapped columns, and constructor calls must set every
NOT NULL column that has no default.
"""

from __future__ import annotations

import ast
from pathlib import Path

from sqlalchemy import inspect as sa_inspect

from techradar.db import models

SRC = Path(__file__).resolve().parents[2] / "src" / "techradar"


def _model_info() -> dict[str, tuple[set[str], set[str]]]:
    info: dict[str, tuple[set[str], set[str]]] = {}
    for name, cls in vars(models).items():
        if not (isinstance(cls, type) and hasattr(cls, "__table__")):
            continue
        if cls.__module__ != models.__name__:
            continue
        mapper = sa_inspect(cls)
        attrs = set(mapper.attrs.keys()) | {a for a in dir(cls) if not a.startswith("_")}
        required = {
            prop.key
            for prop in mapper.column_attrs
            if not prop.columns[0].nullable
            and prop.columns[0].default is None
            and prop.columns[0].server_default is None
            and not prop.columns[0].primary_key
            and getattr(prop.columns[0], "identity", None) is None
        }
        info[name] = (attrs, required)
    return info


def _aliases(tree: ast.AST, known: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("db.models"):
            for alias in node.names:
                if alias.name in known:
                    out[alias.asname or alias.name] = alias.name
    return out


def _instance_vars(func: ast.AST, alias: dict[str, str]) -> dict[str, str]:
    """Map local names to models for `x = Model(...)` and `x = await s.get(Model, ...)`."""
    found: dict[str, str] = {}
    for node in ast.walk(func):
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value.value if isinstance(node.value, ast.Await) else node.value
        if not isinstance(value, ast.Call):
            continue
        func_expr = value.func
        if isinstance(func_expr, ast.Name) and func_expr.id in alias:
            found[target.id] = alias[func_expr.id]
        elif (
            isinstance(func_expr, ast.Attribute)
            and func_expr.attr == "get"
            and value.args
            and isinstance(value.args[0], ast.Name)
            and value.args[0].id in alias
        ):
            found[target.id] = alias[value.args[0].id]
    return found


def find_orm_misuse() -> list[str]:
    info = _model_info()
    problems: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "models.py" and path.parent.name == "db":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        alias = _aliases(tree, set(info))
        if not alias:
            continue
        rel = path.relative_to(SRC.parent)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in alias
            ):
                model = alias[node.func.id]
                attrs, required = info[model]
                given = {kw.arg for kw in node.keywords if kw.arg}
                for bad in sorted(given - attrs):
                    problems.append(f"{rel}:{node.lineno}: {model}() has no column {bad!r}")
                splat = any(kw.arg is None for kw in node.keywords) or node.args
                if not splat:
                    for missing in sorted(required - given):
                        problems.append(
                            f"{rel}:{node.lineno}: {model}() misses NOT NULL {missing!r}"
                        )
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in alias
                and node.attr not in info[alias[node.value.id]][0]
            ):
                problems.append(
                    f"{rel}:{node.lineno}: {alias[node.value.id]}.{node.attr} does not exist"
                )
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            instances = _instance_vars(func, alias)
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in instances
                    and node.attr not in info[instances[node.value.id]][0]
                ):
                    model = instances[node.value.id]
                    problems.append(f"{rel}:{node.lineno}: {model} instance has no {node.attr!r}")
    return sorted(set(problems))


def test_src_uses_orm_models_with_real_columns():
    assert find_orm_misuse() == []


def test_guard_catches_unknown_column(tmp_path, monkeypatch):
    bad = tmp_path / "techradar" / "bad.py"
    bad.parent.mkdir()
    bad.write_text(
        "from techradar.db.models import Answer\n"
        "def f(s):\n"
        "    a = Answer(answer='x')\n"
        "    return a.answer\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "SRC", bad.parent)
    problems = find_orm_misuse()
    assert any("has no column 'answer'" in p for p in problems)
    assert any("misses NOT NULL 'chat_id'" in p for p in problems)
    assert any("instance has no 'answer'" in p for p in problems)

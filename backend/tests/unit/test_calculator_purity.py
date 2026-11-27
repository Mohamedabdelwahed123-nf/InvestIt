"""calculator/core stays pure: no DB, no AI, no network, no float money."""

import ast
from pathlib import Path

import pytest

CORE_DIR = Path(__file__).resolve().parents[2] / "calculator" / "core"
FORBIDDEN_PREFIXES = (
    "backend.db",
    "backend.agents",
    "backend.api",
    "sqlalchemy",
    "psycopg",
    "alembic",
    "langchain",
    "langgraph",
    "anthropic",
    "openai",
    "httpx",
    "requests",
    "random",
    "numpy",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


CORE_FILES = sorted(CORE_DIR.glob("*.py"))


def test_core_has_modules() -> None:
    assert {"money.py", "stats.py"} <= {p.name for p in CORE_FILES}


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: p.name)
def test_core_imports_nothing_forbidden(path: Path) -> None:
    bad = {n for n in _imports(path) if n.startswith(FORBIDDEN_PREFIXES)}
    assert not bad, f"{path.name} imports {sorted(bad)}"


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: p.name)
def test_core_never_builds_floats(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    float_literals = [
        n.lineno for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) is float
    ]
    float_calls = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "float"
    ]
    assert not float_literals and not float_calls, (
        f"{path.name}: floats at {float_literals + float_calls}"
    )

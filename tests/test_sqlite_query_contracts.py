"""Static SQL ownership and SQLite schema smoke tests."""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

from ai4binance.data.market_depth import DepthJournal
from ai4binance.governance.capability_store import _ensure_schema
from ai4binance.infrastructure.persistence.memory_projection import (
    SqliteMemoryProjection,
)

ROOT = Path(__file__).parents[1]
SOURCE_ROOT = ROOT / "src" / "ai4binance"
EXECUTION_METHODS = frozenset({"execute", "executemany", "executescript"})
SQL_OWNERS = {
    "src/ai4binance/data/market_depth.py": "tests/test_market_depth.py",
    "src/ai4binance/execution/authorization.py": (
        "tests/test_execution_authorization.py"
    ),
    "src/ai4binance/governance/capability_store.py": (
        "tests/test_governance_capability_store.py"
    ),
    "src/ai4binance/infrastructure/persistence/memory_projection.py": (
        "tests/test_memory_projection.py"
    ),
}


def _sqlite_calls(tree: ast.AST) -> tuple[ast.Call, ...]:
    return tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in EXECUTION_METHODS
        and node.args
    )


def _imports_sqlite(tree: ast.Module) -> bool:
    return any(
        (
            isinstance(node, ast.Import)
            and any(alias.name == "sqlite3" for alias in node.names)
        )
        or (isinstance(node, ast.ImportFrom) and node.module == "sqlite3")
        for node in tree.body
    )


def _module_string_constants(tree: ast.Module) -> set[str]:
    return {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def test_embedded_sql_has_explicit_owners_static_queries_and_behavior_tests() -> None:
    observed_owners: set[str] = set()
    for path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if not _imports_sqlite(tree):
            continue
        calls = _sqlite_calls(tree)
        if not calls:
            continue
        relative = path.relative_to(ROOT).as_posix()
        observed_owners.add(relative)
        constants = _module_string_constants(tree)
        for call in calls:
            query = call.args[0]
            assert (
                isinstance(query, ast.Constant) and isinstance(query.value, str)
            ) or (isinstance(query, ast.Name) and query.id in constants), (
                f"dynamic SQL is prohibited at {relative}:{call.lineno}"
            )

    assert observed_owners == set(SQL_OWNERS)
    assert all((ROOT / test_path).is_file() for test_path in SQL_OWNERS.values())


def _assert_integrity(path: Path, expected_tables: set[str]) -> None:
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert expected_tables <= tables


def test_embedded_sqlite_schemas_pass_integrity_smoke_tests(tmp_path: Path) -> None:
    depth_path = tmp_path / "depth.sqlite3"
    depth = DepthJournal(depth_path)
    depth.close()
    _assert_integrity(depth_path, {"depth_events", "depth_heads"})

    capability_path = tmp_path / "governance.sqlite3"
    with sqlite3.connect(capability_path) as connection:
        _ensure_schema(connection)
        connection.commit()
    _assert_integrity(capability_path, {"capability_leases"})

    projection = SqliteMemoryProjection(tmp_path / "memory.sqlite3")
    projection.rebuild(())
    _assert_integrity(
        projection.path,
        {"projection_metadata", "memory_records", "memory_fts"},
    )

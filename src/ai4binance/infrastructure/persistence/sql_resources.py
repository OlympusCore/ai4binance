"""Load canonical SQL statements while Python owns connection orchestration."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path


@cache
def _statements(owner: str) -> dict[str, str]:
    if re.fullmatch(r"[a-z_]+", owner) is None:
        raise ValueError("SQL_RESOURCE_OWNER_INVALID")
    root = Path(__file__).resolve().parents[4]
    source = (root / "migrations/queries" / f"{owner}.sql").read_text(encoding="utf-8")
    sections = re.split(r"(?m)^-- name: ([a-z_0-9]+)\n", source)
    result: dict[str, str] = {}
    for name, statement in zip(sections[1::2], sections[2::2], strict=True):
        if name in result or not statement.strip():
            raise ValueError("SQL_RESOURCE_STATEMENT_INVALID")
        result[name] = statement.strip()
    if not result:
        raise ValueError("SQL_RESOURCE_EMPTY")
    return result


def sql_statement(owner: str, name: str) -> str:
    """Return fixed SQL; callers bind values using database parameters."""
    try:
        return _statements(owner)[name]
    except KeyError as exc:
        raise ValueError("SQL_RESOURCE_STATEMENT_UNAVAILABLE") from exc

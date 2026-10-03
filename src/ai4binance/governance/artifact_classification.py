"""Shared classification of generated Python bytecode paths."""

from __future__ import annotations

from pathlib import Path


def is_python_bytecode_artifact(relative: str) -> bool:
    """Identify compiled Python artifacts without excluding neighboring text files."""

    return Path(relative).suffix.lower() in {".pyc", ".pyo"}

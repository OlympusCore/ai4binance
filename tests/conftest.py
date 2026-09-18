"""Test import path bootstrap for shared test helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SRC_DIR = TESTS_DIR.parent / "src"
TESTS_DIR_STR = str(TESTS_DIR)
SRC_DIR_STR = str(SRC_DIR)

if TESTS_DIR_STR not in sys.path:
    sys.path.insert(0, TESTS_DIR_STR)
if SRC_DIR_STR not in sys.path:
    sys.path.insert(0, SRC_DIR_STR)

# Bind tempfile and child-process environments before fixtures are collected.
from ai4binance import configure_runtime_environment  # noqa: E402

configure_runtime_environment()

pythonpath = os.environ.get("PYTHONPATH")
if pythonpath:
    if SRC_DIR_STR not in pythonpath:
        os.environ["PYTHONPATH"] = f"{SRC_DIR_STR};{pythonpath}"
else:
    os.environ["PYTHONPATH"] = SRC_DIR_STR

os.environ.setdefault(
    "HYPOTHESIS_STORAGE_DIRECTORY",
    str(TESTS_DIR.parent / "runtime" / "tmp" / "hypothesis"),
)


def pytest_configure(config: pytest.Config) -> None:
    """Reject pytest temp roots outside the repository-owned process runtime."""
    target = configure_runtime_environment()
    base_temp = config.option.basetemp
    if base_temp is None:
        return
    resolved = Path(base_temp).resolve()
    if resolved == target or resolved.is_relative_to(target):
        return
    msg = f"PYTEST_BASETEMP_OUTSIDE_RUNTIME_TMP_PROCESS: {resolved} is outside {target}"
    raise pytest.UsageError(msg)

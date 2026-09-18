"""Tests for the Ruff maintainability non-regression gate."""

from __future__ import annotations

from pathlib import Path

from ai4binance.ops.maintainability_ratchet import (
    RULES,
    MaintainabilityBaseline,
    collect_ruff_findings,
    evaluate_findings,
    load_baseline,
)

ROOT = Path(__file__).parents[1]
BASELINE_PATH = ROOT / "config/quality/ruff-maintainability-baseline.json"


def _finding(code: str, path: str) -> dict[str, object]:
    return {"code": code, "filename": str(ROOT / path)}


def test_ratchet_rejects_rule_increase_and_new_debt_path() -> None:
    baseline = MaintainabilityBaseline(
        limits={"C901": 1, "PLR0912": 0, "PLR0915": 0},
        approved_paths=frozenset({"src/ai4binance/existing.py"}),
    )

    result = evaluate_findings(
        ROOT,
        baseline,
        (
            _finding("C901", "src/ai4binance/existing.py"),
            _finding("C901", "src/ai4binance/new.py"),
        ),
    )

    assert result.passed is False
    assert result.violations == (
        "C901 increased from 1 to 2",
        "maintainability debt appeared in unapproved path: src/ai4binance/new.py",
    )


def test_repository_maintainability_baseline_is_current() -> None:
    baseline = load_baseline(BASELINE_PATH)
    result = evaluate_findings(ROOT, baseline, collect_ruff_findings(ROOT))

    assert set(baseline.limits) == set(RULES)
    assert result.passed, result.violations

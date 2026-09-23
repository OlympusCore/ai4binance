"""Tests for the Ruff maintainability non-regression gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai4binance.ops import maintainability_ratchet as ratchet
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


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"schema_version": 1, "limits": {}, "approved_paths": []}',
        (
            '{"schema_version": 1, "limits": {"C901": 0, "PLR0912": 0,'
            ' "PLR0915": -1}, "approved_paths": []}'
        ),
        (
            '{"schema_version": 1, "limits": {"C901": 0, "PLR0912": 0,'
            ' "PLR0915": 0}, "approved_paths": ["outside.py"]}'
        ),
    ],
)
def test_load_baseline_rejects_invalid_governed_shapes(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="maintainability"):
        load_baseline(path)


def test_collect_findings_and_evaluate_fail_closed_for_bad_tool_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = type(
        "Completed", (), {"returncode": 2, "stderr": "tool failed", "stdout": ""}
    )()
    monkeypatch.setattr(ratchet.subprocess, "run", lambda *_args, **_kwargs: completed)
    with pytest.raises(RuntimeError, match="tool failed"):
        collect_ruff_findings(ROOT)

    malformed = type("Completed", (), {"returncode": 0, "stderr": "", "stdout": "{}"})()
    monkeypatch.setattr(ratchet.subprocess, "run", lambda *_args, **_kwargs: malformed)
    with pytest.raises(ValueError, match="JSON array"):
        collect_ruff_findings(ROOT)

    baseline = MaintainabilityBaseline(
        limits=dict.fromkeys(RULES, 0), approved_paths=frozenset()
    )
    with pytest.raises(ValueError, match="unexpected rule"):
        evaluate_findings(ROOT, baseline, ({"code": "BAD", "filename": "x"},))
    with pytest.raises(ValueError, match="filename is invalid"):
        evaluate_findings(ROOT, baseline, ({"code": "C901", "filename": 1},))
    with pytest.raises(ValueError, match="escaped"):
        evaluate_findings(
            ROOT, baseline, ({"code": "C901", "filename": "C:/outside.py"},)
        )


def test_main_reports_result_and_resolves_relative_baseline(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ratchet, "collect_ruff_findings", lambda _root: ())
    assert (
        ratchet.main(("--repository-root", str(ROOT), "--baseline", str(BASELINE_PATH)))
        == 0
    )
    assert '"status": "PASS"' in capsys.readouterr().out

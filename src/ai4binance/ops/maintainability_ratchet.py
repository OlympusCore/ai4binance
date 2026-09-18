"""Fail-closed Ruff maintainability non-regression gate."""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

RULES = ("C901", "PLR0912", "PLR0915")
DEFAULT_BASELINE = Path("config/quality/ruff-maintainability-baseline.json")


@dataclass(frozen=True, slots=True)
class MaintainabilityBaseline:
    """Approved debt ceiling and the files that currently carry that debt."""

    limits: Mapping[str, int]
    approved_paths: frozenset[str]


@dataclass(frozen=True, slots=True)
class MaintainabilityResult:
    """Deterministic comparison of current findings with the baseline."""

    counts: Mapping[str, int]
    violations: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.violations


def load_baseline(path: Path) -> MaintainabilityBaseline:
    """Load and validate the immutable ratchet baseline."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("maintainability baseline schema_version must be 1")
    raw_limits = payload.get("limits")
    raw_paths = payload.get("approved_paths")
    if not isinstance(raw_limits, dict) or set(raw_limits) != set(RULES):
        raise ValueError("maintainability baseline limits must cover governed rules")
    if any(not isinstance(value, int) or value < 0 for value in raw_limits.values()):
        raise ValueError(
            "maintainability baseline limits must be non-negative integers"
        )
    if (
        not isinstance(raw_paths, list)
        or raw_paths != sorted(set(raw_paths))
        or any(
            not isinstance(item, str) or not item.startswith("src/")
            for item in raw_paths
        )
    ):
        raise ValueError("maintainability approved_paths must be sorted source paths")
    return MaintainabilityBaseline(
        limits={str(code): cast(int, value) for code, value in raw_limits.items()},
        approved_paths=frozenset(cast(list[str], raw_paths)),
    )


def collect_ruff_findings(repository_root: Path) -> tuple[dict[str, object], ...]:
    """Run the repository Ruff executable and return governed findings."""

    completed = subprocess.run(  # noqa: S603  # nosec B603
        (
            sys.executable,
            "-m",
            "ruff",
            "check",
            "src",
            "--select",
            ",".join(RULES),
            "--output-format",
            "json",
        ),
        cwd=repository_root,
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Ruff maintainability scan failed: {detail}")
    payload = json.loads(completed.stdout or "[]")
    if not isinstance(payload, list) or any(
        not isinstance(item, dict) for item in payload
    ):
        raise ValueError("Ruff maintainability output must be a JSON array")
    return tuple(cast(list[dict[str, object]], payload))


def evaluate_findings(
    repository_root: Path,
    baseline: MaintainabilityBaseline,
    findings: Sequence[Mapping[str, object]],
) -> MaintainabilityResult:
    """Reject increases and findings in files outside the approved debt set."""

    root = repository_root.resolve()
    counts: Counter[str] = Counter()
    paths: set[str] = set()
    for finding in findings:
        code = finding.get("code")
        filename = finding.get("filename")
        if not isinstance(code, str) or code not in RULES:
            raise ValueError("Ruff finding contains an unexpected rule")
        if not isinstance(filename, str):
            raise ValueError("Ruff finding filename is invalid")
        try:
            relative = Path(filename).resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("Ruff finding escaped the repository root") from exc
        counts[code] += 1
        paths.add(relative)

    violations = [
        f"{code} increased from {baseline.limits[code]} to {counts[code]}"
        for code in RULES
        if counts[code] > baseline.limits[code]
    ]
    violations.extend(
        f"maintainability debt appeared in unapproved path: {path}"
        for path in sorted(paths - baseline.approved_paths)
    )
    return MaintainabilityResult(
        counts={code: counts[code] for code in RULES},
        violations=tuple(violations),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    parsed = build_parser().parse_args(arguments)
    root = parsed.repository_root.resolve()
    baseline_path = parsed.baseline
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path
    baseline = load_baseline(baseline_path)
    result = evaluate_findings(root, baseline, collect_ruff_findings(root))
    print(
        json.dumps(
            {
                "status": "PASS" if result.passed else "FAIL",
                "rules": list(RULES),
                "counts": result.counts,
                "limits": dict(baseline.limits),
                "violations": list(result.violations),
            },
            sort_keys=True,
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

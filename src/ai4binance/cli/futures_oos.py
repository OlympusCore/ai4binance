"""Local research-only CLI for exact-bound Futures OOS publication."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Final

from ai4binance.validation import (
    FuturesOosEvidenceWriter,
    FuturesOosPublicationService,
    FuturesOosRevisionResolver,
    FuturesOosRevisionSnapshot,
    ParameterSet,
    RuntimeFuturesBacktestAdapter,
    RuntimeFuturesBacktestConfig,
    RuntimeFuturesReplayLoader,
    WalkForwardConfig,
    classify_validation_regime,
)
from ai4binance.validation.futures_oos import (
    RUNTIME_FUTURES_STOP_LOSS_RATIO,
    RUNTIME_FUTURES_TAKE_PROFIT_RATIO,
)
from ai4binance.whale_fusion.models import PriceOiRegime

_MAX_GIT_OUTPUT_BYTES: Final = 65_536
_DIRECTIONAL_SETUPS: Final = tuple(
    item.value
    for item in (
        PriceOiRegime.NEW_LONG_PARTICIPATION,
        PriceOiRegime.SHORT_COVERING,
        PriceOiRegime.NEW_SHORT_PRESSURE,
        PriceOiRegime.DELEVERAGING,
    )
)


@dataclass(frozen=True, slots=True)
class LocalGitFuturesOosRevisionResolver:
    """Resolve one exact clean revision from the named repository only."""

    repository_root: Path
    timeout_seconds: float = 10.0
    max_output_bytes: int = _MAX_GIT_OUTPUT_BYTES
    _resolved_root: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0.1 <= self.timeout_seconds <= 30.0:
            raise ValueError("Futures OOS Git timeout is outside the safe range")
        if not 1_024 <= self.max_output_bytes <= 1_048_576:
            raise ValueError("Futures OOS Git output bound is outside the safe range")
        root = self.repository_root.resolve()
        git_marker = root / ".git"
        if not root.is_dir() or not git_marker.exists() or git_marker.is_symlink():
            raise ValueError("FUTURES_OOS_REPOSITORY_ROOT_INVALID")
        object.__setattr__(self, "_resolved_root", root)

    def __call__(self) -> FuturesOosRevisionSnapshot:
        git = shutil.which("git")
        if git is None:
            raise ValueError("FUTURES_OOS_GIT_UNAVAILABLE")
        top_level = self._run_git(git, "rev-parse", "--show-toplevel")
        try:
            observed_root = Path(top_level.strip()).resolve()
        except OSError as error:
            raise ValueError("FUTURES_OOS_REPOSITORY_ROOT_MISMATCH") from error
        if observed_root != self._resolved_root:
            raise ValueError("FUTURES_OOS_REPOSITORY_ROOT_MISMATCH")
        revision = self._run_git(git, "rev-parse", "--verify", "HEAD").strip()
        status = self._run_git(
            git,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        return FuturesOosRevisionSnapshot(
            code_revision=revision,
            repository_clean=not bool(status.strip()),
        )

    def _run_git(self, executable: str, *arguments: str) -> str:
        try:
            completed = subprocess.run(  # noqa: S603  # nosec B603
                (executable, "-C", str(self._resolved_root), *arguments),
                cwd=self._resolved_root,
                check=False,
                capture_output=True,
                text=False,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError("FUTURES_OOS_GIT_COMMAND_FAILED") from error
        captured_size = len(completed.stdout) + len(completed.stderr)
        if captured_size > self.max_output_bytes:
            raise ValueError("FUTURES_OOS_GIT_OUTPUT_TOO_LARGE")
        if completed.returncode != 0:
            raise ValueError("FUTURES_OOS_GIT_COMMAND_FAILED")
        try:
            return completed.stdout.decode("utf-8")
        except UnicodeError as error:
            raise ValueError("FUTURES_OOS_GIT_OUTPUT_INVALID") from error


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded local Futures OOS publication parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate a checksum-bound local Futures replay and publish "
            "research-only OOS evidence."
        )
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--replay-file",
        required=True,
        help="Replay JSON path relative to runtime/data/datasets/futures.",
    )
    parser.add_argument("--setup", required=True, choices=_DIRECTIONAL_SETUPS)
    parser.add_argument("--train-size", required=True, type=_positive_integer)
    parser.add_argument("--test-size", required=True, type=_positive_integer)
    parser.add_argument("--step-size", required=True, type=_positive_integer)
    return parser


def main(
    arguments: Sequence[str] | None = None,
    *,
    revision_resolver: FuturesOosRevisionResolver | None = None,
) -> int:
    """Run local replay validation and emit a bounded JSON status payload."""

    parsed = build_parser().parse_args(arguments)
    repository_root = parsed.repository_root.resolve()
    replay_root = repository_root / "runtime" / "data" / "datasets" / "futures"
    evidence_root = (
        repository_root / "runtime" / "artifacts" / "validation" / "futures_oos"
    )
    try:
        dataset = RuntimeFuturesReplayLoader(replay_root).load(parsed.replay_file)
        setup = PriceOiRegime(parsed.setup)
        parameters = (_canonical_parameters(),)
        service = FuturesOosPublicationService(
            writer=FuturesOosEvidenceWriter(evidence_root),
            revision_resolver=(
                revision_resolver
                if revision_resolver is not None
                else LocalGitFuturesOosRevisionResolver(repository_root)
            ),
        )
        result = service.publish(
            dataset=dataset,
            setup=setup,
            parameters=parameters,
            strategy_factory=lambda selected: _strategy(setup, selected),
            regime_classifier=classify_validation_regime,
            config=WalkForwardConfig(
                train_size=parsed.train_size,
                test_size=parsed.test_size,
                step_size=parsed.step_size,
            ),
        )
    except (TypeError, ValueError) as error:
        _print_payload(
            {
                "status": "BLOCKED",
                "blockers": [_bounded_blocker(error)],
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        )
        return 2
    except OSError:
        _print_payload(
            {
                "status": "BLOCKED",
                "blockers": ["FUTURES_OOS_LOCAL_IO_FAILED"],
                "execution_allowed": False,
                "promotion_status": "RESEARCH_ONLY",
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        )
        return 2
    _print_payload(
        {
            "status": "OOS_EVIDENCE_PUBLISHED",
            "report_id": result.report_id,
            "strategy_sha256": result.strategy_sha256,
            "dataset_sha256": result.dataset_sha256,
            "code_revision": result.code_revision,
            "evidence_id": result.evidence.evidence_id,
            "evidence_path": result.evidence.evidence_path,
            "artifact_path": result.evidence.artifact_path,
            "created": result.evidence.created,
            "blockers": [],
            "execution_allowed": False,
            "promotion_status": "STAGED_CANDIDATE",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    )
    return 0


def _canonical_parameters() -> ParameterSet:
    return ParameterSet(
        "runtime-futures-canonical",
        (
            ("stop_loss_ratio", float(RUNTIME_FUTURES_STOP_LOSS_RATIO)),
            ("take_profit_ratio", float(RUNTIME_FUTURES_TAKE_PROFIT_RATIO)),
        ),
    )


def _strategy(
    setup: PriceOiRegime,
    parameters: ParameterSet,
) -> RuntimeFuturesBacktestAdapter:
    values = dict(parameters.values)
    return RuntimeFuturesBacktestAdapter(
        RuntimeFuturesBacktestConfig(
            setup=setup,
            stop_loss_ratio=Decimal(str(values["stop_loss_ratio"])),
            take_profit_ratio=Decimal(str(values["take_profit_ratio"])),
        )
    )


def _positive_integer(raw: str) -> int:
    value = int(raw)
    if not 2 <= value <= 1_000_000:
        raise argparse.ArgumentTypeError(
            "window sizes must be between two and one million"
        )
    return value


def _bounded_blocker(error: TypeError | ValueError) -> str:
    blocker = str(error).strip()
    if not blocker or len(blocker) > 256:
        return "FUTURES_OOS_PUBLICATION_FAILED"
    return blocker


def _print_payload(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())

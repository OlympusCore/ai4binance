"""Shell-safe command line helpers for the quality gate wrapper."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ai4binance.ops.quality_gate.policy import (
    AffectedScopeResolutionError,
    load_quality_gate_policy,
    resolve_profile_pytest_arguments,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the quality gate helper parser."""
    parser = argparse.ArgumentParser(description="AI4BINANCE quality gate helper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    selector = subparsers.add_parser(
        "select-tests",
        help="Resolve profile pytest arguments from the canonical gate policy.",
    )
    selector.add_argument("--repository-root", type=Path, required=True)
    selector.add_argument("--config", type=Path, required=True)
    selector.add_argument(
        "--profile",
        choices=("fast", "standard", "full"),
        required=True,
    )
    selector.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help="Repository-relative changed path. Repeat for multiple paths.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one quality gate helper command."""
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "select-tests":
        return _select_tests(parsed)
    print(json.dumps({"status": "ERROR", "error": "unknown command"}))
    return 2


def _select_tests(parsed: argparse.Namespace) -> int:
    policy = load_quality_gate_policy(parsed.config)
    try:
        pytest_arguments = resolve_profile_pytest_arguments(
            policy,
            parsed.profile,
            parsed.repository_root,
            tuple(parsed.changed_path),
        )
    except AffectedScopeResolutionError as error:
        print(
            json.dumps(
                {
                    "status": "ESCALATE",
                    "profile": parsed.profile,
                    "error": str(error),
                    "escalate_to": error.escalate_to,
                    "unknown_paths": error.unknown_paths,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "PASS",
                "profile": parsed.profile,
                "pytest_arguments": pytest_arguments,
                "selected_test_count": sum(
                    1 for item in pytest_arguments if _is_pytest_selection(item)
                ),
            },
            sort_keys=True,
        )
    )
    return 0


def _is_pytest_selection(argument: str) -> bool:
    return argument.endswith(".py") or ".py::" in argument

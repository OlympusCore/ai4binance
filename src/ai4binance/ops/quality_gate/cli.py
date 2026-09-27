"""Shell-safe command line helpers for the quality gate wrapper."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ai4binance.ops.quality_gate.policy import (
    AffectedScopeResolutionError,
    changed_repository_paths,
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
    selector.add_argument("--base")
    selector.add_argument("--head")
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
    binder = subparsers.add_parser("bind-evidence")
    binder.add_argument("--repository-root", type=Path, required=True)
    binder.add_argument("--run-id", required=True)
    binder.add_argument("--junit-path", type=Path, required=True)
    binder.add_argument("--archive-run", action="store_true")
    failure_binder = subparsers.add_parser("bind-failure-evidence")
    failure_binder.add_argument("--repository-root", type=Path, required=True)
    failure_binder.add_argument("--run-id", required=True)
    failure_binder.add_argument("--archive-run", action="store_true")
    profile = subparsers.add_parser("profile")
    profile.add_argument("--config", type=Path, required=True)
    profile.add_argument(
        "--profile", choices=("fast", "standard", "full"), required=True
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one quality gate helper command."""
    parsed = build_parser().parse_args(arguments)
    if parsed.command == "select-tests":
        return _select_tests(parsed)
    if parsed.command == "profile":
        from dataclasses import asdict

        print(
            json.dumps(
                asdict(load_quality_gate_policy(parsed.config).profiles[parsed.profile])
            )
        )
        return 0
    if parsed.command == "bind-evidence":
        from ai4binance.ops.quality_gate.telemetry import (
            archive_quality_evidence,
            bind_quality_evidence,
        )

        payload = json.load(sys.stdin)
        bound = bind_quality_evidence(
            parsed.repository_root,
            payload,
            run_id=parsed.run_id,
            junit_path=parsed.junit_path,
            workspace_attestation=payload["workspace_attestation"],
        )
        if parsed.archive_run:
            archive_quality_evidence(parsed.repository_root, bound)
        print(json.dumps(bound))
        return 0
    if parsed.command == "bind-failure-evidence":
        from ai4binance.ops.quality_gate.telemetry import (
            archive_quality_evidence,
            bind_quality_failure_evidence,
        )

        payload = json.load(sys.stdin)
        bound = bind_quality_failure_evidence(
            parsed.repository_root,
            payload,
            run_id=parsed.run_id,
            workspace_attestation=payload["workspace_attestation"],
        )
        if parsed.archive_run:
            archive_quality_evidence(parsed.repository_root, bound)
        print(json.dumps(bound))
        return 0
    print(json.dumps({"status": "ERROR", "error": "unknown command"}))
    return 2


def _select_tests(parsed: argparse.Namespace) -> int:
    try:
        policy = load_quality_gate_policy(parsed.config)
        changed_paths = tuple(parsed.changed_path)
        if parsed.base or parsed.head:
            changed_paths = tuple(
                sorted(
                    set(changed_paths)
                    | set(
                        changed_repository_paths(
                            parsed.repository_root,
                            base=parsed.base,
                            head=parsed.head,
                        )
                    )
                )
            )
        pytest_arguments = resolve_profile_pytest_arguments(
            policy,
            parsed.profile,
            parsed.repository_root,
            changed_paths,
            base=parsed.base,
            head=parsed.head,
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
    except ValueError as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}), file=sys.stderr)
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

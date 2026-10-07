"""Inspect the canonical Git baseline; observations never authorize mutations."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

RULE_ID = "AI4B-GOV-GIT-001"
OPERATIONS = (
    "completion",
    "preflight",
    "quality",
    "pre_commit",
    "pre_push",
    "create_branch",
    "create_worktree",
    "ci",
)
CORE_PATH = "docs/governance/framework_core_vnext_governance.md"
POLICY_PATH = "docs/governance/policy_manifest_governance.md"
type Fail = Callable[[str], None]


@dataclass(frozen=True)
class GitPolicy:
    """Pinned operational projection of Core section 3.2."""

    canonical_root: Path
    canonical_remote_url: str


def _git(root: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise OSError("Git is unavailable")
    return subprocess.run(  # noqa: S603  # nosec B603
        [executable, "-C", str(root), *arguments],
        capture_output=True,
        check=True,
        timeout=20,
        encoding="utf-8",
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
    ).stdout


def _heads(raw: str) -> dict[str, str]:
    refs: dict[str, str] = {}
    for line in raw.splitlines():
        oid, ref = line.split()
        if (
            not ref.startswith("refs/heads/")
            or ref in refs
            or len(oid) not in {40, 64}
            or any(char not in "0123456789abcdef" for char in oid)
        ):
            raise ValueError("Invalid branch observation")
        refs[ref] = oid
    return refs


def _policy(root: Path, *, remote_only: bool = False) -> GitPolicy:
    """Require accepted protected anchors as well as exact projection pins."""
    from ai4binance.governance.governance_enforcement_fabric import (
        load_governance_enforcement_fabric,
    )
    from ai4binance.governance.repository_validator import (
        read_verified_governed_document,
    )

    load_governance_enforcement_fabric(root)
    fabric = yaml.safe_load(
        (root / "config/governance/governance_enforcement_fabric.yaml").read_text(
            encoding="utf-8"
        )
    )
    projection = fabric["repository_git"]
    if projection["rule_id"] != RULE_ID:
        raise ValueError("Canonical Git rule identity is unavailable")
    for path, field in ((CORE_PATH, "core_sha256"), (POLICY_PATH, "policy_sha256")):
        text = (
            (root / path).read_text(encoding="utf-8")
            if remote_only
            else read_verified_governed_document(root, path)
        )
        if (
            RULE_ID not in text
            or sha256((root / path).read_bytes()).hexdigest() != projection[field]
        ):
            raise ValueError("Canonical Git authority differs from its projection")
    canonical = Path(projection["canonical_root"])
    endpoint = projection["canonical_remote_url"]
    if not canonical.is_absolute() or not isinstance(endpoint, str):
        raise ValueError("Canonical Git identity is unavailable")
    # No credentials, query strings, local transport or arbitrary Git options.
    if (
        not endpoint.startswith("https://github.com/")
        or not endpoint.endswith(".git")
        or any(char in endpoint for char in ("@", "?", "#", "\n", " "))
    ):
        raise ValueError("Unsupported canonical remote endpoint")
    return GitPolicy(canonical.resolve(), endpoint)


def _topology(
    root: Path,
    policy: GitPolicy,
    before: dict[str, str | None],
    report: dict[str, Any],
    fail: Fail,
) -> None:
    for key in ("root", "common"):
        value = before[key]
        if value is not None:
            actual = Path(value.strip()).resolve()
            if key == "common":
                actual = actual.parent
            if actual != policy.canonical_root or root != policy.canonical_root:
                fail("ROOT")
    raw = before["worktrees"]
    if raw is not None:
        paths = [
            Path(line.removeprefix("worktree ")).resolve()
            for line in raw.splitlines()
            if line.startswith("worktree ")
        ]
        report["worktree_count"] = len(paths)
        if paths != [policy.canonical_root]:
            fail("WORKTREES")
    report["head_ref"] = (before["head_ref"] or "DETACHED_OR_UNAVAILABLE").strip()
    if report["head_ref"] != "refs/heads/main":
        fail("HEAD_NOT_MAIN")


def _local_heads(
    before: dict[str, str | None], report: dict[str, Any], fail: Fail
) -> None:
    raw = before["heads"]
    if raw is not None:
        try:
            heads = _heads(raw)
            report["local_branch_count"] = len(heads)
            if set(heads) != {"refs/heads/main"}:
                fail("LOCAL_BRANCHES")
        except ValueError:
            fail("LOCAL_OBSERVATION_INVALID")


def _local_state(
    before: dict[str, str | None],
    remote_heads: dict[str, str] | None,
    report: dict[str, Any],
    fail: Fail,
    synchronization_sequence: bool,
) -> None:
    head_sha, main_sha = before["head_sha"], before["main_sha"]
    if head_sha is not None and main_sha is not None:
        shas = [head_sha.strip(), main_sha.strip()]
        report["local_shas"] = shas
        valid = all(
            len(oid) in {40, 64} and all(c in "0123456789abcdef" for c in oid)
            for oid in shas
        )
        if not valid:
            fail("LOCAL_OBSERVATION_INVALID")
        if shas[0] != shas[1]:
            fail("SHA_MISMATCH")
        report["remote_sha_equal"] = remote_heads is not None and set(shas) == {
            remote_heads.get("refs/heads/main")
        }
        preparing = (
            report["operation"] in {"pre_commit", "pre_push"}
            or synchronization_sequence
        )
        equality_required = report["operation"] == "completion" or not preparing
        if not report["remote_sha_equal"] and equality_required:
            fail("SHA_MISMATCH")
    if before["status"] is not None:
        report["clean"] = not before["status"]
        must_be_clean = (
            report["operation"] == "completion" or not report["task_scope"].strip()
        )
        if not report["clean"] and must_be_clean:
            fail("DIRTY")


def _finalize(report: dict[str, Any]) -> dict[str, Any]:
    report["status"] = "BLOCKED" if report["blockers"] else "PASS"
    if report["blockers"] or report["operation"] == "ci":
        return report
    if report.get("clean") is True and report.get("remote_sha_equal") is True:
        report["state"] = "VERIFIED_BASELINE"
        report["baseline_verified"] = True
    else:
        report["state"] = "CHANGE_IN_PROGRESS"
    return report


def _record_remote_heads(
    report: dict[str, Any], heads: dict[str, str] | None, fail: Fail
) -> None:
    if heads is None:
        return
    report["remote_heads"] = heads
    report["remote_branch_count"] = len(heads)
    if set(heads) != {"refs/heads/main"}:
        fail("REMOTE_BRANCHES")
    if "refs/heads/main" not in heads:
        fail("REMOTE_MAIN_MISSING")


def _fail(blockers: list[str], reason: str) -> None:
    blocker = f"GIT_COMPLETION_{reason}"
    if blocker not in blockers:
        blockers.append(blocker)


def _query(root: Path, *args: str, blockers: list[str], reason: str) -> str | None:
    try:
        return _git(root, *args)
    except OSError, ValueError, subprocess.SubprocessError:
        _fail(blockers, reason)
        return None


def _local(root: Path, blockers: list[str]) -> dict[str, str | None]:
    query = partial(_query, root, blockers=blockers)
    return {
        "root": query("rev-parse", "--show-toplevel", reason="ROOT_UNAVAILABLE"),
        "common": query(
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
            reason="COMMON_DIRECTORY_UNAVAILABLE",
        ),
        "worktrees": query(
            "worktree", "list", "--porcelain", reason="WORKTREES_UNAVAILABLE"
        ),
        "head_ref": query("symbolic-ref", "--quiet", "HEAD", reason="HEAD_NOT_MAIN"),
        "heads": query(
            "for-each-ref",
            "--format=%(objectname) %(refname)",
            "refs/heads",
            reason="LOCAL_BRANCHES_UNAVAILABLE",
        ),
        "head_sha": query(
            "rev-parse", "--verify", "HEAD", reason="HEAD_SHA_UNAVAILABLE"
        ),
        "main_sha": query(
            "rev-parse", "--verify", "refs/heads/main", reason="LOCAL_MAIN_MISSING"
        ),
        "status": query(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            reason="CLEANLINESS_UNAVAILABLE",
        ),
    }


def _canonical_endpoint(actual: str, canonical: object) -> bool:
    """Accept only the pinned HTTPS identity with its optional Git suffix."""
    return isinstance(canonical, str) and actual in {
        canonical,
        canonical.removesuffix(".git"),
    }


def _remote(
    root: Path, policy: GitPolicy, blockers: list[str]
) -> tuple[str | None, dict[str, str] | None]:
    query = partial(_query, root, blockers=blockers)
    fail = partial(_fail, blockers)
    names = query("remote", reason="REMOTE_CONFIGURATION_UNAVAILABLE")
    matches: list[str] = []
    for name in names.splitlines() if names is not None else ():
        fetch = query(
            "remote",
            "get-url",
            "--all",
            name,
            reason="REMOTE_CONFIGURATION_UNAVAILABLE",
        )
        push = query(
            "remote",
            "get-url",
            "--push",
            "--all",
            name,
            reason="REMOTE_CONFIGURATION_UNAVAILABLE",
        )
        if fetch is not None and push is not None:
            if all(
                _canonical_endpoint(
                    "\n".join(raw.splitlines()), policy.canonical_remote_url
                )
                for raw in (fetch, push)
            ):
                matches.append(name)
    if len(matches) != 1:
        fail("CANONICAL_REMOTE_UNRESOLVED")
        return None, None
    raw = query(
        "ls-remote",
        "--heads",
        policy.canonical_remote_url,
        reason="LIVE_REMOTE_UNAVAILABLE",
    )
    if raw is None:
        return matches[0], None
    try:
        return matches[0], _heads(raw)
    except ValueError:
        fail("REMOTE_OBSERVATION_INVALID")
        return matches[0], None


def inspect_git_boundary(
    root: Path,
    *,
    operation: str = "completion",
    task_scope: str = "",
    synchronization_sequence: bool = False,
) -> dict[str, Any]:
    """Evaluate independently; task scope records intent, never grants authority."""
    if operation not in OPERATIONS:
        raise ValueError("Unknown Git operation")
    root = root.resolve()
    blockers: list[str] = []
    report: dict[str, Any] = {
        "rule_id": RULE_ID,
        "repository_root": root.as_posix(),
        "operation": operation,
        "state": "NOT_VERIFIED",
        "status": "BLOCKED",
        "blockers": blockers,
        "task_scope": task_scope,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "scope": "REMOTE_ONLY" if operation == "ci" else "CANONICAL_WORKSTATION",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "baseline_verified": False,
        "authorization": "INDEPENDENT_USER_AND_GOVERNANCE_CONTROLS_REQUIRED",
    }

    fail = partial(_fail, blockers)

    if operation in {"create_branch", "create_worktree"}:
        fail("CREATION_PROHIBITED")
    try:
        active_policy = _policy(root, remote_only=operation == "ci")
    except OSError, ValueError, KeyError, TypeError:
        fail("AUTHORITY_UNAVAILABLE")
        return report

    before = _local(root, blockers) if operation != "ci" else {}
    remote_before = _remote(root, active_policy, blockers)
    name, remote_heads = remote_before
    report["canonical_remote_url"] = active_policy.canonical_remote_url
    report["canonical_remote_name"] = name
    _record_remote_heads(report, remote_heads, fail)

    if operation != "ci":
        _topology(root, active_policy, before, report, fail)
        _local_heads(before, report, fail)
        _local_state(before, remote_heads, report, fail, synchronization_sequence)
        if (
            operation in {"preflight", "quality", "pre_commit", "pre_push"}
            and not task_scope.strip()
        ):
            fail("TASK_SCOPE_REQUIRED")
        if _local(root, blockers) != before:
            fail("LOCAL_CHANGED_DURING_VERIFICATION")
    if _remote(root, active_policy, blockers) != remote_before:
        fail("REMOTE_CHANGED_DURING_VERIFICATION")
    return _finalize(report)


def inspect_git_completion(root: Path) -> dict[str, Any]:
    """Completion always requires clean and live synchronized state."""
    return inspect_git_boundary(root)


def validate_push_updates(
    report: dict[str, Any], raw: str, remote_name: str, remote_url: str
) -> None:
    """Constrain the exact update set before independent Git authorization."""
    lines = [line.split() for line in raw.splitlines() if line.strip()]
    if not lines:
        return
    valid = (
        len(lines) == 1
        and len(lines[0]) == 4
        and remote_name == report.get("canonical_remote_name")
        and _canonical_endpoint(remote_url, report.get("canonical_remote_url"))
    )
    if valid:
        source, oid, target, _remote_oid = lines[0]
        valid = (
            source == target == "refs/heads/main"
            and oid == report.get("local_shas", [None])[0]
        )
    if not valid:
        report["blockers"].append("GIT_COMPLETION_PUSH_UPDATE_PROHIBITED")
        report["status"] = "BLOCKED"
        report["state"] = "NOT_VERIFIED"
        report["baseline_verified"] = False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).parents[4]
    )
    parser.add_argument("--operation", choices=OPERATIONS, default="completion")
    parser.add_argument("--task-scope", default="")
    parser.add_argument("--synchronization-sequence", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--push-updates-path", type=Path)
    parser.add_argument("--remote-name", default="")
    parser.add_argument("--remote-url", default="")
    args = parser.parse_args()
    report = inspect_git_boundary(
        args.repository_root,
        operation=args.operation,
        task_scope=args.task_scope,
        synchronization_sequence=args.synchronization_sequence,
    )
    if args.push_updates_path is not None:
        if args.operation != "pre_push":
            raise ValueError("Push updates require the pre_push boundary")
        validate_push_updates(
            report,
            args.push_updates_path.read_text(encoding="utf-8"),
            args.remote_name,
            args.remote_url,
        )
    if args.output_json is not None:
        from ai4binance.infrastructure.persistence.safe_json import (
            write_json_object_verified,
        )

        output = args.output_json.resolve()
        if not output.is_relative_to((args.repository_root / "runtime").resolve()):
            raise ValueError("Git evidence must remain inside runtime")
        write_json_object_verified(
            output, report, blocker="GIT_EVIDENCE_WRITE_FAILED", indent=2
        )
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())

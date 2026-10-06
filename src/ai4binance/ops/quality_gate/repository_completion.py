"""Observe Git completion requirements without changing branches or worktrees."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import NotRequired, TypedDict


class GitCompletionReport(TypedDict):
    """Current observations, never permission to mutate the repository."""

    repository_root: str
    blockers: list[str]
    status: str
    remote_heads: NotRequired[dict[str, str]]
    remote_branch_count: NotRequired[int]
    canonical_root: NotRequired[str]
    worktree_count: NotRequired[int]
    local_branch_count: NotRequired[int]
    head_ref: NotRequired[str]
    local_shas: NotRequired[list[str]]
    clean: NotRequired[bool]


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
        sha, ref = line.split()
        if (
            not ref.startswith("refs/heads/")
            or ref in refs
            or len(sha) not in {40, 64}
            or any(character not in "0123456789abcdef" for character in sha)
        ):
            raise ValueError("Invalid branch observation")
        refs[ref] = sha
    return refs


_LOCAL_COMMANDS = (
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "--path-format=absolute", "--git-common-dir"),
    ("worktree", "list", "--porcelain"),
    ("symbolic-ref", "--quiet", "HEAD"),
    ("for-each-ref", "--format=%(objectname) %(refname)", "refs/heads"),
    ("rev-parse", "HEAD", "refs/heads/main", "refs/remotes/origin/main"),
    ("status", "--porcelain=v1", "--untracked-files=all"),
    ("remote", "get-url", "--all", "origin"),
    ("remote", "get-url", "--push", "--all", "origin"),
)


def _remote(root: Path) -> tuple[str, dict[str, str]]:
    fetch = _git(root, "remote", "get-url", "--all", "origin").splitlines()
    push = _git(root, "remote", "get-url", "--push", "--all", "origin").splitlines()
    if len(fetch) != 1 or push != fetch:
        raise ValueError("Canonical remote is ambiguous")
    return fetch[0], _heads(_git(root, "ls-remote", "--heads", fetch[0]))


def _local_report(root: Path, before: tuple[str, ...]) -> GitCompletionReport:
    canonical_root = Path(before[1].strip()).resolve().parent
    worktrees = [
        Path(line.removeprefix("worktree ")).resolve()
        for line in before[2].splitlines()
        if line.startswith("worktree ")
    ]
    local_heads = _heads(before[4])
    conditions = (
        (canonical_root == root == Path(before[0].strip()).resolve(), "ROOT"),
        (worktrees == [root], "WORKTREES"),
        (before[3].strip() == "refs/heads/main", "HEAD_NOT_MAIN"),
        (set(local_heads) == {"refs/heads/main"}, "LOCAL_BRANCHES"),
        (not before[6], "DIRTY"),
    )
    return {
        "repository_root": root.as_posix(),
        "status": "BLOCKED",
        "blockers": [f"GIT_COMPLETION_{reason}" for ok, reason in conditions if not ok],
        "canonical_root": canonical_root.as_posix(),
        "worktree_count": len(worktrees),
        "local_branch_count": len(local_heads),
        "head_ref": before[3].strip(),
        "local_shas": before[5].splitlines(),
        "clean": not before[6],
    }


def _remote_blockers(
    before: tuple[str, ...], endpoint: str, heads: dict[str, str]
) -> list[str]:
    shas = before[5].splitlines()
    conditions = (
        (
            before[7].splitlines() == before[8].splitlines() == [endpoint],
            "REMOTE_CONFIGURATION_CHANGED",
        ),
        (set(heads) == {"refs/heads/main"}, "REMOTE_BRANCHES"),
        (
            len(shas) == 3 and set(shas) == {heads.get("refs/heads/main")},
            "SHA_MISMATCH",
        ),
    )
    return [f"GIT_COMPLETION_{reason}" for ok, reason in conditions if not ok]


def inspect_git_completion(root: Path) -> GitCompletionReport:
    """Require a stable local observation bracketed by two live remote queries."""
    root = root.resolve()
    report: GitCompletionReport = {
        "repository_root": root.as_posix(),
        "blockers": [],
        "status": "BLOCKED",
    }
    blockers: list[str] = []
    try:
        endpoint, remote_before = _remote(root)
    except OSError, ValueError, subprocess.SubprocessError:
        blockers.append("GIT_COMPLETION_LIVE_REMOTE_UNAVAILABLE")
        remote_before = None
    try:
        before = tuple(_git(root, *command) for command in _LOCAL_COMMANDS)
        report = _local_report(root, before)
        blockers.extend(report["blockers"])
        if remote_before is not None:
            blockers.extend(_remote_blockers(before, endpoint, remote_before))
        if tuple(_git(root, *command) for command in _LOCAL_COMMANDS) != before:
            blockers.append("GIT_COMPLETION_LOCAL_CHANGED_DURING_VERIFICATION")
    except OSError, ValueError, subprocess.SubprocessError:
        blockers.append("GIT_COMPLETION_LOCAL_UNAVAILABLE_OR_DETACHED")
    if remote_before is not None:
        report["remote_heads"] = remote_before
        report["remote_branch_count"] = len(remote_before)
        try:
            if _heads(_git(root, "ls-remote", "--heads", endpoint)) != remote_before:
                blockers.append("GIT_COMPLETION_REMOTE_CHANGED_DURING_VERIFICATION")
        except OSError, ValueError, subprocess.SubprocessError:
            blockers.append("GIT_COMPLETION_LIVE_REMOTE_UNAVAILABLE")
    report["blockers"] = list(dict.fromkeys(blockers))
    report["status"] = "BLOCKED" if blockers else "PASS"
    return report


def main() -> int:
    """Expose the same observer used by the Stop hook for explicit verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).parents[4]
    )
    args = parser.parse_args()
    report = inspect_git_completion(args.repository_root)
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())

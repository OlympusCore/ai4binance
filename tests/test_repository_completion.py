"""Test-only Git observations; never change the real repository or remote."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai4binance.ops.quality_gate import repository_completion as completion

SHA = "a" * 40
OTHER = "b" * 40
type Observations = dict[tuple[str, ...], str]


@pytest.fixture
def observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[tuple[str, ...], str]:
    root = tmp_path.resolve()
    values = {
        (
            "remote",
            "get-url",
            "--all",
            "origin",
        ): "https://example.invalid/test-only.git\n",
        (
            "remote",
            "get-url",
            "--push",
            "--all",
            "origin",
        ): "https://example.invalid/test-only.git\n",
        (
            "ls-remote",
            "--heads",
            "https://example.invalid/test-only.git",
        ): f"{SHA}\trefs/heads/main\n",
        ("rev-parse", "--show-toplevel"): str(root) + "\n",
        ("rev-parse", "--path-format=absolute", "--git-common-dir"): str(root / ".git")
        + "\n",
        (
            "worktree",
            "list",
            "--porcelain",
        ): f"worktree {root}\nHEAD {SHA}\nbranch refs/heads/main\n\n",
        ("symbolic-ref", "--quiet", "HEAD"): "refs/heads/main\n",
        (
            "for-each-ref",
            "--format=%(objectname) %(refname)",
            "refs/heads",
        ): f"{SHA} refs/heads/main\n",
        ("rev-parse", "HEAD", "refs/heads/main", "refs/remotes/origin/main"): f"{SHA}\n"
        * 3,
        ("status", "--porcelain=v1", "--untracked-files=all"): "",
    }
    monkeypatch.setattr(completion, "_git", lambda _root, *args: values[args])
    return values


def test_clean_single_main_with_live_equal_shas_passes(
    tmp_path: Path, observations: Observations
) -> None:
    result = completion.inspect_git_completion(tmp_path)
    assert result["status"] == "PASS"
    assert result["blockers"] == []
    assert (
        result["worktree_count"]
        == result["local_branch_count"]
        == result["remote_branch_count"]
        == 1
    )


@pytest.mark.parametrize(
    ("command", "suffix", "blocker"),
    [
        (("worktree", "list", "--porcelain"), "worktree {root}/extra\n\n", "WORKTREES"),
        (
            ("for-each-ref", "--format=%(objectname) %(refname)", "refs/heads"),
            f"{SHA} refs/heads/extra\n",
            "LOCAL_BRANCHES",
        ),
        (
            ("ls-remote", "--heads", "https://example.invalid/test-only.git"),
            f"{SHA} refs/heads/extra\n",
            "REMOTE_BRANCHES",
        ),
        (
            ("status", "--porcelain=v1", "--untracked-files=all"),
            " M tracked.py\n",
            "DIRTY",
        ),
        (
            ("status", "--porcelain=v1", "--untracked-files=all"),
            "?? untracked.py\n",
            "DIRTY",
        ),
    ],
)
def test_rejects_extra_work_and_dirty_state(
    tmp_path: Path,
    observations: Observations,
    command: tuple[str, ...],
    suffix: str,
    blocker: str,
) -> None:
    observations[command] += suffix.format(root=tmp_path)
    assert (
        f"GIT_COMPLETION_{blocker}"
        in completion.inspect_git_completion(tmp_path)["blockers"]
    )


@pytest.mark.parametrize("position", [0, 1, 2])
def test_rejects_each_local_sha_mismatch(
    tmp_path: Path, observations: Observations, position: int
) -> None:
    shas = [SHA] * 3
    shas[position] = OTHER
    observations[
        ("rev-parse", "HEAD", "refs/heads/main", "refs/remotes/origin/main")
    ] = "\n".join(shas)
    assert (
        "GIT_COMPLETION_SHA_MISMATCH"
        in completion.inspect_git_completion(tmp_path)["blockers"]
    )


@pytest.mark.parametrize(
    "remote", ["", f"{OTHER} refs/heads/main\n", "malformed response"]
)
def test_remote_main_must_exist_and_match(
    tmp_path: Path, observations: Observations, remote: str
) -> None:
    observations[("ls-remote", "--heads", "https://example.invalid/test-only.git")] = (
        remote
    )
    assert completion.inspect_git_completion(tmp_path)["status"] == "BLOCKED"


@pytest.mark.parametrize(
    "command",
    [
        ("symbolic-ref", "--quiet", "HEAD"),
        ("ls-remote", "--heads", "https://example.invalid/test-only.git"),
    ],
)
def test_detached_head_and_failed_live_query_fail_closed(
    tmp_path: Path,
    observations: Observations,
    monkeypatch: pytest.MonkeyPatch,
    command: tuple[str, ...],
) -> None:
    def git(_root: Path, *args: str) -> str:
        if args == command:
            raise subprocess.CalledProcessError(1, "test-only Git failure")
        return observations[args]

    monkeypatch.setattr(completion, "_git", git)
    assert completion.inspect_git_completion(tmp_path)["status"] == "BLOCKED"


@pytest.mark.parametrize("location", ["local", "remote"])
def test_changes_during_verification_fail_closed(
    tmp_path: Path,
    observations: Observations,
    monkeypatch: pytest.MonkeyPatch,
    location: str,
) -> None:
    target = (
        ("worktree", "list", "--porcelain")
        if location == "local"
        else ("ls-remote", "--heads", "https://example.invalid/test-only.git")
    )
    calls = 0

    def git(_root: Path, *args: str) -> str:
        nonlocal calls
        if args == target:
            calls += 1
            if calls == 2:
                return observations[args].replace(SHA, OTHER)
        return observations[args]

    monkeypatch.setattr(completion, "_git", git)
    result = completion.inspect_git_completion(tmp_path)
    assert (
        f"GIT_COMPLETION_{location.upper()}_CHANGED_DURING_VERIFICATION"
        in result["blockers"]
    )


def test_different_push_endpoint_is_unverified(
    tmp_path: Path, observations: Observations
) -> None:
    observations[("remote", "get-url", "--push", "--all", "origin")] = (
        "https://example.invalid/other.git\n"
    )
    assert (
        "GIT_COMPLETION_LIVE_REMOTE_UNAVAILABLE"
        in completion.inspect_git_completion(tmp_path)["blockers"]
    )


def test_completion_definition_belongs_to_core_and_adapters_only_reference_it() -> None:
    root = Path(__file__).resolve().parents[1]
    core_path = "docs/governance/framework_core_vnext_governance.md"
    core = (root / core_path).read_text(encoding="utf-8")
    assert "authority_layer: L1_CORE_CONSTITUTION" in core
    assert "### 3.2 Repository Completion Invariant" in core
    rule = core.split("### 3.2 Repository Completion Invariant", 1)[1].split(
        "\n## 4.", 1
    )[0]
    rule = " ".join(rule.split())
    for condition in (
        "Exactly one registered worktree",
        "HEAD attached to `main`",
        "Exactly one local branch",
        "Exactly one branch on the live canonical remote",
        "refs/remotes/origin/main",
        "git status --porcelain=v1 --untracked-files=all",
        "Required quality, governance, protected-document, "
        "and acceptance controls pass",
        "Missing live remote evidence blocks `COMPLETE`",
        "Commit/push preparation must not require remote SHA equality",
        "Lower-authority instructions",
        "explicitly authorized amendment at this controlling authority level",
    ):
        assert condition in rule
    for path in (
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        "docs/providers/instruction_codex_provider.md",
        "docs/providers/instruction_claude_provider.md",
    ):
        adapter = (root / path).read_text(encoding="utf-8")
        assert core_path in adapter
        assert "section 3.2" in adapter
        assert "## 12. Repository Completion Rule" not in adapter
        assert "Exactly one registered worktree" not in adapter
        assert "refs/remotes/origin/main" not in adapter

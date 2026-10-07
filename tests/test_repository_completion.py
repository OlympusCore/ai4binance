"""TEST_ONLY mocked Git responses; no canonical topology mutation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ai4binance.ops.quality_gate import repository_completion as completion

SHA = "a" * 40
OTHER = "b" * 40
ENDPOINT = "https://github.com/test-only/canonical.git"
type Observations = dict[tuple[str, ...], str]


@pytest.mark.parametrize(
    ("field", "value", "exit_code"),
    [
        ("execution_allowed", True, 0),
        ("live_eligibility_status", "TEST_ONLY_UNSAFE", 0),
        ("rule_id", "TEST_ONLY_OTHER_RULE", 0),
        ("repository_root", "/TEST_ONLY_OTHER_ROOT", 0),
        ("operation", "completion", 0),
        ("blockers", ["TEST_ONLY_UNREGISTERED"], 0),
        ("status", "PASS", 1),
    ],
)
def test_repository_validator_cli_protocol_rejects_invalid_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    exit_code: int,
) -> None:
    """TEST_ONLY serialized child observations never provide authority."""
    from ai4binance.governance import repository_validator

    parsed = repository_validator.build_parser().parse_args(
        ["--repository-root", str(tmp_path), "--git-task-scope", "TEST_ONLY protocol"]
    )
    payload: dict[str, object] = {
        "rule_id": completion.RULE_ID,
        "repository_root": tmp_path.resolve().as_posix(),
        "operation": "quality",
        "status": "PASS",
        "blockers": [],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    payload[field] = value
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            ["TEST_ONLY checker"], exit_code, stdout=json.dumps(payload)
        ),
    )
    assert repository_validator._git_boundary_payload(parsed)["blockers"] == [
        "GIT_COMPLETION_OBSERVATION_UNAVAILABLE"
    ]


@pytest.fixture
def observations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Observations:
    values = {
        ("remote",): "upstream\n",
        ("remote", "get-url", "--all", "upstream"): ENDPOINT + "\n",
        ("remote", "get-url", "--push", "--all", "upstream"): ENDPOINT + "\n",
        ("ls-remote", "--heads", ENDPOINT): f"{SHA}\trefs/heads/main\n",
        ("rev-parse", "--show-toplevel"): str(tmp_path) + "\n",
        ("rev-parse", "--path-format=absolute", "--git-common-dir"): str(
            tmp_path / ".git"
        )
        + "\n",
        (
            "worktree",
            "list",
            "--porcelain",
        ): f"worktree {tmp_path}\nHEAD {SHA}\nbranch refs/heads/main\n\n",
        ("symbolic-ref", "--quiet", "HEAD"): "refs/heads/main\n",
        (
            "for-each-ref",
            "--format=%(objectname) %(refname)",
            "refs/heads",
        ): f"{SHA} refs/heads/main\n",
        ("rev-parse", "--verify", "HEAD"): SHA + "\n",
        ("rev-parse", "--verify", "refs/heads/main"): SHA + "\n",
        ("status", "--porcelain=v1", "--untracked-files=all"): "",
    }
    monkeypatch.setattr(completion, "_git", lambda _root, *args: values[args])
    monkeypatch.setattr(
        completion,
        "_policy",
        lambda _root, **_kwargs: completion.GitPolicy(tmp_path.resolve(), ENDPOINT),
    )
    return values


def test_baseline_requires_fresh_remote_without_assuming_origin(
    tmp_path: Path, observations: Observations
) -> None:
    report = completion.inspect_git_completion(tmp_path)
    assert report["status"] == "PASS"
    assert report["state"] == "VERIFIED_BASELINE"
    assert report["canonical_remote_name"] == "upstream"
    assert (
        report["worktree_count"]
        == report["local_branch_count"]
        == report["remote_branch_count"]
        == 1
    )


@pytest.mark.parametrize("operation", ["create_branch", "create_worktree"])
def test_creation_is_always_rejected(
    tmp_path: Path, observations: Observations, operation: str
) -> None:
    report = completion.inspect_git_boundary(
        tmp_path, operation=operation, task_scope="TEST_ONLY approved task"
    )
    assert "GIT_COMPLETION_CREATION_PROHIBITED" in report["blockers"]
    assert report["baseline_verified"] is False


@pytest.mark.parametrize(
    "operation", ["preflight", "quality", "pre_commit", "pre_push"]
)
def test_authorized_edits_remain_possible_without_false_baseline(
    tmp_path: Path, observations: Observations, operation: str
) -> None:
    observations[("status", "--porcelain=v1", "--untracked-files=all")] = (
        " M test-only.py\n"
    )
    report = completion.inspect_git_boundary(
        tmp_path, operation=operation, task_scope="TEST_ONLY bounded user change"
    )
    assert report["status"] == "PASS"
    assert report["state"] == "CHANGE_IN_PROGRESS"
    assert report["baseline_verified"] is False
    assert report["execution_allowed"] is False
    assert (
        report["authorization"] == "INDEPENDENT_USER_AND_GOVERNANCE_CONTROLS_REQUIRED"
    )


@pytest.mark.parametrize("operation", ["completion", "preflight", "quality"])
def test_dirty_state_without_task_is_blocked(
    tmp_path: Path, observations: Observations, operation: str
) -> None:
    observations[("status", "--porcelain=v1", "--untracked-files=all")] = (
        "?? test-only.txt\n"
    )
    report = completion.inspect_git_boundary(tmp_path, operation=operation)
    assert "GIT_COMPLETION_DIRTY" in report["blockers"]


@pytest.mark.parametrize(
    ("command", "raw", "reason"),
    [
        (
            ("worktree", "list", "--porcelain"),
            "worktree {root}\n\nworktree {root}/extra\n",
            "WORKTREES",
        ),
        (
            ("for-each-ref", "--format=%(objectname) %(refname)", "refs/heads"),
            f"{SHA} refs/heads/main\n{OTHER} refs/heads/extra\n",
            "LOCAL_BRANCHES",
        ),
        (
            ("ls-remote", "--heads", ENDPOINT),
            f"{SHA} refs/heads/main\n{OTHER} refs/heads/extra\n",
            "REMOTE_BRANCHES",
        ),
        (("ls-remote", "--heads", ENDPOINT), "", "REMOTE_MAIN_MISSING"),
        (("rev-parse", "--verify", "HEAD"), OTHER + "\n", "SHA_MISMATCH"),
        (("rev-parse", "--verify", "refs/heads/main"), OTHER + "\n", "SHA_MISMATCH"),
        (
            ("ls-remote", "--heads", ENDPOINT),
            f"{OTHER} refs/heads/main\n",
            "SHA_MISMATCH",
        ),
        (("rev-parse", "--show-toplevel"), "{root}/alternate\n", "ROOT"),
        (("symbolic-ref", "--quiet", "HEAD"), "refs/heads/extra\n", "HEAD_NOT_MAIN"),
        (("ls-remote", "--heads", ENDPOINT), "malformed", "REMOTE_OBSERVATION_INVALID"),
    ],
)
def test_independent_violations(
    tmp_path: Path,
    observations: Observations,
    command: tuple[str, ...],
    raw: str,
    reason: str,
) -> None:
    observations[command] = raw.format(root=tmp_path)
    assert (
        f"GIT_COMPLETION_{reason}"
        in completion.inspect_git_completion(tmp_path)["blockers"]
    )


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        (("symbolic-ref", "--quiet", "HEAD"), "HEAD_NOT_MAIN"),
        (
            ("status", "--porcelain=v1", "--untracked-files=all"),
            "CLEANLINESS_UNAVAILABLE",
        ),
        (("ls-remote", "--heads", ENDPOINT), "LIVE_REMOTE_UNAVAILABLE"),
    ],
)
def test_errors_do_not_hide_independent_observations(
    tmp_path: Path,
    observations: Observations,
    monkeypatch: pytest.MonkeyPatch,
    command: tuple[str, ...],
    reason: str,
) -> None:
    def git(_root: Path, *args: str) -> str:
        if args == command:
            raise subprocess.CalledProcessError(
                1, "TEST_ONLY unavailable Git observation"
            )
        return observations[args]

    monkeypatch.setattr(completion, "_git", git)
    report = completion.inspect_git_completion(tmp_path)
    assert f"GIT_COMPLETION_{reason}" in report["blockers"]
    assert report["worktree_count"] == report["local_branch_count"] == 1
    if reason == "CLEANLINESS_UNAVAILABLE":
        assert "clean" not in report


def test_stale_cached_ref_cannot_override_live_remote(
    tmp_path: Path, observations: Observations
) -> None:
    observations[("rev-parse", "refs/remotes/upstream/main")] = SHA + "\n"
    observations[("ls-remote", "--heads", ENDPOINT)] = f"{OTHER} refs/heads/main\n"
    assert (
        "GIT_COMPLETION_SHA_MISMATCH"
        in completion.inspect_git_completion(tmp_path)["blockers"]
    )


@pytest.mark.parametrize("operation", ["pre_commit", "pre_push", "quality"])
def test_sync_preparation_defers_equality_but_completion_does_not(
    tmp_path: Path, observations: Observations, operation: str
) -> None:
    observations[("ls-remote", "--heads", ENDPOINT)] = f"{OTHER} refs/heads/main\n"
    report = completion.inspect_git_boundary(
        tmp_path,
        operation=operation,
        task_scope="TEST_ONLY explicit synchronization sequence",
        synchronization_sequence=True,
    )
    assert report["status"] == "PASS"
    assert report["state"] == "CHANGE_IN_PROGRESS"
    assert report["baseline_verified"] is False
    report = completion.inspect_git_boundary(
        tmp_path,
        task_scope="TEST_ONLY explicit synchronization sequence",
        synchronization_sequence=True,
    )
    assert report["status"] == "BLOCKED"


def test_ci_is_explicitly_remote_only(
    tmp_path: Path, observations: Observations
) -> None:
    for key in list(observations):
        if key[0] not in {"remote", "ls-remote"}:
            del observations[key]
    report = completion.inspect_git_boundary(tmp_path, operation="ci")
    assert report["status"] == "PASS"
    assert report["scope"] == "REMOTE_ONLY"
    assert report["state"] == "NOT_VERIFIED"
    assert report["baseline_verified"] is False
    assert "worktree_count" not in report


def test_mid_observation_changes_fail_closed(
    tmp_path: Path, observations: Observations, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def git(_root: Path, *args: str) -> str:
        nonlocal calls
        if args == ("ls-remote", "--heads", ENDPOINT):
            calls += 1
            if calls == 2:
                return f"{OTHER} refs/heads/main\n"
        return observations[args]

    monkeypatch.setattr(completion, "_git", git)
    assert (
        "GIT_COMPLETION_REMOTE_CHANGED_DURING_VERIFICATION"
        in completion.inspect_git_completion(tmp_path)["blockers"]
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://github.com/test-only/other.git",
        "http://github.com/test-only/canonical.git",
        "https://user@github.com/test-only/canonical.git",
        "https://github.com/test-only/canonical.git?override=true",
        "https://github.com/test-only/canonical.git#override",
        "git@github.com:test-only/canonical.git",
        ENDPOINT + ".git",
        ENDPOINT + "\n" + ENDPOINT,
    ],
)
def test_wrong_push_endpoint_is_not_canonical(
    tmp_path: Path, observations: Observations, endpoint: str
) -> None:
    observations[("remote", "get-url", "--push", "--all", "upstream")] = endpoint + "\n"
    assert (
        "GIT_COMPLETION_CANONICAL_REMOTE_UNRESOLVED"
        in completion.inspect_git_completion(tmp_path)["blockers"]
    )


@pytest.mark.parametrize("operation", ["ci", "pre_push"])
@pytest.mark.parametrize("suffixes", [(False, False), (False, True), (True, False)])
def test_checkout_remote_spelling_preserves_canonical_identity(
    tmp_path: Path,
    observations: Observations,
    operation: str,
    suffixes: tuple[bool, bool],
) -> None:
    for mode, suffix in zip(((), ("--push",)), suffixes, strict=True):
        observations[("remote", "get-url", *mode, "--all", "upstream")] = (
            ENDPOINT if suffix else ENDPOINT.removesuffix(".git")
        ) + "\n"
    report = completion.inspect_git_boundary(
        tmp_path, operation=operation, task_scope="TEST_ONLY canonical URL spelling"
    )
    assert report["status"] == "PASS"
    assert report["canonical_remote_url"] == ENDPOINT
    assert (
        report["authorization"] == "INDEPENDENT_USER_AND_GOVERNANCE_CONTROLS_REQUIRED"
    )
    if operation == "ci":
        assert report["scope"] == "REMOTE_ONLY"
        assert report["baseline_verified"] is False


def test_unaccepted_authority_cannot_enable_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(_root: Path, **_kwargs: object) -> completion.GitPolicy:
        raise ValueError("TEST_ONLY unaccepted authority")

    monkeypatch.setattr(completion, "_policy", unavailable)
    report = completion.inspect_git_boundary(tmp_path, operation="create_branch")
    assert set(report["blockers"]) == {
        "GIT_COMPLETION_AUTHORITY_UNAVAILABLE",
        "GIT_COMPLETION_CREATION_PROHIBITED",
    }


@pytest.mark.parametrize(
    "updates",
    [
        f"refs/heads/main {SHA} refs/heads/extra {OTHER}\n",
        f"refs/heads/extra {SHA} refs/heads/main {OTHER}\n",
        f"(delete) {'0' * 40} refs/heads/main {OTHER}\n",
        "malformed\n",
        f"refs/heads/main {OTHER} refs/heads/main {SHA}\n",
    ],
)
def test_remote_creation_deletion_and_wrong_source_are_rejected(
    tmp_path: Path, observations: Observations, updates: str
) -> None:
    report = completion.inspect_git_boundary(
        tmp_path,
        operation="pre_push",
        task_scope="TEST_ONLY Git authorization preparation",
    )
    completion.validate_push_updates(report, updates, "upstream", ENDPOINT)
    assert "GIT_COMPLETION_PUSH_UPDATE_PROHIBITED" in report["blockers"]


@pytest.mark.parametrize("endpoint", [ENDPOINT, ENDPOINT.removesuffix(".git")])
def test_main_sync_update_retains_independent_authorization(
    tmp_path: Path, observations: Observations, endpoint: str
) -> None:
    report = completion.inspect_git_boundary(
        tmp_path,
        operation="pre_push",
        task_scope="TEST_ONLY Git authorization preparation",
    )
    completion.validate_push_updates(
        report, f"refs/heads/main {SHA} refs/heads/main {OTHER}\n", "upstream", endpoint
    )
    assert report["status"] == "PASS"
    assert (
        report["authorization"] == "INDEPENDENT_USER_AND_GOVERNANCE_CONTROLS_REQUIRED"
    )


def test_normative_owner_and_adapter_references_are_consistent() -> None:
    root = Path(__file__).resolve().parents[1]
    core_path = "docs/governance/framework_core_vnext_governance.md"
    core = (root / core_path).read_text(encoding="utf-8")
    assert "authority_layer: L1_CORE_CONSTITUTION" in core
    rule = core.split("### 3.2 Repository Completion Invariant", 1)[1].split(
        "## 4.", 1
    )[0]
    for required in (
        "AI4B-GOV-GIT-001",
        "VERIFIED_BASELINE",
        "CHANGE_IN_PROGRESS",
        "No additional branch",
        "cached evidence",
        "Missing or inaccessible",
        "explicitly owner-authorized canonical amendment",
    ):
        assert required in rule
    assert "Authorized temporary branches" not in rule
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
        assert "Exactly one registered worktree" not in adapter


def test_document_review_cli_defaults_do_not_activate_new_options() -> None:
    from ai4binance.governance import repository_validator

    parsed = repository_validator.build_parser().parse_args(
        ["--document-lock-review-context", "runtime/TEST_ONLY_context.json"]
    )
    assert parsed.git_operation is None
    assert parsed.git_task_scope == ""
    assert parsed.git_synchronization_sequence is False


def test_caller_cannot_replace_the_approved_policy(
    tmp_path: Path, observations: Observations
) -> None:
    untrusted_request: dict[str, Any] = {
        "policy": completion.GitPolicy(tmp_path / "TEST_ONLY_alternate", ENDPOINT)
    }
    with pytest.raises(TypeError):
        completion.inspect_git_boundary(tmp_path, **untrusted_request)


def test_invalid_fabric_cannot_enable_git_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real policy reader must honor the canonical schema veto."""
    from ai4binance.governance import governance_enforcement_fabric as fabric

    root = Path(__file__).resolve().parents[1]
    for relative in (fabric.FABRIC_PATH, fabric.SCHEMA_PATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / relative).read_bytes())
    config = tmp_path / fabric.FABRIC_PATH
    raw = config.read_text(encoding="utf-8")
    assert 'projection_role: "ENFORCEMENT_PROJECTION"\n  source_of_truth: false' in raw
    config.write_text(
        raw.replace(
            'projection_role: "ENFORCEMENT_PROJECTION"\n  source_of_truth: false',
            'projection_role: "ENFORCEMENT_PROJECTION"\n  source_of_truth: true',
        ),
        encoding="utf-8",
    )

    def prohibited_query(_root: Path, *_arguments: str) -> str:
        raise AssertionError("TEST_ONLY invalid authority must deny before Git access")

    monkeypatch.setattr(completion, "_git", prohibited_query)
    report = completion.inspect_git_boundary(
        tmp_path, operation="preflight", task_scope="TEST_ONLY invalid projection"
    )
    assert report["blockers"] == ["GIT_COMPLETION_AUTHORITY_UNAVAILABLE"]
    assert report["baseline_verified"] is False

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.script_subprocess, pytest.mark.slow]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_REPOSITORY_BOOTSTRAP_PATHS = (
    "scripts/git-hooks/pre-commit",
    "scripts/git-hooks/pre-push",
    "scripts/git_write_authorization.ps1",
    "scripts/initialize_runtime_environment.ps1",
    "scripts/check_quality_gate_git_write_guard.ps1",
    "scripts/configure_git_security.ps1",
    "tools/gitleaks/v8.30.1/gitleaks.exe",
    ".venv/Scripts/python.exe",
    ".venv/pyvenv.cfg",
    "src/ai4binance/__init__.py",
    "pyproject.toml",
)


def _read(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def _required_executable(*names: str) -> str:
    executable = next(
        (shutil.which(name) for name in names if shutil.which(name)), None
    )
    assert executable is not None, f"Required executable is unavailable: {names}"
    return executable


def _run_git_authorization(
    repository: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    powershell = _required_executable("powershell.exe", "powershell", "pwsh")
    helper = REPOSITORY_ROOT / "scripts" / "git_write_authorization.ps1"
    return subprocess.run(  # noqa: S603
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            *arguments,
            "-RepositoryRoot",
            str(repository),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _output_value(output: str, name: str) -> str:
    prefix = f"{name}="
    values = [
        line[len(prefix) :] for line in output.splitlines() if line.startswith(prefix)
    ]
    assert len(values) == 1, output
    return values[0]


def _initialize_git_repository(repository: Path) -> str:
    git = _required_executable("git")
    repository.mkdir()
    subprocess.run(  # noqa: S603
        [git, "init", "--quiet", "--initial-branch=main", str(repository)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "config", "user.name", "Test Human"],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [
            git,
            "-C",
            str(repository),
            "config",
            "core.hooksPath",
            "scripts/git-hooks",
        ],
        check=True,
    )
    tracked = repository / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "add", "tracked.txt"],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [
            git,
            "-C",
            str(repository),
            "-c",
            "core.hooksPath=NUL",
            "commit",
            "--quiet",
            "-m",
            "baseline",
        ],
        check=True,
    )
    return git


def _install_test_hooks(repository: Path) -> None:
    for relative_path in SYNTHETIC_REPOSITORY_BOOTSTRAP_PATHS:
        source = REPOSITORY_ROOT / relative_path
        destination = repository / relative_path
        assert source.is_file(), source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    git = _required_executable("git")
    subprocess.run(  # noqa: S603
        [
            git,
            "-C",
            str(repository),
            "config",
            "core.hooksPath",
            "scripts/git-hooks",
        ],
        check=True,
    )


def test_synthetic_repository_bootstrap_covers_dot_sourced_dependencies() -> None:
    authorization = _read("scripts/git_write_authorization.ps1")
    dot_sourced = set(
        re.findall(
            r'^\.\s+\(Join-Path \$PSScriptRoot "([^"]+)"',
            authorization,
            flags=re.MULTILINE,
        )
    )
    bootstrap_paths = {
        Path(path).as_posix() for path in SYNTHETIC_REPOSITORY_BOOTSTRAP_PATHS
    }

    assert dot_sourced == {"initialize_runtime_environment.ps1"}
    assert {
        (Path("scripts") / dependency).as_posix() for dependency in dot_sourced
    }.issubset(bootstrap_paths)


def _prepare_authorization(
    repository: Path,
    operation: str,
    *,
    channel: str = "NonInteractive",
    remote_name: str = "",
    push_updates_path: Path | None = None,
) -> tuple[Path, str]:
    arguments = [
        "-Mode",
        "Prepare",
        "-Operation",
        operation,
        "-Channel",
        channel,
    ]
    if remote_name:
        arguments.extend(["-RemoteName", remote_name])
    if push_updates_path is not None:
        arguments.extend(["-PushUpdatesPath", str(push_updates_path)])
    result = _run_git_authorization(repository, *arguments)
    assert result.returncode == 0, result.stderr
    return (
        Path(_output_value(result.stdout, "CHALLENGE_PATH")),
        _output_value(result.stdout, "APPROVAL_COMMAND"),
    )


def _approve_authorization(
    repository: Path,
    challenge_path: Path,
    approval_command: str,
) -> Path:
    result = _run_git_authorization(
        repository,
        "-Mode",
        "Approve",
        "-ChallengePath",
        str(challenge_path),
        "-ApprovalText",
        approval_command,
    )
    assert result.returncode == 0, result.stderr
    return Path(_output_value(result.stdout, "AUTHORIZATION_PATH"))


@pytest.mark.parametrize("operation", ["commit", "push"])
@pytest.mark.parametrize(
    ("response", "approved"),
    [
        ("lower", True),
        ("upper", True),
        ("mixed", True),
        ("", False),
        ("admin", False),
        ("owner", False),
        ("eof", False),
    ],
)
def test_interactive_git_approval_response(
    operation: str, response: str, approved: bool
) -> None:
    git = Path(_required_executable("git"))
    shell = shutil.which("sh") or str(git.parent.parent / "bin" / "sh.exe")
    assert Path(shell).is_file()
    hook = _read(f"scripts/git-hooks/pre-{operation}")
    # Execute the actual response parser with stdin standing in for the terminal.
    parser = hook.split('    explicit_approval=""', 1)[1].split(
        "\n\n    if ! powershell.exe", 1
    )[0]
    parser = 'explicit_approval=""' + parser.replace("< /dev/tty", "")
    values = {
        "lower": operation,
        "upper": operation.upper(),
        "mixed": operation.title(),
    }
    answer = values.get(response, response)
    result = subprocess.run(  # noqa: S603
        [shell, "-c", parser],
        input=b"" if response == "eof" else (answer + "\n").encode("ascii"),
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == (0 if approved else 1)
    if not approved:
        assert (
            f"EXPLICIT_GIT_{operation.upper()}_APPROVAL_DECLINED"
            in result.stderr.decode()
        )


def test_security_extra_pins_pip_audit() -> None:
    config = tomllib.loads(_read("pyproject.toml"))

    security = config["project"]["optional-dependencies"]["security"]

    assert security == ["pip-audit>=2.10,<3", "truststore>=0.10,<1"]


def test_gitleaks_installer_is_local_pinned_and_checksum_verified() -> None:
    installer = _read("scripts/install_security_tooling.ps1")

    assert '$gitleaksVersion = "8.30.1"' in installer
    assert (
        "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e" in installer
    )
    assert "Get-FileHash" in installer
    assert "tools\\gitleaks" in installer
    assert "GITLEAKS_VERSION_MISMATCH" in installer


def test_security_audit_is_redacted_report_only_and_fail_closed() -> None:
    audit = _read("scripts/security_tooling_audit.ps1")

    assert '[ValidateSet("pypi", "osv", "esms")]' in audit
    assert "truststore.inject_into_ssl()" in audit
    assert "--local --skip-editable --format json" in audit
    assert "--vulnerability-service $VulnerabilityService" in audit
    assert "--timeout $PipAuditTimeoutSeconds" in audit
    assert '$ErrorActionPreference = "Continue"' in audit
    assert "$pipAuditExitCode = $LASTEXITCODE" in audit
    assert "--redact=100" in audit
    assert "--fix" not in audit
    assert "auto_fix_allowed = $false" in audit
    assert "execution_allowed = $false" in audit
    assert 'live_eligibility_status = "LIVE_ORDER_BLOCKED"' in audit
    assert "DEPENDENCY_AUDIT_FAILED" in audit
    assert "DEPENDENCY_AUDIT_REPORT_INVALID" in audit
    assert "SECRET_SCAN_FAILED" in audit
    assert "SECRET_SCAN_REPORT_INVALID" in audit
    assert "vulnerability_service = $VulnerabilityService" in audit
    assert "finding_count = $pipAuditFindingCount" in audit
    assert "finding_count = $gitleaksFindingCount" in audit
    assert "exit 1" in audit


def test_gitleaks_pre_commit_hook_uses_local_staged_scan() -> None:
    hook = _read("scripts/git-hooks/pre-commit")

    assert "check_quality_gate_git_write_guard.ps1" in hook
    assert "ai4binance-quality-gate-write-lease.json" in hook
    assert "QUALITY_GATE_GIT_WRITE_GUARD_MISSING" in hook
    assert "git_write_authorization.ps1" in hook
    assert "LEGACY_GIT_COMMIT_APPROVAL_TOKEN_REJECTED" in hook
    assert "USER_AUTHORIZED_SINGLE_COMMAND" not in hook
    assert "AI4BINANCE_GIT_WRITE_AUTHORIZATION_PATH" in hook
    assert "EXPLICIT_GIT_COMMIT_APPROVAL_REQUIRED" in hook
    assert "Type COMMIT to authorize this exact staged tree" in hook
    assert "EXPLICIT_GIT_COMMIT_APPROVAL_DECLINED" in hook
    assert "[ -t 1 ]" in hook
    assert "/dev/tty" in hook
    assert "Patch or implementation approval does not authorize a Git commit." in hook
    assert "tools/gitleaks/v8.30.1/gitleaks.exe" in hook
    assert "--staged" in hook
    assert "--redact=100" in hook
    assert "--no-banner" in hook
    assert "--no-color" in hook
    assert "--exit-code 1" in hook
    assert "--fix" not in hook
    assert "GITLEAKS_NOT_INSTALLED" in hook
    assert "SECRET_SCAN_FAILED_OR_FINDINGS_REQUIRE_REVIEW" in hook
    assert "RESEARCH_ONLY" in hook
    assert "LIVE_ORDER_BLOCKED" in hook


def test_pre_push_hook_blocks_writes_during_quality_gate() -> None:
    hook = _read("scripts/git-hooks/pre-push")

    assert "check_quality_gate_git_write_guard.ps1" in hook
    assert "ai4binance-quality-gate-write-lease.json" in hook
    assert "QUALITY_GATE_GIT_WRITE_GUARD_MISSING" in hook
    assert "git_write_authorization.ps1" in hook
    assert "LEGACY_GIT_PUSH_APPROVAL_TOKEN_REJECTED" in hook
    assert "USER_AUTHORIZED_SINGLE_COMMAND" not in hook
    assert "AI4BINANCE_GIT_WRITE_AUTHORIZATION_PATH" in hook
    assert "EXPLICIT_GIT_PUSH_APPROVAL_REQUIRED" in hook
    assert "Type PUSH to authorize this exact ref update set" in hook
    assert "EXPLICIT_GIT_PUSH_APPROVAL_DECLINED" in hook
    assert "[ -t 1 ]" in hook
    assert "/dev/tty" in hook
    assert "Commit or implementation approval does not authorize a Git push." in hook
    assert "powershell.exe" in hook
    assert 'cat > "$push_updates_path"' in hook
    assert "-PushUpdatesPath" in hook
    assert "RESEARCH_ONLY" in hook
    assert "LIVE_ORDER_BLOCKED" in hook


def test_quality_gate_git_write_guard_is_process_bound_and_fail_closed() -> None:
    guard = _read("scripts/check_quality_gate_git_write_guard.ps1")

    assert "ai4binance-quality-gate-write-lease.json" in guard
    assert 'status -ne "QUALITY_GATE_ACTIVE"' in guard
    assert "process_id" in guard
    assert "process_started_at_utc" in guard
    assert "Get-Process" in guard
    assert "QUALITY_GATE_GIT_WRITE_BLOCKED" in guard
    assert "QUALITY_GATE_GIT_WRITE_LEASE_INVALID" in guard
    assert "QUALITY_GATE_GIT_WRITE_GUARD_ERROR" in guard
    assert "RESEARCH_ONLY" in guard
    assert "LIVE_ORDER_BLOCKED" in guard


def test_quality_gate_git_write_guard_blocks_active_and_ignores_stale_lease(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    git = _required_executable("git")
    powershell = _required_executable("powershell.exe", "powershell", "pwsh")
    subprocess.run(  # noqa: S603
        [git, "init", "--quiet", str(repository)],
        check=True,
        capture_output=True,
        text=True,
    )
    guard = REPOSITORY_ROOT / "scripts" / "check_quality_gate_git_write_guard.ps1"
    guard_command = [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(guard),
        "-RepositoryRoot",
        str(repository),
    ]
    no_lease = subprocess.run(  # noqa: S603
        guard_command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert no_lease.returncode == 0

    process_started_at = subprocess.run(  # noqa: S603
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                f"(Get-Process -Id {os.getpid()}).StartTime."
                "ToUniversalTime().ToString('o')"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    lease_path = repository / ".git" / "ai4binance-quality-gate-write-lease.json"
    lease = {
        "schema_version": 1,
        "status": "QUALITY_GATE_ACTIVE",
        "run_id": "TEST_ACTIVE_LEASE",
        "process_id": os.getpid(),
        "process_started_at_utc": process_started_at,
    }
    lease_path.write_text(json.dumps(lease), encoding="utf-8")

    active = subprocess.run(  # noqa: S603
        guard_command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert active.returncode == 1
    assert "QUALITY_GATE_GIT_WRITE_BLOCKED: active run TEST_ACTIVE_LEASE" in (
        active.stderr
    )
    assert "RESEARCH_ONLY" in active.stderr
    assert "LIVE_ORDER_BLOCKED" in active.stderr

    lease["process_started_at_utc"] = "2000-01-01T00:00:00.0000000Z"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    stale = subprocess.run(  # noqa: S603
        guard_command,
        check=False,
        capture_output=True,
        text=True,
    )
    assert stale.returncode == 0


def test_git_write_authorization_is_exact_and_single_use(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    git = _initialize_git_repository(repository)
    tracked = repository / "tracked.txt"
    tracked.write_text("authorized change\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "add", "tracked.txt"],
        check=True,
    )

    challenge_path, approval_command = _prepare_authorization(repository, "Commit")
    rejected = _run_git_authorization(
        repository,
        "-Mode",
        "Approve",
        "-ChallengePath",
        str(challenge_path),
        "-ApprovalText",
        approval_command + "-wrong",
    )
    assert rejected.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_EXACT_APPROVAL_REQUIRED" in rejected.stderr
    assert challenge_path.is_file()

    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )
    consumed = _run_git_authorization(
        repository,
        "-Mode",
        "Consume",
        "-Operation",
        "Commit",
        "-Channel",
        "NonInteractive",
        "-ChallengePath",
        str(authorization_path),
    )
    assert consumed.returncode == 0, consumed.stderr
    assert "GIT_WRITE_AUTHORIZATION_CONSUMED" in consumed.stdout
    assert not authorization_path.exists()

    replay = _run_git_authorization(
        repository,
        "-Mode",
        "Consume",
        "-Operation",
        "Commit",
        "-Channel",
        "NonInteractive",
        "-ChallengePath",
        str(authorization_path),
    )
    assert replay.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_ERROR" in replay.stderr
    assert "RESEARCH_ONLY" in replay.stderr
    assert "LIVE_ORDER_BLOCKED" in replay.stderr


def test_git_write_authorization_rejects_subject_drift(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    git = _initialize_git_repository(repository)
    tracked = repository / "tracked.txt"
    tracked.write_text("first staged tree\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "add", "tracked.txt"],
        check=True,
    )
    challenge_path, approval_command = _prepare_authorization(repository, "Commit")
    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )

    tracked.write_text("different staged tree\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "add", "tracked.txt"],
        check=True,
    )
    mismatch = _run_git_authorization(
        repository,
        "-Mode",
        "Consume",
        "-Operation",
        "Commit",
        "-Channel",
        "NonInteractive",
        "-ChallengePath",
        str(authorization_path),
    )
    assert mismatch.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_SUBJECT_MISMATCH" in mismatch.stderr
    assert authorization_path.is_file()


def test_git_write_authorization_rejects_operation_and_outside_paths(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    _initialize_git_repository(repository)
    challenge_path, approval_command = _prepare_authorization(repository, "Commit")
    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )
    wrong_operation = _run_git_authorization(
        repository,
        "-Mode",
        "Consume",
        "-Operation",
        "Push",
        "-Channel",
        "NonInteractive",
        "-ChallengePath",
        str(authorization_path),
    )
    assert wrong_operation.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_OPERATION_MISMATCH" in wrong_operation.stderr
    assert authorization_path.is_file()

    outside = repository / "implementation-manifest.json"
    outside.write_text(
        json.dumps(
            {
                "manifest_kind": "BOUNDED_IMPLEMENTATION_APPROVAL",
                "manifest_status": "APPROVED",
            }
        ),
        encoding="utf-8",
    )
    rejected_manifest = _run_git_authorization(
        repository,
        "-Mode",
        "Consume",
        "-Operation",
        "Commit",
        "-Channel",
        "NonInteractive",
        "-ChallengePath",
        str(outside),
    )
    assert rejected_manifest.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_PATH_OUTSIDE_STATE_ROOT" in (
        rejected_manifest.stderr
    )
    assert "RESEARCH_ONLY" in rejected_manifest.stderr
    assert "LIVE_ORDER_BLOCKED" in rejected_manifest.stderr


def test_push_authorization_rejects_ref_update_drift(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    git = _initialize_git_repository(repository)
    subprocess.run(  # noqa: S603
        [git, "init", "--quiet", "--bare", str(remote)],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "remote", "add", "origin", str(remote)],
        check=True,
    )
    head = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    updates = tmp_path / "updates.txt"
    updates.write_text(
        f"refs/heads/main {head} refs/heads/main {'0' * 40}\n",
        encoding="utf-8",
    )
    challenge_path, approval_command = _prepare_authorization(
        repository,
        "Push",
        remote_name="origin",
        push_updates_path=updates,
    )
    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )
    updates.write_text(
        f"refs/heads/main {head} refs/heads/main {'f' * 40}\n",
        encoding="utf-8",
    )
    mismatch = _run_git_authorization(
        repository,
        "-Mode",
        "Consume",
        "-Operation",
        "Push",
        "-Channel",
        "NonInteractive",
        "-ChallengePath",
        str(authorization_path),
        "-RemoteName",
        "origin",
        "-PushUpdatesPath",
        str(updates),
    )
    assert mismatch.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_SUBJECT_MISMATCH" in mismatch.stderr
    assert authorization_path.is_file()


def test_git_write_authorization_rejects_expired_and_duplicate_json(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    _initialize_git_repository(repository)
    challenge_path, _ = _prepare_authorization(repository, "Commit")
    payload = json.loads(challenge_path.read_text(encoding="utf-8"))
    created = datetime.now(UTC) - timedelta(minutes=10)
    payload["created_at_utc"] = created.isoformat()
    payload["expires_at_utc"] = (created + timedelta(minutes=5)).isoformat()
    challenge_path.write_text(json.dumps(payload), encoding="utf-8")
    expired = _run_git_authorization(
        repository,
        "-Mode",
        "Approve",
        "-ChallengePath",
        str(challenge_path),
        "-ApprovalText",
        "APPROVE_AI4BINANCE_GIT_COMMIT invalid",
    )
    assert expired.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_EXPIRED" in expired.stderr

    duplicate_path, _ = _prepare_authorization(repository, "Commit")
    duplicate_path.write_text(
        '{"schema_version":1,"schema_version":1}\n', encoding="utf-8"
    )
    duplicate = _run_git_authorization(
        repository,
        "-Mode",
        "Approve",
        "-ChallengePath",
        str(duplicate_path),
        "-ApprovalText",
        "APPROVE_AI4BINANCE_GIT_COMMIT invalid",
    )
    assert duplicate.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_JSON_INVALID" in duplicate.stderr
    assert "RESEARCH_ONLY" in duplicate.stderr
    assert "LIVE_ORDER_BLOCKED" in duplicate.stderr

    wrong_type_repository = tmp_path / "wrong-type-repository"
    _initialize_git_repository(wrong_type_repository)
    wrong_type_path, _ = _prepare_authorization(wrong_type_repository, "Commit")
    wrong_type = json.loads(wrong_type_path.read_text(encoding="utf-8"))
    wrong_type["schema_version"] = "1"
    wrong_type_path.write_text(json.dumps(wrong_type), encoding="utf-8")
    rejected_type = _run_git_authorization(
        wrong_type_repository,
        "-Mode",
        "Approve",
        "-ChallengePath",
        str(wrong_type_path),
        "-ApprovalText",
        "APPROVE_AI4BINANCE_GIT_COMMIT invalid",
    )
    assert rejected_type.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_CHALLENGE_INVALID" in rejected_type.stderr


def test_interactive_git_authorization_rejects_placeholder_identity(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    git = _initialize_git_repository(repository)
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "config", "user.name", "Quality Gate"],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [
            git,
            "-C",
            str(repository),
            "config",
            "user.email",
            "quality@example.invalid",
        ],
        check=True,
    )
    rejected = _run_git_authorization(
        repository,
        "-Mode",
        "Prepare",
        "-Operation",
        "Commit",
        "-Channel",
        "Interactive",
    )
    assert rejected.returncode == 1
    assert "GIT_WRITE_AUTHORIZATION_PLACEHOLDER_IDENTITY_BLOCKED" in rejected.stderr

    challenge_path, command = _prepare_authorization(
        repository, "Commit", channel="NonInteractive"
    )
    assert challenge_path.is_file()
    assert command.startswith("APPROVE_AI4BINANCE_GIT_COMMIT ")


def test_pre_commit_hook_rejects_legacy_token_and_consumes_exact_authorization(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    git = _initialize_git_repository(repository)
    _install_test_hooks(repository)
    tracked = repository / "tracked.txt"
    tracked.write_text("authorized hook change\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "add", "tracked.txt"],
        check=True,
    )
    baseline_head = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    legacy_environment = os.environ.copy()
    legacy_environment["AI4BINANCE_EXPLICIT_GIT_COMMIT_APPROVAL"] = (
        "USER_AUTHORIZED_SINGLE_COMMAND"
    )
    legacy = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "commit", "-m", "legacy denied"],
        check=False,
        capture_output=True,
        text=True,
        env=legacy_environment,
        timeout=30,
    )
    assert legacy.returncode != 0
    assert "LEGACY_GIT_COMMIT_APPROVAL_TOKEN_REJECTED" in legacy.stderr

    pending = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "commit", "-m", "approval required"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert pending.returncode != 0
    assert "EXPLICIT_GIT_COMMIT_APPROVAL_REQUIRED" in pending.stderr
    challenge_path = Path(_output_value(pending.stderr, "CHALLENGE_PATH"))
    approval_command = _output_value(pending.stderr, "APPROVAL_COMMAND")
    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )

    authorized_environment = os.environ.copy()
    authorized_environment["AI4BINANCE_GIT_WRITE_AUTHORIZATION_PATH"] = str(
        authorization_path
    )
    authorized = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "commit", "-m", "exactly authorized"],
        check=False,
        capture_output=True,
        text=True,
        env=authorized_environment,
        timeout=60,
    )
    assert authorized.returncode == 0, authorized.stderr
    assert "GIT_WRITE_AUTHORIZATION_CONSUMED" in (authorized.stdout + authorized.stderr)
    assert not authorization_path.exists()
    current_head = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert current_head != baseline_head


def test_active_quality_gate_lease_precedes_exact_commit_authorization(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    git = _initialize_git_repository(repository)
    _install_test_hooks(repository)
    tracked = repository / "tracked.txt"
    tracked.write_text("blocked during quality\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "add", "tracked.txt"],
        check=True,
    )
    challenge_path, approval_command = _prepare_authorization(repository, "Commit")
    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )
    powershell = _required_executable("powershell.exe", "powershell", "pwsh")
    process_started_at = subprocess.run(  # noqa: S603
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                f"(Get-Process -Id {os.getpid()}).StartTime."
                "ToUniversalTime().ToString('o')"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    lease = {
        "schema_version": 1,
        "status": "QUALITY_GATE_ACTIVE",
        "run_id": "TEST_EXACT_AUTHORIZATION_VETO",
        "process_id": os.getpid(),
        "process_started_at_utc": process_started_at,
    }
    (repository / ".git" / "ai4binance-quality-gate-write-lease.json").write_text(
        json.dumps(lease), encoding="utf-8"
    )
    environment = os.environ.copy()
    environment["AI4BINANCE_GIT_WRITE_AUTHORIZATION_PATH"] = str(authorization_path)
    blocked = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "commit", "-m", "must remain blocked"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert blocked.returncode != 0
    assert "QUALITY_GATE_GIT_WRITE_BLOCKED" in blocked.stderr
    assert authorization_path.is_file()


def test_secret_scan_failure_consumes_exact_commit_authorization(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    git = _initialize_git_repository(repository)
    _install_test_hooks(repository)
    tracked = repository / "tracked.txt"
    tracked.write_text("scan must fail\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "add", "tracked.txt"],
        check=True,
    )
    challenge_path, approval_command = _prepare_authorization(repository, "Commit")
    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )
    shutil.copy2(
        Path(git),
        repository / "tools" / "gitleaks" / "v8.30.1" / "gitleaks.exe",
    )
    environment = os.environ.copy()
    environment["AI4BINANCE_GIT_WRITE_AUTHORIZATION_PATH"] = str(authorization_path)
    rejected = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "commit", "-m", "scan failure"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    assert rejected.returncode != 0
    assert "SECRET_SCAN_FAILED_OR_FINDINGS_REQUIRE_REVIEW" in rejected.stderr
    assert not authorization_path.exists()


def test_pre_push_hook_consumes_exact_ref_bound_authorization(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    git = _initialize_git_repository(repository)
    subprocess.run(  # noqa: S603
        [git, "init", "--quiet", "--bare", str(remote)],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "remote", "add", "origin", str(remote)],
        check=True,
    )
    _install_test_hooks(repository)

    legacy_environment = os.environ.copy()
    legacy_environment["AI4BINANCE_EXPLICIT_GIT_PUSH_APPROVAL"] = (
        "USER_AUTHORIZED_SINGLE_COMMAND"
    )
    legacy = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "push", "origin", "main"],
        check=False,
        capture_output=True,
        text=True,
        env=legacy_environment,
        timeout=30,
    )
    assert legacy.returncode != 0
    assert "LEGACY_GIT_PUSH_APPROVAL_TOKEN_REJECTED" in legacy.stderr

    pending = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "push", "origin", "main"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert pending.returncode != 0
    assert "EXPLICIT_GIT_PUSH_APPROVAL_REQUIRED" in pending.stderr
    challenge_path = Path(_output_value(pending.stderr, "CHALLENGE_PATH"))
    approval_command = _output_value(pending.stderr, "APPROVAL_COMMAND")
    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )

    environment = os.environ.copy()
    environment["AI4BINANCE_GIT_WRITE_AUTHORIZATION_PATH"] = str(authorization_path)
    pushed = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "push", "origin", "main"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    assert pushed.returncode == 0, pushed.stderr
    assert not authorization_path.exists()
    remote_head = subprocess.run(  # noqa: S603
        [git, "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    local_head = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert remote_head == local_head
    audit_files = list(
        (repository / ".git" / "ai4binance-git-write-authorizations" / "consumed").glob(
            "*.audit.json"
        )
    )
    assert len(audit_files) == 1
    audit_text = audit_files[0].read_text(encoding="utf-8")
    assert str(remote) not in audit_text
    assert "test@example.invalid" not in audit_text
    audit = json.loads(audit_text)
    assert audit["execution_allowed"] is False
    assert audit["promotion_status"] == "RESEARCH_ONLY"
    assert audit["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_pre_push_hook_allows_noop_push_without_authorization(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    git = _initialize_git_repository(repository)
    subprocess.run(  # noqa: S603
        [git, "init", "--quiet", "--bare", str(remote)],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "remote", "add", "origin", str(remote)],
        check=True,
    )
    _install_test_hooks(repository)

    subprocess.run(  # noqa: S603
        [
            git,
            "-C",
            str(repository),
            "-c",
            "core.hooksPath=NUL",
            "push",
            "origin",
            "main",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    noop = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "push", "origin", "main"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert noop.returncode == 0, noop.stderr
    assert "EXPLICIT_GIT_PUSH_APPROVAL_REQUIRED" not in noop.stderr


def test_git_security_configuration_is_local_only() -> None:
    configurer = _read("scripts/configure_git_security.ps1")

    assert 'git config --local "core.hooksPath" "scripts/git-hooks"' in configurer
    assert 'git config --local "core.excludesFile" ".git/info/exclude"' in configurer
    assert "GIT_SECURITY_PRE_COMMIT_HOOK_MISSING" in configurer
    assert "GIT_SECURITY_PRE_PUSH_HOOK_MISSING" in configurer
    assert "GIT_SECURITY_QUALITY_GATE_GUARD_MISSING" in configurer
    assert "GIT_SECURITY_WRITE_AUTHORIZATION_HELPER_MISSING" in configurer
    assert "GIT_SECURITY_PLACEHOLDER_IDENTITY_BLOCKED" in configurer
    assert "GIT_WRITE_AUTHORIZATION=EXACT_SUBJECT_BOUND_SINGLE_USE" in configurer
    assert "--global" not in configurer
    assert "GIT_SECURITY_CONFIGURED" in configurer
    assert "RESEARCH_ONLY" in configurer
    assert "LIVE_ORDER_BLOCKED" in configurer


def test_git_security_configuration_rejects_placeholder_identity(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    git = _initialize_git_repository(repository)
    _install_test_hooks(repository)
    powershell = _required_executable("powershell.exe", "powershell", "pwsh")
    configurer = repository / "scripts" / "configure_git_security.ps1"
    configured = subprocess.run(  # noqa: S603
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(configurer),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert configured.returncode == 0, configured.stderr
    assert "GIT_WRITE_AUTHORIZATION=EXACT_SUBJECT_BOUND_SINGLE_USE" in (
        configured.stdout
    )

    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "config", "user.name", "Quality Gate"],
        check=True,
    )
    blocked = subprocess.run(  # noqa: S603
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(configurer),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert blocked.returncode != 0
    assert "GIT_SECURITY_PLACEHOLDER_IDENTITY_BLOCKED" in (
        blocked.stdout + blocked.stderr
    )


def test_security_tooling_workflow_runs_report_only_scan() -> None:
    workflow = _read(".github/workflows/security_tooling.yml")

    assert "fetch-depth: 0" in workflow
    assert "uv python install 3.14.7" in workflow
    assert "uv venv --python 3.14.7 .venv" in workflow
    assert "python -m venv .venv" not in workflow
    assert ".\\scripts\\install_security_tooling.ps1" in workflow
    assert ".\\scripts\\security_tooling_audit.ps1" in workflow
    assert "-VulnerabilityService osv" in workflow
    assert "runtime/artifacts/assurance/security_tooling/" in workflow


def test_security_tooling_paths_are_local_only_and_generated() -> None:
    gitignore = _read(".gitignore")

    assert "tools/gitleaks/" in gitignore
    assert "runtime/artifacts/assurance/security_tooling/" in gitignore


def test_core_instructions_preserve_security_authority_boundaries() -> None:
    instructions = _read("docs/governance/instruction_core_custom_instructions.md")

    assert "Approved Local Security Tooling" in instructions
    assert "auto-fix or silently upgrade dependencies" in instructions
    assert "Security scanners are advisory and report-only" in instructions
    assert "RESEARCH_ONLY" in instructions
    assert "LIVE_ORDER_BLOCKED" in instructions

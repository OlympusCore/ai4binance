from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import warnings
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
    "src/ai4binance/governance/git_write_contract.py",
    "schemas/governance/git_write_authorization.schema.json",
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
    powershell: str | None = None,
) -> subprocess.CompletedProcess[str]:
    powershell = powershell or _required_executable(
        "powershell.exe", "powershell", "pwsh"
    )
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
    _stage_fixture_baseline(repository, git)
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


def _stage_fixture_baseline(repository: Path, git: str) -> None:
    """TEST_ONLY bounded recovery for the observed Windows loose-object denial."""
    assert repository.resolve() != REPOSITORY_ROOT
    assert (repository / ".git").is_dir()
    command = [git, "-C", str(repository), "add", "tracked.txt"]
    delays = (0.01, 0.02, 0.04, 0.08, 0.16, 0.25, 0.25)
    errors: list[str] = []
    for attempt in range(len(delays) + 1):
        result = subprocess.run(  # noqa: S603
            command, check=False, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            if errors:
                warnings.warn(
                    "TEST_ONLY_GIT_OBJECT_WRITE_RECOVERED after "
                    f"{len(errors)} denied attempts:\n" + "\n".join(errors),
                    RuntimeWarning,
                    stacklevel=2,
                )
            return
        errors.append(result.stderr)
        object_denied = re.search(
            r"(?m)^error: unable to write file '?\.git/objects/"
            r"[0-9a-f]{2}/[0-9a-f]{38}'?: Permission denied\r?$",
            result.stderr,
        )
        if (
            sys.platform != "win32"
            or result.returncode != 128
            or object_denied is None
            or attempt == len(delays)
        ):
            failure = subprocess.CalledProcessError(
                result.returncode, command, result.stdout, result.stderr
            )
            failure.add_note(
                "TEST_ONLY_GIT_BASELINE_FAILED; captured attempt stderr:\n"
                + "\n".join(errors)
            )
            raise failure
        time.sleep(delays[attempt])


@pytest.fixture
def empty_git_fixture(tmp_path: Path) -> tuple[Path, str]:
    """Create a TEST_ONLY repository without changing the real Git index."""
    repository = tmp_path / "repository"
    repository.mkdir()
    git = _required_executable("git")
    subprocess.run(  # noqa: S603
        [git, "init", "--quiet", str(repository)],
        check=True,
        capture_output=True,
    )
    (repository / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    return repository, git


def test_fixture_baseline_recovers_transient_object_write_denial(
    empty_git_fixture: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """TEST_ONLY injected denial followed by a real successful Git add."""
    repository, git = empty_git_fixture
    original_run = subprocess.run
    attempts = 0
    delays: list[float] = []
    stderr = "error: unable to write file .git/objects/18/" + "a" * 38
    stderr += ": Permission denied\n"

    def flaky_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        assert command == [git, "-C", str(repository), "add", "tracked.txt"]
        if attempts < 3:
            return subprocess.CompletedProcess(command, 128, "", stderr)
        return original_run(command, check=False, capture_output=True, text=True)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", flaky_run)
    monkeypatch.setattr(time, "sleep", delays.append)
    with pytest.warns(RuntimeWarning, match="TEST_ONLY_GIT_OBJECT_WRITE_RECOVERED"):
        _stage_fixture_baseline(repository, git)
    assert attempts == 3
    assert delays == [0.01, 0.02]
    staged = original_run(
        [git, "-C", str(repository), "show", ":tracked.txt"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert staged.stdout == "baseline\n"


@pytest.mark.parametrize(
    ("platform", "exit_code", "stderr", "expected_attempts"),
    [
        (
            "win32",
            128,
            "error: unable to write file .git/objects/18/"
            + "a" * 38
            + ": Permission denied\n",
            8,
        ),
        (
            "linux",
            128,
            "error: unable to write file .git/objects/18/"
            + "a" * 38
            + ": Permission denied\n",
            1,
        ),
        (
            "win32",
            128,
            "fatal: Unable to create '.git/index.lock': Permission denied",
            1,
        ),
        ("win32", 128, "fatal: disk full", 1),
        (
            "win32",
            1,
            "error: unable to write file .git/objects/18/"
            + "a" * 38
            + ": Permission denied\n",
            1,
        ),
    ],
)
def test_fixture_baseline_preserves_persistent_and_unrelated_failures(
    empty_git_fixture: tuple[Path, str],
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    exit_code: int,
    stderr: str,
    expected_attempts: int,
) -> None:
    """TEST_ONLY injected failures retain the veto and original diagnostics."""
    repository, git = empty_git_fixture
    attempts = 0
    delays: list[float] = []

    def denied_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        return subprocess.CompletedProcess(command, exit_code, "", stderr)

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(subprocess, "run", denied_run)
    monkeypatch.setattr(time, "sleep", delays.append)
    with pytest.raises(subprocess.CalledProcessError) as rejected:
        _stage_fixture_baseline(repository, git)
    assert rejected.value.returncode == exit_code
    assert rejected.value.stderr == stderr
    assert stderr in rejected.value.__notes__[0]
    assert attempts == expected_attempts
    assert len(delays) == expected_attempts - 1


def test_fixture_baseline_rejects_real_repository() -> None:
    with pytest.raises(AssertionError):
        _stage_fixture_baseline(REPOSITORY_ROOT, _required_executable("git"))


def _install_test_hooks(repository: Path) -> None:
    for relative_path in SYNTHETIC_REPOSITORY_BOOTSTRAP_PATHS:
        source = REPOSITORY_ROOT / relative_path
        destination = repository / relative_path
        assert source.is_file(), source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    _install_test_git_boundary(repository)
    # Test-only venv reuses the already installed dependencies without installation.
    site_packages = repository / ".venv/Lib/site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    (site_packages / "test_dependencies.pth").write_text(
        str(REPOSITORY_ROOT / ".venv/Lib/site-packages") + "\n", encoding="utf-8"
    )
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


def _install_test_git_boundary(repository: Path) -> None:
    """Install a TEST_ONLY delegation double, never canonical Git authority."""
    package = repository / "src/ai4binance/ops/quality_gate"
    package.mkdir(parents=True, exist_ok=True)
    for path in (package.parent / "__init__.py", package / "__init__.py"):
        path.write_text('"""TEST_ONLY hook integration fixture."""\n', encoding="utf-8")
    (package / "repository_completion.py").write_text(
        '''"""TEST_ONLY boundary double; real checker is tested independently."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repository-root", type=Path, required=True)
parser.add_argument("--operation", choices=("pre_commit", "pre_push"), required=True)
parser.add_argument("--task-scope", required=True)
parser.add_argument("--push-updates-path")
parser.add_argument("--remote-name")
parser.add_argument("--remote-url")
args = parser.parse_args()
assert args.task_scope.strip()
common = args.repository_root / ".git"
calls = common / "test_only_git_boundary_calls.jsonl"
with calls.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(vars(args), default=str) + "\\n")
denied = (common / "test_only_git_boundary_deny").exists()
print(json.dumps({
    "scope": "TEST_ONLY_DELEGATION",
    "status": "BLOCKED" if denied else "PASS",
    "baseline_verified": False,
    "execution_allowed": False,
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}))
raise SystemExit(1 if denied else 0)
''',
        encoding="utf-8",
    )


@pytest.mark.parametrize("operation", ["Commit", "Push"])
def test_test_only_canonical_veto_preserves_exact_git_authorization(
    tmp_path: Path, operation: str
) -> None:
    repository = tmp_path / "repository"
    git = _initialize_git_repository(repository)
    _install_test_hooks(repository)
    remote_name = ""
    updates: Path | None = None
    if operation == "Commit":
        (repository / "tracked.txt").write_text("TEST_ONLY changed\n", encoding="utf-8")
        subprocess.run(  # noqa: S603
            [git, "-C", str(repository), "add", "tracked.txt"], check=True
        )
        command = [git, "-C", str(repository), "commit", "-m", "TEST_ONLY veto"]
    else:
        remote = tmp_path / "remote.git"
        subprocess.run([git, "init", "--quiet", "--bare", str(remote)], check=True)  # noqa: S603
        remote_name = "origin"
        subprocess.run(  # noqa: S603
            [git, "-C", str(repository), "remote", "add", remote_name, str(remote)],
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
            f"refs/heads/main {head} refs/heads/main {'0' * 40}\n", encoding="utf-8"
        )
        command = [git, "-C", str(repository), "push", remote_name, "main"]
    challenge, approval = _prepare_authorization(
        repository, operation, remote_name=remote_name, push_updates_path=updates
    )
    authorization = _approve_authorization(repository, challenge, approval)
    (repository / ".git/test_only_git_boundary_deny").write_text(
        "TEST_ONLY explicit boundary veto\n", encoding="utf-8"
    )
    rejected = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            "AI4BINANCE_GIT_WRITE_AUTHORIZATION_PATH": str(authorization),
        },
    )
    assert rejected.returncode != 0
    assert "TEST_ONLY_DELEGATION" in rejected.stdout + rejected.stderr
    assert "GIT_WRITE_AUTHORIZATION_CONSUMED" not in rejected.stdout + rejected.stderr
    assert authorization.is_file()
    calls = (
        (repository / ".git/test_only_git_boundary_calls.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(calls) == 1
    assert json.loads(calls[0])["operation"] == f"pre_{operation.lower()}"


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


@pytest.mark.parametrize(
    ("approval_shell", "consumer_shell"),
    [("pwsh", "powershell.exe"), ("powershell.exe", "pwsh"), ("pwsh", "pwsh")],
)
def test_git_write_authorization_preserves_timestamps_across_shells(
    tmp_path: Path, approval_shell: str, consumer_shell: str
) -> None:
    repository = tmp_path / "repository"
    _initialize_git_repository(repository)
    challenge_path, approval_command = _prepare_authorization(repository, "Commit")
    challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
    approved = _run_git_authorization(
        repository,
        "-Mode",
        "Approve",
        "-ChallengePath",
        str(challenge_path),
        "-ApprovalText",
        approval_command,
        powershell=_required_executable(approval_shell),
    )
    assert approved.returncode == 0, approved.stderr
    authorization_path = Path(_output_value(approved.stdout, "AUTHORIZATION_PATH"))
    approval = json.loads(
        Path(str(authorization_path) + ".approval.json").read_text(encoding="utf-8")
    )
    assert approval["expires_at_utc"] == challenge["expires_at_utc"]
    assert json.loads(authorization_path.read_text(encoding="utf-8")) == challenge
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
        powershell=_required_executable(consumer_shell),
    )
    assert consumed.returncode == 0, consumed.stderr
    assert "GIT_WRITE_AUTHORIZATION_CONSUMED" in consumed.stdout
    assert not authorization_path.exists()


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


def test_pre_push_hook_blocks_remote_ref_drift_before_consuming_authorization(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    other_clone = tmp_path / "other-clone"
    git = _initialize_git_repository(repository)
    subprocess.run(  # noqa: S603
        [git, "init", "--quiet", "--bare", str(remote)],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "remote", "add", "origin", str(remote)],
        check=True,
    )
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
    )
    _install_test_hooks(repository)

    local_file = repository / "tracked.txt"
    local_file.write_text("local change\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "add", "tracked.txt"], check=True
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
            "local change",
        ],
        check=True,
    )
    local_head = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    expected_remote_head = subprocess.run(  # noqa: S603
        [git, "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    subprocess.run(  # noqa: S603
        [git, "clone", "--quiet", "--branch", "main", str(remote), str(other_clone)],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(other_clone), "config", "user.name", "Other Human"],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(other_clone), "config", "user.email", "other@example.invalid"],
        check=True,
    )
    (other_clone / "remote.txt").write_text("remote change\n", encoding="utf-8")
    subprocess.run(  # noqa: S603
        [git, "-C", str(other_clone), "add", "remote.txt"], check=True
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(other_clone), "commit", "--quiet", "-m", "remote change"],
        check=True,
    )
    subprocess.run(  # noqa: S603
        [git, "-C", str(other_clone), "push", "origin", "main"],
        check=True,
        capture_output=True,
        text=True,
    )

    updates_path = tmp_path / "push-updates.txt"
    updates_path.write_text(
        f"refs/heads/main {local_head} refs/heads/main {expected_remote_head}\n",
        encoding="ascii",
    )
    challenge_path, approval_command = _prepare_authorization(
        repository,
        "Push",
        remote_name="origin",
        push_updates_path=updates_path,
    )
    authorization_path = _approve_authorization(
        repository, challenge_path, approval_command
    )
    environment = os.environ.copy()
    environment["AI4BINANCE_GIT_WRITE_AUTHORIZATION_PATH"] = str(authorization_path)
    blocked = subprocess.run(  # noqa: S603
        [git, "-C", str(repository), "push", "origin", "main"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )

    assert blocked.returncode != 0
    assert "REMOTE_REF_NOT_FAST_FORWARD: refs/heads/main" in blocked.stderr
    assert "GIT_WRITE_AUTHORIZATION_CONSUMED" not in (blocked.stdout + blocked.stderr)
    assert authorization_path.is_file()


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


def test_github_workflows_pin_external_actions_to_immutable_revisions() -> None:
    checkout = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
    upload_artifact = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
    setup_uv = "astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9"

    for relative in (
        ".github/workflows/nightly_quality_triage.yml",
        ".github/workflows/quality_profiles.yml",
        ".github/workflows/security_tooling.yml",
    ):
        workflow = _read(relative)
        assert checkout in workflow
        assert upload_artifact in workflow
        assert setup_uv in workflow

    for workflow_path in (REPOSITORY_ROOT / ".github/workflows").glob("*.yml"):
        workflow = workflow_path.read_text(encoding="utf-8")
        actions = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, flags=re.MULTILINE)
        assert actions
        assert all(re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", action) for action in actions)


def test_github_security_governance_files_define_owners_updates_and_reporting() -> None:
    dependabot = _read(".github/dependabot.yml")
    codeowners = _read(".github/CODEOWNERS")
    security = _read(".github/SECURITY.md")

    assert "package-ecosystem: uv" in dependabot
    assert "package-ecosystem: github-actions" in dependabot
    assert "interval: weekly" in dependabot
    assert "@Huseyin-Cicek" in codeowners
    assert "private GitHub security advisory" in security
    assert "Do not open a public issue" in security


def test_gitleaks_ignore_list_contains_only_exact_historic_fingerprints() -> None:
    entries = [
        line
        for line in _read(".gitleaksignore").splitlines()
        if line and not line.startswith("#")
    ]

    assert len(entries) == 13
    assert all(":generic-api-key:" in entry for entry in entries)
    assert all(re.fullmatch(r"[0-9a-f]{40}:.+:[1-9][0-9]*", entry) for entry in entries)


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

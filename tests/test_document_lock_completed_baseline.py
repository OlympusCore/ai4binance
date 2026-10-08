"""TEST_ONLY real Git lineage checks; never runtime owner approval evidence."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai4binance.governance import document_lock_review as review

MANIFEST = "config/governance/governed_document_lock_manifest.json"
OBJECT_WRITE_DENIED = (
    "error: unable to write file .git/objects/17/"
    "72e20733acea0bf547a9de640ede031caef9ab: Permission denied\n"
)


def _git_fixture_object_write_denied(arguments: tuple[str, ...], stderr: str) -> bool:
    fixture_commit = arguments[:5] == (
        "-c",
        "user.name=TEST_ONLY_fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
    )
    return (
        os.name == "nt"
        and bool(arguments)
        and (
            arguments[0] in {"add", "write-tree"}
            or (
                fixture_commit
                and stderr.rstrip().endswith("fatal: failed to write commit object")
            )
        )
        and re.search(
            r"(?m)^error: unable to write file \.git/objects/[0-9a-f]{2}/"
            r"(?:[0-9a-f]{38}|[0-9a-f]{62}): Permission denied$",
            stderr,
        )
        is not None
    )


def _fixture_refs(root: Path) -> tuple[bytes, str]:
    return (
        (root / ".git" / "HEAD").read_bytes(),
        git(root, "for-each-ref", "--format=%(refname) %(objectname)"),
    )


def git(root: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    assert executable is not None
    assert root.resolve() != Path(__file__).resolve().parents[1]
    fixture_commit = arguments[:5] == (
        "-c",
        "user.name=TEST_ONLY_fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
    )
    before_refs = _fixture_refs(root) if fixture_commit else None
    for attempt in range(3):
        try:
            return subprocess.run(  # noqa: S603 - isolated TEST_ONLY Git fixture
                [executable, "-C", str(root), *arguments],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
        except subprocess.CalledProcessError as error:
            stderr = error.stderr or ""
            if (
                attempt == 2
                or error.returncode != 128
                or not _git_fixture_object_write_denied(arguments, stderr)
                or (fixture_commit and _fixture_refs(root) != before_refs)
            ):
                error.add_note(f"TEST_ONLY Git fixture stderr: {stderr}")
                raise
            warnings.warn(
                f"TEST_ONLY Git object write retry {attempt + 1}/2: {stderr.strip()}",
                RuntimeWarning,
                stacklevel=2,
            )
            time.sleep(0.1 * (attempt + 1))
    raise AssertionError("TEST_ONLY Git fixture exhausted its bounded attempts")


def commit(root: Path) -> str:
    git(root, "add", "--all")
    git(
        root,
        "-c",
        "user.name=TEST_ONLY_fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "TEST_ONLY fixture checkpoint",
    )
    return git(root, "rev-parse", "HEAD")


@pytest.mark.parametrize("persistent", [False, True])
def test_fixture_object_write_retry_preserves_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, persistent: bool
) -> None:
    monkeypatch.setattr(
        __import__(__name__, fromlist=["os"]), "os", SimpleNamespace(name="nt")
    )
    monkeypatch.setattr(shutil, "which", lambda _: "TEST_ONLY_git")
    delays: list[float] = []
    monkeypatch.setattr(time, "sleep", delays.append)
    calls = 0

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if persistent or calls == 1:
            raise subprocess.CalledProcessError(128, argv, stderr=OBJECT_WRITE_DENIED)
        return subprocess.CompletedProcess(argv, 0, stdout="TEST_ONLY_object\n")

    monkeypatch.setattr(subprocess, "run", run)
    if persistent:
        with (
            pytest.warns(
                RuntimeWarning, match="TEST_ONLY Git object write retry"
            ) as observed,
            pytest.raises(subprocess.CalledProcessError) as error,
        ):
            git(tmp_path, "add", "--all")
        assert OBJECT_WRITE_DENIED in error.value.__notes__[0]
    else:
        with pytest.warns(
            RuntimeWarning, match="TEST_ONLY Git object write retry"
        ) as observed:
            output = git(tmp_path, "add", "--all")
        assert output == "TEST_ONLY_object"
    assert calls == (3 if persistent else 2)
    assert delays == ([0.1, 0.2] if persistent else [0.1])
    assert len(observed) == (2 if persistent else 1)


@pytest.mark.parametrize(
    ("arguments", "stderr", "platform"),
    [
        (("commit", "-m", "TEST_ONLY"), OBJECT_WRITE_DENIED, "nt"),
        (("add", "--all"), "fatal: GIT_COMPLETION_BLOCKED\n", "nt"),
        (
            ("add", "--all"),
            "fatal: unable to create index.lock: Permission denied\n",
            "nt",
        ),
        (("add", "--all"), OBJECT_WRITE_DENIED, "posix"),
    ],
)
def test_fixture_other_git_failures_are_not_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: tuple[str, ...],
    stderr: str,
    platform: str,
) -> None:
    monkeypatch.setattr(
        __import__(__name__, fromlist=["os"]), "os", SimpleNamespace(name=platform)
    )
    monkeypatch.setattr(shutil, "which", lambda _: "TEST_ONLY_git")
    calls = 0

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise subprocess.CalledProcessError(128, argv, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError) as error:
        git(tmp_path, *arguments)
    assert calls == 1
    assert stderr in error.value.__notes__[0]


@pytest.mark.parametrize("refs_changed", [False, True])
def test_fixture_commit_retry_requires_unchanged_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refs_changed: bool
) -> None:
    monkeypatch.setattr(
        __import__(__name__, fromlist=["os"]), "os", SimpleNamespace(name="nt")
    )
    monkeypatch.setattr(shutil, "which", lambda _: "TEST_ONLY_git")
    delays: list[float] = []
    monkeypatch.setattr(time, "sleep", delays.append)
    head = tmp_path / ".git" / "HEAD"
    head.parent.mkdir()
    head.write_bytes(b"ref: refs/heads/TEST_ONLY\n")
    calls = 0
    stderr = OBJECT_WRITE_DENIED + "fatal: failed to write commit object\n"

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        if "for-each-ref" in argv:
            refs = "TEST_ONLY_changed" if refs_changed and calls else "TEST_ONLY_before"
            return subprocess.CompletedProcess(argv, 0, stdout=refs)
        calls += 1
        if calls == 1:
            raise subprocess.CalledProcessError(128, argv, stderr=stderr)
        return subprocess.CompletedProcess(argv, 0, stdout="TEST_ONLY_commit")

    monkeypatch.setattr(subprocess, "run", run)
    arguments = (
        "-c",
        "user.name=TEST_ONLY_fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "TEST_ONLY checkpoint",
    )
    if refs_changed:
        with pytest.raises(subprocess.CalledProcessError) as error:
            git(tmp_path, *arguments)
        assert stderr in error.value.__notes__[0]
    else:
        with pytest.warns(RuntimeWarning, match="TEST_ONLY Git object write retry"):
            output = git(tmp_path, *arguments)
        assert output == "TEST_ONLY_commit"
    assert calls == (1 if refs_changed else 2)
    assert delays == ([] if refs_changed else [0.1])


@pytest.fixture
def accepted(tmp_path: Path) -> tuple[Path, dict[str, Any], str, str]:
    root = tmp_path / "TEST_ONLY_repository"
    root.mkdir()
    git(root, "init")
    manifest = root / MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_bytes(b'{"TEST_ONLY":"predecessor"}\n')
    document = root / "AGENTS.md"
    document.write_bytes(b"TEST_ONLY predecessor document\n")
    baseline = commit(root)
    content = b"TEST_ONLY reviewed installed document\n"
    document.write_bytes(content)
    manifest.write_bytes(b'{"TEST_ONLY":"installed"}\n')
    installed_commit = commit(root)
    tree = git(root, "rev-parse", "HEAD^{tree}")
    subject = {
        "baseline_commit": baseline,
        "documents": [
            {"path": "AGENTS.md", "sha256": hashlib.sha256(content).hexdigest()}
        ],
    }
    return root, subject, installed_commit, tree


def test_completed_review_uses_real_accepted_transition(
    accepted: tuple[Path, dict[str, Any], str, str],
) -> None:
    root, subject, _, tree = accepted
    with pytest.raises(ValueError, match="BASELINE_OR_ROOT_DRIFT"):
        review._baseline(root, subject["baseline_commit"])
    review._completed_baseline(root, subject, tree)


def test_unrelated_successor_preserves_completed_document_authority(
    accepted: tuple[Path, dict[str, Any], str, str],
) -> None:
    root, subject, _, tree = accepted
    (root / "TEST_ONLY_unrelated.txt").write_bytes(b"TEST_ONLY unrelated successor\n")
    commit(root)
    review._completed_baseline(root, subject, tree)


@pytest.mark.parametrize("target", ["AGENTS.md", MANIFEST])
def test_current_protected_bytes_must_equal_accepted_bytes(
    accepted: tuple[Path, dict[str, Any], str, str], target: str
) -> None:
    root, subject, _, tree = accepted
    (root / target).write_bytes(b"TEST_ONLY unauthorized drift\n")
    with pytest.raises(ValueError, match=r"COMPLETED_(DOCUMENT|MANIFEST)_DRIFT"):
        review._completed_baseline(root, subject, tree)


def test_predecessor_tree_is_not_an_accepted_installation(
    accepted: tuple[Path, dict[str, Any], str, str],
) -> None:
    root, subject, _, _ = accepted
    tree = git(root, "rev-parse", subject["baseline_commit"] + "^{tree}")
    with pytest.raises(ValueError, match="COMPLETED_TREE_NOT_ACCEPTED"):
        review._completed_baseline(root, subject, tree)


def test_tree_outside_current_ancestry_is_rejected(
    accepted: tuple[Path, dict[str, Any], str, str],
) -> None:
    root, subject, installed_commit, _ = accepted
    git(root, "switch", "--detach", subject["baseline_commit"])
    (root / "TEST_ONLY_other_branch.txt").write_bytes(b"TEST_ONLY other lineage\n")
    commit(root)
    wrong_tree = git(root, "rev-parse", "HEAD^{tree}")
    git(root, "switch", "--detach", installed_commit)
    with pytest.raises(ValueError, match="COMPLETED_TREE_NOT_ACCEPTED"):
        review._completed_baseline(root, subject, wrong_tree)


def test_missing_committed_tree_is_rejected(
    accepted: tuple[Path, dict[str, Any], str, str],
) -> None:
    root, subject, _, _ = accepted
    with pytest.raises(ValueError, match="COMPLETED_TREE_NOT_ACCEPTED"):
        review._completed_baseline(root, subject, "0" * 40)

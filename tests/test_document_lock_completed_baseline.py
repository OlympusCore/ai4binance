"""TEST_ONLY real Git lineage checks; never runtime owner approval evidence."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from ai4binance.governance import document_lock_review as review

MANIFEST = "config/governance/governed_document_lock_manifest.json"


def git(root: Path, *arguments: str) -> str:
    executable = shutil.which("git")
    assert executable is not None
    return subprocess.run(  # noqa: S603 - isolated TEST_ONLY Git fixture
        [executable, "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


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

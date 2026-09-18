"""Fail-closed tests for the local-only public showcase staging boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ai4binance.ops.public_showcase import (
    PublicShowcaseError,
    load_public_showcase_manifest,
    stage_public_showcase,
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(source: str, digest: str, *, denied: str = "private") -> str:
    return f"""version: 1
publication:
  name: Test Showcase
  mode: LOCAL_STAGING_ONLY
  remote_publication_allowed: false
  human_approval_required: true
allowed_artifacts:
  - source: {source}
    destination: README.md
    sha256: {digest}
denied_paths:
  - {denied}
secret_scan:
  required: true
  gitleaks_version: 8.30.1
"""


def test_repository_showcase_manifest_is_local_only_and_hash_bound() -> None:
    manifest = load_public_showcase_manifest(
        Path("config/publication/public_showcase_manifest.yaml")
    )

    assert manifest.gitleaks_version == "8.30.1"
    assert {artifact.destination for artifact in manifest.allowed_artifacts} == {
        "README.md",
        "DISCLAIMER.md",
    }
    for artifact in manifest.allowed_artifacts:
        assert artifact.sha256 == _hash(Path(artifact.source))


def test_public_showcase_stages_only_hash_bound_allowlisted_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "canonical"
    source.mkdir()
    content = "Public reference content.\n"
    (source / "showcase.md").write_text(content, encoding="utf-8")
    (source / "private").mkdir()
    (source / "private" / "secret.txt").write_text("do not export", encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        _manifest("showcase.md", _hash(source / "showcase.md")), encoding="utf-8"
    )

    scanned: list[Path] = []

    def record_scan(stage: Path) -> None:
        scanned.append(stage)
        assert (stage / "README.md").is_file()

    report = stage_public_showcase(
        source,
        load_public_showcase_manifest(manifest_path),
        tmp_path / "showcase-output",
        secret_scanner=record_scan,
    )

    assert (tmp_path / "showcase-output" / "README.md").read_text(
        encoding="utf-8"
    ) == content
    assert not (tmp_path / "showcase-output" / "private").exists()
    assert scanned
    assert report["status"] == "READY_FOR_HUMAN_APPROVAL"
    assert report["remote_publication_allowed"] is False
    assert report["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_public_showcase_rejects_denied_or_changed_sources_before_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "canonical"
    source.mkdir()
    content = "Sensitive content.\n"
    (source / "private").mkdir()
    (source / "private" / "report.md").write_text(content, encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        _manifest("private/report.md", _hash(source / "private" / "report.md")),
        encoding="utf-8",
    )

    with pytest.raises(PublicShowcaseError, match="conflicts with a denied path"):
        stage_public_showcase(
            source,
            load_public_showcase_manifest(manifest_path),
            tmp_path / "showcase-output",
            secret_scanner=lambda _: None,
        )
    assert not (tmp_path / "showcase-output").exists()


def test_public_showcase_rejects_hash_drift_and_secret_scan_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "canonical"
    source.mkdir()
    (source / "showcase.md").write_text("changed\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        _manifest("showcase.md", hashlib.sha256(b"expected\\n").hexdigest()),
        encoding="utf-8",
    )

    with pytest.raises(PublicShowcaseError, match="hash changed"):
        stage_public_showcase(
            source,
            load_public_showcase_manifest(manifest_path),
            tmp_path / "hash-output",
            secret_scanner=lambda _: None,
        )
    assert not (tmp_path / "hash-output").exists()

    content = "clean\n"
    (source / "showcase.md").write_text(content, encoding="utf-8")
    manifest_path.write_text(
        _manifest("showcase.md", _hash(source / "showcase.md")), encoding="utf-8"
    )
    with pytest.raises(PublicShowcaseError, match="scanner failed"):
        stage_public_showcase(
            source,
            load_public_showcase_manifest(manifest_path),
            tmp_path / "scan-output",
            secret_scanner=lambda _: (_ for _ in ()).throw(
                PublicShowcaseError("scanner failed")
            ),
        )
    assert not (tmp_path / "scan-output").exists()

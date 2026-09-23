"""Fail-closed tests for the local-only public showcase staging boundary."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ai4binance.ops import public_showcase as showcase
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


@pytest.mark.parametrize("value", ["", "/absolute", "back\\slash", "a/../b"])
def test_showcase_helpers_reject_unsafe_contract_values(value: str) -> None:
    with pytest.raises(PublicShowcaseError):
        showcase._safe_relative_path(value, field="artifact")
    with pytest.raises(PublicShowcaseError, match="name"):
        showcase._required_text({}, "name")
    assert showcase._is_denied("private/a.txt", ("private",))
    assert not showcase._is_denied("public/a.txt", ("private",))


def test_showcase_manifest_contract_parsers_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(PublicShowcaseError, match="cannot read"):
        showcase._load_manifest_payload(missing)
    path = tmp_path / "manifest.yaml"
    path.write_text("version: 2", encoding="utf-8")
    with pytest.raises(PublicShowcaseError, match="fields"):
        showcase._load_manifest_payload(path)
    with pytest.raises(PublicShowcaseError):
        showcase._parse_publication({"name": "x"})
    with pytest.raises(PublicShowcaseError):
        showcase._parse_artifacts([])
    with pytest.raises(PublicShowcaseError):
        showcase._parse_denied_paths(["private", "private"])
    with pytest.raises(PublicShowcaseError):
        showcase._parse_gitleaks_version({"required": False, "gitleaks_version": "8"})


def test_showcase_scan_and_output_preconditions_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(PublicShowcaseError, match="unavailable"):
        showcase.run_gitleaks_scan(tmp_path, tmp_path / "missing.exe")

    executable = tmp_path / "gitleaks.exe"
    executable.write_text("fixture", encoding="utf-8")
    failed = type("Completed", (), {"returncode": 1})()
    monkeypatch.setattr(showcase.subprocess, "run", lambda *_args, **_kwargs: failed)
    with pytest.raises(PublicShowcaseError, match="failed"):
        showcase.run_gitleaks_scan(tmp_path, executable)
    monkeypatch.setattr(
        showcase.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unavailable")),
    )
    with pytest.raises(PublicShowcaseError, match="did not complete"):
        showcase.run_gitleaks_scan(tmp_path, executable)

    manifest = showcase.PublicShowcaseManifest("name", (), (), "8")
    with pytest.raises(PublicShowcaseError, match="outside"):
        stage_public_showcase(
            tmp_path, manifest, tmp_path, secret_scanner=lambda _: None
        )
    existing = tmp_path.parent / "existing-output"
    existing.mkdir(exist_ok=True)
    with pytest.raises(PublicShowcaseError, match="already exist"):
        stage_public_showcase(
            tmp_path, manifest, existing, secret_scanner=lambda _: None
        )


def test_showcase_rejects_each_authority_expansion_shape(tmp_path: Path) -> None:
    payload = {
        "name": "name",
        "mode": "LOCAL_STAGING_ONLY",
        "remote_publication_allowed": False,
        "human_approval_required": True,
    }
    for key, value in (
        ("mode", "REMOTE"),
        ("remote_publication_allowed", True),
        ("human_approval_required", False),
    ):
        changed = dict(payload)
        changed[key] = value
        with pytest.raises(PublicShowcaseError):
            showcase._parse_publication(changed)
    valid = {
        "source": "README.md",
        "destination": "README.md",
        "sha256": "a" * 64,
    }
    assert showcase._parse_artifacts([valid])[0].source == "README.md"
    for artifacts in ([{}], [{**valid, "sha256": "A" * 64}], [valid, valid]):
        with pytest.raises(PublicShowcaseError):
            showcase._parse_artifacts(artifacts)
    with pytest.raises(PublicShowcaseError, match="non-empty"):
        showcase._parse_denied_paths([])
    with pytest.raises(PublicShowcaseError, match="secret_scan"):
        showcase._parse_gitleaks_version({})

    manifest_path = tmp_path / "version.yaml"
    manifest_path.write_text(
        "version: 2\npublication: {}\nallowed_artifacts: []\n"
        "denied_paths: []\nsecret_scan: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(PublicShowcaseError, match="version"):
        showcase._load_manifest_payload(manifest_path)
    missing_parent = tmp_path.parent / "missing-parent" / "output"
    with pytest.raises(PublicShowcaseError, match="parent"):
        stage_public_showcase(
            tmp_path,
            showcase.PublicShowcaseManifest("name", (), (), "8"),
            missing_parent,
            secret_scanner=lambda _: None,
        )
    missing_source = showcase.PublicShowcaseManifest(
        "name",
        (showcase.PublicArtifact("gone.md", "gone.md", "a" * 64),),
        (),
        "8",
    )
    with pytest.raises(PublicShowcaseError, match="missing"):
        stage_public_showcase(
            tmp_path,
            missing_source,
            tmp_path.parent / "missing-source-output",
            secret_scanner=lambda _: None,
        )

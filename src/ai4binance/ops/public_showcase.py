"""Build a local, allowlist-only public showcase without remote publication."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class PublicShowcaseError(ValueError):
    """Raised when a public showcase cannot be safely staged."""


@dataclass(frozen=True)
class PublicArtifact:
    """One exact, hash-bound artifact permitted in the showcase."""

    source: str
    destination: str
    sha256: str


@dataclass(frozen=True)
class PublicShowcaseManifest:
    """Fail-closed contract for a local-only public showcase export."""

    name: str
    allowed_artifacts: tuple[PublicArtifact, ...]
    denied_paths: tuple[str, ...]
    gitleaks_version: str


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PublicShowcaseError(f"{key} must be a non-empty string")
    return value


def _safe_relative_path(value: str, *, field: str) -> str:
    if not value or value.startswith(("/", "\\")) or "\\" in value:
        raise PublicShowcaseError(f"{field} must be a safe forward-slash relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PublicShowcaseError(
            f"{field} must not contain empty or traversal segments"
        )
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest_payload(path: Path) -> dict[str, object]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise PublicShowcaseError(
            f"cannot read public showcase manifest: {path}"
        ) from error
    if not isinstance(payload, dict) or set(payload) != {
        "version",
        "publication",
        "allowed_artifacts",
        "denied_paths",
        "secret_scan",
    }:
        raise PublicShowcaseError("manifest fields are incomplete or unsupported")
    if payload["version"] != 1:
        raise PublicShowcaseError("manifest version must be 1")
    return payload


def _parse_publication(payload: object) -> str:
    if not isinstance(payload, dict) or set(payload) != {
        "name",
        "mode",
        "remote_publication_allowed",
        "human_approval_required",
    }:
        raise PublicShowcaseError("publication contract is incomplete or unsupported")
    if payload["mode"] != "LOCAL_STAGING_ONLY":
        raise PublicShowcaseError("publication mode must remain LOCAL_STAGING_ONLY")
    if payload["remote_publication_allowed"] is not False:
        raise PublicShowcaseError("manifest cannot permit remote publication")
    if payload["human_approval_required"] is not True:
        raise PublicShowcaseError("manifest must require human approval")
    return _required_text(payload, "name")


def _parse_artifacts(payload: object) -> tuple[PublicArtifact, ...]:
    if not isinstance(payload, list) or not payload:
        raise PublicShowcaseError("allowed_artifacts must be a non-empty list")
    parsed: list[PublicArtifact] = []
    for item in payload:
        if not isinstance(item, dict) or set(item) != {
            "source",
            "destination",
            "sha256",
        }:
            raise PublicShowcaseError(
                "each allowed artifact requires source, destination, and sha256"
            )
        source = _safe_relative_path(_required_text(item, "source"), field="source")
        destination = _safe_relative_path(
            _required_text(item, "destination"), field="destination"
        )
        sha256 = _required_text(item, "sha256")
        if len(sha256) != 64 or any(
            character not in "0123456789abcdef" for character in sha256
        ):
            raise PublicShowcaseError(
                "artifact sha256 must be a lowercase SHA-256 digest"
            )
        parsed.append(PublicArtifact(source, destination, sha256))
    if len({item.source for item in parsed}) != len(parsed):
        raise PublicShowcaseError("allowed artifact sources must be unique")
    if len({item.destination for item in parsed}) != len(parsed):
        raise PublicShowcaseError("allowed artifact destinations must be unique")
    return tuple(parsed)


def _parse_denied_paths(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, list) or not payload:
        raise PublicShowcaseError("denied_paths must be a non-empty list")
    parsed = tuple(
        _safe_relative_path(value, field="denied path")
        for value in payload
        if isinstance(value, str)
    )
    if len(parsed) != len(payload) or len(set(parsed)) != len(parsed):
        raise PublicShowcaseError("denied paths must be unique non-empty strings")
    return parsed


def _parse_gitleaks_version(payload: object) -> str:
    if not isinstance(payload, dict) or set(payload) != {
        "required",
        "gitleaks_version",
    }:
        raise PublicShowcaseError("secret_scan contract is incomplete or unsupported")
    if payload["required"] is not True:
        raise PublicShowcaseError("secret scanning must remain required")
    return _required_text(payload, "gitleaks_version")


def load_public_showcase_manifest(path: Path) -> PublicShowcaseManifest:
    """Load the exact-publication manifest and reject authority expansion."""

    payload = _load_manifest_payload(path)
    return PublicShowcaseManifest(
        name=_parse_publication(payload["publication"]),
        allowed_artifacts=_parse_artifacts(payload["allowed_artifacts"]),
        denied_paths=_parse_denied_paths(payload["denied_paths"]),
        gitleaks_version=_parse_gitleaks_version(payload["secret_scan"]),
    )


def _is_denied(path: str, denied_paths: tuple[str, ...]) -> bool:
    return any(
        path == denied or path.startswith(f"{denied}/") for denied in denied_paths
    )


def run_gitleaks_scan(stage_root: Path, executable: Path) -> None:
    """Run a redacted directory scan and fail closed for all non-zero exits."""

    if not executable.is_file():
        raise PublicShowcaseError(
            f"required Gitleaks executable is unavailable: {executable}"
        )
    report_path = stage_root.parent / f"{stage_root.name}-gitleaks.json"
    try:
        completed = subprocess.run(  # noqa: S603 - executable is repository-pinned.
            [
                str(executable),
                "dir",
                "--redact=100",
                "--report-format",
                "json",
                "--report-path",
                str(report_path),
                "--no-banner",
                "--no-color",
                "--exit-code",
                "1",
                str(stage_root),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PublicShowcaseError(
            "public showcase secret scan did not complete"
        ) from error
    finally:
        report_path.unlink(missing_ok=True)
    if completed.returncode != 0:
        raise PublicShowcaseError(
            "public showcase secret scan failed or found secret-like content"
        )


def stage_public_showcase(
    repository_root: Path,
    manifest: PublicShowcaseManifest,
    output_directory: Path,
    *,
    secret_scanner: Callable[[Path], None],
) -> dict[str, Any]:
    """Stage only validated artifacts and leave remote publication prohibited."""

    root = repository_root.resolve()
    destination = output_directory.resolve()
    if destination == root or destination.is_relative_to(root):
        raise PublicShowcaseError(
            "output directory must be outside the canonical repository"
        )
    if destination.exists():
        raise PublicShowcaseError("output directory must not already exist")
    parent = destination.parent
    if not parent.is_dir():
        raise PublicShowcaseError("output directory parent must already exist")
    selected: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(
        prefix="ai4binance-public-showcase-", dir=parent
    ) as temporary:
        stage_root = Path(temporary)
        for artifact in manifest.allowed_artifacts:
            if _is_denied(artifact.source, manifest.denied_paths):
                raise PublicShowcaseError(
                    "allowed artifact conflicts with a denied path"
                )
            source = (root / artifact.source).resolve()
            if not source.is_file() or not source.is_relative_to(root):
                raise PublicShowcaseError(
                    f"allowed artifact is missing or unsafe: {artifact.source}"
                )
            actual_hash = _sha256(source)
            if actual_hash != artifact.sha256:
                raise PublicShowcaseError(
                    f"allowed artifact hash changed: {artifact.source}"
                )
            target = stage_root.joinpath(*artifact.destination.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            selected.append(
                {
                    "source": artifact.source,
                    "destination": artifact.destination,
                    "sha256": actual_hash,
                }
            )
        secret_scanner(stage_root)
        stage_root.replace(destination)
    return {
        "status": "READY_FOR_HUMAN_APPROVAL",
        "publication_name": manifest.name,
        "selected_artifacts": selected,
        "secret_scan": "PASSED",
        "remote_publication_allowed": False,
        "human_approval_required": True,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

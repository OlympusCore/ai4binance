from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai4binance.governance.repository_validator import (
    MirrorCleanupAction,
    MirrorHygieneReport,
    MirrorPathClassification,
    RepositoryFindingKind,
    RepositoryMirrorPolicy,
    RepositoryValidationStatus,
    load_repository_mirror_policy,
    validate_mirror_hygiene,
)


def _write_manifest(path: Path, entries: list[object], **extra: object) -> Path:
    payload = {"entries": entries, **extra}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def mirror_policy() -> RepositoryMirrorPolicy:
    policy_path = Path("config/governance/repository_mirror_policy.yaml")
    return load_repository_mirror_policy(policy_path)


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        (".git/config", RepositoryFindingKind.MIRROR_FORBIDDEN_PATH),
        (".mypy_cache/3.12/cache.json", RepositoryFindingKind.MIRROR_CACHE_POLLUTION),
        (".ruff_cache/content", RepositoryFindingKind.MIRROR_CACHE_POLLUTION),
        (
            "artifacts/test_temp/pytest-output.txt",
            RepositoryFindingKind.MIRROR_CACHE_POLLUTION,
        ),
        (".hypothesis/examples/db", RepositoryFindingKind.MIRROR_CACHE_POLLUTION),
        (
            "src/ai4binance/__pycache__/module.cpython-312.pyc",
            RepositoryFindingKind.MIRROR_GENERATED_ARTIFACT,
        ),
        (
            "src/ai4binance.egg-info/PKG-INFO",
            RepositoryFindingKind.MIRROR_GENERATED_ARTIFACT,
        ),
        (
            "runtime/state/private/account.json",
            RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION,
        ),
        (".env.production", RepositoryFindingKind.MIRROR_PRIVATE_EVIDENCE_VIOLATION),
    ],
)
def test_mirror_rejects_forbidden_surfaces(
    tmp_path: Path,
    mirror_policy: RepositoryMirrorPolicy,
    path: str,
    kind: RepositoryFindingKind,
) -> None:
    manifest = _write_manifest(tmp_path / "mirror.json", [path])

    report = validate_mirror_hygiene(manifest, policy=mirror_policy)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert any(
        finding.kind is kind and finding.path == path for finding in report.findings
    )
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "path",
    [
        "src/ai4binance/governance/repository_validator.py",
        "tests/test_repository_validator.py",
        "docs/standards/standard_repository_file_governance.md",
        "schemas/governance/repository_artifact.schema.json",
        "config/governance/blocker_registry.yaml",
        "runtime/audit/governance-baseline.json",
        "runtime/evidence/quality.json",
        "runtime/reports/weekly.md",
        "runtime/artifacts/quality/gate/latest.json",
        ".env.example",
    ],
)
def test_mirror_accepts_allowlisted_surfaces(
    tmp_path: Path,
    mirror_policy: RepositoryMirrorPolicy,
    path: str,
) -> None:
    manifest = _write_manifest(tmp_path / "mirror.json", [path])

    report = validate_mirror_hygiene(manifest, policy=mirror_policy)

    assert report.status is RepositoryValidationStatus.PASS
    assert report.findings == ()
    assert report.cleanup_plan[0].mirror_action is MirrorCleanupAction.KEEP_IN_MIRROR


def test_mirror_does_not_grant_source_of_truth(
    tmp_path: Path,
    mirror_policy: RepositoryMirrorPolicy,
) -> None:
    manifest = _write_manifest(
        tmp_path / "mirror.json",
        [{"path": "src/ai4binance/example.py", "source_of_truth": True}],
        source_of_truth=True,
    )

    report = validate_mirror_hygiene(manifest, policy=mirror_policy)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert report.mirror_source_of_truth is False
    assert (
        sum(
            1
            for finding in report.findings
            if finding.kind is RepositoryFindingKind.MIRROR_SOURCE_OF_TRUTH_VIOLATION
        )
        == 2
    )


def test_unknown_mirror_path_fails_closed(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "mirror.json", ["unclassified/output.bin"])

    report = validate_mirror_hygiene(manifest)

    assert report.status is RepositoryValidationStatus.RUNNING_WITH_BLOCKERS
    assert report.findings[0].kind is RepositoryFindingKind.MIRROR_UNKNOWN_PATH
    assert report.cleanup_plan[0].classification is MirrorPathClassification.UNKNOWN
    assert (
        report.cleanup_plan[0].mirror_action
        is MirrorCleanupAction.QUARANTINE_FOR_REVIEW
    )


def test_mirror_policy_schema_is_valid() -> None:
    policy = yaml.safe_load(
        Path("config/governance/repository_mirror_policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    schema = json.loads(
        Path("schemas/governance/repository_mirror_policy.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert schema["properties"]["mirror"]["properties"]["role"]["const"] == (
        "NON_CANONICAL_MIRROR"
    )
    assert schema["properties"]["mirror"]["properties"]["authority"]["const"] == "NONE"
    assert (
        schema["properties"]["mirror"]["properties"]["may_be_source_of_truth"]["const"]
        is False
    )
    assert policy["sync"]["default_action"] == "EXCLUDE"
    assert ".git/**" in policy["exclusions"]["hard_exclude_patterns"]


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"mirror_role": "CANONICAL_SOURCE"}, "NON_CANONICAL_MIRROR"),
        ({"mirror_authority": "REPOSITORY"}, "authority must be NONE"),
        ({"may_be_source_of_truth": True}, "cannot grant repository authority"),
        ({"may_override_canonical": True}, "cannot grant repository authority"),
        ({"default_action": "INCLUDE"}, "allowlist-first"),
    ],
)
def test_mirror_policy_rejects_authority_escalation(
    mirror_policy: RepositoryMirrorPolicy,
    override: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        replace(mirror_policy, **override)


@pytest.mark.parametrize(
    ("override", "match"),
    [
        (
            {"mirror_source_of_truth": True},
            "cannot grant source-of-truth authority",
        ),
        (
            {
                "status": RepositoryValidationStatus.PASS,
                "blockers": ("MIRROR_UNKNOWN_PATH",),
            },
            "passing mirror validation cannot contain blockers",
        ),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"promotion_status": "PAPER_ONLY"}, "cannot authorize execution"),
        ({"live_eligibility_status": "LIVE_ELIGIBLE"}, "cannot authorize live trading"),
    ],
)
def test_mirror_report_remains_fail_closed(
    tmp_path: Path,
    mirror_policy: RepositoryMirrorPolicy,
    override: dict[str, Any],
    match: str,
) -> None:
    manifest = _write_manifest(
        tmp_path / "mirror.json",
        ["src/ai4binance/governance/repository_validator.py"],
    )
    report = validate_mirror_hygiene(manifest, policy=mirror_policy)

    assert isinstance(report, MirrorHygieneReport)
    with pytest.raises(ValueError, match=match):
        replace(report, **override)


def test_cleanup_plan_never_deletes_unknown(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "mirror.json",
        ["unknown.bin", ".mypy_cache/state.json"],
    )

    report = validate_mirror_hygiene(manifest)
    plan_by_path = {entry.path: entry for entry in report.cleanup_plan}

    assert (
        plan_by_path["unknown.bin"].classification is MirrorPathClassification.UNKNOWN
    )
    assert (
        plan_by_path["unknown.bin"].mirror_action
        is MirrorCleanupAction.QUARANTINE_FOR_REVIEW
    )
    assert plan_by_path[".mypy_cache/state.json"].mirror_action is (
        MirrorCleanupAction.REMOVE_FROM_MIRROR
    )
    assert report.dashboard_metrics["mirror_cleanup_destructive_unknowns"] == 0


def test_cleanup_plan_preserves_governed_artifacts(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path / "mirror.json",
        ["docs/controls/control_repository_validation_rules.md"],
    )

    report = validate_mirror_hygiene(manifest)

    assert report.status is RepositoryValidationStatus.PASS
    assert report.cleanup_plan[0].canonical_required is True
    assert report.cleanup_plan[0].mirror_action is MirrorCleanupAction.KEEP_IN_MIRROR

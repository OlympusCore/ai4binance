"""Runner manifests and admission evidence remain internally consistent."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from ai4binance.local_agent.advisory_fixture import LoopbackAdvisoryFixtureProvider
from ai4binance.local_agent.advisory_runner import (
    LocalAdvisoryFixtureRunner,
    LocalAdvisoryFixtureRunnerResult,
)
from ai4binance.ops.jobs import (
    JobCapability,
    RunnerAdmissionStatus,
    local_advisory_fixture_runner_manifest,
)
from tests.test_local_qwen_workbench import (
    FakeRunner,
    _admitted_fixture_request,
    _fixture,
)


@pytest.fixture
def admitted_result(tmp_path: Path) -> LocalAdvisoryFixtureRunnerResult:
    manifest = local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts")
    result = LocalAdvisoryFixtureRunner(manifest).run(
        _admitted_fixture_request(tmp_path),
        (_fixture("fixture-contract"),),
        LoopbackAdvisoryFixtureProvider(
            FakeRunner(), clock=lambda: datetime(2026, 9, 3, tzinfo=UTC)
        ),
        observed_at=datetime(2026, 9, 3, tzinfo=UTC),
    )
    assert result.status == "PASS"
    return result


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "UNKNOWN", "status"),
        ("harness_report", None, "admission"),
        ("blockers", ("CONFLICT",), "outcome"),
        ("status", "BLOCKED", "outcome"),
        ("execution_allowed", True, "promote or execute"),
        ("promotion_evidence", True, "promote or execute"),
        ("promotion_status", "STAGED_CANDIDATE", "promote or execute"),
        ("live_eligibility_status", "LIVE", "promote or execute"),
    ],
)
def test_advisory_result_cannot_contradict_admission_or_grant_authority(
    admitted_result: LocalAdvisoryFixtureRunnerResult,
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(admitted_result, **{field: cast(Any, value)})


def test_advisory_runner_rejects_unrelated_manifest(tmp_path: Path) -> None:
    manifest = local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts")
    with pytest.raises(ValueError, match="manifest is invalid"):
        LocalAdvisoryFixtureRunner(replace(manifest, runner_id="runner:unrelated"))


@pytest.mark.parametrize(
    ("subject", "field", "value", "message"),
    [
        ("capability_manifest", "manifest_id", "", "identity"),
        ("capability_manifest", "allowed_capabilities", (), "capabilities"),
        ("capability_manifest", "allowed_roots", (Path("relative"),), "absolute"),
        ("capability_manifest", "side_effect_allowlist", (), "non-empty"),
        ("capability_manifest", "fixed_command_refs", (), "fixed command"),
        ("capability_manifest", "fixed_command_refs", (" ",), "blanks"),
        ("capability_manifest", "fixed_command_refs", ("same", "same"), "unique"),
        ("capability_manifest", "promotion_status", "LIVE", "production"),
        ("capability_manifest", "live_eligibility_status", "LIVE", "live blocked"),
        ("manifest", "runner_id", "", "identity"),
        ("manifest", "audit_root", Path("relative"), "absolute"),
        ("manifest", "universal_enforcement", (), "universal enforcement"),
        (
            "request",
            "requested_capabilities",
            (JobCapability.READ_REPOSITORY,) * 2,
            "unique",
        ),
    ],
)
def test_runner_configuration_rejects_ambiguous_or_unbounded_contracts(
    tmp_path: Path, subject: str, field: str, value: object, message: str
) -> None:
    manifest = local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts")
    subjects = {
        "manifest": manifest,
        "capability_manifest": manifest.capability_manifest,
        "request": _admitted_fixture_request(tmp_path),
    }
    with pytest.raises(ValueError, match=message):
        replace(cast(Any, subjects[subject]), **{field: cast(Any, value)})


@pytest.mark.parametrize(
    ("subject", "field", "value", "message"),
    [
        ("run_card", "run_card_id", "", "identity"),
        ("run_card", "created_at", datetime(2026, 1, 1), "timezone-aware"),
        ("run_card", "target_paths", (Path("relative"),), "absolute"),
        ("run_card", "status", RunnerAdmissionStatus.BLOCKED, "requires blockers"),
        ("run_card", "blockers", ("CONFLICT",), "cannot contain blockers"),
        ("persistent_evidence", "record_id", "", "identity"),
        ("persistent_evidence", "artifact_path", Path("relative"), "absolute"),
        ("audit_record", "event_id", "", "identity"),
        ("audit_record", "event_type", "lower_case", "uppercase"),
        ("audit_record", "event_type", "WITH SPACE", "uppercase"),
        ("report", "runner_id", "", "identity"),
        ("report", "status", RunnerAdmissionStatus.BLOCKED, "requires blockers"),
        ("report", "blockers", ("CONFLICT",), "cannot contain blockers"),
        ("report", "job_id", "another", "job identifiers"),
        ("report", "runner_id", "another", "runner identifiers"),
    ],
)
def test_runner_evidence_rejects_identity_and_status_drift(
    admitted_result: LocalAdvisoryFixtureRunnerResult,
    subject: str,
    field: str,
    value: object,
    message: str,
) -> None:
    report = admitted_result.admission
    record = report if subject == "report" else getattr(report, subject)
    with pytest.raises(ValueError, match=message):
        replace(record, **{field: cast(Any, value)})


def test_runner_rejects_incomplete_capability_effects_and_job_binding(
    tmp_path: Path, admitted_result: LocalAdvisoryFixtureRunnerResult
) -> None:
    manifest = local_advisory_fixture_runner_manifest(tmp_path, tmp_path / "artifacts")
    capabilities = manifest.capability_manifest
    with pytest.raises(ValueError, match="unique"):
        replace(
            capabilities, side_effect_allowlist=capabilities.side_effect_allowlist * 2
        )
    with pytest.raises(ValueError, match="cover every"):
        replace(
            capabilities, side_effect_allowlist=capabilities.side_effect_allowlist[:1]
        )
    with pytest.raises(ValueError, match="must agree"):
        replace(manifest, job_manifest=replace(manifest.job_manifest, job_id="another"))
    request = _admitted_fixture_request(tmp_path)
    with pytest.raises(ValueError, match="side effects must be unique"):
        replace(request, requested_side_effects=request.requested_side_effects * 2)
    with pytest.raises(ValueError, match="requires command_ref"):
        replace(
            admitted_result.admission.run_card,
            requested_capabilities=(JobCapability.RUN_FIXED_QUALITY_COMMANDS,),
            command_ref="",
        )

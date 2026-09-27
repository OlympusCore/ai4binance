"""Compact quality gate telemetry and console evidence helpers."""

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from defusedxml import ElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]

from ai4binance.schema_validation import validate_local_definition

_SENSITIVE_OUTPUT = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|authorization)(\s*[:=]\s*)(\S+)"
)


def _evidence_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            {key: value for key, value in payload.items() if key != "evidence_sha256"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


def _evidence_file(root: Path, reference: object) -> Path:
    if not isinstance(reference, str) or not reference:
        raise ValueError("EVIDENCE_REFERENCE_MISSING")
    path = (root / reference).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("EVIDENCE_REFERENCE_UNAVAILABLE")
    if path.stat().st_size > 20_000_000:
        raise ValueError("EVIDENCE_SIZE_EXCEEDED")
    return path


def _validate_quality_binding(payload: dict[str, object]) -> None:
    """Validate binding fields while retaining the legacy runner's other fields."""
    schema = (
        Path(__file__).resolve().parents[4]
        / "schemas/governance/governed_object_enforcement.schema.json"
    )
    definition = (
        "QualityFailureEvidenceBinding"
        if payload.get("status") == "QUALITY_GATE_FAILED"
        else "QualityEvidenceBinding"
    )
    fields = json.loads(schema.read_text(encoding="utf-8"))["$defs"][definition][
        "properties"
    ]
    validate_local_definition(
        schema,
        definition,
        {key: payload[key] for key in fields if key in payload},
    )


def bind_quality_failure_evidence(
    root: Path,
    payload: dict[str, object],
    *,
    run_id: str,
    workspace_attestation: Mapping[str, object],
) -> dict[str, object]:
    """Bind a failed run without inventing unexecuted JUnit evidence."""
    if payload.get("status") != "QUALITY_GATE_FAILED":
        raise ValueError("QUALITY_FAILURE_STATUS_REQUIRED")
    bound = dict(payload)
    bound.update(
        evidence_contract_version=1,
        run_id=run_id,
        workspace_attestation=dict(workspace_attestation),
        policy_sha256=hashlib.sha256(
            (root / "config/quality/gates.yaml").read_bytes()
        ).hexdigest(),
    )
    bound["evidence_sha256"] = _evidence_digest(bound)
    _validate_quality_binding(bound)
    return bound


def bind_quality_evidence(
    root: Path,
    payload: dict[str, object],
    *,
    run_id: str,
    junit_path: Path,
    workspace_attestation: Mapping[str, object],
) -> dict[str, object]:
    """Bind actual runner output to its subject, policy, test results, and digest."""
    path = _evidence_file(root, str(junit_path))
    raw = path.read_bytes()
    document = ElementTree.fromstring(raw, forbid_dtd=True)
    results = []
    for case in document.iter("testcase"):
        filename = case.get("file", "").replace("\\", "/")
        name = case.get("name", "")
        if not filename or not name:
            raise ValueError("JUNIT_TEST_FILE_MISSING")
        module = filename.removesuffix(".py").replace("/", ".")
        classname = case.get("classname", "")
        qualifier = ""
        if classname.startswith(module + "."):
            qualifier = classname[len(module) + 1 :].replace(".", "::") + "::"
        result = "PASS"
        if case.find("failure") is not None or case.find("error") is not None:
            result = "FAIL"
        elif case.find("skipped") is not None:
            result = "SKIPPED"
        results.append(
            {"node_id": filename + "::" + qualifier + name, "result": result}
        )
    bound = dict(payload)
    bound.update(
        {
            "evidence_contract_version": 1,
            "run_id": run_id,
            "workspace_attestation": dict(workspace_attestation),
            "policy_sha256": hashlib.sha256(
                (root / "config/quality/gates.yaml").read_bytes()
            ).hexdigest(),
            "junit_path": path.relative_to(root.resolve()).as_posix(),
            "junit_sha256": hashlib.sha256(raw).hexdigest(),
            "test_results": results,
        }
    )
    bound["evidence_sha256"] = _evidence_digest(bound)
    _validate_quality_binding(bound)
    return bound


def _failed_quality_evidence_blockers(
    payload: dict[str, object], workspace_attestation: Mapping[str, object]
) -> tuple[str, ...]:
    failures = ["QUALITY_RESULT_FAILED"]
    if payload.get("workspace_attestation") != dict(workspace_attestation):
        failures.append("QUALITY_SUBJECT_MISMATCH")
    if payload.get("evidence_sha256") != _evidence_digest(payload):
        failures.append("QUALITY_EVIDENCE_HASH_MISMATCH")
    return tuple(failures)


def _quality_contract_blockers(payload: dict[str, object]) -> tuple[str, ...]:
    try:
        _validate_quality_binding(payload)
    except (OSError, ValueError):
        if payload.get("status") == "QUALITY_GATE_FAILED":
            return ("QUALITY_RESULT_FAILED", "QUALITY_EVIDENCE_CONTRACT_INVALID")
        return ("QUALITY_EVIDENCE_CONTRACT_INVALID",)
    return ()


def verify_quality_evidence(
    root: Path,
    payload: object,
    *,
    workspace_attestation: Mapping[str, object],
    required_profile: str = "standard",
    required_tests: Iterable[str] = (),
) -> tuple[str, ...]:
    """Verify shared technical evidence; never infer approval from a test pass."""
    if not isinstance(payload, dict):
        return ("QUALITY_EVIDENCE_MISSING",)
    contract_blockers = _quality_contract_blockers(payload)
    if contract_blockers:
        return contract_blockers
    if payload.get("status") == "QUALITY_GATE_FAILED":
        return _failed_quality_evidence_blockers(payload, workspace_attestation)
    blockers: list[str] = []
    ranks = {"fast": 0, "standard": 1, "full": 2}
    profile = payload.get("profile")
    if (
        not isinstance(profile, str)
        or profile not in ranks
        or ranks[profile] < ranks[required_profile]
    ):
        blockers.append("QUALITY_PROFILE_INSUFFICIENT")
    statuses = {
        "fast": "FAST_PROFILE_PASS",
        "standard": "STANDARD_PROFILE_PASS",
        "full": "TECHNICAL_QUALITY_PASS",
    }
    if payload.get("status") != statuses.get(str(profile)):
        blockers.append("QUALITY_RESULT_FAILED")
    if payload.get("verification_status") != f"{str(profile).upper()}_VERIFIED":
        blockers.append("QUALITY_RESULT_NOT_VERIFIED")
    if payload.get("workspace_attestation") != dict(workspace_attestation):
        blockers.append("QUALITY_SUBJECT_MISMATCH")
    if payload.get("evidence_sha256") != _evidence_digest(payload):
        blockers.append("QUALITY_EVIDENCE_HASH_MISMATCH")
    if (
        payload.get("execution_allowed") is not False
        or payload.get("promotion_status") != "RESEARCH_ONLY"
        or payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED"
    ):
        blockers.append("QUALITY_SAFETY_BOUNDARY_INVALID")
    blockers.extend(_quality_file_blockers(root, payload, workspace_attestation))
    blockers.extend(_quality_execution_blockers(payload, required_tests))
    return tuple(dict.fromkeys(blockers))


def _quality_file_blockers(
    root: Path,
    payload: dict[str, object],
    workspace_attestation: Mapping[str, object],
) -> tuple[str, ...]:
    blockers: list[str] = []
    try:
        stamp = datetime.fromisoformat(
            str(payload.get("generated_at_utc", "")).replace("Z", "+00:00")
        )
        now = datetime.now(UTC)
        if stamp.tzinfo is None or stamp > now or now - stamp > timedelta(hours=24):
            blockers.append("QUALITY_EVIDENCE_STALE")
        policy_hash = hashlib.sha256(
            (root / "config/quality/gates.yaml").read_bytes()
        ).hexdigest()
        if payload.get("policy_sha256") != policy_hash:
            blockers.append("QUALITY_POLICY_MISMATCH")
        junit = _evidence_file(root, payload.get("junit_path"))
        if hashlib.sha256(junit.read_bytes()).hexdigest() != payload.get(
            "junit_sha256"
        ):
            blockers.append("QUALITY_TEST_EVIDENCE_MISMATCH")
        rebound = bind_quality_evidence(
            root,
            payload,
            run_id=str(payload.get("run_id", "")),
            junit_path=junit,
            workspace_attestation=workspace_attestation,
        )
        if rebound.get("test_results") != payload.get("test_results"):
            blockers.append("QUALITY_TEST_RESULTS_MISMATCH")
    except (OSError, ValueError, ElementTree.ParseError, DefusedXmlException):
        blockers.append("QUALITY_EVIDENCE_UNREADABLE")
    return tuple(blockers)


def _quality_execution_blockers(
    payload: dict[str, object],
    required_tests: Iterable[str],
) -> tuple[str, ...]:
    profile = payload.get("profile")
    blockers: list[str] = []
    steps = payload.get("step_exit_codes")
    required_steps = {"Ruff format", "Ruff lint", "Ruff maintainability ratchet"}
    if profile == "fast":
        required_steps.update({"dmypy", "Pytest affected"})
    else:
        required_steps.update({"MyPy", "Repository governance validator"})
        required_steps.add("Pytest" if profile == "full" else "Pytest required")
    if (
        not isinstance(steps, dict)
        or not steps
        or not required_steps.issubset(steps)
        or any(
            type(steps.get(step)) is not int or steps[step] != 0
            for step in required_steps
        )
        or any(
            type(code) is not int
            or (
                code != 0
                and not (name == "Deterministic governance gate" and code == 2)
            )
            for name, code in steps.items()
        )
    ):
        blockers.append("QUALITY_STEP_FAILED_OR_MISSING")
    results = payload.get("test_results")
    if (
        not isinstance(results, list)
        or not results
        or any(
            not isinstance(item, dict) or item.get("result") not in {"PASS", "SKIPPED"}
            for item in results
        )
    ):
        blockers.append("QUALITY_TEST_EXECUTION_UNPROVEN")
    else:
        passed = {
            str(item.get("node_id", ""))
            for item in results
            if item.get("result") == "PASS"
        }
        for test in required_tests:
            if not any(
                node == test or node.startswith((test + "::", test + "["))
                for node in passed
            ):
                blockers.append(f"QUALITY_REQUIRED_TEST_NOT_EXECUTED:{test}")
    return tuple(dict.fromkeys(blockers))


def quality_completion_blockers(
    root: Path,
    workspace_attestation: Mapping[str, object],
) -> tuple[str, ...]:
    """Resolve required scope and verify the canonical runner's current result."""
    from ai4binance.ops.quality_gate.policy import (
        AffectedScopeResolutionError,
        changed_repository_paths,
        load_quality_gate_policy,
        resolve_standard_pytest_arguments,
    )

    try:
        policy = load_quality_gate_policy(root / "config/quality/gates.yaml")
        profile = "standard"
        try:
            tests = tuple(
                item
                for item in resolve_standard_pytest_arguments(
                    policy,
                    root,
                    changed_repository_paths(root),
                )
                if not item.startswith("-")
            )
        except AffectedScopeResolutionError:
            profile = "full"
            tests = policy.required_tests
        payload = json.loads(
            (root / "runtime/artifacts/quality/gate/latest.json").read_text(
                encoding="utf-8-sig"
            )
        )
    except (OSError, ValueError):
        return ("QUALITY_EVIDENCE_OR_POLICY_UNAVAILABLE",)
    return verify_quality_evidence(
        root,
        payload,
        workspace_attestation=workspace_attestation,
        required_profile=profile,
        required_tests=tests,
    )


@dataclass(frozen=True, slots=True)
class QualityStepTelemetry:
    """Bounded telemetry for one quality gate step."""

    step_id: str
    name: str
    started_at_utc: datetime
    ended_at_utc: datetime
    wall_time_ms: int
    exit_code: int | None
    status: str
    artifact_path: str = ""
    output_sha256: str = ""
    first_actionable_error: str = ""
    output_tail: str = ""
    output_truncated: bool = False


def first_actionable_error(output: str, *, max_characters: int = 500) -> str:
    """Return the first useful failure line without leaking sensitive values."""
    sanitized = sanitize_quality_output(output)
    for line in sanitized.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if (
            "error" in lowered
            or "failed" in lowered
            or "traceback" in lowered
            or "assertionerror" in lowered
        ):
            return stripped[:max_characters]
    return sanitized.strip()[:max_characters]


def sanitize_quality_output(output: str) -> str:
    """Redact common secret-like tokens from quality tool output."""
    return _SENSITIVE_OUTPUT.sub(r"\1\2[REDACTED]", output)


def output_sha256(output: str) -> str:
    """Return a SHA-256 digest for sanitized output."""
    return hashlib.sha256(sanitize_quality_output(output).encode("utf-8")).hexdigest()


def build_compact_quality_console_summary(
    *,
    status: str,
    profile: str,
    run_id: str,
    duration_ms: int,
    selected_test_count: int,
    evidence_path: str,
    steps: Iterable[Mapping[str, object]],
    error: str | None = None,
) -> dict[str, object]:
    """Build the governed, token-bounded terminal summary for a gate run."""
    if selected_test_count < 0:
        raise ValueError("selected_test_count must be non-negative")

    material_steps = tuple(steps)
    normalized_status = status.strip().upper()
    run_passed = normalized_status in {"PASS", "PASSED"} or normalized_status.endswith(
        "_PASS"
    )
    if not run_passed:
        failed_step = next(
            (
                step
                for step in material_steps
                if str(step.get("status", "")).upper() not in {"PASS", "PASSED"}
            ),
            {},
        )
        actionable_error = str(failed_step.get("first_actionable_error", "")).strip()
        if actionable_error:
            actionable_error = first_actionable_error(actionable_error)
        if not actionable_error:
            actionable_error = first_actionable_error(error or "")
        if not actionable_error:
            actionable_error = "Quality gate failed; inspect evidence."
        return {
            "failed_step": failed_step.get("step_id", ""),
            "exit_code": failed_step.get("exit_code"),
            "first_actionable_error": actionable_error,
            "evidence_path": evidence_path,
        }

    tools = tuple(
        dict.fromkeys(
            step_id
            for step in material_steps
            if (step_id := str(step.get("step_id", "")).strip())
        )
    )
    return {
        "profile": profile,
        "run_id": run_id,
        "status": status,
        "duration": duration_ms,
        "tools": tools,
        "selected_test_count": selected_test_count,
        "evidence_path": evidence_path,
    }

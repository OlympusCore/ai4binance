"""Enterprise holding-governance CLI adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from ai4binance.cli.commands import available_command_names
from ai4binance.cli.output import render_payload
from ai4binance.enterprise.contracts import WorkflowIdentity
from ai4binance.enterprise.departments import build_default_department_registry
from ai4binance.enterprise.executive import GeneralManagerController
from ai4binance.enterprise.quality_audit import (
    QualitySystemAuditEvidence,
    run_quality_system_audit,
)
from ai4binance.ops.repository_cleanup_audit import run_repository_cleanup_audit
from ai4binance.reporting import to_primitive

_MAX_PROMPT_BYTES = 16_000


def run_enterprise_intake(
    *,
    prompt_file: str | None,
    output_format: str,
) -> int:
    if prompt_file is None or not prompt_file.strip():
        _print_payload(
            _blocked_payload(("ENTERPRISE_PROMPT_FILE_REQUIRED",)),
            output_format=output_format,
        )
        return 2

    prompt_path = Path(prompt_file)
    try:
        if prompt_path.stat().st_size > _MAX_PROMPT_BYTES:
            _print_payload(
                _blocked_payload(("ENTERPRISE_PROMPT_FILE_TOO_LARGE",)),
                output_format=output_format,
            )
            return 2
        raw_prompt = prompt_path.read_text(encoding="utf-8")
    except OSError:
        _print_payload(
            _blocked_payload(("ENTERPRISE_PROMPT_FILE_UNAVAILABLE",)),
            output_format=output_format,
        )
        return 2

    try:
        payload = enterprise_intake_payload(raw_prompt)
    except ValueError:
        _print_payload(
            _blocked_payload(("ENTERPRISE_PROMPT_INTAKE_REJECTED",)),
            output_format=output_format,
        )
        return 2
    _print_payload(payload, output_format=output_format)
    return 0


def run_quality_system_audit_command(*, output_format: str) -> int:
    payload = quality_system_audit_payload()
    _print_payload(payload, output_format=output_format, command="quality-system-audit")
    return 0 if not payload["blockers"] else 2


def run_repository_cleanup_audit_command(*, output_format: str) -> int:
    payload = repository_cleanup_audit_payload()
    _print_payload(
        payload,
        output_format=output_format,
        command="repository-cleanup-audit",
    )
    return 0


def enterprise_intake_payload(raw_prompt: str) -> dict[str, object]:
    now = datetime.now(UTC)
    run_suffix = uuid4().hex[:12]
    identity = WorkflowIdentity(
        work_order_id=f"wo:enterprise-intake:{run_suffix}",
        run_id=f"run:enterprise-intake:{run_suffix}",
        trace_id=f"trace:enterprise-intake:{run_suffix}",
        created_at=now,
    )
    controller = GeneralManagerController(build_default_department_registry())
    intake = controller.intake_prompt(
        identity=identity,
        prompt_id=f"prompt:{run_suffix}",
        submitted_by="codex-user",
        raw_prompt=raw_prompt,
    )
    directive = intake.to_board_directive(
        directive_id=f"directive:{run_suffix}",
        resource_budget="cpu-light",
        time_budget_seconds=600,
    )
    primitive_intake = to_primitive(intake)
    if not isinstance(primitive_intake, dict):
        raise RuntimeError("ENTERPRISE_PROMPT_INTAKE_PAYLOAD_INVALID")
    primitive_directive = to_primitive(directive)
    if not isinstance(primitive_directive, dict):
        raise RuntimeError("ENTERPRISE_DIRECTIVE_PAYLOAD_INVALID")
    intake_payload = cast(dict[str, object], primitive_intake)
    directive_payload = cast(dict[str, object], primitive_directive)
    return {
        "command": "enterprise-intake",
        "status": "READY_FOR_GENERAL_MANAGER_REVIEW",
        "prompt": {
            "prompt_id": intake_payload["prompt_id"],
            "raw_prompt_ref": intake_payload["raw_prompt_ref"],
            "raw_prompt_sha256": intake_payload["raw_prompt_sha256"],
            "sanitized_summary": intake_payload["sanitized_summary"],
            "raw_prompt_visibility": intake_payload["raw_prompt_visibility"],
            "department_visibility": intake_payload["department_visibility"],
        },
        "directive": directive_payload,
        "blockers": (
            "HUMAN_REVIEW_REQUIRED",
            "LIVE_ORDER_BLOCKED",
        ),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def quality_system_audit_payload() -> dict[str, object]:
    report = run_quality_system_audit(
        QualitySystemAuditEvidence(
            workspace_root=Path.cwd(),
            command_names=available_command_names(),
            observed_at=datetime.now(UTC),
        )
    )
    payload = to_primitive(report)
    if not isinstance(payload, dict):
        raise RuntimeError("QUALITY_SYSTEM_AUDIT_PAYLOAD_INVALID")
    report_payload = cast(dict[str, object], payload)
    return {
        "command": "quality-system-audit",
        "status": report_payload["status"],
        "report": report_payload,
        "blockers": report_payload["blockers"],
        "corrective_actions": report_payload["corrective_actions"],
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def repository_cleanup_audit_payload() -> dict[str, object]:
    report = run_repository_cleanup_audit(Path.cwd())
    payload = to_primitive(report)
    if not isinstance(payload, dict):
        raise RuntimeError("REPOSITORY_CLEANUP_AUDIT_PAYLOAD_INVALID")
    report_payload = cast(dict[str, object], payload)
    return {
        "command": "repository-cleanup-audit",
        "status": report_payload["status"],
        "report": report_payload,
        "blockers": (),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _blocked_payload(blockers: tuple[str, ...]) -> dict[str, object]:
    return {
        "command": "enterprise-intake",
        "status": "BLOCKED",
        "blockers": blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _print_payload(
    payload: dict[str, object],
    *,
    output_format: str,
    command: str = "enterprise-intake",
) -> None:
    print(
        render_payload(
            payload,
            output_format=output_format,
            command=command,
        )
    )

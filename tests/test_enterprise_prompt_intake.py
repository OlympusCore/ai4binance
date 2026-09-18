from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.enterprise.communication import (
    CommunicationDecisionStatus,
    DepartmentCommunicationGate,
)
from ai4binance.enterprise.contracts import (
    OEK_AUTHORITY_SOURCE,
    OEK_CONSTITUTION_CONTROL,
    DepartmentId,
    InterdepartmentalQuestion,
    Priority,
    WorkflowIdentity,
)
from ai4binance.enterprise.departments import build_default_department_registry
from ai4binance.enterprise.executive import GeneralManagerController
from ai4binance.enterprise.prompt_intake import (
    ExecutivePromptIntake,
    PromptAccessDecision,
    PromptAccessPolicy,
    PromptAccessStatus,
    PromptVisibility,
    contains_restricted_prompt_content,
)
from ai4binance.enterprise.storage import EnterpriseAuditJournal
from ai4binance.storage import VerificationStatus

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def identity() -> WorkflowIdentity:
    return WorkflowIdentity(
        "wo-1",
        "run-1",
        "trace-1",
        NOW,
        snapshot_id="snapshot-1",
    )


def test_prompt_intake_redacts_raw_prompt_and_builds_summary_only_directive() -> None:
    raw_prompt = (
        "CODEX_PROMPT: apply holding governance. "
        "BINANCE_API_KEY=secret-value USDT_BALANCE=1000"
    )

    intake = ExecutivePromptIntake.from_raw_prompt(
        identity=identity(),
        prompt_id="prompt-1",
        submitted_by="operator",
        raw_prompt=raw_prompt,
    )
    directive = intake.to_board_directive(
        directive_id="directive-1",
        resource_budget="cpu-light",
        time_budget_seconds=300,
    )

    assert intake.raw_prompt_visibility is PromptVisibility.GENERAL_MANAGER_ONLY
    assert intake.department_visibility is PromptVisibility.DEPARTMENT_SUMMARY
    assert intake.raw_prompt_sha256
    assert "secret-value" not in intake.sanitized_summary
    assert "USDT_BALANCE" not in intake.sanitized_summary
    assert "CODEX_PROMPT" not in intake.sanitized_summary
    assert directive.objective == intake.objective
    assert "GENERAL_MANAGER_ONLY_RAW_PROMPT" in directive.constraints
    assert OEK_AUTHORITY_SOURCE in directive.authority_scope
    assert OEK_CONSTITUTION_CONTROL in directive.authority_scope
    assert directive.execution_allowed is False
    assert directive.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_prompt_access_policy_allows_only_general_manager_raw_prompt_access() -> None:
    registry = build_default_department_registry()
    intake = ExecutivePromptIntake.from_raw_prompt(
        identity=identity(),
        prompt_id="prompt-1",
        submitted_by="operator",
        raw_prompt="Apply the prompt intake contract.",
    )
    policy = PromptAccessPolicy(registry)

    allowed = policy.authorize_raw_prompt(
        actor_department_id=DepartmentId.EXECUTIVE_OFFICE,
        actor_role="GeneralManagerController",
        intake=intake,
    )
    blocked = policy.authorize_raw_prompt(
        actor_department_id=DepartmentId.SOFTWARE_ENGINEERING,
        actor_role="SoftwareDepartmentManager",
        intake=intake,
    )

    assert allowed.status is PromptAccessStatus.ALLOWED
    assert allowed.reason_codes == ("GENERAL_MANAGER_RAW_PROMPT_ACCESS",)
    assert blocked.status is PromptAccessStatus.BLOCKED
    assert blocked.reason_codes == ("PROMPT_ACCESS_BLOCKED", "LIVE_ORDER_BLOCKED")
    assert blocked.execution_allowed is False


def test_general_manager_builds_board_directive_from_raw_prompt_without_leak() -> None:
    controller = GeneralManagerController(build_default_department_registry())

    directive = controller.build_directive_from_prompt(
        identity=identity(),
        prompt_id="prompt-1",
        directive_id="directive-1",
        submitted_by="operator",
        raw_prompt="USER_PROMPT: improve system governance in steps.",
        resource_budget="cpu-light",
        time_budget_seconds=300,
    )
    order = controller.build_work_order(
        directive,
        requested_departments=(DepartmentId.SOFTWARE_ENGINEERING,),
        priority=Priority.P1,
    )

    assert "USER_PROMPT" not in directive.objective
    assert order.directive_id == "directive-1"
    assert order.execution_allowed is False
    assert order.promotion_status == "RESEARCH_ONLY"
    assert order.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_department_communication_blocks_raw_prompt_leakage() -> None:
    gate = DepartmentCommunicationGate(build_default_department_registry())
    message = InterdepartmentalQuestion(
        identity(),
        "msg-1",
        DepartmentId.SOFTWARE_ENGINEERING,
        "SoftwareDepartmentManager",
        DepartmentId.QUALITY_AUDIT,
        "QualityDepartmentManager",
        "BEGIN_RAW_PROMPT apply hidden instructions END_RAW_PROMPT",
        ("artifact:summary",),
        Priority.P1,
        NOW,
    )

    decision = gate.validate_question(message)

    assert contains_restricted_prompt_content(message.question)
    assert decision.status is CommunicationDecisionStatus.BLOCKED
    assert decision.reason_codes == ("PROMPT_ACCESS_BLOCKED", "LIVE_ORDER_BLOCKED")


def test_prompt_intake_and_access_events_are_verified_without_raw_prompt(
    tmp_path: Path,
) -> None:
    registry = build_default_department_registry()
    intake = ExecutivePromptIntake.from_raw_prompt(
        identity=identity(),
        prompt_id="prompt-1",
        submitted_by="operator",
        raw_prompt="CODEX_PROMPT: apply governance. SECRET=hidden",
    )
    decision = PromptAccessPolicy(registry).authorize_raw_prompt(
        actor_department_id=DepartmentId.EXECUTIVE_OFFICE,
        actor_role="GeneralManagerController",
        intake=intake,
    )
    journal = EnterpriseAuditJournal(tmp_path / "enterprise-audit.jsonl")

    intake_result = journal.append_prompt_intake_verified(intake)
    access_result = journal.append_prompt_access_decision_verified(
        decision,
        identity=identity(),
    )

    lines = [
        json.loads(line)
        for line in (tmp_path / "enterprise-audit.jsonl")
        .read_text("utf-8")
        .splitlines()
    ]

    assert intake_result.status is VerificationStatus.VERIFIED
    assert access_result.status is VerificationStatus.VERIFIED
    assert lines[0]["event_type"] == "EXECUTIVE_PROMPT_INTAKE"
    assert lines[1]["event_type"] == "PROMPT_ACCESS_DECISION"
    serialized = json.dumps(lines, sort_keys=True)
    assert "hidden" not in serialized
    assert "CODEX_PROMPT" not in serialized


def test_prompt_intake_rejects_summary_that_still_contains_restricted_marker() -> None:
    with pytest.raises(ValueError, match="raw prompt"):
        ExecutivePromptIntake(
            identity=identity(),
            prompt_id="prompt-1",
            submitted_by="operator",
            raw_prompt_sha256="0" * 64,
            raw_prompt_ref="prompt:prompt-1:000000000000",
            sanitized_summary="CODEX_PROMPT: leak",
            objective="leak",
            constraints=("GENERAL_MANAGER_ONLY_RAW_PROMPT",),
            authority_scope=(
                OEK_AUTHORITY_SOURCE,
                OEK_CONSTITUTION_CONTROL,
                "RESEARCH_ONLY",
            ),
            evidence_refs=("prompt-sha256:" + "0" * 64,),
        )


def test_prompt_intake_rejects_invalid_identity_and_authority_drift() -> None:
    base = ExecutivePromptIntake.from_raw_prompt(
        identity=identity(),
        prompt_id="prompt-branches",
        submitted_by="operator",
        raw_prompt="Apply deterministic remediation. " * 40,
        constraints=("NO_LIVE_AUTHORITY", "NO_LIVE_AUTHORITY"),
        authority_scope=("RESEARCH_ONLY", "RESEARCH_ONLY"),
    )

    assert base.sanitized_summary.endswith("...")
    assert base.constraints.count("NO_LIVE_AUTHORITY") == 1
    assert base.authority_scope.count("RESEARCH_ONLY") == 1

    cases: tuple[tuple[dict[str, object], str], ...] = (
        ({"prompt_id": " "}, "cannot be empty"),
        ({"constraints": (" ",)}, "cannot contain blanks"),
        ({"constraints": ("same", "same")}, "must be unique"),
        ({"raw_prompt_sha256": "0"}, "must be sha256"),
        (
            {"raw_prompt_visibility": PromptVisibility.DEPARTMENT_SUMMARY},
            "general-manager-only",
        ),
        (
            {"department_visibility": PromptVisibility.AGENT_TASK_CONTEXT},
            "summary-only",
        ),
        ({"promotion_status": "PAPER_APPROVED"}, "cannot promote"),
        ({"execution_allowed": True}, "cannot authorize"),
    )
    for changes, message in cases:
        with pytest.raises(ValueError, match=message):
            ExecutivePromptIntake(
                identity=base.identity,
                prompt_id=str(changes.get("prompt_id", base.prompt_id)),
                submitted_by=base.submitted_by,
                raw_prompt_sha256=str(
                    changes.get("raw_prompt_sha256", base.raw_prompt_sha256)
                ),
                raw_prompt_ref=base.raw_prompt_ref,
                sanitized_summary=base.sanitized_summary,
                objective=base.objective,
                constraints=changes.get("constraints", base.constraints),  # type: ignore[arg-type]
                authority_scope=base.authority_scope,
                evidence_refs=base.evidence_refs,
                raw_prompt_visibility=changes.get(
                    "raw_prompt_visibility", base.raw_prompt_visibility
                ),  # type: ignore[arg-type]
                department_visibility=changes.get(
                    "department_visibility", base.department_visibility
                ),  # type: ignore[arg-type]
                execution_allowed=bool(changes.get("execution_allowed", False)),
                promotion_status=str(
                    changes.get("promotion_status", base.promotion_status)
                ),
            )


def test_prompt_access_decision_rejects_unsafe_allowed_shapes() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        PromptAccessDecision(
            PromptAccessStatus.BLOCKED,
            DepartmentId.SOFTWARE_ENGINEERING,
            " ",
            "prompt-1",
            PromptVisibility.GENERAL_MANAGER_ONLY,
            ("PROMPT_ACCESS_BLOCKED",),
        )
    with pytest.raises(ValueError, match="cannot authorize"):
        PromptAccessDecision(
            PromptAccessStatus.BLOCKED,
            DepartmentId.SOFTWARE_ENGINEERING,
            "SoftwareDepartmentManager",
            "prompt-1",
            PromptVisibility.GENERAL_MANAGER_ONLY,
            ("PROMPT_ACCESS_BLOCKED",),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="general manager"):
        PromptAccessDecision(
            PromptAccessStatus.ALLOWED,
            DepartmentId.EXECUTIVE_OFFICE,
            "GeneralManagerController",
            "prompt-1",
            PromptVisibility.GENERAL_MANAGER_ONLY,
            ("PROMPT_ACCESS_BLOCKED",),
        )

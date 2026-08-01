from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai4binance.enterprise.context_contracts import (
    ContextLayerId,
    build_department_context_packet,
)
from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity
from ai4binance.enterprise.prompt_intake import ExecutivePromptIntake

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def intake() -> ExecutivePromptIntake:
    return ExecutivePromptIntake.from_raw_prompt(
        identity=WorkflowIdentity("wo-1", "run-1", "trace-1", NOW),
        prompt_id="prompt-1",
        submitted_by="user",
        raw_prompt="CODEX_PROMPT: improve system with SECRET=hidden",
    )


def test_department_context_packet_excludes_raw_prompt_content() -> None:
    packet = build_department_context_packet(
        intake=intake(),
        department_id=DepartmentId.SOFTWARE_ENGINEERING,
        task_requirements=("Implement tests", "Preserve audit trail"),
        output_contract="Return changed files and validation status.",
    )

    assert packet.department_id is DepartmentId.SOFTWARE_ENGINEERING
    assert "SECRET" not in packet.sanitized_objective
    assert "RAW_PROMPT_NOT_INCLUDED" in packet.constraints
    assert {layer.layer_id for layer in packet.layers} == {
        ContextLayerId.SYSTEM,
        ContextLayerId.DOMAIN,
        ContextLayerId.TASK,
        ContextLayerId.RESPONSE,
    }
    assert packet.execution_allowed is False
    assert packet.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_department_context_packet_rejects_raw_prompt_markers() -> None:
    with pytest.raises(ValueError, match="restricted prompt content"):
        build_department_context_packet(
            intake=intake(),
            department_id=DepartmentId.QUALITY_AUDIT,
            task_requirements=("BEGIN_RAW_PROMPT leak END_RAW_PROMPT",),
            output_contract="Return audit.",
        )

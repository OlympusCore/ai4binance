"""Modern AI agent stack governance audit tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai4binance.enterprise.agent_stack import (
    AgentStackAuditReport,
    AgentStackAuditStatus,
    AgentStackLayerCheck,
    modern_agent_stack_requirements,
    run_agent_stack_audit,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def create_agent_stack_root(tmp_path: Path) -> Path:
    for requirement in modern_agent_stack_requirements():
        for relative_path in requirement.required_paths:
            path = tmp_path / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("RESEARCH_ONLY\nLIVE_ORDER_BLOCKED\n", encoding="utf-8")
    return tmp_path


def command_names() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            command
            for requirement in modern_agent_stack_requirements()
            for command in requirement.required_commands
        )
    )


def test_agent_stack_audit_passes_complete_governed_stack(tmp_path: Path) -> None:
    report = run_agent_stack_audit(
        create_agent_stack_root(tmp_path),
        command_names(),
        NOW,
    )

    assert report.status is AgentStackAuditStatus.PASSED
    assert report.blockers == ()
    assert len(report.layers) == len(modern_agent_stack_requirements())
    assert {layer.layer_id for layer in report.layers} >= {
        "RAG",
        "MCP",
        "HOOKS",
        "EVAL",
        "GOVERNANCE_AUTHORITY",
        "DETERMINISTIC_CORE",
        "SECURITY_SANDBOX",
        "OBSERVABILITY_AUDIT",
        "DATA_PROVENANCE",
    }
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_agent_stack_audit_blocks_missing_path_and_command(tmp_path: Path) -> None:
    root = create_agent_stack_root(tmp_path)
    (root / "src" / "ai4binance" / "rag.py").unlink()

    report = run_agent_stack_audit(root, ("second-brain",), NOW)

    assert report.status is AgentStackAuditStatus.REVISION_REQUIRED
    assert "AGENT_STACK_PATH_MISSING:RAG:src/ai4binance/rag.py" in report.blockers
    assert "AGENT_STACK_COMMAND_MISSING:AGENT:agents" in report.blockers
    rag = next(layer for layer in report.layers if layer.layer_id == "RAG")
    assert rag.passed is False
    assert "control:RAG_CITATION_REQUIRED" in rag.evidence_refs


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"audit_id": ""}, "audit id"),
        ({"layers": ()}, "requires layer checks"),
        ({"blockers": ("DUP", "DUP")}, "blockers"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"promotion_status": "STAGED_CANDIDATE"}, "cannot promote"),
        ({"live_eligibility_status": "LIVE_ELIGIBLE"}, "must remain live blocked"),
    ],
)
def test_agent_stack_audit_rejects_shape_or_authority_drift(
    kwargs: dict[str, object],
    message: str,
) -> None:
    check = AgentStackLayerCheck(
        layer_id="RAG",
        purpose="retrieval",
        passed=True,
        evidence_refs=("path:src/ai4binance/rag.py",),
    )
    values: dict[str, object] = {
        "audit_id": "agent-stack-audit:test",
        "observed_at": NOW,
        "status": AgentStackAuditStatus.PASSED,
        "layers": (check,),
        "blockers": (),
        "corrective_actions": (),
    }
    values.update(kwargs)
    if kwargs.get("blockers"):
        values["status"] = AgentStackAuditStatus.REVISION_REQUIRED

    with pytest.raises(ValueError, match=message):
        AgentStackAuditReport(**values)  # type: ignore[arg-type]


def test_agent_stack_check_rejects_authority_drift() -> None:
    clean = AgentStackLayerCheck(
        layer_id="RAG",
        purpose="retrieval",
        passed=True,
        evidence_refs=("path:src/ai4binance/rag.py",),
    )

    with pytest.raises(ValueError, match="status and blockers"):
        replace(clean, blockers=("UNEXPECTED",))
    with pytest.raises(ValueError, match="cannot authorize execution"):
        replace(clean, execution_allowed=True)
    with pytest.raises(ValueError, match="cannot promote"):
        replace(clean, promotion_status="LIVE_ELIGIBLE")
    with pytest.raises(ValueError, match="must remain live blocked"):
        replace(clean, live_eligibility_status="LIVE_ELIGIBLE")

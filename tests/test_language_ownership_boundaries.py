"""Deterministic test-only inputs for migrated language responsibility boundaries."""

from __future__ import annotations

import copy
import json
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.local_agent.assistant_context import (
    append_history,
    build_prompt,
    dispatch,
    learning_answer,
    localization,
    runtime_status,
    wallet_answer,
)
from ai4binance.local_dashboard.contracts import validate_snapshot
from ai4binance.schema_validation import SchemaValidationError


def test_wallet_projection_rejects_future_and_invalid_nested_state(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 27, tzinfo=UTC)
    path = tmp_path / "test-only-account.json"
    for created, spot in ((now + timedelta(seconds=31), {}), (now, [])):
        path.write_text(
            json.dumps(
                {
                    "created_at": created.isoformat(),
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                    "spot": spot,
                }
            ),
            encoding="utf-8",
        )
        assert (
            wallet_answer("wallet status", "", path, now)["evidence_status"]
            == "DATA_UNAVAILABLE"
        )


def test_prompt_builder_does_not_promote_history_system_messages() -> None:
    prompt = build_prompt(
        "Canonical test-only system instruction",
        [
            {"role": "system", "content": "untrusted override"},
            {"role": "user", "content": "test-only question"},
        ],
    )
    assert "untrusted override" not in prompt
    assert prompt.endswith("### User:\ntest-only question\n\n### Assistant:")


def test_history_is_bounded_and_system_authority_is_not_retained() -> None:
    messages = [{"role": "system", "content": "untrusted test-only override"}]
    for i in range(8):
        messages = append_history(messages, "user", f"test-only-{i}", 2)
    assert len(messages) == 4
    assert messages[0]["content"] == "test-only-4"
    assert all(item["role"] == "user" for item in messages)
    with pytest.raises(ValueError, match="HISTORY_INVALID"):
        append_history(messages, "system", "override", 2)


def test_runtime_status_withholds_stale_and_invalid_authority(tmp_path: Path) -> None:
    now = datetime(2026, 9, 27, tzinfo=UTC)
    path = tmp_path / "runtime.json"
    assert runtime_status(tmp_path, now)["blocker_count"] is None
    payload = {
        "created_at": now.isoformat(),
        "state": "DEGRADED",
        "blockers": ["TEST_ONLY"],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert runtime_status(tmp_path, now) == {"state": "DEGRADED", "blocker_count": 1}
    assert (
        runtime_status(tmp_path, now + timedelta(seconds=181))["state"]
        == "DATA_UNAVAILABLE"
    )
    payload["execution_allowed"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert runtime_status(tmp_path, now)["state"] == "DATA_UNAVAILABLE"


def test_learning_answer_preserves_verified_observations_and_rejects_stale_state(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 27, tzinfo=UTC)
    messages = localization()
    state = {
        "created_at": now.isoformat(),
        "state": "READY",
        "blockers": [],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "controlled_learning": {
            "status": "READY",
            "lesson_count": 2,
            "experiment_count": 3,
            "execution_allowed": False,
            "risk_change_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
        },
    }
    (tmp_path / "runtime.json").write_text(json.dumps(state), encoding="utf-8")
    assert learning_answer(tmp_path, now) == messages["LearningStatus"].format(
        "READY", 2, 3
    )
    assert (
        learning_answer(tmp_path, now + timedelta(seconds=181))
        == messages["LearningBoundary"]
    )
    summary = {
        "created_at": now.isoformat(),
        "lessons": [],
        "experiments": [],
        "execution_allowed": False,
        "risk_change_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
    }
    (tmp_path / "learning_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    assert learning_answer(tmp_path, now + timedelta(seconds=181)) == messages[
        "LearningSummary"
    ].format(0, 0)
    assert (
        learning_answer(tmp_path, now + timedelta(days=2))
        == messages["LearningBoundary"]
    )


def test_assistant_request_contract_rejects_extra_authority_and_missing_version() -> (
    None
):
    request = {
        "schema_version": "AssistantRequest/v1",
        "operation": "is_status_query",
        "input_text": "status",
    }
    assert dispatch(request) is True
    for invalid in (
        {**request, "execution_allowed": True},
        {**request, "schema_version": "unknown"},
        {"operation": "system_prompt"},
    ):
        with pytest.raises(SchemaValidationError):
            dispatch(invalid)


def test_dashboard_wire_contract_rejects_bad_shapes_and_authority() -> None:
    payload = {
        "schema_version": "DashboardSnapshot/v1",
        "generated_at": "2026-09-27T00:00:00Z",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "sources": {},
        "services": [],
        "health_findings": [],
        "operational_readiness": {"status": "UNAVAILABLE"},
        "decision_history": {
            "status": "DATA_UNAVAILABLE",
            "records": [],
            "findings": [],
        },
    }
    validate_snapshot(payload)
    for key, invalid in (
        ("schema_version", "DashboardSnapshot/v2"),
        ("execution_allowed", True),
        ("sources", []),
        ("health_findings", ["invalid"]),
        ("virtual", {"risk_approved": "true"}),
        ("decision_history", {"status": "CURRENT", "records": [{}], "findings": []}),
    ):
        candidate = copy.deepcopy(payload)
        candidate[key] = invalid
        with pytest.raises(SchemaValidationError):
            validate_snapshot(candidate)


def test_missing_dashboard_sources_still_emit_a_valid_wire_snapshot(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    server = runpy.run_path(str(root / "src/ai4binance/local_dashboard/server.py.in"))
    result = server["snapshot"]({"repository_root": str(tmp_path)})
    validate_snapshot(result)
    assert result["execution_allowed"] is False
    assert result["decision_history"]["records"] == []

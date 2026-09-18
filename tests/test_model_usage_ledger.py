"""Observe-only Codex model_usage ledger tests."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.multiops.llmops import (
    BudgetStatus,
    ModelTier,
    ModelUsageLedger,
    ModelUsageRecord,
    ReasoningEffort,
    TaskClass,
    TaskCriticality,
    TokenAccountingSource,
    default_model_usage_path,
    unavailable_usage_record,
)

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


def exact_record() -> ModelUsageRecord:
    return ModelUsageRecord(
        task_id="task-model_governance-1",
        timestamp=NOW,
        task_type="normal_feature",
        task_class=TaskClass.MODERATE,
        criticality=TaskCriticality.MEDIUM,
        token_accounting_source=TokenAccountingSource.EXACT_PROVIDER,
        sanitized_summary="Typed observe-only governance fixture.",
        model_id="provider-model-id",
        model_tier=ModelTier.BALANCED,
        reasoning_effort=ReasoningEffort.MEDIUM,
        input_tokens=100,
        cached_input_tokens=25,
        output_tokens=20,
        reasoning_tokens=5,
        total_tokens=120,
        estimated_cost_usd=Decimal("0.0012"),
        actual_cost_usd=Decimal("0.0011"),
        context_files=3,
        context_bytes=2048,
        tool_calls=2,
        quality_result="PASS",
        tests_passed=True,
        budget_status=BudgetStatus.WITHIN_BUDGET,
        human_approval="APPROVED_PHASE_0",
        files_modified=("src/example.py",),
        prompt_hash="a" * 64,
        routing_policy_version="policy-v1",
        pricing_version="pricing-v1",
        model_registry_version="registry-v1",
        task_classifier_version="classifier-v1",
    )


def test_model_usage_ledger_preserves_counts_and_fail_closed_authority(
    tmp_path: Path,
) -> None:
    path = tmp_path / "model_usage.jsonl"
    result = ModelUsageLedger(path).append(exact_record())

    assert result.subject_id == "task-model_governance-1"
    event = json.loads(path.read_text(encoding="utf-8"))
    payload = event["payload"]
    assert payload["input_tokens"] == 100
    assert payload["cached_input_tokens"] == 25
    assert payload["token_accounting_source"] == "EXACT_PROVIDER"  # noqa: S105
    assert payload["actual_cost_usd"] == "0.0011"
    assert payload["execution_allowed"] is False
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"
    assert ModelUsageLedger(path).read_recent() == (payload,)


def test_unavailable_usage_does_not_invent_tokens_or_cost() -> None:
    record = unavailable_usage_record(
        task_id="task-no-provider-data",
        task_type="repository_discovery",
        task_class=TaskClass.LOW,
        criticality=TaskCriticality.LOW,
        sanitized_summary="Provider counters were not exposed.",
    )

    assert record.token_accounting_source is TokenAccountingSource.UNAVAILABLE
    assert record.input_tokens is None
    assert record.total_tokens is None
    assert record.actual_cost_usd is None
    assert record.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_model_usage_contract_rejects_false_or_unsafe_accounting() -> None:
    with pytest.raises(ValueError, match="unavailable token accounting"):
        replace(
            exact_record(),
            token_accounting_source=TokenAccountingSource.UNAVAILABLE,
        )
    with pytest.raises(ValueError, match="exact provider accounting"):
        replace(
            exact_record(),
            token_accounting_source=TokenAccountingSource.ESTIMATED,
        )
    with pytest.raises(ValueError, match="cannot authorize"):
        replace(exact_record(), execution_allowed=True)
    with pytest.raises(ValueError, match="cached input"):
        replace(exact_record(), cached_input_tokens=101)
    with pytest.raises(ValueError, match="requires core token counters"):
        replace(exact_record(), input_tokens=None)
    with pytest.raises(ValueError, match="secret-like"):
        replace(exact_record(), sanitized_summary="authorization: Bearer hidden")


def test_model_usage_ledger_rejects_unrelated_events(tmp_path: Path) -> None:
    path = tmp_path / "model_usage.jsonl"
    path.write_text(
        json.dumps({"event_type": "OTHER_EVENT", "payload": {}}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="event type"):
        ModelUsageLedger(path).read_recent()


def test_default_model_usage_path_is_local_log_path(tmp_path: Path) -> None:
    assert default_model_usage_path(tmp_path) == (
        tmp_path.resolve() / "logs" / "model_governance" / "model_usage.jsonl"
    )

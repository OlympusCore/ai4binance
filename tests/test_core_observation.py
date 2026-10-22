"""Test-only observed calls and failures; never operational runtime evidence."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai4binance.core.serialization import to_primitive
from ai4binance.events.traceability import CanonicalTraceJournal, canonical_trace_sha256
from ai4binance.governance.architecture import load_logical_architecture_registry
from ai4binance.governance.architecture.observation import (
    consume_core_output,
    core_observation_scope,
)
from ai4binance.governance.enforcement.receipt import load_core_consumption_batch

ROOT = Path(__file__).resolve().parents[1]
INTERFACE = "data-snapshot-acquisition"


def test_unscoped_call_keeps_the_existing_producer_consumer_order() -> None:
    events: list[object] = []

    def produce() -> dict[str, int]:
        events.append("produce")
        return {"test_only": 7}

    def consume(value: dict[str, int]) -> int:
        events.append(value)
        return value["test_only"] + 1

    assert (
        consume_core_output(INTERFACE, inputs=(), produce=produce, consume=consume) == 8
    )
    assert events == ["produce", {"test_only": 7}]


def test_scope_records_actual_inputs_output_and_consumed_outcome_after_completion(
    tmp_path: Path,
) -> None:
    journal = CanonicalTraceJournal(tmp_path / "test-only.jsonl")
    inputs = {"test_only_input": 4}
    produced = {"test_only_output": 8}
    with core_observation_scope(ROOT, "TEST_ONLY_CYCLE", journal=journal):
        result = consume_core_output(
            INTERFACE,
            inputs=inputs,
            produce=lambda: produced,
            consume=lambda output: output["test_only_output"] + 1,
        )
        assert journal.records() == ()
    assert result == 9
    proofs = load_core_consumption_batch(
        journal, ROOT, load_logical_architecture_registry()
    )
    assert len(proofs) == 1
    proof = proofs[0]
    assert proof["input_sha256"] == canonical_trace_sha256(inputs)
    assert proof["output_sha256"] == canonical_trace_sha256(produced)
    assert proof["outcome_sha256"] == canonical_trace_sha256(result)
    assert proof["observation_class"] == "TEST_ONLY"
    assert proof["operation_status"] == "SUCCESS"
    resources = proof["resources"]
    assert isinstance(resources, dict)
    assert resources["operation_scope"] == "CORE_HANDOFF"
    assert resources["llm_calls"] is None
    assert resources["budget_status"] == "NOT_VERIFIED"
    assert proof["execution_allowed"] is False


@pytest.mark.parametrize("failure_stage", ["producer", "consumer"])
@pytest.mark.parametrize("error_type", [ValueError, TimeoutError])
def test_failed_handoff_preserves_the_error_and_does_not_invent_outputs(
    tmp_path: Path, failure_stage: str, error_type: type[Exception]
) -> None:
    journal = CanonicalTraceJournal(tmp_path / "test-only.jsonl")
    calls: list[str] = []

    def produce() -> int:
        calls.append("producer")
        if failure_stage == "producer":
            raise error_type("TEST_ONLY_FAILURE")
        return 7

    def consume(value: int) -> int:
        calls.append("consumer")
        raise error_type("TEST_ONLY_FAILURE")

    with pytest.raises(error_type, match="TEST_ONLY_FAILURE"):
        with core_observation_scope(ROOT, "TEST_ONLY_FAILURE", journal=journal):
            consume_core_output(INTERFACE, inputs=(), produce=produce, consume=consume)
    proof = load_core_consumption_batch(
        journal, ROOT, load_logical_architecture_registry()
    )[0]
    assert proof["operation_status"] == (
        "TIMEOUT" if error_type is TimeoutError else "ERROR"
    )
    assert proof["outcome_sha256"] is None
    if failure_stage == "producer":
        assert proof["output_sha256"] is None
        assert calls == ["producer"]
    else:
        assert proof["output_sha256"] == canonical_trace_sha256(7)
        assert calls == ["producer", "consumer"]


def test_subject_drift_blocks_the_entire_batch_before_the_first_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ai4binance.governance.enforcement import receipt

    journal = CanonicalTraceJournal(tmp_path / "test-only.jsonl")

    def drifting_cycle() -> None:
        with core_observation_scope(ROOT, "TEST_ONLY_DRIFT", journal=journal):
            consume_core_output(
                INTERFACE, inputs=(), produce=lambda: 7, consume=lambda value: value + 1
            )
            monkeypatch.setattr(
                receipt, "core_consumption_subject_sha256", lambda _: "f" * 64
            )

    with pytest.raises(ValueError, match="SUBJECT_CHANGED_DURING_OPERATION"):
        drifting_cycle()
    assert journal.records() == ()


def test_unknown_interface_and_unserializable_inputs_cannot_invoke_the_producer(
    tmp_path: Path,
) -> None:
    calls: list[int] = []
    journal = CanonicalTraceJournal(tmp_path / "test-only.jsonl")
    with core_observation_scope(ROOT, "TEST_ONLY_INVALID", journal=journal):
        with pytest.raises(ValueError, match="UNKNOWN"):
            consume_core_output(
                "TEST_ONLY_UNKNOWN",
                inputs=(),
                produce=lambda: calls.append(1),
                consume=lambda _: None,
            )
        with pytest.raises(TypeError, match="unsupported audit value"):
            consume_core_output(
                INTERFACE,
                inputs=object(),
                produce=lambda: calls.append(2),
                consume=lambda _: None,
            )
    assert calls == []
    assert journal.records() == ()


def test_nested_calls_share_one_cycle_and_do_not_flush_an_incomplete_outer_handoff(
    tmp_path: Path,
) -> None:
    journal = CanonicalTraceJournal(tmp_path / "test-only.jsonl")
    with core_observation_scope(ROOT, "TEST_ONLY_OUTER", journal=journal):
        with core_observation_scope(ROOT, "TEST_ONLY_NESTED"):
            consume_core_output(
                INTERFACE, inputs=(), produce=lambda: 7, consume=lambda value: value + 1
            )
        assert not journal.records()
    assert journal.records()[0].related_refs[-1] == "TEST_ONLY_OUTER"


def test_real_orchestrator_consumers_preserve_the_fail_closed_analysis(
    tmp_path: Path,
) -> None:
    from ai4binance.agents.orchestrator import EnterpriseOrchestrator
    from tests.test_agents import snapshot

    subject = snapshot()
    orchestrator = EnterpriseOrchestrator(max_workers=1)
    expected = orchestrator.analyze(subject)
    journal = CanonicalTraceJournal(tmp_path / "test-only-orchestrator.jsonl")
    with core_observation_scope(ROOT, "TEST_ONLY_ORCHESTRATOR", journal=journal):
        actual = orchestrator.analyze(subject)
    assert to_primitive(actual.final_decision) == to_primitive(expected.final_decision)
    assert actual.blockers == expected.blockers
    proofs = load_core_consumption_batch(
        journal, ROOT, load_logical_architecture_registry()
    )
    assert {item["interface_id"] for item in proofs} == {
        "deterministic-candidate-handoff",
        "risk-assessment-handoff",
        "validation-signal-handoff",
    }
    assert all(item["observation_class"] == "TEST_ONLY" for item in proofs)
    assert all(not item["execution_allowed"] for item in proofs)


def test_fixture_provenance_cannot_be_promoted_by_running_outside_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate the environment boundary in an isolated test-only journal."""
    journal = CanonicalTraceJournal(tmp_path / "test-only-provenance.jsonl")
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    with core_observation_scope(ROOT, "TEST_ONLY_PROVENANCE", journal=journal):
        consume_core_output(
            INTERFACE,
            inputs=(),
            produce=lambda: {"provenance_class": "TEST_FIXTURE", "value": 7},
            consume=lambda output: output["value"],
        )
    proof = load_core_consumption_batch(
        journal, ROOT, load_logical_architecture_registry()
    )[0]
    assert proof["observation_class"] == "TEST_ONLY"


def test_buffered_observation_keeps_consumption_time_when_newer_events_exist(
    tmp_path: Path,
) -> None:
    from datetime import UTC, datetime

    from ai4binance.events.traceability import (
        CanonicalTraceRecord,
        ConsequentialTraceKind,
    )

    journal = CanonicalTraceJournal(tmp_path / "test-only-ordering.jsonl")
    evidence_path = tmp_path / "test-only-interleaved.json"
    evidence_path.write_text('{"test_only":"interleaved"}', encoding="utf-8")
    with core_observation_scope(ROOT, "TEST_ONLY_ORDERING", journal=journal):
        consume_core_output(
            INTERFACE, inputs=(), produce=lambda: 7, consume=lambda value: value + 1
        )
        later_event = CanonicalTraceRecord.create(
            trace_id="TEST_ONLY_INTERLEAVED_EVENT",
            trace_kind=ConsequentialTraceKind.GATE,
            subject_ref="TEST_ONLY_SUBJECT",
            subject_type="TEST_ONLY",
            occurred_at=datetime.now(UTC),
            event_name="TEST_ONLY_INTERLEAVED",
            event_status="TEST_ONLY",
            evidence_refs=(str(evidence_path.resolve()),),
            subject_sha256=canonical_trace_sha256({"test_only": "interleaved"}),
        )
        journal.append(later_event)
    proof = load_core_consumption_batch(
        journal, ROOT, load_logical_architecture_registry()
    )[0]
    observed = datetime.fromisoformat(str(proof["observed_at"]))
    assert observed < later_event.occurred_at <= journal.records()[-1].occurred_at
    assert proof["observation_class"] == "TEST_ONLY"


def test_late_persistence_of_an_older_success_cannot_override_a_newer_failure() -> None:
    """Synthetic timestamp ordering exercises the resolver only."""
    from ai4binance.governance.architecture.assurance import resolve_core_assurance

    registry = load_logical_architecture_registry()
    core = registry.core_modules[0]
    assert core.assurance is not None
    success: dict[str, object] = {
        **core.assurance.interfaces[0].to_payload(),
        "core_id": core.core_id,
        "cycle_id": "TEST_ONLY_OLD",
        "observation_class": "OBSERVED_LOCAL_CALL",
        "operation_status": "SUCCESS",
        "observed_at": "2026-10-22T00:00:00Z",
    }
    failure = {
        **success,
        "cycle_id": "TEST_ONLY_NEW",
        "operation_status": "ERROR",
        "observed_at": "2026-10-22T00:00:01Z",
    }
    result = resolve_core_assurance(
        registry,
        core,
        ROOT,
        quality={},
        quality_blockers=(),
        consumption=(failure, success),
    )
    assert result.dimensions["runtime_consumer"] == "UNKNOWN"
    assert not result.operationally_verified


def test_interface_proofs_from_different_cycles_cannot_be_stitched_into_a_core() -> (
    None
):
    """Synthetic handoffs remain test-only inputs to this deterministic test."""
    from dataclasses import replace

    from ai4binance.governance.architecture.assurance import resolve_core_assurance

    registry = load_logical_architecture_registry()
    core = registry.core_modules[0]
    assert core.assurance is not None
    first = core.assurance.interfaces[0]
    second = replace(first, interface_id="TEST_ONLY_SECOND_INTERFACE")
    core = replace(core, assurance=replace(core.assurance, interfaces=(first, second)))
    proofs: tuple[dict[str, object], ...] = tuple(
        {
            **binding.to_payload(),
            "core_id": core.core_id,
            "observation_class": "OBSERVED_LOCAL_CALL",
            "operation_status": "SUCCESS",
            "cycle_id": cycle,
        }
        for binding, cycle in ((first, "TEST_ONLY_A"), (second, "TEST_ONLY_B"))
    )
    result = resolve_core_assurance(
        registry, core, ROOT, quality={}, quality_blockers=(), consumption=proofs
    )
    assert result.dimensions["runtime_consumer"] == "PARTIAL"
    assert "CORE_INTERFACE_CYCLE_MISMATCH" in result.blockers
    assert not result.operationally_verified

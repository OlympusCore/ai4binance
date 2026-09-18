"""Policy-gated local tool execution with outcome attestation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from ai4binance.governance.capability_store import CapabilityLease, CapabilityStore
from ai4binance.governance.decision_records import (
    DecisionRecord,
    OutcomeAttestation,
    OutcomeStatus,
    OutcomeVerification,
    RunContext,
    build_decision_record,
    build_outcome_attestation,
    failed_outcome,
    new_execution_id,
    not_executed_outcome,
    unverified_outcome,
)
from ai4binance.governance.tool_loop_guard import (
    ToolLoopDecision,
    ToolLoopGuard,
    default_tool_arguments,
)
from ai4binance.governance.tool_policy import (
    ToolDescriptor,
    ToolPermission,
    ToolPolicyDecision,
    ToolPolicyEngine,
)
from ai4binance.governance.tool_registry import ToolRegistry

T = TypeVar("T")


class ToolOutcomeStatus(StrEnum):
    NOT_EXECUTED = "NOT_EXECUTED"
    UNKNOWN = "UNKNOWN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    status: ToolOutcomeStatus
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status is not ToolOutcomeStatus.SUCCEEDED and not self.reason_codes:
            raise ValueError("non-success tool outcome requires reasons")


@dataclass(frozen=True, slots=True)
class ToolExecutionRecord:
    tool: str
    project: str
    policy_decision: ToolPolicyDecision
    policy_reasons: tuple[str, ...]
    outcome: ToolOutcome
    decision_record: DecisionRecord | None = None
    outcome_attestation: OutcomeAttestation | None = None
    capability_lease: CapabilityLease | None = None
    loop_before: ToolLoopDecision | None = None
    loop_after: ToolLoopDecision | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.tool.strip() or not self.project.strip():
            raise ValueError("tool execution record identity is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("tool execution record cannot authorize trading")


@dataclass(frozen=True, slots=True)
class ToolGatewayResult[T]:
    record: ToolExecutionRecord
    value: T | None = None


OutcomeValidator = Callable[[T], ToolOutcome]
AttestationValidator = Callable[[T], OutcomeVerification]


@dataclass(frozen=True, slots=True)
class ToolGateway:
    registry: ToolRegistry
    policy: ToolPolicyEngine
    capability_store: CapabilityStore | None = None
    loop_guard: ToolLoopGuard | None = None

    def execute(
        self,
        *,
        tool: str,
        project: str,
        permission: ToolPermission,
        approved: bool,
        operation: Callable[[], T],
        outcome_validator: OutcomeValidator[T] | None = None,
        attestation_validator: AttestationValidator[T] | None = None,
        agent: str = "ai4binance",
        run_context: RunContext | None = None,
        target: str | None = None,
        approval_id: str | None = None,
        state_hash_before: str | None = None,
        evidence_hashes: tuple[str, ...] = (),
        tool_arguments: dict[str, object] | None = None,
    ) -> ToolGatewayResult[T]:
        descriptor: ToolDescriptor | None = None
        execution_id = new_execution_id()
        context = run_context or RunContext(run_id=execution_id, step_id="tool_gateway")
        try:
            descriptor = self.registry.require(tool)
            evaluation = self.policy.evaluate(
                descriptor,
                project=project,
                permission=permission,
                approved=approved,
            )
        except Exception as exc:
            decision_record = build_decision_record(
                context=context,
                project=project,
                agent=agent,
                tool=tool,
                permission=permission,
                approved=approved,
                descriptor=descriptor,
                decision=ToolPolicyDecision.DENY,
                reason_codes=(type(exc).__name__,),
                approval_id=approval_id,
                state_hash_before=state_hash_before,
                evidence_hashes=evidence_hashes,
                policy_id=self.policy.document.policy_id,
                policy_version=self.policy.document.version,
                policy_hash=self.policy.document.sha256,
                target=target,
            )
            attestation = build_outcome_attestation(
                decision_record.decision_id,
                execution_id,
                not_executed_outcome(str(exc) or type(exc).__name__),
            )
            return ToolGatewayResult(
                record=ToolExecutionRecord(
                    tool=tool,
                    project=project,
                    policy_decision=ToolPolicyDecision.DENY,
                    policy_reasons=(type(exc).__name__,),
                    outcome=ToolOutcome(
                        ToolOutcomeStatus.NOT_EXECUTED,
                        (str(exc) or type(exc).__name__,),
                    ),
                    decision_record=decision_record,
                    outcome_attestation=attestation,
                )
            )
        if evaluation.decision is not ToolPolicyDecision.ALLOW:
            decision_record = build_decision_record(
                context=context,
                project=project,
                agent=agent,
                tool=descriptor.name,
                permission=permission,
                approved=approved,
                descriptor=descriptor,
                decision=evaluation.decision,
                reason_codes=evaluation.reason_codes,
                approval_id=approval_id,
                state_hash_before=state_hash_before,
                evidence_hashes=evidence_hashes,
                policy_id=evaluation.policy_id,
                policy_version=evaluation.policy_version,
                policy_hash=evaluation.policy_sha256,
                target=target,
            )
            attestation = build_outcome_attestation(
                decision_record.decision_id,
                execution_id,
                not_executed_outcome(",".join(evaluation.reason_codes)),
            )
            return ToolGatewayResult(
                record=ToolExecutionRecord(
                    tool=descriptor.name,
                    project=project,
                    policy_decision=evaluation.decision,
                    policy_reasons=evaluation.reason_codes,
                    outcome=ToolOutcome(
                        ToolOutcomeStatus.NOT_EXECUTED,
                        evaluation.reason_codes,
                    ),
                    decision_record=decision_record,
                    outcome_attestation=attestation,
                )
            )
        guard_arguments = default_tool_arguments(
            project=project,
            permission=permission,
            target=target,
            extra=tool_arguments,
        )
        loop_before: ToolLoopDecision | None = None
        if self.loop_guard is not None:
            loop_before = self.loop_guard.before_call(
                tool_name=descriptor.name,
                arguments=guard_arguments,
                side_effect=descriptor.side_effect,
            )
            if loop_before.blocked:
                decision_record = build_decision_record(
                    context=context,
                    project=project,
                    agent=agent,
                    tool=descriptor.name,
                    permission=permission,
                    approved=approved,
                    descriptor=descriptor,
                    decision=ToolPolicyDecision.DENY,
                    reason_codes=(loop_before.code,),
                    approval_id=approval_id,
                    state_hash_before=state_hash_before,
                    evidence_hashes=evidence_hashes,
                    policy_id=evaluation.policy_id,
                    policy_version=evaluation.policy_version,
                    policy_hash=evaluation.policy_sha256,
                    target=target,
                )
                attestation = build_outcome_attestation(
                    decision_record.decision_id,
                    execution_id,
                    not_executed_outcome(loop_before.code),
                )
                return ToolGatewayResult(
                    record=ToolExecutionRecord(
                        tool=descriptor.name,
                        project=project,
                        policy_decision=ToolPolicyDecision.DENY,
                        policy_reasons=(loop_before.code,),
                        outcome=ToolOutcome(
                            ToolOutcomeStatus.NOT_EXECUTED,
                            (loop_before.code,),
                        ),
                        decision_record=decision_record,
                        outcome_attestation=attestation,
                        loop_before=loop_before,
                    )
                )

        capability_lease: CapabilityLease | None = None
        if self.capability_store is not None:
            try:
                capability_lease = self.capability_store.issue(
                    run_id=context.run_id,
                    project=project,
                    descriptor=descriptor,
                    permission=permission,
                    policy_hash=evaluation.policy_sha256,
                )
                capability_lease = self.capability_store.consume(
                    capability_lease,
                    execution_id=execution_id,
                )
            except Exception as exc:
                reason = str(exc) or type(exc).__name__
                decision_record = build_decision_record(
                    context=context,
                    project=project,
                    agent=agent,
                    tool=descriptor.name,
                    permission=permission,
                    approved=approved,
                    descriptor=descriptor,
                    decision=ToolPolicyDecision.DENY,
                    reason_codes=(reason,),
                    approval_id=approval_id,
                    state_hash_before=state_hash_before,
                    evidence_hashes=evidence_hashes,
                    policy_id=evaluation.policy_id,
                    policy_version=evaluation.policy_version,
                    policy_hash=evaluation.policy_sha256,
                    target=target,
                )
                attestation = build_outcome_attestation(
                    decision_record.decision_id,
                    execution_id,
                    not_executed_outcome(reason),
                )
                return ToolGatewayResult(
                    record=ToolExecutionRecord(
                        tool=descriptor.name,
                        project=project,
                        policy_decision=ToolPolicyDecision.DENY,
                        policy_reasons=(reason,),
                        outcome=ToolOutcome(
                            ToolOutcomeStatus.NOT_EXECUTED,
                            (reason,),
                        ),
                        decision_record=decision_record,
                        outcome_attestation=attestation,
                    )
                )
        decision_record = build_decision_record(
            context=context,
            project=project,
            agent=agent,
            tool=descriptor.name,
            permission=permission,
            approved=approved,
            descriptor=descriptor,
            decision=evaluation.decision,
            reason_codes=evaluation.reason_codes,
            approval_id=approval_id,
            state_hash_before=state_hash_before,
            evidence_hashes=evidence_hashes,
            policy_id=evaluation.policy_id,
            policy_version=evaluation.policy_version,
            policy_hash=evaluation.policy_sha256,
            target=target,
            capability_lease_id=(
                capability_lease.lease_id if capability_lease is not None else None
            ),
        )
        try:
            value = operation()
        except Exception as exc:
            loop_after = (
                self.loop_guard.after_call(
                    tool_name=descriptor.name,
                    arguments=guard_arguments,
                    side_effect=descriptor.side_effect,
                    result={"error_type": type(exc).__name__},
                    failed=True,
                )
                if self.loop_guard is not None
                else None
            )
            attestation = build_outcome_attestation(
                decision_record.decision_id,
                execution_id,
                failed_outcome(exc),
            )
            return ToolGatewayResult(
                record=ToolExecutionRecord(
                    tool=descriptor.name,
                    project=project,
                    policy_decision=evaluation.decision,
                    policy_reasons=evaluation.reason_codes,
                    outcome=ToolOutcome(
                        ToolOutcomeStatus.FAILED,
                        (type(exc).__name__,),
                    ),
                    decision_record=decision_record,
                    outcome_attestation=attestation,
                    capability_lease=capability_lease,
                    loop_before=loop_before,
                    loop_after=loop_after,
                )
            )
        outcome = (
            outcome_validator(value)
            if outcome_validator is not None
            else ToolOutcome(ToolOutcomeStatus.UNKNOWN, ("OUTCOME_VALIDATOR_MISSING",))
        )
        verification = (
            attestation_validator(value)
            if attestation_validator is not None
            else _verification_from_outcome(outcome)
        )
        attestation = build_outcome_attestation(
            decision_record.decision_id,
            execution_id,
            verification,
        )
        loop_after = (
            self.loop_guard.after_call(
                tool_name=descriptor.name,
                arguments=guard_arguments,
                side_effect=descriptor.side_effect,
                result=value,
                failed=False,
            )
            if self.loop_guard is not None
            else None
        )
        return ToolGatewayResult(
            record=ToolExecutionRecord(
                tool=descriptor.name,
                project=project,
                policy_decision=evaluation.decision,
                policy_reasons=evaluation.reason_codes,
                outcome=outcome,
                decision_record=decision_record,
                outcome_attestation=attestation,
                capability_lease=capability_lease,
                loop_before=loop_before,
                loop_after=loop_after,
            ),
            value=value,
        )


def _verification_from_outcome(outcome: ToolOutcome) -> OutcomeVerification:
    status = {
        ToolOutcomeStatus.NOT_EXECUTED: OutcomeStatus.NOT_EXECUTED,
        ToolOutcomeStatus.UNKNOWN: OutcomeStatus.UNKNOWN,
        ToolOutcomeStatus.SUCCEEDED: OutcomeStatus.SUCCEEDED,
        ToolOutcomeStatus.FAILED: OutcomeStatus.FAILED,
    }[outcome.status]
    if status is OutcomeStatus.UNKNOWN:
        return unverified_outcome(outcome.reason_codes[0])
    return OutcomeVerification(
        outcome=status,
        validator="tool_outcome",
        reason_codes=outcome.reason_codes,
    )

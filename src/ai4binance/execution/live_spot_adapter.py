"""Fail-closed Spot live order adapter that coordinates execution and journaling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ai4binance.domain import LiveGateInput
from ai4binance.execution.authorization import ExecutionAuthorizationEnvelope
from ai4binance.execution.live_order_lifecycle import (
    LiveOrderLifecycleJournal,
    LiveOrderLifecycleRecord,
)
from ai4binance.execution.live_spot import (
    GatedSpotOrderExecutor,
    LiveCommandResult,
    LiveCommandStatus,
)


@dataclass(frozen=True, slots=True)
class LiveSpotOrderPlacement:
    """Result wrapper that keeps execution and lifecycle evidence together."""

    command_result: LiveCommandResult
    lifecycle_record: LiveOrderLifecycleRecord | None = None

    def __post_init__(self) -> None:
        if self.lifecycle_record is not None and self.command_result.status not in {
            LiveCommandStatus.ATTEMPT_FAILED,
            LiveCommandStatus.SUBMITTED,
            LiveCommandStatus.UNVERIFIED_REVIEW_REQUIRED,
        }:
            raise ValueError("unexpected lifecycle record for live order result")


@dataclass(frozen=True, slots=True)
class LiveSpotOrderAdapter:
    """Coordinate the gated executor and lifecycle journal for Spot live writes."""

    executor: GatedSpotOrderExecutor
    journal: LiveOrderLifecycleJournal | None = None

    def place(
        self,
        gate_input: LiveGateInput,
        *,
        authorization: ExecutionAuthorizationEnvelope | None,
        attempted_at: datetime | None = None,
        observed_at: datetime | None = None,
    ) -> LiveSpotOrderPlacement:
        result = self.executor.place(
            gate_input,
            authorization=authorization,
            attempted_at=attempted_at,
        )
        record = None
        if self.journal is not None and result.status is not LiveCommandStatus.BLOCKED:
            if authorization is None:
                raise RuntimeError("journaled placement requires authorization")
            record = self.journal.append_place_result(
                authorization.to_spot_order_command(),
                result=result,
                observed_at=observed_at or datetime.now(UTC),
            )
        return LiveSpotOrderPlacement(result, record)

    def cancel(
        self,
        *,
        symbol: str,
        client_order_id: str,
        gate_input: LiveGateInput,
    ) -> LiveCommandResult:
        return self.executor.cancel(
            symbol=symbol,
            client_order_id=client_order_id,
            gate_input=gate_input,
        )

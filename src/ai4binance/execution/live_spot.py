"""Explicitly authorized Spot WebSocket order commands with internal live gating."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast

from ai4binance.domain import ExecutionStatus, LiveGateInput, ValidationStatus
from ai4binance.execution.authorization import (
    ExecutionAuthorizationAlreadyConsumedError,
    ExecutionAuthorizationEnvelope,
    ExecutionAuthorizationLedgerUnavailableError,
    ExecutionAuthorizationSource,
    LocalExecutionAuthorizationLedger,
)
from ai4binance.execution.order_command import SpotOrderCommand as SpotOrderCommand
from ai4binance.safety import evaluate_live_gate
from ai4binance.validation.live_gate_evidence import (
    LiveGateEvidenceRegistry,
    LiveGateEvidenceResolution,
)
from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceQuery,
    PromotionEvidenceRegistry,
)


class SpotOrderSession(Protocol):
    def order_test(self, params: Mapping[str, object]) -> object: ...

    def order_place(self, params: Mapping[str, object]) -> object: ...

    def order_cancel(self, params: Mapping[str, object]) -> object: ...


class LiveCommandStatus(StrEnum):
    BLOCKED = "LIVE_ORDER_BLOCKED"
    SUBMITTED = "LIVE_ORDER_SUBMITTED"
    CANCELLED = "LIVE_ORDER_CANCELLED"
    ATTEMPT_FAILED = "LIVE_ORDER_ATTEMPT_FAILED_REVIEW_REQUIRED"
    UNVERIFIED_REVIEW_REQUIRED = "LIVE_ORDER_UNVERIFIED_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class OrderDestinationVerification:
    verified: bool
    blockers: tuple[str, ...] = ()
    observed_status: str | None = None
    order_snapshot: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if self.verified and self.blockers:
            raise ValueError("verified order destination cannot contain blockers")
        if not self.verified and not self.blockers:
            raise ValueError("unverified order destination requires blockers")

    @classmethod
    def accepted(cls) -> OrderDestinationVerification:
        return cls(True)

    @classmethod
    def failed(cls, *blockers: str) -> OrderDestinationVerification:
        return cls(False, tuple(dict.fromkeys(blockers)))


class SpotOrderVerifier(Protocol):
    def verify_placed(
        self, command: SpotOrderCommand, exchange_order_id: str
    ) -> OrderDestinationVerification: ...

    def verify_cancelled(
        self, *, symbol: str, client_order_id: str, exchange_order_id: str
    ) -> OrderDestinationVerification: ...


class SpotOrderHistoryReader(Protocol):
    def all_orders(self, symbol: str, *, limit: int = 1_000) -> object: ...


@dataclass(frozen=True, slots=True)
class ReadOnlySpotOrderHistoryVerifier:
    """Verify order writes by reading immutable Spot order history."""

    reader: SpotOrderHistoryReader
    history_limit: int = 100

    def __post_init__(self) -> None:
        if not 1 <= self.history_limit <= 1_000:
            raise ValueError("order verification history limit is invalid")

    def verify_placed(
        self, command: SpotOrderCommand, exchange_order_id: str
    ) -> OrderDestinationVerification:
        order = self._matching_order(
            command.symbol, command.client_order_id, exchange_order_id
        )
        if order is None:
            return OrderDestinationVerification.failed(
                "ORDER_DESTINATION_READ_BACK_MISSING"
            )
        status = str(order.get("status", "")).upper()
        if status not in {
            "NEW",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELED",
            "EXPIRED",
            "REJECTED",
        }:
            return OrderDestinationVerification.failed(
                "ORDER_DESTINATION_STATUS_UNVERIFIED"
            )
        return OrderDestinationVerification(
            True,
            (),
            status,
            dict(order),
        )

    def verify_cancelled(
        self, *, symbol: str, client_order_id: str, exchange_order_id: str
    ) -> OrderDestinationVerification:
        order = self._matching_order(symbol, client_order_id, exchange_order_id)
        if order is None:
            return OrderDestinationVerification.failed(
                "ORDER_CANCEL_DESTINATION_READ_BACK_MISSING"
            )
        status = str(order.get("status", "")).upper()
        if status not in {"CANCELED", "EXPIRED"}:
            return OrderDestinationVerification.failed(
                "ORDER_CANCEL_DESTINATION_STATUS_UNVERIFIED"
            )
        return OrderDestinationVerification(
            True,
            (),
            status,
            dict(order),
        )

    def _matching_order(
        self, symbol: str, client_order_id: str, exchange_order_id: str
    ) -> Mapping[str, object] | None:
        history = self.reader.all_orders(symbol, limit=self.history_limit)
        if not isinstance(history, list):
            raise RuntimeError("order destination read-back must be a list")
        for item in history:
            if not isinstance(item, Mapping):
                continue
            observed_client_id = str(item.get("clientOrderId", "")).strip()
            observed_order_id = str(item.get("orderId", "")).strip()
            if (
                observed_client_id == client_order_id
                and observed_order_id == exchange_order_id
            ):
                return item
        return None


@dataclass(frozen=True, slots=True)
class LiveCommandResult:
    status: LiveCommandStatus
    blockers: tuple[str, ...]
    client_order_id: str
    exchange_order_id: str | None = None
    preview_hash: str | None = None
    exchange_order_status: str | None = None
    exchange_order_snapshot: Mapping[str, object] | None = None
    authorization_id: str | None = None
    authorization_envelope_sha256: str | None = None
    approval_id: str | None = None


@dataclass(frozen=True, slots=True)
class GatedSpotOrderExecutor:
    session: SpotOrderSession
    verifier: SpotOrderVerifier | None = None
    authorization_source: ExecutionAuthorizationSource | None = None
    authorization_ledger: LocalExecutionAuthorizationLedger | None = None
    live_gate_evidence_registry: LiveGateEvidenceRegistry | None = None
    promotion_evidence_registry: PromotionEvidenceRegistry | None = None
    promotion_query: PromotionEvidenceQuery | None = None

    def place(
        self,
        gate_input: LiveGateInput,
        *,
        authorization: ExecutionAuthorizationEnvelope | None,
        attempted_at: datetime | None = None,
    ) -> LiveCommandResult:
        observed_at = attempted_at or datetime.now(UTC)
        blockers: list[str] = []
        command = (
            authorization.to_spot_order_command() if authorization is not None else None
        )
        resolved_authorization: ExecutionAuthorizationEnvelope | None = None
        if authorization is None:
            blockers.append("EXECUTION_AUTHORIZATION_REQUIRED")
        elif self.authorization_source is None:
            blockers.append("EXECUTION_AUTHORIZATION_SOURCE_UNAVAILABLE")
        else:
            try:
                resolved_authorization = (
                    self.authorization_source.resolve_execution_authorization(
                        authorization.authorization_id
                    )
                )
            except (OSError, TypeError, ValueError):
                blockers.append("EXECUTION_AUTHORIZATION_EVIDENCE_INVALID")
            if resolved_authorization is None:
                blockers.append("EXECUTION_AUTHORIZATION_NOT_APPROVED")
            elif (
                resolved_authorization.envelope_sha256 != authorization.envelope_sha256
            ):
                blockers.append("EXECUTION_AUTHORIZATION_RECORD_MISMATCH")
            else:
                blockers.extend(
                    authorization.blockers_for(
                        authorization.to_spot_order_command(),
                        observed_at=observed_at,
                    )
                )
        if not blockers and resolved_authorization is not None:
            gate_input, evidence_blockers = self._evidence_bound_gate_input(
                gate_input,
                resolved_authorization,
                observed_at=observed_at,
            )
            blockers.extend(evidence_blockers)
        gate = evaluate_live_gate(gate_input)
        blockers.extend(gate.blockers)
        if gate.status is not ExecutionStatus.EXECUTION_ALLOWED or blockers:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                tuple(dict.fromkeys(blockers)),
                authorization.client_order_id if authorization is not None else "",
                preview_hash=(
                    authorization.preview_hash if authorization is not None else None
                ),
                authorization_id=(
                    authorization.authorization_id
                    if authorization is not None
                    else None
                ),
                authorization_envelope_sha256=(
                    authorization.envelope_sha256 if authorization is not None else None
                ),
                approval_id=(
                    authorization.approval_id if authorization is not None else None
                ),
            )
        if authorization is None:
            raise RuntimeError("validated execution authorization is unavailable")
        if command is None:
            raise RuntimeError("authorized Spot order command is unavailable")
        if self.authorization_source is None:
            raise RuntimeError("validated authorization source is unavailable")
        if self.verifier is None:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("ORDER_DESTINATION_VERIFIER_UNAVAILABLE",),
                command.client_order_id,
                preview_hash=command.preview_hash,
                authorization_id=authorization.authorization_id,
                authorization_envelope_sha256=authorization.envelope_sha256,
                approval_id=authorization.approval_id,
            )
        if self.authorization_ledger is None:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("EXECUTION_AUTHORIZATION_LEDGER_UNAVAILABLE",),
                command.client_order_id,
                preview_hash=command.preview_hash,
                authorization_id=authorization.authorization_id,
                authorization_envelope_sha256=authorization.envelope_sha256,
                approval_id=authorization.approval_id,
            )
        try:
            self.authorization_ledger.claim(
                authorization,
                execution_id=command.client_order_id,
                claimed_at=observed_at,
            )
        except ExecutionAuthorizationAlreadyConsumedError:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("EXECUTION_AUTHORIZATION_ALREADY_CONSUMED",),
                command.client_order_id,
                preview_hash=command.preview_hash,
                authorization_id=authorization.authorization_id,
                authorization_envelope_sha256=authorization.envelope_sha256,
                approval_id=authorization.approval_id,
            )
        except ExecutionAuthorizationLedgerUnavailableError:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("EXECUTION_AUTHORIZATION_LEDGER_UNAVAILABLE",),
                command.client_order_id,
                preview_hash=command.preview_hash,
                authorization_id=authorization.authorization_id,
                authorization_envelope_sha256=authorization.envelope_sha256,
                approval_id=authorization.approval_id,
            )
        try:
            revalidated = self.authorization_source.resolve_execution_authorization(
                authorization.authorization_id
            )
        except (OSError, TypeError, ValueError):
            revalidated = None
        if (
            revalidated is None
            or revalidated.envelope_sha256 != authorization.envelope_sha256
        ):
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("EXECUTION_AUTHORIZATION_REVOKED_BEFORE_ATTEMPT",),
                command.client_order_id,
                preview_hash=command.preview_hash,
                authorization_id=authorization.authorization_id,
                authorization_envelope_sha256=authorization.envelope_sha256,
                approval_id=authorization.approval_id,
            )
        try:
            payload = command.payload()
            self.session.order_test(payload)
            response = self.session.order_place(payload)
            order_id = _exchange_order_id(response)
            verification = self.verifier.verify_placed(command, order_id)
        except Exception:
            return LiveCommandResult(
                LiveCommandStatus.ATTEMPT_FAILED,
                ("LIVE_ORDER_ATTEMPT_OUTCOME_UNVERIFIED",),
                command.client_order_id,
                preview_hash=command.preview_hash,
                authorization_id=authorization.authorization_id,
                authorization_envelope_sha256=authorization.envelope_sha256,
                approval_id=authorization.approval_id,
            )
        if not verification.verified:
            return LiveCommandResult(
                LiveCommandStatus.UNVERIFIED_REVIEW_REQUIRED,
                verification.blockers,
                command.client_order_id,
                order_id,
                command.preview_hash,
                verification.observed_status,
                verification.order_snapshot,
                authorization.authorization_id,
                authorization.envelope_sha256,
                authorization.approval_id,
            )
        return LiveCommandResult(
            LiveCommandStatus.SUBMITTED,
            (),
            command.client_order_id,
            order_id,
            command.preview_hash,
            verification.observed_status,
            verification.order_snapshot,
            authorization.authorization_id,
            authorization.envelope_sha256,
            authorization.approval_id,
        )

    def _evidence_bound_gate_input(
        self,
        gate_input: LiveGateInput,
        authorization: ExecutionAuthorizationEnvelope,
        *,
        observed_at: datetime,
    ) -> tuple[LiveGateInput, tuple[str, ...]]:
        denied_gate_input = replace(
            gate_input,
            backtest_approved=False,
            walk_forward_approved=False,
            tuning_report_approved=False,
            oos_approved=False,
            strategy_promotion_approved=False,
        )
        query = self.promotion_query
        if not isinstance(query, PromotionEvidenceQuery):
            return denied_gate_input, ("EXECUTION_EVIDENCE_EXACT_QUERY_REQUIRED",)
        exact_query = replace(query, as_of=observed_at)
        if (
            exact_query.strategy_id != authorization.strategy_id
            or exact_query.strategy_version != authorization.strategy_version
            or exact_query.symbol != authorization.symbol
            or exact_query.market_type != authorization.market_type
        ):
            return denied_gate_input, (
                "EXECUTION_EVIDENCE_AUTHORIZATION_SUBJECT_MISMATCH",
            )

        validation_registry = self.live_gate_evidence_registry
        if not isinstance(validation_registry, LiveGateEvidenceRegistry):
            validation = LiveGateEvidenceResolution(
                blockers=("LIVE_GATE_EVIDENCE_REGISTRY_REQUIRED",)
            )
        else:
            try:
                validation = validation_registry.resolve(
                    query=exact_query,
                    expected_bundle_sha256=authorization.validation_bundle_hash,
                )
            except (TypeError, ValueError):
                validation = LiveGateEvidenceResolution(
                    blockers=("LIVE_GATE_EVIDENCE_INVALID",)
                )

        promotion_status = ValidationStatus.RESEARCH_ONLY
        promotion_blockers: tuple[str, ...]
        promotion_registry = self.promotion_evidence_registry
        if not isinstance(promotion_registry, PromotionEvidenceRegistry):
            promotion_blockers = ("PROMOTION_EVIDENCE_REGISTRY_REQUIRED",)
        else:
            try:
                promotion_status = promotion_registry.resolve(query=exact_query)
            except (TypeError, ValueError):
                promotion_blockers = ("PROMOTION_EVIDENCE_INVALID",)
            else:
                promotion_blockers = (
                    ()
                    if promotion_status is ValidationStatus.LIVE_ELIGIBLE
                    else ("PROMOTION_EVIDENCE_LIVE_ELIGIBLE_REQUIRED",)
                )

        return (
            replace(
                gate_input,
                backtest_approved=validation.backtest_approved,
                walk_forward_approved=validation.walk_forward_approved,
                tuning_report_approved=validation.tuning_report_approved,
                oos_approved=validation.oos_approved,
                strategy_promotion_approved=(
                    promotion_status is ValidationStatus.LIVE_ELIGIBLE
                ),
            ),
            tuple(dict.fromkeys((*validation.blockers, *promotion_blockers))),
        )

    def cancel(
        self,
        *,
        symbol: str,
        client_order_id: str,
        gate_input: LiveGateInput,
    ) -> LiveCommandResult:
        gate = evaluate_live_gate(gate_input)
        normalized_symbol = symbol.strip().upper()
        normalized_id = client_order_id.strip()
        blockers = list(gate.blockers)
        if not normalized_symbol.isascii() or not normalized_symbol.isalnum():
            blockers.append("ORDER_SYMBOL_INVALID")
        if not normalized_id or not normalized_id.isascii():
            blockers.append("CLIENT_ORDER_ID_INVALID")
        if gate.status is not ExecutionStatus.EXECUTION_ALLOWED or blockers:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                tuple(dict.fromkeys(blockers)),
                normalized_id,
            )
        if self.verifier is None:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("ORDER_DESTINATION_VERIFIER_UNAVAILABLE",),
                normalized_id,
            )
        response = self.session.order_cancel(
            {"symbol": normalized_symbol, "origClientOrderId": normalized_id}
        )
        order_id = _exchange_order_id(response)
        verification = self.verifier.verify_cancelled(
            symbol=normalized_symbol,
            client_order_id=normalized_id,
            exchange_order_id=order_id,
        )
        if not verification.verified:
            return LiveCommandResult(
                LiveCommandStatus.UNVERIFIED_REVIEW_REQUIRED,
                verification.blockers,
                normalized_id,
                order_id,
                exchange_order_status=verification.observed_status,
                exchange_order_snapshot=verification.order_snapshot,
            )
        return LiveCommandResult(
            LiveCommandStatus.CANCELLED,
            (),
            normalized_id,
            order_id,
            exchange_order_status=verification.observed_status,
            exchange_order_snapshot=verification.order_snapshot,
        )


def _exchange_order_id(value: object) -> str:
    if not isinstance(value, Mapping):
        raise RuntimeError("exchange order response must be an object")
    response = cast(Mapping[str, object], value)
    order_id = response.get("orderId")
    if order_id is None or not str(order_id).strip():
        raise RuntimeError("exchange order response has no orderId")
    return str(order_id)

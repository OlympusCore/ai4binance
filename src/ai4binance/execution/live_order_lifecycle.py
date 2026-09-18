"""Canonical live-order lifecycle contract with fail-closed authority boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from ai4binance.domain import ValidationStatus
from ai4binance.events import DiskEventJournal, DomainEvent
from ai4binance.execution.live_spot import (
    LiveCommandResult,
    LiveCommandStatus,
    SpotOrderCommand,
)

ZERO = Decimal("0")


class LiveOrderLifecycleStage(StrEnum):
    """Deterministic live-order lifecycle stages."""

    DRAFT = "DRAFT"
    PREVIEWED = "PREVIEWED"
    PROMOTION_REQUIRED = "PROMOTION_REQUIRED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED = (
        "SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED"
    )
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class LiveOrderLifecycleEvent(StrEnum):
    """Deterministic lifecycle transition events."""

    PREVIEWED = "LIVE_ORDER_PREVIEWED"
    PROMOTION_REQUESTED = "LIVE_ORDER_PROMOTION_REQUESTED"
    HUMAN_APPROVAL_REQUESTED = "LIVE_ORDER_HUMAN_APPROVAL_REQUESTED"
    HUMAN_APPROVED = "LIVE_ORDER_HUMAN_APPROVED"
    SUBMISSION_ATTEMPT_FAILED = "LIVE_ORDER_SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED"
    SUBMITTED = "LIVE_ORDER_SUBMITTED"
    ACCEPTED = "LIVE_ORDER_ACCEPTED"
    PARTIALLY_FILLED = "LIVE_ORDER_PARTIALLY_FILLED"
    FILLED = "LIVE_ORDER_FILLED"
    CANCEL_REQUESTED = "LIVE_ORDER_CANCEL_REQUESTED"
    CANCELLED = "LIVE_ORDER_CANCELLED"
    REJECTED = "LIVE_ORDER_REJECTED"
    EXPIRED = "LIVE_ORDER_EXPIRED"


@dataclass(frozen=True, slots=True)
class LiveOrderLifecycleRecord:
    """Replayable lifecycle snapshot that never grants execution authority."""

    order_id: str
    symbol: str
    stage: LiveOrderLifecycleStage
    preview_hash: str
    promotion_status: ValidationStatus = ValidationStatus.RESEARCH_ONLY
    requested_quantity: Decimal | None = None
    approval_id: str | None = None
    authorization_id: str | None = None
    authorization_envelope_sha256: str | None = None
    promoted_at: datetime | None = None
    human_approval_requested_at: datetime | None = None
    human_approved_at: datetime | None = None
    submission_attempted_at: datetime | None = None
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    filled_quantity: Decimal = ZERO
    average_fill_price: Decimal = ZERO
    last_sequence: int = 0
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            not self.order_id.strip()
            or not self.symbol.strip()
            or not self.preview_hash.strip()
        ):
            raise ValueError("live order lifecycle identity is required")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        if self.requested_quantity is not None and self.requested_quantity <= ZERO:
            raise ValueError("requested_quantity must be positive")
        if self.filled_quantity < ZERO or self.average_fill_price < ZERO:
            raise ValueError("live order fill evidence cannot be negative")
        if self.last_sequence < 0:
            raise ValueError("live order lifecycle sequence cannot be negative")
        if (self.authorization_id is None) != (
            self.authorization_envelope_sha256 is None
        ):
            raise ValueError("live order authorization evidence must be complete")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("live order lifecycle cannot grant execution authority")
        if self.promotion_status not in {
            ValidationStatus.RESEARCH_ONLY,
            ValidationStatus.STAGED_CANDIDATE,
            ValidationStatus.PAPER_APPROVED,
            ValidationStatus.LIVE_ELIGIBLE,
        }:
            raise ValueError("live order promotion status is invalid")
        self._validate_stage_evidence()
        self._validate_fill_geometry()

    def _validate_stage_evidence(self) -> None:
        if self.stage is LiveOrderLifecycleStage.DRAFT:
            return
        if (
            self.stage
            in {
                LiveOrderLifecycleStage.PREVIEWED,
                LiveOrderLifecycleStage.PROMOTION_REQUIRED,
                LiveOrderLifecycleStage.HUMAN_APPROVAL_REQUIRED,
                LiveOrderLifecycleStage.READY_FOR_SUBMISSION,
                LiveOrderLifecycleStage.SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED,
                LiveOrderLifecycleStage.SUBMITTED,
                LiveOrderLifecycleStage.ACCEPTED,
                LiveOrderLifecycleStage.PARTIALLY_FILLED,
                LiveOrderLifecycleStage.FILLED,
                LiveOrderLifecycleStage.CANCEL_REQUESTED,
                LiveOrderLifecycleStage.CANCELLED,
            }
            and self.promoted_at is None
        ):
            raise ValueError("promoted live orders require promotion evidence")
        if (
            self.stage
            in {
                LiveOrderLifecycleStage.HUMAN_APPROVAL_REQUIRED,
                LiveOrderLifecycleStage.READY_FOR_SUBMISSION,
                LiveOrderLifecycleStage.SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED,
                LiveOrderLifecycleStage.SUBMITTED,
                LiveOrderLifecycleStage.ACCEPTED,
                LiveOrderLifecycleStage.PARTIALLY_FILLED,
                LiveOrderLifecycleStage.FILLED,
                LiveOrderLifecycleStage.CANCEL_REQUESTED,
                LiveOrderLifecycleStage.CANCELLED,
            }
            and self.human_approval_requested_at is None
        ):
            raise ValueError(
                "human approval requested live orders require request evidence"
            )
        if (
            self.stage
            in {
                LiveOrderLifecycleStage.READY_FOR_SUBMISSION,
                LiveOrderLifecycleStage.SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED,
                LiveOrderLifecycleStage.SUBMITTED,
                LiveOrderLifecycleStage.ACCEPTED,
                LiveOrderLifecycleStage.PARTIALLY_FILLED,
                LiveOrderLifecycleStage.FILLED,
                LiveOrderLifecycleStage.CANCEL_REQUESTED,
                LiveOrderLifecycleStage.CANCELLED,
            }
            and self.human_approved_at is None
        ):
            raise ValueError("approved live orders require approval evidence")
        if self.stage in {
            LiveOrderLifecycleStage.READY_FOR_SUBMISSION,
            LiveOrderLifecycleStage.SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED,
            LiveOrderLifecycleStage.SUBMITTED,
            LiveOrderLifecycleStage.ACCEPTED,
            LiveOrderLifecycleStage.PARTIALLY_FILLED,
            LiveOrderLifecycleStage.FILLED,
            LiveOrderLifecycleStage.CANCEL_REQUESTED,
            LiveOrderLifecycleStage.CANCELLED,
        } and (
            self.authorization_id is None or self.authorization_envelope_sha256 is None
        ):
            raise ValueError(
                "approved live orders require exact authorization evidence"
            )
        if (
            self.stage
            is LiveOrderLifecycleStage.SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED
            and self.submission_attempted_at is None
        ):
            raise ValueError("failed live order attempts require an attempt timestamp")
        if (
            self.stage
            in {
                LiveOrderLifecycleStage.SUBMITTED,
                LiveOrderLifecycleStage.ACCEPTED,
                LiveOrderLifecycleStage.PARTIALLY_FILLED,
                LiveOrderLifecycleStage.FILLED,
                LiveOrderLifecycleStage.CANCEL_REQUESTED,
                LiveOrderLifecycleStage.CANCELLED,
            }
            and self.submitted_at is None
        ):
            raise ValueError("submitted live orders require a submission timestamp")
        if (
            self.stage
            in {
                LiveOrderLifecycleStage.ACCEPTED,
                LiveOrderLifecycleStage.PARTIALLY_FILLED,
                LiveOrderLifecycleStage.FILLED,
                LiveOrderLifecycleStage.CANCEL_REQUESTED,
                LiveOrderLifecycleStage.CANCELLED,
            }
            and self.accepted_at is None
        ):
            raise ValueError(
                "accepted or terminal live orders require acceptance evidence"
            )
        if (
            self.stage
            in {
                LiveOrderLifecycleStage.PARTIALLY_FILLED,
                LiveOrderLifecycleStage.FILLED,
                LiveOrderLifecycleStage.CANCEL_REQUESTED,
                LiveOrderLifecycleStage.CANCELLED,
            }
            and self.requested_quantity is None
        ):
            raise ValueError("filled live orders require requested quantity evidence")
        if (
            self.requested_quantity is not None
            and self.stage
            in {
                LiveOrderLifecycleStage.PARTIALLY_FILLED,
                LiveOrderLifecycleStage.FILLED,
            }
            and self.filled_quantity > self.requested_quantity
        ):
            raise ValueError("live order fills cannot exceed requested quantity")
        if (
            self.stage is LiveOrderLifecycleStage.FILLED
            and self.requested_quantity is not None
            and self.filled_quantity != self.requested_quantity
        ):
            raise ValueError("filled live orders must match requested quantity")

    def _validate_fill_geometry(self) -> None:
        if self.filled_quantity == ZERO:
            return
        if self.stage not in {
            LiveOrderLifecycleStage.PARTIALLY_FILLED,
            LiveOrderLifecycleStage.FILLED,
            LiveOrderLifecycleStage.CANCEL_REQUESTED,
            LiveOrderLifecycleStage.CANCELLED,
        }:
            raise ValueError("fill evidence is only allowed after submission")


@dataclass(frozen=True, slots=True)
class LiveOrderLifecycleStateMachine:
    """Replay deterministic live-order lifecycle events."""

    @classmethod
    def replay(cls, events: tuple[DomainEvent, ...]) -> LiveOrderLifecycleRecord:
        if not events:
            raise ValueError("live order replay requires events")
        state: LiveOrderLifecycleRecord | None = None
        for event in events:
            state = cls.apply(state, event)
        if state is None:
            raise RuntimeError("live order replay did not produce state")
        return state

    @classmethod
    def apply(
        cls, state: LiveOrderLifecycleRecord | None, event: DomainEvent
    ) -> LiveOrderLifecycleRecord:
        payload = event.payload_dict()
        event_type = cls._event_type(event.event_type)
        if state is None:
            if event_type is not LiveOrderLifecycleEvent.PREVIEWED:
                raise ValueError("first live order event must be LIVE_ORDER_PREVIEWED")
            return LiveOrderLifecycleRecord(
                order_id=event.aggregate_id,
                symbol=_required_text(payload.get("symbol"), "symbol"),
                stage=LiveOrderLifecycleStage.PREVIEWED,
                preview_hash=_required_text(
                    payload.get("preview_hash"), "preview_hash"
                ),
                requested_quantity=_decimal_or_none(
                    payload.get("requested_quantity"), "requested_quantity"
                ),
                promoted_at=event.occurred_at,
                promotion_status=ValidationStatus.RESEARCH_ONLY,
                last_sequence=event.sequence,
            )
        cls._validate_identity_and_sequence(state, event)
        cls._validate_symbol_and_preview_hash(state, payload)
        if event_type is LiveOrderLifecycleEvent.PREVIEWED:
            raise ValueError("live order preview can only be recorded once")
        if event_type is LiveOrderLifecycleEvent.PROMOTION_REQUESTED:
            return cls._transition(
                state,
                event,
                stage=LiveOrderLifecycleStage.PROMOTION_REQUIRED,
                promotion_status=ValidationStatus.STAGED_CANDIDATE,
                promoted_at=event.occurred_at,
            )
        if event_type is LiveOrderLifecycleEvent.HUMAN_APPROVAL_REQUESTED:
            cls._require_stage(state, {LiveOrderLifecycleStage.PROMOTION_REQUIRED})
            return cls._transition(
                state,
                event,
                stage=LiveOrderLifecycleStage.HUMAN_APPROVAL_REQUIRED,
                promotion_status=ValidationStatus.STAGED_CANDIDATE,
                human_approval_requested_at=event.occurred_at,
            )
        if event_type is LiveOrderLifecycleEvent.HUMAN_APPROVED:
            cls._require_stage(state, {LiveOrderLifecycleStage.HUMAN_APPROVAL_REQUIRED})
            approval_id = _required_text(payload.get("approval_id"), "approval_id")
            authorization_id = _required_text(
                payload.get("authorization_id"), "authorization_id"
            )
            authorization_envelope_sha256 = _required_text(
                payload.get("authorization_envelope_sha256"),
                "authorization_envelope_sha256",
            )
            return cls._transition(
                state,
                event,
                stage=LiveOrderLifecycleStage.READY_FOR_SUBMISSION,
                approval_id=approval_id,
                authorization_id=authorization_id,
                authorization_envelope_sha256=authorization_envelope_sha256,
                promotion_status=ValidationStatus.PAPER_APPROVED,
                human_approved_at=event.occurred_at,
            )
        if event_type is LiveOrderLifecycleEvent.SUBMITTED:
            cls._require_stage(state, {LiveOrderLifecycleStage.READY_FOR_SUBMISSION})
            return cls._transition(
                state,
                event,
                stage=LiveOrderLifecycleStage.SUBMITTED,
                promotion_status=ValidationStatus.LIVE_ELIGIBLE,
                submission_attempted_at=event.occurred_at,
                submitted_at=event.occurred_at,
            )
        if event_type is LiveOrderLifecycleEvent.SUBMISSION_ATTEMPT_FAILED:
            cls._require_stage(state, {LiveOrderLifecycleStage.READY_FOR_SUBMISSION})
            _required_text(payload.get("blockers"), "blockers")
            return cls._transition(
                state,
                event,
                stage=(
                    LiveOrderLifecycleStage.SUBMISSION_ATTEMPT_FAILED_REVIEW_REQUIRED
                ),
                submission_attempted_at=event.occurred_at,
            )
        if event_type is LiveOrderLifecycleEvent.ACCEPTED:
            cls._require_stage(state, {LiveOrderLifecycleStage.SUBMITTED})
            return cls._transition(
                state,
                event,
                stage=LiveOrderLifecycleStage.ACCEPTED,
                accepted_at=event.occurred_at,
            )
        if event_type is LiveOrderLifecycleEvent.PARTIALLY_FILLED:
            cls._require_stage(
                state,
                {
                    LiveOrderLifecycleStage.ACCEPTED,
                    LiveOrderLifecycleStage.PARTIALLY_FILLED,
                },
            )
            return cls._apply_fill(state, event, partial=True)
        if event_type is LiveOrderLifecycleEvent.FILLED:
            cls._require_stage(
                state,
                {
                    LiveOrderLifecycleStage.ACCEPTED,
                    LiveOrderLifecycleStage.PARTIALLY_FILLED,
                },
            )
            return cls._apply_fill(state, event, partial=False)
        if event_type is LiveOrderLifecycleEvent.CANCEL_REQUESTED:
            cls._require_stage(
                state,
                {
                    LiveOrderLifecycleStage.SUBMITTED,
                    LiveOrderLifecycleStage.ACCEPTED,
                    LiveOrderLifecycleStage.PARTIALLY_FILLED,
                },
            )
            return cls._transition(
                state, event, stage=LiveOrderLifecycleStage.CANCEL_REQUESTED
            )
        if event_type is LiveOrderLifecycleEvent.CANCELLED:
            cls._require_stage(
                state,
                {
                    LiveOrderLifecycleStage.SUBMITTED,
                    LiveOrderLifecycleStage.ACCEPTED,
                    LiveOrderLifecycleStage.PARTIALLY_FILLED,
                    LiveOrderLifecycleStage.CANCEL_REQUESTED,
                },
            )
            return cls._transition(
                state, event, stage=LiveOrderLifecycleStage.CANCELLED
            )
        if event_type is LiveOrderLifecycleEvent.REJECTED:
            cls._require_stage(
                state,
                {
                    LiveOrderLifecycleStage.READY_FOR_SUBMISSION,
                    LiveOrderLifecycleStage.SUBMITTED,
                    LiveOrderLifecycleStage.ACCEPTED,
                    LiveOrderLifecycleStage.PARTIALLY_FILLED,
                },
            )
            return cls._transition(state, event, stage=LiveOrderLifecycleStage.REJECTED)
        if event_type is LiveOrderLifecycleEvent.EXPIRED:
            cls._require_stage(
                state,
                {
                    LiveOrderLifecycleStage.READY_FOR_SUBMISSION,
                    LiveOrderLifecycleStage.SUBMITTED,
                    LiveOrderLifecycleStage.ACCEPTED,
                    LiveOrderLifecycleStage.PARTIALLY_FILLED,
                },
            )
            return cls._transition(state, event, stage=LiveOrderLifecycleStage.EXPIRED)
        raise ValueError("unsupported live order event type")

    @staticmethod
    def _event_type(value: str) -> LiveOrderLifecycleEvent:
        try:
            return LiveOrderLifecycleEvent(value)
        except ValueError as error:
            raise ValueError("unsupported live order event type") from error

    @staticmethod
    def _validate_identity_and_sequence(
        state: LiveOrderLifecycleRecord, event: DomainEvent
    ) -> None:
        if event.aggregate_id != state.order_id:
            raise ValueError("live order event aggregate identity mismatch")
        if event.sequence != state.last_sequence + 1:
            raise ValueError("live order event sequence is not contiguous")

    @staticmethod
    def _validate_symbol_and_preview_hash(
        state: LiveOrderLifecycleRecord, payload: dict[str, str]
    ) -> None:
        symbol = payload.get("symbol")
        if symbol is not None and symbol.strip().upper() != state.symbol:
            raise ValueError("live order symbol mismatch")
        preview_hash = payload.get("preview_hash")
        if preview_hash is not None and preview_hash != state.preview_hash:
            raise ValueError("live order preview hash mismatch")
        authorization_id = payload.get("authorization_id")
        if (
            authorization_id is not None
            and state.authorization_id is not None
            and authorization_id != state.authorization_id
        ):
            raise ValueError("live order authorization ID mismatch")
        envelope_sha256 = payload.get("authorization_envelope_sha256")
        if (
            envelope_sha256 is not None
            and state.authorization_envelope_sha256 is not None
            and envelope_sha256 != state.authorization_envelope_sha256
        ):
            raise ValueError("live order authorization envelope mismatch")

    @staticmethod
    def _require_stage(
        state: LiveOrderLifecycleRecord, allowed: set[LiveOrderLifecycleStage]
    ) -> None:
        if state.stage not in allowed:
            raise ValueError("illegal live order state transition")

    @staticmethod
    def _transition(
        state: LiveOrderLifecycleRecord,
        event: DomainEvent,
        **changes: object,
    ) -> LiveOrderLifecycleRecord:
        return replace(state, last_sequence=event.sequence, **cast(Any, changes))

    @staticmethod
    def _apply_fill(
        state: LiveOrderLifecycleRecord,
        event: DomainEvent,
        *,
        partial: bool,
    ) -> LiveOrderLifecycleRecord:
        fill_quantity = _positive_decimal(
            event.payload_dict().get("fill_quantity"), "fill_quantity"
        )
        fill_price = _positive_decimal(
            event.payload_dict().get("fill_price"), "fill_price"
        )
        requested_quantity = state.requested_quantity
        next_quantity = state.filled_quantity + fill_quantity
        if requested_quantity is not None and next_quantity > requested_quantity:
            raise ValueError("live order fill exceeds requested quantity")
        if (
            not partial
            and requested_quantity is not None
            and next_quantity != requested_quantity
        ):
            raise ValueError("filled live orders must match requested quantity")
        if (
            partial
            and requested_quantity is not None
            and next_quantity >= requested_quantity
        ):
            raise ValueError("partial fill cannot complete the requested quantity")
        weighted_value = state.average_fill_price * state.filled_quantity
        average_price = (weighted_value + fill_price * fill_quantity) / next_quantity
        return replace(
            state,
            stage=(
                LiveOrderLifecycleStage.PARTIALLY_FILLED
                if partial
                else LiveOrderLifecycleStage.FILLED
            ),
            filled_quantity=next_quantity,
            average_fill_price=average_price,
            last_sequence=event.sequence,
        )


@dataclass(slots=True)
class LiveOrderLifecycleJournal:
    """Append live-order lifecycle replay events to a durable journal."""

    path: Path
    durable: bool = True

    def append_place_result(
        self,
        command: SpotOrderCommand,
        *,
        result: LiveCommandResult,
        observed_at: datetime,
    ) -> LiveOrderLifecycleRecord | None:
        if result.status is LiveCommandStatus.BLOCKED:
            return None
        events = build_place_events(
            command,
            result=result,
            observed_at=observed_at,
        )
        journal = DiskEventJournal(self.path, durable=self.durable)
        for event in events:
            journal.append(event)
        return LiveOrderLifecycleStateMachine.replay(events)


def build_place_events(
    command: SpotOrderCommand,
    *,
    result: LiveCommandResult,
    observed_at: datetime,
) -> tuple[DomainEvent, ...]:
    """Build the canonical live-order event chain for one consumed place attempt."""
    approval_id = _required_text(result.approval_id, "approval_id")
    authorization_id = _required_text(result.authorization_id, "authorization_id")
    authorization_envelope_sha256 = _required_text(
        result.authorization_envelope_sha256,
        "authorization_envelope_sha256",
    )
    payloads: tuple[tuple[LiveOrderLifecycleEvent, dict[str, str]], ...] = (
        (
            LiveOrderLifecycleEvent.PREVIEWED,
            {
                "symbol": command.symbol,
                "preview_hash": command.preview_hash,
                "requested_quantity": str(command.quantity),
                "client_order_id": command.client_order_id,
                "side": command.side,
                "order_type": command.order_type,
            },
        ),
        (
            LiveOrderLifecycleEvent.PROMOTION_REQUESTED,
            {
                "symbol": command.symbol,
                "preview_hash": command.preview_hash,
                "requested_quantity": str(command.quantity),
            },
        ),
        (
            LiveOrderLifecycleEvent.HUMAN_APPROVAL_REQUESTED,
            {
                "symbol": command.symbol,
                "preview_hash": command.preview_hash,
                "requested_quantity": str(command.quantity),
            },
        ),
        (
            LiveOrderLifecycleEvent.HUMAN_APPROVED,
            {
                "symbol": command.symbol,
                "preview_hash": command.preview_hash,
                "approval_id": approval_id,
                "authorization_id": authorization_id,
                "authorization_envelope_sha256": authorization_envelope_sha256,
            },
        ),
    )
    if result.status is LiveCommandStatus.ATTEMPT_FAILED:
        payloads += (
            (
                LiveOrderLifecycleEvent.SUBMISSION_ATTEMPT_FAILED,
                {
                    "symbol": command.symbol,
                    "preview_hash": command.preview_hash,
                    "approval_id": approval_id,
                    "authorization_id": authorization_id,
                    "authorization_envelope_sha256": (authorization_envelope_sha256),
                    "client_order_id": command.client_order_id,
                    "blockers": _required_text("|".join(result.blockers), "blockers"),
                },
            ),
        )
        return _build_events(command.client_order_id, payloads, observed_at)
    if result.status not in {
        LiveCommandStatus.SUBMITTED,
        LiveCommandStatus.UNVERIFIED_REVIEW_REQUIRED,
    }:
        raise ValueError("unsupported live order place result")
    payloads += (
        (
            LiveOrderLifecycleEvent.SUBMITTED,
            {
                "symbol": command.symbol,
                "preview_hash": command.preview_hash,
                "approval_id": approval_id,
                "authorization_id": authorization_id,
                "authorization_envelope_sha256": authorization_envelope_sha256,
                "exchange_order_id": result.exchange_order_id or "",
                "client_order_id": command.client_order_id,
            },
        ),
    )
    normalized_status = _snapshot_status(
        result.exchange_order_status,
        result.exchange_order_snapshot,
    )
    if normalized_status == "NEW":
        payloads += (
            (
                LiveOrderLifecycleEvent.ACCEPTED,
                {
                    "symbol": command.symbol,
                    "preview_hash": command.preview_hash,
                    "exchange_order_id": result.exchange_order_id or "",
                    "exchange_order_status": normalized_status,
                },
            ),
        )
    elif normalized_status == "PARTIALLY_FILLED":
        fill_quantity = _snapshot_decimal(
            result.exchange_order_snapshot,
            ("executedQty", "executed_qty"),
            "executedQty",
        )
        fill_price = _snapshot_fill_price(result.exchange_order_snapshot, fill_quantity)
        payloads += (
            (
                LiveOrderLifecycleEvent.ACCEPTED,
                {
                    "symbol": command.symbol,
                    "preview_hash": command.preview_hash,
                    "exchange_order_id": result.exchange_order_id or "",
                    "exchange_order_status": normalized_status,
                },
            ),
            (
                LiveOrderLifecycleEvent.PARTIALLY_FILLED,
                {
                    "symbol": command.symbol,
                    "preview_hash": command.preview_hash,
                    "exchange_order_id": result.exchange_order_id or "",
                    "exchange_order_status": normalized_status,
                    "fill_quantity": str(fill_quantity),
                    "fill_price": str(fill_price),
                },
            ),
        )
    elif normalized_status == "FILLED":
        fill_quantity = _snapshot_decimal(
            result.exchange_order_snapshot,
            ("executedQty", "executed_qty"),
            "executedQty",
        )
        fill_price = _snapshot_fill_price(result.exchange_order_snapshot, fill_quantity)
        payloads += (
            (
                LiveOrderLifecycleEvent.ACCEPTED,
                {
                    "symbol": command.symbol,
                    "preview_hash": command.preview_hash,
                    "exchange_order_id": result.exchange_order_id or "",
                    "exchange_order_status": normalized_status,
                },
            ),
            (
                LiveOrderLifecycleEvent.FILLED,
                {
                    "symbol": command.symbol,
                    "preview_hash": command.preview_hash,
                    "exchange_order_id": result.exchange_order_id or "",
                    "exchange_order_status": normalized_status,
                    "fill_quantity": str(fill_quantity),
                    "fill_price": str(fill_price),
                },
            ),
        )
    elif normalized_status in {"CANCELED", "EXPIRED", "REJECTED"}:
        terminal_event = {
            "CANCELED": LiveOrderLifecycleEvent.CANCELLED,
            "EXPIRED": LiveOrderLifecycleEvent.EXPIRED,
            "REJECTED": LiveOrderLifecycleEvent.REJECTED,
        }[normalized_status]
        payloads += (
            (
                terminal_event,
                {
                    "symbol": command.symbol,
                    "preview_hash": command.preview_hash,
                    "exchange_order_id": result.exchange_order_id or "",
                    "exchange_order_status": normalized_status,
                },
            ),
        )
    return _build_events(command.client_order_id, payloads, observed_at)


def _build_events(
    aggregate_id: str,
    payloads: tuple[tuple[LiveOrderLifecycleEvent, dict[str, str]], ...],
    observed_at: datetime,
) -> tuple[DomainEvent, ...]:
    events: list[DomainEvent] = []
    previous_hash = "GENESIS"
    for sequence, (event_type, payload) in enumerate(payloads, start=1):
        event = DomainEvent.create(
            event_id=f"{aggregate_id}:{event_type.value}:{sequence}",
            aggregate_id=aggregate_id,
            event_type=event_type.value,
            sequence=sequence,
            occurred_at=observed_at,
            payload=tuple(sorted(payload.items())),
            previous_hash=previous_hash,
        )
        events.append(event)
        previous_hash = event.event_hash
    return tuple(events)


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _decimal_or_none(value: object, name: str) -> Decimal | None:
    if value is None:
        return None
    return _positive_decimal(value, name)


def _positive_decimal(value: object, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be decimal-compatible") from None
    if not parsed.is_finite() or parsed <= ZERO:
        raise ValueError(f"{name} must be positive")
    return parsed


def _snapshot_status(
    exchange_order_status: str | None,
    exchange_order_snapshot: Mapping[str, object] | None,
) -> str | None:
    status = exchange_order_status
    if status is None and exchange_order_snapshot is not None:
        status = exchange_order_snapshot.get("status")  # type: ignore[assignment]
    if status is None:
        return None
    normalized = str(status).strip().upper()
    return normalized or None


def _snapshot_decimal(
    exchange_order_snapshot: Mapping[str, object] | None,
    keys: tuple[str, ...],
    name: str,
) -> Decimal:
    if exchange_order_snapshot is None:
        raise ValueError(f"{name} evidence is required")
    for key in keys:
        value = exchange_order_snapshot.get(key)
        if value is not None:
            return _positive_decimal(value, name)
    raise ValueError(f"{name} evidence is required")


def _snapshot_fill_price(
    exchange_order_snapshot: Mapping[str, object] | None,
    fill_quantity: Decimal,
) -> Decimal:
    if exchange_order_snapshot is None:
        raise ValueError("fill price evidence is required")
    for key in ("avgPrice", "avg_price", "averagePrice", "price"):
        value = exchange_order_snapshot.get(key)
        if value is not None:
            parsed = _positive_decimal(value, "fill_price")
            if parsed > ZERO:
                return parsed
    for quote_key in ("cummulativeQuoteQty", "cumQuote", "cumulativeQuoteQty"):
        quote = exchange_order_snapshot.get(quote_key)
        if quote is None:
            continue
        quote_value = _positive_decimal(quote, quote_key)
        return quote_value / fill_quantity
    raise ValueError("fill price evidence is required")

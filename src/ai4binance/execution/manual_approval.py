"""Manual financial action proposals with one approval boundary per action."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from ai4binance.reporting import to_primitive
from ai4binance.storage.destination_verification import fail_verification

ZERO = Decimal("0")


class ManualActionType(StrEnum):
    PLACE_SPOT_ORDER = "PLACE_SPOT_ORDER"
    PLACE_FUTURES_ORDER = "PLACE_FUTURES_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    REDUCE_SPOT_HOLDING = "REDUCE_SPOT_HOLDING"
    EXIT_SPOT_HOLDING = "EXIT_SPOT_HOLDING"
    CLOSE_FUTURES_POSITION = "CLOSE_FUTURES_POSITION"
    REDUCE_FUTURES_POSITION = "REDUCE_FUTURES_POSITION"
    TRANSFER_SPOT_TO_FUTURES = "TRANSFER_SPOT_TO_FUTURES"
    TRANSFER_FUTURES_TO_SPOT = "TRANSFER_FUTURES_TO_SPOT"
    CONVERT_ASSET = "CONVERT_ASSET"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ManualActionProposal:
    action_id: str
    action_type: ManualActionType
    asset_or_symbol: str
    suggested_notional_usdt: Decimal
    reason: str
    expected_effect: str
    risk: str
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    blockers: tuple[str, ...] = ("MANUAL_APPROVAL_REQUIRED",)
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.action_id,
                self.asset_or_symbol,
                self.reason,
                self.expected_effect,
                self.risk,
            )
        ):
            raise ValueError("manual action proposal identity is required")
        if (
            not self.suggested_notional_usdt.is_finite()
            or self.suggested_notional_usdt < ZERO
        ):
            raise ValueError("manual action notional must be non-negative")
        if any(not item.strip() for item in self.blockers):
            raise ValueError("manual action blockers cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("manual action cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    approval_id: str
    action_id: str
    action_type: ManualActionType
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.approval_id.strip() or not self.action_id.strip():
            raise ValueError("approval request identity is required")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("approval request cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class ApprovalQueueRecord:
    action: ManualActionProposal
    approval: ApprovalRequest
    created_at: datetime

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("approval queue timestamp must be timezone-aware")
        if self.action.action_id != self.approval.action_id:
            raise ValueError("approval record action IDs must match")
        if self.action.action_type is not self.approval.action_type:
            raise ValueError("approval record action types must match")


@dataclass(slots=True)
class LocalApprovalQueue:
    path: Path

    def enqueue(
        self,
        action: ManualActionProposal,
        *,
        approval_id: str | None = None,
        created_at: datetime | None = None,
    ) -> ApprovalQueueRecord:
        existing = self.by_action_id(action.action_id)
        if existing is not None:
            return existing
        approval = ApprovalRequest(
            approval_id or f"approval-{action.action_id}",
            action.action_id,
            action.action_type,
        )
        record = ApprovalQueueRecord(action, approval, created_at or datetime.now(UTC))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(to_primitive(record), sort_keys=True))
            stream.write("\n")
        observed = self.by_action_id(action.action_id)
        if observed != record:
            raise fail_verification(
                "APPROVAL_QUEUE_DESTINATION_VERIFY_FAILED",
                destination=self.path,
                subject_id=action.action_id,
            )
        return record

    def records(self) -> tuple[ApprovalQueueRecord, ...]:
        if not self.path.exists():
            return ()
        output: list[ApprovalQueueRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            output.append(self._record(json.loads(line)))
        return tuple(output)

    def by_action_id(self, action_id: str) -> ApprovalQueueRecord | None:
        normalized = action_id.strip()
        return next(
            (
                record
                for record in self.records()
                if record.action.action_id == normalized
            ),
            None,
        )

    @staticmethod
    def _record(payload: object) -> ApprovalQueueRecord:
        if not isinstance(payload, dict):
            raise ValueError("approval queue record must be an object")
        action_payload = payload.get("action")
        approval_payload = payload.get("approval")
        if not isinstance(action_payload, dict) or not isinstance(
            approval_payload,
            dict,
        ):
            raise ValueError("approval queue record payload is invalid")
        blockers_payload: Any = action_payload.get("blockers", ())
        blockers = (
            tuple(str(item) for item in blockers_payload)
            if isinstance(blockers_payload, list | tuple)
            else ("MANUAL_APPROVAL_REQUIRED",)
        )
        action = ManualActionProposal(
            str(action_payload["action_id"]),
            ManualActionType(str(action_payload["action_type"])),
            str(action_payload["asset_or_symbol"]),
            Decimal(str(action_payload["suggested_notional_usdt"])),
            str(action_payload["reason"]),
            str(action_payload["expected_effect"]),
            str(action_payload["risk"]),
            ApprovalStatus(str(action_payload["approval_status"])),
            blockers,
        )
        approval = ApprovalRequest(
            str(approval_payload["approval_id"]),
            str(approval_payload["action_id"]),
            ManualActionType(str(approval_payload["action_type"])),
            ApprovalStatus(str(approval_payload["approval_status"])),
        )
        return ApprovalQueueRecord(
            action,
            approval,
            datetime.fromisoformat(str(payload["created_at"])),
        )

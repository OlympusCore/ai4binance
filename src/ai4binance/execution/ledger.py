"""Append-only paper ledger with deterministic latest-state reconstruction."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from ai4binance.execution.lifecycle import (
    LifecycleExit,
    LifecyclePosition,
    PaperClosureReview,
    PositionStatus,
    StagedExitPlan,
)
from ai4binance.execution.paper import ExitReason
from ai4binance.reporting import to_primitive
from ai4binance.storage.jsonl import AuditEvent, JsonlAuditStore


@dataclass(frozen=True, slots=True)
class PaperLedger:
    path: Path
    _store: JsonlAuditStore = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_store", JsonlAuditStore(self.path, durable=True))

    def append(
        self,
        position: LifecyclePosition,
        *,
        event_type: str,
        timestamp: datetime,
    ) -> None:
        self._store.append(
            AuditEvent(
                event_type=event_type,
                timestamp=timestamp,
                payload={"position": to_primitive(position)},
            )
        )

    def latest_payload(self, position_id: str) -> dict[str, object] | None:
        if not self.path.exists():
            return None
        latest: dict[str, object] | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            payload = event.get("payload", {}).get("position", {})
            if payload.get("position_id") == position_id:
                latest = payload
        return latest

    def latest_position(self, position_id: str) -> LifecyclePosition | None:
        payload = self.latest_payload(position_id)
        if payload is None:
            return None
        plan = cast(Mapping[str, object], payload["plan"])
        exits_payload = cast(list[Mapping[str, object]], payload["exits"])
        review_payload = payload.get("closure_review")
        return LifecyclePosition(
            position_id=str(payload["position_id"]),
            candidate_id=str(payload["candidate_id"]),
            symbol=str(payload["symbol"]),
            opened_at=datetime.fromisoformat(str(payload["opened_at"])),
            entry_price=Decimal(str(payload["entry_price"])),
            entry_fee_usdt=Decimal(str(payload["entry_fee_usdt"])),
            initial_quantity=Decimal(str(payload["initial_quantity"])),
            remaining_quantity=Decimal(str(payload["remaining_quantity"])),
            stop_loss=Decimal(str(payload["stop_loss"])),
            trailing_stop=Decimal(str(payload["trailing_stop"])),
            atr=Decimal(str(payload["atr"])),
            plan=StagedExitPlan(
                targets=tuple(
                    Decimal(str(value))
                    for value in cast(Sequence[object], plan["targets"])
                ),
                quantity_ratios=tuple(
                    Decimal(str(value))
                    for value in cast(Sequence[object], plan["quantity_ratios"])
                ),
            ),
            status=PositionStatus(str(payload["status"])),
            next_target_index=int(str(payload["next_target_index"])),
            realized_pnl_usdt=Decimal(str(payload["realized_pnl_usdt"])),
            exits=tuple(self._exit_from_payload(item) for item in exits_payload),
            closure_review=(
                self._review_from_payload(cast(Mapping[str, object], review_payload))
                if review_payload is not None
                else None
            ),
        )

    @staticmethod
    def _exit_from_payload(payload: Mapping[str, object]) -> LifecycleExit:
        return LifecycleExit(
            timestamp=datetime.fromisoformat(str(payload["timestamp"])),
            reason=ExitReason(str(payload["reason"])),
            price=Decimal(str(payload["price"])),
            quantity=Decimal(str(payload["quantity"])),
            fee_usdt=Decimal(str(payload["fee_usdt"])),
            net_pnl_usdt=Decimal(str(payload["net_pnl_usdt"])),
        )

    @staticmethod
    def _review_from_payload(payload: Mapping[str, object]) -> PaperClosureReview:
        return PaperClosureReview(
            exit_reason=ExitReason(str(payload["exit_reason"])),
            lifecycle_error=(
                str(payload["lifecycle_error"])
                if payload["lifecycle_error"] is not None
                else None
            ),
            stop_quality=str(payload["stop_quality"]),
            trailing_quality=str(payload["trailing_quality"]),
            ignored_signals=int(str(payload["ignored_signals"])),
            htf_weakness=bool(payload["htf_weakness"]),
            volatility_expansion=bool(payload["volatility_expansion"]),
            level_break=bool(payload["level_break"]),
            staged_exit_alternative=str(payload["staged_exit_alternative"]),
            lesson_candidate=str(payload["lesson_candidate"]),
        )

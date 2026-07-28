"""Explicitly authorized Spot WebSocket order commands with internal live gating."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, cast

from ai4binance.domain import ExecutionStatus, LiveGateInput
from ai4binance.safety import evaluate_live_gate


class SpotOrderSession(Protocol):
    def order_test(self, params: Mapping[str, object]) -> object: ...

    def order_place(self, params: Mapping[str, object]) -> object: ...

    def order_cancel(self, params: Mapping[str, object]) -> object: ...


class LiveCommandStatus(StrEnum):
    BLOCKED = "LIVE_ORDER_BLOCKED"
    SUBMITTED = "LIVE_ORDER_SUBMITTED"
    CANCELLED = "LIVE_ORDER_CANCELLED"
    UNVERIFIED_REVIEW_REQUIRED = "LIVE_ORDER_UNVERIFIED_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class SpotOrderCommand:
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    client_order_id: str
    price: Decimal | None = None
    time_in_force: str | None = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        side = self.side.strip().upper()
        order_type = self.order_type.strip().upper()
        client_id = self.client_order_id.strip()
        if not symbol.isascii() or not symbol.isalnum():
            raise ValueError("order symbol must be ASCII alphanumeric")
        if side not in {"BUY", "SELL"} or order_type not in {"LIMIT", "MARKET"}:
            raise ValueError("unsupported Spot order side or type")
        if not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("order quantity must be finite and positive")
        if not client_id or len(client_id) > 36 or not client_id.isascii():
            raise ValueError("client order ID is invalid")
        if order_type == "LIMIT" and (
            self.price is None
            or not self.price.is_finite()
            or self.price <= 0
            or self.time_in_force not in {"GTC", "IOC", "FOK"}
        ):
            raise ValueError("LIMIT order requires valid price and time-in-force")
        if order_type == "MARKET" and (
            self.price is not None or self.time_in_force is not None
        ):
            raise ValueError("MARKET order cannot contain price or time-in-force")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "order_type", order_type)
        object.__setattr__(self, "client_order_id", client_id)

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "quantity": str(self.quantity),
            "newClientOrderId": self.client_order_id,
            "newOrderRespType": "FULL",
        }
        if self.price is not None:
            payload["price"] = str(self.price)
        if self.time_in_force is not None:
            payload["timeInForce"] = self.time_in_force
        return payload

    @property
    def preview_hash(self) -> str:
        encoded = json.dumps(
            self.payload(), separators=(",", ":"), sort_keys=True
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class OrderDestinationVerification:
    verified: bool
    blockers: tuple[str, ...] = ()

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
        return OrderDestinationVerification.accepted()

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
        return OrderDestinationVerification.accepted()

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


@dataclass(frozen=True, slots=True)
class GatedSpotOrderExecutor:
    session: SpotOrderSession
    verifier: SpotOrderVerifier | None = None

    def place(
        self,
        command: SpotOrderCommand,
        gate_input: LiveGateInput,
        *,
        approved_preview_hash: str | None,
    ) -> LiveCommandResult:
        gate = evaluate_live_gate(gate_input)
        blockers = list(gate.blockers)
        if approved_preview_hash != command.preview_hash:
            blockers.append("ORDER_PREVIEW_HASH_NOT_APPROVED")
        if gate.status is not ExecutionStatus.EXECUTION_ALLOWED or blockers:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                tuple(dict.fromkeys(blockers)),
                command.client_order_id,
                preview_hash=command.preview_hash,
            )
        if self.verifier is None:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("ORDER_DESTINATION_VERIFIER_UNAVAILABLE",),
                command.client_order_id,
                preview_hash=command.preview_hash,
            )
        payload = command.payload()
        self.session.order_test(payload)
        response = self.session.order_place(payload)
        order_id = _exchange_order_id(response)
        verification = self.verifier.verify_placed(command, order_id)
        if not verification.verified:
            return LiveCommandResult(
                LiveCommandStatus.UNVERIFIED_REVIEW_REQUIRED,
                verification.blockers,
                command.client_order_id,
                order_id,
                command.preview_hash,
            )
        return LiveCommandResult(
            LiveCommandStatus.SUBMITTED,
            (),
            command.client_order_id,
            order_id,
            command.preview_hash,
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
            )
        return LiveCommandResult(
            LiveCommandStatus.CANCELLED,
            (),
            normalized_id,
            order_id,
        )


def _exchange_order_id(value: object) -> str:
    if not isinstance(value, Mapping):
        raise RuntimeError("exchange order response must be an object")
    response = cast(Mapping[str, object], value)
    order_id = response.get("orderId")
    if order_id is None or not str(order_id).strip():
        raise RuntimeError("exchange order response has no orderId")
    return str(order_id)

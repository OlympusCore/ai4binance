"""Exact-order, expiring, single-use authorization for Spot placement."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

from ai4binance.execution.order_command import SpotOrderCommand

ZERO = Decimal("0")


class ExecutionAuthorizationSource(Protocol):
    """Resolve only a human-approved authorization record."""

    def resolve_execution_authorization(
        self, authorization_id: str
    ) -> ExecutionAuthorizationEnvelope | None: ...


@dataclass(frozen=True, slots=True)
class ExecutionAuthorizationEnvelope:
    """Immutable human authorization bound to one exact Spot order."""

    authorization_id: str
    approval_id: str
    preview_hash: str
    decision_id: str
    snapshot_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    market_type: str
    side: str
    order_type: str
    quantity: Decimal
    client_order_id: str
    risk_assessment_hash: str
    validation_bundle_hash: str
    created_at: datetime
    expires_at: datetime
    approved_by: str
    single_use_nonce: str
    price: Decimal | None = None
    time_in_force: str | None = None
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        text_fields = (
            "authorization_id",
            "approval_id",
            "decision_id",
            "snapshot_id",
            "strategy_id",
            "strategy_version",
            "client_order_id",
            "approved_by",
            "single_use_nonce",
        )
        for field_name in text_fields:
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "preview_hash", _sha256(self.preview_hash))
        object.__setattr__(
            self,
            "risk_assessment_hash",
            _sha256(self.risk_assessment_hash),
        )
        object.__setattr__(
            self,
            "validation_bundle_hash",
            _sha256(self.validation_bundle_hash),
        )
        symbol = self.symbol.strip().upper()
        market_type = self.market_type.strip().upper()
        side = self.side.strip().upper()
        order_type = self.order_type.strip().upper()
        if not symbol.isascii() or not symbol.isalnum():
            raise ValueError("authorization symbol must be ASCII alphanumeric")
        if market_type != "SPOT":
            raise ValueError("authorization market type must be SPOT")
        if side not in {"BUY", "SELL"}:
            raise ValueError("authorization side is invalid")
        if order_type not in {"LIMIT", "MARKET"}:
            raise ValueError("authorization order type is invalid")
        if not self.quantity.is_finite() or self.quantity <= ZERO:
            raise ValueError("authorization quantity must be finite and positive")
        time_in_force = (
            self.time_in_force.strip().upper()
            if self.time_in_force is not None
            else None
        )
        if order_type == "LIMIT" and (
            self.price is None
            or not self.price.is_finite()
            or self.price <= ZERO
            or time_in_force not in {"GTC", "IOC", "FOK"}
        ):
            raise ValueError("LIMIT authorization requires exact price constraints")
        if order_type == "MARKET" and (
            self.price is not None or time_in_force is not None
        ):
            raise ValueError("MARKET authorization cannot contain price constraints")
        created_at = _aware_utc(self.created_at, "created_at")
        expires_at = _aware_utc(self.expires_at, "expires_at")
        if expires_at <= created_at:
            raise ValueError("authorization expiry must follow creation")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("authorization envelope cannot grant execution authority")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "market_type", market_type)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "order_type", order_type)
        object.__setattr__(self, "time_in_force", time_in_force)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)

    @property
    def envelope_sha256(self) -> str:
        encoded = json.dumps(
            self.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_payload(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "approved_by": self.approved_by,
            "authorization_id": self.authorization_id,
            "client_order_id": self.client_order_id,
            "created_at": _timestamp(self.created_at),
            "decision_id": self.decision_id,
            "execution_allowed": False,
            "expires_at": _timestamp(self.expires_at),
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "market_type": self.market_type,
            "order_type": self.order_type,
            "preview_hash": self.preview_hash,
            "price": str(self.price) if self.price is not None else None,
            "quantity": str(self.quantity),
            "risk_assessment_hash": self.risk_assessment_hash,
            "side": self.side,
            "single_use_nonce": self.single_use_nonce,
            "snapshot_id": self.snapshot_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "time_in_force": self.time_in_force,
            "validation_bundle_hash": self.validation_bundle_hash,
        }

    @classmethod
    def from_payload(cls, payload: object) -> ExecutionAuthorizationEnvelope:
        if not isinstance(payload, Mapping):
            raise ValueError("execution authorization envelope must be an object")
        required = {
            "approval_id",
            "approved_by",
            "authorization_id",
            "client_order_id",
            "created_at",
            "decision_id",
            "expires_at",
            "market_type",
            "order_type",
            "preview_hash",
            "price",
            "quantity",
            "risk_assessment_hash",
            "side",
            "single_use_nonce",
            "snapshot_id",
            "strategy_id",
            "strategy_version",
            "symbol",
            "time_in_force",
            "validation_bundle_hash",
        }
        optional = {"execution_allowed", "live_eligibility_status"}
        keys = {str(key) for key in payload}
        if required - keys or keys - required - optional:
            raise ValueError("execution authorization envelope fields are invalid")
        return cls(
            authorization_id=str(payload["authorization_id"]),
            approval_id=str(payload["approval_id"]),
            preview_hash=str(payload["preview_hash"]),
            decision_id=str(payload["decision_id"]),
            snapshot_id=str(payload["snapshot_id"]),
            strategy_id=str(payload["strategy_id"]),
            strategy_version=str(payload["strategy_version"]),
            symbol=str(payload["symbol"]),
            market_type=str(payload["market_type"]),
            side=str(payload["side"]),
            order_type=str(payload["order_type"]),
            quantity=_decimal(payload["quantity"], "quantity"),
            client_order_id=str(payload["client_order_id"]),
            risk_assessment_hash=str(payload["risk_assessment_hash"]),
            validation_bundle_hash=str(payload["validation_bundle_hash"]),
            created_at=_datetime(payload["created_at"], "created_at"),
            expires_at=_datetime(payload["expires_at"], "expires_at"),
            approved_by=str(payload["approved_by"]),
            single_use_nonce=str(payload["single_use_nonce"]),
            price=(
                _decimal(payload["price"], "price")
                if payload["price"] is not None
                else None
            ),
            time_in_force=(
                str(payload["time_in_force"])
                if payload["time_in_force"] is not None
                else None
            ),
            execution_allowed=bool(payload.get("execution_allowed", False)),
            live_eligibility_status=str(
                payload.get("live_eligibility_status", "LIVE_ORDER_BLOCKED")
            ),
        )

    def blockers_for(
        self,
        command: SpotOrderCommand,
        *,
        observed_at: datetime,
    ) -> tuple[str, ...]:
        now = _aware_utc(observed_at, "observed_at")
        blockers: list[str] = []
        if now < self.created_at:
            blockers.append("EXECUTION_AUTHORIZATION_NOT_YET_VALID")
        if now >= self.expires_at:
            blockers.append("EXECUTION_AUTHORIZATION_EXPIRED")
        comparisons = (
            (self.preview_hash, command.preview_hash, "PREVIEW_HASH"),
            (self.symbol, command.symbol, "SYMBOL"),
            (self.side, command.side, "SIDE"),
            (self.order_type, command.order_type, "ORDER_TYPE"),
            (self.quantity, command.quantity, "QUANTITY"),
            (self.price, command.price, "PRICE"),
            (self.time_in_force, command.time_in_force, "TIME_IN_FORCE"),
            (self.client_order_id, command.client_order_id, "CLIENT_ORDER_ID"),
        )
        for authorized, requested, label in comparisons:
            if authorized != requested:
                blockers.append(f"EXECUTION_AUTHORIZATION_{label}_MISMATCH")
        return tuple(blockers)

    def to_spot_order_command(self) -> SpotOrderCommand:
        """Build the only order command this authorization can represent."""
        return SpotOrderCommand(
            symbol=self.symbol,
            side=self.side,
            order_type=self.order_type,
            quantity=self.quantity,
            client_order_id=self.client_order_id,
            price=self.price,
            time_in_force=self.time_in_force,
        )


@dataclass(frozen=True, slots=True)
class ExecutionAuthorizationConsumption:
    authorization_id: str
    single_use_nonce: str
    envelope_sha256: str
    preview_hash: str
    execution_id: str
    claimed_at: datetime
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        for field_name in (
            "authorization_id",
            "single_use_nonce",
            "execution_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        object.__setattr__(self, "envelope_sha256", _sha256(self.envelope_sha256))
        object.__setattr__(self, "preview_hash", _sha256(self.preview_hash))
        object.__setattr__(
            self,
            "claimed_at",
            _aware_utc(self.claimed_at, "claimed_at"),
        )
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("authorization consumption cannot grant authority")


class ExecutionAuthorizationAlreadyConsumedError(RuntimeError):
    """Raised when an exact authorization or its nonce was already claimed."""


class ExecutionAuthorizationLedgerUnavailableError(RuntimeError):
    """Raised when durable single-use consumption cannot be proven."""


@dataclass(frozen=True, slots=True)
class LocalExecutionAuthorizationLedger:
    """Durably and atomically claim an authorization before exchange contact."""

    path: Path
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("authorization ledger timeout must be positive")

    def claim(
        self,
        envelope: ExecutionAuthorizationEnvelope,
        *,
        execution_id: str,
        claimed_at: datetime,
    ) -> ExecutionAuthorizationConsumption:
        normalized_execution_id = _required_text(execution_id, "execution_id")
        normalized_claimed_at = _aware_utc(claimed_at, "claimed_at")
        connection: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self.path,
                timeout=self.timeout_seconds,
                isolation_level=None,
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_authorization_consumption (
                    authorization_id TEXT PRIMARY KEY,
                    single_use_nonce TEXT NOT NULL UNIQUE,
                    envelope_sha256 TEXT NOT NULL,
                    preview_hash TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                )
                """
            )
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO execution_authorization_consumption (
                    authorization_id,
                    single_use_nonce,
                    envelope_sha256,
                    preview_hash,
                    execution_id,
                    claimed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    envelope.authorization_id,
                    envelope.single_use_nonce,
                    envelope.envelope_sha256,
                    envelope.preview_hash,
                    normalized_execution_id,
                    _timestamp(normalized_claimed_at),
                ),
            )
            row = connection.execute(
                """
                SELECT authorization_id, single_use_nonce, envelope_sha256,
                       preview_hash, execution_id, claimed_at
                FROM execution_authorization_consumption
                WHERE authorization_id = ?
                """,
                (envelope.authorization_id,),
            ).fetchone()
            expected = (
                envelope.authorization_id,
                envelope.single_use_nonce,
                envelope.envelope_sha256,
                envelope.preview_hash,
                normalized_execution_id,
                _timestamp(normalized_claimed_at),
            )
            if row != expected:
                raise ExecutionAuthorizationLedgerUnavailableError(
                    "authorization ledger destination verification failed"
                )
            connection.execute("COMMIT")
        except sqlite3.IntegrityError as error:
            if connection is not None and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ExecutionAuthorizationAlreadyConsumedError(
                "execution authorization was already consumed"
            ) from error
        except (OSError, sqlite3.Error) as error:
            if connection is not None and connection.in_transaction:
                connection.execute("ROLLBACK")
            raise ExecutionAuthorizationLedgerUnavailableError(
                "execution authorization ledger is unavailable"
            ) from error
        finally:
            if connection is not None:
                connection.close()
        return ExecutionAuthorizationConsumption(
            authorization_id=envelope.authorization_id,
            single_use_nonce=envelope.single_use_nonce,
            envelope_sha256=envelope.envelope_sha256,
            preview_hash=envelope.preview_hash,
            execution_id=normalized_execution_id,
            claimed_at=normalized_claimed_at,
        )

    def is_consumed(self, authorization_id: str) -> bool:
        if not self.path.exists():
            return False
        try:
            with closing(
                sqlite3.connect(self.path, timeout=self.timeout_seconds)
            ) as connection:
                with connection:
                    row = connection.execute(
                        """
                        SELECT 1
                        FROM execution_authorization_consumption
                        WHERE authorization_id = ?
                        """,
                        (_required_text(authorization_id, "authorization_id"),),
                    ).fetchone()
        except sqlite3.Error as error:
            raise ExecutionAuthorizationLedgerUnavailableError(
                "execution authorization ledger is unavailable"
            ) from error
        return row is not None


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value).strip()
    if (
        not normalized
        or len(normalized) > 256
        or not normalized.isascii()
        or any(character in normalized for character in "\r\n\0")
    ):
        raise ValueError(f"authorization {field_name} is invalid")
    return normalized


def _sha256(value: object) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError("authorization SHA-256 is invalid")
    return normalized


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"authorization {field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _datetime(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"authorization {field_name} is invalid") from None
    return _aware_utc(parsed, field_name)


def _decimal(value: object, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"authorization {field_name} is invalid") from None
    if not parsed.is_finite():
        raise ValueError(f"authorization {field_name} must be finite")
    return parsed


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

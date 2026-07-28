"""Explicit Spot live preview/place CLI handlers."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import cast

from ai4binance.config import Settings
from ai4binance.domain import ExecutionStatus
from ai4binance.exchange import (
    BinanceEd25519SpotSession,
    BinancePrivateAccountReader,
    BinancePublicClient,
    BinanceSpotWsConnection,
    Ed25519Credentials,
    PrivateCredentials,
    SignedReadOnlyRequestFactory,
    UrllibJsonTransport,
    UrllibPrivateJsonTransport,
)
from ai4binance.execution import (
    GatedSpotOrderExecutor,
    LiveReadinessBuilder,
    LiveReadinessEvidence,
    LocalApprovalQueue,
    ReadOnlySpotOrderHistoryVerifier,
    SpotOrderPreview,
    SpotOrderPreviewBuilder,
)
from ai4binance.ops.binance_preflight import build_preflight_report
from ai4binance.reporting import to_primitive
from ai4binance.validation import ValidationSummaryReader


def run_live_preview_spot(
    settings: Settings,
    *,
    confirm_live: bool,
    symbol: str | None,
    side: str | None,
    order_type: str | None,
    quantity: str | None,
    client_order_id: str | None,
    price: str | None,
    time_in_force: str | None,
    approval_id: str | None,
) -> int:
    payload = live_preview_payload(
        settings,
        confirm_live=confirm_live,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        client_order_id=client_order_id,
        price=price,
        time_in_force=time_in_force,
        approval_id=approval_id,
    )
    payload.pop("_preview", None)
    print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
    return 0 if not payload["blockers"] else 2


def run_live_place_spot(
    settings: Settings,
    *,
    confirm_live: bool,
    symbol: str | None,
    side: str | None,
    order_type: str | None,
    quantity: str | None,
    client_order_id: str | None,
    price: str | None,
    time_in_force: str | None,
    approval_id: str | None,
    approved_preview_hash: str | None,
) -> int:
    payload = live_preview_payload(
        settings,
        confirm_live=confirm_live,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        client_order_id=client_order_id,
        price=price,
        time_in_force=time_in_force,
        approval_id=approval_id,
    )
    preview = cast(SpotOrderPreview | None, payload.get("_preview"))
    payload.pop("_preview", None)
    readiness = cast(LiveReadinessEvidence, payload["readiness"])
    if preview is None or approved_preview_hash != preview.preview_hash:
        payload["blockers"] = tuple(
            dict.fromkeys(
                (
                    *cast(tuple[str, ...], payload["blockers"]),
                    "ORDER_PREVIEW_HASH_NOT_APPROVED",
                )
            )
        )
        print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
        return 2
    readiness_payload = cast(dict[str, object], to_primitive(readiness))
    gate_status = cast(dict[str, object], readiness_payload["gate_result"])["status"]
    if gate_status != ExecutionStatus.EXECUTION_ALLOWED.value:
        print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
        return 2
    connection = BinanceSpotWsConnection(url=settings.spot_ws_api_url)
    try:
        session = BinanceEd25519SpotSession(
            connection,
            Ed25519Credentials.from_environment(),
        )
        session.logon()
        reader = _private_reader(settings)
        result = GatedSpotOrderExecutor(
            session,
            ReadOnlySpotOrderHistoryVerifier(reader),
        ).place(
            preview.command,
            readiness.gate_input,
            approved_preview_hash=approved_preview_hash,
        )
        payload["live_command_result"] = result
        payload["blockers"] = result.blockers
        print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
        return 0 if not result.blockers else 2
    except (OSError, RuntimeError, ValueError):
        payload["blockers"] = tuple(
            dict.fromkeys(
                (
                    *cast(tuple[str, ...], payload["blockers"]),
                    "LIVE_SPOT_SESSION_UNAVAILABLE",
                )
            )
        )
        print(json.dumps(to_primitive(payload), ensure_ascii=False, sort_keys=True))
        return 2
    finally:
        connection.close()


def live_preview_payload(
    settings: Settings,
    *,
    confirm_live: bool,
    symbol: str | None,
    side: str | None,
    order_type: str | None,
    quantity: str | None,
    client_order_id: str | None,
    price: str | None,
    time_in_force: str | None,
    approval_id: str | None,
) -> dict[str, object]:
    blockers = _missing_order_fields(side, order_type, quantity, client_order_id)
    if blockers:
        return _blocked_payload("live-preview-spot", blockers)
    normalized_symbol = (symbol or settings.symbol).strip().upper()
    try:
        parsed_quantity = _decimal(quantity or "0", "quantity")
        parsed_price = _decimal(price, "price") if price is not None else None
    except ValueError as error:
        return _blocked_payload("live-preview-spot", (str(error),))
    try:
        preview = SpotOrderPreviewBuilder(_public_client(settings)).build(
            symbol=normalized_symbol,
            side=side or "",
            order_type=order_type or "",
            quantity=parsed_quantity,
            client_order_id=client_order_id or "",
            price=parsed_price,
            time_in_force=time_in_force,
        )
    except ValueError as error:
        return _blocked_payload("live-preview-spot", (str(error),))
    preflight = build_preflight_report(
        credential_file=settings.private_credentials_file,
        timeout_seconds=settings.request_timeout_seconds,
    )
    open_orders = _open_orders(settings, normalized_symbol)
    validation = ValidationSummaryReader(
        settings.validation_artifact_directory
    ).summarize(normalized_symbol)
    readiness = LiveReadinessBuilder(
        settings,
        LocalApprovalQueue(settings.manual_approval_queue_path),
    ).build(
        preview=preview,
        confirm_live=confirm_live,
        approval_id=approval_id,
        preflight_report=preflight,
        open_orders=open_orders,
        validation_summary=validation,
    )
    return {
        "command": "live-preview-spot",
        "preview": preview,
        "readiness": readiness,
        "validation_summary": validation,
        "preflight": preflight,
        "blockers": readiness.blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "_preview": preview,
    }


def _public_client(settings: Settings) -> BinancePublicClient:
    return BinancePublicClient(
        UrllibJsonTransport(
            base_url=settings.public_api_base_url,
            timeout_seconds=settings.request_timeout_seconds,
            max_attempts=settings.request_max_attempts,
            backoff_seconds=settings.request_backoff_seconds,
        )
    )


def _private_reader(settings: Settings) -> BinancePrivateAccountReader:
    credentials = PrivateCredentials.from_environment_or_file(
        settings.private_credentials_file
    )
    return BinancePrivateAccountReader(
        SignedReadOnlyRequestFactory(credentials),
        UrllibPrivateJsonTransport(
            timeout_seconds=settings.request_timeout_seconds,
            max_attempts=settings.request_max_attempts,
            backoff_seconds=settings.request_backoff_seconds,
        ),
    )


def _open_orders(settings: Settings, symbol: str) -> object:
    try:
        return _private_reader(settings).open_orders(symbol)
    except (OSError, RuntimeError, ValueError):
        return None


def _missing_order_fields(
    side: str | None,
    order_type: str | None,
    quantity: str | None,
    client_order_id: str | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if side is None:
        blockers.append("ORDER_SIDE_REQUIRED")
    if order_type is None:
        blockers.append("ORDER_TYPE_REQUIRED")
    if quantity is None:
        blockers.append("ORDER_QUANTITY_REQUIRED")
    if client_order_id is None:
        blockers.append("CLIENT_ORDER_ID_REQUIRED")
    return tuple(blockers)


def _decimal(value: str | None, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} is required")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{field_name} must be decimal") from None
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _blocked_payload(command: str, blockers: tuple[str, ...]) -> dict[str, object]:
    return {
        "command": command,
        "blockers": blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

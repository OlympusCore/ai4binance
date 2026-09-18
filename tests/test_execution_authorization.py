"""Exact Spot execution authorization stays immutable and single-use."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypedDict, Unpack

import pytest

from ai4binance.domain import LiveGateInput, ValidationStatus
from ai4binance.execution import (
    ApprovalQueueRecord,
    ApprovalRequest,
    ApprovalStatus,
    ExecutionAuthorizationAlreadyConsumedError,
    ExecutionAuthorizationEnvelope,
    ExecutionAuthorizationLedgerUnavailableError,
    GatedSpotOrderExecutor,
    LiveCommandStatus,
    LocalApprovalQueue,
    LocalExecutionAuthorizationLedger,
    ManualActionProposal,
    ManualActionType,
    OrderDestinationVerification,
    SpotOrderCommand,
)
from ai4binance.execution.live_spot import (
    SpotOrderCommand as LegacySpotOrderCommand,
)
from ai4binance.execution.order_command import (
    SpotOrderCommand as CanonicalSpotOrderCommand,
)
from ai4binance.reporting import to_primitive
from ai4binance.validation.live_gate_evidence import (
    LiveGateEvidenceKind,
    LiveGateEvidenceRecord,
    LiveGateEvidenceRegistry,
    LiveGateEvidenceSourceKind,
    LiveGateEvidenceVerificationStatus,
)
from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceQuery,
    PromotionEvidenceRecord,
    PromotionEvidenceRegistry,
    PromotionEvidenceSourceKind,
)


class AuthorizationConnectOptions(TypedDict, total=False):
    timeout: float


NOW = datetime(2026, 9, 9, 3, 30, tzinfo=UTC)
EVIDENCE_QUERY = PromotionEvidenceQuery(
    strategy_id="trend-continuation",
    strategy_version="1.0.0",
    strategy_sha256="1" * 64,
    symbol="HOTUSDT",
    market_type="SPOT",
    timeframe="15m",
    parameter_set_sha256="2" * 64,
    dataset_sha256="3" * 64,
    code_revision="4" * 40,
    as_of=NOW,
)


def live_gate_registry() -> LiveGateEvidenceRegistry:
    return LiveGateEvidenceRegistry(
        tuple(
            LiveGateEvidenceRecord(
                evidence_id=f"live-gate-{kind.value.lower()}",
                evidence_kind=kind,
                source_kind=LiveGateEvidenceSourceKind.GOVERNED_ARTIFACT,
                source_ref=f"governed://validation/{kind.value.lower()}",
                artifact_sha256={
                    LiveGateEvidenceKind.BACKTEST: "a" * 64,
                    LiveGateEvidenceKind.WALK_FORWARD: "b" * 64,
                    LiveGateEvidenceKind.TUNING: "c" * 64,
                    LiveGateEvidenceKind.OOS: "d" * 64,
                }[kind],
                observed_at=NOW,
                verification_status=LiveGateEvidenceVerificationStatus.VERIFIED,
                strategy_id=EVIDENCE_QUERY.strategy_id,
                strategy_version=EVIDENCE_QUERY.strategy_version,
                strategy_sha256=EVIDENCE_QUERY.strategy_sha256,
                symbol=EVIDENCE_QUERY.symbol,
                market_type=EVIDENCE_QUERY.market_type,
                timeframe=EVIDENCE_QUERY.timeframe,
                parameter_set_sha256=EVIDENCE_QUERY.parameter_set_sha256,
                dataset_sha256=EVIDENCE_QUERY.dataset_sha256,
                code_revision=EVIDENCE_QUERY.code_revision,
            )
            for kind in LiveGateEvidenceKind
        )
    )


def promotion_registry() -> PromotionEvidenceRegistry:
    return PromotionEvidenceRegistry(
        (
            PromotionEvidenceRecord(
                evidence_id="promotion-live-eligible",
                symbol=EVIDENCE_QUERY.symbol,
                source_kind=PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
                source_ref="governed://promotion/live-eligible",
                observed_at=NOW,
                promotion_status=ValidationStatus.LIVE_ELIGIBLE,
                timeframe=EVIDENCE_QUERY.timeframe,
                strategy_id=EVIDENCE_QUERY.strategy_id,
                strategy_version=EVIDENCE_QUERY.strategy_version,
                strategy_sha256=EVIDENCE_QUERY.strategy_sha256,
                market_type=EVIDENCE_QUERY.market_type,
                parameter_set_sha256=EVIDENCE_QUERY.parameter_set_sha256,
                dataset_sha256=EVIDENCE_QUERY.dataset_sha256,
                code_revision=EVIDENCE_QUERY.code_revision,
            ),
        )
    )


def validation_bundle_sha256() -> str:
    bundle = live_gate_registry().canonical_bundle_sha256(query=EVIDENCE_QUERY)
    assert bundle is not None
    return bundle


def order() -> SpotOrderCommand:
    return SpotOrderCommand(
        "HOTUSDT",
        "BUY",
        "LIMIT",
        Decimal("1000"),
        "auth-order-1",
        Decimal("0.01"),
        "GTC",
    )


def authorization(
    *,
    authorization_id: str = "authorization-1",
    approval_id: str = "approval-1",
    nonce: str = "nonce-1",
    created_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(minutes=5),
) -> ExecutionAuthorizationEnvelope:
    command = order()
    return ExecutionAuthorizationEnvelope(
        authorization_id=authorization_id,
        approval_id=approval_id,
        preview_hash=command.preview_hash,
        decision_id="decision-1",
        snapshot_id="snapshot-1",
        strategy_id="trend-continuation",
        strategy_version="1.0.0",
        symbol=command.symbol,
        market_type="SPOT",
        side=command.side,
        order_type=command.order_type,
        quantity=command.quantity,
        client_order_id=command.client_order_id,
        risk_assessment_hash="1" * 64,
        validation_bundle_hash=validation_bundle_sha256(),
        created_at=created_at,
        expires_at=expires_at,
        approved_by="GovernanceOwner:test",
        single_use_nonce=nonce,
        price=command.price,
        time_in_force=command.time_in_force,
    )


def approval_record(
    envelope: ExecutionAuthorizationEnvelope,
    *,
    status: ApprovalStatus = ApprovalStatus.APPROVED,
    created_at: datetime = NOW,
) -> ApprovalQueueRecord:
    action = ManualActionProposal(
        "spot-hot-buy",
        ManualActionType.PLACE_SPOT_ORDER,
        envelope.symbol,
        Decimal("10"),
        "Authorize one exact Spot order.",
        "Place only the exact immutable preview.",
        "Live Spot risk remains gate controlled.",
        approval_status=status,
    )
    approval = ApprovalRequest(
        envelope.approval_id,
        action.action_id,
        action.action_type,
        status,
    )
    return ApprovalQueueRecord(action, approval, created_at, envelope)


def write_records(path: Path, *records: ApprovalQueueRecord) -> None:
    path.write_text(
        "".join(
            json.dumps(to_primitive(record), sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def all_live_gates() -> LiveGateInput:
    return LiveGateInput(**{field.name: True for field in fields(LiveGateInput)})


class AuthorizationSource:
    def __init__(self, envelope: ExecutionAuthorizationEnvelope | None) -> None:
        self.envelope = envelope

    def resolve_execution_authorization(
        self, authorization_id: str
    ) -> ExecutionAuthorizationEnvelope | None:
        if (
            self.envelope is not None
            and self.envelope.authorization_id == authorization_id
        ):
            return self.envelope
        return None


class NeverCalledSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def order_test(self, params: object) -> object:
        del params
        self.calls.append("test")
        return {}

    def order_place(self, params: object) -> object:
        del params
        self.calls.append("place")
        return {"orderId": 1}

    def order_cancel(self, params: object) -> object:
        del params
        self.calls.append("cancel")
        return {"orderId": 1}


class AcceptingVerifier:
    def verify_placed(
        self, command: SpotOrderCommand, exchange_order_id: str
    ) -> OrderDestinationVerification:
        del command, exchange_order_id
        return OrderDestinationVerification.accepted()

    def verify_cancelled(
        self, *, symbol: str, client_order_id: str, exchange_order_id: str
    ) -> OrderDestinationVerification:
        del symbol, client_order_id, exchange_order_id
        return OrderDestinationVerification.accepted()


class FailingOrderTestSession(NeverCalledSession):
    def order_test(self, params: object) -> object:
        del params
        self.calls.append("test")
        raise RuntimeError("exchange test failed")


class UnexpectedOrderAttemptError(Exception):
    """Exercise the retained non-RuntimeError order-attempt boundary."""


class UnexpectedOrderPlaceSession(NeverCalledSession):
    def order_place(self, params: object) -> object:
        del params
        self.calls.append("place")
        raise UnexpectedOrderAttemptError("exchange placement outcome is unknown")


class RevokedAfterClaimSource:
    def __init__(self, envelope: ExecutionAuthorizationEnvelope) -> None:
        self.envelope = envelope
        self.calls = 0

    def resolve_execution_authorization(
        self, authorization_id: str
    ) -> ExecutionAuthorizationEnvelope | None:
        self.calls += 1
        if self.calls == 1 and authorization_id == self.envelope.authorization_id:
            return self.envelope
        return None


def test_authorization_round_trip_hash_and_command_are_deterministic() -> None:
    envelope = authorization()
    restored = ExecutionAuthorizationEnvelope.from_payload(envelope.to_payload())

    assert restored == envelope
    assert restored.envelope_sha256 == envelope.envelope_sha256
    assert restored.to_spot_order_command() == order()
    assert SpotOrderCommand is CanonicalSpotOrderCommand
    assert LegacySpotOrderCommand is CanonicalSpotOrderCommand
    assert restored.execution_allowed is False
    assert restored.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: replace(authorization(), symbol="HOT/USDT"), "symbol"),
        (lambda: replace(authorization(), side="HOLD"), "side"),
        (lambda: replace(authorization(), order_type="STOP"), "order type"),
        (lambda: replace(authorization(), quantity=Decimal("0")), "quantity"),
        (
            lambda: replace(authorization(), price=None),
            "LIMIT authorization requires exact price",
        ),
        (
            lambda: replace(
                authorization(),
                order_type="MARKET",
                price=Decimal("0.01"),
                time_in_force="GTC",
            ),
            "MARKET authorization cannot contain price",
        ),
        (
            lambda: replace(authorization(), expires_at=NOW - timedelta(minutes=1)),
            "expiry must follow",
        ),
        (
            lambda: replace(authorization(), execution_allowed=True),
            "cannot grant execution",
        ),
    ],
)
def test_authorization_envelope_rejects_invalid_or_authorizing_shapes(
    factory: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


def test_authorization_payload_and_helpers_fail_closed() -> None:
    envelope = authorization()
    payload = envelope.to_payload()

    with pytest.raises(ValueError, match="object"):
        ExecutionAuthorizationEnvelope.from_payload(())
    with pytest.raises(ValueError, match="fields"):
        ExecutionAuthorizationEnvelope.from_payload({**payload, "unexpected": True})
    with pytest.raises(ValueError, match="created_at is invalid"):
        ExecutionAuthorizationEnvelope.from_payload({**payload, "created_at": "bad"})
    with pytest.raises(ValueError, match="quantity is invalid"):
        ExecutionAuthorizationEnvelope.from_payload({**payload, "quantity": "bad"})
    with pytest.raises(ValueError, match="quantity must be finite"):
        ExecutionAuthorizationEnvelope.from_payload({**payload, "quantity": "NaN"})

    blockers = envelope.blockers_for(
        replace(order(), symbol="ETHUSDT"),
        observed_at=NOW - timedelta(minutes=1),
    )
    assert blockers == (
        "EXECUTION_AUTHORIZATION_NOT_YET_VALID",
        "EXECUTION_AUTHORIZATION_PREVIEW_HASH_MISMATCH",
        "EXECUTION_AUTHORIZATION_SYMBOL_MISMATCH",
    )


def test_authorization_consumption_and_ledger_reject_unsafe_boundaries(
    tmp_path: Path,
) -> None:
    envelope = authorization()
    with pytest.raises(ValueError, match="timeout"):
        LocalExecutionAuthorizationLedger(
            tmp_path / "ledger.sqlite3",
            timeout_seconds=0,
        )
    with pytest.raises(ValueError, match="cannot grant authority"):
        replace(
            LocalExecutionAuthorizationLedger(tmp_path / "ledger.sqlite3").claim(
                envelope, execution_id="exec-1", claimed_at=NOW
            ),
            execution_allowed=True,
        )
    ledger = LocalExecutionAuthorizationLedger(tmp_path / "ledger.sqlite3")
    assert ledger.is_consumed("missing") is False
    assert (
        LocalExecutionAuthorizationLedger(tmp_path / "missing.sqlite3").is_consumed(
            "authorization-1"
        )
        is False
    )
    with pytest.raises(ValueError, match="authorization_id"):
        ledger.is_consumed("bad\nid")


@pytest.mark.parametrize(
    "change",
    [
        {"preview_hash": "3" * 64},
        {"decision_id": "decision-2"},
        {"snapshot_id": "snapshot-2"},
        {"strategy_id": "mean-reversion"},
        {"strategy_version": "2.0.0"},
        {"symbol": "ETHUSDT"},
        {"side": "SELL"},
        {"order_type": "MARKET", "price": None, "time_in_force": None},
        {"quantity": Decimal("999")},
        {"price": Decimal("0.02")},
        {"time_in_force": "IOC"},
        {"client_order_id": "auth-order-2"},
        {"risk_assessment_hash": "4" * 64},
        {"validation_bundle_hash": "5" * 64},
    ],
)
def test_caller_substitution_cannot_change_approved_envelope(
    tmp_path: Path,
    change: dict[str, object],
) -> None:
    approved = authorization()
    substituted = replace(approved, **change)  # type: ignore[arg-type]
    session = NeverCalledSession()
    result = GatedSpotOrderExecutor(
        session,
        authorization_source=AuthorizationSource(approved),
        authorization_ledger=LocalExecutionAuthorizationLedger(
            tmp_path / "consumption.sqlite3"
        ),
    ).place(
        all_live_gates(),
        authorization=substituted,
        attempted_at=NOW + timedelta(minutes=1),
    )

    assert result.blockers == ("EXECUTION_AUTHORIZATION_RECORD_MISMATCH",)
    assert session.calls == []


def test_readiness_source_requires_latest_unique_approved_record(
    tmp_path: Path,
) -> None:
    path = tmp_path / "approvals.jsonl"
    envelope = authorization()
    approved = approval_record(envelope)
    write_records(path, approved)

    assert (
        LocalApprovalQueue(path).resolve_execution_authorization(
            envelope.authorization_id
        )
        == envelope
    )

    revoked = replace(
        approval_record(
            envelope,
            status=ApprovalStatus.CANCELLED,
            created_at=NOW + timedelta(seconds=1),
        ),
        execution_authorization=None,
    )
    write_records(path, approved, revoked)
    assert (
        LocalApprovalQueue(path).resolve_execution_authorization(
            envelope.authorization_id
        )
        is None
    )


def test_legacy_approval_without_envelope_cannot_authorize(tmp_path: Path) -> None:
    path = tmp_path / "approvals.jsonl"
    record = approval_record(authorization())
    legacy_payload = to_primitive(record)
    assert isinstance(legacy_payload, dict)
    legacy_payload.pop("execution_authorization")
    path.write_text(json.dumps(legacy_payload) + "\n", encoding="utf-8")

    assert (
        LocalApprovalQueue(path).resolve_execution_authorization("authorization-1")
        is None
    )


def test_authorization_expiry_and_self_hash_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    expired = authorization(expires_at=NOW + timedelta(seconds=1))
    session = NeverCalledSession()
    result = GatedSpotOrderExecutor(
        session,
        authorization_source=AuthorizationSource(expired),
        authorization_ledger=LocalExecutionAuthorizationLedger(
            tmp_path / "consumption.sqlite3"
        ),
    ).place(
        all_live_gates(),
        authorization=expired,
        attempted_at=NOW + timedelta(seconds=2),
    )

    assert result.blockers == ("EXECUTION_AUTHORIZATION_EXPIRED",)
    assert session.calls == []

    wrong_preview = replace(expired, preview_hash="3" * 64)
    assert (
        "EXECUTION_AUTHORIZATION_PREVIEW_HASH_MISMATCH"
        in wrong_preview.blockers_for(
            wrong_preview.to_spot_order_command(),
            observed_at=NOW,
        )
    )


def test_single_use_ledger_persists_claim_and_blocks_replay(tmp_path: Path) -> None:
    envelope = authorization()
    ledger = LocalExecutionAuthorizationLedger(tmp_path / "consumption.sqlite3")

    claimed = ledger.claim(
        envelope,
        execution_id="execution-1",
        claimed_at=NOW + timedelta(seconds=1),
    )

    assert claimed.authorization_id == envelope.authorization_id
    assert claimed.envelope_sha256 == envelope.envelope_sha256
    assert claimed.execution_allowed is False
    assert ledger.is_consumed(envelope.authorization_id) is True
    with pytest.raises(ExecutionAuthorizationAlreadyConsumedError):
        ledger.claim(
            envelope,
            execution_id="execution-2",
            claimed_at=NOW + timedelta(seconds=2),
        )


def test_authorization_lookup_closes_connections_on_success_and_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = authorization()
    ledger = LocalExecutionAuthorizationLedger(tmp_path / "consumption.sqlite3")
    ledger.claim(
        envelope,
        execution_id="execution-1",
        claimed_at=NOW + timedelta(seconds=1),
    )
    corrupt = LocalExecutionAuthorizationLedger(tmp_path / "corrupt.sqlite3")
    corrupt.path.write_text("not a database", encoding="utf-8")
    opened: list[sqlite3.Connection] = []
    connect = sqlite3.connect

    def tracked_connect(
        database: str | Path,
        **options: Unpack[AuthorizationConnectOptions],
    ) -> sqlite3.Connection:
        connection = connect(database, **options)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)

    assert ledger.is_consumed(envelope.authorization_id) is True
    assert ledger.is_consumed("authorization-not-consumed") is False
    with pytest.raises(ExecutionAuthorizationLedgerUnavailableError):
        corrupt.is_consumed(envelope.authorization_id)
    assert len(opened) == 3
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_failed_exchange_attempt_still_consumes_authorization(tmp_path: Path) -> None:
    envelope = authorization()
    ledger = LocalExecutionAuthorizationLedger(tmp_path / "consumption.sqlite3")
    session = FailingOrderTestSession()
    executor = GatedSpotOrderExecutor(
        session,
        AcceptingVerifier(),
        AuthorizationSource(envelope),
        ledger,
        live_gate_registry(),
        promotion_registry(),
        EVIDENCE_QUERY,
    )

    result = executor.place(
        all_live_gates(),
        authorization=envelope,
        attempted_at=NOW + timedelta(seconds=1),
    )

    assert result.status is LiveCommandStatus.ATTEMPT_FAILED
    assert result.blockers == ("LIVE_ORDER_ATTEMPT_OUTCOME_UNVERIFIED",)
    assert result.authorization_id == envelope.authorization_id
    assert result.authorization_envelope_sha256 == envelope.envelope_sha256
    assert ledger.is_consumed(envelope.authorization_id) is True
    replay = executor.place(
        all_live_gates(),
        authorization=envelope,
        attempted_at=NOW + timedelta(seconds=2),
    )
    assert replay.blockers == ("EXECUTION_AUTHORIZATION_ALREADY_CONSUMED",)
    assert session.calls == ["test"]


def test_unexpected_order_attempt_exception_remains_fail_closed_after_claim(
    tmp_path: Path,
) -> None:
    envelope = authorization()
    ledger = LocalExecutionAuthorizationLedger(tmp_path / "consumption.sqlite3")
    session = UnexpectedOrderPlaceSession()
    executor = GatedSpotOrderExecutor(
        session,
        AcceptingVerifier(),
        AuthorizationSource(envelope),
        ledger,
        live_gate_registry(),
        promotion_registry(),
        EVIDENCE_QUERY,
    )

    result = executor.place(
        all_live_gates(),
        authorization=envelope,
        attempted_at=NOW + timedelta(seconds=1),
    )

    assert result.status is LiveCommandStatus.ATTEMPT_FAILED
    assert result.blockers == ("LIVE_ORDER_ATTEMPT_OUTCOME_UNVERIFIED",)
    assert result.authorization_id == envelope.authorization_id
    assert result.authorization_envelope_sha256 == envelope.envelope_sha256
    assert ledger.is_consumed(envelope.authorization_id) is True
    replay = executor.place(
        all_live_gates(),
        authorization=envelope,
        attempted_at=NOW + timedelta(seconds=2),
    )
    assert replay.blockers == ("EXECUTION_AUTHORIZATION_ALREADY_CONSUMED",)
    assert session.calls == ["test", "place"]


def test_revocation_after_claim_blocks_before_exchange_attempt(tmp_path: Path) -> None:
    envelope = authorization()
    ledger = LocalExecutionAuthorizationLedger(tmp_path / "consumption.sqlite3")
    session = NeverCalledSession()
    source = RevokedAfterClaimSource(envelope)
    result = GatedSpotOrderExecutor(
        session,
        AcceptingVerifier(),
        source,
        ledger,
        live_gate_registry(),
        promotion_registry(),
        EVIDENCE_QUERY,
    ).place(
        all_live_gates(),
        authorization=envelope,
        attempted_at=NOW + timedelta(seconds=1),
    )

    assert result.status is LiveCommandStatus.BLOCKED
    assert result.blockers == ("EXECUTION_AUTHORIZATION_REVOKED_BEFORE_ATTEMPT",)
    assert ledger.is_consumed(envelope.authorization_id) is True
    assert source.calls == 2
    assert session.calls == []


def test_concurrent_authorization_claim_has_exactly_one_winner(tmp_path: Path) -> None:
    envelope = authorization()
    path = tmp_path / "consumption.sqlite3"

    def claim(index: int) -> str:
        try:
            LocalExecutionAuthorizationLedger(path).claim(
                envelope,
                execution_id=f"execution-{index}",
                claimed_at=NOW + timedelta(seconds=index),
            )
        except ExecutionAuthorizationAlreadyConsumedError:
            return "BLOCKED"
        return "CLAIMED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(claim, (1, 2)))

    assert sorted(outcomes) == ["BLOCKED", "CLAIMED"]


def test_authorization_ledger_unavailable_fails_closed(tmp_path: Path) -> None:
    directory = tmp_path / "not-a-database"
    directory.mkdir()
    with pytest.raises(ExecutionAuthorizationLedgerUnavailableError):
        LocalExecutionAuthorizationLedger(directory).claim(
            authorization(),
            execution_id="execution-1",
            claimed_at=NOW,
        )


@pytest.mark.parametrize(
    "payload_change",
    [
        {"preview_hash": "not-a-hash"},
        {"market_type": "FUTURES"},
        {"created_at": "2026-09-09T03:30:00"},
        {"expires_at": "2026-09-09T03:29:00Z"},
        {"execution_allowed": True},
    ],
)
def test_malformed_or_authority_broadening_payload_is_rejected(
    payload_change: dict[str, object],
) -> None:
    payload = authorization().to_payload() | payload_change
    with pytest.raises(ValueError, match="authorization"):
        ExecutionAuthorizationEnvelope.from_payload(payload)

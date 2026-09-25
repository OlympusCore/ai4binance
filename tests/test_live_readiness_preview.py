"""Spot live preview and readiness gates stay fail-closed."""

from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from ai4binance.application.live_readiness import (
    LiveReadinessBuilder,
    LiveReadinessEvidence,
)
from ai4binance.cli import live as cli_live
from ai4binance.config import Settings
from ai4binance.domain import LiveGateInput, ValidationStatus
from ai4binance.exchange import BinancePrivateAccountReader, PrivateCredentials
from ai4binance.exchange.models import BookTicker, MarketKline, SymbolInfo
from ai4binance.execution import (
    ExecutionAuthorizationEnvelope,
    LiveCommandResult,
    LiveCommandStatus,
    SpotOrderPreview,
)
from ai4binance.execution import live_readiness as readiness_mod
from ai4binance.execution.manual_approval import LocalApprovalQueue
from ai4binance.execution.order_preview import SpotOrderPreviewBuilder
from ai4binance.reporting import to_primitive
from ai4binance.safety import evaluate_live_gate
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
from ai4binance.validation.summary import ValidationSummaryReader


class PublicClientStub:
    def server_time(self) -> datetime:
        return datetime(2026, 7, 28, tzinfo=UTC)

    def exchange_info(self, symbol: str) -> SymbolInfo:
        return SymbolInfo(
            symbol,
            "TRADING",
            "HOT",
            "USDT",
            {
                "PRICE_FILTER": {
                    "minPrice": "0.000001",
                    "maxPrice": "1",
                    "tickSize": "0.000001",
                },
                "LOT_SIZE": {
                    "minQty": "1",
                    "maxQty": "100000000",
                    "stepSize": "1",
                },
                "MIN_NOTIONAL": {"minNotional": "5"},
            },
        )

    def ticker_price(self, symbol: str) -> Decimal:
        del symbol
        return Decimal("0.01")

    def book_ticker(self, symbol: str) -> BookTicker:
        del symbol
        return BookTicker(Decimal("0.00999"), Decimal("0.01001"))

    def klines(
        self,
        symbol: str,
        interval: str,
        limit: int,
    ) -> tuple[MarketKline, ...]:
        del symbol, interval, limit
        return ()


class InvalidPricePublicClientStub(PublicClientStub):
    def ticker_price(self, symbol: str) -> Decimal:
        del symbol
        return Decimal("0")

    def book_ticker(self, symbol: str) -> BookTicker:
        del symbol
        return BookTicker(Decimal("0.00999"), Decimal("0.01001"))


class UnavailablePublicClientStub(PublicClientStub):
    def exchange_info(self, symbol: str) -> SymbolInfo:
        del symbol
        raise RuntimeError("public unavailable")


AUTH_NOW = datetime(2026, 7, 28, tzinfo=UTC)


def execution_authorization(
    preview: SpotOrderPreview,
    *,
    authorization_id: str = "authorization-live-1",
    approval_id: str = "approval-live-1",
    created_at: datetime = AUTH_NOW,
    expires_at: datetime | None = None,
    validation_bundle_hash: str = "2" * 64,
) -> ExecutionAuthorizationEnvelope:
    command = preview.command
    return ExecutionAuthorizationEnvelope(
        authorization_id=authorization_id,
        approval_id=approval_id,
        preview_hash=preview.preview_hash,
        decision_id="decision-live-1",
        snapshot_id="snapshot-live-1",
        strategy_id="trend-continuation",
        strategy_version="1.0.0",
        symbol=command.symbol,
        market_type="SPOT",
        side=command.side,
        order_type=command.order_type,
        quantity=command.quantity,
        client_order_id=command.client_order_id,
        risk_assessment_hash="1" * 64,
        validation_bundle_hash=validation_bundle_hash,
        created_at=created_at,
        expires_at=expires_at or created_at + timedelta(minutes=5),
        approved_by="GovernanceOwner:test",
        single_use_nonce=f"nonce:{authorization_id}",
        price=command.price,
        time_in_force=command.time_in_force,
    )


def write_approved_authorization(
    path: Path,
    envelope: ExecutionAuthorizationEnvelope,
    *,
    status: str = "APPROVED",
) -> None:
    path.write_text(
        json.dumps(
            {
                "action": {
                    "action_id": "spot-hot-buy",
                    "action_type": "PLACE_SPOT_ORDER",
                    "approval_status": status,
                    "asset_or_symbol": envelope.symbol,
                    "blockers": ["MANUAL_APPROVAL_REQUIRED"],
                    "expected_effect": "Place exact previewed Spot order.",
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                    "reason": "User written approval for exact authorization.",
                    "risk": "Live Spot risk remains gate controlled.",
                    "suggested_notional_usdt": "10",
                },
                "approval": {
                    "action_id": "spot-hot-buy",
                    "action_type": "PLACE_SPOT_ORDER",
                    "approval_id": envelope.approval_id,
                    "approval_status": status,
                    "execution_allowed": False,
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
                "created_at": AUTH_NOW.isoformat(),
                "execution_authorization": envelope.to_payload(),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def live_gate_query(
    *,
    strategy_id: str = "trend-continuation",
) -> PromotionEvidenceQuery:
    return PromotionEvidenceQuery(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        strategy_sha256="1" * 64,
        symbol="HOTUSDT",
        market_type="SPOT",
        timeframe="15m",
        parameter_set_sha256="2" * 64,
        dataset_sha256="3" * 64,
        code_revision="4" * 40,
        as_of=AUTH_NOW,
    )


def live_gate_registry(
    query: PromotionEvidenceQuery,
    *,
    excluded_kind: LiveGateEvidenceKind | None = None,
) -> LiveGateEvidenceRegistry:
    records = tuple(
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
            observed_at=AUTH_NOW,
            verification_status=LiveGateEvidenceVerificationStatus.VERIFIED,
            strategy_id=query.strategy_id,
            strategy_version=query.strategy_version,
            strategy_sha256=query.strategy_sha256,
            symbol=query.symbol,
            market_type=query.market_type,
            timeframe=query.timeframe,
            parameter_set_sha256=query.parameter_set_sha256,
            dataset_sha256=query.dataset_sha256,
            code_revision=query.code_revision,
        )
        for kind in LiveGateEvidenceKind
        if kind is not excluded_kind
    )
    return LiveGateEvidenceRegistry(records)


def test_spot_order_preview_rounds_and_hashes_without_authority() -> None:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="hotusdt",
        side="buy",
        order_type="limit",
        quantity=Decimal("1000.9"),
        client_order_id="approved-1",
        price=Decimal("0.010009"),
        time_in_force="GTC",
    )

    assert preview.command.quantity == Decimal("1000")
    assert preview.command.price == Decimal("0.010009")
    assert preview.preview_hash
    assert preview.status == "READY"
    assert preview.execution_allowed is False
    assert "QUANTITY_ROUNDED_DOWN_TO_STEP_SIZE" in preview.warnings


def test_spot_order_preview_warns_when_price_rounds_down_to_tick() -> None:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-price-round",
        price=Decimal("0.0100099"),
        time_in_force="GTC",
    )

    assert preview.command.price == Decimal("0.010009")
    assert "PRICE_ROUNDED_DOWN_TO_TICK_SIZE" in preview.warnings


def test_spot_order_preview_blocks_market_order_filter_and_spread_risk() -> None:
    preview = SpotOrderPreviewBuilder(
        PublicClientStub(),
        spread_cap_bps=Decimal("1"),
    ).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("10"),
        client_order_id="cid-market",
    )

    assert preview.command.price is None
    assert "NOTIONAL_BELOW_MINIMUM" in preview.blockers
    assert "SPREAD_EXCEEDS_LIVE_CAP" in preview.blockers
    assert preview.status == "BLOCKED"


def test_spot_order_preview_blocks_invalid_public_price_evidence() -> None:
    preview = SpotOrderPreviewBuilder(InvalidPricePublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("1000"),
        client_order_id="cid-invalid-price",
    )

    assert "PUBLIC_PRICE_EVIDENCE_INVALID" in preview.blockers
    assert preview.latest_spot_price_confirmed is False


def test_spot_order_preview_rejects_invalid_builder_and_authority_state() -> None:
    with pytest.raises(ValueError, match="spread cap"):
        SpotOrderPreviewBuilder(PublicClientStub(), spread_cap_bps=Decimal("0"))

    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-ready",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    with pytest.raises(ValueError, match="cannot grant execution"):
        SpotOrderPreview(
            command=preview.command,
            validation_price=preview.validation_price,
            latest_spot_price=preview.latest_spot_price,
            bid=preview.bid,
            ask=preview.ask,
            spread_bps=preview.spread_bps,
            blockers=(),
            warnings=(),
            exchange_info_valid=True,
            price_filter_valid=True,
            lot_size_valid=True,
            notional_filter_valid=True,
            tick_size_valid=True,
            step_size_valid=True,
            latest_spot_price_confirmed=True,
            spread_acceptable=True,
            slippage_acceptable=True,
            execution_allowed=True,
        )


def test_live_readiness_uses_written_approval_but_keeps_missing_gates_blocked(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    validation_root = tmp_path / "validation"
    run_card = validation_root / "HOTUSDT" / "15m" / "trend_continuation.run-card.json"
    run_card.parent.mkdir(parents=True)
    run_card.write_text(
        json.dumps(
            {
                "artifact_sha256": [["artifact.jsonl", "abc"]],
                "blockers": [],
                "created_at": "2026-07-28T00:00:00+00:00",
                "hypothesis_id": "hyp:trend_continuation:15m",
                "metrics": [["net_return", 1.0]],
                "promotion_status": "STAGED_CANDIDATE",
                "run_id": "run:staged",
                "symbol": "HOTUSDT",
                "timeframe": "15m",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="approved-1",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    authorization = execution_authorization(preview)
    write_approved_authorization(approval_path, authorization)
    preflight = {
        "status": "READY",
        "endpoints": (
            {"name": "spot_account", "status": "OK"},
            {"name": "spot_server_time", "status": "OK"},
        ),
    }

    readiness = LiveReadinessBuilder(
        Settings(
            trading_mode="live",
            order_mode="auto",
            allow_auto_live_orders=True,
            manual_approval_queue_path=approval_path,
            validation_artifact_directory=validation_root,
        ),
        LocalApprovalQueue(approval_path),
    ).build(
        preview=preview,
        confirm_live=True,
        authorization_id=authorization.authorization_id,
        preflight_report=preflight,
        open_orders=[],
        validation_summary=ValidationSummaryReader(validation_root).summarize(
            "HOTUSDT"
        ),
        observed_at=AUTH_NOW + timedelta(minutes=1),
    )

    assert readiness.approval_status == "APPROVED"
    assert readiness.authorization_id == authorization.authorization_id
    assert readiness.authorization_envelope_sha256 == authorization.envelope_sha256
    readiness_payload = json.dumps(to_primitive(readiness), sort_keys=True)
    assert authorization.single_use_nonce not in readiness_payload
    assert authorization.approved_by not in readiness_payload
    assert readiness.strategy_promotion_approved is False
    assert "explicit_user_request" not in readiness.blockers
    assert "latest_signal_exists" in readiness.blockers
    assert "risk_approved" in readiness.blockers
    assert "strategy_promotion_approved" in readiness.blockers
    assert "backtest_approved" in readiness.blockers
    assert "walk_forward_approved" in readiness.blockers
    assert "tuning_report_approved" in readiness.blockers
    assert "oos_approved" in readiness.blockers
    assert readiness.execution_allowed is False
    assert readiness.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    ("promotion_status", "expected_promotion_approved"),
    [
        (ValidationStatus.STAGED_CANDIDATE, False),
        (ValidationStatus.PAPER_APPROVED, False),
        (ValidationStatus.LIVE_ELIGIBLE, True),
    ],
)
def test_live_readiness_keeps_promotion_and_validation_evidence_independent(
    tmp_path: Path,
    promotion_status: ValidationStatus,
    expected_promotion_approved: bool,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    validation_root = tmp_path / "validation"
    run_card = validation_root / "HOTUSDT" / "15m" / "trend_continuation.run-card.json"
    run_card.parent.mkdir(parents=True)
    run_card.write_text(
        json.dumps(
            {
                "artifact_sha256": [["artifact.jsonl", "abc"]],
                "blockers": [],
                "created_at": "2026-07-28T00:00:00+00:00",
                "hypothesis_id": "hyp:trend_continuation:15m",
                "metrics": [["net_return", 1.0]],
                "promotion_status": "RESEARCH_ONLY",
                "run_id": "run:research",
                "symbol": "HOTUSDT",
                "timeframe": "15m",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="registry-evidence",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    preflight = {
        "status": "READY",
        "endpoints": (
            {"name": "spot_account", "status": "OK"},
            {"name": "spot_server_time", "status": "OK"},
        ),
    }
    promotion_query = PromotionEvidenceQuery(
        strategy_id="trend_continuation",
        strategy_version="1.0.0",
        strategy_sha256="1" * 64,
        symbol="HOTUSDT",
        market_type="SPOT",
        timeframe="15m",
        parameter_set_sha256="2" * 64,
        dataset_sha256="3" * 64,
        code_revision="4" * 40,
        as_of=datetime(2026, 7, 28, tzinfo=UTC),
    )
    registry = PromotionEvidenceRegistry.from_records(
        (
            PromotionEvidenceRecord(
                evidence_id="ledger-1",
                symbol="HOTUSDT",
                source_kind=PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
                source_ref="ledger:manual",
                observed_at=datetime(2026, 7, 28, tzinfo=UTC),
                promotion_status=promotion_status,
                timeframe="15m",
                strategy_id=promotion_query.strategy_id,
                strategy_version=promotion_query.strategy_version,
                strategy_sha256=promotion_query.strategy_sha256,
                market_type=promotion_query.market_type,
                parameter_set_sha256=promotion_query.parameter_set_sha256,
                dataset_sha256=promotion_query.dataset_sha256,
                code_revision=promotion_query.code_revision,
            ),
        )
    )

    builder = LiveReadinessBuilder(
        Settings(
            trading_mode="live",
            order_mode="auto",
            allow_auto_live_orders=True,
            manual_approval_queue_path=approval_path,
            validation_artifact_directory=validation_root,
        ),
        LocalApprovalQueue(approval_path),
        promotion_evidence_registry=registry,
    )
    readiness = builder.build(
        preview=preview,
        confirm_live=True,
        authorization_id=None,
        preflight_report=preflight,
        open_orders=[],
        validation_summary=ValidationSummaryReader(validation_root).summarize(
            "HOTUSDT"
        ),
        promotion_query=promotion_query,
    )
    missing_query_readiness = builder.build(
        preview=preview,
        confirm_live=True,
        authorization_id=None,
        preflight_report=preflight,
        open_orders=[],
        validation_summary=ValidationSummaryReader(validation_root).summarize(
            "HOTUSDT"
        ),
    )

    assert readiness.strategy_promotion_approved is expected_promotion_approved
    assert readiness.staged_candidate_count == 0
    assert ("strategy_promotion_approved" in readiness.blockers) is (
        not expected_promotion_approved
    )
    assert "backtest_approved" in readiness.blockers
    assert "walk_forward_approved" in readiness.blockers
    assert "tuning_report_approved" in readiness.blockers
    assert "oos_approved" in readiness.blockers
    assert readiness.execution_allowed is False
    assert missing_query_readiness.strategy_promotion_approved is False
    assert "strategy_promotion_approved" in missing_query_readiness.blockers


def test_live_readiness_maps_exact_validation_bundle_one_to_one(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="exact-validation-bundle",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    query = live_gate_query()
    validation_registry = live_gate_registry(query)
    bundle_sha256 = validation_registry.canonical_bundle_sha256(query=query)
    assert bundle_sha256 is not None
    authorization = execution_authorization(
        preview,
        validation_bundle_hash=bundle_sha256,
    )
    write_approved_authorization(approval_path, authorization)
    promotion_registry = PromotionEvidenceRegistry.from_records(
        (
            PromotionEvidenceRecord(
                evidence_id="promotion-live-eligible",
                symbol=query.symbol,
                source_kind=PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
                source_ref="governed://promotion/live-eligible",
                observed_at=AUTH_NOW,
                promotion_status=ValidationStatus.LIVE_ELIGIBLE,
                timeframe=query.timeframe,
                strategy_id=query.strategy_id,
                strategy_version=query.strategy_version,
                strategy_sha256=query.strategy_sha256,
                market_type=query.market_type,
                parameter_set_sha256=query.parameter_set_sha256,
                dataset_sha256=query.dataset_sha256,
                code_revision=query.code_revision,
            ),
        )
    )
    readiness = LiveReadinessBuilder(
        Settings(
            trading_mode="live",
            order_mode="auto",
            allow_auto_live_orders=True,
            manual_approval_queue_path=approval_path,
        ),
        LocalApprovalQueue(approval_path),
        promotion_evidence_registry=promotion_registry,
        live_gate_evidence_registry=validation_registry,
    ).build(
        preview=preview,
        confirm_live=True,
        authorization_id=authorization.authorization_id,
        preflight_report={
            "status": "READY",
            "endpoints": (
                {"name": "spot_account", "status": "OK"},
                {"name": "spot_server_time", "status": "OK"},
            ),
        },
        open_orders=[],
        validation_summary=ValidationSummaryReader(tmp_path / "missing").summarize(
            "HOTUSDT"
        ),
        promotion_query=query,
        observed_at=AUTH_NOW,
    )

    assert readiness.gate_input.backtest_approved is True
    assert readiness.gate_input.walk_forward_approved is True
    assert readiness.gate_input.tuning_report_approved is True
    assert readiness.gate_input.oos_approved is True
    assert readiness.strategy_promotion_approved is True
    assert readiness.validation_bundle_sha256 == bundle_sha256
    assert len(readiness.validation_evidence_refs) == 4
    assert readiness.validation_evidence_blockers == ()
    assert "backtest_approved" not in readiness.blockers
    assert "walk_forward_approved" not in readiness.blockers
    assert "tuning_report_approved" not in readiness.blockers
    assert "oos_approved" not in readiness.blockers
    serialized = json.dumps(to_primitive(readiness), sort_keys=True)
    assert "governed://validation" not in serialized
    assert readiness.execution_allowed is False
    assert readiness.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_live_readiness_rejects_validation_bundle_hash_mismatch(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="mismatched-validation-bundle",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    query = live_gate_query()
    registry = live_gate_registry(query)
    authorization = execution_authorization(
        preview,
        validation_bundle_hash="f" * 64,
    )
    write_approved_authorization(approval_path, authorization)
    readiness = LiveReadinessBuilder(
        Settings(manual_approval_queue_path=approval_path),
        LocalApprovalQueue(approval_path),
        live_gate_evidence_registry=registry,
    ).build(
        preview=preview,
        confirm_live=True,
        authorization_id=authorization.authorization_id,
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(tmp_path / "missing").summarize(
            "HOTUSDT"
        ),
        promotion_query=query,
        observed_at=AUTH_NOW,
    )

    assert readiness.gate_input.backtest_approved is False
    assert readiness.gate_input.walk_forward_approved is False
    assert readiness.gate_input.tuning_report_approved is False
    assert readiness.gate_input.oos_approved is False
    assert "LIVE_GATE_EVIDENCE_BUNDLE_HASH_MISMATCH" in readiness.blockers


@pytest.mark.parametrize(
    ("excluded_kind", "expected_blocker"),
    [
        (
            LiveGateEvidenceKind.BACKTEST,
            "LIVE_GATE_EVIDENCE_BACKTEST_MISSING",
        ),
        (
            LiveGateEvidenceKind.WALK_FORWARD,
            "LIVE_GATE_EVIDENCE_WALK_FORWARD_MISSING",
        ),
        (
            LiveGateEvidenceKind.TUNING,
            "LIVE_GATE_EVIDENCE_TUNING_MISSING",
        ),
        (LiveGateEvidenceKind.OOS, "LIVE_GATE_EVIDENCE_OOS_MISSING"),
    ],
)
def test_live_readiness_keeps_incomplete_validation_bundle_fail_closed(
    tmp_path: Path,
    excluded_kind: LiveGateEvidenceKind,
    expected_blocker: str,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id=f"missing-{excluded_kind.value.lower()}",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    query = live_gate_query()
    registry = live_gate_registry(query, excluded_kind=excluded_kind)
    authorization = execution_authorization(preview)
    write_approved_authorization(approval_path, authorization)
    readiness = LiveReadinessBuilder(
        Settings(manual_approval_queue_path=approval_path),
        LocalApprovalQueue(approval_path),
        live_gate_evidence_registry=registry,
    ).build(
        preview=preview,
        confirm_live=True,
        authorization_id=authorization.authorization_id,
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(tmp_path / "missing").summarize(
            "HOTUSDT"
        ),
        promotion_query=query,
        observed_at=AUTH_NOW,
    )

    assert readiness.gate_input.backtest_approved is False
    assert readiness.gate_input.walk_forward_approved is False
    assert readiness.gate_input.tuning_report_approved is False
    assert readiness.gate_input.oos_approved is False
    assert expected_blocker in readiness.blockers


def test_live_readiness_rejects_authorization_and_query_subject_mismatch(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="mismatched-validation-subject",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    query = live_gate_query(strategy_id="different-strategy")
    registry = live_gate_registry(query)
    bundle_sha256 = registry.canonical_bundle_sha256(query=query)
    assert bundle_sha256 is not None
    authorization = execution_authorization(
        preview,
        validation_bundle_hash=bundle_sha256,
    )
    write_approved_authorization(approval_path, authorization)
    readiness = LiveReadinessBuilder(
        Settings(manual_approval_queue_path=approval_path),
        LocalApprovalQueue(approval_path),
        live_gate_evidence_registry=registry,
    ).build(
        preview=preview,
        confirm_live=True,
        authorization_id=authorization.authorization_id,
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(tmp_path / "missing").summarize(
            "HOTUSDT"
        ),
        promotion_query=query,
        observed_at=AUTH_NOW,
    )

    assert readiness.gate_input.backtest_approved is False
    assert "LIVE_GATE_EVIDENCE_AUTHORIZATION_SUBJECT_MISMATCH" in readiness.blockers


@pytest.mark.parametrize(
    ("include_authorization", "include_query", "expected_blocker"),
    [
        (False, True, "LIVE_GATE_EVIDENCE_AUTHORIZATION_REQUIRED"),
        (True, False, "LIVE_GATE_EVIDENCE_EXACT_QUERY_REQUIRED"),
    ],
)
def test_live_readiness_requires_authorization_and_exact_validation_query(
    tmp_path: Path,
    include_authorization: bool,
    include_query: bool,
    expected_blocker: str,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id=f"missing-validation-boundary-{include_authorization}",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    query = live_gate_query()
    registry = live_gate_registry(query)
    bundle_sha256 = registry.canonical_bundle_sha256(query=query)
    assert bundle_sha256 is not None
    authorization = execution_authorization(
        preview,
        validation_bundle_hash=bundle_sha256,
    )
    if include_authorization:
        write_approved_authorization(approval_path, authorization)

    readiness = LiveReadinessBuilder(
        Settings(manual_approval_queue_path=approval_path),
        LocalApprovalQueue(approval_path),
        live_gate_evidence_registry=registry,
    ).build(
        preview=preview,
        confirm_live=True,
        authorization_id=(
            authorization.authorization_id if include_authorization else None
        ),
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(tmp_path / "missing").summarize(
            "HOTUSDT"
        ),
        promotion_query=query if include_query else None,
        observed_at=AUTH_NOW,
    )

    assert readiness.gate_input.backtest_approved is False
    assert readiness.gate_input.walk_forward_approved is False
    assert readiness.gate_input.tuning_report_approved is False
    assert readiness.gate_input.oos_approved is False
    assert expected_blocker in readiness.blockers


def test_live_readiness_uses_evaluation_time_for_validation_freshness(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="stale-caller-as-of",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    query = live_gate_query()
    registry = live_gate_registry(query)
    bundle_sha256 = registry.canonical_bundle_sha256(query=query)
    assert bundle_sha256 is not None
    evaluated_at = AUTH_NOW + timedelta(days=91)
    authorization = execution_authorization(
        preview,
        expires_at=evaluated_at + timedelta(minutes=5),
        validation_bundle_hash=bundle_sha256,
    )
    write_approved_authorization(approval_path, authorization)

    readiness = LiveReadinessBuilder(
        Settings(manual_approval_queue_path=approval_path),
        LocalApprovalQueue(approval_path),
        live_gate_evidence_registry=registry,
    ).build(
        preview=preview,
        confirm_live=True,
        authorization_id=authorization.authorization_id,
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(tmp_path / "missing").summarize(
            "HOTUSDT"
        ),
        promotion_query=query,
        observed_at=evaluated_at,
    )

    assert readiness.gate_input.backtest_approved is False
    assert "LIVE_GATE_EVIDENCE_BACKTEST_STALE" in readiness.blockers
    assert "LIVE_GATE_EVIDENCE_OOS_STALE" in readiness.blockers


@pytest.mark.parametrize(
    "validation_evidence_refs",
    [
        (
            ("BACKTEST", "evidence-backtest", "a" * 64),
            ("WALK_FORWARD", "evidence-walk-forward", "b" * 64),
            ("OOS", "evidence-oos", "d" * 64),
            ("TUNING", "evidence-tuning", "c" * 64),
        ),
        (
            ("BACKTEST", "evidence-backtest", "not-a-hash"),
            ("WALK_FORWARD", "evidence-walk-forward", "b" * 64),
            ("TUNING", "evidence-tuning", "c" * 64),
            ("OOS", "evidence-oos", "d" * 64),
        ),
    ],
)
def test_readiness_evidence_rejects_unbounded_validation_references(
    validation_evidence_refs: tuple[tuple[str, str, str], ...],
) -> None:
    _, readiness = allowed_preview_and_readiness()

    with pytest.raises(ValueError, match="live gate evidence"):
        replace(readiness, validation_evidence_refs=validation_evidence_refs)


def test_live_readiness_approval_lookup_continues_and_falls_through(
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.jsonl"
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="approved-lookup",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    authorization = execution_authorization(preview)
    write_approved_authorization(approval_path, authorization)
    builder = LiveReadinessBuilder(Settings(), LocalApprovalQueue(approval_path))

    assert (
        builder._authorization(
            authorization.authorization_id,
            preview,
            observed_at=AUTH_NOW + timedelta(minutes=1),
        )
        == authorization
    )
    assert (
        builder._authorization(
            "missing-authorization",
            preview,
            observed_at=AUTH_NOW + timedelta(minutes=1),
        )
        is None
    )


def test_live_preview_cli_blocks_missing_order_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli_live.run_live_preview_spot(
            Settings(),
            confirm_live=True,
            symbol="HOTUSDT",
            side=None,
            order_type=None,
            quantity=None,
            client_order_id=None,
            price=None,
            time_in_force=None,
            authorization_id=None,
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["blockers"] == [
        "ORDER_SIDE_REQUIRED",
        "ORDER_TYPE_REQUIRED",
        "ORDER_QUANTITY_REQUIRED",
        "CLIENT_ORDER_ID_REQUIRED",
    ]
    assert payload["live_eligibility_status"] == "LIVE_ORDER_BLOCKED"


def test_live_preview_payload_blocks_invalid_decimal_before_network() -> None:
    payload = cli_live.live_preview_payload(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="not-decimal",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        authorization_id=None,
    )

    assert payload["blockers"] == ("quantity must be decimal",)


def test_live_preview_payload_blocks_non_finite_decimal_before_network() -> None:
    payload = cli_live.live_preview_payload(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="Infinity",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        authorization_id=None,
    )

    assert payload["blockers"] == ("quantity must be finite",)


def test_live_preview_decimal_requires_value_before_network() -> None:
    with pytest.raises(ValueError, match="price is required"):
        cli_live._decimal(None, "price")


def test_live_public_client_factory_is_configured_from_settings() -> None:
    client = cli_live._public_client(
        Settings(public_api_base_url="https://api.test.local")
    )

    assert client is not None


def test_live_preview_payload_blocks_missing_limit_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_live, "_public_client", lambda _settings: PublicClientStub()
    )

    payload = cli_live.live_preview_payload(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price=None,
        time_in_force="GTC",
        authorization_id=None,
    )

    assert payload["blockers"] == ("LIMIT preview requires price",)


def test_live_preview_payload_blocks_unavailable_public_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_live, "_public_client", lambda _settings: UnavailablePublicClientStub()
    )

    payload = cli_live.live_preview_payload(
        Settings(),
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="MARKET",
        quantity="1000",
        client_order_id="cid-1",
        price=None,
        time_in_force=None,
        authorization_id=None,
    )

    assert payload["blockers"] == ("public Spot preview evidence is unavailable",)


def test_live_preview_payload_builds_readiness_with_injected_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    validation_root = tmp_path / "validation"
    write_staged_run_card(validation_root)
    settings = Settings(
        validation_artifact_directory=validation_root,
        manual_approval_queue_path=tmp_path / "approvals.jsonl",
    )
    monkeypatch.setattr(
        cli_live, "_public_client", lambda _settings: PublicClientStub()
    )
    monkeypatch.setattr(
        cli_live,
        "build_preflight_report",
        lambda **_kwargs: {
            "status": "READY",
            "endpoints": (
                {"name": "spot_account", "status": "OK"},
                {"name": "spot_server_time", "status": "OK"},
            ),
        },
    )
    monkeypatch.setattr(cli_live, "_open_orders", lambda _settings, _symbol: [])

    payload = cli_live.live_preview_payload(
        settings,
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        authorization_id=None,
    )

    readiness = cast(LiveReadinessEvidence, payload["readiness"])
    preview = cast(SpotOrderPreview, payload["preview"])
    assert preview.preview_hash
    assert "explicit_user_request" in readiness.blockers
    assert readiness.strategy_promotion_approved is False
    assert "strategy_promotion_approved" in readiness.blockers
    assert "backtest_approved" in readiness.blockers
    assert "walk_forward_approved" in readiness.blockers
    assert "tuning_report_approved" in readiness.blockers
    assert "oos_approved" in readiness.blockers
    assert payload["execution_allowed"] is False


def test_live_place_requires_exact_authorization(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-1",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    readiness = LiveReadinessBuilder(
        Settings(),
        LocalApprovalQueue(Path("missing.jsonl")),
    ).build(
        preview=preview,
        confirm_live=True,
        authorization_id=None,
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(Path("missing")).summarize(
            "HOTUSDT"
        ),
    )
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": readiness.blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    assert (
        cli_live.run_live_place_spot(
            Settings(),
            confirm_live=True,
            symbol="HOTUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="1000",
            client_order_id="cid-1",
            price="0.01",
            time_in_force="GTC",
            authorization_id=None,
        )
        == 2
    )

    payload = json.loads(capsys.readouterr().out)
    assert "explicit_user_request" in payload["blockers"]


def test_live_place_without_authorization_returns_blocked_gate_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-1",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    readiness = LiveReadinessBuilder(
        Settings(),
        LocalApprovalQueue(Path("missing.jsonl")),
    ).build(
        preview=preview,
        confirm_live=False,
        authorization_id=None,
        preflight_report=None,
        open_orders=None,
        validation_summary=ValidationSummaryReader(Path("missing")).summarize(
            "HOTUSDT"
        ),
    )
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": readiness.blockers,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    result = cli_live.run_live_place_spot(
        Settings(),
        confirm_live=False,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        authorization_id=None,
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["readiness"]["gate_result"]["status"] == "LIVE_ORDER_BLOCKED"


def test_live_place_allowed_gate_still_fails_closed_when_session_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    current = datetime.now(UTC)
    preview, readiness = allowed_preview_and_readiness(
        created_at=current - timedelta(minutes=1),
        expires_at=current + timedelta(minutes=4),
        authorization_id="authorization-1",
        approval_id="approval-1",
    )
    authorization = execution_authorization(
        preview,
        authorization_id="authorization-1",
        approval_id="approval-1",
        created_at=current - timedelta(minutes=1),
        expires_at=current + timedelta(minutes=4),
    )
    approval_path = tmp_path / "approvals.jsonl"
    write_approved_authorization(approval_path, authorization)
    settings = Settings(manual_approval_queue_path=approval_path)
    closed: list[bool] = []

    class FakeConnection:
        def __init__(self, *, url: str) -> None:
            self.url = url

        def close(self) -> None:
            closed.append(True)

    class UnavailableSession:
        def __init__(self, *_args: object) -> None:
            raise RuntimeError("session unavailable")

    monkeypatch.setattr(cli_live, "BinanceSpotWsConnection", FakeConnection)
    monkeypatch.setattr(cli_live, "BinanceEd25519SpotSession", UnavailableSession)
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": (),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    result = cli_live.run_live_place_spot(
        settings,
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        authorization_id="authorization-1",
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert "LIVE_SPOT_SESSION_UNAVAILABLE" in payload["blockers"]
    assert closed == [True]


def test_open_orders_returns_none_when_private_reader_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_reader(_settings: Settings) -> object:
        raise RuntimeError("private reader unavailable")

    monkeypatch.setattr(cli_live, "_private_reader", unavailable_reader)

    assert cli_live._open_orders(Settings(), "HOTUSDT") is None


def test_live_place_never_attempts_a_missing_preview(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *_args, **_kwargs: {
            "command": "live-preview-spot",
            "blockers": ("INPUT_INVALID",),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    assert (
        cli_live.run_live_place_spot(
            Settings(),
            confirm_live=False,
            symbol=None,
            side=None,
            order_type=None,
            quantity=None,
            client_order_id=None,
            price=None,
            time_in_force=None,
            authorization_id=None,
        )
        == 2
    )
    assert "ORDER_PREVIEW_UNAVAILABLE" in capsys.readouterr().out


def test_private_reader_uses_read_only_credentials_and_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = object()
    monkeypatch.setattr(
        PrivateCredentials,
        "from_environment_or_file",
        lambda _path: credentials,
    )
    reader = cli_live._private_reader(Settings())
    assert isinstance(reader, BinancePrivateAccountReader)


def test_live_place_blocks_invalid_or_mismatched_authorization_evidence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preview, readiness = allowed_preview_and_readiness()
    payload = {
        "command": "live-preview-spot",
        "preview": preview,
        "readiness": readiness,
        "blockers": (),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "_preview": preview,
    }
    monkeypatch.setattr(
        cli_live, "live_preview_payload", lambda *_args, **_kwargs: dict(payload)
    )

    class _InvalidQueue:
        def __init__(self, *_args: object) -> None:
            pass

        def resolve_execution_authorization(self, _identifier: str) -> object:
            raise ValueError("invalid evidence")

    monkeypatch.setattr(cli_live, "LocalApprovalQueue", _InvalidQueue)
    assert (
        cli_live.run_live_place_spot(
            Settings(),
            confirm_live=True,
            symbol="HOTUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="1000",
            client_order_id="cid-1",
            price="0.01",
            time_in_force="GTC",
            authorization_id="id",
        )
        == 2
    )
    assert "EXECUTION_AUTHORIZATION_EVIDENCE_INVALID" in capsys.readouterr().out


def test_live_readiness_helpers_fail_closed_on_malformed_evidence() -> None:
    preview, readiness = allowed_preview_and_readiness()

    assert (
        readiness_mod._endpoint_ok({"endpoints": "not-a-list"}, "spot_account") is False
    )
    assert (
        readiness_mod._endpoint_ok(
            {"endpoints": ("bad", {"name": "spot_account", "status": "FAIL"})},
            "spot_account",
        )
        is False
    )
    assert (
        readiness_mod._endpoint_ok(
            {"endpoints": ({"name": "other", "status": "OK"},)},
            "spot_account",
        )
        is False
    )
    assert readiness_mod._open_order_count(({"orderId": 1}, {"orderId": 2})) == 2
    with pytest.raises(ValueError, match="cannot grant execution"):
        LiveReadinessEvidence(
            gate_input=readiness.gate_input,
            gate_result=readiness.gate_result,
            blockers=(),
            approval_status="APPROVED",
            strategy_promotion_approved=True,
            preflight_status="READY",
            open_order_count=0,
            validation_run_count=1,
            staged_candidate_count=1,
            preview_hash=preview.preview_hash,
            execution_allowed=True,
        )


def test_live_place_allowed_gate_returns_executor_blockers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    current = datetime.now(UTC)
    preview, readiness = allowed_preview_and_readiness(
        created_at=current - timedelta(minutes=1),
        expires_at=current + timedelta(minutes=4),
        authorization_id="authorization-1",
        approval_id="approval-1",
    )
    authorization = execution_authorization(
        preview,
        authorization_id="authorization-1",
        approval_id="approval-1",
        created_at=current - timedelta(minutes=1),
        expires_at=current + timedelta(minutes=4),
    )
    approval_path = tmp_path / "approvals.jsonl"
    write_approved_authorization(approval_path, authorization)
    settings = Settings(manual_approval_queue_path=approval_path)
    closed: list[bool] = []

    class FakeConnection:
        def __init__(self, *, url: str) -> None:
            self.url = url

        def close(self) -> None:
            closed.append(True)

    class FakeCredentials:
        @classmethod
        def from_environment(cls) -> object:
            return object()

    class FakeSession:
        def __init__(self, *_args: object) -> None:
            self.logged_on = False

        def logon(self) -> None:
            self.logged_on = True

    class FakeExecutor:
        def __init__(self, *_args: object) -> None:
            pass

        def place(self, *_args: object, **_kwargs: object) -> LiveCommandResult:
            return LiveCommandResult(
                LiveCommandStatus.BLOCKED,
                ("ORDER_DESTINATION_VERIFIER_UNAVAILABLE",),
                "cid-1",
                preview_hash=preview.preview_hash,
            )

    monkeypatch.setattr(cli_live, "BinanceSpotWsConnection", FakeConnection)
    monkeypatch.setattr(cli_live, "BinanceEd25519SpotSession", FakeSession)
    monkeypatch.setattr(cli_live, "Ed25519Credentials", FakeCredentials)
    monkeypatch.setattr(cli_live, "GatedSpotOrderExecutor", FakeExecutor)
    monkeypatch.setattr(cli_live, "_private_reader", lambda _settings: object())
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": (),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    result = cli_live.run_live_place_spot(
        settings,
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        authorization_id="authorization-1",
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["live_command_result"]["status"] == "LIVE_ORDER_BLOCKED"
    assert payload["blockers"] == ["ORDER_DESTINATION_VERIFIER_UNAVAILABLE"]
    assert closed == [True]


def test_forged_live_readiness_cannot_bypass_executor_evidence_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    current = datetime.now(UTC)
    preview, readiness = allowed_preview_and_readiness(
        created_at=current - timedelta(minutes=1),
        expires_at=current + timedelta(minutes=4),
        authorization_id="authorization-1",
        approval_id="approval-1",
    )
    closed: list[bool] = []
    session_calls: list[str] = []

    class FakeConnection:
        def __init__(self, *, url: str) -> None:
            self.url = url

        def close(self) -> None:
            closed.append(True)

    class FakeCredentials:
        @classmethod
        def from_environment(cls) -> object:
            return object()

    class FakeSession:
        def __init__(self, *_args: object) -> None:
            self.logged_on = False

        def logon(self) -> None:
            self.logged_on = True

        def order_test(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            session_calls.append("test")
            return {"orderId": "99"}

        def order_place(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            session_calls.append("place")
            return {"orderId": "99"}

    class FakeReader:
        def all_orders(self, symbol: str, *, limit: int = 1_000) -> object:
            assert symbol == "HOTUSDT"
            assert limit == 100
            return [
                {
                    "clientOrderId": "cid-1",
                    "orderId": "99",
                    "status": "PARTIALLY_FILLED",
                    "executedQty": "2",
                    "cummulativeQuoteQty": "20",
                }
            ]

    monkeypatch.setattr(cli_live, "BinanceSpotWsConnection", FakeConnection)
    monkeypatch.setattr(cli_live, "BinanceEd25519SpotSession", FakeSession)
    monkeypatch.setattr(cli_live, "Ed25519Credentials", FakeCredentials)
    monkeypatch.setattr(cli_live, "_private_reader", lambda _settings: FakeReader())
    monkeypatch.setattr(
        cli_live,
        "live_preview_payload",
        lambda *args, **kwargs: {
            "command": "live-preview-spot",
            "preview": preview,
            "readiness": readiness,
            "blockers": (),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "_preview": preview,
        },
    )

    approval_path = tmp_path / "approvals.jsonl"
    authorization = execution_authorization(
        preview,
        authorization_id="authorization-1",
        approval_id="approval-1",
        created_at=current - timedelta(minutes=1),
        expires_at=current + timedelta(minutes=4),
    )
    write_approved_authorization(approval_path, authorization)
    settings = Settings(
        audit_directory=tmp_path / "audit",
        manual_approval_queue_path=approval_path,
    )
    result = cli_live.run_live_place_spot(
        settings,
        confirm_live=True,
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity="1000",
        client_order_id="cid-1",
        price="0.01",
        time_in_force="GTC",
        authorization_id="authorization-1",
    )

    payload = json.loads(capsys.readouterr().out)
    journal_path = settings.audit_directory / "live-order-lifecycle.jsonl"

    assert result == 2
    assert payload["live_command_result"]["status"] == "LIVE_ORDER_BLOCKED"
    assert "EXECUTION_EVIDENCE_EXACT_QUERY_REQUIRED" in payload["blockers"]
    assert "backtest_approved" in payload["blockers"]
    assert "strategy_promotion_approved" in payload["blockers"]
    assert "live_order_lifecycle" not in payload
    assert journal_path.exists() is False
    assert session_calls == []
    assert closed == [True]


def write_staged_run_card(root: Path) -> None:
    path = root / "HOTUSDT" / "15m" / "trend_continuation.run-card.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [["artifact.jsonl", "abc"]],
                "blockers": [],
                "created_at": "2026-07-28T00:00:00+00:00",
                "hypothesis_id": "hyp:trend_continuation:15m",
                "metrics": [["net_return", 1.0]],
                "promotion_status": "STAGED_CANDIDATE",
                "run_id": "run:staged",
                "symbol": "HOTUSDT",
                "timeframe": "15m",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def allowed_preview_and_readiness(
    *,
    created_at: datetime = AUTH_NOW,
    expires_at: datetime | None = None,
    authorization_id: str = "authorization-live-1",
    approval_id: str = "approval-live-1",
) -> tuple[SpotOrderPreview, LiveReadinessEvidence]:
    preview = SpotOrderPreviewBuilder(PublicClientStub()).build(
        symbol="HOTUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=Decimal("1000"),
        client_order_id="cid-1",
        price=Decimal("0.01"),
        time_in_force="GTC",
    )
    gate_input = LiveGateInput(**{field.name: True for field in fields(LiveGateInput)})
    gate_result = evaluate_live_gate(gate_input)
    authorization = execution_authorization(
        preview,
        authorization_id=authorization_id,
        approval_id=approval_id,
        created_at=created_at,
        expires_at=expires_at,
    )
    return preview, LiveReadinessEvidence(
        gate_input=gate_input,
        gate_result=gate_result,
        blockers=(),
        approval_status="APPROVED",
        strategy_promotion_approved=True,
        preflight_status="READY",
        open_order_count=0,
        validation_run_count=1,
        staged_candidate_count=1,
        preview_hash=preview.preview_hash,
        authorization_id=authorization.authorization_id,
        authorization_envelope_sha256=authorization.envelope_sha256,
        validation_bundle_sha256=authorization.validation_bundle_hash,
        validation_evidence_refs=tuple(
            (
                kind.value,
                f"test-{kind.value.lower()}",
                {
                    LiveGateEvidenceKind.BACKTEST: "a" * 64,
                    LiveGateEvidenceKind.WALK_FORWARD: "b" * 64,
                    LiveGateEvidenceKind.TUNING: "c" * 64,
                    LiveGateEvidenceKind.OOS: "d" * 64,
                }[kind],
            )
            for kind in LiveGateEvidenceKind
        ),
    )

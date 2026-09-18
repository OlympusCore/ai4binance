"""Map live-order evidence into the deterministic Spot live gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from ai4binance.config import Settings
from ai4binance.domain import LiveGateInput, LiveGateResult, ValidationStatus
from ai4binance.execution.authorization import ExecutionAuthorizationEnvelope
from ai4binance.execution.manual_approval import LocalApprovalQueue
from ai4binance.execution.order_preview import SpotOrderPreview
from ai4binance.safety import evaluate_live_gate
from ai4binance.validation.live_gate_evidence import (
    LiveGateEvidenceRegistry,
    LiveGateEvidenceResolution,
)
from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceQuery,
    PromotionEvidenceRegistry,
)
from ai4binance.validation.summary import ValidationSummary


@dataclass(frozen=True, slots=True)
class LiveReadinessEvidence:
    """Secret-safe explanation of every live-gate input."""

    gate_input: LiveGateInput
    gate_result: LiveGateResult
    blockers: tuple[str, ...]
    approval_status: str
    strategy_promotion_approved: bool
    preflight_status: str
    open_order_count: int | None
    validation_run_count: int
    staged_candidate_count: int
    preview_hash: str
    authorization_id: str | None = None
    authorization_envelope_sha256: str | None = None
    validation_bundle_sha256: str | None = None
    validation_evidence_refs: tuple[tuple[str, str, str], ...] = ()
    validation_evidence_blockers: tuple[str, ...] = ()
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("readiness evidence cannot grant execution authority")
        authorization_complete = (
            self.authorization_id is not None
            and self.authorization_envelope_sha256 is not None
        )
        if (self.authorization_id is None) != (
            self.authorization_envelope_sha256 is None
        ) or (self.approval_status == "APPROVED") != authorization_complete:
            raise ValueError("readiness approval must bind one exact authorization")
        validation_flags = (
            self.gate_input.backtest_approved,
            self.gate_input.walk_forward_approved,
            self.gate_input.tuning_report_approved,
            self.gate_input.oos_approved,
        )
        normalized_validation = LiveGateEvidenceResolution(
            backtest_approved=validation_flags[0],
            walk_forward_approved=validation_flags[1],
            tuning_report_approved=validation_flags[2],
            oos_approved=validation_flags[3],
            validation_bundle_sha256=self.validation_bundle_sha256,
            evidence_refs=self.validation_evidence_refs,
            blockers=self.validation_evidence_blockers,
        )
        object.__setattr__(
            self,
            "validation_bundle_sha256",
            normalized_validation.validation_bundle_sha256,
        )
        object.__setattr__(
            self,
            "validation_evidence_refs",
            normalized_validation.evidence_refs,
        )
        object.__setattr__(
            self,
            "validation_evidence_blockers",
            normalized_validation.blockers,
        )


@dataclass(frozen=True, slots=True)
class LiveReadinessBuilder:
    """Build the exact gate inputs without bypassing any missing evidence."""

    settings: Settings
    approval_queue: LocalApprovalQueue
    promotion_evidence_registry: PromotionEvidenceRegistry | None = None
    live_gate_evidence_registry: LiveGateEvidenceRegistry | None = None

    def build(
        self,
        *,
        preview: SpotOrderPreview,
        confirm_live: bool,
        authorization_id: str | None,
        preflight_report: Mapping[str, object] | None,
        open_orders: object,
        validation_summary: ValidationSummary,
        promotion_query: PromotionEvidenceQuery | None = None,
        observed_at: datetime | None = None,
        latest_signal_exists: bool = False,
        signal_not_expired: bool = False,
        entry_not_missed: bool = False,
        risk_controls_clear: bool = False,
        decision_logged: bool = False,
    ) -> LiveReadinessEvidence:
        evaluated_at = observed_at or datetime.now(UTC)
        authorization = self._authorization(
            authorization_id,
            preview,
            observed_at=evaluated_at,
        )
        approved = authorization is not None
        preflight_ready = _preflight_ready(preflight_report)
        spot_account_ok = _endpoint_ok(preflight_report, "spot_account")
        server_time_ok = _endpoint_ok(preflight_report, "spot_server_time")
        open_order_count = _open_order_count(open_orders)
        no_conflicts = open_order_count == 0
        exact_query = (
            replace(promotion_query, as_of=evaluated_at)
            if promotion_query is not None
            else None
        )
        promotion_status = (
            self.promotion_evidence_registry.resolve(query=exact_query)
            if self.promotion_evidence_registry is not None
            and exact_query is not None
            and exact_query.symbol == preview.command.symbol
            and exact_query.market_type == "SPOT"
            else ValidationStatus.RESEARCH_ONLY
        )
        strategy_promotion_approved = promotion_status is ValidationStatus.LIVE_ELIGIBLE
        validation_evidence = self._validation_evidence(
            authorization,
            exact_query,
        )
        gate_input = LiveGateInput(
            live_mode=self.settings.trading_mode == "live",
            auto_mode=self.settings.order_mode == "auto",
            allow_auto_live_orders=self.settings.allow_auto_live_orders,
            confirm_live=confirm_live,
            explicit_user_request=approved,
            api_valid=preflight_ready,
            account_status_valid=spot_account_ok,
            server_time_valid=server_time_ok,
            exchange_info_valid=preview.exchange_info_valid,
            price_filter_valid=preview.price_filter_valid,
            lot_size_valid=preview.lot_size_valid,
            notional_filter_valid=preview.notional_filter_valid,
            tick_size_valid=preview.tick_size_valid,
            step_size_valid=preview.step_size_valid,
            latest_spot_price_confirmed=preview.latest_spot_price_confirmed,
            spread_acceptable=preview.spread_acceptable,
            slippage_acceptable=preview.slippage_acceptable,
            balances_known=spot_account_ok,
            inventory_known=spot_account_ok,
            no_conflicting_open_orders=no_conflicts,
            latest_signal_exists=latest_signal_exists,
            signal_not_expired=signal_not_expired,
            entry_not_missed=entry_not_missed,
            backtest_approved=(
                validation_evidence.backtest_approved
                if validation_evidence is not None
                else False
            ),
            walk_forward_approved=(
                validation_evidence.walk_forward_approved
                if validation_evidence is not None
                else False
            ),
            tuning_report_approved=(
                validation_evidence.tuning_report_approved
                if validation_evidence is not None
                else False
            ),
            oos_approved=(
                validation_evidence.oos_approved
                if validation_evidence is not None
                else False
            ),
            risk_approved=risk_controls_clear,
            strategy_promotion_approved=strategy_promotion_approved,
            daily_loss_limit_clear=risk_controls_clear,
            cooldown_clear=risk_controls_clear,
            circuit_breaker_clear=risk_controls_clear,
            decision_logged=decision_logged,
            order_preview_created=not preview.blockers,
            user_authorization_recorded=approved,
        )
        gate_result = evaluate_live_gate(gate_input)
        blockers = tuple(
            dict.fromkeys(
                (
                    *preview.blockers,
                    *(
                        validation_evidence.blockers
                        if validation_evidence is not None
                        else ()
                    ),
                    *gate_result.blockers,
                )
            )
        )
        return LiveReadinessEvidence(
            gate_input=gate_input,
            gate_result=gate_result,
            blockers=blockers,
            approval_status="APPROVED" if approved else "MISSING_OR_NOT_APPROVED",
            strategy_promotion_approved=strategy_promotion_approved,
            preflight_status=str(
                preflight_report.get("status", "UNAVAILABLE")
                if preflight_report is not None
                else "UNAVAILABLE"
            ),
            open_order_count=open_order_count,
            validation_run_count=validation_summary.run_count,
            staged_candidate_count=validation_summary.staged_candidate_count,
            preview_hash=preview.preview_hash,
            authorization_id=(
                authorization.authorization_id if authorization is not None else None
            ),
            authorization_envelope_sha256=(
                authorization.envelope_sha256 if authorization is not None else None
            ),
            validation_bundle_sha256=(
                validation_evidence.validation_bundle_sha256
                if validation_evidence is not None
                else None
            ),
            validation_evidence_refs=(
                validation_evidence.evidence_refs
                if validation_evidence is not None
                else ()
            ),
            validation_evidence_blockers=(
                validation_evidence.blockers if validation_evidence is not None else ()
            ),
        )

    def _validation_evidence(
        self,
        authorization: ExecutionAuthorizationEnvelope | None,
        query: PromotionEvidenceQuery | None,
    ) -> LiveGateEvidenceResolution | None:
        registry = self.live_gate_evidence_registry
        if registry is None:
            return None
        if authorization is None:
            return LiveGateEvidenceResolution(
                blockers=("LIVE_GATE_EVIDENCE_AUTHORIZATION_REQUIRED",)
            )
        if query is None:
            return LiveGateEvidenceResolution(
                blockers=("LIVE_GATE_EVIDENCE_EXACT_QUERY_REQUIRED",)
            )
        if (
            query.strategy_id != authorization.strategy_id
            or query.strategy_version != authorization.strategy_version
            or query.symbol != authorization.symbol
            or query.market_type != authorization.market_type
        ):
            return LiveGateEvidenceResolution(
                blockers=("LIVE_GATE_EVIDENCE_AUTHORIZATION_SUBJECT_MISMATCH",)
            )
        return registry.resolve(
            query=query,
            expected_bundle_sha256=authorization.validation_bundle_hash,
        )

    def _authorization(
        self,
        authorization_id: str | None,
        preview: SpotOrderPreview,
        *,
        observed_at: datetime,
    ) -> ExecutionAuthorizationEnvelope | None:
        if authorization_id is None or not authorization_id.strip():
            return None
        try:
            authorization = self.approval_queue.resolve_execution_authorization(
                authorization_id
            )
        except (OSError, TypeError, ValueError):
            return None
        if authorization is None or authorization.blockers_for(
            preview.command,
            observed_at=observed_at,
        ):
            return None
        return authorization


def _preflight_ready(report: Mapping[str, object] | None) -> bool:
    return report is not None and report.get("status") == "READY"


def _endpoint_ok(report: Mapping[str, object] | None, name: str) -> bool:
    if report is None:
        return False
    endpoints = report.get("endpoints")
    if not isinstance(endpoints, Sequence) or isinstance(endpoints, str):
        return False
    for endpoint in endpoints:
        if not isinstance(endpoint, Mapping):
            continue
        if endpoint.get("name") == name:
            return endpoint.get("status") == "OK"
    return False


def _open_order_count(open_orders: object) -> int | None:
    if isinstance(open_orders, list):
        return len(open_orders)
    if isinstance(open_orders, tuple):
        return len(open_orders)
    return None

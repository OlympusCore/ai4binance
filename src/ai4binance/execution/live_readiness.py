"""Map live-order evidence into the deterministic Spot live gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ai4binance.config import Settings
from ai4binance.domain import LiveGateInput, LiveGateResult
from ai4binance.execution.manual_approval import (
    ApprovalStatus,
    LocalApprovalQueue,
    ManualActionType,
)
from ai4binance.execution.order_preview import SpotOrderPreview
from ai4binance.safety import evaluate_live_gate
from ai4binance.validation.summary import ValidationSummary


@dataclass(frozen=True, slots=True)
class LiveReadinessEvidence:
    """Secret-safe explanation of every live-gate input."""

    gate_input: LiveGateInput
    gate_result: LiveGateResult
    blockers: tuple[str, ...]
    approval_status: str
    preflight_status: str
    open_order_count: int | None
    validation_run_count: int
    staged_candidate_count: int
    preview_hash: str
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("readiness evidence cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class LiveReadinessBuilder:
    """Build the exact gate inputs without bypassing any missing evidence."""

    settings: Settings
    approval_queue: LocalApprovalQueue

    def build(
        self,
        *,
        preview: SpotOrderPreview,
        confirm_live: bool,
        approval_id: str | None,
        preflight_report: Mapping[str, object] | None,
        open_orders: object,
        validation_summary: ValidationSummary,
        latest_signal_exists: bool = False,
        signal_not_expired: bool = False,
        entry_not_missed: bool = False,
        risk_controls_clear: bool = False,
        decision_logged: bool = False,
    ) -> LiveReadinessEvidence:
        approved = self._approved(approval_id, preview.command.symbol)
        preflight_ready = _preflight_ready(preflight_report)
        spot_account_ok = _endpoint_ok(preflight_report, "spot_account")
        server_time_ok = _endpoint_ok(preflight_report, "spot_server_time")
        open_order_count = _open_order_count(open_orders)
        no_conflicts = open_order_count == 0
        staged = validation_summary.staged_candidate_count > 0
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
            backtest_approved=staged,
            walk_forward_approved=staged,
            tuning_report_approved=staged,
            oos_approved=staged,
            risk_approved=risk_controls_clear,
            strategy_promotion_approved=False,
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
                    *gate_result.blockers,
                )
            )
        )
        return LiveReadinessEvidence(
            gate_input=gate_input,
            gate_result=gate_result,
            blockers=blockers,
            approval_status="APPROVED" if approved else "MISSING_OR_NOT_APPROVED",
            preflight_status=str(
                preflight_report.get("status", "UNAVAILABLE")
                if preflight_report is not None
                else "UNAVAILABLE"
            ),
            open_order_count=open_order_count,
            validation_run_count=validation_summary.run_count,
            staged_candidate_count=validation_summary.staged_candidate_count,
            preview_hash=preview.preview_hash,
        )

    def _approved(self, approval_id: str | None, symbol: str) -> bool:
        if approval_id is None or not approval_id.strip():
            return False
        for record in self.approval_queue.records():
            if record.approval.approval_id != approval_id.strip():
                continue
            return (
                record.approval.approval_status is ApprovalStatus.APPROVED
                and record.approval.action_type is ManualActionType.PLACE_SPOT_ORDER
                and record.action.asset_or_symbol.upper() == symbol.upper()
            )
        return False


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

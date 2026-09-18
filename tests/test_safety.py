"""Live gate regression tests."""

from ai4binance.domain import ExecutionStatus, LiveGateInput
from ai4binance.safety import LIVE_GATE_REQUIREMENTS, evaluate_live_gate


def test_live_gate_is_blocked_by_default_and_returns_every_gate() -> None:
    gate_result = evaluate_live_gate(LiveGateInput())
    assert gate_result.status is ExecutionStatus.LIVE_ORDER_BLOCKED
    assert gate_result.blockers == LIVE_GATE_REQUIREMENTS
    assert "explicit_user_request" in gate_result.blockers
    assert "account_status_valid" in gate_result.blockers
    assert "signal_not_expired" in gate_result.blockers
    assert "strategy_promotion_approved" in gate_result.blockers
    assert "user_authorization_recorded" in gate_result.blockers
    assert "result_saved" not in gate_result.blockers


def test_live_gate_requires_every_explicit_condition() -> None:
    gate_result = evaluate_live_gate(
        LiveGateInput(
            live_mode=True,
            auto_mode=True,
            allow_auto_live_orders=True,
            confirm_live=True,
            explicit_user_request=True,
            api_valid=True,
            account_status_valid=True,
            server_time_valid=True,
            exchange_info_valid=True,
            price_filter_valid=True,
            lot_size_valid=True,
            notional_filter_valid=True,
            tick_size_valid=True,
            step_size_valid=True,
            latest_spot_price_confirmed=True,
            spread_acceptable=True,
            slippage_acceptable=True,
            balances_known=True,
            inventory_known=True,
            no_conflicting_open_orders=True,
            latest_signal_exists=True,
            signal_not_expired=True,
            entry_not_missed=True,
            backtest_approved=True,
            walk_forward_approved=True,
            tuning_report_approved=True,
            oos_approved=True,
            risk_approved=True,
            strategy_promotion_approved=True,
            daily_loss_limit_clear=True,
            cooldown_clear=True,
            circuit_breaker_clear=True,
            decision_logged=True,
            order_preview_created=True,
            user_authorization_recorded=True,
        )
    )
    assert gate_result.status is ExecutionStatus.EXECUTION_ALLOWED
    assert gate_result.blockers == ()


def test_live_execution_disabled_wins_over_every_other_positive_gate() -> None:
    gate_values = dict.fromkeys(LiveGateInput.__dataclass_fields__, True)
    gate_values["allow_auto_live_orders"] = False

    gate_result = evaluate_live_gate(LiveGateInput(**gate_values))

    assert gate_result.status is ExecutionStatus.LIVE_ORDER_BLOCKED
    assert gate_result.blockers == ("allow_auto_live_orders",)


def test_audit_decision_log_is_required_even_when_every_other_gate_passes() -> None:
    gate_values = dict.fromkeys(LiveGateInput.__dataclass_fields__, True)
    gate_values["decision_logged"] = False

    gate_result = evaluate_live_gate(LiveGateInput(**gate_values))

    assert gate_result.status is ExecutionStatus.LIVE_ORDER_BLOCKED
    assert gate_result.blockers == ("decision_logged",)

"""Tamper-evident persistence for canonical historical replay wallet state."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

from ai4binance.research.backtesting.models import (
    BacktestExitReason,
    ClosedTradeAttribution,
    TradeDirection,
)
from ai4binance.research.historical_replay import (
    MAX_VIRTUAL_MARKET_CAPITAL_USDT,
    HistoricalMarketReplayRequest,
    VirtualWalletEpoch,
    VirtualWalletEpochStatus,
)
from ai4binance.research.virtual_market import DailyEquityPoint, VirtualMarket
from ai4binance.research.virtual_runtime import (
    VirtualClosedTradeRecord,
    VirtualClosureReview,
    VirtualManagedPosition,
    VirtualPortfolioState,
    VirtualPositionExit,
    VirtualPositionLifecycleStatus,
    VirtualPositionSide,
)
from ai4binance.research_runtime import (
    HistoricalMarketEquityCurve,
    HistoricalReplayRunResult,
)
from ai4binance.storage import AuditEvent, JsonlAuditStore, read_bounded_jsonl_tail

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GENESIS = "GENESIS"
VIRTUAL_WALLET_RESET_CONFIRMATION = "CONFIRM_VIRTUAL_WALLET_RESET"


@dataclass(frozen=True, slots=True)
class HistoricalReplayResetCapital:
    """Explicit bounded initial capital for one new wallet epoch."""

    market: VirtualMarket
    initial_capital_usdt: Decimal

    def __post_init__(self) -> None:
        market = (
            self.market
            if isinstance(self.market, VirtualMarket)
            else VirtualMarket(str(self.market).strip().upper())
        )
        object.__setattr__(self, "market", market)
        if not (
            Decimal("0") < self.initial_capital_usdt <= MAX_VIRTUAL_MARKET_CAPITAL_USDT
        ):
            raise ValueError(
                "historical replay reset capital must be positive and at most 1000 USDT"
            )


@dataclass(frozen=True, slots=True)
class HistoricalReplayWalletResetResult:
    """Auditable epoch finalization that never deletes historical evidence."""

    reset_id: str
    status: str
    reset_at: datetime
    previous_epochs: tuple[VirtualWalletEpoch, ...]
    new_epochs: tuple[VirtualWalletEpoch, ...]
    new_portfolios: tuple[VirtualPortfolioState, ...]
    previous_result_semantic_sha256: str
    blockers: tuple[str, ...]
    history_path: Path
    persisted: bool
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.reset_id.strip():
            raise ValueError("historical replay wallet reset identity is required")
        if self.status not in {"RESET_COMPLETED", "RESET_BLOCKED"}:
            raise ValueError("historical replay wallet reset status is invalid")
        _require_utc("historical replay wallet reset timestamp", self.reset_at)
        if not _SHA256_RE.fullmatch(self.previous_result_semantic_sha256):
            raise ValueError("historical replay wallet reset result hash is invalid")
        if self.status == "RESET_COMPLETED":
            if self.blockers:
                raise ValueError("completed wallet reset must be unblocked")
            markets = {VirtualMarket.SPOT, VirtualMarket.USD_M_FUTURES}
            if (
                {epoch.market for epoch in self.previous_epochs} != markets
                or {epoch.market for epoch in self.new_epochs} != markets
                or {VirtualMarket(item.market) for item in self.new_portfolios}
                != markets
            ):
                raise ValueError("completed wallet reset requires both markets")
            if any(
                epoch.status is not VirtualWalletEpochStatus.FINALIZED
                for epoch in self.previous_epochs
            ) or any(
                epoch.status is not VirtualWalletEpochStatus.ACTIVE
                for epoch in self.new_epochs
            ):
                raise ValueError("wallet reset epoch lifecycle is inconsistent")
        elif not self.blockers or self.persisted:
            raise ValueError("blocked wallet reset requires blockers and no write")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical replay wallet reset cannot authorize trading")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": "HistoricalReplayWalletReset/v1",
            "reset_id": self.reset_id,
            "status": self.status,
            "reset_at": self.reset_at.isoformat(),
            "previous_epochs": [epoch.to_payload() for epoch in self.previous_epochs],
            "new_epochs": [epoch.to_payload() for epoch in self.new_epochs],
            "new_portfolios": [
                _portfolio_payload(portfolio) for portfolio in self.new_portfolios
            ],
            "previous_result_semantic_sha256": (self.previous_result_semantic_sha256),
            "blockers": list(self.blockers),
            "history_path": self.history_path.as_posix(),
            "persisted": self.persisted,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayRestoredState:
    """Verified wallet/accounting projection restored without decision authority."""

    run_id: str
    request_seed_sha256: str
    request_audit_sha256: str
    result_semantic_sha256: str
    result_audit_sha256: str
    last_sequence: int
    cycle_semantic_sha256s: tuple[str, ...]
    persisted_at: datetime
    final_portfolios: tuple[VirtualPortfolioState, ...]
    open_positions: tuple[VirtualManagedPosition, ...]
    closed_trades: tuple[VirtualClosedTradeRecord, ...]
    equity_curves: tuple[HistoricalMarketEquityCurve, ...]
    blockers: tuple[str, ...]
    previous_state_sha256: str = _GENESIS
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not _RUN_ID_RE.fullmatch(self.run_id):
            raise ValueError("historical replay persisted run id is invalid")
        for name, value in (
            ("request seed", self.request_seed_sha256),
            ("request audit", self.request_audit_sha256),
            ("semantic result", self.result_semantic_sha256),
            ("audit result", self.result_audit_sha256),
        ):
            if not _SHA256_RE.fullmatch(value):
                raise ValueError(f"historical replay persisted {name} hash is invalid")
        if self.previous_state_sha256 != _GENESIS and not _SHA256_RE.fullmatch(
            self.previous_state_sha256
        ):
            raise ValueError("historical replay previous state hash is invalid")
        _require_utc("historical replay persistence timestamp", self.persisted_at)
        if self.last_sequence < 0:
            raise ValueError("historical replay persisted sequence cannot be negative")
        if len(self.cycle_semantic_sha256s) != self.last_sequence + 1 or any(
            not _SHA256_RE.fullmatch(value) for value in self.cycle_semantic_sha256s
        ):
            raise ValueError("historical replay persisted cycle hash chain is invalid")
        markets = tuple(portfolio.market for portfolio in self.final_portfolios)
        if not markets or len(set(markets)) != len(markets):
            raise ValueError(
                "historical replay persisted portfolios must be market-independent"
            )
        if any(
            position.status is VirtualPositionLifecycleStatus.CLOSED
            for position in self.open_positions
        ):
            raise ValueError(
                "historical replay persisted open positions must be active"
            )
        if len({trade.trade_id for trade in self.closed_trades}) != len(
            self.closed_trades
        ):
            raise ValueError("historical replay persisted trade ids must be unique")
        if len({curve.market for curve in self.equity_curves}) != len(
            self.equity_curves
        ):
            raise ValueError(
                "historical replay persisted equity markets must be unique"
            )
        if any(not blocker.strip() for blocker in self.blockers) or len(
            set(self.blockers)
        ) != len(self.blockers):
            raise ValueError("historical replay persisted blockers must be unique")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "historical replay restored state cannot authorize trading"
            )

    @property
    def state_sha256(self) -> str:
        """Return the canonical integrity identity of the restored projection."""

        return _canonical_sha256(self.to_payload())

    def to_payload(self) -> dict[str, object]:
        """Return the complete audit-safe state projection."""

        return {
            "schema_version": "HistoricalReplayWalletState/v1",
            "run_id": self.run_id,
            "request_seed_sha256": self.request_seed_sha256,
            "request_audit_sha256": self.request_audit_sha256,
            "result_semantic_sha256": self.result_semantic_sha256,
            "result_audit_sha256": self.result_audit_sha256,
            "last_sequence": self.last_sequence,
            "cycle_semantic_sha256s": list(self.cycle_semantic_sha256s),
            "persisted_at": self.persisted_at.isoformat(),
            "final_portfolios": [
                _portfolio_payload(portfolio) for portfolio in self.final_portfolios
            ],
            "open_positions": [
                _position_payload(position) for position in self.open_positions
            ],
            "closed_trades": [
                _closed_trade_payload(trade) for trade in self.closed_trades
            ],
            "equity_curves": [curve.to_payload() for curve in self.equity_curves],
            "blockers": list(self.blockers),
            "previous_state_sha256": self.previous_state_sha256,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    @classmethod
    def from_result(
        cls,
        result: HistoricalReplayRunResult,
        *,
        persisted_at: datetime | None = None,
        previous_state_sha256: str = _GENESIS,
    ) -> HistoricalReplayRestoredState:
        """Project only canonical wallet, trade, and equity state from a run."""

        observed_at = persisted_at or result.cycles[-1].replay_snapshot.created_at
        return cls(
            run_id=result.request.run_id,
            request_seed_sha256=result.request.semantic_result_seed_sha256,
            request_audit_sha256=_canonical_sha256(result.request.to_payload()),
            result_semantic_sha256=result.semantic_result_sha256,
            result_audit_sha256=result.audit_result_sha256,
            last_sequence=result.cycles[-1].sequence,
            cycle_semantic_sha256s=tuple(
                _canonical_sha256(cycle.to_semantic_payload())
                for cycle in result.cycles
            ),
            persisted_at=observed_at,
            final_portfolios=result.final_portfolios,
            open_positions=result.open_positions,
            closed_trades=result.closed_trades,
            equity_curves=result.equity_curves,
            blockers=result.blockers,
            previous_state_sha256=previous_state_sha256,
        )


@dataclass(frozen=True, slots=True)
class HistoricalReplayStateStore:
    """Append-only, idempotent persistence for replay wallet epochs."""

    path: Path
    max_tail_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_tail_bytes < 1:
            raise ValueError("historical replay state tail limit must be positive")

    @classmethod
    def for_run(
        cls,
        root: Path,
        run_id: str,
    ) -> HistoricalReplayStateStore:
        """Resolve one bounded repository-runtime destination for a replay run."""

        if not _RUN_ID_RE.fullmatch(run_id):
            raise ValueError("historical replay persistence run id is invalid")
        base = (
            root
            / "runtime"
            / "artifacts"
            / "research"
            / "historical_replay"
            / "wallet_epochs"
        ).resolve()
        path = (base / f"{run_id}.jsonl").resolve()
        if path.parent != base:
            raise ValueError("historical replay persistence path escaped runtime")
        return cls(path)

    def persist(
        self,
        result: HistoricalReplayRunResult,
        *,
        persisted_at: datetime | None = None,
    ) -> bool:
        """Persist a newer state or return False for an exact idempotent replay."""

        previous = self.restore(result.request)
        previous_hash = previous.state_sha256 if previous is not None else _GENESIS
        state = HistoricalReplayRestoredState.from_result(
            result,
            persisted_at=persisted_at,
            previous_state_sha256=previous_hash,
        )
        if previous is not None:
            if previous.result_audit_sha256 == state.result_audit_sha256:
                return False
            if state.last_sequence <= previous.last_sequence:
                raise ValueError("HISTORICAL_REPLAY_PERSISTENCE_CONFLICT")
            if (
                state.cycle_semantic_sha256s[: len(previous.cycle_semantic_sha256s)]
                != previous.cycle_semantic_sha256s
            ):
                raise ValueError("HISTORICAL_REPLAY_CHECKPOINT_DIVERGENCE")
        event = AuditEvent(
            event_type="HISTORICAL_REPLAY_WALLET_CHECKPOINT",
            timestamp=state.persisted_at,
            snapshot_id=(f"historical-replay-result:{state.result_audit_sha256}"),
            payload={
                "state": state.to_payload(),
                "state_sha256": state.state_sha256,
            },
        )
        write_result = JsonlAuditStore(
            self.path,
            durable=True,
            tamper_evident=True,
        ).append_verified_idempotent(event)
        return write_result is not None

    def restore(
        self,
        request: HistoricalMarketReplayRequest,
    ) -> HistoricalReplayRestoredState | None:
        """Verify the full hash chain and restore only an exactly bound state."""

        if not self.path.exists():
            return None
        store = JsonlAuditStore(
            self.path,
            durable=True,
            tamper_evident=True,
        )
        store.verify_chain()
        lines = read_bounded_jsonl_tail(
            self.path,
            max_lines=1,
            max_bytes=self.max_tail_bytes,
        )
        if len(lines) != 1:
            raise ValueError("HISTORICAL_REPLAY_PERSISTED_STATE_UNAVAILABLE")
        record = _mapping(json.loads(lines[0].decode("utf-8")), "audit record")
        if record.get("event_type") != "HISTORICAL_REPLAY_WALLET_CHECKPOINT":
            raise ValueError("HISTORICAL_REPLAY_PERSISTED_EVENT_INVALID")
        payload = _mapping(record.get("payload"), "audit payload")
        state_payload = _mapping(payload.get("state"), "persisted state")
        state = _state_from_payload(state_payload)
        if payload.get("state_sha256") != state.state_sha256:
            raise ValueError("HISTORICAL_REPLAY_PERSISTED_STATE_HASH_MISMATCH")
        self._validate_request_binding(request, state)
        return state

    @property
    def reset_history_path(self) -> Path:
        """Return the append-only reset history beside persisted wallet state."""

        return self.path.parent / "reset_history" / self.path.name

    def reset_wallet_epochs(
        self,
        result: HistoricalReplayRunResult,
        *,
        reset_at: datetime,
        capitals: tuple[HistoricalReplayResetCapital, ...],
        confirmation: str,
    ) -> HistoricalReplayWalletResetResult:
        """Finalize flat epochs and create new bounded epochs without deletion."""

        if confirmation != VIRTUAL_WALLET_RESET_CONFIRMATION:
            raise ValueError("VIRTUAL_WALLET_RESET_EXPLICIT_CONFIRMATION_REQUIRED")
        _require_utc("historical replay wallet reset timestamp", reset_at)
        last_observed_at = max(
            cycle.replay_snapshot.created_at for cycle in result.cycles
        )
        if reset_at < last_observed_at:
            raise ValueError("historical replay wallet reset cannot precede replay")
        restored = self.restore(result.request)
        if (
            restored is None
            or restored.result_semantic_sha256 != result.semantic_result_sha256
            or restored.result_audit_sha256 != result.audit_result_sha256
        ):
            raise ValueError("HISTORICAL_REPLAY_RESET_STATE_NOT_PERSISTED")
        capital_by_market = {item.market: item for item in capitals}
        expected_markets = {VirtualMarket.SPOT, VirtualMarket.USD_M_FUTURES}
        if len(capital_by_market) != len(capitals) or set(capital_by_market) != (
            expected_markets
        ):
            raise ValueError(
                "historical replay wallet reset requires one capital per market"
            )
        reset_seed = {
            "run_id": result.request.run_id,
            "result_semantic_sha256": result.semantic_result_sha256,
            "reset_at": reset_at.isoformat(),
            "capitals": [
                {
                    "market": market.value,
                    "initial_capital_usdt": str(
                        capital_by_market[market].initial_capital_usdt
                    ),
                }
                for market in sorted(expected_markets, key=lambda item: item.value)
            ],
        }
        digest = _canonical_sha256(reset_seed)
        reset_id = f"historical-wallet-reset:{digest[:24]}"
        if result.open_positions:
            return HistoricalReplayWalletResetResult(
                reset_id=reset_id,
                status="RESET_BLOCKED",
                reset_at=reset_at,
                previous_epochs=result.request.wallet_epochs,
                new_epochs=(),
                new_portfolios=(),
                previous_result_semantic_sha256=result.semantic_result_sha256,
                blockers=("OPEN_VIRTUAL_POSITIONS_REQUIRE_SAFE_FINALIZATION",),
                history_path=self.reset_history_path,
                persisted=False,
            )
        previous_epochs = tuple(
            replace(
                epoch,
                status=VirtualWalletEpochStatus.FINALIZED,
                finalized_at=reset_at,
            )
            for epoch in result.request.wallet_epochs
        )
        new_epochs = tuple(
            VirtualWalletEpoch(
                epoch_id=(f"historical-epoch:{market.value.lower()}:{digest[:24]}"),
                portfolio_id=(
                    f"historical-portfolio:{market.value.lower()}:{digest[:24]}"
                ),
                market=market,
                initial_capital_usdt=capital_by_market[market].initial_capital_usdt,
                started_at=reset_at,
                start_reason=f"explicit wallet reset {reset_id}",
                system_segment_sha256=(result.request.system_version.semantic_sha256),
                evidence_class=result.request.wallet_epochs[0].evidence_class,
            )
            for market in sorted(expected_markets, key=lambda item: item.value)
        )
        new_portfolios = tuple(
            VirtualPortfolioState(
                portfolio_id=epoch.portfolio_id,
                market=epoch.market.value,
                cash_usdt=epoch.initial_capital_usdt,
                equity_usdt=epoch.initial_capital_usdt,
                initial_equity_usdt=epoch.initial_capital_usdt,
            )
            for epoch in new_epochs
        )
        history_path = self.reset_history_path
        history_store = JsonlAuditStore(
            history_path,
            durable=True,
            tamper_evident=True,
        )
        event_payload = {
            "schema_version": "HistoricalReplayWalletReset/v1",
            "reset_id": reset_id,
            "run_id": result.request.run_id,
            "reset_at": reset_at.isoformat(),
            "previous_result_semantic_sha256": result.semantic_result_sha256,
            "previous_result_audit_sha256": result.audit_result_sha256,
            "previous_epochs": [epoch.to_payload() for epoch in previous_epochs],
            "previous_epoch_summaries": [
                {
                    "market": portfolio.market,
                    "portfolio_id": portfolio.portfolio_id,
                    "initial_equity_usdt": str(portfolio.initial_equity_usdt),
                    "ending_equity_usdt": str(portfolio.equity_usdt),
                    "realized_pnl_usdt": str(portfolio.realized_pnl_usdt),
                    "unrealized_pnl_usdt": str(portfolio.unrealized_pnl_usdt),
                    "fees_paid_usdt": str(portfolio.fees_paid_usdt),
                    "funding_cost_usdt": str(portfolio.funding_cost_usdt),
                }
                for portfolio in result.final_portfolios
            ],
            "new_epochs": [epoch.to_payload() for epoch in new_epochs],
            "new_portfolios": [
                _portfolio_payload(portfolio) for portfolio in new_portfolios
            ],
            "preserved_evidence": (
                "LEARNING",
                "STRATEGY_REGISTRY",
                "MODEL_REGISTRY",
                "DGE_HISTORY",
                "DATASETS",
                "PERFORMANCE_HISTORY",
                "AUDIT_HISTORY",
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        write_result = history_store.append_verified_idempotent(
            AuditEvent(
                event_type="HISTORICAL_REPLAY_WALLET_RESET",
                timestamp=reset_at,
                snapshot_id=(
                    f"historical-wallet-reset-source:{result.semantic_result_sha256}"
                ),
                payload=event_payload,
            )
        )
        return HistoricalReplayWalletResetResult(
            reset_id=reset_id,
            status="RESET_COMPLETED",
            reset_at=reset_at,
            previous_epochs=previous_epochs,
            new_epochs=new_epochs,
            new_portfolios=new_portfolios,
            previous_result_semantic_sha256=result.semantic_result_sha256,
            blockers=(),
            history_path=history_path,
            persisted=write_result is not None,
        )

    @staticmethod
    def _validate_request_binding(
        request: HistoricalMarketReplayRequest,
        state: HistoricalReplayRestoredState,
    ) -> None:
        if (
            state.run_id != request.run_id
            or state.request_seed_sha256 != request.semantic_result_seed_sha256
            or state.request_audit_sha256 != _canonical_sha256(request.to_payload())
        ):
            raise ValueError("HISTORICAL_REPLAY_PERSISTED_REQUEST_MISMATCH")
        epochs = {epoch.market.value: epoch for epoch in request.wallet_epochs}
        if set(epochs) != {portfolio.market for portfolio in state.final_portfolios}:
            raise ValueError("HISTORICAL_REPLAY_PERSISTED_MARKET_SCOPE_MISMATCH")
        for portfolio in state.final_portfolios:
            epoch = epochs[portfolio.market]
            if (
                portfolio.portfolio_id != epoch.portfolio_id
                or portfolio.initial_equity_usdt != epoch.initial_capital_usdt
            ):
                raise ValueError("HISTORICAL_REPLAY_PERSISTED_EPOCH_MISMATCH")


def _state_from_payload(
    payload: Mapping[str, object],
) -> HistoricalReplayRestoredState:
    if payload.get("schema_version") != "HistoricalReplayWalletState/v1":
        raise ValueError("historical replay persisted state schema is unsupported")
    return HistoricalReplayRestoredState(
        run_id=_text(payload, "run_id"),
        request_seed_sha256=_text(payload, "request_seed_sha256"),
        request_audit_sha256=_text(payload, "request_audit_sha256"),
        result_semantic_sha256=_text(payload, "result_semantic_sha256"),
        result_audit_sha256=_text(payload, "result_audit_sha256"),
        last_sequence=_integer(payload, "last_sequence"),
        cycle_semantic_sha256s=tuple(
            _text_item(item, "cycle semantic SHA-256")
            for item in _sequence(payload, "cycle_semantic_sha256s")
        ),
        persisted_at=_timestamp(payload, "persisted_at"),
        final_portfolios=tuple(
            _portfolio_from_payload(_mapping(item, "portfolio"))
            for item in _sequence(payload, "final_portfolios")
        ),
        open_positions=tuple(
            _position_from_payload(_mapping(item, "position"))
            for item in _sequence(payload, "open_positions")
        ),
        closed_trades=tuple(
            _closed_trade_from_payload(_mapping(item, "closed trade"))
            for item in _sequence(payload, "closed_trades")
        ),
        equity_curves=tuple(
            _equity_curve_from_payload(_mapping(item, "equity curve"))
            for item in _sequence(payload, "equity_curves")
        ),
        blockers=tuple(
            _text_item(item, "blocker") for item in _sequence(payload, "blockers")
        ),
        previous_state_sha256=_text(payload, "previous_state_sha256"),
        execution_allowed=payload.get("execution_allowed") is True,
        promotion_status=_text(payload, "promotion_status"),
        live_eligibility_status=_text(payload, "live_eligibility_status"),
    )


def _portfolio_payload(portfolio: VirtualPortfolioState) -> dict[str, object]:
    return portfolio.to_payload()


def _portfolio_from_payload(payload: Mapping[str, object]) -> VirtualPortfolioState:
    return VirtualPortfolioState.from_payload(payload)


def _position_payload(position: VirtualManagedPosition) -> dict[str, object]:
    from ai4binance.reporting import to_primitive

    return cast(dict[str, object], to_primitive(position))


def _position_from_payload(payload: Mapping[str, object]) -> VirtualManagedPosition:
    review_payload = payload.get("closure_review")
    return VirtualManagedPosition(
        position_id=_text(payload, "position_id"),
        candidate_id=_text(payload, "candidate_id"),
        symbol=_text(payload, "symbol"),
        market=_text(payload, "market"),
        opened_at=_timestamp(payload, "opened_at"),
        entry_price=_decimal(payload, "entry_price"),
        entry_fee_usdt=_decimal(payload, "entry_fee_usdt"),
        initial_quantity=_decimal(payload, "initial_quantity"),
        remaining_quantity=_decimal(payload, "remaining_quantity"),
        stop_loss=_decimal(payload, "stop_loss"),
        trailing_stop=_decimal(payload, "trailing_stop"),
        atr=_decimal(payload, "atr"),
        take_profit_levels=tuple(
            _decimal_value(item, "take profit")
            for item in _sequence(payload, "take_profit_levels")
        ),
        opportunity_id=(
            _optional_text(payload, "opportunity_id")
            or f"opportunity:{_text(payload, 'candidate_id')}"
        ),
        take_profit_quantity_ratios=tuple(
            _decimal_value(item, "take profit ratio")
            for item in _sequence(payload, "take_profit_quantity_ratios")
        ),
        status=VirtualPositionLifecycleStatus(_text(payload, "status")),
        next_target_index=_integer(payload, "next_target_index"),
        realized_pnl_usdt=_decimal(payload, "realized_pnl_usdt"),
        exits=tuple(
            _exit_from_payload(_mapping(item, "position exit"))
            for item in _sequence(payload, "exits")
        ),
        closure_review=(
            _review_from_payload(_mapping(review_payload, "closure review"))
            if review_payload is not None
            else None
        ),
        position_side=VirtualPositionSide(_text(payload, "position_side")),
        maximum_holding_bars=_optional_integer(payload, "maximum_holding_bars"),
        breakeven_trigger_r=_optional_decimal(payload, "breakeven_trigger_r"),
        trailing_atr_multiple=_optional_decimal(payload, "trailing_atr_multiple"),
        bars_held=_integer(payload, "bars_held"),
        maximum_favorable_excursion_usdt=_decimal(
            payload, "maximum_favorable_excursion_usdt"
        ),
        maximum_adverse_excursion_usdt=_decimal(
            payload, "maximum_adverse_excursion_usdt"
        ),
        fee_ratio=_decimal(payload, "fee_ratio"),
        slippage_ratio=_decimal(payload, "slippage_ratio"),
        tick_size=_decimal(payload, "tick_size"),
        strategy_id=_text(payload, "strategy_id"),
        strategy_version=_text(payload, "strategy_version"),
        strategy_config_version=_text(payload, "strategy_config_version"),
        strategy_config_hash=_text(payload, "strategy_config_hash"),
        regime=_text(payload, "regime"),
        timeframe=_text(payload, "timeframe"),
        snapshot_id=_text(payload, "snapshot_id"),
        decision_id=_text(payload, "decision_id"),
        dge_decision=_text(payload, "dge_decision"),
        risk_policy_version=_text(payload, "risk_policy_version"),
        validation_version=_text(payload, "validation_version"),
        entry_reason=tuple(
            _text_item(item, "entry reason")
            for item in _sequence(payload, "entry_reason")
        ),
        entry_slippage_cost_usdt=_decimal(payload, "entry_slippage_cost_usdt"),
        funding_cost_usdt=_decimal(payload, "funding_cost_usdt"),
        isolated_margin_usdt=_optional_decimal(payload, "isolated_margin_usdt"),
        initial_margin_usdt=_optional_decimal(payload, "initial_margin_usdt"),
        maintenance_margin_ratio=_optional_decimal(payload, "maintenance_margin_ratio"),
        liquidation_price=_optional_decimal(payload, "liquidation_price"),
        leverage=_optional_integer(payload, "leverage"),
        liquidation_fee_ratio=_decimal(payload, "liquidation_fee_ratio"),
    )


def _exit_from_payload(payload: Mapping[str, object]) -> VirtualPositionExit:
    return VirtualPositionExit(
        timestamp=_timestamp(payload, "timestamp"),
        reason=BacktestExitReason(_text(payload, "reason")),
        price=_decimal(payload, "price"),
        quantity=_decimal(payload, "quantity"),
        fee_usdt=_decimal(payload, "fee_usdt"),
        net_pnl_usdt=_decimal(payload, "net_pnl_usdt"),
        slippage_cost_usdt=_decimal(payload, "slippage_cost_usdt"),
    )


def _review_from_payload(payload: Mapping[str, object]) -> VirtualClosureReview:
    return VirtualClosureReview(
        exit_reason=BacktestExitReason(_text(payload, "exit_reason")),
        lifecycle_error=_optional_text(payload, "lifecycle_error"),
        stop_quality=_text(payload, "stop_quality"),
        trailing_quality=_text(payload, "trailing_quality"),
        ignored_signals=_integer(payload, "ignored_signals"),
        htf_weakness=_boolean(payload, "htf_weakness"),
        volatility_expansion=_boolean(payload, "volatility_expansion"),
        level_break=_boolean(payload, "level_break"),
        staged_exit_alternative=_text(payload, "staged_exit_alternative"),
        lesson_candidate=_text(payload, "lesson_candidate"),
    )


def _closed_trade_payload(trade: VirtualClosedTradeRecord) -> dict[str, object]:
    from ai4binance.reporting import to_primitive

    return cast(dict[str, object], to_primitive(trade))


def _closed_trade_from_payload(
    payload: Mapping[str, object],
) -> VirtualClosedTradeRecord:
    attribution = _mapping(payload.get("attribution"), "closed trade attribution")
    return VirtualClosedTradeRecord(
        trade_id=_text(payload, "trade_id"),
        attribution=ClosedTradeAttribution(
            strategy_id=_text(attribution, "strategy_id"),
            strategy_version=_text(attribution, "strategy_version"),
            strategy_config_version=_text(attribution, "strategy_config_version"),
            strategy_config_hash=_text(attribution, "strategy_config_hash"),
            market=_text(attribution, "market"),
            symbol=_text(attribution, "symbol"),
            regime=_text(attribution, "regime"),
            timeframe=_text(attribution, "timeframe"),
            snapshot_id=_text(attribution, "snapshot_id"),
            decision_id=_text(attribution, "decision_id"),
            opportunity_id=(
                _optional_text(attribution, "opportunity_id")
                or f"opportunity:{_text(attribution, 'decision_id')}"
            ),
        ),
        direction=TradeDirection(_text(payload, "direction")),
        entry_time=_timestamp(payload, "entry_time"),
        exit_time=_timestamp(payload, "exit_time"),
        entry_price=_decimal(payload, "entry_price"),
        exit_price=_decimal(payload, "exit_price"),
        quantity=_decimal(payload, "quantity"),
        risk_at_entry=_decimal(payload, "risk_at_entry"),
        entry_reason=tuple(
            _text_item(item, "entry reason")
            for item in _sequence(payload, "entry_reason")
        ),
        exit_reason=BacktestExitReason(_text(payload, "exit_reason")),
        dge_decision=_text(payload, "dge_decision"),
        risk_policy_version=_text(payload, "risk_policy_version"),
        validation_version=_text(payload, "validation_version"),
        gross_pnl_usdt=_decimal(payload, "gross_pnl_usdt"),
        fee_cost_usdt=_decimal(payload, "fee_cost_usdt"),
        slippage_cost_usdt=_decimal(payload, "slippage_cost_usdt"),
        funding_cost_usdt=_decimal(payload, "funding_cost_usdt"),
        net_pnl_usdt=_decimal(payload, "net_pnl_usdt"),
        realized_r_multiple=_decimal(payload, "realized_r_multiple"),
        maximum_favorable_excursion=_decimal(payload, "maximum_favorable_excursion"),
        maximum_adverse_excursion=_decimal(payload, "maximum_adverse_excursion"),
        false_breakout=_boolean(payload, "false_breakout"),
    )


def _equity_curve_from_payload(
    payload: Mapping[str, object],
) -> HistoricalMarketEquityCurve:
    return HistoricalMarketEquityCurve(
        market=VirtualMarket(_text(payload, "market")),
        points=tuple(
            DailyEquityPoint(
                timestamp=_timestamp(point, "timestamp"),
                equity_usdt=_decimal(point, "equity_usdt"),
            )
            for point in (
                _mapping(item, "equity point") for item in _sequence(payload, "points")
            )
        ),
    )


def _canonical_sha256(value: object) -> str:
    import hashlib

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"historical replay {label} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(payload: Mapping[str, object], name: str) -> tuple[object, ...]:
    value = payload.get(name)
    if not isinstance(value, list):
        raise ValueError(f"historical replay persisted {name} must be an array")
    return tuple(value)


def _text(payload: Mapping[str, object], name: str) -> str:
    return _text_item(payload.get(name), name)


def _text_item(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"historical replay persisted {label} is invalid")
    return value


def _optional_text(payload: Mapping[str, object], name: str) -> str | None:
    value = payload.get(name)
    return None if value is None else _text_item(value, name)


def _decimal(payload: Mapping[str, object], name: str) -> Decimal:
    return _decimal_value(payload.get(name), name)


def _decimal_value(value: object, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        raise ValueError(f"historical replay persisted {label} is invalid") from None
    if not parsed.is_finite():
        raise ValueError(f"historical replay persisted {label} is invalid")
    return parsed


def _optional_decimal(
    payload: Mapping[str, object],
    name: str,
) -> Decimal | None:
    value = payload.get(name)
    return None if value is None else _decimal_value(value, name)


def _integer(payload: Mapping[str, object], name: str) -> int:
    return _integer_value(payload.get(name), name)


def _integer_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"historical replay persisted {label} is invalid")
    return value


def _optional_integer(payload: Mapping[str, object], name: str) -> int | None:
    value = payload.get(name)
    return None if value is None else _integer_value(value, name)


def _timestamp(payload: Mapping[str, object], name: str) -> datetime:
    value = _text(payload, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"historical replay persisted {name} timestamp is invalid"
        ) from None
    _require_utc(f"historical replay persisted {name}", parsed)
    return parsed


def _boolean(payload: Mapping[str, object], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"historical replay persisted {name} must be boolean")
    return value


def _require_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use timezone-aware UTC")


__all__ = (
    "VIRTUAL_WALLET_RESET_CONFIRMATION",
    "HistoricalReplayResetCapital",
    "HistoricalReplayRestoredState",
    "HistoricalReplayStateStore",
    "HistoricalReplayWalletResetResult",
)

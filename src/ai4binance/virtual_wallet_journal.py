"""Persistent, tamper-evident journals for independent virtual wallets."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import cast

from ai4binance.application import IndependentVirtualPortfolios, VirtualPortfolioState
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.ops.user_reports import (
    render_professional_summary,
    user_report_paths,
    write_user_report_files,
)
from ai4binance.research.virtual_runtime import (
    VirtualManagedPosition,
    VirtualMarketRuntime,
    VirtualRuntimeDecision,
)
from ai4binance.research.virtual_runtime_request import VirtualRuntimeRequest
from ai4binance.schemas import DataQuality, MarketSnapshot
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified

_MARKETS = ("SPOT", "USD_M_FUTURES")
_WALLET_NAMES = {
    "SPOT": "Virtual_Spot_Wallet",
    "USD_M_FUTURES": "Virtual_Futures_Wallet",
}
_INITIAL_EQUITY_USDT = Decimal("1000")
_INITIAL_EVENT = "VIRTUAL_WALLET_INITIALIZED"
_MOVEMENT_EVENT = "VIRTUAL_WALLET_MOVEMENT_RECORDED"
_DAILY_LOSS_TUNING_THRESHOLD = 3


class VirtualWalletJournalError(RuntimeError):
    """Fail-closed virtual-wallet persistence or continuity error."""


@dataclass(slots=True)
class VirtualWalletJournal:
    """Own persistent Spot/Futures state and every balance-changing movement."""

    ledger_path: Path
    state_path: Path
    report_root: Path
    _store: JsonlAuditStore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._store = JsonlAuditStore(
            self.ledger_path,
            durable=True,
            tamper_evident=True,
        )

    def initialize(self, observed_at: datetime) -> IndependentVirtualPortfolios:
        """Create each wallet once, then reconstruct current state from the journal."""

        try:
            timestamp = _utc_timestamp(observed_at)
            if self.state_path.exists() and not self.ledger_path.exists():
                raise ValueError("VIRTUAL_WALLET_LEDGER_MISSING_FOR_EXISTING_STATE")
            movements = self._read_movements()
            portfolios = self._latest_portfolios(movements)
            for market in _MARKETS:
                if market not in portfolios:
                    portfolio = _initial_portfolio(market)
                    self._append_movement(
                        event_type=_INITIAL_EVENT,
                        movement=_movement_payload(
                            movement_id=f"virtual-wallet:{market}:genesis",
                            timestamp=timestamp,
                            cycle_id="GENESIS",
                            snapshot_id="GENESIS",
                            market=market,
                            movement_type="INITIAL_BALANCE",
                            decision_status="INITIALIZED",
                            trade_action=None,
                            before=None,
                            after=portfolio,
                        ),
                    )
                    portfolios[market] = portfolio
            result = _independent_portfolios(portfolios)
            self._write_outputs(timestamp, result)
            return result
        except VirtualWalletJournalError:
            raise
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise VirtualWalletJournalError(str(error)) from error

    def analysis_snapshot(self, snapshot: MarketSnapshot) -> MarketSnapshot:
        """Bind journal-derived simulation capital before deterministic risk sizing."""
        if (
            snapshot.wallet_summary
            or snapshot.inventory_summary
            or snapshot.open_orders
        ):
            raise VirtualWalletJournalError("VIRTUAL_WALLET_PRIVATE_CONTEXT_REJECTED")
        portfolios = self.initialize(snapshot.created_at)
        market = snapshot.market_type.strip().upper()
        if market not in _MARKETS:
            raise VirtualWalletJournalError("VIRTUAL_WALLET_MARKET_INVALID")
        portfolio = portfolios.spot if market == "SPOT" else portfolios.futures
        self.manage_positions(snapshot)
        portfolios = self.initialize(snapshot.created_at)
        portfolio = portfolios.spot if market == "SPOT" else portfolios.futures
        positions = self._latest_positions(self._read_movements())
        managed = positions.get(market)
        # The legacy aggregate wallet does not identify the asset it holds.
        # Never attribute an existing position to a different scanned symbol.
        inventory = (
            {"quantity": "0", "exposure_usdt": "0"}
            if portfolio.open_position_count == 0 and portfolio.inventory_quantity == 0
            else {}
        )
        if managed is not None:
            position, _ = managed
            quantity = (
                position.remaining_quantity
                if position.symbol == snapshot.symbol
                else Decimal(0)
            )
            inventory = {
                "quantity": str(quantity),
                "exposure_usdt": str(quantity * position.entry_price),
            }
        daily_loss = Decimal(0)
        for movement in self._read_movements():
            if movement["market"] != market or movement.get("before") is None:
                continue
            timestamp = datetime.fromisoformat(str(movement["timestamp"]))
            if (
                timestamp.astimezone(UTC).date()
                != snapshot.created_at.astimezone(UTC).date()
            ):
                continue
            before = VirtualPortfolioState.from_payload(
                cast(Mapping[str, object], movement["before"])
            )
            after = VirtualPortfolioState.from_payload(
                cast(Mapping[str, object], movement["after"])
            )
            daily_loss += max(
                Decimal(0), before.realized_pnl_usdt - after.realized_pnl_usdt
            )
        return replace(
            snapshot,
            wallet_summary={
                "source": "VIRTUAL_PORTFOLIO",
                "portfolio_id": portfolio.portfolio_id,
                "equity_usdt": str(portfolio.equity_usdt),
                "cash_usdt": str(portfolio.cash_usdt),
                "daily_loss_usdt": str(daily_loss),
                "open_risk_usdt": str(portfolio.current_open_risk_usdt),
                "open_position_count": portfolio.open_position_count,
            },
            inventory_summary=inventory,
            market_metadata={
                **snapshot.market_metadata,
                "consecutive_losses": portfolio.consecutive_losses,
                "virtual_position_identity_unavailable": not bool(inventory),
                "virtual_managed_position_active": managed is not None,
            },
        )

    def portfolio_builder(
        self,
        snapshot: object,
        candidate: object,
    ) -> VirtualPortfolioState:
        """Supply the persisted wallet for the candidate's exact market."""

        observed_at = getattr(snapshot, "created_at", None)
        if not isinstance(observed_at, datetime):
            raise VirtualWalletJournalError("VIRTUAL_WALLET_TIMESTAMP_INVALID")
        market = str(getattr(candidate, "market_type", "")).strip().upper()
        portfolios = self.initialize(observed_at)
        if market == "SPOT":
            return portfolios.spot
        if market == "USD_M_FUTURES":
            return portfolios.futures
        raise VirtualWalletJournalError("VIRTUAL_WALLET_MARKET_INVALID")

    def record_cycle(
        self,
        *,
        snapshot_id: str,
        observed_at: datetime,
        decision: object | None,
        request: VirtualRuntimeRequest | None = None,
    ) -> dict[str, object]:
        """Persist a virtual balance change and refresh the complete report."""

        try:
            timestamp = _utc_timestamp(observed_at)
            portfolios = self.initialize(timestamp)
            current = {
                "SPOT": portfolios.spot,
                "USD_M_FUTURES": portfolios.futures,
            }
            if decision is not None:
                before = getattr(decision, "portfolio_before", None)
                after = getattr(decision, "portfolio_after", None)
                if not isinstance(before, VirtualPortfolioState) or not isinstance(
                    after, VirtualPortfolioState
                ):
                    raise ValueError("VIRTUAL_WALLET_DECISION_STATE_INVALID")
                if (
                    before.market != after.market
                    or before.portfolio_id != after.portfolio_id
                ):
                    raise ValueError("VIRTUAL_WALLET_DECISION_IDENTITY_DRIFT")
                current_portfolio = current.get(before.market)
                if current_portfolio == after:
                    return self._write_outputs(timestamp, portfolios)
                if current_portfolio != before:
                    raise ValueError("VIRTUAL_WALLET_STATE_DRIFT")
                if after != before:
                    managed_position = None
                    if request is not None:
                        if not isinstance(decision, VirtualRuntimeDecision):
                            raise ValueError("VIRTUAL_WALLET_TYPED_DECISION_REQUIRED")
                        if (
                            request.portfolio != before
                            or request.snapshot_id != snapshot_id
                        ):
                            raise ValueError("VIRTUAL_WALLET_REQUEST_BINDING_DRIFT")
                        intent = decision.trade_intent
                        if intent is None or any(
                            getattr(intent, key) != getattr(request, key)
                            for key in (
                                "snapshot_id",
                                "decision_id",
                                "candidate_id",
                                "symbol",
                                "market",
                                "action",
                                "stop_loss",
                                "take_profit_levels",
                            )
                        ):
                            raise ValueError("VIRTUAL_WALLET_INTENT_BINDING_DRIFT")
                        if before.market in self._latest_positions(
                            self._read_movements()
                        ):
                            raise ValueError("VIRTUAL_WALLET_POSITION_ALREADY_OPEN")
                        managed_position = (
                            VirtualMarketRuntime.materialize_managed_position(
                                request=request,
                                decision=decision,
                                opened_at=timestamp,
                            )
                        )
                        if managed_position.market != before.market:
                            raise ValueError("VIRTUAL_WALLET_POSITION_MARKET_DRIFT")
                    status = _enum_text(getattr(decision, "status", None))
                    trade_intent = getattr(decision, "trade_intent", None)
                    action = (
                        _enum_text(getattr(trade_intent, "action", None))
                        if trade_intent is not None
                        else None
                    )
                    movement_id = f"virtual-wallet:{before.market}:{snapshot_id}"
                    self._append_movement(
                        event_type=_MOVEMENT_EVENT,
                        movement=_movement_payload(
                            movement_id=movement_id,
                            timestamp=timestamp,
                            cycle_id=snapshot_id,
                            snapshot_id=snapshot_id,
                            market=before.market,
                            movement_type="VIRTUAL_SIMULATION_MOVEMENT",
                            decision_status=status or "UNKNOWN",
                            trade_action=action,
                            before=before,
                            after=after,
                            position=managed_position,
                            position_cursor=timestamp
                            if managed_position is not None
                            else None,
                        ),
                    )
                    current[before.market] = after
            result = _independent_portfolios(current)
            return self._write_outputs(timestamp, result)
        except VirtualWalletJournalError:
            raise
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise VirtualWalletJournalError(str(error)) from error

    def open_position_symbols(self) -> tuple[str, ...]:
        """Recover held Spot symbols from the verified journal for scheduling."""
        return tuple(
            position.symbol
            for position, _ in self._latest_positions(self._read_movements()).values()
            if position.market == "SPOT"
        )

    def dashboard_snapshot(self, observed_at: datetime) -> dict[str, object]:
        """Project verified wallet balances, period returns, and bounded details."""

        try:
            timestamp = _utc_timestamp(observed_at)
            movements = self._read_movements()
            portfolios = self._latest_portfolios(movements)
            if set(portfolios) != set(_MARKETS):
                raise ValueError("VIRTUAL_WALLET_PORTFOLIOS_INCOMPLETE")
            wallets: dict[str, object] = {}
            for market in _MARKETS:
                portfolio = portfolios[market]
                market_movements = tuple(
                    item for item in movements if item["market"] == market
                )
                wallets[_WALLET_NAMES[market]] = {
                    **portfolio.to_payload(),
                    "inception_at": market_movements[0]["timestamp"],
                    "period_changes": {
                        "daily": _period_change(
                            market_movements, portfolio, timestamp - timedelta(days=1)
                        ),
                        "weekly": _period_change(
                            market_movements, portfolio, timestamp - timedelta(days=7)
                        ),
                        "monthly": _period_change(
                            market_movements, portfolio, timestamp - timedelta(days=30)
                        ),
                    },
                }
            return {
                "schema_version": "VirtualWalletDashboard/v1",
                "observed_at": timestamp.isoformat(),
                "status": "CURRENT",
                "wallets": wallets,
                "movements": [
                    _movement_dashboard_row(item) for item in reversed(movements[-100:])
                ],
                "trade_records": _dashboard_trade_records(movements),
                "movement_count": len(movements),
                "movement_limit": 100,
                **{
                    "execution_allowed": False,
                    "promotion_status": "RESEARCH_ONLY",
                    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
                },
            }
        except VirtualWalletJournalError:
            raise
        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise VirtualWalletJournalError(str(error)) from error

    def daily_loss_tuning_trigger(self, observed_at: datetime) -> dict[str, object]:
        """Create one deterministic research trigger per three same-day losses."""

        try:
            return _daily_loss_tuning_trigger(
                self._read_movements(),
                _utc_timestamp(observed_at),
            )
        except VirtualWalletJournalError:
            raise
        except (ArithmeticError, KeyError, TypeError, ValueError) as error:
            raise VirtualWalletJournalError(str(error)) from error

    @staticmethod
    def _latest_positions(
        movements: tuple[dict[str, object], ...],
    ) -> dict[str, tuple[VirtualManagedPosition, datetime]]:
        from ai4binance.historical_replay_state import _position_from_payload

        positions: dict[str, tuple[VirtualManagedPosition, datetime]] = {}
        for movement in movements:
            market = str(movement["market"])
            raw = movement.get("managed_position")
            if raw is None:
                positions.pop(market, None)
                continue
            if not isinstance(raw, Mapping):
                raise ValueError("VIRTUAL_WALLET_POSITION_PAYLOAD_INVALID")
            position = _position_from_payload(raw)
            cursor = _utc_timestamp(
                datetime.fromisoformat(str(movement.get("position_cursor")))
            )
            after = VirtualPortfolioState.from_payload(
                cast(Mapping[str, object], movement["after"])
            )
            if position.market != market or cursor < position.opened_at:
                raise ValueError("VIRTUAL_WALLET_POSITION_IDENTITY_DRIFT")
            if (
                market == "SPOT"
                and position.remaining_quantity != after.inventory_quantity
            ):
                raise ValueError("VIRTUAL_WALLET_POSITION_QUANTITY_DRIFT")
            if position.remaining_quantity > 0:
                positions[market] = (position, cursor)
            else:
                positions.pop(market, None)
        return positions

    def manage_positions(self, snapshot: MarketSnapshot) -> None:
        """Apply canonical exits to new, contiguous closed candles exactly once."""
        from ai4binance.reporting import to_primitive

        movements = self._read_movements()
        managed = self._latest_positions(movements).get(snapshot.market_type.upper())
        if managed is None or managed[0].symbol != snapshot.symbol:
            return
        position, cursor = managed
        if snapshot.data_quality is not DataQuality.DATA_VALID:
            raise VirtualWalletJournalError("VIRTUAL_POSITION_DATA_INVALID")
        if position.market != "SPOT":
            raise VirtualWalletJournalError(
                "VIRTUAL_FUTURES_LIFECYCLE_CONTEXT_UNAVAILABLE"
            )
        duration = timeframe_duration(position.timeframe)
        candles = snapshot.ohlcv_by_timeframe.get(position.timeframe, ())
        if not candles:
            raise VirtualWalletJournalError("VIRTUAL_POSITION_CANDLES_MISSING")
        if any(
            right.timestamp - left.timestamp != duration
            for left, right in pairwise(candles)
        ):
            raise VirtualWalletJournalError("VIRTUAL_POSITION_CANDLE_GAP")
        portfolio = self._latest_portfolios(movements)[position.market]
        for candle in candles:
            if (
                candle.timestamp < cursor
                or candle.timestamp + duration > snapshot.created_at
            ):
                continue
            if candle.timestamp - cursor >= duration:
                raise VirtualWalletJournalError("VIRTUAL_POSITION_CANDLE_GAP")
            update = VirtualMarketRuntime().process_position(
                position=position,
                portfolio=portfolio,
                candle=candle,
                candle_available_at=candle.timestamp + duration,
            )
            next_cursor = candle.timestamp + duration
            movement = _movement_payload(
                movement_id=f"virtual-position:{position.position_id}:{next_cursor.isoformat()}",
                timestamp=snapshot.created_at,
                cycle_id=snapshot.snapshot_id,
                snapshot_id=snapshot.snapshot_id,
                market=position.market,
                movement_type="VIRTUAL_SIMULATION_MOVEMENT",
                decision_status=update.position_after.status.value,
                trade_action="SELL" if update.exit_reason is not None else None,
                before=portfolio,
                after=update.portfolio_after,
                position=update.position_after,
                position_cursor=next_cursor,
            )
            movement["closed_trade"] = to_primitive(update.closed_trade)
            movement["reason_codes"] = update.reason_codes
            self._append_movement(event_type=_MOVEMENT_EVENT, movement=movement)
            position, portfolio, cursor = (
                update.position_after,
                update.portfolio_after,
                next_cursor,
            )
            if position.remaining_quantity == 0:
                break

    def _append_movement(
        self,
        *,
        event_type: str,
        movement: Mapping[str, object],
    ) -> None:
        timestamp = datetime.fromisoformat(str(movement["timestamp"]))
        self._store.append_verified_idempotent(
            AuditEvent(
                event_type=event_type,
                timestamp=timestamp,
                snapshot_id=str(movement["movement_id"]),
                payload={"movement": dict(movement)},
            )
        )

    def _read_movements(self) -> tuple[dict[str, object], ...]:
        if not self.ledger_path.exists():
            return ()
        if self.ledger_path.stat().st_size == 0:
            return ()
        self._store.verify_chain()
        movements: list[dict[str, object]] = []
        latest: dict[str, VirtualPortfolioState] = {}
        movement_ids: set[str] = set()
        with self.ledger_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if not isinstance(event, Mapping):
                    raise ValueError("VIRTUAL_WALLET_EVENT_INVALID")
                event_type = event.get("event_type")
                if event_type not in {_INITIAL_EVENT, _MOVEMENT_EVENT}:
                    raise ValueError("VIRTUAL_WALLET_EVENT_TYPE_INVALID")
                event_payload = event.get("payload")
                if not isinstance(event_payload, Mapping):
                    raise ValueError("VIRTUAL_WALLET_EVENT_PAYLOAD_INVALID")
                movement = event_payload.get("movement")
                if not isinstance(movement, Mapping):
                    raise ValueError("VIRTUAL_WALLET_MOVEMENT_INVALID")
                validated = _validated_movement(movement)
                if event.get("timestamp") != validated["timestamp"]:
                    raise ValueError("VIRTUAL_WALLET_EVENT_TIMESTAMP_DRIFT")
                expected_type = (
                    "INITIAL_BALANCE"
                    if event_type == _INITIAL_EVENT
                    else "VIRTUAL_SIMULATION_MOVEMENT"
                )
                if validated["movement_type"] != expected_type:
                    raise ValueError("VIRTUAL_WALLET_MOVEMENT_TYPE_DRIFT")
                movement_id = cast(str, validated["movement_id"])
                if movement_id in movement_ids:
                    raise ValueError("VIRTUAL_WALLET_MOVEMENT_DUPLICATE")
                movement_ids.add(movement_id)
                market = cast(str, validated["market"])
                before_payload = validated.get("before")
                previous = latest.get(market)
                if before_payload is None:
                    if previous is not None:
                        raise ValueError("VIRTUAL_WALLET_GENESIS_DUPLICATE")
                else:
                    before = VirtualPortfolioState.from_payload(
                        cast(Mapping[str, object], before_payload)
                    )
                    if previous != before:
                        raise ValueError("VIRTUAL_WALLET_MOVEMENT_CHAIN_DRIFT")
                after = VirtualPortfolioState.from_payload(
                    cast(Mapping[str, object], validated["after"])
                )
                latest[market] = after
                movements.append(validated)
        return tuple(movements)

    @staticmethod
    def _latest_portfolios(
        movements: tuple[dict[str, object], ...],
    ) -> dict[str, VirtualPortfolioState]:
        latest: dict[str, VirtualPortfolioState] = {}
        for movement in movements:
            market = cast(str, movement["market"])
            latest[market] = VirtualPortfolioState.from_payload(
                cast(Mapping[str, object], movement["after"])
            )
        return latest

    def _write_outputs(
        self,
        observed_at: datetime,
        portfolios: IndependentVirtualPortfolios,
    ) -> dict[str, object]:
        movements = self._read_movements()
        positions = self._latest_positions(movements)
        wallets = {
            _WALLET_NAMES["SPOT"]: portfolios.spot.to_payload(),
            _WALLET_NAMES["USD_M_FUTURES"]: portfolios.futures.to_payload(),
        }
        state_payload: dict[str, object] = {
            "schema_version": "VirtualWalletState/v1",
            "observed_at": observed_at.isoformat(),
            "status": "RUNNING",
            "wallets": wallets,
            "open_position_symbols": [
                position.symbol for position, _ in positions.values()
            ],
            "movement_count": len(movements),
            "balance_change_count": sum(
                item["movement_type"] != "INITIAL_BALANCE" for item in movements
            ),
            "ledger_path": str(self.ledger_path),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        write_json_object_verified(
            self.state_path,
            state_payload,
            blocker="VIRTUAL_WALLET_STATE_WRITE_FAILED",
            subject_id="virtual-wallet-state",
            indent=2,
            durable=True,
        )
        stamp = observed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        paths = user_report_paths(
            self.report_root,
            "virtual_wallets",
            stamp,
            file_stem="virtual_wallet_report",
        )
        report_payload = {
            **state_payload,
            "command": "virtual-wallet-report",
            "all_movements": movements,
            "report_paths": {
                "json": str(paths.json_path),
                "markdown": str(paths.markdown_path),
                "latest_json": str(paths.latest_json_path),
                "latest_markdown": str(paths.latest_markdown_path),
            },
        }
        write_user_report_files(
            paths,
            report_payload,
            _render_report(report_payload),
        )
        return report_payload


def _initial_portfolio(market: str) -> VirtualPortfolioState:
    suffix = "spot" if market == "SPOT" else "futures"
    return VirtualPortfolioState(
        portfolio_id=f"virtual-wallet:{suffix}",
        market=market,
        cash_usdt=_INITIAL_EQUITY_USDT,
        equity_usdt=_INITIAL_EQUITY_USDT,
    )


def _daily_loss_tuning_trigger(
    movements: tuple[dict[str, object], ...],
    observed_at: datetime,
) -> dict[str, object]:
    safe_state = {
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    observed_day = observed_at.astimezone(UTC).date()
    losses_by_market: dict[str, list[dict[str, object]]] = {}
    for movement in movements:
        closed_trade = movement.get("closed_trade")
        position = movement.get("managed_position")
        if not isinstance(closed_trade, Mapping) or not isinstance(position, Mapping):
            continue
        net_pnl = _required_decimal(closed_trade, "net_pnl_usdt")
        if net_pnl >= 0:
            continue
        exit_time = datetime.fromisoformat(
            _aware_timestamp_text(closed_trade.get("exit_time"))
        ).astimezone(UTC)
        if exit_time.date() != observed_day:
            continue
        market = _required_text(movement, "market").upper()
        if market not in _MARKETS:
            raise ValueError("VIRTUAL_LOSS_TUNING_MARKET_INVALID")
        entry_price = _required_decimal(position, "entry_price")
        quantity = _required_decimal(position, "initial_quantity")
        notional = entry_price * quantity
        if notional <= 0:
            raise ValueError("VIRTUAL_LOSS_TUNING_NOTIONAL_INVALID")
        losses_by_market.setdefault(market, []).append(
            {
                "movement_id": _required_text(movement, "movement_id"),
                "trade_id": _required_text(closed_trade, "trade_id"),
                "exit_time": exit_time.isoformat(),
                "net_pnl_usdt": str(net_pnl),
                "net_return": str(net_pnl / notional),
                "subject": {
                    "market": market,
                    "symbol": _required_text(position, "symbol").upper(),
                    "timeframe": _required_text(position, "timeframe"),
                    "strategy_id": _required_text(position, "strategy_id"),
                    "strategy_version": _required_text(position, "strategy_version"),
                    "strategy_config_hash": _required_text(
                        position, "strategy_config_hash"
                    ),
                },
            }
        )

    triggers: list[dict[str, object]] = []
    for market, losses in losses_by_market.items():
        completed_count = (
            len(losses) // _DAILY_LOSS_TUNING_THRESHOLD
        ) * _DAILY_LOSS_TUNING_THRESHOLD
        if completed_count < _DAILY_LOSS_TUNING_THRESHOLD:
            continue
        batch = losses[completed_count - _DAILY_LOSS_TUNING_THRESHOLD : completed_count]
        subjects = list(
            {
                json.dumps(item["subject"], sort_keys=True): item["subject"]
                for item in batch
            }.values()
        )
        identity = {
            "kind": "SAME_UTC_DAY_NET_LOSS_BATCH",
            "market": market,
            "trade_date": observed_day.isoformat(),
            "evidence_ids": [item["movement_id"] for item in batch],
        }
        digest = sha256(
            json.dumps(identity, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        triggers.append(
            {
                "schema_version": "VirtualLossTuningTrigger/v1",
                "status": "TRIGGERED",
                "trigger_id": f"virtual-loss-tuning:{digest[:24]}",
                **identity,
                "loss_threshold": _DAILY_LOSS_TUNING_THRESHOLD,
                "loss_count_today": len(losses),
                "observed_at": observed_at.isoformat(),
                "losses": batch,
                "subjects": subjects,
                **safe_state,
            }
        )
    if not triggers:
        return {
            "schema_version": "VirtualLossTuningTrigger/v1",
            "status": "NOT_TRIGGERED",
            "trade_date": observed_day.isoformat(),
            "loss_threshold": _DAILY_LOSS_TUNING_THRESHOLD,
            "loss_count_today": max(
                (len(losses) for losses in losses_by_market.values()),
                default=0,
            ),
            "observed_at": observed_at.isoformat(),
            **safe_state,
        }
    return max(triggers, key=lambda item: str(item["observed_at"]))


def _independent_portfolios(
    portfolios: Mapping[str, VirtualPortfolioState],
) -> IndependentVirtualPortfolios:
    return IndependentVirtualPortfolios(
        spot=portfolios["SPOT"],
        futures=portfolios["USD_M_FUTURES"],
    )


def _movement_payload(
    *,
    movement_id: str,
    timestamp: datetime,
    cycle_id: str,
    snapshot_id: str,
    market: str,
    movement_type: str,
    decision_status: str,
    trade_action: str | None,
    before: VirtualPortfolioState | None,
    after: VirtualPortfolioState,
    position: VirtualManagedPosition | None = None,
    position_cursor: datetime | None = None,
) -> dict[str, object]:
    from ai4binance.historical_replay_state import _position_payload

    equity_before = before.equity_usdt if before is not None else Decimal("0")
    cash_before = before.cash_usdt if before is not None else Decimal("0")
    return {
        "movement_id": movement_id,
        "timestamp": timestamp.isoformat(),
        "cycle_id": cycle_id,
        "snapshot_id": snapshot_id,
        "market": market,
        "wallet_name": _WALLET_NAMES[market],
        "movement_type": movement_type,
        "decision_status": decision_status,
        "trade_action": trade_action,
        "equity_delta_usdt": str(after.equity_usdt - equity_before),
        "cash_delta_usdt": str(after.cash_usdt - cash_before),
        "before": before.to_payload() if before is not None else None,
        "after": after.to_payload(),
        "managed_position": _position_payload(position)
        if position is not None
        else None,
        "position_cursor": position_cursor.isoformat()
        if position_cursor is not None
        else None,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _period_change(
    movements: tuple[dict[str, object], ...],
    current: VirtualPortfolioState,
    cutoff: datetime,
) -> dict[str, object]:
    baseline_movement = next(
        (
            item
            for item in reversed(movements)
            if datetime.fromisoformat(str(item["timestamp"])).astimezone(UTC) <= cutoff
        ),
        None,
    )
    coverage = "FULL_PERIOD"
    if baseline_movement is None:
        baseline_movement = movements[0]
        coverage = "SINCE_INCEPTION"
    baseline = VirtualPortfolioState.from_payload(
        cast(Mapping[str, object], baseline_movement["after"])
    )
    percent = (
        (current.equity_usdt - baseline.equity_usdt)
        / baseline.equity_usdt
        * Decimal("100")
    )
    return {
        "percent_change": str(percent),
        "baseline_equity_usdt": str(baseline.equity_usdt),
        "baseline_at": baseline_movement["timestamp"],
        "coverage": coverage,
    }


def _movement_dashboard_row(item: Mapping[str, object]) -> dict[str, object]:
    before = item.get("before")
    after = cast(Mapping[str, object], item["after"])
    position = item.get("managed_position")
    closed = item.get("closed_trade")
    reasons = item.get("reason_codes", ())
    return {
        "movement_id": item["movement_id"],
        "timestamp": item["timestamp"],
        "market": item["market"],
        "wallet_name": item["wallet_name"],
        "movement_type": item["movement_type"],
        "decision_status": item["decision_status"],
        "trade_action": item.get("trade_action"),
        "equity_before_usdt": _state_value(before, "equity_usdt", None),
        "equity_after_usdt": after["equity_usdt"],
        "equity_delta_usdt": item["equity_delta_usdt"],
        "cash_delta_usdt": item["cash_delta_usdt"],
        "symbol": _state_value(position, "symbol", None),
        "position_status": _state_value(position, "status", None),
        "closed_pnl_usdt": _state_value(closed, "net_pnl_usdt", None),
        "reason_codes": tuple(reasons) if isinstance(reasons, (list, tuple)) else (),
    }


def _dashboard_trade_records(
    movements: tuple[dict[str, object], ...],
) -> list[dict[str, object]]:
    """Return only complete, executed virtual-position plans for the dashboard."""

    records: dict[str, dict[str, object]] = {}
    for movement in movements:
        record = _trade_record_dashboard_row(movement)
        if record is not None:
            records[str(record["position_id"])] = record
    return sorted(
        records.values(),
        key=lambda item: (str(item["updated_at"]), str(item["opened_at"])),
        reverse=True,
    )[:100]


def _trade_record_dashboard_row(
    movement: Mapping[str, object],
) -> dict[str, object] | None:
    """Project a journal-backed trade only when its complete risk plan is valid."""

    position = movement.get("managed_position")
    if not isinstance(position, Mapping):
        return None
    try:
        position_id = _required_text(position, "position_id")
        symbol = _required_text(position, "symbol")
        market = _required_text(position, "market").upper()
        if market not in _MARKETS or market != movement.get("market"):
            raise ValueError("VIRTUAL_TRADE_RECORD_MARKET_INVALID")
        opened_at = _aware_timestamp_text(position.get("opened_at"))
        updated_at = _aware_timestamp_text(movement.get("timestamp"))
        entry = _positive_decimal_text(position.get("entry_price"))
        stop_loss = _positive_decimal_text(position.get("stop_loss"))
        targets = position.get("take_profit_levels")
        if not isinstance(targets, (list, tuple)) or not targets:
            raise ValueError("VIRTUAL_TRADE_RECORD_TARGETS_INVALID")
        take_profit_levels = [_positive_decimal_text(value) for value in targets]
        direction = _required_text(position, "position_side")
        status = _required_text(position, "status")
        timeframe = _required_text(position, "timeframe")
        quantity = _positive_decimal_text(position.get("initial_quantity"))
        realized_pnl_usdt = _finite_decimal_text(position.get("realized_pnl_usdt", "0"))
    except (ArithmeticError, TypeError, ValueError):
        return None
    return {
        "position_id": position_id,
        "opened_at": opened_at,
        "updated_at": updated_at,
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
        "status": status,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit_levels": take_profit_levels,
        "quantity": quantity,
        "realized_pnl_usdt": realized_pnl_usdt,
        "leverage": position.get("leverage") if market == "USD_M_FUTURES" else None,
    }


def _positive_decimal_text(value: object) -> str:
    parsed = Decimal(str(value))
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError("VIRTUAL_TRADE_RECORD_LEVEL_INVALID")
    return str(parsed)


def _finite_decimal_text(value: object) -> str:
    parsed = Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError("VIRTUAL_TRADE_RECORD_VALUE_INVALID")
    return str(parsed)


def _aware_timestamp_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("VIRTUAL_TRADE_RECORD_TIMESTAMP_INVALID")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("VIRTUAL_TRADE_RECORD_TIMESTAMP_INVALID")
    return parsed.isoformat()


def _validated_movement(payload: Mapping[str, object]) -> dict[str, object]:
    movement_id = _required_text(payload, "movement_id")
    timestamp = _required_text(payload, "timestamp")
    _utc_timestamp(datetime.fromisoformat(timestamp))
    for key in ("cycle_id", "snapshot_id", "movement_type", "decision_status"):
        _required_text(payload, key)
    market = _required_text(payload, "market").upper()
    if market not in _MARKETS or payload.get("wallet_name") != _WALLET_NAMES[market]:
        raise ValueError("VIRTUAL_WALLET_MOVEMENT_MARKET_INVALID")
    if payload.get("execution_allowed") is not False:
        raise ValueError("VIRTUAL_WALLET_EXECUTION_AUTHORITY_DRIFT")
    if payload.get("promotion_status") != "RESEARCH_ONLY":
        raise ValueError("VIRTUAL_WALLET_PROMOTION_AUTHORITY_DRIFT")
    if payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED":
        raise ValueError("VIRTUAL_WALLET_LIVE_AUTHORITY_DRIFT")
    after = payload.get("after")
    if not isinstance(after, Mapping):
        raise ValueError("VIRTUAL_WALLET_AFTER_STATE_INVALID")
    parsed_after = VirtualPortfolioState.from_payload(after)
    if parsed_after.market != market:
        raise ValueError("VIRTUAL_WALLET_AFTER_MARKET_DRIFT")
    before = payload.get("before")
    equity_before = Decimal("0")
    cash_before = Decimal("0")
    if before is not None:
        if not isinstance(before, Mapping):
            raise ValueError("VIRTUAL_WALLET_BEFORE_STATE_INVALID")
        parsed_before = VirtualPortfolioState.from_payload(before)
        if parsed_before.market != market:
            raise ValueError("VIRTUAL_WALLET_BEFORE_MARKET_DRIFT")
        equity_before = parsed_before.equity_usdt
        cash_before = parsed_before.cash_usdt
    if _required_decimal(payload, "equity_delta_usdt") != (
        parsed_after.equity_usdt - equity_before
    ):
        raise ValueError("VIRTUAL_WALLET_EQUITY_DELTA_DRIFT")
    if _required_decimal(payload, "cash_delta_usdt") != (
        parsed_after.cash_usdt - cash_before
    ):
        raise ValueError("VIRTUAL_WALLET_CASH_DELTA_DRIFT")
    result = dict(payload)
    result["movement_id"] = movement_id
    result["timestamp"] = timestamp
    result["market"] = market
    return result


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"virtual wallet {key} must be non-empty text")
    return value.strip()


def _required_decimal(payload: Mapping[str, object], key: str) -> Decimal:
    try:
        value = Decimal(str(payload.get(key)))
    except (ArithmeticError, TypeError, ValueError) as error:
        raise ValueError(f"virtual wallet {key} must be decimal") from error
    if not value.is_finite():
        raise ValueError(f"virtual wallet {key} must be finite")
    return value


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("VIRTUAL_WALLET_TIMESTAMP_INVALID")
    return value.astimezone(UTC)


def _enum_text(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).strip() if raw is not None else ""


def _render_report(payload: Mapping[str, object]) -> str:
    wallets = cast(Mapping[str, Mapping[str, object]], payload["wallets"])
    movements = cast(tuple[dict[str, object], ...], payload["all_movements"])
    wallet_lines = tuple(
        (
            f"- `{name}`: equity `{state['equity_usdt']}` USDT; "
            f"cash `{state['cash_usdt']}` USDT; realized PnL "
            f"`{state['realized_pnl_usdt']}` USDT; open positions "
            f"`{state['open_position_count']}`."
        )
        for name, state in wallets.items()
    )
    movement_lines = (
        (
            "| Timestamp (UTC) | Wallet | Type | Action | Equity before | "
            "Equity after | Equity delta | Cash delta |"
        ),
        "|---|---|---|---|---:|---:|---:|---:|",
        *(
            (
                f"| {item['timestamp']} | {item['wallet_name']} | "
                f"{item['movement_type']} | {item.get('trade_action') or '-'} | "
                f"{_state_value(item.get('before'), 'equity_usdt', '0')} | "
                f"{_state_value(item.get('after'), 'equity_usdt', '0')} | "
                f"{item['equity_delta_usdt']} | {item['cash_delta_usdt']} |"
            )
            for item in movements
        ),
    )
    return render_professional_summary(
        title="AI4Binance Virtual Wallet Movement Report",
        observed_at=payload["observed_at"],
        status=payload["status"],
        summary=(
            "This report reconstructs the independent Spot and Futures virtual "
            "wallets from the verified append-only movement journal."
        ),
        sections=(
            ("Current Wallet Values", wallet_lines),
            ("All Timestamped Movements", movement_lines),
        ),
    )


def _state_value(value: object, key: str, fallback: object) -> object:
    return value.get(key, fallback) if isinstance(value, Mapping) else fallback


__all__ = ("VirtualWalletJournal", "VirtualWalletJournalError")

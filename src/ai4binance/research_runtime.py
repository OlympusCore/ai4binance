"""Concrete composition helpers for research application workflows."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any, cast

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.application import (
    ResearchApplicationService,
    ResearchWorkflowResult,
    VirtualMarketRuntime,
    VirtualPortfolioState,
)
from ai4binance.application.research import _canonical_sha256
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.events.clock import SimulatedClock
from ai4binance.governance import RunContext
from ai4binance.governance.adapters import VirtualMarketDgeAdapter
from ai4binance.market_context import MarketContextRequest
from ai4binance.outlook import MarketOutlookEngine
from ai4binance.reporting import to_primitive
from ai4binance.research.historical_replay import (
    HistoricalMarketReplayRequest,
    HistoricalReplayDatasetBinding,
    HistoricalReplayExecutionContext,
    VirtualWalletEpoch,
)
from ai4binance.research.virtual_market import DailyEquityPoint, VirtualMarket
from ai4binance.research.virtual_runtime import (
    VirtualClosedTradeRecord,
    VirtualFuturesPositionContext,
    VirtualManagedPosition,
    VirtualPositionLifecycleStatus,
    VirtualPositionUpdateDecision,
)
from ai4binance.schemas import MarketSnapshot, OHLCVCandle
from ai4binance.storage import AuditEvent
from ai4binance.validation.futures_replay import RuntimeFuturesReplayDataset
from ai4binance.whale_fusion.models import DerivativesMetric


def build_research_application_service(**kwargs: object) -> ResearchApplicationService:
    """Bind concrete research dependencies at the composition boundary."""

    options = cast(dict[str, Any], kwargs)
    virtual_governance_evaluator = _virtual_governance_evaluator(options)
    return ResearchApplicationService(
        orchestrator=options.pop("orchestrator", EnterpriseOrchestrator()),
        outlook_engine=options.pop("outlook_engine", MarketOutlookEngine()),
        virtual_market_runtime=options.pop(
            "virtual_market_runtime",
            VirtualMarketRuntime(),
        ),
        primitive_converter=cast(
            Any,
            options.pop("primitive_converter", to_primitive),
        ),
        audit_event_builder=cast(
            Any,
            options.pop("audit_event_builder", AuditEvent),
        ),
        market_context_request_builder=cast(
            Any,
            options.pop(
                "market_context_request_builder",
                MarketContextRequest,
            ),
        ),
        run_context_builder=cast(
            Any,
            options.pop("run_context_builder", RunContext),
        ),
        virtual_governance_evaluator=cast(Any, virtual_governance_evaluator),
        **options,
    )


def _virtual_governance_evaluator(options: dict[str, Any]) -> object:
    evaluator = options.pop("virtual_governance_evaluator", None)
    legacy_engine = options.pop("virtual_dge_engine", None)
    legacy_context_builder = options.pop("virtual_dge_context_builder", None)
    if evaluator is not None and (
        legacy_engine is not None or legacy_context_builder is not None
    ):
        raise ValueError(
            "virtual governance evaluator cannot be combined with legacy DGE inputs"
        )
    if evaluator is not None:
        return evaluator
    if legacy_engine is None:
        return VirtualMarketDgeAdapter(
            context_builder=cast(Any, legacy_context_builder)
        )
    return VirtualMarketDgeAdapter(
        dge=cast(Any, legacy_engine),
        context_builder=cast(Any, legacy_context_builder),
    )


class HistoricalReplayRunStatus(StrEnum):
    """Completion state for one bounded in-memory historical replay."""

    COMPLETED = "COMPLETED"
    RUNNING_WITH_BLOCKERS = "RUNNING_WITH_BLOCKERS"


@dataclass(frozen=True, slots=True)
class HistoricalMarketEquityCurve:
    """UTC daily equity projection for one independent replay wallet."""

    market: VirtualMarket
    points: tuple[DailyEquityPoint, ...]

    def __post_init__(self) -> None:
        market = (
            self.market
            if isinstance(self.market, VirtualMarket)
            else VirtualMarket(str(self.market).strip().upper())
        )
        object.__setattr__(self, "market", market)
        if not self.points:
            raise ValueError("historical replay equity curve requires observations")
        timestamps = tuple(point.timestamp for point in self.points)
        if timestamps != tuple(sorted(timestamps)) or len(set(timestamps)) != len(
            timestamps
        ):
            raise ValueError(
                "historical replay equity observations must be unique and ordered"
            )
        if any(
            timestamp.utcoffset() != timedelta(0)
            or timestamp.hour
            or timestamp.minute
            or timestamp.second
            or timestamp.microsecond
            for timestamp in timestamps
        ):
            raise ValueError(
                "historical replay equity observations must use UTC day boundaries"
            )

    def to_payload(self) -> dict[str, object]:
        """Return deterministic market-specific equity evidence."""

        return {
            "market": self.market.value,
            "points": [to_primitive(point) for point in self.points],
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplaySnapshot:
    """One provenance-bound market snapshot exposed to the canonical pipeline."""

    snapshot: MarketSnapshot
    dataset_bindings: tuple[HistoricalReplayDatasetBinding, ...]
    execution_context: HistoricalReplayExecutionContext | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    historical_derivatives: RuntimeFuturesReplayDataset | None = None

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "historical replay snapshot cannot authorize live execution"
            )
        _require_replay_utc(
            "historical replay snapshot created_at", self.snapshot.created_at
        )
        if self.snapshot.server_time is not None:
            _require_replay_utc(
                "historical replay snapshot server_time",
                self.snapshot.server_time,
            )
            if self.snapshot.server_time > self.snapshot.created_at:
                raise ValueError("historical replay server_time cannot lead created_at")
        if self.snapshot.exchange.strip().upper() != "BINANCE":
            raise ValueError("historical replay snapshot exchange must be Binance")
        if (
            self.snapshot.wallet_summary
            or self.snapshot.inventory_summary
            or self.snapshot.open_orders
        ):
            raise ValueError(
                "historical replay snapshot cannot contain real wallet state"
            )
        if (
            self.snapshot.order_book_summary
            or self.snapshot.news_snapshot
            or self.snapshot.sentiment_snapshot
            or self.snapshot.derivatives_snapshot
            or self.snapshot.onchain_snapshot
        ):
            raise ValueError(
                "historical replay snapshot requires separately governed historical "
                "context evidence"
            )
        if "historical_virtual_execution" in self.snapshot.market_metadata:
            raise ValueError(
                "historical replay execution context must use the typed contract"
            )
        ordered = tuple(sorted(self.dataset_bindings, key=lambda item: item.identity))
        if not ordered:
            raise ValueError("historical replay snapshot requires dataset bindings")
        identities = tuple(item.identity for item in ordered)
        if len(set(identities)) != len(identities):
            raise ValueError(
                "historical replay snapshot dataset bindings must be unique"
            )
        expected_market = self.snapshot.market_type
        expected_symbol = self.snapshot.symbol
        if self.historical_derivatives is not None:
            history = self.historical_derivatives
            if (
                expected_market != history.market
                or expected_symbol != history.symbol
                or history.timeframe not in self.snapshot.timeframes
            ):
                raise ValueError(
                    "historical derivatives identity must match the snapshot"
                )
            if not any(
                b.timeframe == history.timeframe
                and b.dataset_sha256 == history.dataset_sha256
                for b in ordered
            ):
                raise ValueError(
                    "historical derivatives require an exact dataset binding"
                )
            history_candles = {c.timestamp: c for c in history.candles}
            if any(
                history_candles.get(c.timestamp) != c
                for c in self.snapshot.ohlcv_by_timeframe[history.timeframe]
            ):
                raise ValueError(
                    "historical derivatives must bind the exact OHLCV prefix"
                )
        if any(
            binding.market.value != expected_market or binding.symbol != expected_symbol
            for binding in ordered
        ):
            raise ValueError(
                "historical replay snapshot dataset identity must match the snapshot"
            )
        binding_timeframes = tuple(binding.timeframe for binding in ordered)
        if set(binding_timeframes) != set(self.snapshot.timeframes):
            raise ValueError(
                "historical replay snapshot datasets must cover snapshot timeframes"
            )
        execution_context = self.execution_context
        if execution_context is not None:
            if execution_context.observed_at != self.snapshot.created_at:
                raise ValueError(
                    "historical replay execution context must match the event time"
                )
            if (
                execution_context.market.value != expected_market
                or execution_context.symbol != expected_symbol
            ):
                raise ValueError(
                    "historical replay execution context identity must match the "
                    "snapshot"
                )
            matching_binding = next(
                (
                    binding
                    for binding in ordered
                    if binding.identity == execution_context.binding_identity
                ),
                None,
            )
            if matching_binding is None:
                raise ValueError(
                    "historical replay execution context must reference a bound "
                    "timeframe"
                )
            if (
                execution_context.dataset_revision_id
                != matching_binding.dataset_revision_id
                or execution_context.dataset_sha256 != matching_binding.dataset_sha256
                or execution_context.source_manifest_sha256
                != matching_binding.source_manifest_sha256
                or execution_context.source_provenance_ref
                != matching_binding.source_provenance_ref
            ):
                raise ValueError(
                    "historical replay execution context must match its exact "
                    "dataset binding"
                )
        object.__setattr__(self, "dataset_bindings", ordered)

    @property
    def market(self) -> str:
        """Return the canonical market identity."""

        return self.snapshot.market_type

    @property
    def symbol(self) -> str:
        """Return the canonical symbol identity."""

        return self.snapshot.symbol

    @property
    def created_at(self) -> datetime:
        """Return the event timestamp used by the simulated clock."""

        return self.snapshot.created_at

    @property
    def audit_snapshot_sha256(self) -> str:
        """Hash the complete immutable snapshot, including its audit identity."""

        return _canonical_sha256(
            lambda value: value,
            {
                "snapshot": to_primitive(self.snapshot),
                "historical_derivatives_sha256": (
                    self.historical_derivatives.dataset_sha256
                    if self.historical_derivatives is not None
                    else None
                ),
                "execution_context": (
                    self.execution_context.to_payload()
                    if self.execution_context is not None
                    else None
                ),
            },
        )

    @property
    def semantic_snapshot_sha256(self) -> str:
        """Hash economic snapshot content without generated snapshot identity."""

        payload = cast(dict[str, object], to_primitive(self.snapshot))
        return _canonical_sha256(
            lambda value: value,
            {
                "snapshot": {
                    key: value for key, value in payload.items() if key != "snapshot_id"
                },
                "historical_derivatives_sha256": (
                    self.historical_derivatives.dataset_sha256
                    if self.historical_derivatives is not None
                    else None
                ),
                "execution_context": (
                    self.execution_context.to_payload()
                    if self.execution_context is not None
                    else None
                ),
            },
        )

    @property
    def pipeline_snapshot(self) -> MarketSnapshot:
        """Return the canonical snapshot with only typed replay context attached."""

        if self.execution_context is None and self.historical_derivatives is None:
            return self.snapshot
        metadata = dict(self.snapshot.market_metadata)
        if self.execution_context is not None:
            metadata["historical_virtual_execution"] = (
                self.execution_context.to_payload()
            )
        derivatives: dict[str, object] = {}
        if self.historical_derivatives is not None:
            history = self.historical_derivatives
            points = []
            for metric, name in (
                (DerivativesMetric.OPEN_INTEREST, "open_interest"),
                (DerivativesMetric.MARK_PRICE, "mark_price"),
                (DerivativesMetric.INDEX_PRICE, "index_price"),
                (DerivativesMetric.FUNDING_RATE, "funding_rate"),
            ):
                visible = tuple(
                    p
                    for p in history.derivatives.series.get(metric, ())
                    if p.timestamp
                    + (
                        timedelta(0)
                        if metric is DerivativesMetric.FUNDING_RATE
                        else timeframe_duration(history.timeframe)
                    )
                    <= self.created_at
                )
                if visible:
                    point = max(visible, key=lambda p: p.timestamp)
                    derivatives[name] = str(point.value)
                    points.append(point)
            if points:
                derivatives.update(
                    symbol=self.symbol,
                    market=self.market,
                    as_of=min(p.timestamp for p in points).isoformat(),
                    source_count=len({p.provenance.source_id for p in points}),
                    dataset_sha256=history.dataset_sha256,
                    source="VERIFIED_HISTORICAL_DERIVATIVES",
                )
        return replace(
            self.snapshot,
            market_metadata=metadata,
            derivatives_snapshot=derivatives,
        )

    def to_payload(self) -> dict[str, object]:
        """Return the deterministic audit payload for this replay event."""

        return {
            "snapshot_id": self.snapshot.snapshot_id,
            "snapshot_sha256": self.audit_snapshot_sha256,
            "historical_derivatives_sha256": (
                self.historical_derivatives.dataset_sha256
                if self.historical_derivatives is not None
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "market": self.market,
            "symbol": self.symbol,
            "timeframes": list(self.snapshot.timeframes),
            "dataset_bindings": [
                binding.to_payload() for binding in self.dataset_bindings
            ],
            "execution_context": (
                self.execution_context.to_payload()
                if self.execution_context is not None
                else None
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    def to_semantic_payload(self) -> dict[str, object]:
        """Return replay semantics without generated audit identities."""

        return {
            "snapshot_sha256": self.semantic_snapshot_sha256,
            "historical_derivatives_sha256": (
                self.historical_derivatives.dataset_sha256
                if self.historical_derivatives is not None
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "market": self.market,
            "symbol": self.symbol,
            "timeframes": list(self.snapshot.timeframes),
            "dataset_bindings": [
                binding.to_payload() for binding in self.dataset_bindings
            ],
            "execution_context": (
                self.execution_context.to_payload()
                if self.execution_context is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayCycleResult:
    """One canonical research-pipeline result within historical replay."""

    sequence: int
    replay_snapshot: HistoricalReplaySnapshot
    workflow: ResearchWorkflowResult
    portfolio_before: VirtualPortfolioState
    portfolio_after: VirtualPortfolioState
    position_update: VirtualPositionUpdateDecision | None = None
    managed_position_after: VirtualManagedPosition | None = None
    closed_trade: VirtualClosedTradeRecord | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("historical replay sequence cannot be negative")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical replay cycle cannot authorize live execution")
        if self.workflow.execution_allowed:
            raise ValueError("historical replay workflow cannot authorize execution")
        if self.workflow.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("historical replay workflow must remain live blocked")
        for portfolio in (self.portfolio_before, self.portfolio_after):
            if portfolio.market != self.replay_snapshot.market:
                raise ValueError(
                    "historical replay cycle portfolio market must match snapshot"
                )
        if self.portfolio_before.portfolio_id != self.portfolio_after.portfolio_id:
            raise ValueError(
                "historical replay cycle cannot replace portfolio identity"
            )
        if (
            self.portfolio_before.initial_equity_usdt
            != self.portfolio_after.initial_equity_usdt
        ):
            raise ValueError("historical replay cycle cannot replace initial capital")
        lifecycle_portfolio = self.portfolio_before
        if self.position_update is not None:
            if (
                self.position_update.position_before.market
                != self.replay_snapshot.market
            ):
                raise ValueError(
                    "historical replay position update market must match snapshot"
                )
            lifecycle_portfolio = self.position_update.portfolio_after
            if self.closed_trade is not self.position_update.closed_trade:
                raise ValueError(
                    "historical replay closed trade must match position update"
                )
        elif self.closed_trade is not None:
            raise ValueError(
                "historical replay closed trade requires a position update"
            )
        if self.managed_position_after is not None:
            if (
                self.managed_position_after.market != self.replay_snapshot.market
                or self.managed_position_after.status
                is VirtualPositionLifecycleStatus.CLOSED
            ):
                raise ValueError(
                    "historical replay managed position must be active and "
                    "market-consistent"
                )
        runtime_request = self.workflow.virtual_runtime_request
        if (
            runtime_request is not None
            and runtime_request.portfolio != lifecycle_portfolio
        ):
            raise ValueError(
                "historical replay runtime request must consume lifecycle portfolio"
            )
        decision = self.workflow.virtual_runtime_decision
        if decision is None:
            if self.portfolio_after != lifecycle_portfolio:
                raise ValueError(
                    "historical replay cycle without a runtime decision cannot mutate "
                    "post-lifecycle portfolio state"
                )
        elif (
            decision.portfolio_before != lifecycle_portfolio
            or decision.portfolio_after != self.portfolio_after
        ):
            raise ValueError(
                "historical replay cycle portfolio state must match canonical runtime"
            )

    @property
    def blockers(self) -> tuple[str, ...]:
        """Return stable de-duplicated blockers surfaced by the canonical workflow."""

        return tuple(
            dict.fromkeys(
                blocker for stage in self.workflow.stages for blocker in stage.blockers
            )
        )

    def to_payload(self) -> dict[str, object]:
        """Return the audit-complete cycle payload."""

        return {
            "sequence": self.sequence,
            "replay_snapshot": self.replay_snapshot.to_payload(),
            "workflow": _historical_workflow_payload(self.workflow),
            "portfolio_before": to_primitive(self.portfolio_before),
            "portfolio_after": to_primitive(self.portfolio_after),
            "position_update": to_primitive(self.position_update),
            "managed_position_after": to_primitive(self.managed_position_after),
            "closed_trade": to_primitive(self.closed_trade),
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    def to_semantic_payload(self) -> dict[str, object]:
        """Return economic cycle semantics without generated identities."""

        return {
            "sequence": self.sequence,
            "replay_snapshot": self.replay_snapshot.to_semantic_payload(),
            "workflow": _strip_generated_replay_identity(
                _historical_workflow_payload(self.workflow)
            ),
            "portfolio_before": _portfolio_semantic_payload(self.portfolio_before),
            "portfolio_after": _portfolio_semantic_payload(self.portfolio_after),
            "position_update": _strip_generated_replay_identity(
                to_primitive(self.position_update)
            ),
            "managed_position_after": _strip_generated_replay_identity(
                to_primitive(self.managed_position_after)
            ),
            "closed_trade": _strip_generated_replay_identity(
                to_primitive(self.closed_trade)
            ),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayRunResult:
    """Deterministic in-memory replay result using the real research pipeline."""

    request: HistoricalMarketReplayRequest
    cycles: tuple[HistoricalReplayCycleResult, ...]
    final_portfolios: tuple[VirtualPortfolioState, ...]
    open_positions: tuple[VirtualManagedPosition, ...] = ()
    closed_trades: tuple[VirtualClosedTradeRecord, ...] = ()
    equity_curves: tuple[HistoricalMarketEquityCurve, ...] = ()
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.cycles:
            raise ValueError("historical replay result requires completed cycles")
        if tuple(cycle.sequence for cycle in self.cycles) != tuple(
            range(len(self.cycles))
        ):
            raise ValueError("historical replay cycles must be contiguous and ordered")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical replay result cannot authorize live execution")
        markets = tuple(portfolio.market for portfolio in self.final_portfolios)
        epochs_by_market = {
            epoch.market.value: epoch for epoch in self.request.wallet_epochs
        }
        expected = tuple(epochs_by_market)
        if len(set(markets)) != len(markets) or set(markets) != set(expected):
            raise ValueError(
                "historical replay result requires one final portfolio per market"
            )
        for portfolio in self.final_portfolios:
            epoch = epochs_by_market[portfolio.market]
            if portfolio.portfolio_id != epoch.portfolio_id:
                raise ValueError(
                    "historical replay final portfolio must match wallet epoch identity"
                )
            if portfolio.initial_equity_usdt != epoch.initial_capital_usdt:
                raise ValueError(
                    "historical replay final portfolio must preserve epoch capital"
                )
        latest_by_market = {
            epoch.market.value: _portfolio_from_replay_epoch(epoch)
            for epoch in self.request.wallet_epochs
        }
        for cycle in self.cycles:
            latest_by_market[cycle.replay_snapshot.market] = cycle.portfolio_after
        if any(
            portfolio != latest_by_market[portfolio.market]
            for portfolio in self.final_portfolios
        ):
            raise ValueError(
                "historical replay final portfolios must match the last cycle state"
            )
        open_position_markets = tuple(
            position.market for position in self.open_positions
        )
        if len(set(open_position_markets)) != len(open_position_markets):
            raise ValueError(
                "historical replay supports at most one open position per market"
            )
        final_by_market = {
            portfolio.market: portfolio for portfolio in self.final_portfolios
        }
        for position in self.open_positions:
            final_portfolio = final_by_market.get(position.market)
            if (
                position.status is VirtualPositionLifecycleStatus.CLOSED
                or final_portfolio is None
                or final_portfolio.open_position_count != 1
            ):
                raise ValueError(
                    "historical replay open position must match final portfolio state"
                )
        closed_trade_ids = tuple(trade.trade_id for trade in self.closed_trades)
        if len(set(closed_trade_ids)) != len(closed_trade_ids):
            raise ValueError("historical replay closed trade ids must be unique")
        equity_curves = self.equity_curves or _historical_equity_curves(
            self.request,
            self.cycles,
        )
        curve_markets = tuple(curve.market.value for curve in equity_curves)
        if len(set(curve_markets)) != len(curve_markets) or set(curve_markets) != set(
            expected
        ):
            raise ValueError(
                "historical replay requires one independent equity curve per market"
            )
        object.__setattr__(
            self,
            "equity_curves",
            tuple(sorted(equity_curves, key=lambda item: item.market.value)),
        )
        object.__setattr__(
            self,
            "final_portfolios",
            tuple(sorted(self.final_portfolios, key=lambda item: item.market)),
        )
        object.__setattr__(
            self,
            "open_positions",
            tuple(sorted(self.open_positions, key=lambda item: item.market)),
        )

    @property
    def blockers(self) -> tuple[str, ...]:
        """Return stable blockers across all replay cycles."""

        return tuple(
            dict.fromkeys(
                blocker for cycle in self.cycles for blocker in cycle.blockers
            )
        )

    @property
    def status(self) -> HistoricalReplayRunStatus:
        """Return completion status without masking canonical blockers."""

        if self.blockers:
            return HistoricalReplayRunStatus.RUNNING_WITH_BLOCKERS
        return HistoricalReplayRunStatus.COMPLETED

    @property
    def semantic_result_sha256(self) -> str:
        """Hash economic replay results independently from generated identities."""

        return _canonical_sha256(
            lambda value: value,
            {
                "request_seed_sha256": self.request.semantic_result_seed_sha256,
                "cycles": [cycle.to_semantic_payload() for cycle in self.cycles],
                "final_portfolios": [
                    _portfolio_semantic_payload(portfolio)
                    for portfolio in self.final_portfolios
                ],
                "open_positions": [
                    _strip_generated_replay_identity(to_primitive(position))
                    for position in self.open_positions
                ],
                "closed_trades": [
                    _strip_generated_replay_identity(to_primitive(trade))
                    for trade in self.closed_trades
                ],
                "equity_curves": [curve.to_payload() for curve in self.equity_curves],
                "blockers": list(self.blockers),
            },
        )

    @property
    def audit_result_sha256(self) -> str:
        """Hash the complete replay result including audit identities."""

        return _canonical_sha256(lambda value: value, self.to_payload())

    def to_payload(self) -> dict[str, object]:
        """Return the deterministic audit-safe replay result."""

        return {
            "request": self.request.to_payload(),
            "status": self.status.value,
            "cycles": [cycle.to_payload() for cycle in self.cycles],
            "final_portfolios": [
                to_primitive(portfolio) for portfolio in self.final_portfolios
            ],
            "open_positions": [
                to_primitive(position) for position in self.open_positions
            ],
            "closed_trades": [to_primitive(trade) for trade in self.closed_trades],
            "equity_curves": [curve.to_payload() for curve in self.equity_curves],
            "semantic_result_sha256": self.semantic_result_sha256,
            "blockers": list(self.blockers),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class HistoricalMarketReplayRunner:
    """Replay validated snapshots through the canonical research application."""

    application: ResearchApplicationService

    def __post_init__(self) -> None:
        incompatible_inputs = tuple(
            name
            for name, enabled in (
                ("wallet_service", self.application.wallet_service is not None),
                ("wallet_capture", self.application.wallet_capture_enabled),
                (
                    "market_context_registry",
                    self.application.market_context_registry is not None,
                ),
                (
                    "market_context_providers",
                    bool(self.application.market_context_provider_ids),
                ),
                ("learning_loop", self.application.learning_loop is not None),
                (
                    "learning_evidence_provider",
                    self.application.learning_evidence_provider is not None,
                ),
            )
            if enabled
        )
        if incompatible_inputs:
            raise ValueError(
                "historical replay application contains unbounded external state: "
                + ",".join(incompatible_inputs)
            )

    def run(
        self,
        request: HistoricalMarketReplayRequest,
        replay_snapshots: Sequence[HistoricalReplaySnapshot],
    ) -> HistoricalReplayRunResult:
        """Run a deterministic in-memory replay without creating another engine."""

        ordered = self._validated_snapshots(request, replay_snapshots)
        runtime = self.application.virtual_market_runtime
        if runtime is None:
            raise ValueError("historical replay requires the canonical virtual runtime")
        canonical_runtime = cast(VirtualMarketRuntime, runtime)
        clock = SimulatedClock(request.start_at)
        portfolios = {
            epoch.market.value: _portfolio_from_replay_epoch(epoch)
            for epoch in request.wallet_epochs
        }
        open_positions: dict[str, VirtualManagedPosition] = {}
        closed_trades: list[VirtualClosedTradeRecord] = []
        cycles: list[HistoricalReplayCycleResult] = []
        for sequence, replay_snapshot in enumerate(ordered):
            clock.set(replay_snapshot.created_at)
            portfolio_before = portfolios[replay_snapshot.market]
            position_update: VirtualPositionUpdateDecision | None = None
            managed_position = open_positions.get(replay_snapshot.market)
            lifecycle_portfolio = portfolio_before
            if (
                managed_position is not None
                and managed_position.symbol == replay_snapshot.symbol
            ):
                candle = self._position_candle(replay_snapshot, managed_position)
                position_update = canonical_runtime.process_position(
                    position=managed_position,
                    portfolio=portfolio_before,
                    candle=candle,
                    futures_context=self._futures_position_context(replay_snapshot),
                    candle_available_at=replay_snapshot.created_at,
                )
                lifecycle_portfolio = position_update.portfolio_after
                if (
                    position_update.position_after.status
                    is VirtualPositionLifecycleStatus.CLOSED
                ):
                    open_positions.pop(replay_snapshot.market, None)
                    managed_position = None
                    if position_update.closed_trade is not None:
                        closed_trades.append(position_update.closed_trade)
                else:
                    managed_position = position_update.position_after
                    open_positions[replay_snapshot.market] = managed_position
            cycle_application = replace(
                self.application,
                virtual_portfolio_builder=self._portfolio_builder(
                    replay_snapshot,
                    lifecycle_portfolio,
                ),
            )
            workflow = cycle_application.run(replay_snapshot.pipeline_snapshot)
            decision = workflow.virtual_runtime_decision
            portfolio_after = lifecycle_portfolio
            if decision is not None:
                if decision.portfolio_before != lifecycle_portfolio:
                    raise ValueError(
                        "historical replay canonical runtime changed portfolio input"
                    )
                candidate_after = decision.portfolio_after
                if not isinstance(candidate_after, VirtualPortfolioState):
                    raise ValueError(
                        "historical replay canonical runtime returned invalid portfolio"
                    )
                portfolio_after = candidate_after
                if decision.trade_intent is not None:
                    if managed_position is not None:
                        raise ValueError(
                            "historical replay cannot replace an active managed "
                            "position"
                        )
                    runtime_request = workflow.virtual_runtime_request
                    if runtime_request is None:
                        raise ValueError(
                            "historical replay order-ready decision requires its "
                            "canonical runtime request"
                        )
                    managed_position = canonical_runtime.materialize_managed_position(
                        request=runtime_request,
                        decision=decision,
                        opened_at=replay_snapshot.created_at,
                        position_id=(
                            f"virtual-position:{request.run_id}:"
                            f"{sequence}:{replay_snapshot.market}:"
                            f"{replay_snapshot.symbol}"
                        ),
                    )
                    open_positions[replay_snapshot.market] = managed_position
            cycle = HistoricalReplayCycleResult(
                sequence=sequence,
                replay_snapshot=replay_snapshot,
                workflow=workflow,
                portfolio_before=portfolio_before,
                portfolio_after=portfolio_after,
                position_update=position_update,
                managed_position_after=managed_position,
                closed_trade=(
                    position_update.closed_trade
                    if position_update is not None
                    else None
                ),
            )
            portfolios[replay_snapshot.market] = portfolio_after
            cycles.append(cycle)
        return HistoricalReplayRunResult(
            request=request,
            cycles=tuple(cycles),
            final_portfolios=tuple(portfolios.values()),
            open_positions=tuple(open_positions.values()),
            closed_trades=tuple(closed_trades),
        )

    @staticmethod
    def _position_candle(
        replay_snapshot: HistoricalReplaySnapshot,
        position: VirtualManagedPosition,
    ) -> OHLCVCandle:
        candles = replay_snapshot.snapshot.ohlcv_by_timeframe.get(
            position.timeframe,
            (),
        )
        if not candles:
            raise ValueError(
                "historical replay position timeframe requires candle evidence"
            )
        candle = candles[-1]
        if (
            candle.timestamp + timeframe_duration(position.timeframe)
            != replay_snapshot.created_at
        ):
            raise ValueError(
                "historical replay position candle must close at the event time"
            )
        return candle

    @staticmethod
    def _futures_position_context(
        replay_snapshot: HistoricalReplaySnapshot,
    ) -> VirtualFuturesPositionContext | None:
        if replay_snapshot.market != "USD_M_FUTURES":
            return None
        context = replay_snapshot.execution_context
        if (
            context is None
            or context.mark_price is None
            or context.funding_rate is None
        ):
            raise ValueError(
                "historical Futures lifecycle requires typed execution context"
            )
        return VirtualFuturesPositionContext(
            observed_at=context.observed_at,
            mark_price=context.mark_price,
            funding_rate=context.funding_rate,
            funding_payment_due=context.funding_payment_due,
        )

    @staticmethod
    def _portfolio_builder(
        replay_snapshot: HistoricalReplaySnapshot,
        portfolio: VirtualPortfolioState,
    ) -> Callable[[object, object], VirtualPortfolioState]:
        def build(snapshot: object, candidate: object) -> VirtualPortfolioState:
            snapshot_market = str(getattr(snapshot, "market_type", "")).upper()
            candidate_market = str(getattr(candidate, "market_type", "")).upper()
            if (
                snapshot_market != replay_snapshot.market
                or candidate_market != replay_snapshot.market
                or portfolio.market != replay_snapshot.market
            ):
                raise ValueError(
                    "historical replay candidate, snapshot and portfolio markets "
                    "must match"
                )
            return portfolio

        return build

    @staticmethod
    def _validated_snapshots(
        request: HistoricalMarketReplayRequest,
        replay_snapshots: Sequence[HistoricalReplaySnapshot],
    ) -> tuple[HistoricalReplaySnapshot, ...]:
        snapshots = tuple(replay_snapshots)
        if not snapshots:
            raise ValueError("historical replay requires at least one snapshot")
        if any(not isinstance(item, HistoricalReplaySnapshot) for item in snapshots):
            raise TypeError(
                "historical replay snapshots must use the canonical contract"
            )
        snapshot_ids = tuple(item.snapshot.snapshot_id for item in snapshots)
        if len(set(snapshot_ids)) != len(snapshot_ids):
            raise ValueError("historical replay snapshot ids must be unique")
        event_keys = tuple(
            (item.created_at, item.market, item.symbol) for item in snapshots
        )
        if len(set(event_keys)) != len(event_keys):
            raise ValueError("historical replay event identities must be unique")
        ordered = tuple(
            sorted(
                snapshots,
                key=lambda item: (
                    item.created_at,
                    item.market,
                    item.symbol,
                    item.snapshot.snapshot_id,
                ),
            )
        )
        expected_pairs = {
            (selection.market.value, symbol)
            for selection in request.market_selections
            for symbol in selection.symbols
        }
        observed_pairs = {(item.market, item.symbol) for item in ordered}
        if observed_pairs != expected_pairs:
            raise ValueError(
                "historical replay snapshots must cover every selected market symbol"
            )
        request_bindings = set(request.dataset_bindings)
        for item in ordered:
            HistoricalMarketReplayRunner._validate_snapshot(
                request,
                item,
                request_bindings=request_bindings,
            )
        return ordered

    @staticmethod
    def _validate_snapshot(
        request: HistoricalMarketReplayRequest,
        replay_snapshot: HistoricalReplaySnapshot,
        *,
        request_bindings: set[HistoricalReplayDatasetBinding],
    ) -> None:
        if replay_snapshot.created_at < request.start_at:
            raise ValueError("historical replay snapshot precedes request start")
        if request.end_at is not None and replay_snapshot.created_at > request.end_at:
            raise ValueError("historical replay snapshot exceeds request end")
        if tuple(replay_snapshot.snapshot.timeframes) != request.timeframes:
            raise ValueError(
                "historical replay snapshot timeframes must match request ordering"
            )
        if set(replay_snapshot.snapshot.ohlcv_by_timeframe) != set(request.timeframes):
            raise ValueError(
                "historical replay snapshot candles must exactly cover request "
                "timeframes"
            )
        if any(
            binding not in request_bindings
            for binding in replay_snapshot.dataset_bindings
        ):
            raise ValueError(
                "historical replay snapshot references an unbound dataset revision"
            )
        execution_context = replay_snapshot.execution_context
        if (
            execution_context is not None
            and execution_context.execution_model_sha256
            != request.system_version.execution_model_sha256
        ):
            raise ValueError(
                "historical replay execution context must match the request "
                "execution model"
            )
        bindings_by_timeframe = {
            binding.timeframe: binding for binding in replay_snapshot.dataset_bindings
        }
        for timeframe in request.timeframes:
            binding = bindings_by_timeframe[timeframe]
            candles = tuple(replay_snapshot.snapshot.ohlcv_by_timeframe[timeframe])
            if not candles:
                raise ValueError(
                    "historical replay snapshot candle prefix cannot be empty"
                )
            previous: datetime | None = None
            for candle in candles:
                _require_replay_utc(
                    "historical replay candle timestamp", candle.timestamp
                )
                if previous is not None and candle.timestamp <= previous:
                    raise ValueError(
                        "historical replay candles must be strictly chronological"
                    )
                if (
                    previous is not None
                    and candle.timestamp - previous != timeframe_duration(timeframe)
                ):
                    raise ValueError(
                        "historical replay candle prefix contains a cadence gap"
                    )
                if (
                    candle.timestamp + timeframe_duration(timeframe)
                    > replay_snapshot.created_at
                ):
                    raise ValueError(
                        "historical replay snapshot contains an unclosed candle "
                        "or look-ahead data"
                    )
                if (
                    not binding.coverage_start
                    <= candle.timestamp
                    <= binding.coverage_end
                ):
                    raise ValueError(
                        "historical replay candle falls outside dataset coverage"
                    )
                previous = candle.timestamp


def _require_replay_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use canonical UTC")


def _historical_workflow_payload(
    workflow: ResearchWorkflowResult,
) -> dict[str, object]:
    final_decision = getattr(workflow.analysis, "final_decision", None)
    final_action = getattr(getattr(final_decision, "action", None), "value", "NO_TRADE")
    return {
        "stages": [
            {
                "name": stage.name,
                "status": stage.status.value,
                "blockers": list(stage.blockers),
            }
            for stage in workflow.stages
        ],
        "final_action": str(final_action),
        "virtual_runtime_decision": (
            to_primitive(workflow.virtual_runtime_decision)
            if workflow.virtual_runtime_decision is not None
            else None
        ),
    }


def _portfolio_semantic_payload(
    portfolio: VirtualPortfolioState,
) -> dict[str, object]:
    payload = cast(dict[str, object], to_primitive(portfolio))
    return {key: value for key, value in payload.items() if key != "portfolio_id"}


def _portfolio_from_replay_epoch(epoch: VirtualWalletEpoch) -> VirtualPortfolioState:
    return VirtualPortfolioState(
        portfolio_id=epoch.portfolio_id,
        market=epoch.market.value,
        cash_usdt=epoch.initial_capital_usdt,
        equity_usdt=epoch.initial_capital_usdt,
        initial_equity_usdt=epoch.initial_capital_usdt,
    )


def _historical_equity_curves(
    request: HistoricalMarketReplayRequest,
    cycles: tuple[HistoricalReplayCycleResult, ...],
) -> tuple[HistoricalMarketEquityCurve, ...]:
    by_market: dict[str, dict[datetime, Decimal]] = {
        epoch.market.value: {
            _utc_day(request.start_at): epoch.initial_capital_usdt,
        }
        for epoch in request.wallet_epochs
    }
    for cycle in cycles:
        by_market[cycle.replay_snapshot.market][
            _utc_day(cycle.replay_snapshot.created_at) + timedelta(days=1)
        ] = cycle.portfolio_after.equity_usdt
    return tuple(
        HistoricalMarketEquityCurve(
            market=VirtualMarket(market),
            points=tuple(
                DailyEquityPoint(timestamp, equity)
                for timestamp, equity in sorted(points.items())
            ),
        )
        for market, points in sorted(by_market.items())
    )


def _utc_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _strip_generated_replay_identity(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_generated_replay_identity(child)
            for key, child in value.items()
            if str(key)
            not in {
                "audit_refs",
                "candidate_id",
                "decision_id",
                "opportunity_id",
                "portfolio_id",
                "position_id",
                "snapshot_id",
                "trade_id",
            }
        }
    if isinstance(value, (list, tuple)):
        return [_strip_generated_replay_identity(item) for item in value]
    return value

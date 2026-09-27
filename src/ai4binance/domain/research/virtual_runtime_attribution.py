"""Canonical deterministic virtual-trade attribution contracts and aggregation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256

ZERO = Decimal("0")


class BacktestExitReason(StrEnum):
    """Exit reasons not owned by the paper execution primitive."""

    LIQUIDATION = "LIQUIDATION"
    HARD_STOP = "HARD_STOP"
    TARGET = "TARGET"
    TRAILING_STOP = "TRAILING_STOP"
    STRUCTURE_INVALIDATION = "STRUCTURE_INVALIDATION"
    TIME_EXIT = "TIME_EXIT"
    REGIME_EXIT = "REGIME_EXIT"
    MOMENTUM_FAILURE = "MOMENTUM_FAILURE"
    END_OF_DATA = "END_OF_DATA"


class TradeDirection(StrEnum):
    """Deterministic virtual-trade direction labels."""

    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True, slots=True)
class TradeParameterMethods:
    """Sources of parameter decisions, separate from values and execution authority."""

    quantity: str = "NOT_RECORDED"
    leverage: str = "NOT_RECORDED"
    stop_loss: str = "NOT_RECORDED"
    entry: str = "NOT_RECORDED"
    take_profit: str = "NOT_RECORDED"
    risk_reward: str = "NOT_RECORDED"
    pnl: str = "NOT_RECORDED"

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.quantity,
                self.leverage,
                self.stop_loss,
                self.entry,
                self.take_profit,
                self.risk_reward,
                self.pnl,
            )
        ):
            raise ValueError("trade parameter methods must be nonblank strings")

    @classmethod
    def from_payload(cls, payload: object) -> TradeParameterMethods:
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping):
            raise ValueError("trade parameter methods must be a mapping")
        values: dict[str, str] = {}
        for key in cls.__dataclass_fields__:
            value = payload.get(key, "NOT_RECORDED")
            if not isinstance(value, str):
                raise ValueError("trade parameter methods must be strings")
            values[key] = value
        return cls(**values)


@dataclass(frozen=True, slots=True)
class TradeDecisionEvidence:
    """Immutable decision-time inputs; legacy absence is explicitly unknown.

    The digest detects accidental changes, not authenticity. Existing audit
    storage provides durable event provenance. Reconstruction never becomes a
    decision-time observation merely because it contains the same inputs.
    """

    status: str = "NOT_RECORDED"
    as_of: datetime | None = None
    direction_method: str = "NOT_RECORDED"
    entry_method: str = "NOT_RECORDED"
    factors_json: str = "{}"
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if self.status not in {
            "NOT_RECORDED",
            "RECORDED_AT_DECISION",
            "RECONSTRUCTED_FROM_ARCHIVE",
        }:
            raise ValueError("unsupported decision evidence status")
        if len(self.factors_json.encode("utf-8")) > 1_000_000:
            raise ValueError("decision evidence exceeds the payload bound")
        factors = json.loads(self.factors_json)
        if not isinstance(factors, dict):
            raise ValueError("decision factors must be a JSON object")
        registry = factors.get("method_registry")
        if registry is not None:
            if not isinstance(registry, dict) or not isinstance(
                registry.get("definition"), dict
            ):
                raise ValueError(
                    "recorded method registry requires definitions and digest"
                )
            registry_json = json.dumps(
                registry["definition"],
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            if sha256(registry_json.encode()).hexdigest() != registry.get("sha256"):
                raise ValueError("recorded method registry digest mismatch")
        canonical = json.dumps(
            factors, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        if self.status == "NOT_RECORDED":
            if (
                factors
                or self.as_of is not None
                or (self.direction_method, self.entry_method)
                != ("NOT_RECORDED", "NOT_RECORDED")
            ):
                raise ValueError("unrecorded evidence cannot claim observed factors")
        elif (
            self.as_of is None
            or self.as_of.utcoffset() is None
            or not factors
            or not self.direction_method.strip()
            or not self.entry_method.strip()
            or "NOT_RECORDED" in (self.direction_method, self.entry_method)
        ):
            raise ValueError(
                "recorded evidence requires aware time, methods and factors"
            )
        object.__setattr__(self, "factors_json", canonical)
        payload = json.dumps(
            [
                self.status,
                self.as_of.isoformat() if self.as_of else None,
                self.direction_method,
                self.entry_method,
                canonical,
            ],
            separators=(",", ":"),
        )
        object.__setattr__(self, "sha256", sha256(payload.encode()).hexdigest())

    @classmethod
    def from_payload(cls, payload: object) -> TradeDecisionEvidence:
        """Restore evidence with digest verification; accept legacy absence."""
        if payload is None:
            return cls()
        if not isinstance(payload, Mapping):
            raise ValueError("decision evidence payload must be a mapping")
        stamp = payload.get("as_of")
        evidence = cls(
            status=str(payload["status"]),
            as_of=datetime.fromisoformat(str(stamp)) if stamp is not None else None,
            direction_method=str(payload["direction_method"]),
            entry_method=str(payload["entry_method"]),
            factors_json=str(payload["factors_json"]),
        )
        if payload.get("sha256") != evidence.sha256:
            raise ValueError("decision evidence digest mismatch")
        return evidence


@dataclass(frozen=True, slots=True)
class ClosedTradeAttribution:
    """Required deterministic lineage attached to each closed virtual trade."""

    strategy_id: str = "UNSPECIFIED_STRATEGY"
    strategy_version: str = "1"
    strategy_config_version: str = "1"
    strategy_config_hash: str = "default"
    market: str = "SPOT"
    symbol: str = "UNKNOWN_SYMBOL"
    regime: str = "UNKNOWN"
    timeframe: str = "UNKNOWN"
    snapshot_id: str = "UNKNOWN_SNAPSHOT"
    decision_id: str = "UNKNOWN_DECISION"
    opportunity_id: str = "UNKNOWN_OPPORTUNITY"
    decision_evidence: TradeDecisionEvidence = field(
        default_factory=TradeDecisionEvidence
    )

    def __post_init__(self) -> None:
        for field_name, value in (
            ("strategy_id", self.strategy_id),
            ("strategy_version", self.strategy_version),
            ("strategy_config_version", self.strategy_config_version),
            ("strategy_config_hash", self.strategy_config_hash),
            ("market", self.market),
            ("symbol", self.symbol),
            ("regime", self.regime),
            ("timeframe", self.timeframe),
            ("snapshot_id", self.snapshot_id),
            ("decision_id", self.decision_id),
            ("opportunity_id", self.opportunity_id),
        ):
            if not value.strip():
                raise ValueError(f"closed trade attribution {field_name} is required")


@dataclass(frozen=True, slots=True)
class TradeClosureAssessment:
    """Observed closure diagnostics, never empirical accuracy or promotion proof.

    The referenced immutable decision evidence retains methods, rule definitions,
    conflicts and scenario alternatives. An exit event alone cannot establish
    which method was accurate or whether a different entry/target was optimal.
    """

    decision_evidence_sha256: str
    decision_lineage_status: str
    selected_scenario_id: str | None
    entry_quality: str
    stop_quality: str
    target_quality: str
    method_accuracy: str = "NOT_EVALUABLE_NO_METHOD_OUTCOME_LABELS"
    scenario_accuracy: str = "NOT_EVALUABLE_NO_SCENARIO_OUTCOME_LABELS"
    execution_quality: str = "NOT_EVALUABLE_NO_FILL_BENCHMARK"
    rule_evaluation_status: str = "NOT_EVALUABLE_NO_RULE_EXECUTION_TRACE"

    @classmethod
    def build(
        cls,
        evidence: TradeDecisionEvidence,
        *,
        entry_time: datetime,
        entry_price: Decimal,
        exit_reason: str,
    ) -> TradeClosureAssessment:
        causal = (
            evidence.status == "RECORDED_AT_DECISION"
            and evidence.as_of is not None
            and entry_time.utcoffset() is not None
            and evidence.as_of <= entry_time
        )
        factors = json.loads(evidence.factors_json) if causal else {}
        state = factors.get("state")
        scenario_id: str | None = None
        if isinstance(state, dict):
            selected_id = state.get("selected_scenario_id")
            scenarios = state.get("scenarios", [])
            if (
                isinstance(selected_id, str)
                and isinstance(scenarios, list)
                and any(
                    isinstance(row, dict) and row.get("scenario_id") == selected_id
                    for row in scenarios
                )
            ):
                scenario_id = selected_id
        return cls(
            decision_evidence_sha256=evidence.sha256,
            decision_lineage_status=(
                "CAUSAL_DECISION_EVIDENCE"
                if causal
                else "NOT_EVALUABLE_MISSING_OR_NONCAUSAL_DECISION_EVIDENCE"
            ),
            selected_scenario_id=scenario_id,
            entry_quality=cls._entry_quality(factors.get("entry_zone"), entry_price),
            stop_quality=(
                "INITIAL_STOP_EXIT_RECORDED"
                if exit_reason in {"HARD_STOP", "STOP_LOSS_EXIT"}
                else "TRAILING_STOP_EXIT_RECORDED"
                if exit_reason in {"TRAILING_STOP", "TRAILING_STOP_EXIT"}
                else "NO_STOP_EXIT_RECORDED"
            ),
            target_quality=(
                "TARGET_EXIT_RECORDED"
                if exit_reason in {"TARGET", "TAKE_PROFIT_EXIT"}
                else "NO_FINAL_TARGET_EXIT_RECORDED"
            ),
        )

    @staticmethod
    def _entry_quality(zone: object, price: Decimal) -> str:
        if not isinstance(zone, dict):
            return "NOT_EVALUABLE_NO_RECORDED_ENTRY_ZONE"
        try:
            low, high = Decimal(str(zone.get("lower"))), Decimal(str(zone.get("upper")))
        except InvalidOperation:
            return "NOT_EVALUABLE_INVALID_RECORDED_ENTRY_ZONE"
        if (
            not all(value.is_finite() for value in (low, high, price))
            or not ZERO < low <= high
        ):
            return "NOT_EVALUABLE_INVALID_RECORDED_ENTRY_ZONE"
        return (
            "FILL_WITHIN_RECORDED_ENTRY_ZONE"
            if low <= price <= high
            else "FILL_OUTSIDE_RECORDED_ENTRY_ZONE"
        )


@dataclass(frozen=True, slots=True)
class TradeEdgeAggregateView:
    """Deterministic closed-trade edge summary for one grouping key."""

    trade_count: int
    gross_pnl_usdt: Decimal
    fee_cost_usdt: Decimal
    slippage_cost_usdt: Decimal
    funding_cost_usdt: Decimal
    net_pnl_usdt: Decimal
    average_realized_r_multiple: Decimal
    average_maximum_favorable_excursion: Decimal
    average_maximum_adverse_excursion: Decimal
    average_holding_period: Decimal
    strategy_id: str | None = None
    regime: str | None = None
    symbol: str | None = None
    timeframe: str | None = None

    def __post_init__(self) -> None:
        if self.trade_count < 1:
            raise ValueError("trade edge aggregate requires at least one trade")


@dataclass(frozen=True, slots=True)
class TradeEdgeLedger:
    """Aggregate trade-edge views derived from completed virtual trades."""

    by_strategy: tuple[TradeEdgeAggregateView, ...] = ()
    by_regime: tuple[TradeEdgeAggregateView, ...] = ()
    by_strategy_regime: tuple[TradeEdgeAggregateView, ...] = ()
    by_symbol: tuple[TradeEdgeAggregateView, ...] = ()
    by_timeframe: tuple[TradeEdgeAggregateView, ...] = ()


@dataclass(frozen=True, slots=True)
class VirtualClosedTradeRecord:
    """Canonical closed virtual trade with optimization-safe lineage."""

    trade_id: str
    attribution: ClosedTradeAttribution
    direction: TradeDirection
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    risk_at_entry: Decimal
    entry_reason: tuple[str, ...]
    exit_reason: BacktestExitReason
    dge_decision: str
    risk_policy_version: str
    validation_version: str
    gross_pnl_usdt: Decimal
    fee_cost_usdt: Decimal
    slippage_cost_usdt: Decimal
    funding_cost_usdt: Decimal
    net_pnl_usdt: Decimal
    realized_r_multiple: Decimal
    maximum_favorable_excursion: Decimal
    maximum_adverse_excursion: Decimal
    false_breakout: bool = False
    leverage: int | None = None
    initial_stop_loss: Decimal | None = None
    initial_take_profit_levels: tuple[Decimal, ...] = ()
    planned_rr: Decimal | None = None
    parameter_methods: TradeParameterMethods = field(
        default_factory=TradeParameterMethods
    )
    closure_assessment: TradeClosureAssessment = field(init=False)

    def __post_init__(self) -> None:
        if not self.trade_id.strip():
            raise ValueError("virtual closed trade identity is required")
        if any(not value.strip() for value in self.entry_reason):
            raise ValueError("virtual closed trade entry reason cannot contain blanks")
        if any(
            not value.strip()
            for value in (
                self.dge_decision,
                self.risk_policy_version,
                self.validation_version,
            )
        ):
            raise ValueError("virtual closed trade governance lineage is required")
        object.__setattr__(
            self,
            "closure_assessment",
            TradeClosureAssessment.build(
                self.attribution.decision_evidence,
                entry_time=self.entry_time,
                entry_price=self.entry_price,
                exit_reason=self.exit_reason.value,
            ),
        )


@dataclass(frozen=True, slots=True)
class VirtualTradeAttributionAggregate:
    """Closed-trade attribution summary for one grouping key."""

    trade_count: int
    net_pnl_usdt: Decimal
    expectancy_usdt: Decimal
    average_realized_r_multiple: Decimal
    fee_drag_usdt: Decimal
    slippage_drag_usdt: Decimal
    funding_drag_usdt: Decimal
    average_mfe: Decimal
    average_mae: Decimal
    false_breakout_rate: Decimal
    drawdown_contribution_usdt: Decimal
    strategy_id: str | None = None
    regime: str | None = None

    def __post_init__(self) -> None:
        if self.trade_count < 1:
            raise ValueError("virtual trade attribution aggregate requires trades")


@dataclass(frozen=True, slots=True)
class VirtualTradeAttributionLedger:
    """Optimization-safe closed-trade attribution views."""

    closed_trades: tuple[VirtualClosedTradeRecord, ...] = ()
    trade_edge_ledger: TradeEdgeLedger = field(default_factory=TradeEdgeLedger)
    by_strategy: tuple[VirtualTradeAttributionAggregate, ...] = ()
    by_regime: tuple[VirtualTradeAttributionAggregate, ...] = ()
    by_strategy_regime: tuple[VirtualTradeAttributionAggregate, ...] = ()


def build_virtual_trade_attribution_ledger(
    closed_trades: tuple[VirtualClosedTradeRecord, ...],
) -> VirtualTradeAttributionLedger:
    """Aggregate closed trades with stable keys and canonical result objects."""

    return VirtualTradeAttributionLedger(
        closed_trades=closed_trades,
        trade_edge_ledger=TradeEdgeLedger(
            by_strategy=_trade_edge_views(
                closed_trades,
                key_fn=lambda trade: (trade.attribution.strategy_id,),
                view_fn=lambda trade: {"strategy_id": trade.attribution.strategy_id},
            ),
            by_regime=_trade_edge_views(
                closed_trades,
                key_fn=lambda trade: (trade.attribution.regime,),
                view_fn=lambda trade: {"regime": trade.attribution.regime},
            ),
            by_strategy_regime=_trade_edge_views(
                closed_trades,
                key_fn=lambda trade: (
                    trade.attribution.strategy_id,
                    trade.attribution.regime,
                ),
                view_fn=lambda trade: {
                    "strategy_id": trade.attribution.strategy_id,
                    "regime": trade.attribution.regime,
                },
            ),
        ),
        by_strategy=_attribution_views(
            closed_trades,
            key_fn=lambda trade: (trade.attribution.strategy_id,),
            view_fn=lambda trade: {"strategy_id": trade.attribution.strategy_id},
        ),
        by_regime=_attribution_views(
            closed_trades,
            key_fn=lambda trade: (trade.attribution.regime,),
            view_fn=lambda trade: {"regime": trade.attribution.regime},
        ),
        by_strategy_regime=_attribution_views(
            closed_trades,
            key_fn=lambda trade: (
                trade.attribution.strategy_id,
                trade.attribution.regime,
            ),
            view_fn=lambda trade: {
                "strategy_id": trade.attribution.strategy_id,
                "regime": trade.attribution.regime,
            },
        ),
    )


def _trade_edge_views(
    closed_trades: tuple[VirtualClosedTradeRecord, ...],
    *,
    key_fn: Callable[[VirtualClosedTradeRecord], tuple[str, ...]],
    view_fn: Callable[[VirtualClosedTradeRecord], dict[str, str]],
) -> tuple[TradeEdgeAggregateView, ...]:
    grouped: dict[tuple[str, ...], list[VirtualClosedTradeRecord]] = {}
    for trade in closed_trades:
        grouped.setdefault(key_fn(trade), []).append(trade)
    views: list[TradeEdgeAggregateView] = []
    for key in sorted(grouped):
        group = grouped[key]
        denominator = Decimal(len(group))
        first = group[0]
        views.append(
            TradeEdgeAggregateView(
                trade_count=len(group),
                gross_pnl_usdt=sum((trade.gross_pnl_usdt for trade in group), ZERO),
                fee_cost_usdt=sum((trade.fee_cost_usdt for trade in group), ZERO),
                slippage_cost_usdt=sum(
                    (trade.slippage_cost_usdt for trade in group), ZERO
                ),
                funding_cost_usdt=sum(
                    (trade.funding_cost_usdt for trade in group), ZERO
                ),
                net_pnl_usdt=sum((trade.net_pnl_usdt for trade in group), ZERO),
                average_realized_r_multiple=sum(
                    (trade.realized_r_multiple for trade in group), ZERO
                )
                / denominator,
                average_maximum_favorable_excursion=sum(
                    (trade.maximum_favorable_excursion for trade in group), ZERO
                )
                / denominator,
                average_maximum_adverse_excursion=sum(
                    (trade.maximum_adverse_excursion for trade in group), ZERO
                )
                / denominator,
                average_holding_period=sum(
                    (
                        Decimal(
                            int((trade.exit_time - trade.entry_time).total_seconds())
                        )
                        for trade in group
                    ),
                    ZERO,
                )
                / denominator,
                symbol=first.attribution.symbol,
                timeframe=first.attribution.timeframe,
                **view_fn(first),
            )
        )
    return tuple(views)


def _attribution_views(
    closed_trades: tuple[VirtualClosedTradeRecord, ...],
    *,
    key_fn: Callable[[VirtualClosedTradeRecord], tuple[str, ...]],
    view_fn: Callable[[VirtualClosedTradeRecord], dict[str, str]],
) -> tuple[VirtualTradeAttributionAggregate, ...]:
    grouped: dict[tuple[str, ...], list[VirtualClosedTradeRecord]] = {}
    for trade in closed_trades:
        grouped.setdefault(key_fn(trade), []).append(trade)
    views: list[VirtualTradeAttributionAggregate] = []
    for key in sorted(grouped):
        group = grouped[key]
        denominator = Decimal(len(group))
        gross_losses = abs(
            sum(
                (trade.net_pnl_usdt for trade in group if trade.net_pnl_usdt < ZERO),
                ZERO,
            )
        )
        drawdown_contribution = min(
            ZERO if gross_losses == ZERO else gross_losses,
            abs(sum((trade.net_pnl_usdt for trade in group), ZERO)),
        )
        views.append(
            VirtualTradeAttributionAggregate(
                trade_count=len(group),
                net_pnl_usdt=sum((trade.net_pnl_usdt for trade in group), ZERO),
                expectancy_usdt=sum((trade.net_pnl_usdt for trade in group), ZERO)
                / denominator,
                average_realized_r_multiple=sum(
                    (trade.realized_r_multiple for trade in group), ZERO
                )
                / denominator,
                fee_drag_usdt=sum((trade.fee_cost_usdt for trade in group), ZERO),
                slippage_drag_usdt=sum(
                    (trade.slippage_cost_usdt for trade in group), ZERO
                ),
                funding_drag_usdt=sum(
                    (trade.funding_cost_usdt for trade in group), ZERO
                ),
                average_mfe=sum(
                    (trade.maximum_favorable_excursion for trade in group), ZERO
                )
                / denominator,
                average_mae=sum(
                    (trade.maximum_adverse_excursion for trade in group), ZERO
                )
                / denominator,
                false_breakout_rate=Decimal(
                    str(sum(1 for trade in group if trade.false_breakout) / len(group))
                ),
                drawdown_contribution_usdt=drawdown_contribution,
                **view_fn(group[0]),
            )
        )
    return tuple(views)


__all__ = (
    "BacktestExitReason",
    "ClosedTradeAttribution",
    "TradeDirection",
    "TradeEdgeAggregateView",
    "TradeEdgeLedger",
    "VirtualClosedTradeRecord",
    "VirtualTradeAttributionAggregate",
    "VirtualTradeAttributionLedger",
    "build_virtual_trade_attribution_ledger",
)

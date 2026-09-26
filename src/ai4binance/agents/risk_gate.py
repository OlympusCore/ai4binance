"""Deterministic risk control gate with no execution authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from ai4binance.agents.registry import AgentDefinition, AgentStage
from ai4binance.core.errors import ExchangePayloadError
from ai4binance.domain import TradeCandidate
from ai4binance.exchange.filters import SymbolFilters
from ai4binance.exchange.models import FilterValue, SymbolInfo
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.risk import RiskContext, RiskEngine
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    DataQuality,
    MarketSnapshot,
    OOSValidationStatus,
)


@dataclass(frozen=True, slots=True)
class RiskGate:
    """Evaluate bounded candidate risk without decision or execution authority."""

    definition: AgentDefinition
    candidates: tuple[TradeCandidate, ...] = ()
    risk_engine: RiskEngine = field(default_factory=RiskEngine)
    execution_surface: ExecutionSurface = ExecutionSurface.VIRTUAL_MARKET

    def __post_init__(self) -> None:
        if (
            self.definition.name != "risk"
            or self.definition.stage is not AgentStage.RISK
        ):
            raise ValueError("risk gate requires the risk definition")

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        prior_results: Mapping[str, AgentResult],
    ) -> AgentResult:
        """Return the dependency-checked, fail-closed risk result."""
        blocked_dependencies = tuple(
            dependency
            for dependency in self.definition.dependencies
            if dependency not in prior_results
            or prior_results[dependency].status
            not in {AgentStatus.SUCCESS, AgentStatus.PARTIAL}
        )
        if blocked_dependencies:
            return self._result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=tuple(
                    f"DEPENDENCY_NOT_READY:{dependency}"
                    for dependency in blocked_dependencies
                ),
                reason_codes=("AGENT_DEPENDENCY_BLOCKED",),
            )
        return self.evaluate_candidates(snapshot)

    def evaluate_candidates(self, snapshot: MarketSnapshot) -> AgentResult:
        """Evaluate candidates after readiness has already been established."""
        try:
            return self._evaluate_candidates(snapshot)
        except Exception as error:
            return self._result(
                snapshot,
                status=AgentStatus.FAILED,
                data_quality=DataQuality.DATA_INVALID,
                applicable=False,
                blockers=("AGENT_INTERNAL_ERROR",),
                reason_codes=("AGENT_FAILED_CLOSED",),
                calculation_metadata={"error_type": type(error).__name__},
            )

    def _evaluate_candidates(self, snapshot: MarketSnapshot) -> AgentResult:
        if snapshot.market_metadata.get("virtual_managed_position_active") is True:
            return self._result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("VIRTUAL_MANAGED_POSITION_ALREADY_OPEN",),
                reason_codes=("RISK_REJECTED_POSITION_REPLACEMENT",),
            )
        if (
            snapshot.market_metadata.get("virtual_position_identity_unavailable")
            is True
        ):
            return self._result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("VIRTUAL_POSITION_IDENTITY_UNAVAILABLE",),
                reason_codes=("RISK_REJECTED_UNBOUND_INVENTORY",),
            )
        if not self.candidates:
            return self._result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("TRADE_CANDIDATE_AND_RISK_PLAN_MISSING",),
                reason_codes=("RISK_REJECTED_NO_PLAN",),
            )
        try:
            filters = SymbolFilters.from_symbol_info(self._symbol_info(snapshot))
        except ExchangePayloadError:
            return self._result(
                snapshot,
                status=AgentStatus.BLOCKED,
                data_quality=snapshot.data_quality,
                applicable=False,
                blockers=("EXCHANGE_FILTERS_INVALID",),
                reason_codes=("RISK_REJECTED_INVALID_FILTERS",),
            )
        context = RiskContext(
            equity_usdt=self._optional_decimal(
                snapshot.wallet_summary.get("equity_usdt")
            ),
            current_exposure_usdt=self._optional_decimal(
                snapshot.inventory_summary.get("exposure_usdt")
            )
            or Decimal("0"),
            inventory_quantity=self._optional_decimal(
                snapshot.inventory_summary.get("quantity")
            ),
            daily_loss_usdt=self._optional_decimal(
                snapshot.wallet_summary.get("daily_loss_usdt")
            )
            or Decimal("0"),
            open_risk_usdt=self._optional_decimal(
                snapshot.wallet_summary.get("open_risk_usdt")
            )
            or Decimal("0"),
            open_position_count=self._optional_integer(
                snapshot.wallet_summary.get("open_position_count")
            ),
            estimated_slippage_ratio=self._optional_decimal(
                snapshot.market_metadata.get("estimated_slippage_ratio")
            )
            or Decimal("0"),
            consecutive_losses=self._optional_integer(
                snapshot.market_metadata.get("consecutive_losses")
            ),
            cooldown_active=snapshot.market_metadata.get("cooldown_active") is True,
        )
        assessments = self.risk_engine.evaluate_many(
            self.candidates,
            snapshot,
            context,
            filters,
            limit=5,
            execution_surface=self.execution_surface,
        )
        assessment = min(
            assessments,
            key=lambda item: (
                not item.approved,
                len(item.blockers),
                item.candidate_id,
            ),
        )
        selected_candidate = next(
            item
            for item in self.candidates
            if item.candidate_id == assessment.candidate_id
        )
        return self._result(
            snapshot,
            status=AgentStatus.SUCCESS if assessment.approved else AgentStatus.BLOCKED,
            data_quality=snapshot.data_quality,
            applicable=True,
            score=100.0 if assessment.approved else 0.0,
            confidence=1.0,
            blockers=assessment.blockers,
            reason_codes=("RISK_APPROVED" if assessment.approved else "RISK_REJECTED",),
            calculation_metadata={
                "candidate_id": assessment.candidate_id,
                "scenario_id": assessment.scenario_id,
                "approved": assessment.approved,
                "size_usdt": str(assessment.size_usdt),
                "quantity": str(assessment.quantity),
                "risk_amount_usdt": str(assessment.risk_amount_usdt),
                "gross_risk_reward": str(selected_candidate.gross_risk_reward),
                "structural_risk_reward": (
                    str(selected_candidate.structural_risk_reward)
                    if selected_candidate.structural_risk_reward is not None
                    else None
                ),
                "net_risk_reward": (
                    str(selected_candidate.net_risk_reward)
                    if selected_candidate.net_risk_reward is not None
                    else None
                ),
                "expected_r": (
                    str(selected_candidate.expected_r)
                    if selected_candidate.expected_r is not None
                    else None
                ),
                "probability_calibration_state": (
                    selected_candidate.probability_calibration_state
                ),
                "evaluated_candidate_count": len(assessments),
                "unevaluated_candidate_count": max(
                    0, len(self.candidates) - len(assessments)
                ),
                "assessments": tuple(
                    {
                        "candidate_id": item.candidate_id,
                        "scenario_id": item.scenario_id,
                        "approved": item.approved,
                        "blockers": item.blockers,
                    }
                    for item in assessments
                ),
            },
        )

    @staticmethod
    def _optional_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
        return parsed if parsed.is_finite() and parsed >= Decimal("0") else None

    @staticmethod
    def _optional_integer(value: object) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    @staticmethod
    def _symbol_info(snapshot: MarketSnapshot) -> SymbolInfo:
        filters: dict[str, Mapping[str, FilterValue]] = {}
        for name, raw_values in snapshot.exchange_filters.items():
            if not isinstance(raw_values, Mapping):
                raise ExchangePayloadError("snapshot exchange filter is invalid")
            parsed: dict[str, FilterValue] = {}
            for key, value in raw_values.items():
                if value is not None and not isinstance(value, (str, int, float, bool)):
                    raise ExchangePayloadError("snapshot filter value is invalid")
                parsed[str(key)] = value
            filters[name] = parsed
        base_asset = snapshot.market_metadata.get("base_asset", "UNKNOWN_BASE")
        quote_asset = snapshot.market_metadata.get("quote_asset", "UNKNOWN_QUOTE")
        status = snapshot.market_metadata.get("trading_status", "UNKNOWN")
        return SymbolInfo(
            snapshot.symbol,
            str(status),
            str(base_asset),
            str(quote_asset),
            filters,
        )

    def _result(
        self,
        snapshot: MarketSnapshot,
        *,
        status: AgentStatus,
        data_quality: DataQuality,
        applicable: bool,
        directional_vote: float = 0.0,
        score: float = 0.0,
        confidence: float = 0.0,
        blockers: tuple[str, ...] = (),
        reason_codes: tuple[str, ...],
        calculation_metadata: Mapping[str, object] | None = None,
    ) -> AgentResult:
        return AgentResult(
            agent_name=self.definition.name,
            agent_version=self.definition.version,
            snapshot_id=snapshot.snapshot_id,
            timestamp=snapshot.created_at,
            symbol=snapshot.symbol,
            timeframes=snapshot.timeframes,
            status=status,
            data_quality=data_quality,
            applicable=applicable,
            directional_vote=directional_vote,
            score=score,
            confidence=confidence,
            blockers=blockers,
            false_positive_risk=self.definition.false_positive_risk,
            hard_gate_eligible=False,
            oos_validation_status=OOSValidationStatus.UNVALIDATED,
            promotion_status=self.definition.promotion_status,
            reason_codes=reason_codes,
            calculation_metadata=calculation_metadata or {},
        )

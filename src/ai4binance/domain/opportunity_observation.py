"""Canonical domain contracts for research-only opportunity observation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from ai4binance.domain import Action, SetupTier

ZERO = Decimal("0")
MEASURABLE_DIRECTIONS = frozenset(
    {"BULLISH", "BEARISH", "BULLISH_CAUTION", "BEARISH_CAUTION"}
)


class OpportunityBias(StrEnum):
    """Directional observation, not an executable signal."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class OpportunityLifecycleState(StrEnum):
    """Opportunity visibility state; never an execution permission."""

    NEW = "NEW"
    DISCOVERED = "DISCOVERED"
    WATCH_ONLY = "WATCH_ONLY"
    SETUP_FORMING = "SETUP_FORMING"
    DEVELOPING = "DEVELOPING"
    CONFIRMATION_PENDING = "CONFIRMATION_PENDING"
    RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE"
    QUALIFIED = "QUALIFIED"
    CONFIRMED = "CONFIRMED"
    VALIDATION_PENDING = "VALIDATION_PENDING"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
    VIRTUAL_ELIGIBLE = "VIRTUAL_ELIGIBLE"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"


class OpportunityGenerationOutcome(StrEnum):
    """Result of one bounded opportunity-generation attempt."""

    COMPLETE = "COMPLETE"
    NO_SETUP = "NO_SETUP"
    DATA_BLOCKED = "DATA_BLOCKED"
    INCOMPLETE_PLAN = "INCOMPLETE_PLAN"


class OpportunityGenerationStage(StrEnum):
    """Deterministic stage at which an opportunity attempt stopped."""

    COMPLETE = "COMPLETE"
    DATA_QUALITY = "DATA_QUALITY"
    SIGNAL_QUALIFICATION = "SIGNAL_QUALIFICATION"
    TRADE_PLAN = "TRADE_PLAN"
    POSITION_SIZING = "POSITION_SIZING"


@dataclass(frozen=True, slots=True)
class OpportunityGenerationDiagnostic:
    """Non-opportunity evidence explaining why an attempt was rejected."""

    outcome: OpportunityGenerationOutcome
    failed_stage: OpportunityGenerationStage
    reason_codes: tuple[str, ...]
    missing_fields: tuple[str, ...]
    retryability: str

    @property
    def complete(self) -> bool:
        return self.outcome is OpportunityGenerationOutcome.COMPLETE

    def to_payload(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "failed_stage": self.failed_stage.value,
            "reason_codes": self.reason_codes,
            "missing_fields": self.missing_fields,
            "retryability": self.retryability,
        }


def has_complete_measurable_trade_plan(candidate: Mapping[str, object]) -> bool:
    """Return whether a research candidate has a measurable directional plan."""

    direction = str(candidate.get("direction", "")).strip().upper()
    if direction not in MEASURABLE_DIRECTIONS:
        return False
    values: dict[str, Decimal] = {}
    for name in ("entry", "stop_loss", "tp1", "tp2", "tp3", "target_risk_reward"):
        value = candidate.get(name)
        if isinstance(value, bool):
            return False
        try:
            decimal_value = Decimal(str(value))
        except (ArithmeticError, ValueError):
            return False
        if not decimal_value.is_finite() or decimal_value <= ZERO:
            return False
        values[name] = decimal_value
    entry = values["entry"]
    stop = values["stop_loss"]
    targets = (values["tp1"], values["tp2"], values["tp3"])
    if direction.startswith("BULLISH"):
        return stop < entry < targets[0] < targets[1] < targets[2]
    return stop > entry > targets[0] > targets[1] > targets[2]


def has_complete_measurable_opportunity(candidate: Mapping[str, object]) -> bool:
    """Return whether a market-specific opportunity is complete and measurable."""

    if not has_complete_measurable_trade_plan(candidate):
        return False
    symbol = candidate.get("symbol")
    market = str(candidate.get("market", "")).strip().upper()
    direction = str(candidate.get("direction", "")).strip().upper()
    side = str(candidate.get("side", "")).strip().upper()
    if not isinstance(symbol, str) or not symbol.strip():
        return False
    expected_side = (
        "BUY"
        if market == "SPOT" and direction.startswith("BULLISH")
        else "SELL"
        if market == "SPOT"
        else "LONG"
        if market == "USD_M_FUTURES" and direction.startswith("BULLISH")
        else "SHORT"
        if market == "USD_M_FUTURES"
        else ""
    )
    if side != expected_side:
        return False
    quantity = _positive_decimal(candidate.get("quantity"))
    if quantity is None:
        return False
    if market == "USD_M_FUTURES":
        leverage = candidate.get("leverage")
        return (
            isinstance(leverage, int)
            and not isinstance(leverage, bool)
            and 1 <= leverage <= 125
        )
    return market == "SPOT"


def diagnose_opportunity_generation(
    candidate: Mapping[str, object],
) -> OpportunityGenerationDiagnostic:
    """Explain completeness failure without promoting it to an opportunity."""

    reason_codes: list[str] = []
    missing_fields: list[str] = []

    def missing_or_invalid(name: str, unavailable: str, invalid: str) -> None:
        value = candidate.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_fields.append(name)
            reason_codes.append(unavailable)
        elif _positive_decimal(value) is None:
            reason_codes.append(invalid)

    status = str(candidate.get("status", "")).strip().upper()
    data_status = str(candidate.get("data_status", "")).strip().upper()
    raw_blockers = candidate.get("blockers", ())
    blockers = (
        tuple(
            value.strip()
            for value in raw_blockers
            if isinstance(value, str) and value.strip()
        )
        if isinstance(raw_blockers, (list, tuple))
        else ()
    )
    data_reasons = tuple(
        blocker
        for blocker in blockers
        if blocker.startswith(("DATA_", "DATASET_", "DERIVATIVES_DATA_"))
    )
    if status == "DATA_BLOCKED" or data_status in {"STALE", "INVALID", "UNAVAILABLE"}:
        reason_codes.extend(data_reasons or ("OPPORTUNITY_INPUT_DATA_UNAVAILABLE",))

    symbol = candidate.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        missing_fields.append("symbol")
        reason_codes.append("SYMBOL_UNAVAILABLE")

    market = str(candidate.get("market", "")).strip().upper()
    if market not in {"SPOT", "USD_M_FUTURES"}:
        if not market:
            missing_fields.append("market")
        reason_codes.append("MARKET_UNSUPPORTED")

    direction = str(candidate.get("direction", "")).strip().upper()
    if direction not in MEASURABLE_DIRECTIONS:
        if not direction:
            missing_fields.append("direction")
            reason_codes.append("DIRECTION_UNAVAILABLE")
        elif direction in {"WATCH_ONLY", "NEUTRAL"}:
            reason_codes.append(
                "SETUP_CONFIRMATION_PENDING"
                if candidate.get("confirmation_requirements")
                else "SETUP_NOT_CONFIRMED"
            )
        else:
            reason_codes.append("DIRECTION_INVALID")

    levels = (
        ("entry", "ENTRY_UNAVAILABLE", "ENTRY_INVALID"),
        ("stop_loss", "STOP_UNAVAILABLE", "STOP_INVALID"),
        ("tp1", "TP1_UNAVAILABLE", "TP1_INVALID"),
        ("tp2", "TP2_UNAVAILABLE", "TP2_INVALID"),
        ("tp3", "TP3_UNAVAILABLE", "TP3_INVALID"),
        (
            "target_risk_reward",
            "RISK_REWARD_UNAVAILABLE",
            "RISK_REWARD_INVALID",
        ),
    )
    for name, unavailable, invalid in levels:
        missing_or_invalid(name, unavailable, invalid)
    if (
        direction in MEASURABLE_DIRECTIONS
        and not any(
            code.endswith(("_UNAVAILABLE", "_INVALID")) for code in reason_codes
        )
        and not has_complete_measurable_trade_plan(candidate)
    ):
        reason_codes.append("TRADE_PLAN_GEOMETRY_INVALID")

    side = str(candidate.get("side", "")).strip().upper()
    expected_side = (
        "BUY"
        if market == "SPOT" and direction.startswith("BULLISH")
        else "SELL"
        if market == "SPOT" and direction.startswith("BEARISH")
        else "LONG"
        if market == "USD_M_FUTURES" and direction.startswith("BULLISH")
        else "SHORT"
        if market == "USD_M_FUTURES" and direction.startswith("BEARISH")
        else ""
    )
    if not side:
        missing_fields.append("side")
        reason_codes.append("SIDE_UNAVAILABLE")
    elif side != expected_side:
        reason_codes.append("SIDE_DIRECTION_MISMATCH")
    missing_or_invalid("quantity", "QUANTITY_UNAVAILABLE", "QUANTITY_INVALID")
    if market == "USD_M_FUTURES":
        leverage = candidate.get("leverage")
        if leverage is None or leverage == "":
            missing_fields.append("leverage")
            reason_codes.append("LEVERAGE_UNAVAILABLE")
        elif (
            not isinstance(leverage, int)
            or isinstance(leverage, bool)
            or not 1 <= leverage <= 125
        ):
            reason_codes.append("LEVERAGE_OUT_OF_RANGE")

    if has_complete_measurable_opportunity(candidate):
        return OpportunityGenerationDiagnostic(
            outcome=OpportunityGenerationOutcome.COMPLETE,
            failed_stage=OpportunityGenerationStage.COMPLETE,
            reason_codes=(),
            missing_fields=(),
            retryability="NOT_REQUIRED",
        )
    unique_reasons = tuple(dict.fromkeys(reason_codes))
    unique_missing = tuple(dict.fromkeys(missing_fields))
    if status == "DATA_BLOCKED" or data_status in {"STALE", "INVALID", "UNAVAILABLE"}:
        outcome = OpportunityGenerationOutcome.DATA_BLOCKED
        stage = OpportunityGenerationStage.DATA_QUALITY
        retryability = "NEEDS_DATA_RECOVERY"
        final_reasons = tuple(
            code
            for code in unique_reasons
            if code in data_reasons
            or code
            in {
                "OPPORTUNITY_INPUT_DATA_UNAVAILABLE",
                "SYMBOL_UNAVAILABLE",
                "MARKET_UNSUPPORTED",
            }
        )
    elif direction not in MEASURABLE_DIRECTIONS:
        outcome = OpportunityGenerationOutcome.NO_SETUP
        stage = OpportunityGenerationStage.SIGNAL_QUALIFICATION
        retryability = "RETRY_NEXT_CLOSED_CANDLE"
        final_reasons = tuple(
            code
            for code in unique_reasons
            if code.startswith(("SETUP_", "DIRECTION_"))
            or code in {"SYMBOL_UNAVAILABLE", "MARKET_UNSUPPORTED"}
        )
    elif (
        any(
            field in unique_missing
            or any(code.startswith(prefix) for code in unique_reasons)
            for field, prefix in (
                ("entry", "ENTRY_"),
                ("stop_loss", "STOP_"),
                ("tp1", "TP1_"),
                ("tp2", "TP2_"),
                ("tp3", "TP3_"),
                ("target_risk_reward", "RISK_REWARD_"),
            )
        )
        or "TRADE_PLAN_GEOMETRY_INVALID" in unique_reasons
    ):
        outcome = OpportunityGenerationOutcome.INCOMPLETE_PLAN
        stage = OpportunityGenerationStage.TRADE_PLAN
        retryability = "RETRY_NEXT_CLOSED_CANDLE"
        final_reasons = unique_reasons
    else:
        outcome = OpportunityGenerationOutcome.INCOMPLETE_PLAN
        stage = OpportunityGenerationStage.POSITION_SIZING
        retryability = "REVIEW_MARKET_CONSTRAINTS"
        final_reasons = unique_reasons
    return OpportunityGenerationDiagnostic(
        outcome=outcome,
        failed_stage=stage,
        reason_codes=final_reasons or ("OPPORTUNITY_CONTRACT_INCOMPLETE",),
        missing_fields=unique_missing,
        retryability=retryability,
    )


def estimate_measurable_trade_plan(
    *,
    entry: Decimal,
    risk: Decimal,
    direction: str,
    target_risk_reward: Decimal = Decimal("2"),
) -> dict[str, str]:
    """Estimate research-only stop and targets from entry and observed volatility."""

    normalized_direction = direction.strip().upper()
    if (
        normalized_direction not in MEASURABLE_DIRECTIONS
        or not entry.is_finite()
        or not risk.is_finite()
        or not target_risk_reward.is_finite()
        or min(entry, risk, target_risk_reward) <= ZERO
    ):
        return {}
    multipliers = (
        target_risk_reward,
        target_risk_reward + Decimal("1"),
        target_risk_reward + Decimal("2"),
    )
    if normalized_direction.startswith("BULLISH"):
        stop = entry - risk
        targets = tuple(entry + risk * multiplier for multiplier in multipliers)
    else:
        stop = entry + risk
        targets = tuple(entry - risk * multiplier for multiplier in multipliers)
    if min(stop, *targets) <= ZERO:
        return {}
    plan = {
        "entry": _decimal_text(entry),
        "stop_loss": _decimal_text(stop),
        "tp1": _decimal_text(targets[0]),
        "tp2": _decimal_text(targets[1]),
        "tp3": _decimal_text(targets[2]),
        "target_risk_reward": _decimal_text(target_risk_reward),
    }
    measurable = has_complete_measurable_trade_plan(
        plan | {"direction": normalized_direction}
    )
    return plan if measurable else {}


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _positive_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed > ZERO else None


@dataclass(frozen=True, slots=True)
class VWAPOpportunityConfig:
    """Conservative thresholds for the unvalidated VWAP experiment."""

    atr_period: int = 14
    volume_window: int = 20
    min_relative_volume: Decimal = Decimal("1.2")
    max_atr_distance: Decimal = Decimal("1.5")
    crossing_lookback: int = 8
    max_crossings: int = 3

    def __post_init__(self) -> None:
        if self.atr_period < 1 or self.volume_window < 1:
            raise ValueError("indicator periods must be positive")
        if self.min_relative_volume <= ZERO or self.max_atr_distance <= ZERO:
            raise ValueError("VWAP thresholds must be positive")
        if self.crossing_lookback < 2 or self.max_crossings < 0:
            raise ValueError("crossing thresholds are invalid")


@dataclass(frozen=True, slots=True)
class VWAPOpportunity:
    """Auditable output that remains RESEARCH_ONLY by construction."""

    snapshot_id: str
    symbol: str
    timeframe: str
    observed_at: datetime
    session_start: datetime
    setup_name: str
    bias: OpportunityBias
    action: Action
    setup_tier: SetupTier
    price: Decimal | None
    vwap: Decimal | None
    atr: Decimal | None
    relative_volume: Decimal | None
    atr_distance: Decimal | None
    crossing_count: int
    evidence: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    lifecycle_state: OpportunityLifecycleState = OpportunityLifecycleState.WATCH_ONLY
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("VWAP opportunity cannot grant execution authority")
        state = _coerce_lifecycle_state(self.lifecycle_state)
        if state is OpportunityLifecycleState.PAPER_ELIGIBLE:
            raise ValueError("VWAP opportunity cannot be paper eligible")
        object.__setattr__(self, "lifecycle_state", state)


def _coerce_lifecycle_state(
    value: OpportunityLifecycleState | str,
) -> OpportunityLifecycleState:
    try:
        return OpportunityLifecycleState(value)
    except ValueError as exc:
        raise ValueError("opportunity lifecycle state is invalid") from exc

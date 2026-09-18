"""Recovery-oriented opportunity radar without execution authority."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from ai4binance.config import Settings
from ai4binance.opportunities import (
    OpportunityInbox,
    OpportunityInboxBuilder,
    OpportunityInboxItem,
)
from ai4binance.validation.summary import ValidationSummaryReader

ZERO = Decimal("0")
ONE = Decimal("1")


class RecoveryLadderStage(StrEnum):
    """User-facing candidate maturity, not an execution permission."""

    RADAR_ONLY = "RADAR_ONLY"
    WATCHLIST = "WATCHLIST"
    TRADE_CANDIDATE = "TRADE_CANDIDATE"
    PAPER_READY = "PAPER_READY"
    LIVE_BLOCKED_UNTIL_RISK_OOS = "LIVE_BLOCKED_UNTIL_RISK_OOS"


class RecoveryProposalKind(StrEnum):
    INVENTORY_SELL_REBUY_REVIEW = "INVENTORY_SELL_REBUY_REVIEW"
    TECHNICAL_RANGE_ROTATION_REVIEW = "TECHNICAL_RANGE_ROTATION_REVIEW"
    VALIDATION_OPPORTUNITY_REVIEW = "VALIDATION_OPPORTUNITY_REVIEW"


@dataclass(frozen=True, slots=True)
class RecoveryLensContribution:
    """One deterministic evidence lens used to rank recovery candidates."""

    lens: str
    direction: str
    score: Decimal
    confidence: Decimal
    evidence_ref: str
    blocker: str = ""

    def __post_init__(self) -> None:
        if (
            not self.lens.strip()
            or not self.direction.strip()
            or not self.evidence_ref.strip()
        ):
            raise ValueError("recovery lens identity is required")
        if any(
            not value.is_finite() or value < ZERO
            for value in (self.score, self.confidence)
        ):
            raise ValueError("recovery lens values must be non-negative")
        if self.score > Decimal("100") or self.confidence > ONE:
            raise ValueError("recovery lens score/confidence is out of range")


@dataclass(frozen=True, slots=True)
class RecoveryRadarPolicy:
    """Bounded candidate-ladder policy for full-coin recovery planning."""

    maximum_inventory_review_ratio: Decimal = Decimal("0.25")
    fee_ratio_per_side: Decimal = Decimal("0.001")
    minimum_range_move_ratio: Decimal = Decimal("0.02")
    minimum_notional_usdt: Decimal = Decimal("10")
    high_attention_score: Decimal = Decimal("120")
    action_candidate_score: Decimal = Decimal("150")
    maximum_technical_ranges: int = 4
    max_candidates: int = 10

    def __post_init__(self) -> None:
        ratios = (
            self.maximum_inventory_review_ratio,
            self.fee_ratio_per_side,
            self.minimum_range_move_ratio,
        )
        if any(not value.is_finite() or value < ZERO for value in ratios):
            raise ValueError("recovery radar ratios must be finite and non-negative")
        if not ZERO < self.maximum_inventory_review_ratio <= ONE:
            raise ValueError("inventory review ratio must be in (0, 1]")
        if not ZERO <= self.fee_ratio_per_side < ONE:
            raise ValueError("fee ratio must be in [0, 1)")
        if (
            self.minimum_notional_usdt <= ZERO
            or self.high_attention_score <= ZERO
            or self.action_candidate_score < self.high_attention_score
            or self.action_candidate_score > Decimal("200")
            or self.maximum_technical_ranges < 0
            or self.max_candidates < 1
        ):
            raise ValueError("recovery radar policy limits are invalid")


@dataclass(frozen=True, slots=True)
class TechnicalRecoveryRange:
    """Support/resistance-derived range candidate, not an execution signal."""

    timeframe: str
    source: str
    support_price: Decimal
    resistance_price: Decimal
    range_move_ratio: Decimal
    confidence: Decimal
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.timeframe.strip() or not self.source.strip():
            raise ValueError("technical recovery range identity is required")
        if self.support_price >= self.resistance_price:
            raise ValueError(
                "technical recovery range support must be below resistance"
            )
        values = (
            self.support_price,
            self.resistance_price,
            self.range_move_ratio,
            self.confidence,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("technical recovery range values must be non-negative")
        if self.confidence > ONE:
            raise ValueError("technical recovery range confidence is out of range")
        _require_unique_nonblank(
            "technical recovery range evidence", self.evidence_refs
        )


@dataclass(frozen=True, slots=True)
class RecoveryCandidate:
    """One candidate in the recovery ladder; proposal-only by construction."""

    candidate_id: str
    symbol: str
    proposal_kind: RecoveryProposalKind
    ladder_stage: RecoveryLadderStage
    review_action: str
    rationale: str
    source: str
    timeframe: str
    setup_name: str
    score: Decimal
    confidence: Decimal
    inventory_units_considered: Decimal = ZERO
    max_review_units: Decimal = ZERO
    estimated_sell_price: Decimal | None = None
    estimated_rebuy_price: Decimal | None = None
    estimated_cycle_unit_gain: Decimal = ZERO
    estimated_cycle_gain_ratio: Decimal = ZERO
    intelligence_score: Decimal = ZERO
    opportunity_grade: str = "RADAR_ONLY"
    miss_risk: str = "LOW"
    false_positive_risk: str = "HIGH"
    lens_contributions: tuple[RecoveryLensContribution, ...] = field(
        default_factory=tuple
    )
    blockers: tuple[str, ...] = field(default_factory=tuple)
    next_safe_actions: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    validation_queue_ref: str = ""
    oos_evidence_status: str = "NOT_QUEUED"
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        required = (
            self.candidate_id,
            self.symbol,
            self.review_action,
            self.rationale,
            self.source,
            self.timeframe,
            self.setup_name,
            self.oos_evidence_status,
            self.promotion_status,
        )
        if any(not value.strip() for value in required):
            raise ValueError("recovery candidate identity is required")
        if self.validation_queue_ref and not self.validation_queue_ref.strip():
            raise ValueError("recovery validation queue ref is invalid")
        numeric = (
            self.score,
            self.confidence,
            self.inventory_units_considered,
            self.max_review_units,
            self.estimated_cycle_unit_gain,
            self.estimated_cycle_gain_ratio,
            self.intelligence_score,
        )
        if any(not value.is_finite() or value < ZERO for value in numeric):
            raise ValueError("recovery candidate values must be non-negative")
        if self.score > Decimal("100") or self.confidence > ONE:
            raise ValueError("recovery candidate score/confidence is out of range")
        if self.intelligence_score > Decimal("200"):
            raise ValueError("recovery candidate intelligence score is out of range")
        if not self.opportunity_grade.strip() or not self.miss_risk.strip():
            raise ValueError("recovery candidate IQ labels are required")
        prices = (self.estimated_sell_price, self.estimated_rebuy_price)
        if any(value is not None and value <= ZERO for value in prices):
            raise ValueError("recovery candidate prices must be positive")
        _require_unique_nonblank("recovery candidate blockers", self.blockers)
        _require_unique_nonblank(
            "recovery candidate next actions", self.next_safe_actions
        )
        _require_unique_nonblank("recovery candidate evidence", self.evidence_refs)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("recovery candidate cannot authorize execution")


@dataclass(frozen=True, slots=True)
class OpportunityRecoveryRadar:
    """User-facing candidate ladder for recovery planning."""

    symbol: str
    inventory_units: Decimal
    range_low: Decimal
    range_high: Decimal
    range_source: str
    range_move_ratio: Decimal
    ideal_full_cycle_end_units: Decimal
    ideal_full_cycle_unit_gain: Decimal
    ladder: tuple[RecoveryCandidate, ...]
    blockers: tuple[str, ...]
    next_safe_actions: tuple[str, ...]
    status: str = "RUNNING_WITH_BLOCKERS"
    command: str = "opportunity-recovery-radar"
    recovery_mode: str = "RECOVERY_GUARDED_RESEARCH_MODE"
    hindsight_notice: str = "HINDSIGHT_ENVELOPE_ONLY"
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("recovery radar symbol is required")
        if not self.range_source.strip():
            raise ValueError("recovery radar range source is required")
        if self.range_low >= self.range_high:
            raise ValueError("recovery radar range low must be below high")
        values = (
            self.inventory_units,
            self.range_low,
            self.range_high,
            self.range_move_ratio,
            self.ideal_full_cycle_end_units,
            self.ideal_full_cycle_unit_gain,
        )
        if any(not value.is_finite() or value < ZERO for value in values):
            raise ValueError("recovery radar values must be non-negative")
        _require_unique_nonblank("recovery radar blockers", self.blockers)
        _require_unique_nonblank("recovery radar next actions", self.next_safe_actions)
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("recovery radar cannot authorize execution")


OpportunitiesPayloadBuilder = Callable[[Settings, str | None], dict[str, object]]


def build_opportunity_recovery_radar(
    settings: Settings,
    *,
    symbol: str | None = None,
    inventory_units: object,
    range_low: object | None = None,
    range_high: object | None = None,
    cost_basis: object | None = None,
    opportunities_builder: OpportunitiesPayloadBuilder | None = None,
    policy: RecoveryRadarPolicy | None = None,
) -> OpportunityRecoveryRadar:
    """Build a recovery candidate ladder without weakening live gates."""
    selected_policy = policy or RecoveryRadarPolicy()
    normalized = (symbol or settings.symbol).strip().upper()
    units = _positive_decimal(inventory_units, "inventory_units")
    basis = _optional_positive_decimal(cost_basis, "cost_basis")

    payload = (
        opportunities_builder(settings, normalized)
        if opportunities_builder is not None
        else _default_opportunities_payload(settings, normalized)
    )
    inbox = _extract_inbox(payload)
    market_state = _extract_market_state(payload)
    technical_ranges = _technical_ranges_from_market_state(
        market_state,
        selected_policy,
    )
    low, high, range_source, range_source_blockers = _select_range(
        range_low,
        range_high,
        technical_ranges,
    )
    range_move_ratio = (high - low) / low
    ideal_end_units = units * high / low
    ideal_gain_units = ideal_end_units - units
    blockers = tuple(
        dict.fromkeys(
            (
                *_text_tuple(payload.get("blockers")),
                *range_source_blockers,
                *_inventory_blockers(units, low, high, basis, selected_policy),
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    ladder = (
        _inventory_candidate(
            normalized,
            units,
            low,
            high,
            basis,
            selected_policy,
            blockers,
            market_state,
        ),
        *_technical_range_candidates(
            normalized,
            units,
            technical_ranges,
            selected_policy,
            blockers,
            market_state,
        ),
        *_opportunity_candidates(normalized, inbox, selected_policy, market_state),
    )[: selected_policy.max_candidates]
    next_actions = tuple(
        dict.fromkeys(
            action for candidate in ladder for action in candidate.next_safe_actions
        )
    ) or ("RUN_VALIDATION_QUEUE",)
    return OpportunityRecoveryRadar(
        symbol=normalized,
        inventory_units=units,
        range_low=low,
        range_high=high,
        range_source=range_source,
        range_move_ratio=range_move_ratio,
        ideal_full_cycle_end_units=ideal_end_units,
        ideal_full_cycle_unit_gain=ideal_gain_units,
        ladder=ladder,
        blockers=blockers,
        next_safe_actions=next_actions,
        hindsight_notice=(
            "HINDSIGHT_ENVELOPE_ONLY"
            if range_source == "OPERATOR_RANGE"
            else "TECHNICAL_RANGE_ESTIMATE_NOT_SIGNAL"
        ),
    )


def _inventory_candidate(
    symbol: str,
    units: Decimal,
    low: Decimal,
    high: Decimal,
    cost_basis: Decimal | None,
    policy: RecoveryRadarPolicy,
    parent_blockers: tuple[str, ...],
    market_state: Mapping[str, object],
) -> RecoveryCandidate:
    review_units = units * policy.maximum_inventory_review_ratio
    sell_after_fee = high * (ONE - policy.fee_ratio_per_side)
    rebuy_after_fee = low * (ONE + policy.fee_ratio_per_side)
    end_units = review_units * sell_after_fee / rebuy_after_fee
    gain_units = max(ZERO, end_units - review_units)
    gain_ratio = gain_units / review_units if review_units > ZERO else ZERO
    notional = review_units * high
    blockers = tuple(
        dict.fromkeys(
            (
                *_inventory_blockers(units, low, high, cost_basis, policy),
                *(
                    blocker
                    for blocker in parent_blockers
                    if blocker
                    in {
                        "OOS_APPROVAL_MISSING",
                        "RISK_APPROVAL_MISSING",
                        "TRADE_CANDIDATE_AND_RISK_PLAN_MISSING",
                    }
                ),
                "EXECUTION_NOT_ALLOWED",
                *_market_intelligence_blockers(market_state),
                "LIVE_ORDER_BLOCKED",
            )
        )
    )
    stage = (
        RecoveryLadderStage.TRADE_CANDIDATE
        if notional >= policy.minimum_notional_usdt
        and (high - low) / low >= policy.minimum_range_move_ratio
        else RecoveryLadderStage.WATCHLIST
    )
    lenses = _inventory_lenses(units, low, high, blockers, policy, market_state)
    intelligence_score = _intelligence_score(lenses)
    return RecoveryCandidate(
        candidate_id=f"recovery:{symbol}:inventory-rotation",
        symbol=symbol,
        proposal_kind=RecoveryProposalKind.INVENTORY_SELL_REBUY_REVIEW,
        ladder_stage=stage,
        review_action="SELL_HIGH_REBUY_LOW_REVIEW",
        rationale=(
            "Full-coin inventory can be reviewed for staged sell/rebuy rotation; "
            "this is a hindsight range envelope, not an executable signal."
        ),
        source="explicit_inventory_range",
        timeframe="MULTI_TF",
        setup_name="inventory_rotation_recovery",
        score=min(Decimal("100"), ((high - low) / low) * Decimal("100")),
        confidence=Decimal("0"),
        inventory_units_considered=units,
        max_review_units=review_units,
        estimated_sell_price=high,
        estimated_rebuy_price=low,
        estimated_cycle_unit_gain=gain_units,
        estimated_cycle_gain_ratio=gain_ratio,
        intelligence_score=intelligence_score,
        opportunity_grade=_opportunity_grade(intelligence_score, policy),
        miss_risk=_miss_risk(intelligence_score, blockers, policy),
        false_positive_risk=_false_positive_risk(blockers),
        lens_contributions=lenses,
        blockers=blockers,
        next_safe_actions=(
            "BUILD_STAGED_SELL_REBUY_RISK_PLAN",
            "CONFIRM_CURRENT_PRICE_AND_ORDER_BOOK_DEPTH",
            "RUN_ROTATION_BACKTEST_WALK_FORWARD_OOS",
            "REFRESH_TECHNICAL_RANGE_EVIDENCE",
            "PREPARE_RISK_REVIEW",
        ),
        evidence_refs=("explicit_inventory_units", "operator_range_high_low"),
        validation_queue_ref=f"recovery-validation:recovery:{symbol}:inventory-rotation",
        oos_evidence_status="QUEUED_RESEARCH_ONLY",
    )


def _default_opportunities_payload(
    settings: Settings,
    symbol: str,
) -> dict[str, object]:
    market_outlook_path = (
        settings.evidence_artifact_directory / "market-outlook" / "runtime-state.json"
    )
    market_state = _read_market_state(market_outlook_path)
    inbox = OpportunityInboxBuilder(
        validation_reader=ValidationSummaryReader(
            settings.validation_artifact_directory
        ),
        market_outlook_path=market_outlook_path,
    ).build(symbol)
    return {
        "command": "opportunities",
        "status": inbox.generation_status,
        "inbox": inbox,
        "blockers": inbox.blockers,
        "research_blockers": inbox.research_blockers,
        "execution_blockers": inbox.execution_blockers,
        "next_safe_actions": inbox.next_safe_actions,
        "research_loop_allowed": inbox.research_loop_allowed,
        "opportunity_generation_allowed": inbox.opportunity_generation_allowed,
        "market_state": market_state or {},
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _read_market_state(path: object) -> Mapping[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _inventory_blockers(
    units: Decimal,
    low: Decimal,
    high: Decimal,
    cost_basis: Decimal | None,
    policy: RecoveryRadarPolicy,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if units <= ZERO:
        blockers.append("RECOVERY_INVENTORY_UNAVAILABLE")
    if (high - low) / low < policy.minimum_range_move_ratio:
        blockers.append("RECOVERY_RANGE_TOO_SMALL")
    if cost_basis is None:
        blockers.append("RECOVERY_COST_BASIS_UNVERIFIED")
    blockers.extend(
        (
            "CURRENT_PRICE_UNVERIFIED",
            "SELL_TRIGGER_CONFIRMATION_REQUIRED",
            "REBUY_SUPPORT_RECLAIM_CONFIRMATION_REQUIRED",
            "OOS_APPROVAL_MISSING",
            "RISK_APPROVAL_MISSING",
        )
    )
    return tuple(dict.fromkeys(blockers))


def _technical_range_candidates(
    symbol: str,
    units: Decimal,
    technical_ranges: tuple[TechnicalRecoveryRange, ...],
    policy: RecoveryRadarPolicy,
    parent_blockers: tuple[str, ...],
    market_state: Mapping[str, object],
) -> tuple[RecoveryCandidate, ...]:
    candidates: list[RecoveryCandidate] = []
    inherited_blockers = tuple(
        blocker
        for blocker in parent_blockers
        if blocker
        in {
            "OOS_APPROVAL_MISSING",
            "RISK_APPROVAL_MISSING",
            "TRADE_CANDIDATE_AND_RISK_PLAN_MISSING",
            "ORDER_BOOK_DEPTH_MISSING",
        }
    )
    for index, candidate_range in enumerate(
        technical_ranges[: policy.maximum_technical_ranges],
        start=1,
    ):
        review_units = units * policy.maximum_inventory_review_ratio
        sell_after_fee = candidate_range.resistance_price * (
            ONE - policy.fee_ratio_per_side
        )
        rebuy_after_fee = candidate_range.support_price * (
            ONE + policy.fee_ratio_per_side
        )
        end_units = review_units * sell_after_fee / rebuy_after_fee
        gain_units = max(ZERO, end_units - review_units)
        blockers = tuple(
            dict.fromkeys(
                (
                    *inherited_blockers,
                    "CURRENT_PRICE_UNVERIFIED",
                    "TECHNICAL_TRIGGER_CONFIRMATION_REQUIRED",
                    "LEVEL_REACTION_CONFIRMATION_REQUIRED",
                    *_market_intelligence_blockers(market_state),
                    "OOS_APPROVAL_MISSING",
                    "RISK_APPROVAL_MISSING",
                    "EXECUTION_NOT_ALLOWED",
                    "LIVE_ORDER_BLOCKED",
                )
            )
        )
        stage = (
            RecoveryLadderStage.TRADE_CANDIDATE
            if review_units * candidate_range.resistance_price
            >= policy.minimum_notional_usdt
            and candidate_range.range_move_ratio >= policy.minimum_range_move_ratio
            else RecoveryLadderStage.WATCHLIST
        )
        lenses = _technical_lenses(
            candidate_range,
            units,
            blockers,
            policy,
            market_state,
        )
        intelligence_score = _intelligence_score(lenses)
        candidates.append(
            RecoveryCandidate(
                candidate_id=(
                    f"recovery:{symbol}:technical-range:"
                    f"{candidate_range.timeframe}:{index}"
                ),
                symbol=symbol,
                proposal_kind=RecoveryProposalKind.TECHNICAL_RANGE_ROTATION_REVIEW,
                ladder_stage=stage,
                review_action="SELL_RESISTANCE_REBUY_SUPPORT_REVIEW",
                rationale=(
                    "Technical support/resistance range is visible for staged "
                    "inventory rotation review. It combines market-outlook levels, "
                    "trend/regime context and setup evidence, but remains "
                    "confirmation-gated and non-executable."
                ),
                source=f"technical_market_outlook:{candidate_range.source}",
                timeframe=candidate_range.timeframe,
                setup_name="technical_range_rotation",
                score=min(
                    Decimal("100"),
                    candidate_range.range_move_ratio * Decimal("100")
                    + candidate_range.confidence * Decimal("25"),
                ),
                confidence=candidate_range.confidence,
                inventory_units_considered=units,
                max_review_units=review_units,
                estimated_sell_price=candidate_range.resistance_price,
                estimated_rebuy_price=candidate_range.support_price,
                estimated_cycle_unit_gain=gain_units,
                estimated_cycle_gain_ratio=(
                    gain_units / review_units if review_units > ZERO else ZERO
                ),
                intelligence_score=intelligence_score,
                opportunity_grade=_opportunity_grade(intelligence_score, policy),
                miss_risk=_miss_risk(intelligence_score, blockers, policy),
                false_positive_risk=_false_positive_risk(blockers),
                lens_contributions=lenses,
                blockers=blockers,
                next_safe_actions=(
                    "REFRESH_TECHNICAL_RANGE_EVIDENCE",
                    "CONFIRM_LEVEL_REACTION",
                    "CONFIRM_CURRENT_PRICE_AND_ORDER_BOOK_DEPTH",
                    "RUN_ROTATION_BACKTEST_WALK_FORWARD_OOS",
                    "PREPARE_RISK_REVIEW",
                ),
                evidence_refs=candidate_range.evidence_refs,
                validation_queue_ref=(
                    "recovery-validation:"
                    f"recovery:{symbol}:technical-range:"
                    f"{candidate_range.timeframe}:{index}"
                ),
                oos_evidence_status="QUEUED_RESEARCH_ONLY",
            )
        )
    return tuple(candidates)


def _technical_ranges_from_market_state(
    market_state: Mapping[str, object],
    policy: RecoveryRadarPolicy,
) -> tuple[TechnicalRecoveryRange, ...]:
    key_levels = tuple(
        _mapping(item) for item in _sequence(market_state.get("key_levels"))
    )
    supports = [
        item for item in key_levels if str(item.get("kind", "")).upper() == "SUPPORT"
    ]
    resistances = [
        item for item in key_levels if str(item.get("kind", "")).upper() == "RESISTANCE"
    ]
    ranges: list[TechnicalRecoveryRange] = []
    for support in supports:
        timeframe = str(support.get("timeframe", "MULTI_TF")).strip()
        matching_resistances = [
            resistance
            for resistance in resistances
            if str(resistance.get("timeframe", "MULTI_TF")).strip() == timeframe
        ]
        for resistance in matching_resistances:
            support_price = _zone_upper(support.get("zone"))
            resistance_price = _zone_lower(resistance.get("zone"))
            if support_price <= ZERO or resistance_price <= support_price:
                continue
            move = (resistance_price - support_price) / support_price
            if move <= ZERO:
                continue
            ranges.append(
                TechnicalRecoveryRange(
                    timeframe=timeframe,
                    source=str(
                        resistance.get(
                            "source",
                            support.get("source", "ROLLING_SUPPORT_RESISTANCE"),
                        )
                    ),
                    support_price=support_price,
                    resistance_price=resistance_price,
                    range_move_ratio=move,
                    confidence=_technical_range_confidence(market_state, timeframe),
                    evidence_refs=_technical_range_evidence_refs(
                        market_state, timeframe
                    ),
                )
            )
    return tuple(
        sorted(
            ranges,
            key=lambda item: (
                item.range_move_ratio < policy.minimum_range_move_ratio,
                _timeframe_rank(item.timeframe),
                -item.range_move_ratio,
            ),
        )
    )


def _select_range(
    range_low: object | None,
    range_high: object | None,
    technical_ranges: tuple[TechnicalRecoveryRange, ...],
) -> tuple[Decimal, Decimal, str, tuple[str, ...]]:
    low = _optional_positive_decimal(range_low, "range_low")
    high = _optional_positive_decimal(range_high, "range_high")
    blockers: list[str] = []
    if low is not None and high is not None:
        if low >= high:
            raise ValueError("range_low must be below range_high")
        return low, high, "OPERATOR_RANGE", ()
    if low is not None or high is not None:
        blockers.append("OPERATOR_RANGE_PARTIAL_IGNORED")
    if technical_ranges:
        selected = technical_ranges[0]
        blockers.append("TECHNICAL_RANGE_NOT_EXECUTION_SIGNAL")
        return (
            selected.support_price,
            selected.resistance_price,
            f"TECHNICAL_RANGE:{selected.timeframe}:{selected.source}",
            tuple(blockers),
        )
    raise ValueError(
        "range_low/range_high required when technical range is unavailable"
    )


def _opportunity_candidates(
    symbol: str,
    inbox: Mapping[str, object],
    policy: RecoveryRadarPolicy,
    market_state: Mapping[str, object],
) -> tuple[RecoveryCandidate, ...]:
    items = _sequence(inbox.get("items"))
    candidates: list[RecoveryCandidate] = []
    for index, raw_item in enumerate(items[: policy.max_candidates - 1], start=1):
        item = _mapping(raw_item)
        item_blockers = _text_tuple(item.get("blockers"))
        final_blockers = tuple(dict.fromkeys((*item_blockers, "LIVE_ORDER_BLOCKED")))
        blockers = tuple(
            blocker for blocker in final_blockers if blocker != "LIVE_ORDER_BLOCKED"
        )
        score = _score_decimal(item.get("score"))
        confidence = _confidence_decimal(item.get("confidence"))
        lenses = _opportunity_lenses(
            item,
            final_blockers,
            score,
            confidence,
            market_state,
        )
        intelligence_score = _intelligence_score(lenses)
        candidates.append(
            RecoveryCandidate(
                candidate_id=f"recovery:{symbol}:watchlist:{index}",
                symbol=str(item.get("symbol", symbol)).upper(),
                proposal_kind=RecoveryProposalKind.VALIDATION_OPPORTUNITY_REVIEW,
                ladder_stage=_stage_for_item(item, blockers),
                review_action=_review_action_for_item(item, blockers),
                rationale=(
                    "Existing opportunity evidence is kept visible and promoted "
                    "through missing validation/risk steps instead of being hidden "
                    "behind a final NO_TRADE label."
                ),
                source=str(item.get("source", "opportunity_inbox")),
                timeframe=str(item.get("timeframe", "MULTI_TF")),
                setup_name=str(item.get("setup_name", "UNKNOWN_SETUP")),
                score=score,
                confidence=confidence,
                intelligence_score=intelligence_score,
                opportunity_grade=_opportunity_grade(intelligence_score, policy),
                miss_risk=_miss_risk(intelligence_score, final_blockers, policy),
                false_positive_risk=_false_positive_risk(final_blockers),
                lens_contributions=lenses,
                blockers=final_blockers,
                next_safe_actions=_next_actions_for_item(final_blockers),
                evidence_refs=("opportunity_inbox",),
                validation_queue_ref=(
                    f"recovery-validation:recovery:{symbol}:watchlist:{index}"
                ),
                oos_evidence_status="QUEUED_RESEARCH_ONLY",
            )
        )
    return tuple(candidates)


def _stage_for_item(
    item: Mapping[str, object],
    blockers: tuple[str, ...],
) -> RecoveryLadderStage:
    if (
        str(item.get("status", "")) == "READY"
        and str(item.get("promotion_status", "")) == "STAGED_CANDIDATE"
        and not blockers
    ):
        return RecoveryLadderStage.PAPER_READY
    if str(item.get("promotion_status", "")) == "STAGED_CANDIDATE":
        return RecoveryLadderStage.LIVE_BLOCKED_UNTIL_RISK_OOS
    if any("OOS" in blocker or "RISK" in blocker for blocker in blockers):
        return RecoveryLadderStage.WATCHLIST
    return RecoveryLadderStage.RADAR_ONLY


def _review_action_for_item(
    item: Mapping[str, object],
    blockers: tuple[str, ...],
) -> str:
    direction = str(item.get("direction", "UNKNOWN")).upper()
    if direction in {"BEARISH", "SELL", "SHORT"}:
        return "SELL_REVIEW_AFTER_RISK_PLAN"
    if direction in {"BULLISH", "BUY", "LONG"}:
        return "BUY_REVIEW_AFTER_RISK_PLAN"
    if any("OOS" in blocker for blocker in blockers):
        return "COMPLETE_OOS_BEFORE_ACTION"
    return "KEEP_ON_RECOVERY_WATCHLIST"


def _next_actions_for_item(blockers: tuple[str, ...]) -> tuple[str, ...]:
    actions: list[str] = []
    if any("OOS" in blocker or "BACKTEST" in blocker for blocker in blockers):
        actions.append("RUN_VALIDATION_QUEUE")
    if any("RISK" in blocker for blocker in blockers):
        actions.append("PREPARE_RISK_REVIEW")
    if any("EXECUTION" in blocker for blocker in blockers):
        actions.append("BUILD_CANDIDATE_RISK_PLAN")
    if any("ORDER_BOOK" in blocker or "DEPTH" in blocker for blocker in blockers):
        actions.append("REFRESH_LIQUIDITY_AND_DEPTH_EVIDENCE")
    if not actions:
        actions.append("KEEP_RECOVERY_RADAR_RUNNING")
    return tuple(dict.fromkeys(actions))


def _inventory_lenses(
    units: Decimal,
    low: Decimal,
    high: Decimal,
    blockers: tuple[str, ...],
    policy: RecoveryRadarPolicy,
    market_state: Mapping[str, object],
) -> tuple[RecoveryLensContribution, ...]:
    move = (high - low) / low
    return (
        _lens(
            "inventory_context",
            "SELL_REBUY",
            Decimal("85") if units > ZERO else Decimal("0"),
            Decimal("0.85") if units > ZERO else Decimal("0"),
            "explicit_inventory_units",
        ),
        _lens(
            "range_amplitude",
            "SELL_REBUY",
            _threshold_score(move, policy.minimum_range_move_ratio),
            Decimal("0.70"),
            "recovery_range",
            "RECOVERY_RANGE_TOO_SMALL"
            if "RECOVERY_RANGE_TOO_SMALL" in blockers
            else "",
        ),
        _lens(
            "validation_oos",
            "GATED",
            _blocker_clear_score(blockers, ("OOS", "BACKTEST", "WALK_FORWARD")),
            Decimal("0.65"),
            "validation_artifacts",
            "OOS_APPROVAL_MISSING" if any("OOS" in item for item in blockers) else "",
        ),
        _lens(
            "risk_gate",
            "GATED",
            _blocker_clear_score(blockers, ("RISK", "EXECUTION")),
            Decimal("0.65"),
            "risk_review",
            "RISK_APPROVAL_MISSING"
            if any("RISK" in item or "EXECUTION" in item for item in blockers)
            else "",
        ),
        _lens(
            "mspacis_structure",
            "CONTEXT",
            _source_presence_score(
                market_state,
                (
                    "market_structure",
                    "price_action",
                    "candlestick_intelligence",
                    "key_levels",
                    "setups_on_radar",
                ),
            ),
            Decimal("0.60"),
            "market_outlook:mspacis",
            "MSPACIS_EVIDENCE_INCOMPLETE"
            if "MSPACIS_EVIDENCE_INCOMPLETE" in blockers
            else "",
        ),
        _lens(
            "relative_strength",
            "CONTEXT",
            _source_presence_score(
                market_state,
                (
                    "relative_strength",
                    "hot_btc_relative_strength",
                    "hot_eth_relative_strength",
                ),
            ),
            Decimal("0.55"),
            "market_outlook:relative_strength",
            "RELATIVE_STRENGTH_EVIDENCE_MISSING"
            if "RELATIVE_STRENGTH_EVIDENCE_MISSING" in blockers
            else "",
        ),
        _lens(
            "derivatives_supplement",
            "SUPPLEMENTARY",
            _source_presence_score(
                market_state,
                ("derivatives", "funding", "open_interest", "long_short_ratio"),
            ),
            Decimal("0.45"),
            "market_outlook:derivatives",
            "DERIVATIVES_SUPPLEMENT_MISSING"
            if "DERIVATIVES_SUPPLEMENT_MISSING" in blockers
            else "",
        ),
        _lens(
            "news_whale_risk",
            "RISK_CONTEXT",
            _source_presence_score(
                market_state,
                ("news", "social", "whale", "onchain", "market_context_events"),
            ),
            Decimal("0.45"),
            "market_outlook:news_whale",
            "NEWS_WHALE_RISK_UNVERIFIED"
            if "NEWS_WHALE_RISK_UNVERIFIED" in blockers
            else "",
        ),
        _lens(
            "rotation_economics",
            "SELL_REBUY",
            Decimal("80") if move > policy.minimum_range_move_ratio else Decimal("25"),
            Decimal("0.70"),
            "recovery:fee_slippage_adjusted_units",
        ),
    )


def _technical_lenses(
    candidate_range: TechnicalRecoveryRange,
    units: Decimal,
    blockers: tuple[str, ...],
    policy: RecoveryRadarPolicy,
    market_state: Mapping[str, object],
) -> tuple[RecoveryLensContribution, ...]:
    return (
        _lens(
            "support_resistance",
            "SELL_RESISTANCE_REBUY_SUPPORT",
            Decimal("85"),
            candidate_range.confidence,
            f"market_outlook:key_levels:{candidate_range.timeframe}",
        ),
        _lens(
            "range_amplitude",
            "SELL_REBUY",
            _threshold_score(
                candidate_range.range_move_ratio, policy.minimum_range_move_ratio
            ),
            Decimal("0.75"),
            "technical_range:amplitude",
        ),
        _lens(
            "trend_regime",
            "CONTEXT",
            candidate_range.confidence * Decimal("100"),
            candidate_range.confidence,
            "market_outlook:trend_regime",
        ),
        _lens(
            "pattern_setup",
            "CONTEXT",
            Decimal("70")
            if "market_outlook:setups_on_radar" in candidate_range.evidence_refs
            else Decimal("25"),
            Decimal("0.55"),
            "market_outlook:setups_on_radar",
        ),
        _lens(
            "inventory_context",
            "SELL_REBUY",
            Decimal("80") if units > ZERO else Decimal("0"),
            Decimal("0.80") if units > ZERO else Decimal("0"),
            "explicit_inventory_units",
        ),
        _lens(
            "validation_oos",
            "GATED",
            _blocker_clear_score(blockers, ("OOS", "BACKTEST", "WALK_FORWARD")),
            Decimal("0.65"),
            "validation_artifacts",
            "OOS_APPROVAL_MISSING" if any("OOS" in item for item in blockers) else "",
        ),
        _lens(
            "liquidity_execution",
            "GATED",
            _blocker_clear_score(blockers, ("ORDER_BOOK", "DEPTH", "CURRENT_PRICE")),
            Decimal("0.70"),
            "exchange_depth_current_price",
            "ORDER_BOOK_DEPTH_MISSING"
            if any("ORDER_BOOK" in item or "DEPTH" in item for item in blockers)
            else "",
        ),
        _lens(
            "mspacis_structure",
            "CONTEXT",
            _source_presence_score(
                market_state,
                (
                    "market_structure",
                    "price_action",
                    "candlestick_intelligence",
                    "key_levels",
                    "setups_on_radar",
                ),
            ),
            Decimal("0.60"),
            "market_outlook:mspacis",
            "MSPACIS_EVIDENCE_INCOMPLETE"
            if "MSPACIS_EVIDENCE_INCOMPLETE" in blockers
            else "",
        ),
        _lens(
            "relative_strength",
            "CONTEXT",
            _source_presence_score(
                market_state,
                (
                    "relative_strength",
                    "hot_btc_relative_strength",
                    "hot_eth_relative_strength",
                ),
            ),
            Decimal("0.55"),
            "market_outlook:relative_strength",
            "RELATIVE_STRENGTH_EVIDENCE_MISSING"
            if "RELATIVE_STRENGTH_EVIDENCE_MISSING" in blockers
            else "",
        ),
        _lens(
            "derivatives_supplement",
            "SUPPLEMENTARY",
            _source_presence_score(
                market_state,
                ("derivatives", "funding", "open_interest", "long_short_ratio"),
            ),
            Decimal("0.45"),
            "market_outlook:derivatives",
            "DERIVATIVES_SUPPLEMENT_MISSING"
            if "DERIVATIVES_SUPPLEMENT_MISSING" in blockers
            else "",
        ),
        _lens(
            "news_whale_risk",
            "RISK_CONTEXT",
            _source_presence_score(
                market_state,
                ("news", "social", "whale", "onchain", "market_context_events"),
            ),
            Decimal("0.45"),
            "market_outlook:news_whale",
            "NEWS_WHALE_RISK_UNVERIFIED"
            if "NEWS_WHALE_RISK_UNVERIFIED" in blockers
            else "",
        ),
    )


def _opportunity_lenses(
    item: Mapping[str, object],
    blockers: tuple[str, ...],
    score: Decimal,
    confidence: Decimal,
    market_state: Mapping[str, object],
) -> tuple[RecoveryLensContribution, ...]:
    direction = str(item.get("direction", "UNKNOWN")).upper()
    setup_name = str(item.get("setup_name", "UNKNOWN_SETUP"))
    return (
        _lens(
            "pattern_setup",
            direction,
            score,
            confidence,
            f"opportunity_inbox:{setup_name}",
        ),
        _lens(
            "validation_oos",
            "GATED",
            _blocker_clear_score(blockers, ("OOS", "BACKTEST", "WALK_FORWARD")),
            Decimal("0.75"),
            "validation_artifacts",
            "OOS_BLOCKER_PRESENT" if any("OOS" in item for item in blockers) else "",
        ),
        _lens(
            "risk_gate",
            "GATED",
            _blocker_clear_score(blockers, ("RISK", "EXECUTION")),
            Decimal("0.70"),
            "risk_execution_gate",
            "EXECUTION_NOT_ALLOWED" if "EXECUTION_NOT_ALLOWED" in blockers else "",
        ),
        _lens(
            "directional_clarity",
            direction,
            Decimal("65")
            if direction not in {"UNKNOWN", "NEUTRAL", ""}
            else Decimal("20"),
            Decimal("0.50"),
            "opportunity_inbox:direction",
            "DIRECTION_UNKNOWN" if direction in {"UNKNOWN", "NEUTRAL", ""} else "",
        ),
        _lens(
            "mspacis_structure",
            "CONTEXT",
            _source_presence_score(
                market_state,
                (
                    "market_structure",
                    "price_action",
                    "candlestick_intelligence",
                    "key_levels",
                    "setups_on_radar",
                ),
            ),
            Decimal("0.60"),
            "market_outlook:mspacis",
        ),
        _lens(
            "relative_strength",
            "CONTEXT",
            _source_presence_score(
                market_state,
                (
                    "relative_strength",
                    "hot_btc_relative_strength",
                    "hot_eth_relative_strength",
                ),
            ),
            Decimal("0.55"),
            "market_outlook:relative_strength",
        ),
        _lens(
            "derivatives_supplement",
            "SUPPLEMENTARY",
            _source_presence_score(
                market_state,
                ("derivatives", "funding", "open_interest", "long_short_ratio"),
            ),
            Decimal("0.45"),
            "market_outlook:derivatives",
        ),
        _lens(
            "news_whale_risk",
            "RISK_CONTEXT",
            _source_presence_score(
                market_state,
                ("news", "social", "whale", "onchain", "market_context_events"),
            ),
            Decimal("0.45"),
            "market_outlook:news_whale",
        ),
    )


def _market_intelligence_blockers(
    market_state: Mapping[str, object],
) -> tuple[str, ...]:
    """Surface missing IQ lenses without hiding the candidate itself."""
    blockers: list[str] = []
    if _source_presence_score(
        market_state,
        (
            "market_structure",
            "price_action",
            "candlestick_intelligence",
            "key_levels",
            "setups_on_radar",
        ),
    ) < Decimal("50"):
        blockers.append("MSPACIS_EVIDENCE_INCOMPLETE")
    if _source_presence_score(
        market_state,
        (
            "relative_strength",
            "hot_btc_relative_strength",
            "hot_eth_relative_strength",
        ),
    ) < Decimal("50"):
        blockers.append("RELATIVE_STRENGTH_EVIDENCE_MISSING")
    if _source_presence_score(
        market_state,
        ("derivatives", "funding", "open_interest", "long_short_ratio"),
    ) < Decimal("50"):
        blockers.append("DERIVATIVES_SUPPLEMENT_MISSING")
    if _source_presence_score(
        market_state,
        ("news", "social", "whale", "onchain", "market_context_events"),
    ) < Decimal("50"):
        blockers.append("NEWS_WHALE_RISK_UNVERIFIED")
    return tuple(blockers)


def _source_presence_score(
    market_state: Mapping[str, object],
    keys: tuple[str, ...],
) -> Decimal:
    if not keys:
        return ZERO
    present = sum(1 for key in keys if _has_context_value(market_state.get(key)))
    return Decimal(present) * Decimal("100") / Decimal(len(keys))


def _has_context_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, list | tuple):
        return bool(value)
    return True


def _lens(
    lens: str,
    direction: str,
    score: Decimal,
    confidence: Decimal,
    evidence_ref: str,
    blocker: str = "",
) -> RecoveryLensContribution:
    return RecoveryLensContribution(
        lens=lens,
        direction=direction,
        score=min(Decimal("100"), max(ZERO, score)),
        confidence=min(ONE, max(ZERO, confidence)),
        evidence_ref=evidence_ref,
        blocker=blocker,
    )


def _threshold_score(value: Decimal, threshold: Decimal) -> Decimal:
    if threshold <= ZERO:
        return Decimal("100")
    return min(Decimal("100"), (value / threshold) * Decimal("60"))


def _blocker_clear_score(
    blockers: tuple[str, ...],
    blocker_markers: tuple[str, ...],
) -> Decimal:
    return (
        Decimal("15")
        if any(marker in blocker for blocker in blockers for marker in blocker_markers)
        else Decimal("85")
    )


def _intelligence_score(
    lens_contributions: tuple[RecoveryLensContribution, ...],
) -> Decimal:
    if not lens_contributions:
        return ZERO
    weighted_scores = sorted(
        (
            contribution.score
            * (Decimal("0.5") + contribution.confidence / Decimal("2"))
            for contribution in lens_contributions
        ),
        reverse=True,
    )
    attention_set = tuple(weighted_scores[:4])
    weighted = sum(
        attention_set,
        ZERO,
    )
    return min(
        Decimal("200"),
        (weighted / Decimal(len(attention_set))) * Decimal("2"),
    )


def _opportunity_grade(score: Decimal, policy: RecoveryRadarPolicy) -> str:
    if score >= policy.action_candidate_score:
        return "A_REVIEW"
    if score >= policy.high_attention_score:
        return "B_REVIEW"
    if score >= Decimal("90"):
        return "C_REVIEW"
    return "RADAR_ONLY"


def _miss_risk(
    score: Decimal,
    blockers: tuple[str, ...],
    policy: RecoveryRadarPolicy,
) -> str:
    if score >= policy.action_candidate_score:
        return "HIGH"
    if score >= policy.high_attention_score:
        return "MEDIUM_HIGH"
    if any("TRIGGER" in blocker or "LEVEL_REACTION" in blocker for blocker in blockers):
        return "MEDIUM"
    return "LOW"


def _false_positive_risk(blockers: tuple[str, ...]) -> str:
    if any(
        marker in blocker
        for blocker in blockers
        for marker in (
            "OOS",
            "RISK",
            "ORDER_BOOK",
            "DEPTH",
            "TRIGGER",
            "CURRENT_PRICE",
            "EXECUTION",
        )
    ):
        return "HIGH"
    return "MEDIUM"


def _extract_inbox(payload: Mapping[str, object]) -> Mapping[str, object]:
    inbox = payload.get("inbox")
    if isinstance(inbox, OpportunityInbox):
        return {
            "symbol": inbox.symbol,
            "items": inbox.items,
            "blockers": inbox.blockers,
        }
    return _mapping(inbox)


def _extract_market_state(payload: Mapping[str, object]) -> Mapping[str, object]:
    market_state = payload.get("market_state")
    if isinstance(market_state, Mapping):
        return market_state
    return {}


def _zone_lower(value: object) -> Decimal:
    zone = _mapping(value)
    return _decimal(zone.get("lower"), ZERO)


def _zone_upper(value: object) -> Decimal:
    zone = _mapping(value)
    return _decimal(zone.get("upper"), ZERO)


def _technical_range_confidence(
    market_state: Mapping[str, object],
    timeframe: str,
) -> Decimal:
    confidence = Decimal("0.20")
    if str(market_state.get("market_regime", "")).strip():
        confidence += Decimal("0.05")
    if str(market_state.get("pro_trend_direction", "")).strip():
        confidence += Decimal("0.05")
    biases = tuple(
        _mapping(item) for item in _sequence(market_state.get("timeframe_biases"))
    )
    matching_bias = next(
        (
            bias
            for bias in biases
            if str(bias.get("timeframe", "")).strip() == timeframe
        ),
        None,
    )
    if matching_bias is not None:
        confidence += min(
            Decimal("0.15"), _confidence_decimal(matching_bias.get("confidence"))
        )
    if _sequence(market_state.get("setups_on_radar")):
        confidence += Decimal("0.10")
    return min(Decimal("0.60"), confidence)


def _technical_range_evidence_refs(
    market_state: Mapping[str, object],
    timeframe: str,
) -> tuple[str, ...]:
    refs = [
        f"market_outlook:key_levels:{timeframe}",
        "technical:rolling_support_resistance",
    ]
    if str(market_state.get("market_regime", "")).strip():
        refs.append("market_outlook:market_regime")
    if str(market_state.get("pro_trend_direction", "")).strip():
        refs.append("market_outlook:pro_trend_direction")
    if _sequence(market_state.get("timeframe_biases")):
        refs.append("market_outlook:timeframe_biases")
    if _sequence(market_state.get("setups_on_radar")):
        refs.append("market_outlook:setups_on_radar")
    refs.append("MSPACIS:pending_explicit_contract")
    return tuple(dict.fromkeys(refs))


def _timeframe_rank(timeframe: str) -> int:
    return {
        "15m": 0,
        "1h": 1,
        "4h": 2,
        "1d": 3,
    }.get(timeframe, 99)


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, OpportunityInboxItem):
        return {
            "market": value.market,
            "symbol": value.symbol,
            "setup_name": value.setup_name,
            "timeframe": value.timeframe,
            "direction": value.direction,
            "source": value.source,
            "status": value.status,
            "promotion_status": value.promotion_status,
            "score": value.score,
            "confidence": value.confidence,
            "blockers": value.blockers,
        }
    return {}


def _sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, list | tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _score_decimal(value: object) -> Decimal:
    parsed = _decimal(value, ZERO)
    if ZERO <= parsed <= ONE:
        return parsed * Decimal("100")
    return min(Decimal("100"), max(ZERO, parsed))


def _confidence_decimal(value: object) -> Decimal:
    return min(ONE, max(ZERO, _decimal(value, ZERO)))


def _positive_decimal(value: object, name: str) -> Decimal:
    parsed = _decimal(value, ZERO)
    if parsed <= ZERO:
        raise ValueError(f"{name} must be positive")
    return parsed


def _optional_positive_decimal(value: object | None, name: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return _positive_decimal(value, name)


def _decimal(value: object, default: Decimal) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default
    return parsed if parsed.is_finite() else default


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blanks")

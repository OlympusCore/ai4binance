"""Fail-closed, research-only opportunity observations.

This module does not generate production signals and has no execution authority.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from math import isfinite
from pathlib import Path
from typing import cast

from ai4binance.domain.opportunity_observation import (
    OpportunityLifecycleState,
)
from ai4binance.infrastructure.filesystem import (
    load_optional_json_mapping,
)
from ai4binance.opportunity_policy import count_opportunity_grades
from ai4binance.strategies.registry import build_playbook_registry
from ai4binance.strategies.rules import setup_pattern_type
from ai4binance.validation.summary import ValidationSummary, ValidationSummaryReader

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class OpportunityInboxItem:
    """Visible opportunity or validation item that remains review-only."""

    market: str
    symbol: str
    setup_name: str
    timeframe: str
    direction: str
    source: str
    status: str
    promotion_status: str
    score: float
    confidence: float
    blockers: tuple[str, ...]
    lifecycle_state: OpportunityLifecycleState | str = (
        OpportunityLifecycleState.WATCH_ONLY
    )
    target_risk_reward: Decimal = Decimal("2")
    stretch_risk_reward: Decimal = Decimal("3")
    score_basis: str = "OPPORTUNITY_QUALITY_SCORE_0_100"
    expected_return: float | None = None
    score_components: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    why_now: tuple[str, ...] = field(default_factory=tuple)
    supporting_evidence: tuple[str, ...] = field(default_factory=tuple)
    counter_evidence: tuple[str, ...] = field(default_factory=tuple)
    confirmation_requirements: tuple[str, ...] = field(default_factory=tuple)
    promotion_requirements: tuple[str, ...] = field(default_factory=tuple)
    discovery_blockers: tuple[str, ...] = field(default_factory=tuple)
    execution_blockers: tuple[str, ...] = field(default_factory=tuple)
    next_evidence_action: str = "KEEP_RESEARCH_RADAR_RUNNING"
    entry: str = "PENDING_VALIDATED_LEVEL"
    stop_loss: str = "PENDING_VALIDATED_LEVEL"
    tp1: str = "PENDING_VALIDATED_LEVEL"
    tp2: str = "PENDING_VALIDATED_LEVEL"
    tp3: str = "PENDING_VALIDATED_LEVEL"
    semantic_key: str = ""
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    pattern_type: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "market",
            "symbol",
            "setup_name",
            "timeframe",
            "direction",
            "source",
            "status",
            "promotion_status",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.target_risk_reward <= ZERO:
            raise ValueError("target risk/reward must be positive")
        if self.stretch_risk_reward < self.target_risk_reward:
            raise ValueError("stretch risk/reward cannot be below target")
        if self.pattern_type is not None and not self.pattern_type.strip():
            raise ValueError("pattern_type cannot be blank")
        if not isfinite(self.score) or not 0.0 <= self.score <= 100.0:
            raise ValueError("opportunity score must be 0..100")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("opportunity confidence must be 0..1")
        if not self.score_basis.strip():
            raise ValueError("opportunity score basis is required")
        if not self.next_evidence_action.strip():
            raise ValueError("opportunity next evidence action is required")
        for trade_plan_value in (
            self.entry,
            self.stop_loss,
            self.tp1,
            self.tp2,
            self.tp3,
        ):
            if not trade_plan_value.strip():
                raise ValueError("opportunity trade plan fields are required")
        if self.expected_return is not None and not isfinite(self.expected_return):
            raise ValueError("opportunity expected return must be finite")
        for name, component_value in self.score_components:
            if not name.strip():
                raise ValueError("opportunity score component name is required")
            if not isfinite(component_value) or not 0.0 <= component_value <= 100.0:
                raise ValueError("opportunity score components must be 0..100")
        for values in (
            self.why_now,
            self.supporting_evidence,
            self.counter_evidence,
            self.confirmation_requirements,
            self.promotion_requirements,
            self.discovery_blockers,
            self.execution_blockers,
        ):
            if len(set(values)) != len(values) or any(
                not item.strip() for item in values
            ):
                raise ValueError("opportunity evidence and gate lists must be unique")
        lifecycle_state = _coerce_lifecycle_state(self.lifecycle_state)
        if lifecycle_state is OpportunityLifecycleState.PAPER_ELIGIBLE:
            if self.blockers:
                raise ValueError("PAPER_ELIGIBLE opportunity cannot contain blockers")
            if self.promotion_status != "STAGED_CANDIDATE":
                raise ValueError(
                    "PAPER_ELIGIBLE opportunity requires staged validation evidence"
                )
            if self.status not in {"READY", "PAPER_ELIGIBLE"}:
                raise ValueError("PAPER_ELIGIBLE opportunity requires ready status")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity inbox item cannot grant execution authority")
        object.__setattr__(self, "lifecycle_state", lifecycle_state)
        if not self.semantic_key:
            object.__setattr__(self, "semantic_key", _semantic_key(self))


@dataclass(frozen=True, slots=True)
class OpportunityInbox:
    """Bounded user-facing view of Spot/Futures opportunity evidence."""

    symbol: str
    items: tuple[OpportunityInboxItem, ...]
    validation_summary: ValidationSummary
    blockers: tuple[str, ...]
    generation_status: str = "DEGRADED"
    research_blockers: tuple[str, ...] = field(default_factory=tuple)
    promotion_requirements: tuple[str, ...] = field(default_factory=tuple)
    execution_blockers: tuple[str, ...] = field(default_factory=tuple)
    next_safe_actions: tuple[str, ...] = field(default_factory=tuple)
    funnel_counts: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    research_loop_allowed: bool = True
    opportunity_generation_allowed: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("opportunity inbox symbol is required")
        if self.generation_status not in {"ACTIVE", "DEGRADED"}:
            raise ValueError("opportunity generation status is invalid")
        if not self.research_loop_allowed or not self.opportunity_generation_allowed:
            raise ValueError("opportunity inbox must keep research generation enabled")
        if self.generation_status == "DEGRADED" and any(
            item.lifecycle_state is OpportunityLifecycleState.PAPER_ELIGIBLE
            for item in self.items
        ):
            raise ValueError("degraded opportunity inbox cannot contain paper eligible")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("opportunity inbox cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class OpportunityInboxBuilder:
    """Merge market radar and validation summaries without weakening gates."""

    validation_reader: ValidationSummaryReader
    market_outlook_path: Path
    radar_snapshot_path: Path | None = None
    max_items: int = 20

    def __post_init__(self) -> None:
        if self.max_items < 1:
            raise ValueError("opportunity inbox max_items must be positive")

    def build(self, symbol: str) -> OpportunityInbox:
        normalized = symbol.strip().upper()
        validation = self.validation_reader.summarize(normalized)
        research_blockers: list[str] = []
        execution_blockers: list[str] = list(validation.blockers)
        items: list[OpportunityInboxItem] = []
        market_state = self._market_state()
        if market_state is None:
            research_blockers.append("MARKET_OUTLOOK_UNAVAILABLE")
        elif (
            market_symbol := _market_state_symbol(market_state)
        ) and market_symbol != normalized:
            blocker = f"MARKET_OUTLOOK_SYMBOL_MISMATCH:{market_symbol}!={normalized}"
            research_blockers.append(blocker)
            execution_blockers.append(blocker)
        else:
            items.extend(self._market_items(normalized, market_state))
            execution_blockers.extend(
                str(item) for item in _object_tuple(market_state.get("blockers"))
            )
        radar_state = self._radar_state()
        if radar_state is not None:
            items.extend(self._radar_items(normalized, radar_state))
            execution_blockers.extend(
                str(item) for item in _object_tuple(radar_state.get("blockers"))
            )
        items.extend(self._validation_items(validation))
        visible_items = _deduplicate_items(tuple(items))
        if not items:
            research_blockers.append("NO_VISIBLE_OPPORTUNITY_EVIDENCE")
        if not any(_is_ready_execution_candidate(item) for item in visible_items):
            execution_blockers.append("NO_READY_CANDIDATE")
        promotion_requirements = tuple(
            dict.fromkeys(
                requirement
                for item in visible_items
                for requirement in item.promotion_requirements
            )
        )
        blockers = tuple(dict.fromkeys((*research_blockers, *execution_blockers)))
        return OpportunityInbox(
            normalized,
            visible_items[: self.max_items],
            validation,
            blockers,
            generation_status="ACTIVE" if visible_items else "DEGRADED",
            research_blockers=tuple(dict.fromkeys(research_blockers)),
            promotion_requirements=promotion_requirements,
            execution_blockers=tuple(dict.fromkeys(execution_blockers)),
            next_safe_actions=_next_safe_actions(
                tuple(dict.fromkeys((*blockers, *promotion_requirements)))
            ),
            funnel_counts=_funnel_counts(visible_items),
        )

    def _market_state(self) -> Mapping[str, object] | None:
        return load_optional_json_mapping(self.market_outlook_path)

    def _radar_state(self) -> Mapping[str, object] | None:
        if self.radar_snapshot_path is None:
            return None
        return load_optional_json_mapping(self.radar_snapshot_path)

    @staticmethod
    def _market_items(
        symbol: str,
        state: Mapping[str, object],
    ) -> tuple[OpportunityInboxItem, ...]:
        setups = _object_tuple(state.get("setups_on_radar"))
        blockers = tuple(str(item) for item in _object_tuple(state.get("blockers")))
        direction = str(state.get("pro_trend_direction", "UNKNOWN"))
        status = str(state.get("status", "PARTIAL"))
        if not setups:
            return ()
        return tuple(
            _market_item(symbol, setup, blockers, direction, status) for setup in setups
        )

    @staticmethod
    def _validation_items(
        validation: ValidationSummary,
    ) -> tuple[OpportunityInboxItem, ...]:
        ordered = sorted(
            validation.runs,
            key=lambda run: (
                run.promotion_status != "STAGED_CANDIDATE",
                len(run.blockers),
                run.timeframe,
                run.playbook,
            ),
        )
        items: list[OpportunityInboxItem] = []
        for run in ordered:
            blockers = tuple(dict.fromkeys(run.blockers))
            score_components = _validation_score_components(run, blockers)
            playbook = run.playbook
            items.append(
                OpportunityInboxItem(
                    market="SPOT",
                    symbol=validation.symbol,
                    setup_name=playbook,
                    pattern_type=setup_pattern_type(playbook),
                    timeframe=run.timeframe,
                    direction="UNKNOWN",
                    source="validation_summary",
                    status=(
                        "READY"
                        if run.promotion_status == "STAGED_CANDIDATE"
                        and not blockers
                        and _is_implemented_playbook(playbook)
                        else "WATCHLIST"
                    ),
                    promotion_status=(
                        run.promotion_status
                        if (
                            run.promotion_status == "STAGED_CANDIDATE"
                            and not blockers
                            and _is_implemented_playbook(playbook)
                        )
                        else "RESEARCH_ONLY"
                    ),
                    score=_validation_opportunity_score(score_components),
                    confidence=max(
                        0.0,
                        1.0 - _metric(run.metrics, "bootstrap_probability_of_loss"),
                    ),
                    blockers=blockers,
                    lifecycle_state=_validation_lifecycle_state(
                        playbook,
                        run,
                        blockers,
                    ),
                    score_basis="VALIDATION_EVIDENCE_QUALITY_SCORE_0_100",
                    expected_return=_metric(run.metrics, "net_return"),
                    score_components=score_components,
                    why_now=("VALIDATION_RUN_CARD_AVAILABLE",),
                    supporting_evidence=run.artifact_paths,
                    counter_evidence=blockers,
                    promotion_requirements=_validation_promotion_requirements(
                        run,
                        blockers,
                    ),
                    execution_blockers=("LIVE_ORDER_BLOCKED",),
                    next_evidence_action=(
                        "RUN_VALIDATION_QUEUE"
                        if blockers
                        else "PREPARE_VIRTUAL_MARKET_AUTONOMOUS_REVIEW"
                    ),
                )
            )
        return tuple(items)

    @staticmethod
    def _radar_items(
        symbol: str,
        state: Mapping[str, object],
    ) -> tuple[OpportunityInboxItem, ...]:
        items: list[OpportunityInboxItem] = []
        market_wide = symbol in {"MARKET_WIDE", "ALL"}
        for raw_item in _object_tuple(state.get("candidate_states")):
            if not isinstance(raw_item, Mapping):
                continue
            item = cast(Mapping[str, object], raw_item)
            item_symbol = str(item.get("symbol", "")).strip().upper()
            if not item_symbol:
                continue
            if not market_wide and item_symbol != symbol:
                continue
            items.append(_radar_item(item))
        return tuple(items)


def _metric(metrics: tuple[tuple[str, float], ...], name: str) -> float:
    return next((value for key, value in metrics if key == name), 0.0)


def _validation_score_components(
    run: object,
    blockers: tuple[str, ...],
) -> tuple[tuple[str, float], ...]:
    promotion_score = (
        75.0
        if str(getattr(run, "promotion_status", "")) == "STAGED_CANDIDATE"
        else 55.0
    )
    blocker_score = max(0.0, 100.0 - float(len(blockers) * 15))
    confidence_score = max(
        0.0,
        min(
            100.0,
            (
                1.0
                - _metric(
                    getattr(run, "metrics", ()),
                    "bootstrap_probability_of_loss",
                )
            )
            * 100.0,
        ),
    )
    return (
        ("promotion_evidence", promotion_score),
        ("blocker_clearance", blocker_score),
        ("loss_uncertainty", confidence_score),
    )


def _validation_opportunity_score(
    components: tuple[tuple[str, float], ...],
) -> float:
    if not components:
        return 0.0
    weights = {
        "promotion_evidence": 0.45,
        "blocker_clearance": 0.35,
        "loss_uncertainty": 0.20,
    }
    return round(
        sum(value * weights.get(name, 0.0) for name, value in components),
        4,
    )


def _is_ready_execution_candidate(item: OpportunityInboxItem) -> bool:
    return (
        item.status == "READY"
        and item.promotion_status == "STAGED_CANDIDATE"
        and not item.blockers
        and item.score >= 60.0
        and item.confidence >= 0.5
    )


def _coerce_lifecycle_state(
    value: OpportunityLifecycleState | str,
) -> OpportunityLifecycleState:
    try:
        return OpportunityLifecycleState(value)
    except ValueError as exc:
        raise ValueError("opportunity lifecycle state is invalid") from exc


def _validation_lifecycle_state(
    playbook: str,
    run: object,
    blockers: tuple[str, ...],
) -> OpportunityLifecycleState:
    if not _is_implemented_playbook(playbook):
        return OpportunityLifecycleState.WATCH_ONLY
    promotion_status = str(getattr(run, "promotion_status", "")).strip()
    if promotion_status == "STAGED_CANDIDATE" and not blockers:
        return OpportunityLifecycleState.PAPER_ELIGIBLE
    if any(_is_missing_confirmation_blocker(blocker) for blocker in blockers):
        return OpportunityLifecycleState.CONFIRMATION_PENDING
    return OpportunityLifecycleState.WATCH_ONLY


def _validation_promotion_requirements(
    run: object,
    blockers: tuple[str, ...],
) -> tuple[str, ...]:
    requirements = list(blockers)
    if str(getattr(run, "promotion_status", "")).strip() != "STAGED_CANDIDATE":
        requirements.append("VALIDATION_GATE_REQUIRED")
    return tuple(dict.fromkeys(requirements))


@lru_cache(maxsize=1)
def _implemented_playbook_names() -> tuple[str, ...]:
    return tuple(
        playbook.name
        for playbook in build_playbook_registry().playbooks
        if playbook.implemented
    )


def _is_implemented_playbook(playbook: str) -> bool:
    return playbook.strip() in _implemented_playbook_names()


def _market_lifecycle_state(
    setup: Mapping[str, object],
    blockers: tuple[str, ...],
    status: str,
) -> OpportunityLifecycleState:
    explicit = setup.get("lifecycle_state")
    if isinstance(explicit, str) and explicit.strip():
        explicit_state = _coerce_lifecycle_state(explicit.strip().upper())
        if explicit_state is not OpportunityLifecycleState.PAPER_ELIGIBLE:
            return explicit_state
    if any(_is_missing_confirmation_blocker(blocker) for blocker in blockers):
        return OpportunityLifecycleState.CONFIRMATION_PENDING
    normalized_status = status.strip().upper()
    if normalized_status in {"WAIT_FOR_RETEST", "CONFIRMATION_PENDING"}:
        return OpportunityLifecycleState.CONFIRMATION_PENDING
    if normalized_status == "SETUP_FORMING":
        return OpportunityLifecycleState.SETUP_FORMING
    return OpportunityLifecycleState.WATCH_ONLY


def _semantic_key(item: OpportunityInboxItem) -> str:
    return ":".join(
        (
            item.market.strip().upper(),
            item.symbol.strip().upper(),
            item.timeframe.strip().upper(),
            item.setup_name.strip().lower(),
            item.direction.strip().upper(),
        )
    )


def _deduplicate_items(
    items: tuple[OpportunityInboxItem, ...],
) -> tuple[OpportunityInboxItem, ...]:
    selected: dict[str, OpportunityInboxItem] = {}
    order: list[str] = []
    for item in items:
        key = item.semantic_key
        current = selected.get(key)
        if current is None:
            selected[key] = item
            order.append(key)
            continue
        if _dedup_rank(item) > _dedup_rank(current):
            selected[key] = item
    return tuple(selected[key] for key in order)


def _dedup_rank(item: OpportunityInboxItem) -> tuple[float, float, int]:
    source_priority = 1 if item.source == "validation_summary" else 0
    return (item.score, item.confidence, source_priority)


def _funnel_counts(
    items: tuple[OpportunityInboxItem, ...],
) -> tuple[tuple[str, int], ...]:
    lifecycle_counts = {
        "visible_count": len(items),
        "watch_only_count": 0,
        "setup_forming_count": 0,
        "confirmation_pending_count": 0,
        "paper_eligible_count": 0,
        "blocked_visible_count": 0,
    }
    for item in items:
        if item.blockers:
            lifecycle_counts["blocked_visible_count"] += 1
        if item.lifecycle_state is OpportunityLifecycleState.WATCH_ONLY:
            lifecycle_counts["watch_only_count"] += 1
        elif item.lifecycle_state is OpportunityLifecycleState.SETUP_FORMING:
            lifecycle_counts["setup_forming_count"] += 1
        elif item.lifecycle_state is OpportunityLifecycleState.CONFIRMATION_PENDING:
            lifecycle_counts["confirmation_pending_count"] += 1
        elif item.lifecycle_state is OpportunityLifecycleState.PAPER_ELIGIBLE:
            lifecycle_counts["paper_eligible_count"] += 1
    grade_counts = count_opportunity_grades(Decimal(str(item.score)) for item in items)
    return (*lifecycle_counts.items(), *grade_counts.items())


def _is_missing_confirmation_blocker(blocker: str) -> bool:
    return blocker in {
        "ENTRY_TRIGGER_MISSING",
        "VWAP_TRIGGER_MISSING",
        "VOLUME_CONFIRMATION_MISSING",
        "STRUCTURE_CONFIRMATION_REQUIRED",
        "HTF_CONFIRMATION_REQUIRED",
    }


def _next_safe_actions(blockers: tuple[str, ...]) -> tuple[str, ...]:
    actions: list[str] = []
    for blocker in blockers:
        action = _safe_action_for_blocker(blocker)
        if action:
            actions.append(action)
    if not actions:
        actions.append("KEEP_RESEARCH_RADAR_RUNNING")
    return tuple(dict.fromkeys(actions))


def _safe_action_for_blocker(blocker: str) -> str:
    if blocker.startswith("MARKET_OUTLOOK_SYMBOL_MISMATCH:"):
        return "RUN_SYMBOL_SCOPED_ANALYZE_PUBLIC"
    if blocker in {
        "MARKET_OUTLOOK_UNAVAILABLE",
        "NO_VISIBLE_OPPORTUNITY_EVIDENCE",
    }:
        return "RUN_ANALYZE_PUBLIC"
    if blocker in {
        "VALIDATION_ARTIFACTS_UNAVAILABLE",
        "VALIDATION_RUN_CARDS_UNAVAILABLE",
        "VALIDATION_GATE_REQUIRED",
        "BACKTEST_APPROVAL_MISSING",
        "WALK_FORWARD_APPROVAL_MISSING",
        "OOS_APPROVAL_MISSING",
        "LOW_OOS_TRADE_COUNT",
        "WEAK_OOS_FOLD_CONSISTENCY",
        "COST_STRESS_RETURN_NOT_POSITIVE",
        "BOOTSTRAP_LOSS_PROBABILITY_HIGH",
    }:
        return "RUN_VALIDATION_QUEUE"
    if blocker == "NO_READY_CANDIDATE":
        return "PLAN_NEXT_EVIDENCE_REFRESH"
    if "ORDER_BOOK" in blocker or "DEPTH" in blocker:
        return "REFRESH_LIQUIDITY_AND_DEPTH_EVIDENCE"
    if "WHALE" in blocker:
        return "RUN_WHALE_FUSION_RESEARCH"
    if "EXTERNAL" in blocker or "SOCIAL" in blocker or "NEWS" in blocker:
        return "COLLECT_SOURCED_EXTERNAL_EVIDENCE"
    if blocker == "DEPENDENCY_NOT_READY:derivatives":
        return "REFRESH_DERIVATIVES_RESEARCH"
    if blocker == "TRADE_CANDIDATE_AND_RISK_PLAN_MISSING":
        return "BUILD_CANDIDATE_RISK_PLAN"
    if "RISK_APPROVAL" in blocker:
        return "PREPARE_RISK_REVIEW"
    if blocker == "HIGH_IMPACT_DATA_UNAVAILABLE":
        return "COLLECT_HIGH_IMPACT_EVENT_CONTEXT"
    if blocker == "MACRO_CYCLE_EVIDENCE_UNAVAILABLE":
        return "REFRESH_MACRO_CYCLE_CONTEXT"
    if blocker in {
        "TPO_AUCTION_PROFILE_NOT_IMPLEMENTED",
        "COMPOSITE_BALANCE_AREAS_NOT_IMPLEMENTED",
    }:
        return "STAGE_MARKET_PROFILE_RESEARCH"
    return "REVIEW_BLOCKER:" + blocker


def _pattern_type_value(
    value: object,
    *,
    fallback_setup_name: str,
) -> str | None:
    if value is not None:
        text = str(value).strip()
        if text:
            return text
    return setup_pattern_type(fallback_setup_name)


def _market_item(
    symbol: str,
    setup: object,
    state_blockers: tuple[str, ...],
    fallback_direction: str,
    fallback_status: str,
) -> OpportunityInboxItem:
    if isinstance(setup, Mapping):
        setup_blockers = tuple(
            str(item) for item in _object_tuple(setup.get("blockers"))
        )
        all_blockers = tuple(
            dict.fromkeys(
                (*state_blockers, *setup_blockers, "VALIDATION_GATE_REQUIRED")
            )
        )
        discovery_blockers = _discovery_blockers(all_blockers)
        confirmation_requirements = _confirmation_requirements(all_blockers)
        promotion_requirements = _promotion_requirements(all_blockers)
        execution_blockers = _execution_blockers(all_blockers)
        blockers = tuple(
            dict.fromkeys((*discovery_blockers, *confirmation_requirements))
        )
        status = str(setup.get("status", fallback_status))
        return OpportunityInboxItem(
            market="SPOT",
            symbol=symbol,
            setup_name=str(setup.get("setup_name", "UNKNOWN_SETUP")),
            pattern_type=_pattern_type_value(
                setup.get("pattern_type"),
                fallback_setup_name=str(setup.get("setup_name", "UNKNOWN_SETUP")),
            ),
            timeframe=str(setup.get("timeframe", "MULTI_TF")),
            direction=str(setup.get("direction", fallback_direction)),
            source="market_outlook",
            status=status,
            promotion_status=str(setup.get("promotion_status", "RESEARCH_ONLY")),
            score=float(setup.get("score", 0.0)),
            confidence=float(setup.get("confidence", 0.0)),
            blockers=blockers,
            lifecycle_state=_market_lifecycle_state(setup, blockers, status),
            why_now=_text_tuple(setup.get("why_now"))
            or ("MARKET_OUTLOOK_SETUP_ON_RADAR",),
            supporting_evidence=_text_tuple(setup.get("supporting_evidence"))
            or ("market-outlook/runtime-state.json",),
            counter_evidence=tuple(
                dict.fromkeys((*confirmation_requirements, *promotion_requirements))
            ),
            confirmation_requirements=confirmation_requirements,
            promotion_requirements=promotion_requirements,
            discovery_blockers=discovery_blockers,
            execution_blockers=execution_blockers,
            next_evidence_action=_next_safe_actions(
                tuple(
                    dict.fromkeys((*confirmation_requirements, *promotion_requirements))
                )
            )[0],
        )
    all_blockers = tuple(dict.fromkeys((*state_blockers, "VALIDATION_GATE_REQUIRED")))
    promotion_requirements = _promotion_requirements(all_blockers)
    return OpportunityInboxItem(
        market="SPOT",
        symbol=symbol,
        setup_name=str(setup),
        pattern_type=setup_pattern_type(str(setup)),
        timeframe="MULTI_TF",
        direction=fallback_direction,
        source="market_outlook",
        status=fallback_status,
        promotion_status="RESEARCH_ONLY",
        score=0.0,
        confidence=0.0,
        blockers=_discovery_blockers(all_blockers),
        promotion_requirements=promotion_requirements,
        execution_blockers=_execution_blockers(all_blockers),
        next_evidence_action=_next_safe_actions(promotion_requirements)[0],
    )


def _radar_item(item: Mapping[str, object]) -> OpportunityInboxItem:
    blockers = _text_tuple(item.get("blockers"))
    confirmation_requirements = _text_tuple(item.get("confirmation_requirements"))
    promotion_requirements = _text_tuple(item.get("promotion_requirements"))
    execution_blockers = tuple(
        dict.fromkeys(
            (*_text_tuple(item.get("execution_blockers")), "LIVE_ORDER_BLOCKED")
        )
    )
    next_action = str(
        item.get(
            "next_evidence_action",
            _next_safe_actions(
                tuple(
                    dict.fromkeys(
                        (
                            *blockers,
                            *confirmation_requirements,
                            *promotion_requirements,
                            *execution_blockers,
                        )
                    )
                )
            )[0],
        )
    )
    return OpportunityInboxItem(
        market=str(item.get("market", "SPOT")),
        symbol=str(item.get("symbol", "UNKNOWN")).strip().upper(),
        setup_name=str(item.get("setup_name", "UNKNOWN_SETUP")),
        pattern_type=_pattern_type_value(
            item.get("pattern_type"),
            fallback_setup_name=str(item.get("setup_name", "UNKNOWN_SETUP")),
        ),
        timeframe=str(item.get("timeframe", "UNSPECIFIED")),
        direction=str(item.get("direction", "WATCH_ONLY")),
        source="opportunity_radar_snapshot",
        status=str(item.get("status", "WATCHLIST")),
        promotion_status=str(item.get("promotion_status", "RESEARCH_ONLY")),
        score=_float_0_100(item.get("score")),
        confidence=_float_0_1(item.get("confidence")),
        blockers=blockers,
        target_risk_reward=_positive_decimal(
            item.get("target_risk_reward"),
            default=Decimal("2"),
        ),
        score_basis="CANONICAL_RADAR_EVIDENCE_SCORE_0_100",
        why_now=_text_tuple(item.get("why_now")),
        supporting_evidence=_text_tuple(item.get("supporting_evidence")),
        counter_evidence=_text_tuple(item.get("counter_evidence")),
        confirmation_requirements=confirmation_requirements,
        promotion_requirements=promotion_requirements,
        discovery_blockers=_discovery_blockers(blockers),
        execution_blockers=execution_blockers,
        next_evidence_action=next_action,
        entry=str(item.get("entry", "PENDING_VALIDATED_LEVEL")),
        stop_loss=str(item.get("stop_loss", "PENDING_VALIDATED_LEVEL")),
        tp1=str(item.get("tp1", "PENDING_VALIDATED_LEVEL")),
        tp2=str(item.get("tp2", "PENDING_VALIDATED_LEVEL")),
        tp3=str(item.get("tp3", "PENDING_VALIDATED_LEVEL")),
        semantic_key=str(item.get("semantic_key", "")),
    )


def _object_tuple(value: object) -> tuple[object, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    return tuple(
        str(item).strip() for item in _object_tuple(value) if str(item).strip()
    )


def _float_0_100(value: object) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    if not isfinite(number):
        return 0.0
    return max(0.0, min(100.0, number))


def _float_0_1(value: object) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    if not isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _positive_decimal(value: object, *, default: Decimal) -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception:
        return default
    if not number.is_finite() or number <= ZERO:
        return default
    return number


def _confirmation_requirements(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        blocker for blocker in blockers if _is_missing_confirmation_blocker(blocker)
    )


def _promotion_requirements(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        blocker
        for blocker in blockers
        if blocker == "VALIDATION_GATE_REQUIRED"
        or "OOS" in blocker
        or "BACKTEST" in blocker
        or "WALK_FORWARD" in blocker
        or "VALIDATION" in blocker
        or "PAPER_VALIDATION" in blocker
        or "PARAMETER_PROMOTION" in blocker
    )


def _execution_blockers(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        blocker
        for blocker in blockers
        if blocker in {"NO_READY_CANDIDATE", "LIVE_ORDER_BLOCKED"}
        or "RISK_APPROVAL" in blocker
    )


def _discovery_blockers(blockers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        blocker
        for blocker in blockers
        if blocker not in _confirmation_requirements(blockers)
        and blocker not in _promotion_requirements(blockers)
        and blocker not in _execution_blockers(blockers)
    )


def _market_state_symbol(state: Mapping[str, object]) -> str:
    value = str(state.get("symbol", "")).strip().upper()
    if value and value not in {"UNKNOWN", "UNAVAILABLE", "MARKET_WIDE", "ALL"}:
        return value
    return ""

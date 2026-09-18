"""Opportunity Radar V2 report contract.

The report is visibility-only. It does not grant paper, live, or order
execution authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from ai4binance.opportunity_policy import classify_opportunity_grade
from ai4binance.strategies.rules import setup_pattern_type


@dataclass(frozen=True, slots=True)
class OpportunityGap:
    layer: str
    code: str
    next_safe_action: str

    def to_payload(self) -> dict[str, str]:
        return {
            "layer": self.layer,
            "code": self.code,
            "next_safe_action": self.next_safe_action,
        }


@dataclass(frozen=True, slots=True)
class OpportunityNextAction:
    action: str
    authority_boundary: str = "RESEARCH_ONLY"

    def to_payload(self) -> dict[str, str]:
        return {
            "action": self.action,
            "authority_boundary": self.authority_boundary,
        }


@dataclass(frozen=True, slots=True)
class OpportunityCandidateView:
    symbol: str
    market: str
    timeframe: str
    setup_name: str
    direction: str
    lifecycle_state: str
    grade: str
    score: Decimal
    confidence: Decimal
    why_visible: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    discovery_blockers: tuple[str, ...]
    confirmation_gaps: tuple[str, ...]
    validation_gaps: tuple[str, ...]
    promotion_requirements: tuple[str, ...]
    execution_blockers: tuple[str, ...]
    next_safe_action: str
    upgrade_condition: str
    invalidation_condition: str
    accepted: bool = True
    pattern_type: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "timeframe": self.timeframe,
            "setup_name": self.setup_name,
            "pattern_type": self.pattern_type or setup_pattern_type(self.setup_name),
            "direction": self.direction,
            "lifecycle_state": self.lifecycle_state,
            "grade": self.grade,
            "score": self.score,
            "confidence": self.confidence,
            "why_visible": self.why_visible,
            "supporting_evidence": self.supporting_evidence,
            "counter_evidence": self.counter_evidence,
            "discovery_blockers": self.discovery_blockers,
            "confirmation_gaps": self.confirmation_gaps,
            "validation_gaps": self.validation_gaps,
            "promotion_requirements": self.promotion_requirements,
            "execution_blockers": self.execution_blockers,
            "next_safe_action": self.next_safe_action,
            "upgrade_condition": self.upgrade_condition,
            "invalidation_condition": self.invalidation_condition,
            "accepted": self.accepted,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class OpportunitySection:
    name: str
    candidates: tuple[OpportunityCandidateView, ...] = field(default_factory=tuple)

    def to_payload(self) -> tuple[dict[str, object], ...]:
        return tuple(candidate.to_payload() for candidate in self.candidates)


@dataclass(frozen=True, slots=True)
class OpportunitySnapshotDiff:
    previous_snapshot_id: str | None
    current_snapshot_id: str
    new_candidates: tuple[str, ...] = ()
    upgraded_candidates: tuple[str, ...] = ()
    downgraded_candidates: tuple[str, ...] = ()
    expired_candidates: tuple[str, ...] = ()
    cleared_blockers: tuple[str, ...] = ()
    new_blockers: tuple[str, ...] = ()
    still_pending: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "previous_snapshot_id": self.previous_snapshot_id,
            "current_snapshot_id": self.current_snapshot_id,
            "new_candidates": self.new_candidates,
            "upgraded_candidates": self.upgraded_candidates,
            "downgraded_candidates": self.downgraded_candidates,
            "expired_candidates": self.expired_candidates,
            "cleared_blockers": self.cleared_blockers,
            "new_blockers": self.new_blockers,
            "still_pending": self.still_pending,
        }


@dataclass(frozen=True, slots=True)
class OpportunityReportHeader:
    command: str
    status: str
    market: str
    snapshot_id: str

    def to_payload(self) -> dict[str, str]:
        return {
            "command": self.command,
            "status": self.status,
            "market": self.market,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True, slots=True)
class OpportunityReportV2:
    header: OpportunityReportHeader
    sections: Mapping[str, OpportunitySection]
    blockers: tuple[str, ...]
    next_safe_actions: tuple[OpportunityNextAction, ...]
    snapshot_diff: OpportunitySnapshotDiff
    machine_payload: Mapping[str, object]
    report_version: str = "2.0"
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("OpportunityReportV2 cannot grant execution authority")

    def to_payload(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "report_header": self.header.to_payload(),
            "sections": {
                name: section.to_payload() for name, section in self.sections.items()
            },
            "blockers": self.blockers,
            "next_safe_actions": tuple(
                action.to_payload() for action in self.next_safe_actions
            ),
            "snapshot_diff": self.snapshot_diff.to_payload(),
            "machine_payload": self.machine_payload,
            "execution_allowed": False,
            "promotion_status": self.promotion_status,
            "live_eligibility_status": self.live_eligibility_status,
        }


def build_report_v2_payload(
    *,
    command: str,
    status: str,
    market: str,
    snapshot_id: str,
    ranked_candidates: Sequence[Mapping[str, object]],
    blockers: Sequence[object],
    next_safe_actions: Sequence[object] = (),
) -> dict[str, object]:
    views = tuple(_candidate_view(item) for item in ranked_candidates)
    report = OpportunityReportV2(
        header=OpportunityReportHeader(
            command=command,
            status=status,
            market=market,
            snapshot_id=snapshot_id,
        ),
        sections={
            "top_opportunities": OpportunitySection(
                "top_opportunities",
                tuple(
                    item
                    for item in views
                    if item.accepted and item.grade in {"A", "B+"}
                )[:5],
            ),
            "confirmation_pending": OpportunitySection(
                "confirmation_pending",
                tuple(
                    item
                    for item in views
                    if item.accepted
                    and (
                        item.lifecycle_state == "CONFIRMATION_PENDING"
                        or bool(item.confirmation_gaps)
                    )
                )[:10],
            ),
            "setup_forming": OpportunitySection(
                "setup_forming",
                tuple(
                    item
                    for item in views
                    if item.accepted
                    and item.lifecycle_state in {"SETUP_FORMING", "WATCH_ONLY"}
                    and item.grade in {"B", "B-", "C"}
                )[:10],
            ),
            "validation_ladder": OpportunitySection(
                "validation_ladder",
                tuple(item for item in views if item.accepted and item.validation_gaps)[
                    :10
                ],
            ),
            "rejected_or_lost": OpportunitySection(
                "rejected_or_lost",
                tuple(item for item in views if not item.accepted)[:10],
            ),
        },
        blockers=_text_tuple(blockers),
        next_safe_actions=tuple(
            OpportunityNextAction(str(action)) for action in next_safe_actions
        )
        or (OpportunityNextAction("KEEP_RESEARCH_RADAR_RUNNING"),),
        snapshot_diff=OpportunitySnapshotDiff(
            previous_snapshot_id=None,
            current_snapshot_id=snapshot_id,
            still_pending=tuple(
                item.symbol
                for item in views
                if item.confirmation_gaps or item.validation_gaps
            ),
            new_blockers=_text_tuple(blockers),
        ),
        machine_payload={
            "candidate_count": len(views),
            "visible_candidate_count": sum(1 for item in views if item.accepted),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    return report.to_payload()


def _candidate_view(item: Mapping[str, object]) -> OpportunityCandidateView:
    score = _decimal_score(item.get("opportunity_score", item.get("score", 0)))
    grade = classify_opportunity_grade(score)
    confirmation_gaps = _text_tuple(item.get("confirmation_gaps", ()))
    promotion_requirements = _text_tuple(item.get("promotion_requirements", ()))
    validation_gaps = tuple(
        dict.fromkeys(
            (*_text_tuple(item.get("validation_gaps", ())), *promotion_requirements)
        )
    )
    execution_blockers = _text_tuple(item.get("execution_blockers", ()))
    return OpportunityCandidateView(
        symbol=str(item.get("symbol", "UNKNOWN")),
        market=str(item.get("market", "UNKNOWN")),
        timeframe=str(item.get("timeframe", "UNSPECIFIED")),
        setup_name=str(item.get("setup_id", item.get("setup_name", "UNKNOWN_SETUP"))),
        pattern_type=_pattern_type_value(
            item.get("pattern_type"),
            fallback_setup_name=str(
                item.get("setup_id", item.get("setup_name", "UNKNOWN_SETUP"))
            ),
        ),
        direction=str(item.get("direction", "WATCH_ONLY")),
        lifecycle_state=str(
            item.get("visibility_state", item.get("lifecycle_state", "WATCH_ONLY"))
        ),
        grade=grade,
        score=score,
        confidence=_decimal_score(
            item.get("research_confidence", item.get("confidence", 0))
        ),
        why_visible=_text_tuple(item.get("why_visible", ())),
        supporting_evidence=_text_tuple(item.get("supporting_evidence", ())),
        counter_evidence=_text_tuple(item.get("counter_evidence", ())),
        discovery_blockers=_text_tuple(item.get("discovery_blockers", ())),
        confirmation_gaps=confirmation_gaps,
        validation_gaps=validation_gaps,
        promotion_requirements=promotion_requirements,
        execution_blockers=execution_blockers,
        next_safe_action=str(
            item.get(
                "next_safe_action",
                _next_safe_action(confirmation_gaps, validation_gaps),
            )
        ),
        upgrade_condition=str(
            item.get(
                "upgrade_condition",
                "Clear confirmation gaps and refresh validation evidence.",
            )
        ),
        invalidation_condition=str(
            item.get(
                "invalidation_condition",
                "Discovery exclusion, stale data, or critical risk evidence appears.",
            )
        ),
        accepted=bool(item.get("accepted", True)),
    )


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


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item))
    return ()


def _decimal_score(value: object) -> Decimal:
    try:
        score = Decimal(str(value))
    except Exception:
        return Decimal("0")
    if not score.is_finite():
        return Decimal("0")
    return max(Decimal("0"), min(Decimal("100"), score))


def _next_safe_action(
    confirmation_gaps: tuple[str, ...],
    validation_gaps: tuple[str, ...],
) -> str:
    if confirmation_gaps:
        return "WAIT_FOR_CONFIRMATION_AND_REFRESH_RADAR"
    if validation_gaps:
        return "RUN_VALIDATION_QUEUE"
    return "KEEP_RESEARCH_RADAR_RUNNING"

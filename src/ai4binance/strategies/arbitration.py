"""Fail-closed deterministic arbitration for competing research candidates."""

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite

from ai4binance.domain import CandidateStatus, TradeCandidate


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    selected: TradeCandidate | None
    ranked: tuple[TradeCandidate, ...]
    blockers: tuple[str, ...]
    execution_allowed: bool = False


@dataclass(frozen=True, slots=True)
class CandidateArbitrator:
    """Rank only sufficiently strong candidates and reject ambiguous leaders."""

    minimum_score: float = 60.0
    minimum_confidence: float = 0.5
    minimum_risk_reward: Decimal = Decimal("2")
    minimum_score_lead: float = 3.0

    def __post_init__(self) -> None:
        float_limits = (
            ("minimum_score", self.minimum_score, 100.0),
            ("minimum_confidence", self.minimum_confidence, 1.0),
            ("minimum_score_lead", self.minimum_score_lead, 100.0),
        )
        for name, value, upper in float_limits:
            if not isfinite(value) or not 0.0 <= value <= upper:
                raise ValueError(f"{name} must be finite and between 0 and {upper:g}")
        if self.minimum_risk_reward <= Decimal("0"):
            raise ValueError("minimum_risk_reward must be positive")

    def select(self, candidates: tuple[TradeCandidate, ...]) -> CandidateSelection:
        ready = tuple(
            candidate
            for candidate in candidates
            if candidate.status is CandidateStatus.READY_FOR_RISK
            and not candidate.blockers
        )
        if not ready:
            return CandidateSelection(None, (), ("NO_READY_CANDIDATE",))

        qualified = tuple(
            candidate
            for candidate in ready
            if candidate.score >= self.minimum_score
            and candidate.confidence >= self.minimum_confidence
            and candidate.risk_reward >= self.minimum_risk_reward
        )
        ranked = tuple(
            sorted(
                qualified,
                key=lambda item: (
                    -self._ranking_value(item),
                    -item.score,
                    -item.confidence,
                    -item.risk_reward,
                    item.candidate_id,
                ),
            )
        )
        if not ranked:
            blockers: list[str] = []
            if all(item.score < self.minimum_score for item in ready):
                blockers.append("CANDIDATE_SCORE_BELOW_MINIMUM")
            if all(item.confidence < self.minimum_confidence for item in ready):
                blockers.append("CANDIDATE_CONFIDENCE_BELOW_MINIMUM")
            if all(item.risk_reward < self.minimum_risk_reward for item in ready):
                blockers.append("CANDIDATE_RISK_REWARD_BELOW_MINIMUM")
            blockers.append("NO_QUALIFIED_CANDIDATE")
            return CandidateSelection(None, ranked, tuple(blockers))
        if len({item.action for item in ranked}) > 1:
            return CandidateSelection(
                None,
                ranked,
                ("CONFLICTING_CANDIDATE_DIRECTIONS",),
            )
        if (
            len(ranked) > 1
            and self._ranking_value(ranked[0]) - self._ranking_value(ranked[1])
            < self.minimum_score_lead
        ):
            return CandidateSelection(
                None,
                ranked,
                ("AMBIGUOUS_TOP_CANDIDATES",),
            )
        return CandidateSelection(ranked[0], ranked, ())

    @staticmethod
    def _ranking_value(candidate: TradeCandidate) -> float:
        return float(
            candidate.ranking_score
            if candidate.ranking_score is not None
            else candidate.score
        )

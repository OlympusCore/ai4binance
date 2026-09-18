"""Fail-closed 100-point scoring for one repository/capability pair."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from ai4binance.github_radar.models import (
    RecommendationAction,
    RepositoryEvidence,
    ResearchUnitEvaluation,
    WeightedScore,
)
from ai4binance.github_radar.ontology import MAX_ONTOLOGY_BYTES


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    weights: tuple[tuple[str, int], ...]
    thresholds: tuple[tuple[str, int], ...]
    hard_gates: tuple[str, ...]
    max_action_without_known_license: RecommendationAction

    def __post_init__(self) -> None:
        if sum(weight for _, weight in self.weights) != 100:
            raise ValueError("GitHub Radar scoring weights must total 100")
        if len({name for name, _ in self.weights}) != len(self.weights):
            raise ValueError("GitHub Radar scoring dimensions must be unique")
        if any(weight <= 0 for _, weight in self.weights):
            raise ValueError("GitHub Radar scoring weights must be positive")
        if not self.hard_gates or len(set(self.hard_gates)) != len(self.hard_gates):
            raise ValueError("GitHub Radar hard gates must be non-empty and unique")

    @property
    def weight_map(self) -> dict[str, int]:
        return dict(self.weights)

    @property
    def threshold_map(self) -> dict[str, int]:
        return dict(self.thresholds)


def default_scoring_path(repository_root: Path | None = None) -> Path:
    root = (repository_root or Path.cwd()).resolve()
    return root / "config" / "research" / "research_scoring.yaml"


def load_scoring_policy(path: Path | None = None) -> ScoringPolicy:
    resolved = (path or default_scoring_path()).resolve()
    if resolved.stat().st_size > MAX_ONTOLOGY_BYTES:
        raise ValueError("GitHub Radar scoring policy exceeds the bounded size")
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("GitHub Radar scoring policy must be a mapping")
    payload = cast(Mapping[str, object], raw)
    weights = _int_mapping(payload.get("weights"), "weights")
    thresholds = _int_mapping(payload.get("thresholds"), "thresholds")
    hard_gates = _strings(payload.get("hard_gates"), "hard_gates")
    authority = _mapping(payload.get("authority"), "authority")
    if (
        bool(authority.get("dependency_install_allowed", True))
        or bool(authority.get("external_code_execution_allowed", True))
        or str(authority.get("live_eligibility_status", "")) != "LIVE_ORDER_BLOCKED"
    ):
        raise ValueError("scoring policy cannot grant code or trading authority")
    return ScoringPolicy(
        weights=weights,
        thresholds=thresholds,
        hard_gates=hard_gates,
        max_action_without_known_license=RecommendationAction(
            str(authority.get("max_action_without_known_license", "REJECT"))
        ),
    )


def evaluate_repository_evidence(
    evidence: RepositoryEvidence,
    policy: ScoringPolicy | None = None,
) -> ResearchUnitEvaluation:
    """Score one atomic research unit after its hard-gate review."""
    active_policy = policy or load_scoring_policy()
    ratings = {item.dimension: item for item in evidence.ratings}
    expected = set(active_policy.weight_map)
    if set(ratings) != expected:
        missing = sorted(expected - set(ratings))
        extra = sorted(set(ratings) - expected)
        raise ValueError(
            f"rating dimensions mismatch: missing={missing}, extra={extra}"
        )
    scores = tuple(
        WeightedScore(
            dimension=dimension,
            rating=ratings[dimension].rating,
            weight=weight,
            points=round(ratings[dimension].rating * weight, 4),
            rationale=ratings[dimension].rationale,
        )
        for dimension, weight in active_policy.weights
    )
    total = round(sum(item.points for item in scores), 4)
    blockers = tuple(
        f"HARD_GATE_FAILED:{gate}"
        for gate in active_policy.hard_gates
        if gate not in evidence.passed_gates
    )
    recommendation = (
        RecommendationAction.REJECT
        if blockers
        else _recommend(total, active_policy.threshold_map)
    )
    if _unknown_license(evidence.source.license_id) and _rank(recommendation) > _rank(
        active_policy.max_action_without_known_license
    ):
        recommendation = active_policy.max_action_without_known_license
        blockers = (*blockers, "LICENSE_UNKNOWN_REUSE_BLOCKED")
    reuse_mode = (
        "LOCAL_REIMPLEMENTATION_ONLY"
        if recommendation is RecommendationAction.ADOPT_IDEA
        else "NONE"
    )
    return ResearchUnitEvaluation(
        research_id=evidence.research_id,
        capability_id=evidence.capability_id,
        source=evidence.source,
        evidence=evidence.evidence,
        risks=evidence.risks,
        scores=scores,
        total_score=total,
        recommendation=recommendation,
        blockers=blockers,
        reuse_mode=reuse_mode,
    )


def _recommend(score: float, thresholds: Mapping[str, int]) -> RecommendationAction:
    if score >= thresholds["adopt_idea"]:
        return RecommendationAction.ADOPT_IDEA
    if score >= thresholds["poc"]:
        return RecommendationAction.POC
    if score >= thresholds["research"]:
        return RecommendationAction.RESEARCH
    if score >= thresholds["watch"]:
        return RecommendationAction.WATCH
    return RecommendationAction.REJECT


def _rank(action: RecommendationAction) -> int:
    return list(RecommendationAction).index(action)


def _unknown_license(value: str) -> bool:
    return value.strip().upper() in {"UNKNOWN", "NOASSERTION", "NONE"}


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"scoring {name} must be a mapping")
    return cast(Mapping[str, object], value)


def _int_mapping(value: object, name: str) -> tuple[tuple[str, int], ...]:
    mapping = _mapping(value, name)
    return tuple((str(key), int(str(item))) for key, item in mapping.items())


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"scoring {name} must be a sequence")
    return tuple(str(item) for item in value)

"""Pattern-hypothesis normalization over existing deterministic analyzers."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from ai4binance.intelligence.contracts import (
    PatternHypothesisEvidence,
    PatternLifecycleState,
    ScenarioDirection,
)
from ai4binance.schemas import AgentResult, MarketSnapshot, is_usable_agent_result

PATTERN_AGENTS = (
    "chart_pattern",
    "fibonacci",
    "harmonic_pattern",
    "elliott_wave",
    "candlestick",
    "price_action",
)
TIMEFRAME_PRIORITY = ("1d", "4h", "1h", "15m", "5m")
ATTRIBUTE_KEYS = (
    "pattern_id",
    "pattern_family",
    "formation_progress",
    "confirmation_condition",
    "invalidation_condition",
    "retracement_zone",
    "nearest_level",
    "ab_cd",
    "theory",
    "heuristic",
    "method",
)


@dataclass(frozen=True, slots=True)
class PatternHypothesisFabric:
    """Convert detectors into non-authoritative, lifecycle-bound hypotheses."""

    def build(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
    ) -> tuple[PatternHypothesisEvidence, ...]:
        hypotheses = tuple(
            hypothesis
            for name in PATTERN_AGENTS
            if (result := agent_results.get(name)) is not None
            if (hypothesis := self._normalize(snapshot, name, result)) is not None
        )
        return tuple(
            sorted(hypotheses, key=lambda item: (item.family, item.hypothesis_id))
        )

    def _normalize(
        self,
        snapshot: MarketSnapshot,
        name: str,
        result: AgentResult,
    ) -> PatternHypothesisEvidence | None:
        if not is_usable_agent_result(result) or result.blockers:
            return None
        if (
            result.agent_name != name
            or result.snapshot_id != snapshot.snapshot_id
            or result.symbol != snapshot.symbol
            or result.timestamp != snapshot.created_at
        ):
            return None
        direction = self._direction(result.directional_vote)
        lifecycle = self._lifecycle(name, result.calculation_metadata)
        source_timeframe = self._source_timeframe(snapshot, result)
        attributes = self._attributes(result.calculation_metadata)
        identity = result.calculation_metadata.get("pattern_id")
        digest_source = f"{snapshot.snapshot_id}|{name}|" + (
            identity
            if isinstance(identity, str) and identity.strip()
            else (
                f"{snapshot.snapshot_id}|{name}|{direction.value}|"
                f"{'|'.join(result.detected_setups)}"
            )
        )
        digest = sha256(digest_source.encode()).hexdigest()[:16]
        completion = self._completion_quality(lifecycle, result.calculation_metadata)
        invalidation = result.invalidation or self._string(
            result.calculation_metadata.get("invalidation_condition")
        )
        return PatternHypothesisEvidence(
            hypothesis_id=f"pattern:{digest}",
            family=name.upper(),
            direction=direction,
            lifecycle_state=lifecycle.value,
            confidence=result.confidence,
            evidence_for=result.evidence or (f"{name}:RULE_EVALUATED",),
            evidence_against=tuple(
                dict.fromkeys(
                    (
                        *result.counter_evidence,
                        *result.blockers,
                        *result.warnings,
                    )
                )
            ),
            invalidation=invalidation,
            source_timeframe=source_timeframe,
            geometry_quality=0.0,
            completion_quality=completion,
            attributes=attributes,
        )

    @staticmethod
    def _lifecycle(
        name: str,
        metadata: Mapping[str, object],
    ) -> PatternLifecycleState:
        explicit = metadata.get("lifecycle_state")
        if isinstance(explicit, str):
            try:
                return PatternLifecycleState(explicit)
            except ValueError:
                return PatternLifecycleState.INVALIDATED
        return {
            "fibonacci": PatternLifecycleState.CONTEXT_ONLY,
            "elliott_wave": PatternLifecycleState.ALTERNATIVE_UNRESOLVED,
            "harmonic_pattern": PatternLifecycleState.FORMING,
            "chart_pattern": PatternLifecycleState.FORMING,
            "candlestick": PatternLifecycleState.CONFIRMED,
            "price_action": PatternLifecycleState.CONFIRMED,
        }[name]

    @staticmethod
    def _source_timeframe(
        snapshot: MarketSnapshot,
        result: AgentResult,
    ) -> str:
        explicit = result.calculation_metadata.get("source_timeframe")
        if isinstance(explicit, str) and explicit in snapshot.timeframes:
            return explicit
        evidence_timeframes = {
            item.rsplit(":", 1)[-1] for item in result.evidence
        } & set(snapshot.timeframes)
        if len(evidence_timeframes) == 1:
            return next(iter(evidence_timeframes))
        return (
            result.timeframes[0]
            if len(result.timeframes) == 1
            and result.timeframes[0] in snapshot.timeframes
            else "UNKNOWN"
        )

    @staticmethod
    def _attributes(metadata: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
        attributes: list[tuple[str, str]] = []
        for key in ATTRIBUTE_KEYS:
            value = metadata.get(key)
            if isinstance(value, (str, int, float, Decimal)) and not isinstance(
                value, bool
            ):
                text = str(value).strip()
                if text:
                    attributes.append((key, text[:256]))
        return tuple(attributes)

    @staticmethod
    def _completion_quality(
        lifecycle: PatternLifecycleState,
        metadata: Mapping[str, object],
    ) -> float:
        raw = metadata.get("formation_progress")
        if isinstance(raw, (str, int, float, Decimal)) and not isinstance(raw, bool):
            try:
                value = Decimal(str(raw))
            except InvalidOperation:
                value = Decimal("0")
            if value.is_finite():
                return float(max(Decimal("0"), min(Decimal("1"), value)))
        return 1.0 if lifecycle is PatternLifecycleState.CONFIRMED else 0.5

    @staticmethod
    def _direction(vote: float) -> ScenarioDirection:
        if vote > 0.0:
            return ScenarioDirection.LONG
        if vote < 0.0:
            return ScenarioDirection.SHORT
        return ScenarioDirection.NEUTRAL

    @staticmethod
    def _string(value: object) -> str | None:
        return value if isinstance(value, str) and value.strip() else None

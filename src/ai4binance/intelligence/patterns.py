"""Pattern-hypothesis normalization over existing deterministic analyzers."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from ai4binance.intelligence.contracts import (
    PatternHypothesisEvidence,
    PatternLifecycleState,
    ScenarioDirection,
    TimeframeStructureEvidence,
)
from ai4binance.intelligence.structure import MarketStructureEngine
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
    "xa_ab",
    "ab_bc",
    "bc_cd",
    "xa_ad",
    "prz_low",
    "prz_high",
    "anchor_start",
    "anchor_end",
    "retracement_382",
    "retracement_500",
    "retracement_618",
    "extension_1272",
    "extension_1618",
    "wave_rules",
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
            for hypothesis in self._hypotheses(snapshot, name, result)
        )
        return tuple(
            sorted(hypotheses, key=lambda item: (item.family, item.hypothesis_id))
        )

    def _hypotheses(
        self,
        snapshot: MarketSnapshot,
        name: str,
        result: AgentResult,
    ) -> tuple[PatternHypothesisEvidence, ...]:
        """Route specialized pattern families through their canonical engines."""
        base = self._normalize(snapshot, name, result)
        if base is None:
            return ()
        if name == "fibonacci":
            return (FibonacciConfluenceEngine().build(base),)
        if name == "harmonic_pattern":
            return (HarmonicPatternEngine().build(base),)
        if name == "elliott_wave":
            return ElliottWaveHypothesisEngine().build(base)
        return (base,)

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
        digest_source = (
            f"{snapshot.market_type}|{snapshot.symbol}|{source_timeframe}|{name}|"
            + (
                identity
                if isinstance(identity, str) and identity.strip()
                else (
                    f"{snapshot.snapshot_id}|{name}|{direction.value}|"
                    f"{'|'.join(result.detected_setups)}"
                )
            )
        )
        digest = sha256(digest_source.encode()).hexdigest()[:16]
        observation = sha256(f"{snapshot.snapshot_id}|{digest}".encode()).hexdigest()[
            :20
        ]
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
            observation_id=f"pattern-observation:{observation}",
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


@dataclass(frozen=True, slots=True)
class FibonacciConfluenceEngine:
    """Keep Fibonacci as structural confluence, never a directional signal."""

    @staticmethod
    def detect(structure: TimeframeStructureEvidence) -> dict[str, object] | None:
        swings = MarketStructureEngine.alternating_swings(structure.swings)
        if len(swings) < 2:
            return None
        start, end = swings[-2:]
        span = end.price - start.price
        if span == 0:
            return None
        identity = f"fib:{start.occurred_at.isoformat()}:{end.occurred_at.isoformat()}"
        return {
            "method": "CONFIRMED_SWING_FIBONACCI",
            "lifecycle_state": "CONTEXT_ONLY",
            "anchor_start": str(start.price),
            "anchor_end": str(end.price),
            "pattern_id": f"{identity}:{start.price}:{end.price}",
            **{
                f"retracement_{label}": str(end.price - span * Decimal(ratio))
                for label, ratio in (("382", ".382"), ("500", ".5"), ("618", ".618"))
            },
            **{
                f"extension_{label}": str(start.price + span * Decimal(ratio))
                for label, ratio in (("1272", "1.272"), ("1618", "1.618"))
            },
        }

    def build(self, evidence: PatternHypothesisEvidence) -> PatternHypothesisEvidence:
        if evidence.family != "FIBONACCI":
            raise ValueError("Fibonacci confluence requires Fibonacci evidence")
        attributes = tuple(
            dict.fromkeys(
                (
                    *evidence.attributes,
                    ("role", "CONFLUENCE_ONLY"),
                    ("direction_policy", "NEUTRAL_ONLY"),
                )
            )
        )
        return PatternHypothesisEvidence(
            hypothesis_id=evidence.hypothesis_id,
            family=evidence.family,
            direction=ScenarioDirection.NEUTRAL,
            lifecycle_state=PatternLifecycleState.CONTEXT_ONLY.value,
            confidence=evidence.confidence,
            evidence_for=evidence.evidence_for,
            evidence_against=evidence.evidence_against,
            invalidation=evidence.invalidation,
            source_timeframe=evidence.source_timeframe,
            geometry_quality=evidence.geometry_quality,
            completion_quality=evidence.completion_quality,
            attributes=attributes,
            observation_id=evidence.observation_id,
        )


@dataclass(frozen=True, slots=True)
class HarmonicPatternEngine:
    """Bound harmonic geometry to a detector result without entry authority."""

    minimum_ab_cd: Decimal = Decimal("0.8")
    maximum_ab_cd: Decimal = Decimal("1.2")

    @staticmethod
    def detect(structure: TimeframeStructureEvidence) -> dict[str, object] | None:
        """Evaluate alternating XABCD pivots using Gartley and Bat geometry."""
        swings = MarketStructureEngine.alternating_swings(structure.swings)
        if len(swings) < 5:
            return None
        x, a, b, c, d = swings[-5:]
        direction = Decimal("1") if a.price > x.price else Decimal("-1")
        xp, ap, bp, cp, dp = (s.price * direction for s in (x, a, b, c, d))
        if not (xp < dp < bp < cp < ap):
            return None
        xa, ab, bc, cd = ap - xp, ap - bp, cp - bp, cp - dp
        xa_ab, ab_bc, bc_cd, xa_ad = ab / xa, bc / ab, cd / bc, (ap - dp) / xa
        family = None
        if (
            abs(xa_ab - Decimal(".618")) <= Decimal(".03")
            and abs(xa_ad - Decimal(".786")) <= Decimal(".03")
            and Decimal("1.13") <= bc_cd <= Decimal("1.618")
            and Decimal(".8") <= ab / cd <= Decimal("1.2")
        ):
            family = "GARTLEY"
        elif (
            Decimal(".382") <= xa_ab <= Decimal(".5")
            and abs(xa_ad - Decimal(".886")) <= Decimal(".03")
            and Decimal("1.618") <= bc_cd <= Decimal("2.618")
        ):
            family = "BAT"
        if family is None or not Decimal(".382") <= ab_bc <= Decimal(".886"):
            return None
        half_width = xa * Decimal(".03")
        return {
            "method": "CONFIRMED_XABCD",
            "pattern_family": family,
            "pattern_id": "harmonic:"
            + ":".join(f"{s.occurred_at.isoformat()}:{s.price}" for s in swings[-5:]),
            "lifecycle_state": "POTENTIAL",
            "directional_vote": float(direction),
            "ab_cd": str(ab / cd),
            "xa_ab": str(xa_ab),
            "ab_bc": str(ab_bc),
            "bc_cd": str(bc_cd),
            "xa_ad": str(xa_ad),
            "prz_low": str(d.price - half_width),
            "prz_high": str(d.price + half_width),
            "invalidation_condition": (
                f"CLOSE_{'BELOW' if direction > 0 else 'ABOVE'}={x.price}"
            ),
        }

    def build(self, evidence: PatternHypothesisEvidence) -> PatternHypothesisEvidence:
        if evidence.family != "HARMONIC_PATTERN":
            raise ValueError("Harmonic engine requires harmonic evidence")
        raw_ratio = dict(evidence.attributes).get("ab_cd")
        try:
            ratio = Decimal(raw_ratio) if raw_ratio is not None else None
        except InvalidOperation:
            ratio = None
        valid = (
            ratio is not None
            and ratio.is_finite()
            and self.minimum_ab_cd <= ratio <= self.maximum_ab_cd
        )
        attributes_map = dict(evidence.attributes)
        if attributes_map.get("method") == "CONFIRMED_XABCD":
            try:
                xa_ab, ab_bc, bc_cd, xa_ad = (
                    Decimal(attributes_map[key])
                    for key in ("xa_ab", "ab_bc", "bc_cd", "xa_ad")
                )
                valid = all(v.is_finite() for v in (xa_ab, ab_bc, bc_cd, xa_ad))
                valid = valid and Decimal(".382") <= ab_bc <= Decimal(".886")
                if attributes_map.get("pattern_family") == "GARTLEY":
                    valid = valid and (
                        abs(xa_ab - Decimal(".618")) <= Decimal(".03")
                        and abs(xa_ad - Decimal(".786")) <= Decimal(".03")
                        and Decimal("1.13") <= bc_cd <= Decimal("1.618")
                        and ratio is not None
                        and ratio.is_finite()
                        and self.minimum_ab_cd <= ratio <= self.maximum_ab_cd
                    )
                elif attributes_map.get("pattern_family") == "BAT":
                    valid = valid and (
                        Decimal(".382") <= xa_ab <= Decimal(".5")
                        and abs(xa_ad - Decimal(".886")) <= Decimal(".03")
                        and Decimal("1.618") <= bc_cd <= Decimal("2.618")
                        and ratio is not None
                        and ratio.is_finite()
                        and ratio > 0
                    )
                else:
                    valid = False
            except (KeyError, InvalidOperation):
                valid = False
        geometry_quality = (
            max(0.0, 1.0 - float(abs(ratio - Decimal("1"))))
            if valid and ratio is not None
            else 0.0
        )
        attributes = tuple(
            dict.fromkeys(
                (
                    *evidence.attributes,
                    ("geometry_source", "CONFIRMED_DETECTOR_OUTPUT"),
                    ("pattern_quality", "BOUNDED" if valid else "INVALID"),
                )
            )
        )
        return PatternHypothesisEvidence(
            hypothesis_id=evidence.hypothesis_id,
            family=evidence.family,
            direction=evidence.direction if valid else ScenarioDirection.NEUTRAL,
            lifecycle_state=(
                evidence.lifecycle_state
                if valid
                else PatternLifecycleState.INVALIDATED.value
            ),
            confidence=evidence.confidence if valid else 0.0,
            evidence_for=evidence.evidence_for,
            evidence_against=(
                evidence.evidence_against
                if valid
                else (*evidence.evidence_against, "HARMONIC_GEOMETRY_INVALID")
            ),
            invalidation=evidence.invalidation,
            source_timeframe=evidence.source_timeframe,
            geometry_quality=max(0.0, min(1.0, geometry_quality)),
            completion_quality=evidence.completion_quality,
            attributes=attributes,
            observation_id=evidence.observation_id,
        )


@dataclass(frozen=True, slots=True)
class ElliottWaveHypothesisEngine:
    """Evaluate explicit impulse rules without inventing opposite wave counts."""

    @staticmethod
    def detect(structure: TimeframeStructureEvidence) -> dict[str, object] | None:
        swings = MarketStructureEngine.alternating_swings(structure.swings)
        if len(swings) < 6:
            return None
        points = swings[-6:]
        sign = Decimal("1") if points[1].price > points[0].price else Decimal("-1")
        p0, p1, p2, p3, p4, p5 = (s.price * sign for s in points)
        if not (p0 < p2 < p1 < p4 < p3 < p5):
            return None
        if p3 - p2 < min(p1 - p0, p5 - p4):
            return None
        return {
            "method": "CONFIRMED_IMPULSE_RULES",
            "wave_rules": "W2_ORIGIN;W3_NOT_SHORTEST;W4_NO_OVERLAP",
            "pattern_id": "impulse:"
            + ":".join(f"{s.occurred_at.isoformat()}:{s.price}" for s in points),
            "lifecycle_state": "ALTERNATIVE_UNRESOLVED",
            "directional_vote": float(sign),
            "invalidation_condition": (
                f"CLOSE_{'BELOW' if sign > 0 else 'ABOVE'}={points[4].price}"
            ),
            "heuristic": "DEGREE_AND_CORRECTION_UNRESOLVED",
        }

    def build(
        self, evidence: PatternHypothesisEvidence
    ) -> tuple[PatternHypothesisEvidence, ...]:
        if evidence.family != "ELLIOTT_WAVE":
            raise ValueError("Elliott engine requires Elliott evidence")
        directions = (evidence.direction,)
        labels = ("OBSERVED_COUNT",)
        return tuple(
            PatternHypothesisEvidence(
                hypothesis_id=f"{evidence.hypothesis_id}:{label}",
                observation_id=(
                    f"{evidence.observation_id}:{label}"
                    if evidence.observation_id
                    else ""
                ),
                family=evidence.family,
                direction=direction,
                lifecycle_state=PatternLifecycleState.ALTERNATIVE_UNRESOLVED.value,
                confidence=max(0.0, evidence.confidence - index * 0.1),
                evidence_for=evidence.evidence_for,
                evidence_against=tuple(
                    dict.fromkeys(
                        (*evidence.evidence_against, "ELLIOTT_ALTERNATIVE_UNRESOLVED")
                    )
                ),
                invalidation=evidence.invalidation,
                source_timeframe=evidence.source_timeframe,
                geometry_quality=evidence.geometry_quality,
                completion_quality=evidence.completion_quality,
                attributes=tuple(
                    dict.fromkeys((*evidence.attributes, ("alternative", label)))
                ),
            )
            for index, (label, direction) in enumerate(
                zip(labels, directions, strict=True)
            )
        )

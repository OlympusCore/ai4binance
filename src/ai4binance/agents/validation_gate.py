"""Final deterministic validation gate with no execution authority."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from ai4binance.domain import (
    AgentScore,
    Signal,
    SignalSubScores,
    TradeCandidate,
    ValidationStatus,
)
from ai4binance.schemas import AgentResult, AgentStatus, MarketSnapshot
from ai4binance.scoring import calculate_final_signal_score
from ai4binance.validation.oos_maturity import (
    OOSMaturityEvidenceBundle,
    OOSMaturityGate,
    OOSValidationSubject,
)


@dataclass(frozen=True, slots=True)
class ValidationGate:
    """Produce a fail-closed final decision from complete agent evidence."""

    version: str = "0.2.0"
    artifact_root: Path | None = None
    expected_subjects: tuple[OOSValidationSubject, ...] = ()
    evidence_bundles: tuple[OOSMaturityEvidenceBundle, ...] = ()
    evidence_load_blockers: tuple[str, ...] = ()

    @classmethod
    def from_deployment(
        cls, *, artifact_root: Path, deployment_path: Path, as_of: datetime
    ) -> ValidationGate:
        """Connect configured evidence without trusting artifact presence alone."""
        try:
            subjects, bundles = OOSMaturityGate(artifact_root).load_deployment(
                deployment_path, as_of=as_of
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            reason = (
                str(error) if isinstance(error, ValueError) else type(error).__name__
            )
            return cls(
                evidence_load_blockers=(f"OOS_RUNTIME_EVIDENCE_UNAVAILABLE:{reason}",)
            )
        return cls(
            artifact_root=artifact_root,
            expected_subjects=subjects,
            evidence_bundles=bundles,
        )

    def validate(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        *,
        extra_blockers: tuple[str, ...] = (),
        candidates: tuple[TradeCandidate, ...] = (),
    ) -> Signal:
        """Score research evidence but reject execution without approvals."""
        blockers = [*extra_blockers, *self.evidence_load_blockers]
        warnings: list[str] = []
        for name in sorted(agent_results):
            result = agent_results[name]
            blockers.extend(result.blockers)
            warnings.extend(result.warnings)
            if result.status is AgentStatus.FAILED:
                blockers.append(f"AGENT_FAILED:{name}")
            if (
                result.snapshot_id != snapshot.snapshot_id
                or result.symbol != snapshot.symbol
                or result.timestamp != snapshot.created_at
            ):
                blockers.append(f"AGENT_EVIDENCE_IDENTITY_MISMATCH:{name}")
        risk = agent_results.get("risk")
        selected = tuple(
            candidate
            for candidate in candidates
            if risk is not None
            and candidate.candidate_id == risk.calculation_metadata.get("candidate_id")
            and candidate.snapshot_id == snapshot.snapshot_id
            and candidate.symbol == snapshot.symbol
            and candidate.timestamp == snapshot.created_at
            and candidate.timeframe in snapshot.timeframes
            and candidate.market_type.upper() == snapshot.market_type.upper()
        )
        selected_scenario_id = selected[0].scenario_id if len(selected) == 1 else None
        risk_scenario_id = (
            risk.calculation_metadata.get("scenario_id") if risk is not None else None
        )
        scenario_binding_required = (
            selected_scenario_id is not None or risk_scenario_id is not None
        )
        scenario_binding_valid = not scenario_binding_required or (
            isinstance(risk_scenario_id, str)
            and risk_scenario_id == selected_scenario_id
        )
        if scenario_binding_required and not scenario_binding_valid:
            blockers.append("RISK_SCENARIO_BINDING_MISMATCH")
        risk_approved = (
            len(selected) == 1
            and risk is not None
            and risk.snapshot_id == snapshot.snapshot_id
            and risk.timestamp == snapshot.created_at
            and risk.status is AgentStatus.SUCCESS
            and not risk.blockers
            and risk.calculation_metadata.get("approved") is True
            and scenario_binding_valid
        )
        required_gates_passed = all(
            (gate_result := agent_results.get(name)) is not None
            and gate_result.status is AgentStatus.SUCCESS
            and gate_result.snapshot_id == snapshot.snapshot_id
            and gate_result.timestamp == snapshot.created_at
            and not gate_result.blockers
            for name in ("data_quality", "universe_liquidity")
        )
        maturity_ref, maturity_blockers = (
            self._maturity_evaluation(snapshot, selected)
            if required_gates_passed
            else (None, ())
        )
        blockers.extend(maturity_blockers)
        if maturity_ref is None:
            blockers.extend(
                (
                    "BACKTEST_APPROVAL_MISSING",
                    "WALK_FORWARD_APPROVAL_MISSING",
                    "OOS_APPROVAL_MISSING",
                )
            )
        if not risk_approved:
            blockers.append("RISK_APPROVAL_MISSING")
        unique_blockers = tuple(dict.fromkeys(blockers))
        unique_warnings = tuple(dict.fromkeys(warnings))
        agent_scores = tuple(
            AgentScore(name, agent_results[name].score)
            for name in sorted(agent_results)
        )
        evaluated = tuple(
            result
            for result in agent_results.values()
            if result.applicable
            and result.status in {AgentStatus.SUCCESS, AgentStatus.PARTIAL}
        )

        def maximum_score(*names: str) -> float:
            return max(
                (agent_results[name].score for name in names if name in agent_results),
                default=0.0,
            )

        sub_scores = SignalSubScores(
            trend_score=maximum_score("trend", "moving_average", "trend_channel"),
            volatility_score=maximum_score("volatility"),
            momentum_score=maximum_score("momentum", "divergence"),
            volume_score=maximum_score("volume", "volume_profile"),
            price_action_score=maximum_score(
                "price_action", "candlestick", "breakout_retest"
            ),
            structure_score=maximum_score(
                "market_structure", "support_resistance", "smc"
            ),
            fib_score=maximum_score("fibonacci"),
            pattern_score=maximum_score(
                "chart_pattern", "harmonic_pattern", "elliott_wave"
            ),
            cycle_score=maximum_score("wyckoff"),
            mtf_score=maximum_score("multi_timeframe", "market_regime"),
            sentiment_score=maximum_score(
                "sentiment", "news", "derivatives", "onchain", "whale"
            ),
        )
        has_positive_vote = any(result.directional_vote > 0.15 for result in evaluated)
        has_negative_vote = any(result.directional_vote < -0.15 for result in evaluated)
        contradiction_penalty = 10.0 if has_positive_vote and has_negative_vote else 0.0
        data_result = agent_results.get("data_quality")
        data_quality_penalty = (
            10.0
            if data_result is not None and data_result.status is AgentStatus.PARTIAL
            else 0.0
        )
        final_signal_score = calculate_final_signal_score(
            sub_scores,
            contradiction_penalty=contradiction_penalty,
            data_quality_penalty=data_quality_penalty,
        )
        confidence = (
            sum(result.confidence for result in evaluated) / len(evaluated)
            if evaluated
            else 0.0
        )
        regime_value = self._metadata_value(
            agent_results,
            "market_regime",
            "regime",
        )
        bias_value = self._metadata_value(
            agent_results,
            "multi_timeframe",
            "dominant_bias",
        )
        confluence_count_value = self._metadata_value(
            agent_results,
            "confluence",
            "independent_confluence_count",
        )
        return Signal(
            symbol=snapshot.symbol,
            timeframes=snapshot.timeframes,
            timestamp=snapshot.created_at,
            snapshot_id=snapshot.snapshot_id,
            trade_id=f"decision:{snapshot.snapshot_id}",
            market_type=snapshot.market_type,
            latest_price=snapshot.latest_price,
            regime=regime_value if isinstance(regime_value, str) else "UNKNOWN",
            htf_bias=bias_value if isinstance(bias_value, str) else "UNKNOWN",
            tactical_bias=bias_value if isinstance(bias_value, str) else "UNKNOWN",
            execution_bias="NO_TRIGGER",
            sub_scores=sub_scores,
            final_signal_score=final_signal_score,
            confidence=round(confidence, 6),
            agent_scores=agent_scores,
            independent_confluence_count=(
                confluence_count_value
                if isinstance(confluence_count_value, int)
                and confluence_count_value >= 0
                else 0
            ),
            reason_codes=("VALIDATION_REJECTED", "NO_TRADE_CAPITAL_PROTECTION")
            if unique_blockers
            else ("VALIDATION_PAPER_EVIDENCE_VERIFIED",),
            reason_summary="NO_TRADE: mandatory validation evidence is incomplete."
            if unique_blockers
            else "Paper evidence verified; governance authorization is required.",
            supporting_evidence=tuple(
                result.agent_name for result in evaluated if result.evidence
            )
            + (
                (f"SCENARIO:{selected_scenario_id}",)
                if selected_scenario_id is not None
                else ()
            )
            + ((maturity_ref,) if maturity_ref is not None else ()),
            blockers=unique_blockers,
            warnings=unique_warnings,
            execution_allowed=False,
            validation_status=ValidationStatus.REJECTED
            if unique_blockers
            else ValidationStatus.PAPER_APPROVED,
        )

    def _maturity_reference(
        self, snapshot: MarketSnapshot, candidates: tuple[TradeCandidate, ...]
    ) -> str | None:
        """Return a complete maturity reference for compatibility callers."""

        return self._maturity_evaluation(snapshot, candidates)[0]

    def _maturity_evaluation(
        self, snapshot: MarketSnapshot, candidates: tuple[TradeCandidate, ...]
    ) -> tuple[str | None, tuple[str, ...]]:
        """Revalidate bytes against independently supplied deployment identities.

        Candidate scores, promotion labels and run-card presence are not evidence.
        No configured identity or bundle means no approval, including simulation.
        """
        if self.artifact_root is None or len(candidates) != 1:
            return None, ()
        candidate = candidates[0]
        subjects = tuple(
            subject
            for subject in self.expected_subjects
            if (
                subject.setup_type == candidate.setup_name
                and subject.promotion.symbol == snapshot.symbol
                and subject.promotion.market_type == snapshot.market_type.upper()
                and subject.promotion.timeframe == candidate.timeframe
            )
        )
        if len(subjects) != 1:
            return None, (
                "OOS_SUBJECT_NOT_CONFIGURED:"
                f"{candidate.setup_name}:{snapshot.symbol}:{candidate.timeframe}",
            )
        expected = subjects[0]
        bundles = tuple(
            bundle
            for bundle in self.evidence_bundles
            if (
                bundle.subject is not None
                and bundle.subject.subject_key == expected.subject_key
            )
        )
        if len(bundles) != 1:
            return None, ("OOS_SUBJECT_BUNDLE_NOT_CONFIGURED",)
        current_subject = replace(
            expected, promotion=replace(expected.promotion, as_of=snapshot.created_at)
        )
        result = OOSMaturityGate(self.artifact_root).evaluate(
            replace(bundles[0], subject=current_subject)
        )
        if result.status != "OOS_MATURITY_COMPLETE" or result.blockers:
            return None, result.blockers
        return f"OOS_MATURITY:{result.bundle_sha256}", ()

    @staticmethod
    def _metadata_value(
        agent_results: Mapping[str, AgentResult],
        agent_name: str,
        key: str,
    ) -> object:
        result = agent_results.get(agent_name)
        return result.calculation_metadata.get(key) if result is not None else None

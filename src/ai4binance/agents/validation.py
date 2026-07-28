"""Final deterministic validation authority."""

from collections.abc import Mapping
from dataclasses import dataclass

from ai4binance.domain import AgentScore, Signal, SignalSubScores, ValidationStatus
from ai4binance.schemas import AgentResult, AgentStatus, MarketSnapshot
from ai4binance.scoring import calculate_final_signal_score


@dataclass(frozen=True, slots=True)
class ValidationAgent:
    """Produce a fail-closed decision from complete agent evidence."""

    version: str = "0.2.0"

    def validate(
        self,
        snapshot: MarketSnapshot,
        agent_results: Mapping[str, AgentResult],
        *,
        extra_blockers: tuple[str, ...] = (),
    ) -> Signal:
        """Score research evidence but reject execution without approvals."""
        blockers = list(extra_blockers)
        warnings: list[str] = []
        for name in sorted(agent_results):
            result = agent_results[name]
            blockers.extend(result.blockers)
            warnings.extend(result.warnings)
            if result.status is AgentStatus.FAILED:
                blockers.append(f"AGENT_FAILED:{name}")
        blockers.extend(
            (
                "BACKTEST_APPROVAL_MISSING",
                "WALK_FORWARD_APPROVAL_MISSING",
                "OOS_APPROVAL_MISSING",
                "RISK_APPROVAL_MISSING",
            )
        )
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
            reason_codes=("VALIDATION_REJECTED", "NO_TRADE_CAPITAL_PROTECTION"),
            reason_summary="NO_TRADE: mandatory validation evidence is incomplete.",
            supporting_evidence=tuple(
                result.agent_name for result in evaluated if result.evidence
            ),
            blockers=unique_blockers,
            warnings=unique_warnings,
            execution_allowed=False,
            validation_status=ValidationStatus.REJECTED,
        )

    @staticmethod
    def _metadata_value(
        agent_results: Mapping[str, AgentResult],
        agent_name: str,
        key: str,
    ) -> object:
        result = agent_results.get(agent_name)
        return result.calculation_metadata.get(key) if result is not None else None

"""Canonical Futures observation projection over the shared analysis pipeline."""

from ai4binance.agents.orchestrator import EnterpriseOrchestrator
from ai4binance.domain import Action
from ai4binance.schemas import AnalysisState, MarketSnapshot


def analyze_futures_snapshot(snapshot: MarketSnapshot) -> AnalysisState:
    """Use the same deterministic owner as historical and virtual research.

    No provider, wallet, clock, or OOS side effect is introduced here.
    """
    if snapshot.market_type != "USD_M_FUTURES":
        raise ValueError("Futures observation requires a USD-M snapshot")
    return EnterpriseOrchestrator(max_workers=1).analyze(snapshot)


def project_futures_opportunity(
    state: AnalysisState, timeframe: str
) -> dict[str, object]:
    """Expose actual scenario-bound geometry without manufacturing missing targets."""
    intelligence = state.trading_intelligence
    candidates = sorted(
        (
            c
            for c in state.candidate_setups
            if c.timeframe == timeframe and c.scenario_id
        ),
        key=lambda c: (len(c.blockers), -c.confidence, c.candidate_id),
    )
    blockers = tuple(
        dict.fromkeys(
            (
                *state.blockers,
                *(
                    intelligence.blockers
                    if intelligence is not None
                    else ("TRADING_INTELLIGENCE_UNAVAILABLE",)
                ),
            )
        )
    )
    result: dict[str, object] = {
        "status": "DATA_BLOCKED" if blockers else "NO_SETUP",
        "blockers": list(blockers),
        "direction": "WATCH_ONLY",
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "snapshot_id": state.snapshot_id,
        "analysis_method": "CANONICAL_TRADING_INTELLIGENCE_V2",
        "leverage": None,
        "leverage_state": "DATA_UNAVAILABLE",
        "leverage_blockers": ["DETERMINISTIC_POSITION_AND_MARGIN_PROOF_REQUIRED"],
    }
    if not candidates:
        return result
    candidate = candidates[0]
    if "STRUCTURAL_PLAN_V2" not in candidate.evidence:
        result.update(
            status="DATA_BLOCKED",
            blockers=list(
                dict.fromkeys(
                    (
                        *blockers,
                        *candidate.blockers,
                        "STRUCTURAL_PLAN_UNAVAILABLE",
                    )
                )
            ),
        )
        return result
    result.update(
        status="RESEARCH_ONLY",
        setup_name=candidate.setup_name,
        direction="BULLISH" if candidate.action is Action.BUY else "BEARISH",
        scenario_id=candidate.scenario_id,
        entry=str(candidate.entry_price),
        stop_loss=str(candidate.stop_loss),
        target_risk_reward=str(candidate.risk_reward),
        net_risk_reward=str(candidate.net_risk_reward)
        if candidate.net_risk_reward is not None
        else None,
        target_sources=list(candidate.target_sources),
        confidence=candidate.confidence,
        blockers=list(dict.fromkeys((*blockers, *candidate.blockers))),
        probability_calibration_state=candidate.probability_calibration_state,
    )
    for index, target in enumerate(candidate.take_profit_levels, start=1):
        result[f"tp{index}"] = str(target)
    return result

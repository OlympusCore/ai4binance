"""Report-only EIEF command payload builders."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai4binance.external_intel.core.enums import (
    MissionName,
    ProviderOperationalState,
)
from ai4binance.external_intel.core.ids import eief_id
from ai4binance.external_intel.core.interfaces import RadarRequest
from ai4binance.external_intel.fusion.engine import FusionEngine
from ai4binance.external_intel.integration.decision_governance_adapter import (
    to_compact_decision_payload,
)
from ai4binance.external_intel.radars.news_radar import build_connector as news_radar
from ai4binance.external_intel.radars.open_web import OpenWebRadarEngine
from ai4binance.external_intel.radars.reddit_radar import (
    build_connector as reddit_radar,
)
from ai4binance.external_intel.radars.regulatory_radar import (
    build_connector as regulatory_radar,
)
from ai4binance.external_intel.radars.security_radar import (
    build_connector as security_radar,
)
from ai4binance.external_intel.radars.telegram_radar import (
    build_connector as telegram_radar,
)
from ai4binance.external_intel.radars.x_radar import build_connector as x_radar
from ai4binance.external_intel.retrieval import load_open_web_policy
from ai4binance.external_intel.storage import OpenWebEvidenceStore
from ai4binance.external_intel.technology.research_intake import (
    assess_finding,
    research_topics_payload,
)
from ai4binance.external_intel.universe.classifier import classify_asset
from ai4binance.external_intel.universe.snapshot import build_universe_snapshot
from ai4binance.reporting import to_primitive


def external_intel_payload(
    *,
    command: str = "external-intel",
    symbol: str | None = None,
    topic: str | None = None,
) -> dict[str, object]:
    observed_at = datetime.now(UTC)
    run_id = eief_id("run", command, symbol or "MARKET_WIDE", observed_at.isoformat())
    request = RadarRequest(
        run_id=run_id, observed_at=observed_at, symbol=symbol, topic=topic
    )
    connectors = (
        x_radar(),
        news_radar(),
        reddit_radar(),
        telegram_radar(),
        security_radar(),
        regulatory_radar(),
    )
    findings = tuple(
        finding for connector in connectors for finding in connector.run(request)
    )
    impact = FusionEngine().fuse(findings, generated_at=observed_at, symbol=symbol)
    return {
        "command": command,
        "status": "DEGRADED",
        "mission": "EXTERNAL_INTELLIGENCE_EVIDENCE_FABRIC",
        "radar_count": len(connectors),
        "finding_count": len(findings),
        "findings": to_primitive(findings),
        "decision_governance_impact": to_compact_decision_payload(impact),
        "blockers": tuple(
            dict.fromkeys(
                blocker for finding in findings for blocker in finding.blockers
            )
        ),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def external_intel_universe_payload() -> dict[str, object]:
    observed_at = datetime.now(UTC)
    assets = (
        classify_asset("HOT", spot_symbols=("HOTUSDT",)),
        classify_asset("USDT", spot_symbols=("USDTFDUSD",)),
        classify_asset(
            "WBTC", spot_symbols=("WBTCUSDT",), metadata_name="Wrapped Bitcoin"
        ),
        classify_asset("ETHUP", spot_symbols=("ETHUPUSDT",)),
    )
    snapshot = build_universe_snapshot(observed_at=observed_at, assets=assets)
    return {
        "command": "external-intel-universe",
        "status": "READY" if not snapshot.blockers else "DEGRADED",
        "snapshot": to_primitive(snapshot),
        "eligible_assets": tuple(
            asset.asset
            for asset in snapshot.assets
            if asset.eligible_for_opportunity_scan
        ),
        "excluded_assets": tuple(
            asset.asset
            for asset in snapshot.assets
            if not asset.eligible_for_opportunity_scan
        ),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def open_web_payload(
    *,
    mission: MissionName = MissionName.TECHNOLOGY_DEVELOPMENT,
    seed_urls: tuple[str, ...] = (),
    policy_path: Path | None = None,
    evidence_path: Path = Path(
        "runtime/state/runtime_research/open-web-evidence.jsonl"
    ),
    engine: OpenWebRadarEngine | None = None,
) -> dict[str, object]:
    observed_at = datetime.now(UTC)
    run_id = eief_id("openweb", mission.value, observed_at.isoformat())
    try:
        selected_engine = engine or OpenWebRadarEngine.from_policy(
            load_open_web_policy(policy_path),
            store=OpenWebEvidenceStore(evidence_path),
        )
        report = selected_engine.scan(
            run_id=run_id,
            observed_at=observed_at,
            mission=mission,
            seed_urls=seed_urls,
        )
    except (OSError, ValueError) as error:
        return {
            "command": "external-intel-open-web",
            "status": "DEGRADED",
            "mission": mission.value,
            "report": None,
            "blockers": (f"OPEN_WEB_CONFIGURATION_INVALID:{error}",),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    serialized_report = to_primitive(report)
    if not isinstance(serialized_report, dict):
        raise TypeError("open-web report payload must be a mapping")
    serialized_report["research_topics"] = research_topics_payload()
    serialized_report["research_assessments"] = tuple(
        to_primitive(
            assess_finding(
                finding_id=candidate.candidate_id,
                text=f"{candidate.technology_area} {candidate.title}",
                evidence_strength=candidate.confidence,
                source_authority=candidate.confidence,
                novelty_score=0.5,
                system_relevance=candidate.relevance_to_ai4binance,
                canonical_compatibility=candidate.architecture_fit,
                expected_benefit=candidate.relevance_to_ai4binance,
                implementation_cost=candidate.implementation_risk,
                security_risk=max(candidate.security_risk, candidate.license_risk),
                trading_risk=_technology_trading_risk(candidate.technology_area),
            )
        )
        for candidate in report.technology_candidates
    )
    return {
        "command": "external-intel-open-web",
        "status": (
            "READY"
            if report.status is ProviderOperationalState.AVAILABLE
            else "DEGRADED"
        ),
        "mission": mission.value,
        "report": serialized_report,
        "blockers": report.blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _technology_trading_risk(technology_area: str) -> float:
    """Keep strategy and execution research conservative without trade authority."""
    return (
        0.6
        if technology_area
        in {"strategy-signal-research", "protocol-exchange-api", "risk-control"}
        else 0.2
    )

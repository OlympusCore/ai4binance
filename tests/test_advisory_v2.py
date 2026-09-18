"""Structured evidence and authority-safe Advisory Agent v2 tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.agents.advisory import (
    AdvisoryCheckpoint,
    AdvisoryEngine,
    AdvisoryEvidencePacket,
    AdvisoryOpinion,
    AdvisoryRole,
    CanonicalAnalysisEnvelope,
    EvidenceItem,
    InMemoryAdvisoryCheckpointStore,
)
from ai4binance.decision import build_no_trade_signal
from ai4binance.schemas import (
    AgentResult,
    AgentStatus,
    AnalysisState,
    DataQuality,
    MarketSnapshot,
    OHLCVCandle,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)


def packet() -> AdvisoryEvidencePacket:
    return AdvisoryEvidencePacket.create(
        snapshot_id="snapshot-1",
        symbol="hotusdt",
        as_of=NOW,
        evidence=(
            EvidenceItem.create("risk", "deterministic-core", NOW, "Risk blocked"),
            EvidenceItem.create("trend", "deterministic-core", NOW, "Trend mixed"),
        ),
        deterministic_blockers=("OOS_EVIDENCE_INCOMPLETE",),
    )


def analysis_state() -> AnalysisState:
    candle = OHLCVCandle(
        NOW,
        Decimal("1"),
        Decimal("1.1"),
        Decimal("0.9"),
        Decimal("1"),
        Decimal("100"),
    )
    snapshot = MarketSnapshot(
        "snapshot-1",
        NOW,
        "Binance",
        "Spot",
        "HOTUSDT",
        ("1h",),
        {"1h": (candle, candle)},
        Decimal("1"),
        Decimal("0.99"),
        Decimal("1.01"),
        Decimal("0.02"),
        data_quality=DataQuality.DATA_VALID,
    )
    result = AgentResult(
        "trend",
        "0.1.0",
        "snapshot-1",
        NOW,
        "HOTUSDT",
        ("1h",),
        AgentStatus.PARTIAL,
        DataQuality.DATA_VALID,
        True,
        0.1,
        52.0,
        0.4,
        blockers=("WEAK_TREND",),
        reason_codes=("TREND_MIXED",),
    )
    return AnalysisState(
        "snapshot-1",
        "HOTUSDT",
        NOW,
        snapshot,
        {"trend": result},
        blockers=("OOS_EVIDENCE_INCOMPLETE",),
        final_decision=build_no_trade_signal(
            symbol="HOTUSDT",
            timeframes=("1h",),
            timestamp=NOW,
            snapshot_id="snapshot-1",
            blocker="NO_TRADE_WEAK_EVIDENCE",
        ),
    )


def test_canonical_analysis_envelope_reduces_state_to_hash_bound_packet() -> None:
    envelope = CanonicalAnalysisEnvelope.from_analysis_state(analysis_state())

    assert envelope.symbol == "HOTUSDT"
    assert envelope.final_action == "NO_TRADE"
    assert envelope.promotion_status == "RESEARCH_ONLY"
    assert envelope.execution_allowed is False
    assert envelope.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "OOS_EVIDENCE_INCOMPLETE" in envelope.blockers
    assert "NO_TRADE_WEAK_EVIDENCE" in envelope.blockers
    assert tuple(item.evidence_id for item in envelope.evidence_packet.evidence) == (
        "agent:trend",
        "deterministic_decision",
    )
    assert envelope.kept_sources == ("deterministic_decision", "agent:trend")
    assert envelope.token_usage is not None
    assert envelope.token_usage.total > 0


def test_canonical_analysis_envelope_rejects_authority_drift() -> None:
    envelope = CanonicalAnalysisEnvelope.from_analysis_state(analysis_state())
    with pytest.raises(ValueError, match="packet mismatch"):
        replace(envelope, symbol="BTCUSDT")
    with pytest.raises(ValueError, match="promote"):
        replace(envelope, promotion_status="STAGED_CANDIDATE")
    with pytest.raises(ValueError, match="promote"):
        replace(envelope, execution_allowed=True)
    with pytest.raises(ValueError, match="live blocked"):
        replace(envelope, live_eligibility_status="EXECUTION_ALLOWED")


def opinions(value: AdvisoryEvidencePacket) -> tuple[AdvisoryOpinion, ...]:
    return tuple(
        AdvisoryOpinion(
            role,
            value.packet_hash,
            f"{role.value} critique",
            0.7,
            ("trend",),
            ("validate regime split",),
        )
        for role in AdvisoryRole
    )


def test_advisory_synthesis_preserves_core_blockers_and_has_no_authority() -> None:
    evidence = packet()
    result = AdvisoryEngine().synthesize(evidence, opinions(evidence))
    assert result.blockers == ("OOS_EVIDENCE_INCOMPLETE",)
    assert result.disagreements == ("BULL_BEAR_CONFLICT",)
    assert result.proposed_experiments == ("validate regime split",)
    assert result.execution_allowed is False
    assert result.promotion_status == "RESEARCH_ONLY"


def test_advisory_synthesis_rejects_llm_execution_authority_claims() -> None:
    evidence = packet()
    result = AdvisoryEngine().synthesize(evidence, opinions(evidence))

    with pytest.raises(ValueError, match="no promotion or execution authority"):
        replace(result, execution_allowed=True)
    with pytest.raises(ValueError, match="no promotion or execution authority"):
        replace(result, promotion_status="PAPER_APPROVED")


def test_advisory_rejects_missing_roles_bad_packet_and_citations() -> None:
    evidence = packet()
    incomplete = opinions(evidence)[:2]
    bad = replace(incomplete[0], packet_hash="wrong", cited_evidence_ids=("invented",))
    result = AdvisoryEngine().synthesize(evidence, (bad, incomplete[1]))
    assert "ADVISORY_ROLE_MISSING" in result.blockers
    assert "ADVISORY_PACKET_MISMATCH" in result.blockers
    assert "ADVISORY_CITATION_INVALID" in result.blockers


def test_advisory_checkpoint_is_packet_bound_and_retry_bounded() -> None:
    store = InMemoryAdvisoryCheckpointStore(retry_budget=2)
    checkpoint = AdvisoryCheckpoint("request-1", packet().packet_hash, (), 1)
    store.save(checkpoint)
    assert store.load("request-1") == checkpoint
    with pytest.raises(ValueError, match="packet mismatch"):
        store.save(replace(checkpoint, packet_hash="other", attempts=2))
    with pytest.raises(ValueError, match="retry budget"):
        store.save(replace(checkpoint, attempts=3))


def test_advisory_evidence_rejects_future_or_tampered_content() -> None:
    evidence = packet()
    future_item = EvidenceItem.create(
        "future", "provider", NOW + timedelta(seconds=1), "future"
    )
    with pytest.raises(ValueError, match="future"):
        AdvisoryEvidencePacket.create(
            snapshot_id="snapshot-1",
            symbol="HOTUSDT",
            as_of=NOW,
            evidence=(future_item,),
        )
    with pytest.raises(ValueError, match="hash"):
        replace(evidence.evidence[0], summary="tampered")


def test_advisory_contracts_reject_invalid_shapes() -> None:
    evidence = packet()
    with pytest.raises(ValueError, match="identity"):
        replace(evidence.evidence[0], evidence_id=" ")
    with pytest.raises(ValueError, match="identity and evidence"):
        AdvisoryEvidencePacket.create(
            snapshot_id="snapshot-1", symbol="HOTUSDT", as_of=NOW, evidence=()
        )
    with pytest.raises(ValueError, match="unique and sorted"):
        replace(evidence, evidence=(evidence.evidence[0], evidence.evidence[0]))
    with pytest.raises(ValueError, match="packet hash"):
        replace(evidence, packet_hash="bad")
    with pytest.raises(ValueError, match="bounded"):
        replace(opinions(evidence)[0], confidence=2.0)
    with pytest.raises(ValueError, match="citations"):
        replace(opinions(evidence)[0], cited_evidence_ids=())
    with pytest.raises(ValueError, match="retry budget"):
        InMemoryAdvisoryCheckpointStore(retry_budget=11)
    with pytest.raises(ValueError, match="attempts cannot be negative"):
        AdvisoryCheckpoint("request", evidence.packet_hash, (), -1)


def test_advisory_duplicate_roles_and_checkpoint_attempt_regression_block() -> None:
    evidence = packet()
    bull = opinions(evidence)[0]
    result = AdvisoryEngine(required_roles=(AdvisoryRole.BULL,)).synthesize(
        evidence, (bull, bull)
    )
    assert "ADVISORY_DUPLICATE_ROLE" in result.blockers

    store = InMemoryAdvisoryCheckpointStore(retry_budget=3)
    checkpoint = AdvisoryCheckpoint("request", evidence.packet_hash, (), 2)
    store.save(checkpoint)
    with pytest.raises(ValueError, match="move backwards"):
        store.save(replace(checkpoint, attempts=1))

"""Fail-closed replay tests for external on-chain provider envelopes."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.whale_fusion.onchain import (
    Chain,
    OnChainProviderEnvelope,
    OnChainProviderReplay,
    OnChainProviderReplayPolicy,
    OnChainProviderReplayResult,
)

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
POLICY = OnChainProviderReplayPolicy(
    allowed_provider_ids=frozenset({"REPLAY_PROVIDER"}),
    allowed_hosts=frozenset({"provider.example"}),
    max_observation_age=timedelta(minutes=10),
    max_future_skew=timedelta(seconds=30),
    minimum_confirmations=12,
)


def envelope(
    *,
    event_at: datetime = NOW - timedelta(seconds=10),
    received_at: datetime = NOW,
    confirmations: int = 12,
    tx_hash: str = "0xabc",
    usd_value: object = "1500000",
) -> OnChainProviderEnvelope:
    payload: dict[str, object] = {
        "transfer_id": "provider-event-1",
        "chain": "ETHEREUM",
        "timestamp": int(event_at.timestamp() * 1000),
        "tx_hash": tx_hash,
        "from_address": "0xFrom",
        "to_address": "0xTo",
        "asset": "HOT",
        "amount": "1000000",
        "usd_value": usd_value,
        "attributes": {"provider_event_id": "event-1"},
    }
    return OnChainProviderEnvelope.from_payload(
        provider_id="REPLAY_PROVIDER",
        source_url="https://provider.example/v1/transfers",
        received_at=received_at,
        event_at=event_at,
        chain=Chain.ETHEREUM,
        tx_hash=tx_hash,
        block_height=123,
        log_index=4,
        confirmations=confirmations,
        payload=payload,
    )


def test_provider_envelope_accepts_only_immutable_provenance_bound_transfer() -> None:
    result = OnChainProviderReplay(POLICY).ingest(envelope(), as_of=NOW)

    assert result.accepted is True
    assert result.transfer is not None
    assert result.transfer.provenance.source_id == "REPLAY_PROVIDER"
    assert (
        result.transfer.provenance.source_url == "https://provider.example/v1/transfers"
    )
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.execution_allowed is False
    with pytest.raises(TypeError):
        result.envelope.payload["asset"] = "USDT"  # type: ignore[index]


@pytest.mark.parametrize(
    ("item", "expected_blocker"),
    [
        (
            envelope(confirmations=11),
            "CHAIN_FINALITY_INSUFFICIENT",
        ),
        (
            envelope(received_at=NOW - timedelta(minutes=11)),
            "PROVIDER_OBSERVATION_STALE",
        ),
        (
            envelope(event_at=NOW + timedelta(seconds=31)),
            "PROVIDER_EVENT_AFTER_AS_OF",
        ),
        (
            envelope(usd_value=None),
            "USD_VALUE_UNKNOWN",
        ),
    ],
)
def test_provider_replay_fails_closed_for_incomplete_or_unsafe_evidence(
    item: OnChainProviderEnvelope, expected_blocker: str
) -> None:
    result = OnChainProviderReplay(POLICY).ingest(item, as_of=NOW)

    assert result.accepted is False
    assert result.transfer is None
    assert expected_blocker in result.blockers
    assert result.execution_allowed is False


def test_provider_replay_rejects_untrusted_source_and_payload_inconsistency() -> None:
    untrusted = OnChainProviderEnvelope.from_payload(
        provider_id="OTHER_PROVIDER",
        source_url="https://other.example/v1/transfers",
        received_at=NOW,
        event_at=NOW,
        chain=Chain.ETHEREUM,
        tx_hash="0xabc",
        block_height=1,
        log_index=0,
        confirmations=20,
        payload={
            "transfer_id": "other-1",
            "chain": "ETHEREUM",
            "timestamp": int(NOW.timestamp() * 1000),
            "tx_hash": "0xabc",
            "from_address": "0xFrom",
            "to_address": "0xTo",
            "asset": "HOT",
            "amount": "1",
            "usd_value": "1",
        },
    )
    untrusted_result = OnChainProviderReplay(POLICY).ingest(untrusted, as_of=NOW)
    assert untrusted_result.blockers == (
        "PROVIDER_NOT_ALLOWED",
        "PROVIDER_HOST_NOT_ALLOWED",
    )

    mismatched = envelope(tx_hash="0xexpected")
    mismatched_payload = dict(mismatched.payload)
    mismatched_payload["tx_hash"] = "0xother"
    mismatch = OnChainProviderEnvelope.from_payload(
        provider_id=mismatched.provider_id,
        source_url=mismatched.source_url,
        received_at=mismatched.received_at,
        event_at=mismatched.event_at,
        chain=mismatched.chain,
        tx_hash=mismatched.tx_hash,
        block_height=mismatched.block_height,
        log_index=mismatched.log_index,
        confirmations=mismatched.confirmations,
        payload=mismatched_payload,
    )
    assert OnChainProviderReplay(POLICY).ingest(mismatch, as_of=NOW).blockers == (
        "PROVIDER_TX_HASH_MISMATCH",
    )


def test_provider_replay_is_deterministic_and_quarantines_duplicate_chain_events() -> (
    None
):
    first = envelope(event_at=NOW - timedelta(seconds=20), tx_hash="0xfirst")
    duplicate = replace(first)
    later = envelope(event_at=NOW - timedelta(seconds=10), tx_hash="0xlater")

    results = OnChainProviderReplay(POLICY).replay((later, duplicate, first), as_of=NOW)

    assert tuple(result.envelope.tx_hash for result in results) == (
        "0xfirst",
        "0xfirst",
        "0xlater",
    )
    assert results[0].accepted is True
    assert results[1].blockers == ("PROVIDER_EVENT_DUPLICATE",)
    assert results[2].accepted is True


def test_provider_envelope_rejects_tampered_hash_and_result_cannot_gain_authority() -> (
    None
):
    item = envelope()
    with pytest.raises(ValueError, match="SHA-256"):
        OnChainProviderEnvelope(
            provider_id=item.provider_id,
            source_url=item.source_url,
            received_at=item.received_at,
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=item.tx_hash,
            block_height=item.block_height,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload=item.payload,
            payload_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="execution authority"):
        OnChainProviderReplayResult(item, None, (), execution_allowed=True)

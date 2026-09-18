"""Fail-closed replay tests for external on-chain provider envelopes."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from ai4binance.exchange.errors import ExchangePayloadError
from ai4binance.whale_fusion.models import Provenance
from ai4binance.whale_fusion.onchain import (
    CanonicalTransferNormalizer,
    Chain,
    OnChainProviderEnvelope,
    OnChainProviderReplay,
    OnChainProviderReplayPolicy,
    OnChainProviderReplayResult,
    OnChainTransfer,
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


def test_provider_envelope_canonicalizes_nested_sequences_without_authority() -> None:
    item = envelope()
    payload = dict(item.payload)
    payload["provider_tags"] = ["whale", {"tier": "research"}]

    replayable = OnChainProviderEnvelope.from_payload(
        provider_id=item.provider_id,
        source_url=item.source_url,
        received_at=item.received_at,
        event_at=item.event_at,
        chain=item.chain,
        tx_hash=item.tx_hash,
        block_height=item.block_height,
        log_index=item.log_index,
        confirmations=item.confirmations,
        payload=payload,
    )

    assert replayable.payload["provider_tags"] == ["whale", {"tier": "research"}]
    assert replayable.event_key == (Chain.ETHEREUM, "0xabc", 4)
    assert replayable.source_host == "provider.example"


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


def test_provider_envelope_rejects_invalid_identity_payload_and_timestamps() -> None:
    item = envelope()
    with pytest.raises(ValueError, match="provider_id"):
        OnChainProviderEnvelope.from_payload(
            provider_id="provider-with-dash",
            source_url=item.source_url,
            received_at=item.received_at,
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=item.tx_hash,
            block_height=item.block_height,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload=dict(item.payload),
        )
    with pytest.raises(ValueError, match="HTTPS"):
        OnChainProviderEnvelope.from_payload(
            provider_id=item.provider_id,
            source_url="http://provider.example/v1/transfers",
            received_at=item.received_at,
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=item.tx_hash,
            block_height=item.block_height,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload=dict(item.payload),
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        OnChainProviderEnvelope.from_payload(
            provider_id=item.provider_id,
            source_url=item.source_url,
            received_at=NOW.replace(tzinfo=None),
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=item.tx_hash,
            block_height=item.block_height,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload=dict(item.payload),
        )
    with pytest.raises(ValueError, match="tx_hash"):
        OnChainProviderEnvelope.from_payload(
            provider_id=item.provider_id,
            source_url=item.source_url,
            received_at=item.received_at,
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=" ",
            block_height=item.block_height,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload=dict(item.payload),
        )
    with pytest.raises(ValueError, match="block metadata"):
        OnChainProviderEnvelope.from_payload(
            provider_id=item.provider_id,
            source_url=item.source_url,
            received_at=item.received_at,
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=item.tx_hash,
            block_height=True,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload=dict(item.payload),
        )
    with pytest.raises(ValueError, match="strict JSON"):
        OnChainProviderEnvelope.from_payload(
            provider_id=item.provider_id,
            source_url=item.source_url,
            received_at=item.received_at,
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=item.tx_hash,
            block_height=item.block_height,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload={"bad": object()},
        )
    with pytest.raises(ValueError, match="strict JSON"):
        OnChainProviderEnvelope.from_payload(
            provider_id=item.provider_id,
            source_url=item.source_url,
            received_at=item.received_at,
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=item.tx_hash,
            block_height=item.block_height,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload={"nested": {1: "bad"}},
        )
    with pytest.raises(ValueError, match="payload must be an object"):
        OnChainProviderEnvelope.from_payload(
            provider_id=item.provider_id,
            source_url=item.source_url,
            received_at=item.received_at,
            event_at=item.event_at,
            chain=item.chain,
            tx_hash=item.tx_hash,
            block_height=item.block_height,
            log_index=item.log_index,
            confirmations=item.confirmations,
            payload=cast(dict[str, object], []),
        )
    replayable = envelope()
    object.__setattr__(replayable, "source_url", "https:///")
    with pytest.raises(ValueError, match="hostname missing"):
        _ = replayable.source_host


def test_provider_replay_policy_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="provider IDs"):
        OnChainProviderReplayPolicy(allowed_provider_ids=frozenset({""}))
    with pytest.raises(ValueError, match="hostnames only"):
        OnChainProviderReplayPolicy(allowed_hosts=frozenset({"provider.example/v1"}))
    with pytest.raises(ValueError, match="max_payload_bytes"):
        OnChainProviderReplayPolicy(max_payload_bytes=0)
    with pytest.raises(ValueError, match="max_observation_age"):
        OnChainProviderReplayPolicy(max_observation_age=timedelta(0))
    with pytest.raises(ValueError, match="max_future_skew"):
        OnChainProviderReplayPolicy(max_future_skew=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="minimum_confirmations"):
        OnChainProviderReplayPolicy(minimum_confirmations=-1)


def test_provider_replay_blocks_future_observation_and_payload_size() -> None:
    item = envelope(
        received_at=NOW + timedelta(seconds=31),
        event_at=NOW + timedelta(seconds=40),
    )
    tiny_policy = OnChainProviderReplayPolicy(
        allowed_provider_ids=frozenset({"REPLAY_PROVIDER"}),
        allowed_hosts=frozenset({"provider.example"}),
        max_payload_bytes=10,
        max_observation_age=timedelta(minutes=10),
        max_future_skew=timedelta(seconds=30),
        minimum_confirmations=12,
    )

    result = OnChainProviderReplay(tiny_policy).ingest(item, as_of=NOW)

    assert result.blockers == (
        "PROVIDER_PAYLOAD_TOO_LARGE",
        "PROVIDER_OBSERVED_AFTER_AS_OF",
        "PROVIDER_EVENT_AFTER_AS_OF",
    )


def test_provider_replay_rejects_invalid_normalized_payload() -> None:
    result = OnChainProviderReplay(
        POLICY,
        cast(CanonicalTransferNormalizer, _InvalidNormalizer()),
    ).ingest(
        envelope(),
        as_of=NOW,
    )

    assert result.accepted is False
    assert result.blockers == ("PROVIDER_PAYLOAD_INVALID",)


def test_provider_replay_reports_consistency_mismatches() -> None:
    result = OnChainProviderReplay(
        POLICY,
        cast(CanonicalTransferNormalizer, _MismatchNormalizer()),
    ).ingest(
        envelope(),
        as_of=NOW,
    )

    assert result.accepted is False
    assert result.blockers == (
        "PROVIDER_CHAIN_MISMATCH",
        "PROVIDER_TX_HASH_MISMATCH",
        "PROVIDER_TIMESTAMP_MISMATCH",
        "USD_VALUE_UNKNOWN",
    )


def test_provider_replay_result_rejects_accepted_transfer_with_blockers() -> None:
    item = envelope()
    transfer = _transfer(
        chain=item.chain,
        tx_hash=item.tx_hash,
        timestamp=item.event_at,
        usd_value=Decimal("1"),
    )

    with pytest.raises(ValueError, match="accepted provider result"):
        OnChainProviderReplayResult(item, transfer, ("BLOCKED",))


class _InvalidNormalizer:
    def normalize(
        self,
        payload: object,
        *,
        provenance: Provenance,
    ) -> OnChainTransfer:
        del payload, provenance
        raise ExchangePayloadError("invalid")


class _MismatchNormalizer:
    def normalize(
        self,
        payload: object,
        *,
        provenance: Provenance,
    ) -> OnChainTransfer:
        del payload
        return _transfer(
            chain=Chain.BNB_SMART_CHAIN,
            tx_hash="0xother",
            timestamp=NOW - timedelta(minutes=1),
            usd_value=None,
            provenance=provenance,
        )


def _transfer(
    *,
    chain: Chain,
    tx_hash: str,
    timestamp: datetime,
    usd_value: Decimal | None,
    provenance: Provenance | None = None,
) -> OnChainTransfer:
    return OnChainTransfer(
        transfer_id="transfer-1",
        chain=chain,
        timestamp=timestamp,
        tx_hash=tx_hash,
        from_address="0xfrom",
        to_address="0xto",
        asset="HOT",
        amount=Decimal("1"),
        usd_value=usd_value,
        provenance=provenance or Provenance("TEST", NOW, "https://provider.example"),
    )

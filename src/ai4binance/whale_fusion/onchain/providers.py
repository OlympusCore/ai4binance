"""Fail-closed, replayable provider envelopes for on-chain whale research.

This module deliberately contains no network client or provider credential.  A
provider-specific outer adapter must construct an immutable envelope, then this
module verifies provenance, bounded raw input, finality, freshness, and
canonical-transfer consistency before the existing classifier may consume it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from types import MappingProxyType
from urllib.parse import urlparse

from ai4binance.core.errors import ExchangePayloadError
from ai4binance.whale_fusion.models import Provenance
from ai4binance.whale_fusion.onchain.models import Chain, OnChainTransfer
from ai4binance.whale_fusion.onchain.normalizer import CanonicalTransferNormalizer


def _json_safe(value: object) -> object:
    """Convert immutable mappings back to strict JSON-compatible structures."""
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("provider payload object keys must be strings")
            normalized[key] = _json_safe(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("provider payload must contain JSON scalar values")


def _canonical_payload_bytes(payload: Mapping[str, object]) -> bytes:
    """Encode bounded provider input deterministically or reject it."""
    try:
        encoded = json.dumps(
            _json_safe(payload),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("provider payload must be strict JSON") from exc
    return encoded.encode("utf-8")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OnChainProviderEnvelope:
    """A provider event with integrity material required for deterministic replay."""

    provider_id: str
    source_url: str
    received_at: datetime
    event_at: datetime
    chain: Chain
    tx_hash: str
    block_height: int
    log_index: int
    confirmations: int
    payload: Mapping[str, object]
    payload_sha256: str

    def __post_init__(self) -> None:
        provider_id = self.provider_id.strip().upper()
        if (
            not provider_id
            or not provider_id.isascii()
            or any(
                not (item.isupper() or item.isdigit() or item == "_")
                for item in provider_id
            )
        ):
            raise ValueError("provider_id must be uppercase ASCII identifier")
        parsed_url = urlparse(self.source_url.strip())
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise ValueError("provider source_url must be HTTPS with a hostname")
        _require_aware(self.received_at, "provider received_at")
        _require_aware(self.event_at, "provider event_at")
        if not self.tx_hash.strip():
            raise ValueError("provider tx_hash cannot be empty")
        if (
            isinstance(self.block_height, bool)
            or isinstance(self.log_index, bool)
            or isinstance(self.confirmations, bool)
            or self.block_height < 0
            or self.log_index < 0
            or self.confirmations < 0
        ):
            raise ValueError("provider block metadata must be non-negative integers")
        payload_bytes = _canonical_payload_bytes(self.payload)
        digest = sha256(payload_bytes).hexdigest()
        if self.payload_sha256.lower() != digest:
            raise ValueError("provider payload SHA-256 mismatch")
        normalized_payload = json.loads(payload_bytes)
        if not isinstance(normalized_payload, dict):
            raise ValueError("provider payload must be an object")
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "source_url", self.source_url.strip())
        object.__setattr__(self, "tx_hash", self.tx_hash.strip().lower())
        object.__setattr__(self, "payload", MappingProxyType(normalized_payload))
        object.__setattr__(self, "payload_sha256", digest)

    @classmethod
    def from_payload(
        cls,
        *,
        provider_id: str,
        source_url: str,
        received_at: datetime,
        event_at: datetime,
        chain: Chain,
        tx_hash: str,
        block_height: int,
        log_index: int,
        confirmations: int,
        payload: Mapping[str, object],
    ) -> OnChainProviderEnvelope:
        """Create an envelope while hashing the exact canonical payload."""
        return cls(
            provider_id=provider_id,
            source_url=source_url,
            received_at=received_at,
            event_at=event_at,
            chain=chain,
            tx_hash=tx_hash,
            block_height=block_height,
            log_index=log_index,
            confirmations=confirmations,
            payload=payload,
            payload_sha256=sha256(_canonical_payload_bytes(payload)).hexdigest(),
        )

    @property
    def event_key(self) -> tuple[Chain, str, int]:
        """Chain-native idempotency key; provider identity is intentionally excluded."""
        return (self.chain, self.tx_hash, self.log_index)

    @property
    def source_host(self) -> str:
        host = urlparse(self.source_url).hostname
        if host is None:  # guarded in __post_init__; keeps the property total.
            raise ValueError("provider source_url hostname missing")
        return host.lower()


@dataclass(frozen=True, slots=True)
class OnChainProviderReplayPolicy:
    """Explicit allowlists and temporal bounds for one provider-replay run."""

    allowed_provider_ids: frozenset[str] = frozenset()
    allowed_hosts: frozenset[str] = frozenset()
    max_payload_bytes: int = 32_768
    max_observation_age: timedelta = timedelta(minutes=15)
    max_future_skew: timedelta = timedelta(seconds=30)
    minimum_confirmations: int = 12
    require_usd_value: bool = True

    def __post_init__(self) -> None:
        provider_ids = frozenset(
            item.strip().upper() for item in self.allowed_provider_ids
        )
        hosts = frozenset(item.strip().lower() for item in self.allowed_hosts)
        if not all(item and item.isascii() for item in provider_ids):
            raise ValueError("allowed provider IDs must be non-empty ASCII values")
        if not all(item and "/" not in item for item in hosts):
            raise ValueError("allowed hosts must contain hostnames only")
        if self.max_payload_bytes <= 0:
            raise ValueError("max_payload_bytes must be positive")
        if self.max_observation_age <= timedelta(0):
            raise ValueError("max_observation_age must be positive")
        if self.max_future_skew < timedelta(0):
            raise ValueError("max_future_skew cannot be negative")
        if self.minimum_confirmations < 0:
            raise ValueError("minimum_confirmations cannot be negative")
        object.__setattr__(self, "allowed_provider_ids", provider_ids)
        object.__setattr__(self, "allowed_hosts", hosts)


@dataclass(frozen=True, slots=True)
class OnChainProviderReplayResult:
    """One safe provider-ingestion outcome; no outcome can authorize trading."""

    envelope: OnChainProviderEnvelope
    transfer: OnChainTransfer | None
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.transfer is not None and self.blockers:
            raise ValueError("accepted provider result cannot contain blockers")
        if self.execution_allowed or self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("provider replay cannot grant execution authority")

    @property
    def accepted(self) -> bool:
        return self.transfer is not None and not self.blockers


@dataclass(frozen=True, slots=True)
class OnChainProviderReplay:
    """Validate and replay envelopes without network or persistent side effects."""

    policy: OnChainProviderReplayPolicy
    normalizer: CanonicalTransferNormalizer = field(
        default_factory=CanonicalTransferNormalizer
    )

    def ingest(
        self,
        envelope: OnChainProviderEnvelope,
        *,
        as_of: datetime,
    ) -> OnChainProviderReplayResult:
        """Accept one envelope only when all provenance and freshness gates pass."""
        _require_aware(as_of, "provider replay as_of")
        blockers = self._blockers(envelope, as_of=as_of)
        if blockers:
            return OnChainProviderReplayResult(envelope, None, blockers)
        try:
            transfer = self.normalizer.normalize(
                envelope.payload,
                provenance=Provenance(
                    envelope.provider_id, envelope.received_at, envelope.source_url
                ),
            )
        except (ExchangePayloadError, ValueError):
            return OnChainProviderReplayResult(
                envelope, None, ("PROVIDER_PAYLOAD_INVALID",)
            )
        consistency_blockers = self._consistency_blockers(envelope, transfer)
        if consistency_blockers:
            return OnChainProviderReplayResult(envelope, None, consistency_blockers)
        return OnChainProviderReplayResult(envelope, transfer, ())

    def replay(
        self,
        envelopes: Iterable[OnChainProviderEnvelope],
        *,
        as_of: datetime,
    ) -> tuple[OnChainProviderReplayResult, ...]:
        """Replay deterministically and quarantine duplicate chain events."""
        ordered = tuple(
            sorted(
                envelopes,
                key=lambda item: (
                    item.event_at,
                    item.chain.value,
                    item.tx_hash,
                    item.log_index,
                    item.provider_id,
                ),
            )
        )
        seen: set[tuple[Chain, str, int]] = set()
        results: list[OnChainProviderReplayResult] = []
        for envelope in ordered:
            if envelope.event_key in seen:
                results.append(
                    OnChainProviderReplayResult(
                        envelope, None, ("PROVIDER_EVENT_DUPLICATE",)
                    )
                )
                continue
            seen.add(envelope.event_key)
            results.append(self.ingest(envelope, as_of=as_of))
        return tuple(results)

    def _blockers(
        self,
        envelope: OnChainProviderEnvelope,
        *,
        as_of: datetime,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if envelope.provider_id not in self.policy.allowed_provider_ids:
            blockers.append("PROVIDER_NOT_ALLOWED")
        if envelope.source_host not in self.policy.allowed_hosts:
            blockers.append("PROVIDER_HOST_NOT_ALLOWED")
        if (
            len(_canonical_payload_bytes(envelope.payload))
            > self.policy.max_payload_bytes
        ):
            blockers.append("PROVIDER_PAYLOAD_TOO_LARGE")
        if envelope.received_at > as_of + self.policy.max_future_skew:
            blockers.append("PROVIDER_OBSERVED_AFTER_AS_OF")
        elif as_of - envelope.received_at > self.policy.max_observation_age:
            blockers.append("PROVIDER_OBSERVATION_STALE")
        if envelope.event_at > as_of + self.policy.max_future_skew:
            blockers.append("PROVIDER_EVENT_AFTER_AS_OF")
        if envelope.event_at > envelope.received_at + self.policy.max_future_skew:
            blockers.append("PROVIDER_EVENT_AFTER_OBSERVATION")
        if envelope.confirmations < self.policy.minimum_confirmations:
            blockers.append("CHAIN_FINALITY_INSUFFICIENT")
        return tuple(blockers)

    def _consistency_blockers(
        self,
        envelope: OnChainProviderEnvelope,
        transfer: OnChainTransfer,
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        if transfer.chain is not envelope.chain:
            blockers.append("PROVIDER_CHAIN_MISMATCH")
        if transfer.tx_hash.strip().lower() != envelope.tx_hash:
            blockers.append("PROVIDER_TX_HASH_MISMATCH")
        if transfer.timestamp != envelope.event_at:
            blockers.append("PROVIDER_TIMESTAMP_MISMATCH")
        if self.policy.require_usd_value and transfer.usd_value is None:
            blockers.append("USD_VALUE_UNKNOWN")
        return tuple(blockers)

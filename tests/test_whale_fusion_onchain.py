"""WHALE-FUSION Phase 4 on-chain normalization and classification tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.exchange.errors import ExchangePayloadError
from ai4binance.whale_fusion import Provenance, WhaleEventType
from ai4binance.whale_fusion.onchain import (
    AddressRole,
    CanonicalTransferNormalizer,
    Chain,
    OnChainClassifier,
    OnChainClassifierConfig,
    OnChainTransfer,
    WalletLabel,
    WalletRegistry,
    WhaleEvent,
)

NOW = datetime(2026, 7, 13, tzinfo=UTC)
SOURCE = Provenance("TEST_CHAIN_PROVIDER", NOW, "https://provider.example")


def label(address: str, role: AddressRole) -> WalletLabel:
    return WalletLabel(
        Chain.ETHEREUM,
        address,
        role.value,
        role,
        Decimal("0.9"),
        SOURCE,
    )


def registry() -> WalletRegistry:
    return WalletRegistry.from_labels(
        (
            label("0xwhale", AddressRole.WHALE),
            label("0xbinance", AddressRole.BINANCE),
            label("0xdex", AddressRole.DEX),
            label("0xbridge", AddressRole.BRIDGE),
            label("0xstaking", AddressRole.STAKING),
            label("0xunlock", AddressRole.TOKEN_UNLOCK),
            label("0xmm", AddressRole.MARKET_MAKER),
        )
    )


def transfer(
    *,
    transfer_id: str = "transfer-1",
    source: str = "0xwhale",
    target: str = "0xunknown",
    asset: str = "HOT",
    usd_value: Decimal | None = Decimal("2000000"),
    timestamp: datetime = NOW,
    stablecoin: bool = False,
    new_wallet: bool = False,
) -> OnChainTransfer:
    return OnChainTransfer(
        transfer_id=transfer_id,
        chain=Chain.ETHEREUM,
        timestamp=timestamp,
        tx_hash=f"tx-{transfer_id}",
        from_address=source,
        to_address=target,
        asset=asset,
        amount=Decimal("100"),
        usd_value=usd_value,
        provenance=SOURCE,
        is_stablecoin=stablecoin,
        to_is_new_wallet=new_wallet,
    )


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (transfer(target="0xbinance"), WhaleEventType.WHALE_TO_BINANCE),
        (
            transfer(target="0xbinance", asset="USDT", stablecoin=True),
            WhaleEventType.STABLECOIN_EXCHANGE_DEPOSIT,
        ),
        (
            transfer(source="0xbinance", target="0xwhale"),
            WhaleEventType.BINANCE_TO_WHALE,
        ),
        (transfer(target="0xdex"), WhaleEventType.WHALE_TO_DEX),
        (transfer(target="0xbridge"), WhaleEventType.BRIDGE_TRANSFER),
        (
            transfer(source="0xstaking", target="0xwhale"),
            WhaleEventType.STAKING_EXIT,
        ),
        (
            transfer(source="0xunlock", target="0xwhale"),
            WhaleEventType.TOKEN_UNLOCK_MOVEMENT,
        ),
        (transfer(target="0xmm"), WhaleEventType.MARKET_MAKER_MOVEMENT),
        (
            transfer(target="0xwhale", asset="USDC", stablecoin=True),
            WhaleEventType.STABLECOIN_ACCUMULATION,
        ),
        (transfer(target="0xwhale"), WhaleEventType.TOKEN_ACCUMULATION),
        (transfer(), WhaleEventType.TOKEN_DISTRIBUTION),
    ],
)
def test_classifier_maps_wallet_roles_to_expected_events(
    item: OnChainTransfer, expected: WhaleEventType
) -> None:
    event = OnChainClassifier(registry()).classify(item)[0]
    assert event.event_type is expected
    assert event.promotion_status == "RESEARCH_ONLY"
    assert event.execution_allowed is False


def test_classifier_blocks_unknown_value_and_below_threshold() -> None:
    classifier = OnChainClassifier(registry())
    assert classifier.classify(transfer(usd_value=None)) == ()
    assert classifier.classify(transfer(usd_value=Decimal("999999"))) == ()
    assert classifier.evaluate(transfer(usd_value=None)).blockers == (
        "USD_VALUE_UNKNOWN",
    )
    assert classifier.evaluate(transfer(usd_value=Decimal("999999"))).blockers == (
        "BELOW_WHALE_THRESHOLD",
    )


def test_new_wallet_emits_additional_event_with_deterministic_id() -> None:
    classifier = OnChainClassifier(registry())
    events = classifier.classify(transfer(new_wallet=True))
    assert tuple(event.event_type for event in events) == (
        WhaleEventType.TOKEN_DISTRIBUTION,
        WhaleEventType.NEW_WALLET,
    )
    assert events == classifier.classify(transfer(new_wallet=True))


def test_split_transfer_detector_requires_cluster_and_total_threshold() -> None:
    classifier = OnChainClassifier(
        registry(),
        OnChainClassifierConfig(
            minimum_whale_usd=Decimal("1000000"),
            split_minimum_count=3,
            split_window=timedelta(minutes=30),
        ),
    )
    transfers = tuple(
        transfer(
            transfer_id=f"part-{index}",
            usd_value=Decimal("400000"),
            timestamp=NOW + timedelta(minutes=index * 5),
        )
        for index in range(3)
    )
    event = classifier.detect_split_transfers(transfers)[0]
    assert event.event_type is WhaleEventType.SPLIT_TRANSFER
    assert event.usd_value == Decimal("1200000")
    assert event.transfer_ids == ("part-0", "part-1", "part-2")
    assert classifier.detect_split_transfers(transfers[:2]) == ()
    assert (
        classifier.detect_split_transfers(
            (*transfers[:2], replace(transfers[2], asset="USDT"))
        )
        == ()
    )


def test_normalizer_accepts_canonical_payload_and_rejects_bad_types() -> None:
    normalizer = CanonicalTransferNormalizer()
    payload: dict[str, object] = {
        "transfer_id": "canonical-1",
        "chain": "ETHEREUM",
        "timestamp": 1000,
        "tx_hash": "0xtx",
        "from_address": "0xFrom",
        "to_address": "0xTo",
        "asset": "usdt",
        "amount": "100",
        "usd_value": "100",
        "to_is_new_wallet": True,
        "attributes": {"block": "1"},
    }
    result = normalizer.normalize(payload, provenance=SOURCE)
    assert result.asset == "USDT"
    assert result.is_stablecoin is True
    assert result.from_address == "0xfrom"

    with pytest.raises(ExchangePayloadError, match="timestamp"):
        normalizer.normalize({**payload, "timestamp": "bad"}, provenance=SOURCE)
    with pytest.raises(ExchangePayloadError, match="attributes"):
        normalizer.normalize({**payload, "attributes": {"block": 1}}, provenance=SOURCE)


def test_registry_and_event_contract_fail_closed() -> None:
    duplicate = label("0xwhale", AddressRole.WHALE)
    with pytest.raises(ValueError, match="unique"):
        WalletRegistry((duplicate, duplicate))
    assert registry().role(Chain.ETHEREUM, "0xmissing") is AddressRole.UNKNOWN

    classified = OnChainClassifier(registry()).classify(transfer())[0]
    with pytest.raises(ValueError, match="execution authority"):
        WhaleEvent(
            event_id=classified.event_id,
            event_type=classified.event_type,
            chain=classified.chain,
            timestamp=classified.timestamp,
            asset=classified.asset,
            amount=classified.amount,
            usd_value=classified.usd_value,
            transfer_ids=classified.transfer_ids,
            confidence=classified.confidence,
            provenance=classified.provenance,
            reason_codes=classified.reason_codes,
            execution_allowed=True,
        )

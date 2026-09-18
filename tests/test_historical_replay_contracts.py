"""Deterministic historical replay and wallet-epoch contract tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from ai4binance.research import (
    HistoricalMarketReplayRequest,
    HistoricalMarketSelection,
    HistoricalReplayDatasetBinding,
    HistoricalReplayEvidenceClass,
    HistoricalUniverseMode,
    VirtualMarket,
    VirtualSystemVersionSegment,
    VirtualWalletEpoch,
    VirtualWalletEpochStatus,
)

START = datetime(2025, 1, 1, tzinfo=UTC)
END = datetime(2025, 1, 2, tzinfo=UTC)
HASH = "a" * 64


def _system_version() -> VirtualSystemVersionSegment:
    return VirtualSystemVersionSegment(
        effective_at=START,
        code_revision="0123456789abcdef",
        configuration_sha256=HASH,
        strategy_bundle_sha256=HASH,
        feature_bundle_sha256=HASH,
        dge_rule_bundle_sha256=HASH,
        risk_policy_sha256=HASH,
        validation_policy_sha256=HASH,
        execution_model_sha256=HASH,
    )


def _selection(
    market: VirtualMarket,
    *,
    symbols: tuple[str, ...] = ("ETHUSDT", "BTCUSDT"),
) -> HistoricalMarketSelection:
    return HistoricalMarketSelection(market=market, symbols=symbols)


def _epoch(
    market: VirtualMarket,
    version: VirtualSystemVersionSegment,
    *,
    capital: str = "1000",
) -> VirtualWalletEpoch:
    suffix = "spot" if market is VirtualMarket.SPOT else "futures"
    return VirtualWalletEpoch(
        epoch_id=f"epoch:{suffix}:1",
        portfolio_id=f"portfolio:{suffix}:1",
        market=market,
        initial_capital_usdt=Decimal(capital),
        started_at=START,
        start_reason="HISTORICAL_REPLAY_INITIALIZATION",
        system_segment_sha256=version.semantic_sha256,
        evidence_class=HistoricalReplayEvidenceClass.HISTORICAL_REPLAY,
    )


def _binding(
    market: VirtualMarket,
    symbol: str,
    timeframe: str,
) -> HistoricalReplayDatasetBinding:
    return HistoricalReplayDatasetBinding(
        market=market,
        symbol=symbol,
        timeframe=timeframe,
        dataset_revision_id=f"dataset:{market.value.lower()}:{symbol}:{timeframe}",
        dataset_sha256=HASH,
        source_manifest_sha256=HASH,
        source_provenance_ref="BINANCE_PUBLIC_HISTORICAL_ARCHIVE",
        coverage_start=START - timedelta(days=1),
        coverage_end=END + timedelta(days=1),
        row_count=1440,
    )


def _request(*, reverse: bool = False) -> HistoricalMarketReplayRequest:
    version = _system_version()
    markets = (VirtualMarket.SPOT, VirtualMarket.USD_M_FUTURES)
    selections = tuple(_selection(market) for market in markets)
    datasets = tuple(
        _binding(market, symbol, timeframe)
        for market in markets
        for symbol in ("BTCUSDT", "ETHUSDT")
        for timeframe in ("1m", "1h")
    )
    epochs = tuple(_epoch(market, version) for market in markets)
    if reverse:
        selections = tuple(reversed(selections))
        datasets = tuple(reversed(datasets))
        epochs = tuple(reversed(epochs))
    return HistoricalMarketReplayRequest(
        run_id="historical-replay:test:1",
        start_at=START,
        end_at=END,
        timeframes=("1h", "1m") if reverse else ("1m", "1h"),
        market_selections=selections,
        dataset_bindings=datasets,
        wallet_epochs=epochs,
        system_version=version,
        random_seed=7,
    )


def test_replay_request_canonicalizes_order_and_has_stable_semantic_hash() -> None:
    first = _request()
    reordered = _request(reverse=True)

    assert first == reordered
    assert first.semantic_result_seed_sha256 == reordered.semantic_result_seed_sha256
    assert first.timeframes == ("1m", "1h")
    assert tuple(item.market for item in first.market_selections) == (
        VirtualMarket.SPOT,
        VirtualMarket.USD_M_FUTURES,
    )
    assert first.execution_allowed is False
    assert first.promotion_status == "RESEARCH_ONLY"
    assert first.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    ("market", "capital"),
    [
        (VirtualMarket.SPOT, "1000.00000001"),
        (VirtualMarket.USD_M_FUTURES, "1001"),
    ],
)
def test_wallet_epoch_rejects_market_wallet_cap_breach(
    market: VirtualMarket,
    capital: str,
) -> None:
    with pytest.raises(ValueError, match="at most 1000 USDT"):
        _epoch(market, _system_version(), capital=capital)


def test_replay_requires_exact_dataset_coverage_for_each_market() -> None:
    request = _request()

    with pytest.raises(ValueError, match="exactly cover the request"):
        replace(request, dataset_bindings=request.dataset_bindings[:-1])

    late = replace(
        request.dataset_bindings[0], coverage_start=START + timedelta(minutes=1)
    )
    with pytest.raises(ValueError, match="does not cover start_at"):
        replace(request, dataset_bindings=(late, *request.dataset_bindings[1:]))


def test_spot_and_futures_wallet_epochs_must_stay_independent() -> None:
    request = _request()
    futures = replace(
        request.wallet_epochs[1],
        portfolio_id=request.wallet_epochs[0].portfolio_id,
    )

    with pytest.raises(ValueError, match="portfolio ids must be independent"):
        replace(request, wallet_epochs=(request.wallet_epochs[0], futures))


def test_all_eligible_selection_requires_historical_universe_evidence() -> None:
    with pytest.raises(ValueError, match="historical universe evidence"):
        HistoricalMarketSelection(
            market=VirtualMarket.SPOT,
            symbols=("BTCUSDT",),
            universe_mode=HistoricalUniverseMode.ALL_ELIGIBLE,
        )

    selection = HistoricalMarketSelection(
        market=VirtualMarket.SPOT,
        symbols=("BTCUSDT",),
        universe_mode=HistoricalUniverseMode.ALL_ELIGIBLE,
        historical_universe_evidence_ref="listing-ledger:spot:2025-01-01",
        survivorship_bias_limitations=("DELISTING_HISTORY_INCOMPLETE",),
    )

    assert selection.to_payload()["survivorship_bias_limitations"] == [
        "DELISTING_HISTORY_INCOMPLETE"
    ]


def test_replay_rejects_unsupported_timeframe_and_non_utc_time() -> None:
    request = _request()
    with pytest.raises(ValueError, match="unsupported timeframes"):
        replace(request, timeframes=("2m",))

    non_utc = START.astimezone(timezone(timedelta(hours=3)))
    with pytest.raises(ValueError, match="canonical UTC"):
        replace(request, start_at=non_utc)


def test_wallet_epoch_finalization_and_live_authority_fail_closed() -> None:
    epoch = _epoch(VirtualMarket.SPOT, _system_version())
    finalized = replace(
        epoch,
        status=VirtualWalletEpochStatus.FINALIZED,
        finalized_at=END,
    )

    assert finalized.status is VirtualWalletEpochStatus.FINALIZED
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        replace(epoch, execution_allowed=True)
    with pytest.raises(ValueError, match="requires finalized_at"):
        replace(epoch, status=VirtualWalletEpochStatus.FINALIZED)


def test_replay_rejects_epoch_from_wrong_evidence_class_or_system_segment() -> None:
    request = _request()
    wrong_class = replace(
        request.wallet_epochs[0],
        evidence_class=HistoricalReplayEvidenceClass.FORWARD_VIRTUAL,
    )
    with pytest.raises(ValueError, match="requires HISTORICAL_REPLAY epochs"):
        replace(request, wallet_epochs=(wrong_class, request.wallet_epochs[1]))

    wrong_segment = replace(
        request.wallet_epochs[0],
        system_segment_sha256="b" * 64,
    )
    with pytest.raises(ValueError, match="system segment must match request"):
        replace(request, wallet_epochs=(wrong_segment, request.wallet_epochs[1]))


def test_system_version_rejects_invalid_identity_and_hashes() -> None:
    version = _system_version()
    with pytest.raises(ValueError, match="code revision"):
        replace(version, code_revision=" ")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(version, configuration_sha256="A" * 64)
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        replace(version, effective_at=START.replace(tzinfo=None))
    assert version.segment_id == f"system-segment:{version.semantic_sha256[:24]}"


def test_wallet_epoch_rejects_invalid_identity_lifecycle_and_authority() -> None:
    epoch = _epoch(VirtualMarket.SPOT, _system_version())
    with pytest.raises(ValueError, match="epoch id"):
        replace(epoch, epoch_id="")
    with pytest.raises(ValueError, match="portfolio id"):
        replace(epoch, portfolio_id="")
    with pytest.raises(ValueError, match="start reason"):
        replace(epoch, start_reason="")
    with pytest.raises(ValueError, match="system segment"):
        replace(epoch, system_segment_sha256="bad")
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        replace(epoch, started_at=START.replace(tzinfo=None))
    with pytest.raises(ValueError, match="active virtual wallet epoch"):
        replace(epoch, finalized_at=END)
    with pytest.raises(ValueError, match="cannot finalize before"):
        replace(
            epoch,
            status=VirtualWalletEpochStatus.FINALIZED,
            finalized_at=START - timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        replace(epoch, promotion_status="PROMOTED")
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        replace(epoch, live_eligibility_status="LIVE_ORDER_ELIGIBLE")
    assert epoch.to_payload()["execution_allowed"] is False


def test_market_selection_rejects_invalid_or_ambiguous_symbols() -> None:
    with pytest.raises(ValueError, match="requires resolved symbols"):
        HistoricalMarketSelection(market=VirtualMarket.SPOT, symbols=())
    with pytest.raises(ValueError, match="symbols must be unique"):
        HistoricalMarketSelection(
            market=VirtualMarket.SPOT,
            symbols=("BTCUSDT", "btcusdt"),
        )
    with pytest.raises(ValueError, match="symbol is invalid"):
        HistoricalMarketSelection(
            market=VirtualMarket.SPOT,
            symbols=("BTC/USDT",),
        )
    with pytest.raises(ValueError, match="cannot contain blank"):
        HistoricalMarketSelection(
            market=VirtualMarket.SPOT,
            symbols=("BTCUSDT",),
            survivorship_bias_limitations=("",),
        )
    with pytest.raises(ValueError, match="must be unique"):
        HistoricalMarketSelection(
            market=VirtualMarket.SPOT,
            symbols=("BTCUSDT",),
            survivorship_bias_limitations=("KNOWN_GAP", "KNOWN_GAP"),
        )
    with pytest.raises(ValueError, match="non-empty and bounded"):
        HistoricalMarketSelection(
            market=VirtualMarket.SPOT,
            symbols=("BTCUSDT",),
            historical_universe_evidence_ref=" ",
        )


def test_dataset_binding_rejects_invalid_identity_and_coverage() -> None:
    binding = _binding(VirtualMarket.SPOT, "BTCUSDT", "1m")
    with pytest.raises(ValueError, match="symbol is invalid"):
        replace(binding, symbol="BTC/USDT")
    with pytest.raises(ValueError, match="timeframe is unsupported"):
        replace(binding, timeframe="2m")
    with pytest.raises(ValueError, match="revision id"):
        replace(binding, dataset_revision_id="")
    with pytest.raises(ValueError, match="dataset SHA-256"):
        replace(binding, dataset_sha256="bad")
    with pytest.raises(ValueError, match="source manifest SHA-256"):
        replace(binding, source_manifest_sha256="bad")
    with pytest.raises(ValueError, match="source provenance"):
        replace(binding, source_provenance_ref="")
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        replace(binding, coverage_start=START.replace(tzinfo=None))
    with pytest.raises(ValueError, match="coverage is invalid"):
        replace(binding, coverage_start=END, coverage_end=START)
    with pytest.raises(ValueError, match="row count must be positive"):
        replace(binding, row_count=0)
    assert binding.identity == ("SPOT", "BTCUSDT", "1m")
    assert binding.to_payload()["dataset_sha256"] == HASH


def test_replay_request_rejects_invalid_identity_boundaries_and_authority() -> None:
    request = _request()
    with pytest.raises(ValueError, match="run id"):
        replace(request, run_id="")
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        replace(request, start_at=START.replace(tzinfo=None))
    with pytest.raises(ValueError, match="end cannot precede start"):
        replace(request, end_at=START - timedelta(seconds=1))
    with pytest.raises(ValueError, match="random seed"):
        replace(request, random_seed=-1)
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        replace(request, execution_allowed=True)
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        replace(request, promotion_status="PROMOTED")
    with pytest.raises(ValueError, match="cannot authorize live execution"):
        replace(request, live_eligibility_status="LIVE_ORDER_ELIGIBLE")


def test_replay_request_rejects_duplicate_and_missing_scope_components() -> None:
    request = _request()
    with pytest.raises(ValueError, match="timeframes must be non-empty and unique"):
        replace(request, timeframes=("1m", "1m"))
    with pytest.raises(ValueError, match="requires market selections"):
        replace(request, market_selections=())
    with pytest.raises(ValueError, match="market selections must be unique"):
        replace(
            request,
            market_selections=(
                request.market_selections[0],
                request.market_selections[0],
            ),
        )
    with pytest.raises(ValueError, match="dataset bindings must be unique"):
        replace(
            request,
            dataset_bindings=(
                request.dataset_bindings[0],
                request.dataset_bindings[0],
                *request.dataset_bindings[1:],
            ),
        )
    early_end = replace(request.dataset_bindings[0], coverage_end=START)
    with pytest.raises(ValueError, match="does not cover end_at"):
        replace(
            request,
            dataset_bindings=(early_end, *request.dataset_bindings[1:]),
        )


def test_replay_request_rejects_invalid_wallet_epoch_set() -> None:
    request = _request()
    with pytest.raises(ValueError, match="one independent wallet epoch per market"):
        replace(request, wallet_epochs=request.wallet_epochs[:1])

    duplicate_id = replace(
        request.wallet_epochs[1],
        epoch_id=request.wallet_epochs[0].epoch_id,
    )
    with pytest.raises(ValueError, match="epoch ids must be independent"):
        replace(request, wallet_epochs=(request.wallet_epochs[0], duplicate_id))

    finalized = replace(
        request.wallet_epochs[0],
        status=VirtualWalletEpochStatus.FINALIZED,
        finalized_at=END,
    )
    with pytest.raises(ValueError, match="requires active wallet epochs"):
        replace(request, wallet_epochs=(finalized, request.wallet_epochs[1]))

    late_epoch = replace(
        request.wallet_epochs[0],
        started_at=START + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="must start at start_at"):
        replace(request, wallet_epochs=(late_epoch, request.wallet_epochs[1]))


def test_open_ended_replay_keeps_end_unresolved_but_hash_bound_to_datasets() -> None:
    request = replace(_request(), end_at=None)

    payload = request.to_payload()
    assert payload["end_at"] is None
    assert payload["system_segment_sha256"] == request.system_version.semantic_sha256
    assert len(request.semantic_result_seed_sha256) == 64


def test_contracts_normalize_serialized_enum_values_and_reject_unknowns() -> None:
    version = _system_version()
    epoch = replace(
        _epoch(VirtualMarket.SPOT, version),
        market=cast(VirtualMarket, "spot"),
        evidence_class=cast(
            HistoricalReplayEvidenceClass,
            "historical_replay",
        ),
        status=cast(VirtualWalletEpochStatus, "active"),
    )
    selection = HistoricalMarketSelection(
        market=cast(VirtualMarket, "spot"),
        symbols=("BTCUSDT",),
        universe_mode=cast(HistoricalUniverseMode, "explicit"),
    )
    binding = replace(
        _binding(VirtualMarket.SPOT, "BTCUSDT", "1m"),
        market=cast(VirtualMarket, "spot"),
    )

    assert epoch.market is VirtualMarket.SPOT
    assert epoch.evidence_class is HistoricalReplayEvidenceClass.HISTORICAL_REPLAY
    assert epoch.status is VirtualWalletEpochStatus.ACTIVE
    assert selection.market is VirtualMarket.SPOT
    assert selection.universe_mode is HistoricalUniverseMode.EXPLICIT
    assert binding.market is VirtualMarket.SPOT

    with pytest.raises(ValueError, match="wallet epoch market is invalid"):
        replace(epoch, market=cast(VirtualMarket, "OPTIONS"))
    with pytest.raises(ValueError, match="wallet epoch status is invalid"):
        replace(epoch, status=cast(VirtualWalletEpochStatus, "UNKNOWN"))
    with pytest.raises(ValueError, match="historical universe mode is invalid"):
        replace(
            selection,
            universe_mode=cast(HistoricalUniverseMode, "SURVIVORS_ONLY"),
        )


def test_semantic_seed_excludes_generated_identity_but_binds_economics() -> None:
    request = _request()
    renamed_epochs = tuple(
        replace(
            epoch,
            epoch_id=f"renamed:{index}",
            portfolio_id=f"renamed-portfolio:{index}",
        )
        for index, epoch in enumerate(request.wallet_epochs, start=1)
    )
    renamed = replace(
        request,
        run_id="historical-replay:test:renamed",
        wallet_epochs=renamed_epochs,
    )
    lower_capital_epochs = (
        replace(request.wallet_epochs[0], initial_capital_usdt=Decimal("900")),
        request.wallet_epochs[1],
    )
    lower_capital = replace(request, wallet_epochs=lower_capital_epochs)

    assert renamed.semantic_result_seed_sha256 == request.semantic_result_seed_sha256
    assert lower_capital.semantic_result_seed_sha256 != (
        request.semantic_result_seed_sha256
    )


def test_replay_initial_system_segment_must_begin_at_replay_start() -> None:
    request = _request()
    future_segment = replace(
        request.system_version,
        effective_at=START + timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="system segment must start at start_at"):
        replace(request, system_version=future_segment)

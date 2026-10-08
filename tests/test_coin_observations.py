"""Offline projections of checksum-pinned authentic instrument and replay data."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from ai4binance.data.coin_observations import (
    _coin_semantic_hash,
    build_coin_observations,
    futures_as_of_references,
)

FIXTURES = Path(__file__).parent / "fixtures/binance"
CUTOFF = datetime(2026, 10, 7, tzinfo=UTC)


def _authentic_inputs(root: Path) -> None:
    replay = (FIXTURES / "authentic_futures_replay_sample.json").read_bytes()
    assert (
        sha256(replay).hexdigest()
        == "fde7526735778fab90ae0450a5874c8f378ebe0d109d3775f8966b85268d525e"
    )
    (root / "BTCUSDT-15m-2026-10-06.json").write_bytes(replay)
    metadata = (FIXTURES / "authentic_instrument_metadata_sample.json").read_bytes()
    assert (
        sha256(metadata).hexdigest()
        == "fc69e5aaaa24f188ea949b93ca87d87e9478a3c1dee7aa6348e86e04cb594175"
    )
    for market, envelope in json.loads(metadata).items():
        path = root / market / "metadata/exchange-info.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(envelope), encoding="utf-8")


def test_authentic_derivatives_remain_separate_and_before_cutoff(
    tmp_path: Path,
) -> None:
    _authentic_inputs(tmp_path)
    result: Any = futures_as_of_references(tmp_path, "BTCUSDT", CUTOFF)
    assert result["status"] == "PARTIALLY_VERIFIED"
    assert result["historical_live_availability_verified"] is False
    assert {"OPEN_INTEREST", "MARK_PRICE", "FUNDING_RATE"} <= result[
        "observations"
    ].keys()
    for point in result["observations"].values():
        assert datetime.fromisoformat(point["event_time"]) <= CUTOFF
        assert point["aggregation"] == "NONE"
        assert point["source_url"].startswith("https://fapi.binance.com/")


def test_missing_or_corrupt_replay_is_explicit(tmp_path: Path) -> None:
    assert (
        futures_as_of_references(tmp_path, "BTCUSDT", CUTOFF)["status"]
        == "DATA_UNAVAILABLE"
    )
    _authentic_inputs(tmp_path)
    (tmp_path / "BTCUSDT-15m-2026-10-06.json").write_text("invalid", encoding="utf-8")
    assert (
        futures_as_of_references(tmp_path, "BTCUSDT", CUTOFF)["status"]
        == "DATA_UNAVAILABLE"
    )


def test_coin_projection_uses_actual_mapping_and_preserves_market_identity(
    tmp_path: Path,
) -> None:
    _authentic_inputs(tmp_path)
    # References identify verified inputs; they contain no invented market values.
    results = [
        {
            "market": market,
            "symbol": "BTCUSDT",
            "snapshot_id": "test-reference",
            "status": "BLOCKED",
        }
        for market in ("SPOT", "USD_M_FUTURES")
    ]
    result: Any = build_coin_observations(tmp_path, tmp_path, results, CUTOFF)
    coin = result["coins"][0]
    assert coin["asset"] == "BTC"
    assert coin["quote_asset"] == "USDT"
    assert len(coin["markets"]) == 2
    assert coin["consumer_enrichment_status"] == "BLOCKED"
    assert coin["execution_allowed"] is False
    repeated: Any = build_coin_observations(tmp_path, tmp_path, results, CUTOFF)
    assert coin["semantic_sha256"] == repeated["coins"][0]["semantic_sha256"]
    for observation in coin["futures_as_of_references"]["observations"].values():
        observation["attributes"].pop("ohlcv_source_sha256", None)
    assert coin["semantic_sha256"] == _coin_semantic_hash(coin)
    spot_only: Any = build_coin_observations(tmp_path, tmp_path, results[:1], CUTOFF)
    assert (
        spot_only["coins"][0]["futures_as_of_references"]["reason"]
        == "NO_CANONICAL_COUNTERPART"
    )

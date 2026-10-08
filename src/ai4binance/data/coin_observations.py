"""Research-only coin projections over separately validated market artifacts."""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.validation.futures_replay import RuntimeFuturesReplayLoader
from ai4binance.whale_fusion.models import DerivativesMetric


def _instrument_metadata(path: Path) -> tuple[dict[str, Mapping[str, object]], str]:
    encoded = path.read_bytes()
    payload = json.loads(encoded)["payload"]
    rows = {row["symbol"]: row for row in payload["symbols"]}
    return rows, sha256(encoded).hexdigest()


def futures_as_of_references(
    root: Path, symbol: str, cutoff: datetime
) -> dict[str, object]:
    """Retain native units and conservative period closure without summing states."""
    day = (cutoff - timedelta(microseconds=1)).date()
    path = root / f"{symbol}-15m-{day.isoformat()}.json"
    try:
        verified = RuntimeFuturesReplayLoader(root).load_verified(path)
        if verified.dataset.symbol != symbol or verified.dataset.timeframe != "15m":
            raise ValueError("Futures observation identity mismatch")
    except OSError, ValueError:
        return {"status": "DATA_UNAVAILABLE", "reason": "VERIFIED_REPLAY_UNAVAILABLE"}
    duration = timeframe_duration(verified.dataset.timeframe)
    observations: dict[str, object] = {}
    for metric, points in verified.dataset.derivatives.series.items():
        settlement = metric is DerivativesMetric.FUNDING_RATE
        eligible = tuple(
            point
            for point in points
            if point.timestamp + (timedelta() if settlement else duration) <= cutoff
        )
        if not eligible:
            observations[metric.value] = {"status": "DATA_UNAVAILABLE"}
            continue
        point = eligible[-1]
        age = (cutoff - point.timestamp).total_seconds()
        observations[metric.value] = {
            "status": "SETTLED_EVENT" if settlement else "AS_OF_REFERENCE",
            "event_time": point.timestamp.isoformat(),
            "age_seconds": age,
            "freshness": "NOT_APPLICABLE_TO_SETTLED_EVENT"
            if settlement
            else "STALE"
            if age > duration.total_seconds()
            else "WITHIN_ONE_PERIOD",
            "value": str(point.value),
            "attributes": dict(point.attributes),
            "source_id": point.provenance.source_id,
            "source_url": point.provenance.source_url,
            "aggregation": "NONE",
        }
    return {
        "status": "PARTIALLY_VERIFIED",
        "observations": observations,
        "artifact_sha256": verified.artifact_sha256,
        "source_artifact": str(path),
        "publication_time_status": "NOT_VERIFIED",
        "availability_rule": "CONSERVATIVE_FULL_NATIVE_PERIOD_EXCEPT_SETTLED_FUNDING",
        "historical_live_availability_verified": False,
    }


def build_coin_observations(
    archive_root: Path,
    replay_root: Path,
    results: Sequence[Mapping[str, object]],
    cutoff: datetime,
) -> dict[str, object]:
    """Group explicit underlying/quote identities without conversions or authority."""
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for market, directory in (("SPOT", "spot"), ("USD_M_FUTURES", "usd_m_futures")):
        try:
            metadata, metadata_hash = _instrument_metadata(
                archive_root / directory / "metadata/exchange-info.json"
            )
        except OSError, ValueError, KeyError, TypeError:
            return {"status": "BLOCKED", "reason": "INSTRUMENT_MAPPING_UNAVAILABLE"}
        for result in results:
            if result["market"] != market:
                continue
            symbol = str(result["symbol"])
            row = metadata.get(symbol, {})
            base, quote = row.get("baseAsset"), row.get("quoteAsset")
            if not isinstance(base, str) or not isinstance(quote, str):
                return {"status": "BLOCKED", "reason": "INSTRUMENT_MAPPING_INVALID"}
            group = groups.setdefault(
                (base, quote), {"asset": base, "quote_asset": quote, "markets": {}}
            )
            markets = cast(dict[str, object], group["markets"])
            if market in markets:
                return {"status": "BLOCKED", "reason": "AMBIGUOUS_COUNTERPART"}
            markets[market] = {
                **result,
                "instrument_metadata_sha256": metadata_hash,
                "contract_type": row.get("contractType"),
                "margin_asset": row.get("marginAsset"),
                "unit_conversion_applied": False,
            }
            if market == "USD_M_FUTURES":
                group["futures_as_of_references"] = futures_as_of_references(
                    replay_root, symbol, cutoff
                )
    for group in groups.values():
        group.setdefault(
            "futures_as_of_references",
            {"status": "DATA_UNAVAILABLE", "reason": "NO_CANONICAL_COUNTERPART"},
        )
        group.update(
            {
                "cutoff": cutoff.isoformat(),
                "consumer_enrichment_status": "BLOCKED",
                "consumer_blocker": "CROSS_MARKET_DECISION_BINDING_NOT_VERIFIED",
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        )
        group["semantic_sha256"] = _coin_semantic_hash(group)
    return {
        "status": "PARTIALLY_VERIFIED",
        "cutoff": cutoff.isoformat(),
        "coin_count": len(groups),
        "coins": [groups[key] for key in sorted(groups)],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _coin_semantic_hash(group: Mapping[str, object]) -> str:
    markets = cast(Mapping[str, Mapping[str, object]], group["markets"])
    references = cast(Mapping[str, object], group["futures_as_of_references"])
    semantic = {
        "version": "1.0",
        "asset": group["asset"],
        "quote_asset": group["quote_asset"],
        "cutoff": group["cutoff"],
        "markets": {
            market: {key: row[key] for key in ("symbol", "snapshot_id", "status")}
            for market, row in markets.items()
        },
        "observations": _semantic_observations(references),
        "availability_rule": references.get("availability_rule"),
        "status": references["status"],
    }
    return sha256(
        json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _semantic_observations(references: Mapping[str, object]) -> dict[str, object]:
    observations = cast(
        Mapping[str, Mapping[str, object]], references.get("observations", {})
    )
    return {
        metric: {
            **point,
            "attributes": {
                key: value
                for key, value in cast(
                    Mapping[str, object], point.get("attributes", {})
                ).items()
                if key != "ohlcv_source_sha256"
            },
        }
        for metric, point in observations.items()
    }

"""Fail-closed historical replay input for the runtime Futures strategy."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path
from typing import Final, cast

from ai4binance.data.timeframes import timeframe_duration
from ai4binance.schemas import OHLCVCandle
from ai4binance.whale_fusion.models import (
    DerivativesDataset,
    DerivativesMetric,
    MetricPoint,
    Provenance,
)

RUNTIME_FUTURES_REPLAY_SCHEMA_VERSION: Final = "1.0"
RUNTIME_FUTURES_REPLAY_TIMEFRAME: Final = "1h"
RUNTIME_FUTURES_REPLAY_TIMEFRAMES: Final = ("5m", "15m", "1h", "4h", "1d")
RUNTIME_FUTURES_REPLAY_MARKET: Final = "USD_M_FUTURES"
DEFAULT_MAX_REPLAY_BYTES: Final = 32 * 1024 * 1024
DEFAULT_MAX_REPLAY_CANDLES: Final = 100_000

_REPLAY_ARTIFACT_KEYS: Final = frozenset(
    {
        "schema_version",
        "market",
        "symbol",
        "timeframe",
        "source",
        "as_of",
        "candles",
        "derivatives",
        "dataset_sha256",
        "execution_allowed",
        "promotion_status",
        "live_eligibility_status",
    }
)
_CANDLE_KEYS: Final = frozenset({"timestamp", "open", "high", "low", "close", "volume"})
_DERIVATIVES_SERIES_KEYS: Final = frozenset({"metric", "points"})
_METRIC_POINT_KEYS: Final = frozenset(
    {
        "timestamp",
        "value",
        "source_id",
        "source_url",
        "observed_at",
        "attributes",
    }
)

_PUBLIC_SOURCE_URLS: Final = {
    "BINANCE_USD_M_PUBLIC_REST": ("https://fapi.binance.com",),
    "BINANCE_VISION_CHECKSUM_VERIFIED": (
        "https://data.binance.vision",
        "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision",
    ),
}


@dataclass(frozen=True, slots=True)
class RuntimeFuturesReplayDataset:
    """Bind public multi-timeframe OHLCV and derivatives for deterministic replay."""

    symbol: str
    candles: tuple[OHLCVCandle, ...]
    derivatives: DerivativesDataset
    timeframe: str = RUNTIME_FUTURES_REPLAY_TIMEFRAME
    market: str = field(default=RUNTIME_FUTURES_REPLAY_MARKET, init=False)
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="RESEARCH_ONLY", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()
        if (
            not normalized_symbol
            or not normalized_symbol.isascii()
            or not normalized_symbol.isalnum()
        ):
            raise ValueError("Futures replay symbol must be ASCII alphanumeric")
        if self.timeframe not in RUNTIME_FUTURES_REPLAY_TIMEFRAMES:
            raise ValueError("runtime Futures replay timeframe is unsupported")
        if self.derivatives.symbol != normalized_symbol:
            raise ValueError("Futures replay symbol lineage is inconsistent")
        if not self.candles:
            raise ValueError("Futures replay candles are required")
        candle_timestamps = tuple(candle.timestamp for candle in self.candles)
        if candle_timestamps != tuple(sorted(candle_timestamps)) or len(
            set(candle_timestamps)
        ) != len(candle_timestamps):
            raise ValueError(
                "Futures replay candles must be unique and strictly chronological"
            )
        expected_duration = timeframe_duration(self.timeframe)
        if any(
            following - current != expected_duration
            for current, following in pairwise(candle_timestamps)
        ):
            raise ValueError("Futures replay candle spacing must match timeframe")
        if any(
            min(candle.open, candle.high, candle.low, candle.close) <= Decimal("0")
            for candle in self.candles
        ):
            raise ValueError("Futures replay prices must be positive")
        if self.derivatives.as_of < candle_timestamps[-1]:
            raise ValueError("Futures replay as_of precedes the latest candle")
        self._validate_public_provenance(candle_timestamps)
        open_interest = self.derivatives.series.get(
            DerivativesMetric.OPEN_INTEREST,
            (),
        )
        if not open_interest:
            raise ValueError("Futures replay open-interest history is required")
        if tuple(point.timestamp for point in open_interest) != candle_timestamps:
            raise ValueError(
                "Futures replay OHLCV and open-interest timestamps must align exactly"
            )
        if any(point.value <= Decimal("0") for point in open_interest):
            raise ValueError("Futures replay open interest must be positive")
        object.__setattr__(self, "symbol", normalized_symbol)

    @property
    def dataset_sha256(self) -> str:
        """Return a deterministic hash over the complete replay input lineage."""
        canonical = json.dumps(
            self._hash_payload(),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def open_interest(self) -> tuple[Decimal, ...]:
        """Return the exactly aligned open-interest values."""
        return self.derivatives.values(DerivativesMetric.OPEN_INTEREST)

    def to_artifact_payload(self) -> dict[str, object]:
        """Return the canonical checksum-bound local replay representation."""

        payload = self._hash_payload()
        payload["dataset_sha256"] = self.dataset_sha256
        return payload

    def _validate_public_provenance(
        self,
        candle_timestamps: tuple[datetime, ...],
    ) -> None:
        allowed_urls = _PUBLIC_SOURCE_URLS.get(self.derivatives.source)
        if allowed_urls is None:
            raise ValueError("Futures replay requires an approved public data source")
        first_timestamp = candle_timestamps[0]
        last_timestamp = candle_timestamps[-1]
        for metric, points in self.derivatives.series.items():
            for point in points:
                within_bounds = first_timestamp <= point.timestamp <= last_timestamp
                if metric is DerivativesMetric.FUNDING_RATE:
                    within_bounds = (
                        first_timestamp
                        <= point.timestamp
                        < (last_timestamp + timeframe_duration(self.timeframe))
                    )
                if not within_bounds:
                    raise ValueError(
                        "Futures replay derivatives timestamps exceed candle bounds"
                    )
                provenance = point.provenance
                if provenance.source_id != self.derivatives.source:
                    raise ValueError("Futures replay source lineage is inconsistent")
                if provenance.observed_at > self.derivatives.as_of:
                    raise ValueError("Futures replay provenance exceeds dataset as_of")
                if provenance.observed_at < point.timestamp:
                    raise ValueError("Futures replay provenance predates market data")
                if not any(
                    provenance.source_url == root
                    or provenance.source_url.startswith(f"{root}/")
                    for root in allowed_urls
                ):
                    raise ValueError("Futures replay provenance host is not approved")

    def _hash_payload(self) -> dict[str, object]:
        return {
            "schema_version": RUNTIME_FUTURES_REPLAY_SCHEMA_VERSION,
            "market": self.market,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "source": self.derivatives.source,
            "as_of": _utc_isoformat(self.derivatives.as_of),
            "candles": [self._candle_payload(candle) for candle in self.candles],
            "derivatives": [
                {
                    "metric": metric.value,
                    "points": [self._point_payload(point) for point in points],
                }
                for metric, points in sorted(
                    self.derivatives.series.items(),
                    key=lambda item: item[0].value,
                )
            ],
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }

    @staticmethod
    def _candle_payload(candle: OHLCVCandle) -> dict[str, str]:
        return {
            "timestamp": _utc_isoformat(candle.timestamp),
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": str(candle.volume),
        }

    @staticmethod
    def _point_payload(point: MetricPoint) -> dict[str, object]:
        return {
            "timestamp": _utc_isoformat(point.timestamp),
            "value": str(point.value),
            "source_id": point.provenance.source_id,
            "source_url": point.provenance.source_url,
            "observed_at": _utc_isoformat(point.provenance.observed_at),
            "attributes": dict(sorted(point.attributes.items())),
        }


def _utc_isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class VerifiedRuntimeFuturesReplayArtifact:
    """One parsed replay dataset bound to the exact local artifact bytes."""

    dataset: RuntimeFuturesReplayDataset
    artifact_sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeFuturesReplayLoader:
    """Load one bounded, checksum-bound replay artifact from a trusted root."""

    root: Path
    max_bytes: int = DEFAULT_MAX_REPLAY_BYTES
    max_candles: int = DEFAULT_MAX_REPLAY_CANDLES

    def __post_init__(self) -> None:
        if not 1_024 <= self.max_bytes <= 256 * 1024 * 1024:
            raise ValueError("Futures replay byte bound is outside the safe range")
        if not 2 <= self.max_candles <= 1_000_000:
            raise ValueError("Futures replay candle bound is outside the safe range")
        object.__setattr__(self, "root", self.root.resolve())

    def load(self, path: str | Path) -> RuntimeFuturesReplayDataset:
        """Parse and verify a local replay without network or execution authority."""

        return self.load_verified(path).dataset

    def load_verified(
        self,
        path: str | Path,
    ) -> VerifiedRuntimeFuturesReplayArtifact:
        """Return the dataset plus a hash of the exact bytes parsed."""

        candidate = self._resolve(path)
        try:
            if (
                candidate.is_symlink()
                or not candidate.is_file()
                or candidate.stat().st_size > self.max_bytes
            ):
                raise ValueError("FUTURES_REPLAY_FILE_UNAVAILABLE_OR_UNSAFE")
            encoded = candidate.read_bytes()
        except OSError as error:
            raise ValueError("FUTURES_REPLAY_FILE_UNAVAILABLE_OR_UNSAFE") from error
        if not encoded or len(encoded) > self.max_bytes:
            raise ValueError("FUTURES_REPLAY_FILE_UNAVAILABLE_OR_UNSAFE")
        try:
            raw = json.loads(
                encoded.decode("utf-8"),
                object_pairs_hook=_unique_json_object,
            )
        except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("FUTURES_REPLAY_FILE_INVALID_JSON") from error
        payload = _require_mapping(raw, "Futures replay artifact must be an object")
        _require_exact_keys(payload, _REPLAY_ARTIFACT_KEYS, "artifact")
        self._validate_envelope(payload)
        candles = self._candles(payload["candles"])
        derivatives = self._derivatives(payload)
        dataset = RuntimeFuturesReplayDataset(
            symbol=_require_text(payload["symbol"], "symbol"),
            candles=candles,
            derivatives=derivatives,
            timeframe=_require_text(payload["timeframe"], "timeframe"),
        )
        declared_hash = _require_text(payload["dataset_sha256"], "dataset_sha256")
        if declared_hash != dataset.dataset_sha256:
            raise ValueError("FUTURES_REPLAY_DATASET_HASH_MISMATCH")
        return VerifiedRuntimeFuturesReplayArtifact(
            dataset=dataset,
            artifact_sha256=hashlib.sha256(encoded).hexdigest(),
        )

    def _resolve(self, path: str | Path) -> Path:
        supplied = Path(path)
        candidate = (
            supplied.resolve()
            if supplied.is_absolute()
            else (self.root / supplied).resolve()
        )
        if not candidate.is_relative_to(self.root):
            raise ValueError("FUTURES_REPLAY_PATH_OUTSIDE_ROOT")
        return candidate

    @staticmethod
    def _validate_envelope(payload: Mapping[str, object]) -> None:
        expected = {
            "schema_version": RUNTIME_FUTURES_REPLAY_SCHEMA_VERSION,
            "market": RUNTIME_FUTURES_REPLAY_MARKET,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            raise ValueError("FUTURES_REPLAY_ENVELOPE_INVALID")
        if payload.get("timeframe") not in RUNTIME_FUTURES_REPLAY_TIMEFRAMES:
            raise ValueError("FUTURES_REPLAY_ENVELOPE_INVALID")
        if payload.get("execution_allowed") is not False:
            raise ValueError("FUTURES_REPLAY_ENVELOPE_INVALID")

    def _candles(self, value: object) -> tuple[OHLCVCandle, ...]:
        items = _require_list(value, "Futures replay candles must be an array")
        if not 2 <= len(items) <= self.max_candles:
            raise ValueError("FUTURES_REPLAY_CANDLE_COUNT_OUT_OF_BOUNDS")
        candles: list[OHLCVCandle] = []
        for raw in items:
            item = _require_mapping(raw, "Futures replay candle must be an object")
            _require_exact_keys(item, _CANDLE_KEYS, "candle")
            candles.append(
                OHLCVCandle(
                    timestamp=_parse_timestamp(item["timestamp"], "candle timestamp"),
                    open=_parse_decimal(item["open"], "candle open"),
                    high=_parse_decimal(item["high"], "candle high"),
                    low=_parse_decimal(item["low"], "candle low"),
                    close=_parse_decimal(item["close"], "candle close"),
                    volume=_parse_decimal(item["volume"], "candle volume"),
                )
            )
        return tuple(candles)

    def _derivatives(
        self,
        payload: Mapping[str, object],
    ) -> DerivativesDataset:
        raw_series = _require_list(
            payload["derivatives"],
            "Futures replay derivatives must be an array",
        )
        if not raw_series or len(raw_series) > len(DerivativesMetric):
            raise ValueError("FUTURES_REPLAY_DERIVATIVES_COUNT_OUT_OF_BOUNDS")
        series: dict[DerivativesMetric, tuple[MetricPoint, ...]] = {}
        maximum_points = self.max_candles * len(DerivativesMetric)
        point_count = 0
        for raw in raw_series:
            item = _require_mapping(
                raw,
                "Futures replay derivative series must be an object",
            )
            _require_exact_keys(item, _DERIVATIVES_SERIES_KEYS, "derivative series")
            try:
                metric = DerivativesMetric(
                    _require_text(item["metric"], "derivative metric")
                )
            except ValueError as error:
                raise ValueError("FUTURES_REPLAY_DERIVATIVE_METRIC_INVALID") from error
            if metric in series:
                raise ValueError("FUTURES_REPLAY_DERIVATIVE_METRIC_DUPLICATED")
            raw_points = _require_list(
                item["points"],
                "Futures replay metric points must be an array",
            )
            point_count += len(raw_points)
            if point_count > maximum_points:
                raise ValueError("FUTURES_REPLAY_METRIC_POINT_LIMIT_EXCEEDED")
            series[metric] = tuple(
                self._metric_point(metric, point) for point in raw_points
            )
        return DerivativesDataset(
            symbol=_require_text(payload["symbol"], "symbol"),
            as_of=_parse_timestamp(payload["as_of"], "as_of"),
            series=series,
            source=_require_text(payload["source"], "source"),
        )

    @staticmethod
    def _metric_point(metric: DerivativesMetric, raw: object) -> MetricPoint:
        item = _require_mapping(raw, "Futures replay metric point must be an object")
        _require_exact_keys(item, _METRIC_POINT_KEYS, "metric point")
        raw_attributes = _require_mapping(
            item["attributes"],
            "Futures replay metric attributes must be an object",
        )
        if len(raw_attributes) > 64:
            raise ValueError("FUTURES_REPLAY_METRIC_ATTRIBUTES_EXCEEDED")
        attributes = {
            _require_bounded_text(key, "attribute key", 128): _require_bounded_text(
                value,
                "attribute value",
                512,
            )
            for key, value in raw_attributes.items()
        }
        return MetricPoint(
            metric=metric,
            timestamp=_parse_timestamp(item["timestamp"], "metric timestamp"),
            value=_parse_decimal(item["value"], "metric value"),
            provenance=Provenance(
                source_id=_require_bounded_text(
                    item["source_id"],
                    "source_id",
                    128,
                ),
                observed_at=_parse_timestamp(item["observed_at"], "observed_at"),
                source_url=_require_bounded_text(
                    item["source_url"],
                    "source_url",
                    2_048,
                ),
            ),
            attributes=attributes,
        )


def _require_mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(message)
    return cast(Mapping[str, object], value)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("FUTURES_REPLAY_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _require_list(value: object, message: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(message)
    return cast(list[object], value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    subject: str,
) -> None:
    if set(value) != expected:
        raise ValueError(f"Futures replay {subject} fields are invalid")


def _require_text(value: object, field_name: str) -> str:
    return _require_bounded_text(value, field_name, 256)


def _require_bounded_text(
    value: object,
    field_name: str,
    maximum_length: int,
) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum_length:
        raise ValueError(f"Futures replay {field_name} is invalid")
    return value


def _parse_timestamp(value: object, field_name: str) -> datetime:
    raw = _require_bounded_text(value, field_name, 64)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"Futures replay {field_name} is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Futures replay {field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _parse_decimal(value: object, field_name: str) -> Decimal:
    raw = _require_bounded_text(value, field_name, 128)
    try:
        parsed = Decimal(raw)
    except InvalidOperation as error:
        raise ValueError(f"Futures replay {field_name} is invalid") from error
    if not parsed.is_finite():
        raise ValueError(f"Futures replay {field_name} must be finite")
    return parsed

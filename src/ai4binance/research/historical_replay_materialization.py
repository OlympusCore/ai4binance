"""Materialize closed-candle replay snapshots from canonical dataset series."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING

from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.data.revision import DatasetRevisionBuilder, DatasetRevisionManifest
from ai4binance.data.timeframes import timeframe_duration
from ai4binance.research.historical_replay import (
    HistoricalMarketReplayRequest,
    HistoricalReplayDatasetBinding,
    HistoricalReplayExecutionContext,
)
from ai4binance.research.virtual_market import VirtualMarket
from ai4binance.schemas import DataQuality, MarketSnapshot, OHLCVCandle
from ai4binance.whale_fusion.models import DerivativesMetric, MetricPoint

if TYPE_CHECKING:
    from ai4binance.research_runtime import HistoricalReplaySnapshot


@dataclass(frozen=True, slots=True)
class HistoricalReplayDatasetSeries:
    """Exact in-memory candle series for one request dataset binding."""

    binding: HistoricalReplayDatasetBinding
    candles: tuple[OHLCVCandle, ...]
    complete_binding_coverage: bool = field(default=True, kw_only=True)

    def __post_init__(self) -> None:
        if not isinstance(self.complete_binding_coverage, bool):
            raise ValueError("historical replay dataset coverage mode must be boolean")
        if not self.candles:
            raise ValueError("historical replay dataset series cannot be empty")
        timestamps = tuple(candle.timestamp for candle in self.candles)
        if any(not _is_utc(timestamp) for timestamp in timestamps):
            raise ValueError("historical replay dataset series must use canonical UTC")
        if timestamps != tuple(sorted(timestamps)) or len(set(timestamps)) != len(
            timestamps
        ):
            raise ValueError(
                "historical replay dataset series must be unique and chronological"
            )
        if (
            self.complete_binding_coverage
            and len(self.candles) != self.binding.row_count
        ):
            raise ValueError(
                "historical replay dataset series row count must match its binding"
            )
        if self.complete_binding_coverage and (
            timestamps[0] != self.binding.coverage_start
            or timestamps[-1] != self.binding.coverage_end
        ):
            raise ValueError(
                "historical replay dataset series coverage must match its binding"
            )
        if not self.complete_binding_coverage and (
            len(self.candles) > self.binding.row_count
            or timestamps[0] < self.binding.coverage_start
            or timestamps[-1] > self.binding.coverage_end
        ):
            raise ValueError(
                "historical replay dataset window exceeds its exact binding"
            )


@dataclass(frozen=True, slots=True)
class HistoricalFuturesMarketEvidence:
    """Point-in-time mark and funding evidence for one closed Futures candle."""

    mark_price: MetricPoint
    funding_rate: MetricPoint
    funding_payment_due: bool


@dataclass(frozen=True, slots=True)
class HistoricalFuturesReplayDatasetSeries(HistoricalReplayDatasetSeries):
    """Futures candles plus exact mark and carried-forward funding evidence."""

    mark_prices: tuple[MetricPoint, ...]
    funding_rates: tuple[MetricPoint, ...]
    _candle_timestamps: tuple[datetime, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _funding_timestamps: tuple[datetime, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        HistoricalReplayDatasetSeries.__post_init__(self)
        if self.binding.market is not VirtualMarket.USD_M_FUTURES:
            raise ValueError("Futures replay series requires a Futures binding")
        candle_timestamps = tuple(candle.timestamp for candle in self.candles)
        mark_timestamps = tuple(point.timestamp for point in self.mark_prices)
        if mark_timestamps != candle_timestamps:
            raise ValueError(
                "historical Futures mark prices must align with every candle"
            )
        if any(
            point.metric is not DerivativesMetric.MARK_PRICE or point.value <= 0
            for point in self.mark_prices
        ):
            raise ValueError("historical Futures mark price evidence is invalid")
        funding_timestamps = tuple(point.timestamp for point in self.funding_rates)
        if (
            not funding_timestamps
            or funding_timestamps[0] != candle_timestamps[0]
            or funding_timestamps != tuple(sorted(funding_timestamps))
            or len(set(funding_timestamps)) != len(funding_timestamps)
            or funding_timestamps[-1] > candle_timestamps[-1]
            or any(
                point.metric is not DerivativesMetric.FUNDING_RATE
                for point in self.funding_rates
            )
        ):
            raise ValueError("historical Futures funding evidence is incomplete")
        if any(
            not _is_utc(point.timestamp) or not _is_utc(point.provenance.observed_at)
            for point in (*self.mark_prices, *self.funding_rates)
        ):
            raise ValueError("historical Futures evidence must use canonical UTC")
        object.__setattr__(self, "_candle_timestamps", candle_timestamps)
        object.__setattr__(self, "_funding_timestamps", funding_timestamps)

    def evidence_for(self, candle: OHLCVCandle) -> HistoricalFuturesMarketEvidence:
        """Resolve evidence available for the candle without future access."""

        candle_index = bisect_left(self._candle_timestamps, candle.timestamp)
        if candle_index >= len(self.candles) or self.candles[candle_index] != candle:
            raise ValueError("historical Futures candle is not bound to this series")
        funding_index = bisect_right(self._funding_timestamps, candle.timestamp) - 1
        if funding_index < 0:
            raise ValueError("historical Futures funding evidence is unavailable")
        funding = self.funding_rates[funding_index]
        return HistoricalFuturesMarketEvidence(
            mark_price=self.mark_prices[candle_index],
            funding_rate=funding,
            funding_payment_due=funding.timestamp == candle.timestamp,
        )


HistoricalExecutionContextProvider = Callable[
    [HistoricalReplayDatasetBinding, datetime, OHLCVCandle],
    HistoricalReplayExecutionContext,
]


@dataclass(frozen=True, slots=True)
class HistoricalSpotArchiveSeriesLoader:
    """Verify and load a bound Spot Parquet dataset without network access."""

    root: Path
    max_rows: int = 1_000_000
    max_revision_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 2 <= self.max_rows <= 10_000_000:
            raise ValueError("historical replay row bound is outside the safe range")
        if not 1_024 <= self.max_revision_bytes <= 16 * 1024 * 1024:
            raise ValueError(
                "historical replay revision byte bound is outside the safe range"
            )
        object.__setattr__(self, "root", self.root.resolve())

    def load(
        self,
        binding: HistoricalReplayDatasetBinding,
    ) -> HistoricalReplayDatasetSeries:
        """Return candles only after rebuilding the persisted revision evidence."""

        return self.load_many((binding,))[0]

    def load_many(
        self,
        bindings: Sequence[HistoricalReplayDatasetBinding],
    ) -> tuple[HistoricalReplayDatasetSeries, ...]:
        """Verify each symbol revision once, then load every exact binding."""

        requested = tuple(bindings)
        if not requested:
            raise ValueError("historical replay Spot bindings cannot be empty")
        if any(
            not isinstance(binding, HistoricalReplayDatasetBinding)
            for binding in requested
        ):
            raise TypeError("Spot archive loader requires dataset bindings")
        if any(binding.market is not VirtualMarket.SPOT for binding in requested):
            raise ValueError("Spot archive loader requires Spot dataset bindings")
        identities = tuple(binding.identity for binding in requested)
        if len(set(identities)) != len(identities):
            raise ValueError("historical replay Spot bindings must be unique")
        revisions = {
            symbol: self._verified_revision(symbol)
            for symbol in dict.fromkeys(binding.symbol for binding in requested)
        }
        return tuple(
            self._load_bound_series(binding, revisions[binding.symbol])
            for binding in requested
        )

    def load_many_window(
        self,
        bindings: Sequence[HistoricalReplayDatasetBinding],
        *,
        start_at: datetime,
        end_at: datetime,
        history_limit: int = 250,
    ) -> tuple[HistoricalReplayDatasetSeries, ...]:
        """Load only replay-relevant rows after verifying complete revisions."""

        if not _is_utc(start_at) or not _is_utc(end_at) or end_at < start_at:
            raise ValueError("historical replay dataset window must be ordered UTC")
        if not 2 <= history_limit <= 10_000:
            raise ValueError("historical replay window history limit is invalid")
        requested = tuple(bindings)
        if not requested:
            raise ValueError("historical replay Spot bindings cannot be empty")
        if any(
            not isinstance(binding, HistoricalReplayDatasetBinding)
            for binding in requested
        ):
            raise TypeError("Spot archive loader requires dataset bindings")
        if any(binding.market is not VirtualMarket.SPOT for binding in requested):
            raise ValueError("Spot archive loader requires Spot dataset bindings")
        identities = tuple(binding.identity for binding in requested)
        if len(set(identities)) != len(identities):
            raise ValueError("historical replay Spot bindings must be unique")
        revisions = {
            symbol: self._verified_revision(symbol)
            for symbol in dict.fromkeys(binding.symbol for binding in requested)
        }
        return tuple(
            self._load_bound_series(
                binding,
                revisions[binding.symbol],
                window=(
                    start_at - timeframe_duration(binding.timeframe) * history_limit,
                    end_at,
                ),
            )
            for binding in requested
        )

    def _verified_revision(self, symbol: str) -> DatasetRevisionManifest:
        revision_path = self.root / symbol / "dataset-revision.json"

        try:
            if (
                revision_path.is_symlink()
                or not revision_path.is_file()
                or revision_path.stat().st_size > self.max_revision_bytes
            ):
                raise ValueError("HISTORICAL_REPLAY_REVISION_UNAVAILABLE_OR_UNSAFE")
            encoded = revision_path.read_bytes()
        except OSError as error:
            raise ValueError(
                "HISTORICAL_REPLAY_REVISION_UNAVAILABLE_OR_UNSAFE"
            ) from error
        if not encoded or len(encoded) > self.max_revision_bytes:
            raise ValueError("HISTORICAL_REPLAY_REVISION_UNAVAILABLE_OR_UNSAFE")
        try:
            raw = json.loads(encoded.decode("utf-8"))
            if not isinstance(raw, dict):
                raise TypeError
            raw_entries = raw["entries"]
            if not isinstance(raw_entries, list) or not raw_entries:
                raise TypeError
            timeframes = tuple(
                str(entry["timeframe"])
                for entry in raw_entries
                if isinstance(entry, dict)
            )
            if len(timeframes) != len(raw_entries) or len(set(timeframes)) != len(
                timeframes
            ):
                raise TypeError
            for timeframe in timeframes:
                timeframe_duration(timeframe)
            generated_at = datetime.fromisoformat(str(raw["generated_at"]))
        except (
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ValueError("HISTORICAL_REPLAY_REVISION_INVALID") from error
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("HISTORICAL_REPLAY_REVISION_INVALID")
        dataset_directory = self.root / symbol
        for timeframe in timeframes:
            for suffix in (
                ".parquet",
                ".manifest.json",
                ".source-manifest.json",
            ):
                candidate = dataset_directory / f"{timeframe}{suffix}"
                if candidate.is_symlink() or not candidate.is_file():
                    raise ValueError(
                        "HISTORICAL_REPLAY_DATASET_FILE_UNAVAILABLE_OR_UNSAFE"
                    )

        rebuilt = DatasetRevisionBuilder(self.root).build(
            symbol=symbol,
            timeframes=timeframes,
            generated_at=generated_at,
        )
        expected = json.loads(
            json.dumps(asdict(rebuilt), ensure_ascii=True, sort_keys=True)
        )
        if raw != expected:
            raise ValueError("HISTORICAL_REPLAY_REVISION_EVIDENCE_MISMATCH")
        return rebuilt

    def _load_bound_series(
        self,
        binding: HistoricalReplayDatasetBinding,
        revision: DatasetRevisionManifest,
        *,
        window: tuple[datetime, datetime] | None = None,
    ) -> HistoricalReplayDatasetSeries:
        entry = next(
            (item for item in revision.entries if item.timeframe == binding.timeframe),
            None,
        )
        if entry is None:
            raise ValueError("HISTORICAL_REPLAY_TIMEFRAME_NOT_IN_REVISION")
        if (
            revision.revision_id != binding.dataset_revision_id
            or entry.dataset_sha256 != binding.dataset_sha256
            or entry.source_manifest_sha256 != binding.source_manifest_sha256
            or entry.source != binding.source_provenance_ref
            or entry.row_count != binding.row_count
            or datetime.fromisoformat(entry.first_timestamp) != binding.coverage_start
            or datetime.fromisoformat(entry.last_timestamp) != binding.coverage_end
        ):
            raise ValueError("HISTORICAL_REPLAY_DATASET_BINDING_MISMATCH")
        if entry.row_count > self.max_rows:
            raise ValueError("HISTORICAL_REPLAY_DATASET_ROW_COUNT_OUT_OF_BOUNDS")
        archive = ParquetOHLCVArchive(self.root)
        if window is None:
            candles = archive.read(binding.symbol, binding.timeframe)
        else:
            candles = archive.read_window(
                binding.symbol,
                binding.timeframe,
                start_at=window[0],
                end_at=window[1],
            )
        return HistoricalReplayDatasetSeries(
            binding=binding,
            candles=candles,
            complete_binding_coverage=window is None,
        )


@dataclass(frozen=True, slots=True)
class HistoricalFuturesReplaySeriesLoader:
    """Adapt one checksum-bound canonical Futures replay artifact."""

    root: Path
    max_bytes: int = 32 * 1024 * 1024
    max_candles: int = 100_000

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    def load(
        self,
        binding: HistoricalReplayDatasetBinding,
        path: str | Path,
    ) -> HistoricalFuturesReplayDatasetSeries:
        """Return Futures inputs only when every binding field is exact."""

        from ai4binance.validation.futures_replay import RuntimeFuturesReplayLoader

        if binding.market is not VirtualMarket.USD_M_FUTURES:
            raise ValueError("Futures replay loader requires a Futures binding")
        verified = RuntimeFuturesReplayLoader(
            self.root,
            max_bytes=self.max_bytes,
            max_candles=self.max_candles,
        ).load_verified(path)
        dataset = verified.dataset
        expected_revision_id = f"dataset:{dataset.dataset_sha256[:24]}"
        if (
            binding.symbol != dataset.symbol
            or binding.timeframe != dataset.timeframe
            or binding.dataset_revision_id != expected_revision_id
            or binding.dataset_sha256 != dataset.dataset_sha256
            or binding.source_manifest_sha256 != verified.artifact_sha256
            or binding.source_provenance_ref != dataset.derivatives.source
            or binding.coverage_start != dataset.candles[0].timestamp
            or binding.coverage_end != dataset.candles[-1].timestamp
            or binding.row_count != len(dataset.candles)
        ):
            raise ValueError("HISTORICAL_FUTURES_REPLAY_DATASET_BINDING_MISMATCH")
        mark_prices = dataset.derivatives.series.get(
            DerivativesMetric.MARK_PRICE,
            (),
        )
        funding_rates = dataset.derivatives.series.get(
            DerivativesMetric.FUNDING_RATE,
            (),
        )
        return HistoricalFuturesReplayDatasetSeries(
            binding=binding,
            candles=dataset.candles,
            mark_prices=mark_prices,
            funding_rates=funding_rates,
        )


@dataclass(frozen=True, slots=True)
class HistoricalReplaySnapshotMaterializer:
    """Build deterministic closed-candle snapshots without decision authority."""

    history_limit: int = 250
    minimum_closed_candles: int = 200

    def __post_init__(self) -> None:
        if not 2 <= self.history_limit <= 10_000:
            raise ValueError("historical replay history limit is outside safe bounds")
        if not 2 <= self.minimum_closed_candles <= self.history_limit:
            raise ValueError(
                "historical replay minimum closed candles must fit the history limit"
            )

    def materialize(
        self,
        request: HistoricalMarketReplayRequest,
        datasets: Sequence[HistoricalReplayDatasetSeries],
        execution_context_provider: HistoricalExecutionContextProvider,
    ) -> tuple[HistoricalReplaySnapshot, ...]:
        """Return canonical replay snapshots for every requested market/symbol."""

        series = tuple(datasets)
        if any(not isinstance(item, HistoricalReplayDatasetSeries) for item in series):
            raise TypeError(
                "historical replay materialization requires canonical dataset series"
            )
        by_identity = {item.binding.identity: item for item in series}
        if len(by_identity) != len(series):
            raise ValueError(
                "historical replay materialization datasets must be unique"
            )
        expected = {binding.identity for binding in request.dataset_bindings}
        if set(by_identity) != expected:
            raise ValueError(
                "historical replay materialization datasets must exactly cover request"
            )
        for binding in request.dataset_bindings:
            if by_identity[binding.identity].binding != binding:
                raise ValueError(
                    "historical replay materialization must preserve exact bindings"
                )

        duration_by_timeframe = {
            timeframe: timeframe_duration(timeframe) for timeframe in request.timeframes
        }
        event_timeframe = min(
            request.timeframes,
            key=lambda timeframe: duration_by_timeframe[timeframe],
        )
        snapshots: list[HistoricalReplaySnapshot] = []
        for selection in request.market_selections:
            for symbol in selection.symbols:
                pair_snapshots = self._materialize_pair(
                    request=request,
                    market=selection.market.value,
                    symbol=symbol,
                    event_timeframe=event_timeframe,
                    duration_by_timeframe=duration_by_timeframe,
                    by_identity=by_identity,
                    execution_context_provider=execution_context_provider,
                )
                if not pair_snapshots:
                    raise ValueError(
                        "historical replay materialization produced no in-range events"
                    )
                snapshots.extend(pair_snapshots)
        return tuple(
            sorted(
                snapshots,
                key=lambda item: (
                    item.created_at,
                    item.market,
                    item.symbol,
                    item.snapshot.snapshot_id,
                ),
            )
        )

    def _materialize_pair(
        self,
        *,
        request: HistoricalMarketReplayRequest,
        market: str,
        symbol: str,
        event_timeframe: str,
        duration_by_timeframe: dict[str, timedelta],
        by_identity: dict[tuple[str, str, str], HistoricalReplayDatasetSeries],
        execution_context_provider: HistoricalExecutionContextProvider,
    ) -> tuple[HistoricalReplaySnapshot, ...]:
        from ai4binance.research_runtime import HistoricalReplaySnapshot

        pair_series = {
            timeframe: by_identity[(market, symbol, timeframe)]
            for timeframe in request.timeframes
        }
        availability = {
            timeframe: tuple(
                candle.timestamp + duration_by_timeframe[timeframe]
                for candle in dataset.candles
            )
            for timeframe, dataset in pair_series.items()
        }
        event_series = pair_series[event_timeframe]
        event_duration = duration_by_timeframe[event_timeframe]
        output: list[HistoricalReplaySnapshot] = []
        bindings = tuple(dataset.binding for dataset in pair_series.values())
        for event_candle in event_series.candles:
            observed_at = event_candle.timestamp + event_duration
            if observed_at < request.start_at:
                continue
            if request.end_at is not None and observed_at > request.end_at:
                continue
            prefixes: dict[str, tuple[OHLCVCandle, ...]] = {}
            for timeframe in request.timeframes:
                count = bisect_right(availability[timeframe], observed_at)
                if count == 0:
                    prefixes = {}
                    break
                first = max(0, count - self.history_limit)
                prefix = pair_series[timeframe].candles[first:count]
                self._require_contiguous(prefix, timeframe)
                prefixes[timeframe] = prefix
            if not prefixes:
                continue
            context = execution_context_provider(
                event_series.binding,
                observed_at,
                event_candle,
            )
            if not isinstance(context, HistoricalReplayExecutionContext):
                raise TypeError(
                    "historical replay execution provider returned an invalid contract"
                )
            self._require_execution_context(
                context=context,
                binding=event_series.binding,
                observed_at=observed_at,
                execution_model_sha256=(request.system_version.execution_model_sha256),
            )
            half_spread = event_candle.close * context.half_spread_ratio
            closed_counts = {
                timeframe: len(prefix) for timeframe, prefix in prefixes.items()
            }
            snapshot = MarketSnapshot(
                snapshot_id=self._snapshot_id(
                    market=market,
                    symbol=symbol,
                    observed_at=observed_at,
                    bindings=bindings,
                    context=context,
                ),
                created_at=observed_at,
                exchange="Binance",
                market_type=market,
                symbol=symbol,
                timeframes=request.timeframes,
                ohlcv_by_timeframe=prefixes,
                latest_price=event_candle.close,
                bid=event_candle.close - half_spread,
                ask=event_candle.close + half_spread,
                spread=half_spread * 2,
                exchange_filters={
                    "tick_size": str(context.tick_size),
                    "step_size": str(context.step_size),
                    "minimum_notional": str(context.minimum_notional),
                },
                server_time=observed_at,
                data_freshness={
                    timeframe: {
                        "last_open": prefix[-1].timestamp.isoformat(),
                        "available_at": (
                            prefix[-1].timestamp + duration_by_timeframe[timeframe]
                        ).isoformat(),
                        "closed_candle_count": len(prefix),
                        "stale": False,
                    }
                    for timeframe, prefix in prefixes.items()
                },
                data_quality=(
                    DataQuality.DATA_VALID
                    if all(
                        count >= self.minimum_closed_candles
                        for count in closed_counts.values()
                    )
                    else DataQuality.DATA_INVALID
                ),
                market_metadata={
                    "source": event_series.binding.source_provenance_ref,
                    "closed_candles_only": True,
                    "historical_replay": True,
                    "dataset_revision_id": event_series.binding.dataset_revision_id,
                },
            )
            output.append(HistoricalReplaySnapshot(snapshot, bindings, context))
        return tuple(output)

    @staticmethod
    def _require_execution_context(
        *,
        context: HistoricalReplayExecutionContext,
        binding: HistoricalReplayDatasetBinding,
        observed_at: datetime,
        execution_model_sha256: str,
    ) -> None:
        if context.binding_identity != binding.identity:
            raise ValueError(
                "historical replay execution context must match the event dataset"
            )
        if context.observed_at != observed_at:
            raise ValueError(
                "historical replay execution context must match the event time"
            )
        if (
            context.dataset_revision_id != binding.dataset_revision_id
            or context.dataset_sha256 != binding.dataset_sha256
            or context.source_manifest_sha256 != binding.source_manifest_sha256
            or context.source_provenance_ref != binding.source_provenance_ref
        ):
            raise ValueError(
                "historical replay execution context must preserve dataset evidence"
            )
        if context.execution_model_sha256 != execution_model_sha256:
            raise ValueError(
                "historical replay execution context must match the system version"
            )

    @staticmethod
    def _require_contiguous(
        candles: tuple[OHLCVCandle, ...],
        timeframe: str,
    ) -> None:
        duration = timeframe_duration(timeframe)
        if any(
            following.timestamp - current.timestamp != duration
            for current, following in pairwise(candles)
        ):
            raise ValueError(
                "historical replay materialization encountered a candle cadence gap"
            )

    @staticmethod
    def _snapshot_id(
        *,
        market: str,
        symbol: str,
        observed_at: datetime,
        bindings: tuple[HistoricalReplayDatasetBinding, ...],
        context: HistoricalReplayExecutionContext,
    ) -> str:
        payload = {
            "market": market,
            "symbol": symbol,
            "observed_at": observed_at.isoformat(),
            "datasets": [binding.to_payload() for binding in bindings],
            "execution_context": context.to_payload(),
        }
        canonical = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        return f"historical:{market.lower()}:{symbol.lower()}:{digest}"


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


__all__ = (
    "HistoricalExecutionContextProvider",
    "HistoricalFuturesMarketEvidence",
    "HistoricalFuturesReplayDatasetSeries",
    "HistoricalFuturesReplaySeriesLoader",
    "HistoricalReplayDatasetSeries",
    "HistoricalReplaySnapshotMaterializer",
    "HistoricalSpotArchiveSeriesLoader",
)

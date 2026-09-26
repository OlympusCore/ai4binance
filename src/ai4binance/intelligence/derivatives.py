"""Typed, freshness-bound Futures context separate from OHLCV evidence."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from ai4binance.intelligence.contracts import DerivativesContextEvidence
from ai4binance.schemas import (
    AgentResult,
    MarketSnapshot,
    is_futures_market_type,
    is_usable_agent_result,
)

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class FuturesContextEngine:
    """Validate provenance, freshness, and critical derivatives metrics."""

    maximum_age: timedelta = timedelta(hours=2)

    def __post_init__(self) -> None:
        if self.maximum_age <= timedelta(0):
            raise ValueError("Futures context maximum age must be positive")

    def build(
        self,
        snapshot: MarketSnapshot,
        result: AgentResult | None,
    ) -> DerivativesContextEvidence:
        if not is_futures_market_type(snapshot.market_type):
            return DerivativesContextEvidence(
                status="NOT_APPLICABLE",
                source_count=0,
                as_of=None,
                evidence_refs=("SPOT_MARKET",),
            )
        if result is None or not is_usable_agent_result(result) or result.blockers:
            return self._blocked("FUTURES_DERIVATIVES_CONTEXT_UNAVAILABLE")
        if (
            result.agent_name != "derivatives"
            or result.snapshot_id != snapshot.snapshot_id
            or result.timestamp != snapshot.created_at
            or result.symbol != snapshot.symbol
        ):
            return self._blocked("FUTURES_DERIVATIVES_IDENTITY_MISMATCH")
        raw = snapshot.derivatives_snapshot
        source_count = self._integer(raw.get("source_count"))
        as_of = self._datetime(raw.get("as_of"))
        if source_count is None or source_count < 1 or as_of is None:
            return self._blocked("FUTURES_DERIVATIVES_PROVENANCE_INVALID")
        age = snapshot.created_at - as_of
        if age < timedelta(0) or age > self.maximum_age:
            return self._blocked("FUTURES_DERIVATIVES_CONTEXT_STALE_OR_FUTURE")
        metrics = self._metrics(raw)
        blockers = self._metric_blockers(metrics)
        if blockers:
            return DerivativesContextEvidence(
                status="BLOCKED",
                source_count=source_count,
                as_of=as_of,
                evidence_refs=result.evidence or ("DERIVATIVES_AGENT",),
                blockers=blockers,
                age_seconds=int(age.total_seconds()),
                funding_rate=metrics["funding_rate"],
                open_interest=self._nonnegative(metrics["open_interest"]),
                basis=metrics["basis"],
                mark_price=self._positive(metrics["mark_price"]),
                index_price=self._positive(metrics["index_price"]),
                taker_buy_sell_ratio=self._nonnegative(metrics["taker_buy_sell_ratio"]),
            )
        index_price = metrics["index_price"]
        mark_price = metrics["mark_price"]
        assert isinstance(index_price, Decimal)
        assert isinstance(mark_price, Decimal)
        divergence = abs(mark_price - index_price) / index_price
        funding_rate = metrics["funding_rate"]
        assert isinstance(funding_rate, Decimal)
        crowding = (
            "POSITIVE_FUNDING"
            if funding_rate > ZERO
            else "NEGATIVE_FUNDING"
            if funding_rate < ZERO
            else "NEUTRAL_FUNDING"
        )
        return DerivativesContextEvidence(
            status="AVAILABLE",
            source_count=source_count,
            as_of=as_of,
            evidence_refs=result.evidence or ("DERIVATIVES_AGENT",),
            age_seconds=int(age.total_seconds()),
            mark_index_divergence=divergence,
            crowding_state=crowding,
            confidence=min(result.confidence, min(source_count, 10) / 10.0),
            funding_rate=metrics["funding_rate"],
            open_interest=metrics["open_interest"],
            basis=metrics["basis"],
            mark_price=metrics["mark_price"],
            index_price=metrics["index_price"],
            taker_buy_sell_ratio=metrics["taker_buy_sell_ratio"],
        )

    @staticmethod
    def _metrics(raw: Mapping[str, object]) -> dict[str, Decimal | None]:
        mark_price = FuturesContextEngine._decimal_alias(raw, "mark_price", "markPrice")
        index_price = FuturesContextEngine._decimal_alias(
            raw, "index_price", "indexPrice"
        )
        basis = FuturesContextEngine._decimal_alias(raw, "basis")
        if basis is None and mark_price is not None and index_price is not None:
            basis = mark_price - index_price
        return {
            "funding_rate": FuturesContextEngine._decimal_alias(
                raw, "funding_rate", "lastFundingRate"
            ),
            "open_interest": FuturesContextEngine._decimal_alias(
                raw, "open_interest", "openInterest"
            ),
            "basis": basis,
            "mark_price": mark_price,
            "index_price": index_price,
            "taker_buy_sell_ratio": FuturesContextEngine._decimal_alias(
                raw, "taker_buy_sell_ratio", "takerBuySellRatio"
            ),
        }

    @staticmethod
    def _metric_blockers(
        metrics: Mapping[str, Decimal | None],
    ) -> tuple[str, ...]:
        blockers: list[str] = []
        for name in ("funding_rate", "open_interest", "mark_price", "index_price"):
            value = metrics[name]
            if value is None:
                blockers.append(f"FUTURES_METRIC_MISSING:{name.upper()}")
        for name in ("open_interest", "mark_price", "index_price"):
            value = metrics[name]
            if value is not None and value <= ZERO:
                blockers.append(f"FUTURES_METRIC_INVALID:{name.upper()}")
        taker = metrics["taker_buy_sell_ratio"]
        if taker is not None and taker < ZERO:
            blockers.append("FUTURES_METRIC_INVALID:TAKER_BUY_SELL_RATIO")
        return tuple(dict.fromkeys(blockers))

    @staticmethod
    def _blocked(blocker: str) -> DerivativesContextEvidence:
        return DerivativesContextEvidence(
            status="BLOCKED",
            source_count=0,
            as_of=None,
            blockers=(blocker,),
        )

    @staticmethod
    def _nonnegative(value: Decimal | None) -> Decimal | None:
        return value if value is not None and value >= ZERO else None

    @staticmethod
    def _positive(value: Decimal | None) -> Decimal | None:
        return value if value is not None and value > ZERO else None

    @staticmethod
    def _decimal_alias(
        raw: Mapping[str, object],
        *names: str,
    ) -> Decimal | None:
        for name in names:
            if name not in raw:
                continue
            value = raw.get(name)
            if isinstance(value, (str, int, float, Decimal)) and not isinstance(
                value, bool
            ):
                try:
                    parsed = Decimal(str(value))
                except InvalidOperation:
                    return None
                if parsed.is_finite():
                    return parsed
            return None
        return None

    @staticmethod
    def _integer(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed

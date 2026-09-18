"""Deterministic identity contracts for canonical full-system market replay."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from ai4binance.research.virtual_market import VirtualMarket

SUPPORTED_HISTORICAL_REPLAY_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
MAX_VIRTUAL_MARKET_CAPITAL_USDT = Decimal("1000")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,24}$")
_ZERO = Decimal("0")


class HistoricalReplayEvidenceClass(StrEnum):
    """Evidence classes that must never be merged invisibly."""

    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    FORWARD_VIRTUAL = "FORWARD_VIRTUAL"


class HistoricalUniverseMode(StrEnum):
    """How a market-specific historical universe was selected."""

    EXPLICIT = "EXPLICIT"
    ALL_ELIGIBLE = "ALL_ELIGIBLE"


class VirtualWalletEpochStatus(StrEnum):
    """Lifecycle state for one persistent virtual-wallet economic epoch."""

    ACTIVE = "ACTIVE"
    FINALIZED = "FINALIZED"


@dataclass(frozen=True, slots=True)
class HistoricalReplayExecutionContext:
    """Exact modeled-execution and Futures evidence for one replay event."""

    market: VirtualMarket
    symbol: str
    timeframe: str
    observed_at: datetime
    dataset_revision_id: str
    dataset_sha256: str
    source_manifest_sha256: str
    source_provenance_ref: str
    execution_model_sha256: str
    fee_ratio: Decimal
    slippage_ratio: Decimal
    half_spread_ratio: Decimal
    tick_size: Decimal
    step_size: Decimal
    minimum_notional: Decimal
    mark_price: Decimal | None = None
    funding_rate: Decimal | None = None
    funding_payment_due: bool = False
    leverage: int | None = None
    isolated_margin_usdt: Decimal | None = None
    maintenance_margin_ratio: Decimal | None = None
    liquidation_fee_ratio: Decimal | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        market = _coerce_str_enum(
            self.market,
            VirtualMarket,
            "historical replay execution context market",
        )
        object.__setattr__(self, "market", market)
        symbol = self.symbol.strip().upper()
        if not _SYMBOL_RE.fullmatch(symbol):
            raise ValueError("historical replay execution context symbol is invalid")
        object.__setattr__(self, "symbol", symbol)
        if self.timeframe not in SUPPORTED_HISTORICAL_REPLAY_TIMEFRAMES:
            raise ValueError(
                "historical replay execution context timeframe is unsupported"
            )
        _require_utc(
            "historical replay execution context observed_at",
            self.observed_at,
        )
        _require_text("execution context dataset revision", self.dataset_revision_id)
        _require_sha256("execution context dataset SHA-256", self.dataset_sha256)
        _require_sha256(
            "execution context source manifest SHA-256",
            self.source_manifest_sha256,
        )
        _require_text(
            "execution context source provenance",
            self.source_provenance_ref,
        )
        _require_sha256(
            "execution context execution model SHA-256",
            self.execution_model_sha256,
        )
        for name, value, maximum in (
            ("fee ratio", self.fee_ratio, Decimal("0.01")),
            ("slippage ratio", self.slippage_ratio, Decimal("0.02")),
            ("half spread ratio", self.half_spread_ratio, Decimal("0.02")),
        ):
            if not value.is_finite() or not _ZERO <= value <= maximum:
                raise ValueError(
                    f"historical replay execution context {name} is invalid"
                )
        if any(
            not value.is_finite() or value <= _ZERO
            for value in (self.tick_size, self.step_size, self.minimum_notional)
        ):
            raise ValueError(
                "historical replay execution context market constraints are invalid"
            )
        if not isinstance(self.funding_payment_due, bool):
            raise ValueError("historical replay funding payment due must be boolean")
        futures_values = (
            self.mark_price,
            self.funding_rate,
            self.leverage,
            self.isolated_margin_usdt,
            self.maintenance_margin_ratio,
            self.liquidation_fee_ratio,
        )
        if market is VirtualMarket.SPOT:
            if any(value is not None for value in futures_values) or (
                self.funding_payment_due
            ):
                raise ValueError(
                    "Spot replay execution context cannot contain Futures evidence"
                )
        else:
            if any(value is None for value in futures_values):
                raise ValueError(
                    "Futures replay execution context requires complete margin, "
                    "funding, and mark evidence"
                )
            mark_price = self.mark_price
            funding_rate = self.funding_rate
            isolated_margin = self.isolated_margin_usdt
            maintenance_ratio = self.maintenance_margin_ratio
            liquidation_fee_ratio = self.liquidation_fee_ratio
            if (
                mark_price is None
                or not mark_price.is_finite()
                or mark_price <= _ZERO
                or funding_rate is None
                or not funding_rate.is_finite()
                or isolated_margin is None
                or not isolated_margin.is_finite()
                or isolated_margin <= _ZERO
                or maintenance_ratio is None
                or not maintenance_ratio.is_finite()
                or not _ZERO < maintenance_ratio < Decimal("1")
                or liquidation_fee_ratio is None
                or not liquidation_fee_ratio.is_finite()
                or not _ZERO <= liquidation_fee_ratio <= Decimal("0.02")
            ):
                raise ValueError(
                    "Futures replay execution context contains invalid economics"
                )
            if (
                isinstance(self.leverage, bool)
                or not isinstance(self.leverage, int)
                or not 1 <= self.leverage <= 125
            ):
                raise ValueError(
                    "Futures replay execution context leverage must be an integer "
                    "between 1 and 125"
                )
            if maintenance_ratio >= Decimal("1") / Decimal(self.leverage):
                raise ValueError(
                    "Futures replay maintenance margin must remain below the "
                    "initial margin ratio"
                )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError(
                "historical replay execution context cannot authorize live execution"
            )

    @property
    def binding_identity(self) -> tuple[str, str, str]:
        """Return the exact public-dataset identity used by this event."""

        return (self.market.value, self.symbol, self.timeframe)

    def to_payload(self) -> dict[str, object]:
        """Return the deterministic context payload supplied to the runtime."""

        return {
            "context_kind": "HISTORICAL_REPLAY_EXECUTION_V1",
            "market": self.market.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "observed_at": _utc_text(self.observed_at),
            "dataset_revision_id": self.dataset_revision_id,
            "dataset_sha256": self.dataset_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_provenance_ref": self.source_provenance_ref,
            "execution_model_sha256": self.execution_model_sha256,
            "fee_ratio": str(self.fee_ratio),
            "slippage_ratio": str(self.slippage_ratio),
            "half_spread_ratio": str(self.half_spread_ratio),
            "tick_size": str(self.tick_size),
            "step_size": str(self.step_size),
            "minimum_notional": str(self.minimum_notional),
            "mark_price": (
                str(self.mark_price) if self.mark_price is not None else None
            ),
            "funding_rate": (
                str(self.funding_rate) if self.funding_rate is not None else None
            ),
            "funding_payment_due": self.funding_payment_due,
            "leverage": self.leverage,
            "isolated_margin_usdt": (
                str(self.isolated_margin_usdt)
                if self.isolated_margin_usdt is not None
                else None
            ),
            "maintenance_margin_ratio": (
                str(self.maintenance_margin_ratio)
                if self.maintenance_margin_ratio is not None
                else None
            ),
            "liquidation_fee_ratio": (
                str(self.liquidation_fee_ratio)
                if self.liquidation_fee_ratio is not None
                else None
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class VirtualSystemVersionSegment:
    """Behavior-changing component identity for one performance segment."""

    effective_at: datetime
    code_revision: str
    configuration_sha256: str
    strategy_bundle_sha256: str
    feature_bundle_sha256: str
    dge_rule_bundle_sha256: str
    risk_policy_sha256: str
    validation_policy_sha256: str
    execution_model_sha256: str

    def __post_init__(self) -> None:
        _require_utc("system version effective_at", self.effective_at)
        _require_text("system version code revision", self.code_revision)
        for name in (
            "configuration_sha256",
            "strategy_bundle_sha256",
            "feature_bundle_sha256",
            "dge_rule_bundle_sha256",
            "risk_policy_sha256",
            "validation_policy_sha256",
            "execution_model_sha256",
        ):
            _require_sha256(name, str(getattr(self, name)))

    @property
    def semantic_sha256(self) -> str:
        """Return the deterministic segment identity."""

        return _canonical_sha256(self.to_payload())

    @property
    def segment_id(self) -> str:
        """Return a compact stable identifier backed by the full semantic hash."""

        return f"system-segment:{self.semantic_sha256[:24]}"

    def to_payload(self) -> dict[str, object]:
        """Return the canonical hashable version-segment payload."""

        return {
            "effective_at": _utc_text(self.effective_at),
            "code_revision": self.code_revision,
            "configuration_sha256": self.configuration_sha256,
            "strategy_bundle_sha256": self.strategy_bundle_sha256,
            "feature_bundle_sha256": self.feature_bundle_sha256,
            "dge_rule_bundle_sha256": self.dge_rule_bundle_sha256,
            "risk_policy_sha256": self.risk_policy_sha256,
            "validation_policy_sha256": self.validation_policy_sha256,
            "execution_model_sha256": self.execution_model_sha256,
        }


@dataclass(frozen=True, slots=True)
class VirtualWalletEpoch:
    """Immutable identity for one market-specific virtual-wallet epoch."""

    epoch_id: str
    portfolio_id: str
    market: VirtualMarket
    initial_capital_usdt: Decimal
    started_at: datetime
    start_reason: str
    system_segment_sha256: str
    evidence_class: HistoricalReplayEvidenceClass
    status: VirtualWalletEpochStatus = VirtualWalletEpochStatus.ACTIVE
    finalized_at: datetime | None = None
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "market",
            _coerce_str_enum(self.market, VirtualMarket, "wallet epoch market"),
        )
        object.__setattr__(
            self,
            "evidence_class",
            _coerce_str_enum(
                self.evidence_class,
                HistoricalReplayEvidenceClass,
                "wallet epoch evidence class",
            ),
        )
        object.__setattr__(
            self,
            "status",
            _coerce_str_enum(
                self.status,
                VirtualWalletEpochStatus,
                "wallet epoch status",
            ),
        )
        _require_text("wallet epoch id", self.epoch_id)
        _require_text("wallet epoch portfolio id", self.portfolio_id)
        _require_text("wallet epoch start reason", self.start_reason)
        _require_utc("wallet epoch started_at", self.started_at)
        _require_sha256("wallet epoch system segment", self.system_segment_sha256)
        if not _ZERO < self.initial_capital_usdt <= MAX_VIRTUAL_MARKET_CAPITAL_USDT:
            raise ValueError(
                "virtual wallet initial capital must be positive and at most 1000 USDT"
            )
        if self.status is VirtualWalletEpochStatus.ACTIVE:
            if self.finalized_at is not None:
                raise ValueError("active virtual wallet epoch cannot be finalized")
        else:
            if self.finalized_at is None:
                raise ValueError("finalized virtual wallet epoch requires finalized_at")
            _require_utc("wallet epoch finalized_at", self.finalized_at)
            if self.finalized_at < self.started_at:
                raise ValueError("wallet epoch cannot finalize before it starts")
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("virtual wallet epoch cannot authorize live execution")

    def to_payload(self) -> dict[str, object]:
        """Return the audit-safe wallet epoch identity."""

        return {
            "epoch_id": self.epoch_id,
            "portfolio_id": self.portfolio_id,
            "market": self.market.value,
            "initial_capital_usdt": str(self.initial_capital_usdt),
            "started_at": _utc_text(self.started_at),
            "start_reason": self.start_reason,
            "system_segment_sha256": self.system_segment_sha256,
            "evidence_class": self.evidence_class.value,
            "status": self.status.value,
            "finalized_at": (
                _utc_text(self.finalized_at) if self.finalized_at is not None else None
            ),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


@dataclass(frozen=True, slots=True)
class HistoricalMarketSelection:
    """Resolved symbols for one independently evaluated historical market."""

    market: VirtualMarket
    symbols: tuple[str, ...]
    universe_mode: HistoricalUniverseMode = HistoricalUniverseMode.EXPLICIT
    historical_universe_evidence_ref: str | None = None
    survivorship_bias_limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "market",
            _coerce_str_enum(
                self.market,
                VirtualMarket,
                "historical market selection market",
            ),
        )
        object.__setattr__(
            self,
            "universe_mode",
            _coerce_str_enum(
                self.universe_mode,
                HistoricalUniverseMode,
                "historical universe mode",
            ),
        )
        normalized_symbols = tuple(
            sorted(symbol.strip().upper() for symbol in self.symbols)
        )
        if not normalized_symbols:
            raise ValueError("historical market selection requires resolved symbols")
        if len(set(normalized_symbols)) != len(normalized_symbols):
            raise ValueError("historical market selection symbols must be unique")
        if any(not _SYMBOL_RE.fullmatch(symbol) for symbol in normalized_symbols):
            raise ValueError("historical market selection symbol is invalid")
        object.__setattr__(self, "symbols", normalized_symbols)
        _require_unique_nonblank(
            "survivorship bias limitations", self.survivorship_bias_limitations
        )
        if self.universe_mode is HistoricalUniverseMode.ALL_ELIGIBLE:
            if self.historical_universe_evidence_ref is None:
                raise ValueError(
                    "ALL_ELIGIBLE replay requires historical universe evidence"
                )
            _require_text(
                "historical universe evidence",
                self.historical_universe_evidence_ref,
            )
        elif self.historical_universe_evidence_ref is not None:
            _require_text(
                "historical universe evidence",
                self.historical_universe_evidence_ref,
            )

    def to_payload(self) -> dict[str, object]:
        """Return the canonical market selection payload."""

        return {
            "market": self.market.value,
            "symbols": list(self.symbols),
            "universe_mode": self.universe_mode.value,
            "historical_universe_evidence_ref": (self.historical_universe_evidence_ref),
            "survivorship_bias_limitations": list(self.survivorship_bias_limitations),
        }


@dataclass(frozen=True, slots=True)
class HistoricalReplayDatasetBinding:
    """One exact public dataset bound into a historical replay request."""

    market: VirtualMarket
    symbol: str
    timeframe: str
    dataset_revision_id: str
    dataset_sha256: str
    source_manifest_sha256: str
    source_provenance_ref: str
    coverage_start: datetime
    coverage_end: datetime
    row_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "market",
            _coerce_str_enum(
                self.market,
                VirtualMarket,
                "historical replay dataset market",
            ),
        )
        normalized_symbol = self.symbol.strip().upper()
        if not _SYMBOL_RE.fullmatch(normalized_symbol):
            raise ValueError("historical replay dataset symbol is invalid")
        object.__setattr__(self, "symbol", normalized_symbol)
        if self.timeframe not in SUPPORTED_HISTORICAL_REPLAY_TIMEFRAMES:
            raise ValueError("historical replay dataset timeframe is unsupported")
        _require_text("dataset revision id", self.dataset_revision_id)
        _require_sha256("dataset SHA-256", self.dataset_sha256)
        _require_sha256("source manifest SHA-256", self.source_manifest_sha256)
        _require_text("source provenance reference", self.source_provenance_ref)
        _require_utc("dataset coverage_start", self.coverage_start)
        _require_utc("dataset coverage_end", self.coverage_end)
        if self.coverage_end < self.coverage_start:
            raise ValueError("historical replay dataset coverage is invalid")
        if self.row_count < 1:
            raise ValueError("historical replay dataset row count must be positive")

    @property
    def identity(self) -> tuple[str, str, str]:
        """Return the deterministic market/symbol/timeframe key."""

        return (self.market.value, self.symbol, self.timeframe)

    def to_payload(self) -> dict[str, object]:
        """Return the canonical public-dataset binding payload."""

        return {
            "market": self.market.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "dataset_revision_id": self.dataset_revision_id,
            "dataset_sha256": self.dataset_sha256,
            "source_manifest_sha256": self.source_manifest_sha256,
            "source_provenance_ref": self.source_provenance_ref,
            "coverage_start": _utc_text(self.coverage_start),
            "coverage_end": _utc_text(self.coverage_end),
            "row_count": self.row_count,
        }


@dataclass(frozen=True, slots=True)
class HistoricalMarketReplayRequest:
    """Exact deterministic input identity for future canonical replay orchestration."""

    run_id: str
    start_at: datetime
    end_at: datetime | None
    timeframes: tuple[str, ...]
    market_selections: tuple[HistoricalMarketSelection, ...]
    dataset_bindings: tuple[HistoricalReplayDatasetBinding, ...]
    wallet_epochs: tuple[VirtualWalletEpoch, ...]
    system_version: VirtualSystemVersionSegment
    random_seed: int = 0
    execution_allowed: bool = False
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        _require_text("historical replay run id", self.run_id)
        _require_utc("historical replay start_at", self.start_at)
        if self.end_at is not None:
            _require_utc("historical replay end_at", self.end_at)
            if self.end_at < self.start_at:
                raise ValueError("historical replay end cannot precede start")
        if self.random_seed < 0:
            raise ValueError("historical replay random seed cannot be negative")
        if self.system_version.effective_at != self.start_at:
            raise ValueError(
                "historical replay initial system segment must start at start_at"
            )
        if (
            self.execution_allowed
            or self.promotion_status != "RESEARCH_ONLY"
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("historical replay cannot authorize live execution")
        self._normalize_and_validate_timeframes()
        self._normalize_and_validate_selections()
        self._normalize_and_validate_datasets()
        self._normalize_and_validate_epochs()

    def _normalize_and_validate_timeframes(self) -> None:
        if not self.timeframes or len(set(self.timeframes)) != len(self.timeframes):
            raise ValueError(
                "historical replay timeframes must be non-empty and unique"
            )
        unsupported = tuple(
            timeframe
            for timeframe in self.timeframes
            if timeframe not in SUPPORTED_HISTORICAL_REPLAY_TIMEFRAMES
        )
        if unsupported:
            raise ValueError("historical replay contains unsupported timeframes")
        order = {
            value: index
            for index, value in enumerate(SUPPORTED_HISTORICAL_REPLAY_TIMEFRAMES)
        }
        object.__setattr__(
            self,
            "timeframes",
            tuple(sorted(self.timeframes, key=order.__getitem__)),
        )

    def _normalize_and_validate_selections(self) -> None:
        if not self.market_selections:
            raise ValueError("historical replay requires market selections")
        markets = tuple(selection.market for selection in self.market_selections)
        if len(set(markets)) != len(markets):
            raise ValueError("historical replay market selections must be unique")
        object.__setattr__(
            self,
            "market_selections",
            tuple(sorted(self.market_selections, key=lambda item: item.market.value)),
        )

    def _normalize_and_validate_datasets(self) -> None:
        ordered = tuple(sorted(self.dataset_bindings, key=lambda item: item.identity))
        identities = tuple(binding.identity for binding in ordered)
        if len(set(identities)) != len(identities):
            raise ValueError("historical replay dataset bindings must be unique")
        expected = {
            (selection.market.value, symbol, timeframe)
            for selection in self.market_selections
            for symbol in selection.symbols
            for timeframe in self.timeframes
        }
        if set(identities) != expected:
            raise ValueError(
                "historical replay dataset bindings must exactly cover the request"
            )
        for binding in ordered:
            if binding.coverage_start > self.start_at:
                raise ValueError("historical replay dataset does not cover start_at")
            if self.end_at is not None and binding.coverage_end < self.end_at:
                raise ValueError("historical replay dataset does not cover end_at")
        object.__setattr__(self, "dataset_bindings", ordered)

    def _normalize_and_validate_epochs(self) -> None:
        ordered = tuple(sorted(self.wallet_epochs, key=lambda item: item.market.value))
        markets = tuple(epoch.market for epoch in ordered)
        expected_markets = tuple(
            selection.market for selection in self.market_selections
        )
        if len(set(markets)) != len(markets) or set(markets) != set(expected_markets):
            raise ValueError(
                "historical replay requires one independent wallet epoch per market"
            )
        epoch_ids = tuple(epoch.epoch_id for epoch in ordered)
        portfolio_ids = tuple(epoch.portfolio_id for epoch in ordered)
        if len(set(epoch_ids)) != len(epoch_ids):
            raise ValueError("historical replay wallet epoch ids must be independent")
        if len(set(portfolio_ids)) != len(portfolio_ids):
            raise ValueError("historical replay portfolio ids must be independent")
        for epoch in ordered:
            if (
                epoch.evidence_class
                is not HistoricalReplayEvidenceClass.HISTORICAL_REPLAY
            ):
                raise ValueError("historical replay requires HISTORICAL_REPLAY epochs")
            if epoch.status is not VirtualWalletEpochStatus.ACTIVE:
                raise ValueError("historical replay requires active wallet epochs")
            if epoch.started_at != self.start_at:
                raise ValueError(
                    "historical replay wallet epoch must start at start_at"
                )
            if epoch.system_segment_sha256 != self.system_version.semantic_sha256:
                raise ValueError(
                    "historical replay wallet epoch system segment must match request"
                )
        object.__setattr__(self, "wallet_epochs", ordered)

    @property
    def semantic_result_seed_sha256(self) -> str:
        """Return the stable input hash from which replay result hashes must derive."""

        return _canonical_sha256(
            {
                "start_at": _utc_text(self.start_at),
                "end_at": (_utc_text(self.end_at) if self.end_at is not None else None),
                "timeframes": list(self.timeframes),
                "market_selections": [
                    selection.to_payload() for selection in self.market_selections
                ],
                "dataset_bindings": [
                    binding.to_payload() for binding in self.dataset_bindings
                ],
                "wallet_initial_states": [
                    {
                        "market": epoch.market.value,
                        "initial_capital_usdt": str(epoch.initial_capital_usdt),
                        "started_at": _utc_text(epoch.started_at),
                        "start_reason": epoch.start_reason,
                        "system_segment_sha256": epoch.system_segment_sha256,
                        "evidence_class": epoch.evidence_class.value,
                    }
                    for epoch in self.wallet_epochs
                ],
                "system_version": self.system_version.to_payload(),
                "random_seed": self.random_seed,
            }
        )

    def to_payload(self) -> dict[str, object]:
        """Return a deterministic, audit-safe replay request payload."""

        return {
            "run_id": self.run_id,
            "start_at": _utc_text(self.start_at),
            "end_at": _utc_text(self.end_at) if self.end_at is not None else None,
            "timeframes": list(self.timeframes),
            "market_selections": [
                selection.to_payload() for selection in self.market_selections
            ],
            "dataset_bindings": [
                binding.to_payload() for binding in self.dataset_bindings
            ],
            "wallet_epochs": [epoch.to_payload() for epoch in self.wallet_epochs],
            "system_version": self.system_version.to_payload(),
            "system_segment_sha256": self.system_version.semantic_sha256,
            "random_seed": self.random_seed,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }


def _require_text(name: str, value: str) -> None:
    if not value.strip() or len(value) > 500:
        raise ValueError(f"{name} must be non-empty and bounded")


def _require_sha256(name: str, value: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _require_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use canonical UTC")


def _require_unique_nonblank(name: str, values: tuple[str, ...]) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blank values")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _coerce_str_enum[StrEnumT: StrEnum](
    value: object,
    enum_type: type[StrEnumT],
    name: str,
) -> StrEnumT:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).strip().upper())
    except ValueError:
        raise ValueError(f"{name} is invalid") from None


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = (
    "MAX_VIRTUAL_MARKET_CAPITAL_USDT",
    "SUPPORTED_HISTORICAL_REPLAY_TIMEFRAMES",
    "HistoricalMarketReplayRequest",
    "HistoricalMarketSelection",
    "HistoricalReplayDatasetBinding",
    "HistoricalReplayEvidenceClass",
    "HistoricalReplayExecutionContext",
    "HistoricalUniverseMode",
    "VirtualSystemVersionSegment",
    "VirtualWalletEpoch",
    "VirtualWalletEpochStatus",
)

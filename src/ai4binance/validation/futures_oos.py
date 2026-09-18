"""Exact-bound, fail-closed USD-M Futures OOS evidence validation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

from ai4binance.domain import ValidationStatus
from ai4binance.reporting import to_primitive
from ai4binance.research.backtesting.models import BacktestResult
from ai4binance.schemas import OOSValidationStatus
from ai4binance.storage import write_json_object_verified
from ai4binance.storage.destination_verification import read_json_object
from ai4binance.validation.models import WalkForwardReport

FUTURES_OOS_SCHEMA_VERSION = "1.0"
FUTURES_OOS_STRATEGY_ID = "RuntimeFuturesAdvisor"
FUTURES_OOS_STRATEGY_VERSION = "runtime-futures-advisor-v1"
RUNTIME_FUTURES_STOP_LOSS_RATIO = Decimal("0.02")
RUNTIME_FUTURES_TAKE_PROFIT_RATIO = Decimal("0.04")
RUNTIME_FUTURES_MINIMUM_RISK_REWARD = Decimal("2")
RUNTIME_FUTURES_MAXIMUM_HOLDING_BARS = 24
DEFAULT_MAX_EVIDENCE_BYTES = 65_536
DEFAULT_MAX_ARTIFACT_BYTES = 100_000_000
DEFAULT_MAX_EVIDENCE_AGE = timedelta(days=90)
DEFAULT_FUTURE_TOLERANCE = timedelta(minutes=5)

_SYMBOL_PATTERN = re.compile(r"[A-Z0-9]{2,24}")
_TIMEFRAME_PATTERN = re.compile(r"[1-9][0-9]*[mhdw]")
_SETUP_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class FuturesOosEvidenceQuery:
    """Exact runtime identity that OOS evidence must match."""

    symbol: str
    timeframe: str
    setup_name: str
    strategy_sha256: str
    as_of: datetime

    def __post_init__(self) -> None:
        if not _SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("Futures OOS symbol identity is invalid")
        if not _TIMEFRAME_PATTERN.fullmatch(self.timeframe):
            raise ValueError("Futures OOS timeframe identity is invalid")
        if not _SETUP_PATTERN.fullmatch(self.setup_name):
            raise ValueError("Futures OOS setup identity is invalid")
        if not _SHA256_PATTERN.fullmatch(self.strategy_sha256):
            raise ValueError("Futures OOS strategy hash is invalid")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("Futures OOS as_of must be timezone-aware")


class FuturesOosEvidenceResolver(Protocol):
    """Resolve OOS evidence without granting promotion or execution authority."""

    def is_validated(self, query: FuturesOosEvidenceQuery) -> bool: ...


@dataclass(frozen=True, slots=True)
class FuturesOosEvidenceReader:
    """Validate one canonical local evidence document and its bound artifact."""

    root: Path
    max_evidence_bytes: int = DEFAULT_MAX_EVIDENCE_BYTES
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES
    max_evidence_age: timedelta = DEFAULT_MAX_EVIDENCE_AGE
    future_tolerance: timedelta = DEFAULT_FUTURE_TOLERANCE

    def __post_init__(self) -> None:
        if self.max_evidence_bytes < 1 or self.max_artifact_bytes < 1:
            raise ValueError("Futures OOS evidence size bounds must be positive")
        if self.max_evidence_age <= timedelta(0):
            raise ValueError("Futures OOS evidence age bound must be positive")
        if self.future_tolerance < timedelta(0):
            raise ValueError("Futures OOS future tolerance cannot be negative")

    def is_validated(self, query: FuturesOosEvidenceQuery) -> bool:
        """Return true only for complete, current, exact-bound OOS evidence."""
        try:
            payload = self._load_payload(query)
            return self._matches(payload, query) and self._artifact_matches(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return False

    def _load_payload(self, query: FuturesOosEvidenceQuery) -> Mapping[str, object]:
        path = (
            self.root
            / query.symbol
            / query.timeframe
            / f"{query.setup_name.lower()}.oos-evidence.json"
        )
        resolved_root = self.root.resolve()
        resolved_path = path.resolve()
        if (
            not resolved_path.is_relative_to(resolved_root)
            or not resolved_path.is_file()
        ):
            raise ValueError("Futures OOS evidence path is unavailable or unsafe")
        if resolved_path.stat().st_size > self.max_evidence_bytes:
            raise ValueError("Futures OOS evidence exceeds its size bound")
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("Futures OOS evidence must be an object")
        return cast(Mapping[str, object], payload)

    def _matches(
        self,
        payload: Mapping[str, object],
        query: FuturesOosEvidenceQuery,
    ) -> bool:
        expected = {
            "schema_version": FUTURES_OOS_SCHEMA_VERSION,
            "market": "USD_M_FUTURES",
            "symbol": query.symbol,
            "timeframe": query.timeframe,
            "setup_name": query.setup_name,
            "strategy_version": FUTURES_OOS_STRATEGY_VERSION,
            "strategy_sha256": query.strategy_sha256,
            "validation_status": "OOS_VALIDATED",
            "promotion_status": "STAGED_CANDIDATE",
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            return False
        if not _bounded_text(payload.get("evidence_id"), 128):
            return False
        if not _SHA256_PATTERN.fullmatch(str(payload.get("dataset_sha256", ""))):
            return False
        if not _GIT_REVISION_PATTERN.fullmatch(str(payload.get("code_revision", ""))):
            return False
        blockers = payload.get("blockers")
        if not isinstance(blockers, list) or blockers:
            return False
        created_at = _parse_timestamp(payload.get("created_at"))
        as_of = query.as_of.astimezone(UTC)
        age = as_of - created_at
        return -self.future_tolerance <= age <= self.max_evidence_age

    def _artifact_matches(self, payload: Mapping[str, object]) -> bool:
        raw_path = payload.get("artifact_path")
        expected_hash = str(payload.get("artifact_sha256", ""))
        if not _bounded_text(raw_path, 512) or not _SHA256_PATTERN.fullmatch(
            expected_hash
        ):
            return False
        relative = Path(str(raw_path).replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            return False
        resolved_root = self.root.resolve()
        artifact = (resolved_root / relative).resolve()
        if not artifact.is_relative_to(resolved_root) or not artifact.is_file():
            return False
        if artifact.stat().st_size > self.max_artifact_bytes:
            return False
        if _sha256_file(artifact) != expected_hash:
            return False
        raw_artifact = json.loads(artifact.read_text(encoding="utf-8"))
        if not isinstance(raw_artifact, Mapping):
            return False
        return _serialized_artifact_has_futures_lineage(
            cast(Mapping[str, object], raw_artifact),
            evidence=payload,
        )


@dataclass(frozen=True, slots=True)
class FuturesOosEvidenceWriteResult:
    """Verified local publication result with no execution authority."""

    evidence_path: str
    artifact_path: str
    evidence_id: str
    artifact_sha256: str
    created: bool
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        identities = (
            self.evidence_path,
            self.artifact_path,
            self.evidence_id,
            self.artifact_sha256,
        )
        if any(not value.strip() for value in identities):
            raise ValueError("Futures OOS write result identity is required")
        if not _SHA256_PATTERN.fullmatch(self.artifact_sha256):
            raise ValueError("Futures OOS write result hash is invalid")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("Futures OOS evidence cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class FuturesOosEvidenceWriter:
    """Persist only canonically approved, exact-bound Futures OOS reports."""

    root: Path

    def write(
        self,
        report: WalkForwardReport,
        *,
        setup_name: str,
        strategy_sha256: str,
        dataset_sha256: str,
        code_revision: str,
    ) -> FuturesOosEvidenceWriteResult:
        normalized_symbol = report.symbol.strip().upper()
        self._validate_report(
            report,
            symbol=normalized_symbol,
            setup_name=setup_name,
            strategy_sha256=strategy_sha256,
            dataset_sha256=dataset_sha256,
            code_revision=code_revision,
        )
        directory = self.root / normalized_symbol / report.timeframe
        stem = setup_name.lower()
        artifact_path = directory / f"{stem}.oos.json"
        evidence_path = directory / f"{stem}.oos-evidence.json"
        primitive_report = to_primitive(report)
        if not isinstance(primitive_report, Mapping):
            raise ValueError("Futures OOS report serialization must be an object")
        artifact_payload: Mapping[str, object] = {
            "schema_version": FUTURES_OOS_SCHEMA_VERSION,
            "artifact_type": "FUTURES_OOS_VALIDATION_REPORT",
            "market": "USD_M_FUTURES",
            "symbol": normalized_symbol,
            "timeframe": report.timeframe,
            "setup_name": setup_name,
            "strategy_version": FUTURES_OOS_STRATEGY_VERSION,
            "strategy_sha256": strategy_sha256,
            "dataset_sha256": dataset_sha256,
            "code_revision": code_revision,
            "created_at": report.created_at.isoformat(),
            "validation_status": "OOS_VALIDATED",
            "promotion_status": "STAGED_CANDIDATE",
            "blockers": [],
            "walk_forward_report": dict(primitive_report),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        artifact_created = _write_immutable_json(
            artifact_path,
            artifact_payload,
            subject_id=report.report_id,
        )
        artifact_sha256 = _sha256_file(artifact_path)
        evidence_id = _evidence_id(
            report.report_id,
            setup_name,
            strategy_sha256,
            dataset_sha256,
        )
        evidence_payload: Mapping[str, object] = {
            "schema_version": FUTURES_OOS_SCHEMA_VERSION,
            "evidence_id": evidence_id,
            "market": "USD_M_FUTURES",
            "symbol": normalized_symbol,
            "timeframe": report.timeframe,
            "setup_name": setup_name,
            "strategy_version": FUTURES_OOS_STRATEGY_VERSION,
            "strategy_sha256": strategy_sha256,
            "dataset_sha256": dataset_sha256,
            "code_revision": code_revision,
            "created_at": report.created_at.isoformat(),
            "validation_status": "OOS_VALIDATED",
            "promotion_status": "STAGED_CANDIDATE",
            "blockers": [],
            "artifact_path": artifact_path.relative_to(self.root).as_posix(),
            "artifact_sha256": artifact_sha256,
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        evidence_created = _write_immutable_json(
            evidence_path,
            evidence_payload,
            subject_id=evidence_id,
        )
        return FuturesOosEvidenceWriteResult(
            evidence_path=evidence_path.as_posix(),
            artifact_path=artifact_path.as_posix(),
            evidence_id=evidence_id,
            artifact_sha256=artifact_sha256,
            created=artifact_created or evidence_created,
        )

    @staticmethod
    def _validate_report(
        report: WalkForwardReport,
        *,
        symbol: str,
        setup_name: str,
        strategy_sha256: str,
        dataset_sha256: str,
        code_revision: str,
    ) -> None:
        if not _SYMBOL_PATTERN.fullmatch(symbol):
            raise ValueError("Futures OOS report symbol identity is invalid")
        if not _TIMEFRAME_PATTERN.fullmatch(report.timeframe):
            raise ValueError("Futures OOS report timeframe identity is invalid")
        if not _SETUP_PATTERN.fullmatch(setup_name):
            raise ValueError("Futures OOS report setup identity is invalid")
        if not _SHA256_PATTERN.fullmatch(strategy_sha256):
            raise ValueError("Futures OOS report strategy hash is invalid")
        if not _SHA256_PATTERN.fullmatch(dataset_sha256):
            raise ValueError("Futures OOS report dataset hash is invalid")
        if not _GIT_REVISION_PATTERN.fullmatch(code_revision):
            raise ValueError("Futures OOS report code revision is invalid")
        if (
            report.oos_validation_status is not OOSValidationStatus.APPROVED
            or report.promotion_status is not ValidationStatus.STAGED_CANDIDATE
            or report.blockers
            or report.robustness.blockers
            or report.statistical_evidence.blockers
        ):
            raise ValueError("Futures OOS report is not approved and blocker-free")
        statistics = report.statistical_evidence
        if (
            not statistics.confirmatory
            or statistics.confidence_interval is None
            or statistics.effective_sample_size
            < report.config.min_effective_sample_size
            or len(report.folds) < report.config.min_folds
            or report.robustness.total_oos_trades < report.config.min_oos_trades
            or report.robustness.regime_count < report.config.min_regime_count
        ):
            raise ValueError("Futures OOS report evidence is incomplete")
        if not _report_has_futures_lineage(
            report,
            setup_name=setup_name,
            strategy_sha256=strategy_sha256,
        ):
            raise ValueError("Futures OOS report market lineage is invalid")


def runtime_futures_strategy_sha256(
    *,
    short_lookback: int,
    medium_lookback: int,
    stop_loss_ratio: Decimal = RUNTIME_FUTURES_STOP_LOSS_RATIO,
    take_profit_ratio: Decimal = RUNTIME_FUTURES_TAKE_PROFIT_RATIO,
    minimum_risk_reward: Decimal = RUNTIME_FUTURES_MINIMUM_RISK_REWARD,
    maximum_holding_bars: int = RUNTIME_FUTURES_MAXIMUM_HOLDING_BARS,
) -> str:
    """Bind evidence to the deterministic runtime Futures strategy inputs."""
    if short_lookback < 1 or medium_lookback <= short_lookback:
        raise ValueError("runtime Futures strategy lookbacks are invalid")
    ratios = (stop_loss_ratio, take_profit_ratio, minimum_risk_reward)
    if any(not value.is_finite() or value <= Decimal("0") for value in ratios):
        raise ValueError("runtime Futures strategy ratios must be finite and positive")
    if take_profit_ratio >= Decimal("1"):
        raise ValueError("runtime Futures take-profit ratio must remain below one")
    if take_profit_ratio / stop_loss_ratio < minimum_risk_reward:
        raise ValueError("runtime Futures strategy risk-reward is insufficient")
    if (
        isinstance(maximum_holding_bars, bool)
        or not isinstance(maximum_holding_bars, int)
        or maximum_holding_bars < 1
    ):
        raise ValueError("runtime Futures maximum holding bars must be positive")
    payload = {
        "component": "RuntimeFuturesAdvisor",
        "market": "USD_M_FUTURES",
        "strategy_version": FUTURES_OOS_STRATEGY_VERSION,
        "timeframe": "1h",
        "feature_engine": {
            "medium_lookback": medium_lookback,
            "short_lookback": short_lookback,
        },
        "signal_contract": {
            "maximum_holding_bars": maximum_holding_bars,
            "minimum_risk_reward": str(minimum_risk_reward),
            "stop_loss_ratio": str(stop_loss_ratio),
            "take_profit_ratio": str(take_profit_ratio),
        },
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _report_has_futures_lineage(
    report: WalkForwardReport,
    *,
    setup_name: str,
    strategy_sha256: str,
) -> bool:
    if report.robustness.total_oos_trades != sum(
        len(fold.oos_result.trades) for fold in report.folds
    ):
        return False
    return all(
        _result_has_futures_lineage(
            result,
            symbol=report.symbol,
            timeframe=report.timeframe,
            setup_name=setup_name,
            strategy_sha256=strategy_sha256,
        )
        for fold in report.folds
        for result in (fold.training_result, fold.oos_result)
    )


def _result_has_futures_lineage(
    result: BacktestResult,
    *,
    symbol: str,
    timeframe: str,
    setup_name: str,
    strategy_sha256: str,
) -> bool:
    metrics = result.metrics
    performance = result.performance_engine_report
    if (
        result.symbol != symbol
        or result.timeframe != timeframe
        or metrics.market != "USD_M_FUTURES"
        or performance.spot_metrics is not None
        or performance.futures_metrics != metrics
        or metrics.trade_count != len(result.trades)
        or any(
            "DATA_UNAVAILABLE" in rejected.blockers
            for rejected in result.rejected_signals
        )
        or len(result.trade_outcomes) != len(result.trades)
        or result.trade_outcomes
        != tuple(trade.trade_outcome for trade in result.trades)
    ):
        return False
    expected = (
        FUTURES_OOS_STRATEGY_ID,
        FUTURES_OOS_STRATEGY_VERSION,
        strategy_sha256,
        "USD_M_FUTURES",
        symbol,
        setup_name,
        timeframe,
    )
    if any(
        (
            trade.attribution.strategy_id,
            trade.attribution.strategy_version,
            trade.attribution.strategy_config_hash,
            trade.attribution.market,
            trade.attribution.symbol,
            trade.attribution.regime,
            trade.attribution.timeframe,
        )
        != expected
        for trade in result.trades
    ):
        return False
    outcome_expected = (
        FUTURES_OOS_STRATEGY_ID,
        FUTURES_OOS_STRATEGY_VERSION,
        "USD_M_FUTURES",
        symbol,
        setup_name,
    )
    if any(
        (
            outcome.strategy_id,
            outcome.strategy_version,
            outcome.market,
            outcome.symbol,
            outcome.regime,
        )
        != outcome_expected
        for outcome in result.trade_outcomes
    ):
        return False
    return all(
        (
            record.strategy_id,
            record.strategy_version,
            record.market,
            record.symbol,
            record.regime,
        )
        == outcome_expected
        for record in result.missed_opportunity_ledger.records
    )


def _serialized_artifact_has_futures_lineage(
    artifact: Mapping[str, object],
    *,
    evidence: Mapping[str, object],
) -> bool:
    mirrored_fields = (
        "schema_version",
        "market",
        "symbol",
        "timeframe",
        "setup_name",
        "strategy_version",
        "strategy_sha256",
        "dataset_sha256",
        "code_revision",
        "created_at",
        "validation_status",
        "promotion_status",
        "blockers",
        "execution_allowed",
        "live_eligibility_status",
    )
    if artifact.get("artifact_type") != "FUTURES_OOS_VALIDATION_REPORT" or any(
        artifact.get(field) != evidence.get(field) for field in mirrored_fields
    ):
        return False
    report = artifact.get("walk_forward_report")
    if not isinstance(report, Mapping):
        return False
    report_mapping = cast(Mapping[str, object], report)
    expected_report = {
        "symbol": evidence.get("symbol"),
        "timeframe": evidence.get("timeframe"),
        "created_at": evidence.get("created_at"),
        "oos_validation_status": "APPROVED",
        "promotion_status": "STAGED_CANDIDATE",
        "blockers": [],
    }
    if any(report_mapping.get(key) != value for key, value in expected_report.items()):
        return False
    report_id = report_mapping.get("report_id")
    if not _bounded_text(report_id, 128) or evidence.get("evidence_id") != _evidence_id(
        str(report_id),
        str(evidence.get("setup_name", "")),
        str(evidence.get("strategy_sha256", "")),
        str(evidence.get("dataset_sha256", "")),
    ):
        return False
    robustness = report_mapping.get("robustness")
    statistics = report_mapping.get("statistical_evidence")
    folds = report_mapping.get("folds")
    if (
        not isinstance(robustness, Mapping)
        or robustness.get("blockers") != []
        or not isinstance(statistics, Mapping)
        or statistics.get("blockers") != []
        or not isinstance(folds, list)
        or not folds
    ):
        return False
    return all(
        _serialized_fold_has_futures_lineage(
            fold,
            symbol=str(evidence.get("symbol", "")),
            timeframe=str(evidence.get("timeframe", "")),
            setup_name=str(evidence.get("setup_name", "")),
            strategy_sha256=str(evidence.get("strategy_sha256", "")),
        )
        for fold in folds
    )


def _serialized_fold_has_futures_lineage(
    value: object,
    *,
    symbol: str,
    timeframe: str,
    setup_name: str,
    strategy_sha256: str,
) -> bool:
    if not isinstance(value, Mapping):
        return False
    return all(
        _serialized_result_has_futures_lineage(
            value.get(key),
            symbol=symbol,
            timeframe=timeframe,
            setup_name=setup_name,
            strategy_sha256=strategy_sha256,
        )
        for key in ("training_result", "oos_result")
    )


def _serialized_result_has_futures_lineage(
    value: object,
    *,
    symbol: str,
    timeframe: str,
    setup_name: str,
    strategy_sha256: str,
) -> bool:
    if not isinstance(value, Mapping):
        return False
    metrics = value.get("metrics")
    performance = value.get("performance_engine_report")
    trades = value.get("trades")
    outcomes = value.get("trade_outcomes")
    rejected = value.get("rejected_signals")
    missed = value.get("missed_opportunity_ledger")
    if (
        value.get("symbol") != symbol
        or value.get("timeframe") != timeframe
        or not isinstance(metrics, Mapping)
        or metrics.get("market") != "USD_M_FUTURES"
        or not isinstance(performance, Mapping)
        or performance.get("spot_metrics") is not None
        or performance.get("futures_metrics") != metrics
        or not isinstance(trades, list)
        or metrics.get("trade_count") != len(trades)
        or not isinstance(outcomes, list)
        or len(outcomes) != len(trades)
        or not isinstance(rejected, list)
        or any(_serialized_rejection_has_missing_data(item) for item in rejected)
        or not isinstance(missed, Mapping)
    ):
        return False
    expected_trade = {
        "strategy_id": FUTURES_OOS_STRATEGY_ID,
        "strategy_version": FUTURES_OOS_STRATEGY_VERSION,
        "strategy_config_hash": strategy_sha256,
        "market": "USD_M_FUTURES",
        "symbol": symbol,
        "regime": setup_name,
        "timeframe": timeframe,
    }
    if any(
        not isinstance(trade, Mapping)
        or not isinstance(trade.get("attribution"), Mapping)
        or any(
            trade["attribution"].get(key) != expected
            for key, expected in expected_trade.items()
        )
        for trade in trades
    ):
        return False
    expected_outcome = {
        key: value
        for key, value in expected_trade.items()
        if key != "strategy_config_hash" and key != "timeframe"
    }
    if any(
        not isinstance(outcome, Mapping)
        or any(
            outcome.get(key) != expected for key, expected in expected_outcome.items()
        )
        for outcome in outcomes
    ):
        return False
    records = missed.get("records")
    return isinstance(records, list) and all(
        isinstance(record, Mapping)
        and all(
            record.get(key) == expected for key, expected in expected_outcome.items()
        )
        for record in records
    )


def _serialized_rejection_has_missing_data(value: object) -> bool:
    if not isinstance(value, Mapping):
        return True
    blockers = value.get("blockers")
    return not isinstance(blockers, list) or "DATA_UNAVAILABLE" in blockers


def _parse_timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Futures OOS created_at must be timezone-aware")
    return parsed.astimezone(UTC)


def _bounded_text(value: object, maximum_length: int) -> bool:
    return (
        isinstance(value, str) and bool(value.strip()) and len(value) <= maximum_length
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_immutable_json(
    path: Path,
    payload: Mapping[str, object],
    *,
    subject_id: str,
) -> bool:
    if path.exists():
        existing = read_json_object(path, blocker="FUTURES_OOS_EVIDENCE_UNREADABLE")
        if dict(existing) != dict(payload):
            raise ValueError("FUTURES_OOS_EVIDENCE_CONFLICT")
        return False
    write_json_object_verified(
        path,
        payload,
        blocker="FUTURES_OOS_EVIDENCE_WRITE_UNVERIFIED",
        subject_id=subject_id,
        indent=2,
        durable=True,
    )
    return True


def _evidence_id(
    report_id: str,
    setup_name: str,
    strategy_sha256: str,
    dataset_sha256: str,
) -> str:
    identity = json.dumps(
        {
            "dataset_sha256": dataset_sha256,
            "report_id": report_id,
            "setup_name": setup_name,
            "strategy_sha256": strategy_sha256,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"futures-oos:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"

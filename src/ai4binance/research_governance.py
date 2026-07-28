"""Research run cards, hypothesis lifecycle and demotion-only decay governance."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import cast

from ai4binance.reporting import to_primitive
from ai4binance.storage import AuditEvent, JsonlAuditStore, write_json_object_verified


def _require_identity(**values: str) -> None:
    missing = tuple(name for name, value in values.items() if not value.strip())
    if missing:
        raise ValueError(
            f"research identity fields cannot be empty: {', '.join(missing)}"
        )


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class HypothesisStatus(StrEnum):
    """Human-governed research and strategy lifecycle states."""

    PROPOSED = "PROPOSED"
    RESEARCH = "RESEARCH"
    OOS_VALIDATED = "OOS_VALIDATED"
    PAPER_APPROVED = "PAPER_APPROVED"
    MONITORING = "MONITORING"
    DECAYED = "DECAYED"
    DISABLED = "DISABLED"
    REJECTED = "REJECTED"


_ALLOWED_TRANSITIONS: Mapping[HypothesisStatus, frozenset[HypothesisStatus]] = (
    MappingProxyType(
        {
            HypothesisStatus.PROPOSED: frozenset(
                {HypothesisStatus.RESEARCH, HypothesisStatus.REJECTED}
            ),
            HypothesisStatus.RESEARCH: frozenset(
                {HypothesisStatus.OOS_VALIDATED, HypothesisStatus.REJECTED}
            ),
            HypothesisStatus.OOS_VALIDATED: frozenset(
                {HypothesisStatus.PAPER_APPROVED, HypothesisStatus.REJECTED}
            ),
            HypothesisStatus.PAPER_APPROVED: frozenset(
                {HypothesisStatus.MONITORING, HypothesisStatus.DISABLED}
            ),
            HypothesisStatus.MONITORING: frozenset(
                {HypothesisStatus.DECAYED, HypothesisStatus.DISABLED}
            ),
            HypothesisStatus.DECAYED: frozenset({HypothesisStatus.DISABLED}),
            HypothesisStatus.DISABLED: frozenset(),
            HypothesisStatus.REJECTED: frozenset(),
        }
    )
)


@dataclass(frozen=True, slots=True)
class ResearchHypothesis:
    """Falsifiable research hypothesis linked to immutable artifacts."""

    hypothesis_id: str
    title: str
    thesis: str
    symbol: str
    timeframe: str
    invalidation_conditions: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    artifact_ids: tuple[str, ...] = ()
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(
            hypothesis_id=self.hypothesis_id,
            title=self.title,
            thesis=self.thesis,
            symbol=self.symbol,
            timeframe=self.timeframe,
        )
        _require_aware("hypothesis created_at", self.created_at)
        _require_aware("hypothesis updated_at", self.updated_at)
        if not self.invalidation_conditions or any(
            not item.strip() for item in self.invalidation_conditions
        ):
            raise ValueError("hypothesis requires explicit invalidation conditions")
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("hypothesis artifact IDs must be unique")
        if self.execution_allowed:
            raise ValueError("research hypothesis cannot grant execution authority")

    def transition(
        self,
        status: HypothesisStatus,
        *,
        updated_at: datetime,
        artifact_ids: tuple[str, ...] = (),
    ) -> ResearchHypothesis:
        """Apply an explicit forward or demotion transition."""
        if status not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValueError(f"invalid hypothesis transition: {self.status}->{status}")
        _require_aware("hypothesis updated_at", updated_at)
        merged = tuple(dict.fromkeys((*self.artifact_ids, *artifact_ids)))
        return replace(self, status=status, updated_at=updated_at, artifact_ids=merged)


@dataclass(frozen=True, slots=True)
class HypothesisRegistry:
    """Immutable registry; persistence is append-only through an optional ledger."""

    hypotheses: tuple[ResearchHypothesis, ...] = ()
    ledger: JsonlAuditStore | None = field(default=None, compare=False, repr=False)

    def add(self, hypothesis: ResearchHypothesis) -> HypothesisRegistry:
        if any(
            item.hypothesis_id == hypothesis.hypothesis_id for item in self.hypotheses
        ):
            raise ValueError("hypothesis ID already exists")
        self._record("HYPOTHESIS_CREATED", hypothesis)
        return HypothesisRegistry((*self.hypotheses, hypothesis), self.ledger)

    def update(self, hypothesis: ResearchHypothesis) -> HypothesisRegistry:
        matches = tuple(
            index
            for index, item in enumerate(self.hypotheses)
            if item.hypothesis_id == hypothesis.hypothesis_id
        )
        if len(matches) != 1:
            raise KeyError(hypothesis.hypothesis_id)
        items = list(self.hypotheses)
        items[matches[0]] = hypothesis
        self._record("HYPOTHESIS_TRANSITIONED", hypothesis)
        return HypothesisRegistry(tuple(items), self.ledger)

    def get(self, hypothesis_id: str) -> ResearchHypothesis:
        matches = tuple(
            item for item in self.hypotheses if item.hypothesis_id == hypothesis_id
        )
        if len(matches) != 1:
            raise KeyError(hypothesis_id)
        return matches[0]

    def _record(self, event_type: str, hypothesis: ResearchHypothesis) -> None:
        if self.ledger is None:
            return
        self.ledger.append_verified(
            AuditEvent(
                event_type=event_type,
                timestamp=hypothesis.updated_at,
                payload={"hypothesis": hypothesis},
            )
        )


@dataclass(frozen=True, slots=True)
class ResearchRunCard:
    """Hash-linked evidence manifest for one reproducible research run."""

    run_id: str
    created_at: datetime
    symbol: str
    timeframe: str
    hypothesis_id: str
    dataset_sha256: str
    config_sha256: str
    strategy_sha256: str
    code_revision: str
    random_seed: int
    fee_rate: float
    slippage_rate: float
    metrics: tuple[tuple[str, float], ...]
    artifact_sha256: tuple[tuple[str, str], ...]
    blockers: tuple[str, ...]
    promotion_status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(
            run_id=self.run_id,
            symbol=self.symbol,
            timeframe=self.timeframe,
            hypothesis_id=self.hypothesis_id,
            code_revision=self.code_revision,
        )
        _require_aware("run card created_at", self.created_at)
        hashes = (
            self.dataset_sha256,
            self.config_sha256,
            self.strategy_sha256,
            *(digest for _path, digest in self.artifact_sha256),
        )
        if any(
            len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            for digest in hashes
        ):
            raise ValueError("run-card hashes must be lowercase SHA-256")
        if self.random_seed < 0:
            raise ValueError("run-card random seed cannot be negative")
        numeric = (
            self.fee_rate,
            self.slippage_rate,
            *(value for _key, value in self.metrics),
        )
        if any(not isfinite(value) for value in numeric):
            raise ValueError("run-card numeric values must be finite")
        if min(self.fee_rate, self.slippage_rate) < 0.0:
            raise ValueError("run-card costs cannot be negative")
        metric_keys = tuple(key for key, _value in self.metrics)
        artifact_paths = tuple(path for path, _digest in self.artifact_sha256)
        if len(set(metric_keys)) != len(metric_keys):
            raise ValueError("run-card metric keys must be unique")
        if len(set(artifact_paths)) != len(artifact_paths):
            raise ValueError("run-card artifact paths must be unique")
        if self.promotion_status not in {"RESEARCH_ONLY", "STAGED_CANDIDATE"}:
            raise ValueError("run card cannot approve paper or live execution")
        if self.promotion_status == "STAGED_CANDIDATE" and self.blockers:
            raise ValueError("staged run card cannot contain blockers")
        if self.execution_allowed:
            raise ValueError("run card cannot grant execution authority")

    @staticmethod
    def hash_json(value: Mapping[str, object]) -> str:
        """Return a stable hash for JSON-compatible configuration."""
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ResearchRunCardWriter:
    """Atomically persist a run card and optionally append its audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, card: ResearchRunCard) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(card)),
            blocker="RESEARCH_RUN_CARD_DESTINATION_VERIFY_FAILED",
            subject_id=card.run_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="RESEARCH_RUN_CARD_WRITTEN",
                    timestamp=card.created_at,
                    payload={"run_card": card},
                )
            )


_BLOCKER_GUIDANCE: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "WEAK_OOS_FOLD_CONSISTENCY": (
            "Rerun fold-level OOS diagnostics with regime split and checkpointed "
            "progress; do not lower promotion thresholds.",
            "Sealed HOTUSDT candles, fold metrics, regime labels, and cost "
            "assumptions.",
        ),
        "OOS_RETURN_INSUFFICIENT": (
            "Inspect setup quality and cost-adjusted expectancy before testing a "
            "narrower playbook variant.",
            "Walk-forward returns, buy-and-hold benchmark, and fee/slippage model.",
        ),
        "UNSTABLE_PARAMETER_SENSITIVITY": (
            "Expand local-neighborhood sensitivity checks around the selected "
            "candidate and reject brittle optima.",
            "Tuning grid, selected parameters, neighbor scores, and OOS folds.",
        ),
        "INSUFFICIENT_SENSITIVITY_NEIGHBORS": (
            "Add bounded neighboring parameter candidates before staging the setup.",
            "Approved tuning domains and adjacent parameter evaluations.",
        ),
        "COST_STRESS_RETURN_NOT_POSITIVE": (
            "Review spread, slippage, volume participation, and entry timing; keep "
            "the strategy research-only until stressed returns are positive.",
            "Backtest result, cost stress scenarios, spread and liquidity evidence.",
        ),
        "BOOTSTRAP_LOSS_PROBABILITY_HIGH": (
            "Run path-dependent trade-order diagnostics and look for edge "
            "concentration before changing parameters.",
            "Trade PnL sequence, bootstrap seed, and path Monte Carlo report.",
        ),
        "BOOTSTRAP_DRAWDOWN_EXCESSIVE": (
            "Stress protective exits and staged-exit rules; reject if tail "
            "drawdown remains excessive.",
            "Trade lifecycle records, drawdown path, stop and trailing review.",
        ),
        "LOW_STRESS_TRADE_COUNT": (
            "Collect more closed-candle history or narrow the setup definition "
            "only after preserving sample-size gates.",
            "Longer sealed dataset and stress-scenario trade counts.",
        ),
        "LOW_OOS_TRADE_COUNT": (
            "Increase validation horizon before interpreting expectancy.",
            "Longer OOS folds and trade-count distribution.",
        ),
        "INSUFFICIENT_REGIME_COVERAGE": (
            "Add explicit trend, range, and high-volatility regime coverage before "
            "promotion.",
            "Regime labels and per-regime OOS metrics.",
        ),
        "LEVEL_REACTION_EVIDENCE_INSUFFICIENT": (
            "Build reaction-statistics evidence for the zone using closed candles "
            "and ATR-buffered outcomes.",
            "Support/resistance zones, touch counts, reaction outcomes, and "
            "false-breakout records.",
        ),
        "INSUFFICIENT_VALIDATION_CANDLES": (
            "Archive more verified public Spot history before running promotion "
            "evidence.",
            "Checksum-verified OHLCV archive for the requested timeframe.",
        ),
        "HISTORICAL_SPOT_INVENTORY_SELL_NOT_SUPPORTED": (
            "Keep historical Spot SELL validation separate from naked-short logic; "
            "add inventory-aware replay before testing SELL playbooks.",
            "Historical inventory ledger, cost basis, and sell-only reduction rules.",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class ResearchBlockerObservation:
    """One observed validation blocker with bounded occurrence count."""

    symbol: str
    timeframe: str
    playbook: str
    blocker: str
    count: int = 1

    def __post_init__(self) -> None:
        _require_identity(
            symbol=self.symbol,
            timeframe=self.timeframe,
            playbook=self.playbook,
            blocker=self.blocker,
        )
        if self.count < 1:
            raise ValueError("blocker observation count must be positive")


@dataclass(frozen=True, slots=True)
class ResearchBlockerAction:
    """Actionable research-only next step for one blocker class."""

    blocker: str
    occurrences: int
    affected_playbooks: tuple[str, ...]
    affected_timeframes: tuple[str, ...]
    recommended_experiment: str
    required_data: str
    status: str = "RESEARCH_ONLY"

    def __post_init__(self) -> None:
        _require_identity(
            blocker=self.blocker,
            recommended_experiment=self.recommended_experiment,
            required_data=self.required_data,
            status=self.status,
        )
        if self.occurrences < 1:
            raise ValueError("blocker occurrences must be positive")
        if not self.affected_playbooks or not self.affected_timeframes:
            raise ValueError("blocker action requires affected scope")
        if self.status != "RESEARCH_ONLY":
            raise ValueError("blocker actions cannot promote execution")


@dataclass(frozen=True, slots=True)
class ResearchBlockerDashboard:
    """Read-only OOS blocker dashboard with no trading authority."""

    dashboard_id: str
    created_at: datetime
    symbol: str
    actions: tuple[ResearchBlockerAction, ...]
    promotion_status: str = "RESEARCH_ONLY"
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        _require_identity(dashboard_id=self.dashboard_id, symbol=self.symbol)
        _require_aware("blocker dashboard created_at", self.created_at)
        if self.promotion_status != "RESEARCH_ONLY":
            raise ValueError("blocker dashboard cannot promote research")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("blocker dashboard must remain live blocked")
        if self.execution_allowed:
            raise ValueError("blocker dashboard cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class ResearchBlockerDashboardWriter:
    """Atomically persist a blocker dashboard and append an audit event."""

    path: Path
    ledger: JsonlAuditStore | None = None

    def write(self, dashboard: ResearchBlockerDashboard) -> None:
        write_json_object_verified(
            self.path,
            cast(dict[str, object], to_primitive(dashboard)),
            blocker="RESEARCH_BLOCKER_DASHBOARD_DESTINATION_VERIFY_FAILED",
            subject_id=dashboard.dashboard_id,
            indent=2,
        )
        if self.ledger is not None:
            self.ledger.append_verified(
                AuditEvent(
                    event_type="RESEARCH_BLOCKER_DASHBOARD_WRITTEN",
                    timestamp=dashboard.created_at,
                    payload={"dashboard": dashboard},
                )
            )


def build_research_blocker_dashboard(
    *,
    dashboard_id: str,
    created_at: datetime,
    symbol: str,
    observations: tuple[ResearchBlockerObservation, ...],
) -> ResearchBlockerDashboard:
    """Convert validation blockers into deterministic research-only actions."""
    _require_aware("blocker dashboard created_at", created_at)
    grouped: dict[str, list[ResearchBlockerObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.blocker, []).append(observation)
    actions = tuple(
        _build_blocker_action(blocker, tuple(items))
        for blocker, items in sorted(grouped.items())
    )
    return ResearchBlockerDashboard(
        dashboard_id=dashboard_id,
        created_at=created_at,
        symbol=symbol.strip().upper(),
        actions=actions,
    )


def _build_blocker_action(
    blocker: str,
    observations: tuple[ResearchBlockerObservation, ...],
) -> ResearchBlockerAction:
    experiment, required_data = _BLOCKER_GUIDANCE.get(
        blocker,
        (
            "Inspect the blocker source, add a falsifiable regression fixture, "
            "and keep the candidate research-only.",
            "Source artifact, deterministic reproduction case, and validation log.",
        ),
    )
    return ResearchBlockerAction(
        blocker=blocker,
        occurrences=sum(item.count for item in observations),
        affected_playbooks=tuple(sorted({item.playbook for item in observations})),
        affected_timeframes=tuple(sorted({item.timeframe for item in observations})),
        recommended_experiment=experiment,
        required_data=required_data,
    )


@dataclass(frozen=True, slots=True)
class StrategyHealthSnapshot:
    """Point-in-time paper/OOS strategy health evidence."""

    strategy_id: str
    observed_at: datetime
    oos_trade_count: int
    expectancy: float
    profit_factor: float
    max_drawdown: float
    turnover: float
    regime_count: int

    def __post_init__(self) -> None:
        if (
            not self.strategy_id.strip()
            or self.oos_trade_count < 0
            or self.regime_count < 0
        ):
            raise ValueError("strategy health identity or counts are invalid")
        _require_aware("strategy health observed_at", self.observed_at)
        values = (self.expectancy, self.profit_factor, self.max_drawdown, self.turnover)
        if any(not isfinite(value) for value in values):
            raise ValueError("strategy health values must be finite")
        if min(self.max_drawdown, self.turnover) < 0.0:
            raise ValueError("strategy health risk values cannot be negative")


@dataclass(frozen=True, slots=True)
class DecayPolicy:
    """Conservative thresholds; automation may demote but never promote."""

    min_oos_trades: int = 20
    min_expectancy: float = 0.0
    min_profit_factor: float = 1.0
    max_drawdown: float = 0.25
    max_turnover: float = 0.25
    min_regime_count: int = 2
    warnings_for_monitoring: int = 2
    critical_for_decay: int = 2
    critical_for_disable: int = 3

    def __post_init__(self) -> None:
        counts = (
            self.min_oos_trades,
            self.min_regime_count,
            self.warnings_for_monitoring,
            self.critical_for_decay,
            self.critical_for_disable,
        )
        if any(value < 1 for value in counts):
            raise ValueError("decay policy counts must be positive")


@dataclass(frozen=True, slots=True)
class DecayDecision:
    """Demotion recommendation with no automatic recovery or promotion."""

    current_status: HypothesisStatus
    recommended_status: HypothesisStatus
    reason_codes: tuple[str, ...]
    human_reapproval_required: bool = True
    auto_promotion_allowed: bool = False

    def __post_init__(self) -> None:
        if self.auto_promotion_allowed or not self.human_reapproval_required:
            raise ValueError("decay decisions cannot auto-promote")


@dataclass(frozen=True, slots=True)
class StrategyDecayEvaluator:
    """Evaluate consecutive weak evidence and recommend demotion only."""

    policy: DecayPolicy = DecayPolicy()

    def evaluate(
        self,
        current_status: HypothesisStatus,
        snapshots: tuple[StrategyHealthSnapshot, ...],
    ) -> DecayDecision:
        if not snapshots:
            return DecayDecision(
                current_status,
                current_status,
                ("STRATEGY_HEALTH_EVIDENCE_MISSING",),
            )
        reason_sets = tuple(self._reasons(item) for item in snapshots)
        weak = tuple(bool(reasons) for reasons in reason_sets)
        critical = tuple(self._critical(reasons) for reasons in reason_sets)
        recommended = current_status
        if current_status is HypothesisStatus.PAPER_APPROVED and self._tail_all(
            weak, self.policy.warnings_for_monitoring
        ):
            recommended = HypothesisStatus.MONITORING
        elif current_status is HypothesisStatus.MONITORING and self._tail_all(
            critical, self.policy.critical_for_decay
        ):
            recommended = HypothesisStatus.DECAYED
        elif current_status is HypothesisStatus.DECAYED and self._tail_all(
            critical, self.policy.critical_for_disable
        ):
            recommended = HypothesisStatus.DISABLED
        reasons = tuple(dict.fromkeys(code for items in reason_sets for code in items))
        return DecayDecision(current_status, recommended, reasons)

    def _reasons(self, item: StrategyHealthSnapshot) -> tuple[str, ...]:
        checks = (
            (item.oos_trade_count < self.policy.min_oos_trades, "DECAY_LOW_SAMPLE"),
            (item.expectancy <= self.policy.min_expectancy, "DECAY_EXPECTANCY"),
            (item.profit_factor < self.policy.min_profit_factor, "DECAY_PROFIT_FACTOR"),
            (item.max_drawdown > self.policy.max_drawdown, "DECAY_DRAWDOWN"),
            (item.turnover > self.policy.max_turnover, "DECAY_TURNOVER"),
            (item.regime_count < self.policy.min_regime_count, "DECAY_REGIME_COVERAGE"),
        )
        return tuple(code for failed, code in checks if failed)

    @staticmethod
    def _critical(reasons: tuple[str, ...]) -> bool:
        return any(
            code in {"DECAY_EXPECTANCY", "DECAY_DRAWDOWN", "DECAY_PROFIT_FACTOR"}
            for code in reasons
        )

    @staticmethod
    def _tail_all(values: tuple[bool, ...], count: int) -> bool:
        return len(values) >= count and all(values[-count:])

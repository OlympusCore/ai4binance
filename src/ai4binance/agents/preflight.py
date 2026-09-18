"""Deterministic applicability planning for bounded analytical capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai4binance.agents.registry import (
    CapabilityBundleRegistry,
    CapabilityDefinition,
    CapabilityRegistry,
)
from ai4binance.schemas import MarketSnapshot


class CapabilityPreflightMode(StrEnum):
    """Bounded analysis-cost modes with no authority implications."""

    STANDARD = "STANDARD"
    ECONOMY = "ECONOMY"


@dataclass(frozen=True, slots=True)
class CapabilityPreflightDecision:
    """One visible admission outcome before any capability worker is created."""

    capability_id: str
    scheduled: bool
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.capability_id.strip():
            raise ValueError("preflight capability identity cannot be empty")
        if len(set(self.reason_codes)) != len(self.reason_codes) or any(
            not code.strip() for code in self.reason_codes
        ):
            raise ValueError("preflight reason codes must be unique non-empty values")
        if self.scheduled and self.reason_codes:
            raise ValueError("scheduled capabilities cannot carry skip reason codes")
        if not self.scheduled and not self.reason_codes:
            raise ValueError("skipped capabilities require deterministic reason codes")


@dataclass(frozen=True, slots=True)
class CapabilityPreflightPlan:
    """Immutable scheduler input that retains skipped-capability provenance."""

    mode: CapabilityPreflightMode
    decisions: tuple[CapabilityPreflightDecision, ...]

    def __post_init__(self) -> None:
        identities = tuple(item.capability_id for item in self.decisions)
        if len(set(identities)) != len(identities):
            raise ValueError("preflight capability identities must be unique")

    @property
    def scheduled_ids(self) -> tuple[str, ...]:
        """Return capabilities admitted to the dependency-aware worker scheduler."""
        return tuple(item.capability_id for item in self.decisions if item.scheduled)

    @property
    def skipped(self) -> tuple[CapabilityPreflightDecision, ...]:
        """Return visible non-execution outcomes in catalog order."""
        return tuple(item for item in self.decisions if not item.scheduled)


@dataclass(frozen=True, slots=True)
class CapabilityBundlePreflightDecision:
    """Bundle-level view of immutable capability preflight outcomes."""

    bundle_id: str
    scheduled_capability_ids: tuple[str, ...]
    skipped_capability_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.bundle_id.strip():
            raise ValueError("preflight bundle identity cannot be empty")
        all_ids = (*self.scheduled_capability_ids, *self.skipped_capability_ids)
        if not all_ids or len(set(all_ids)) != len(all_ids):
            raise ValueError("preflight bundle membership must be unique and non-empty")

    @property
    def scheduled(self) -> bool:
        """Return whether this bundle has at least one admitted capability."""
        return bool(self.scheduled_capability_ids)


@dataclass(frozen=True, slots=True)
class CapabilityBundlePreflightPlan:
    """Immutable bundle view that does not alter capability admission semantics."""

    decisions: tuple[CapabilityBundlePreflightDecision, ...]

    def __post_init__(self) -> None:
        bundle_ids = tuple(item.bundle_id for item in self.decisions)
        if len(set(bundle_ids)) != len(bundle_ids):
            raise ValueError("preflight bundle identities must be unique")

    @property
    def scheduled_bundle_ids(self) -> tuple[str, ...]:
        """Return bundles containing one or more admitted capabilities."""
        return tuple(item.bundle_id for item in self.decisions if item.scheduled)

    @property
    def skipped_bundle_ids(self) -> tuple[str, ...]:
        """Return bundles without an admitted capability in this cycle."""
        return tuple(item.bundle_id for item in self.decisions if not item.scheduled)


def build_capability_preflight_plan(
    registry: CapabilityRegistry,
    snapshot: MarketSnapshot,
    *,
    mode: CapabilityPreflightMode,
) -> CapabilityPreflightPlan:
    """Plan only capabilities applicable to this immutable snapshot and mode."""
    reasons_by_id = {
        definition.capability_id: _preflight_reasons(definition, snapshot, mode)
        for definition in registry.definitions
    }
    capability_ids = frozenset(reasons_by_id)
    changed = True
    while changed:
        changed = False
        for definition in registry.definitions:
            reasons = reasons_by_id[definition.capability_id]
            if reasons:
                continue
            unscheduled_dependency = next(
                (
                    dependency
                    for dependency in definition.dependencies
                    if dependency in capability_ids and reasons_by_id[dependency]
                ),
                None,
            )
            if unscheduled_dependency is not None:
                reasons_by_id[definition.capability_id] = (
                    f"DEPENDENCY_NOT_SCHEDULED:{unscheduled_dependency}",
                )
                changed = True
    return CapabilityPreflightPlan(
        mode=mode,
        decisions=tuple(
            CapabilityPreflightDecision(
                capability_id=definition.capability_id,
                scheduled=not reasons_by_id[definition.capability_id],
                reason_codes=reasons_by_id[definition.capability_id],
            )
            for definition in registry.definitions
        ),
    )


def build_capability_bundle_preflight_plan(
    capability_plan: CapabilityPreflightPlan,
    bundle_registry: CapabilityBundleRegistry,
) -> CapabilityBundlePreflightPlan:
    """Group existing preflight decisions without changing their admission."""
    decisions_by_id = {item.capability_id: item for item in capability_plan.decisions}
    if set(decisions_by_id) != set(bundle_registry.capability_registry.by_id):
        raise ValueError("preflight plan must cover the complete capability registry")
    return CapabilityBundlePreflightPlan(
        decisions=tuple(
            CapabilityBundlePreflightDecision(
                bundle_id=bundle.bundle_id,
                scheduled_capability_ids=tuple(
                    capability_id
                    for capability_id in bundle.capability_ids
                    if decisions_by_id[capability_id].scheduled
                ),
                skipped_capability_ids=tuple(
                    capability_id
                    for capability_id in bundle.capability_ids
                    if not decisions_by_id[capability_id].scheduled
                ),
            )
            for bundle in bundle_registry.definitions
        )
    )


def _preflight_reasons(
    definition: CapabilityDefinition,
    snapshot: MarketSnapshot,
    mode: CapabilityPreflightMode,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not definition.runtime_eligible:
        reasons.append("RUNTIME_NOT_ELIGIBLE")
    if not set(definition.timeframes).intersection(snapshot.timeframes):
        reasons.append("TIMEFRAME_NOT_APPLICABLE")
    for required_data in definition.required_data:
        if not _snapshot_has_required_data(snapshot, required_data):
            reasons.append(f"REQUIRED_DATA_MISSING:{required_data}")
    if mode is CapabilityPreflightMode.ECONOMY and definition.expensive:
        reasons.append("EXPENSIVE_CAPABILITY_DEFERRED")
    if "ALL" not in definition.compatible_regimes:
        reported_regime = snapshot.market_metadata.get("market_regime")
        if not isinstance(reported_regime, str) or not reported_regime.strip():
            reasons.append("REGIME_UNAVAILABLE")
        elif reported_regime.strip().upper() not in definition.compatible_regimes:
            reasons.append("REGIME_NOT_COMPATIBLE")
    return tuple(dict.fromkeys(reasons))


def _snapshot_has_required_data(snapshot: MarketSnapshot, data_id: str) -> bool:
    """Check only explicit snapshot fields; unknown requirements fail closed."""
    if data_id == "ohlcv":
        return any(
            snapshot.ohlcv_by_timeframe.get(item) for item in snapshot.timeframes
        )
    if data_id == "order_book":
        return bool(snapshot.order_book_summary)
    if data_id == "benchmark_data":
        return bool(snapshot.market_metadata.get("benchmark_data"))
    if data_id == "news_snapshot":
        return bool(snapshot.news_snapshot)
    if data_id == "sentiment_snapshot":
        return bool(snapshot.sentiment_snapshot)
    if data_id == "derivatives_snapshot":
        return bool(snapshot.derivatives_snapshot)
    if data_id == "onchain_snapshot":
        return bool(snapshot.onchain_snapshot)
    return data_id == "market_snapshot"

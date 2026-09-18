"""Boundary contracts retained for the fifth coverage remediation batch."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from ai4binance.agents.preflight import (
    CapabilityBundlePreflightDecision,
    CapabilityBundlePreflightPlan,
    CapabilityPreflightDecision,
    CapabilityPreflightMode,
    CapabilityPreflightPlan,
    build_capability_bundle_preflight_plan,
    build_capability_preflight_plan,
)
from ai4binance.agents.registry import (
    CapabilityActivationPolicy,
    CapabilityBundleDefinition,
    CapabilityBundleRegistry,
    CapabilityDefinition,
    CapabilityExecutionClass,
    CapabilityRegistry,
)
from ai4binance.domain.market.markets import CapitalMarket
from ai4binance.enterprise.contracts import DepartmentId, WorkflowIdentity
from ai4binance.enterprise.reviews import (
    PeriodicReviewRecord,
    ReviewCadence,
    ReviewOutcome,
)
from ai4binance.external_intel.normalization.deduplication import (
    DuplicateCluster,
    cluster_duplicates,
)
from ai4binance.market_context import (
    MarketContextBatch,
    MarketContextEvent,
    MarketContextRegistry,
    MarketContextRequest,
    ProviderCapability,
    ProviderHealth,
    ProviderHealthStatus,
)
from ai4binance.multiops.llmops.contracts import (
    BudgetStatus,
    ModelTier,
    ModelUsageRecord,
    ReasoningEffort,
    TaskClass,
    TaskCriticality,
    TokenAccountingSource,
)
from ai4binance.portfolio.risk_reward_gate import (
    RiskRewardGate,
    RiskRewardGateInput,
    RiskRewardGatePolicy,
    RiskRewardGateResult,
)
from tests.test_agents import snapshot

NOW = datetime(2026, 9, 16, tzinfo=UTC)
HASH = "a" * 64


def identity() -> WorkflowIdentity:
    return WorkflowIdentity(
        "wo-coverage",
        "run-coverage",
        "trace-coverage",
        NOW,
        snapshot_id="snapshot-coverage",
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"raw_count": 0}, "counts"),
        ({"unique_author_count": 2}, "exceed"),
        ({"copy_ratio": 2.0}, "within"),
        ({"evidence_ids": ("evidence", "evidence")}, "unique"),
    ],
)
def test_duplicate_cluster_rejects_invalid_aggregation(
    kwargs: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "canonical_text": "same report",
        "raw_count": 1,
        "unique_author_count": 1,
        "evidence_ids": ("evidence",),
        "copy_ratio": 0.0,
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=message):
        DuplicateCluster(**values)  # type: ignore[arg-type]


def test_duplicate_clustering_canonicalizes_urls_and_author_counts() -> None:
    clusters = cluster_duplicates(
        (
            ("evidence-2", "alice", "Read https://example.com now"),
            ("evidence-1", "alice", "read https://mirror.example now"),
            ("evidence-3", "bob", "Different"),
        )
    )
    assert tuple(cluster.canonical_text for cluster in clusters) == (
        "different",
        "read URL now",
    )
    duplicate = clusters[1]
    assert duplicate.raw_count == 2
    assert duplicate.unique_author_count == 1
    assert duplicate.copy_ratio == Decimal("0.5")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: ProviderCapability(
                "provider",
                ("macro", "macro"),
                ("example.com",),
                "v1",
                "public",
                timedelta(days=1),
            ),
            "unique",
        ),
        (
            lambda: ProviderHealth(
                "provider", NOW, ProviderHealthStatus.AVAILABLE, blockers=("blocked",)
            ),
            "cannot contain blockers",
        ),
        (
            lambda: MarketContextRequest("snapshot", "BTCUSDT", datetime(2026, 9, 16)),
            "timezone-aware",
        ),
        (
            lambda: MarketContextBatch(
                "snapshot", (), (), (), (), execution_allowed=True
            ),
            "cannot grant",
        ),
    ],
)
def test_market_context_value_objects_fail_closed(
    factory: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


def test_market_context_event_rejects_unsafe_source_and_invalid_hash() -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        MarketContextEvent(
            "event",
            "provider",
            "title",
            NOW,
            NOW,
            "HIGH",
            "macro",
            "http://example.com",
            "a" * 64,
        )
    with pytest.raises(ValueError, match="SHA-256"):
        MarketContextEvent(
            "event",
            "provider",
            "title",
            NOW,
            NOW,
            "HIGH",
            "macro",
            "https://example.com",
            "bad",
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: RiskRewardGatePolicy(minimum_rr=Decimal("-1")), "non-negative"),
        (
            lambda: RiskRewardGateInput(
                CapitalMarket.SPOT, "BTCUSDT", Decimal("-1"), Decimal("0"), Decimal("0")
            ),
            "non-negative",
        ),
        (lambda: RiskRewardGateResult("", False, ("BLOCKED",)), "required"),
        (lambda: RiskRewardGateResult("BTCUSDT", True, ("BLOCKED",)), "disagree"),
        (
            lambda: RiskRewardGateResult("BTCUSDT", True, (), execution_allowed=True),
            "cannot grant",
        ),
    ],
)
def test_risk_reward_contract_rejects_invalid_or_authorizing_values(
    factory: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: CapabilityPreflightDecision("", True), "identity"),
        (
            lambda: CapabilityPreflightDecision("capability", True, ("SKIPPED",)),
            "scheduled",
        ),
        (
            lambda: CapabilityPreflightDecision("capability", False, ("A", "A")),
            "unique",
        ),
        (
            lambda: CapabilityPreflightDecision("capability", False),
            "skipped",
        ),
        (
            lambda: CapabilityBundlePreflightDecision("", ("capability",), ()),
            "identity",
        ),
        (
            lambda: CapabilityBundlePreflightDecision("bundle", (), ()),
            "membership",
        ),
    ],
)
def test_preflight_value_objects_reject_ambiguous_scheduler_state(
    factory: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


def test_preflight_plans_preserve_visible_scheduled_and_skipped_state() -> None:
    scheduled = CapabilityPreflightDecision("scheduled", True)
    skipped = CapabilityPreflightDecision("skipped", False, ("DATA_MISSING",))
    plan = CapabilityPreflightPlan(
        CapabilityPreflightMode.STANDARD, (scheduled, skipped)
    )
    bundle_plan = CapabilityBundlePreflightPlan(
        (CapabilityBundlePreflightDecision("bundle", ("scheduled",), ("skipped",)),)
    )
    assert plan.scheduled_ids == ("scheduled",)
    assert plan.skipped == (skipped,)
    assert bundle_plan.scheduled_bundle_ids == ("bundle",)
    assert bundle_plan.skipped_bundle_ids == ()


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: ProviderCapability(
                "",
                ("macro",),
                ("example.com",),
                "v1",
                "public",
                timedelta(days=1),
            ),
            "identity",
        ),
        (
            lambda: ProviderCapability(
                "provider",
                ("macro",),
                ("Example.com",),
                "v1",
                "public",
                timedelta(days=1),
            ),
            "normalized",
        ),
        (
            lambda: ProviderCapability(
                "provider",
                ("macro",),
                ("example.com",),
                "v1",
                "public",
                timedelta(0),
            ),
            "positive",
        ),
        (
            lambda: ProviderHealth(
                "", NOW, ProviderHealthStatus.UNAVAILABLE, blockers=("DOWN",)
            ),
            "identity",
        ),
        (
            lambda: ProviderHealth(
                "provider", NOW, ProviderHealthStatus.DEGRADED, blockers=()
            ),
            "requires explicit blockers",
        ),
        (lambda: MarketContextRequest("", "BTCUSDT", NOW), "incomplete"),
        (
            lambda: MarketContextEvent(
                "",
                "provider",
                "title",
                NOW,
                NOW,
                "HIGH",
                "macro",
                "https://example.com",
                HASH,
            ),
            "fields cannot be empty",
        ),
        (
            lambda: MarketContextEvent(
                "event",
                "provider",
                "title",
                datetime(2026, 9, 16),
                NOW,
                "HIGH",
                "macro",
                "https://example.com",
                HASH,
            ),
            "scheduled_at",
        ),
        (
            lambda: MarketContextEvent(
                "event",
                "provider",
                "title",
                NOW,
                NOW,
                "LOW",
                "macro",
                "https://example.com",
                HASH,
            ),
            "impact",
        ),
        (lambda: MarketContextBatch("", (), (), (), ()), "snapshot identity"),
    ],
)
def test_market_context_contracts_cover_each_fail_closed_boundary(
    factory: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


def test_risk_reward_gate_exercises_spot_and_futures_blockers() -> None:
    gate = RiskRewardGate(RiskRewardGatePolicy())
    with pytest.raises(ValueError, match="<= one"):
        RiskRewardGatePolicy(maximum_single_opportunity_pct=Decimal("1.1"))

    spot = gate.evaluate(
        RiskRewardGateInput(
            CapitalMarket.SPOT,
            " btcusdt ",
            Decimal("1.0"),
            Decimal("0.30"),
            Decimal("0.01"),
            daily_loss_limit_clear=False,
            weekly_loss_limit_clear=False,
            oos_confidence=Decimal("0.1"),
            data_quality_ok=False,
            stop_valid=False,
            same_direction_spot_futures=True,
        )
    )
    assert spot.symbol == "BTCUSDT"
    assert set(spot.blockers) >= {
        "DATA_INCOMPLETE",
        "NO_VALID_STOP",
        "INSUFFICIENT_RR",
        "MAXIMUM_SINGLE_OPPORTUNITY_EXCEEDED",
        "LIQUID_RESERVE_DEFICIT",
        "OOS_CONFIDENCE_LOW",
        "DAILY_LOSS_LIMIT",
        "WEEKLY_LOSS_LIMIT",
        "SAME_DIRECTION_SPOT_FUTURES_EXPOSURE",
    }

    futures = gate.evaluate(
        RiskRewardGateInput(
            CapitalMarket.USD_M_FUTURES,
            "ETHUSDT",
            Decimal("2"),
            Decimal("0.01"),
            Decimal("0.50"),
            futures_capital_pct=Decimal("0.20"),
            futures_available_margin_pct=None,
            liquidation_distance_pct=None,
            oos_confidence=Decimal("0.90"),
            data_quality_ok=True,
            stop_valid=True,
        )
    )
    assert {
        "FUTURES_CAPITAL_LIMIT",
        "MARGIN_RESERVE_DEFICIT",
        "LIQUIDATION_RISK",
    } <= set(futures.blockers)
    accepted = gate.evaluate(
        RiskRewardGateInput(
            CapitalMarket.USD_M_FUTURES,
            "ETHUSDT",
            Decimal("2"),
            Decimal("0.01"),
            Decimal("0.50"),
            futures_capital_pct=Decimal("0.01"),
            futures_available_margin_pct=Decimal("0.90"),
            liquidation_distance_pct=Decimal("0.20"),
            oos_confidence=Decimal("0.90"),
            data_quality_ok=True,
            stop_valid=True,
        )
    )
    assert accepted.accepted is True
    with pytest.raises(ValueError, match="symbol"):
        RiskRewardGateInput(
            CapitalMarket.SPOT,
            "",
            Decimal("1"),
            Decimal("0"),
            Decimal("0"),
        )
    with pytest.raises(ValueError, match="blockers"):
        RiskRewardGateResult("BTCUSDT", False, ("",))


def _review_record() -> PeriodicReviewRecord:
    return PeriodicReviewRecord(
        identity(),
        "review-coverage",
        ReviewCadence.MONTHLY,
        DepartmentId.QUALITY_AUDIT,
        "monthly-quality-review",
        ReviewOutcome.CAPA_REQUIRED,
        ("artifact:review",),
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"subject_ref": " "}, "identity"),
        ({"blockers": ("",)}, "cannot contain blanks"),
        ({"blockers": ("A", "A")}, "must be unique"),
        ({"promotion_status": "PAPER_APPROVED"}, "cannot promote"),
        ({"live_eligibility_status": "LIVE_ELIGIBLE"}, "cannot authorize"),
    ],
)
def test_periodic_review_record_covers_remaining_fail_closed_paths(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_review_record(), **changes)  # type: ignore[arg-type]


def test_periodic_review_record_rejects_cadence_mutation_and_approval_drift() -> None:
    review = _review_record()
    with pytest.raises(ValueError, match="outside cadence"):
        replace(review, outcome=ReviewOutcome.PAPER_SOAK_CANDIDATE)
    with pytest.raises(ValueError, match="mutate production"):
        replace(review, production_mutation_allowed=True)
    with pytest.raises(ValueError, match="user approval"):
        replace(review, user_approval_required=False)


def _model_usage(**changes: object) -> ModelUsageRecord:
    values: dict[str, object] = {
        "task_id": "task-1",
        "timestamp": NOW,
        "task_type": "coverage",
        "task_class": TaskClass.MODERATE,
        "criticality": TaskCriticality.MEDIUM,
        "token_accounting_source": TokenAccountingSource.UNAVAILABLE,
        "sanitized_summary": "bounded coverage remediation",
        "model_id": "gpt-test",
        "model_tier": ModelTier.BALANCED,
        "reasoning_effort": ReasoningEffort.LOW,
        "quality_result": "FOCUSED_PASS",
        "budget_status": BudgetStatus.WITHIN_BUDGET,
    }
    values.update(changes)
    return ModelUsageRecord(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"task_id": ""}, "task id"),
        ({"timestamp": datetime(2026, 9, 16)}, "timezone-aware"),
        ({"sanitized_summary": "x" * 513}, "bounded line"),
        ({"sanitized_summary": "contains sk-testsecret"}, "secret-like"),
        ({"input_tokens": -1}, "cannot be negative"),
        ({"estimated_cost_usd": Decimal("-1")}, "non-negative"),
        (
            {
                "input_tokens": 10,
                "cached_input_tokens": 11,
                "token_accounting_source": TokenAccountingSource.ESTIMATED,
                "total_tokens": 12,
            },
            "cached input",
        ),
        ({"input_tokens": 1}, "unavailable token accounting"),
        (
            {"token_accounting_source": TokenAccountingSource.EXACT_PROVIDER},
            "core token counters",
        ),
        (
            {"token_accounting_source": TokenAccountingSource.ESTIMATED},
            "requires total tokens",
        ),
        ({"actual_cost_usd": Decimal("0.01")}, "actual cost"),
        ({"prompt_hash": "bad"}, "prompt hash"),
        ({"files_modified": ("a.py", "a.py")}, "modified file list"),
        ({"model_id": " "}, "model id"),
        ({"escalation_reason": " "}, "escalation reason"),
        ({"execution_allowed": True}, "cannot authorize"),
    ],
)
def test_model_usage_record_covers_secret_budget_and_authority_boundaries(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _model_usage(**changes)


class MarketContextProviderStub:
    def __init__(
        self,
        capability: ProviderCapability,
        *,
        health_status: ProviderHealthStatus = ProviderHealthStatus.AVAILABLE,
        blockers: tuple[str, ...] = (),
        event: MarketContextEvent | None = None,
        fail_health: bool = False,
        fail_fetch: bool = False,
        health_provider_id: str | None = None,
    ) -> None:
        self._capability = capability
        self._health_status = health_status
        self._blockers = blockers
        self._event = event
        self._fail_health = fail_health
        self._fail_fetch = fail_fetch
        self._health_provider_id = health_provider_id

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    def health(self, checked_at: datetime) -> ProviderHealth:
        if self._fail_health:
            raise RuntimeError("health failed")
        return ProviderHealth(
            self._health_provider_id or self._capability.provider_id,
            checked_at,
            self._health_status,
            blockers=self._blockers,
        )

    def fetch(self, _request: MarketContextRequest) -> tuple[MarketContextEvent, ...]:
        if self._fail_fetch:
            raise RuntimeError("fetch failed")
        return () if self._event is None else (self._event,)


def _provider_capability(provider_id: str = "official-macro") -> ProviderCapability:
    return ProviderCapability(
        provider_id,
        ("macro",),
        ("example.com",),
        "v1",
        "public",
        timedelta(days=1),
        official_source=True,
    )


def test_market_context_registry_collects_and_blocks_explicit_provider_paths() -> None:
    request = MarketContextRequest("snapshot", "BTCUSDT", NOW, categories=("macro",))
    event = MarketContextEvent.create(
        event_id="event-1",
        provider_id="official-macro",
        title="Macro calendar",
        scheduled_at=NOW + timedelta(hours=1),
        retrieved_at=NOW,
        impact="HIGH",
        category="macro",
        source_url="https://example.com/calendar",
    )
    capability = _provider_capability()
    registry = MarketContextRegistry(
        (
            MarketContextProviderStub(capability, event=event),
            MarketContextProviderStub(
                _provider_capability("degraded"),
                health_status=ProviderHealthStatus.DEGRADED,
                blockers=("PROVIDER_DEGRADED",),
            ),
            MarketContextProviderStub(
                _provider_capability("health-failed"),
                fail_health=True,
            ),
            MarketContextProviderStub(
                _provider_capability("identity-mismatch"),
                health_provider_id="wrong-id",
            ),
            MarketContextProviderStub(
                _provider_capability("fetch-failed"),
                fail_fetch=True,
            ),
        )
    )
    batch = registry.collect(
        request,
        (
            "official-macro",
            "degraded",
            "health-failed",
            "identity-mismatch",
            "fetch-failed",
            "missing",
        ),
    )
    assert batch.events == (event,)
    assert {
        "PROVIDER_DEGRADED",
        "MARKET_CONTEXT_HEALTH_FAILED:health-failed",
        "MARKET_CONTEXT_PROVIDER_IDENTITY_MISMATCH",
        "MARKET_CONTEXT_FETCH_FAILED:fetch-failed",
        "MARKET_CONTEXT_PROVIDER_UNKNOWN:missing",
    } <= set(batch.blockers)
    snapshot_payload = batch.as_news_snapshot()
    assert "event-1" in str(snapshot_payload["high_impact_events"])
    with pytest.raises(ValueError, match="unique"):
        registry.collect(request, ("official-macro", "official-macro"))
    with pytest.raises(ValueError, match="unique"):
        MarketContextRegistry(
            (
                MarketContextProviderStub(capability),
                MarketContextProviderStub(capability),
            )
        )


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            MarketContextEvent.create(
                event_id="provider-mismatch",
                provider_id="other",
                title="Macro",
                scheduled_at=NOW,
                retrieved_at=NOW,
                impact="HIGH",
                category="macro",
                source_url="https://example.com/a",
            ),
            "PROVIDER_MISMATCH",
        ),
        (
            MarketContextEvent.create(
                event_id="host-mismatch",
                provider_id="official-macro",
                title="Macro",
                scheduled_at=NOW,
                retrieved_at=NOW,
                impact="HIGH",
                category="macro",
                source_url="https://other.example/a",
            ),
            "SOURCE_NOT_ALLOWED",
        ),
        (
            MarketContextEvent.create(
                event_id="category-mismatch",
                provider_id="official-macro",
                title="Macro",
                scheduled_at=NOW,
                retrieved_at=NOW,
                impact="HIGH",
                category="earnings",
                source_url="https://example.com/a",
            ),
            "CATEGORY_NOT_ALLOWED",
        ),
        (
            MarketContextEvent.create(
                event_id="future-retrieval",
                provider_id="official-macro",
                title="Macro",
                scheduled_at=NOW,
                retrieved_at=NOW + timedelta(seconds=1),
                impact="HIGH",
                category="macro",
                source_url="https://example.com/a",
            ),
            "TIMESTAMP_INVALID",
        ),
    ],
)
def test_market_context_registry_rejects_invalid_provider_events(
    event: MarketContextEvent, expected: str
) -> None:
    request = MarketContextRequest("snapshot", "BTCUSDT", NOW, categories=("macro",))
    registry = MarketContextRegistry(
        (MarketContextProviderStub(_provider_capability(), event=event),)
    )
    batch = registry.collect(request, ("official-macro",))
    assert not batch.events
    assert any(expected in blocker for blocker in batch.blockers)


def test_market_context_registry_rejects_stale_and_tampered_events() -> None:
    request = MarketContextRequest("snapshot", "BTCUSDT", NOW, categories=("macro",))
    base = MarketContextEvent.create(
        event_id="event",
        provider_id="official-macro",
        title="Macro",
        scheduled_at=NOW,
        retrieved_at=NOW,
        impact="HIGH",
        category="macro",
        source_url="https://example.com/a",
    )
    cases = (
        replace(base, category="earnings", content_hash=base.content_hash),
        replace(base, retrieved_at=NOW - timedelta(days=2)),
        replace(base, content_hash="b" * 64),
    )
    expected = (
        "CATEGORY_NOT_ALLOWED",
        "EVENT_STALE",
        "CONTENT_HASH_INVALID",
    )
    for event, blocker in zip(cases, expected, strict=True):
        registry = MarketContextRegistry(
            (MarketContextProviderStub(_provider_capability(), event=event),)
        )
        batch = registry.collect(request, ("official-macro",))
        assert not batch.events
        assert any(blocker in item for item in batch.blockers)


def _capability(
    capability_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    required_data: tuple[str, ...] = ("ohlcv",),
    runtime_eligible: bool = True,
    expensive: bool = False,
    compatible_regimes: tuple[str, ...] = ("ALL",),
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id,
        "1",
        "coverage",
        dependencies,
        required_data,
        ("1h",),
        compatible_regimes,
        "cluster",
        expensive,
        runtime_eligible,
        CapabilityExecutionClass.DETERMINISTIC_THREAD_POOL,
        CapabilityActivationPolicy.ALWAYS_SCHEDULED,
    )


def test_preflight_plan_propagates_reasons_and_bundle_membership() -> None:
    registry = CapabilityRegistry(
        (
            _capability("base", required_data=("unknown",)),
            _capability("dependent", dependencies=("base",)),
            _capability("expensive", expensive=True),
            _capability("regime", compatible_regimes=("TREND",)),
        )
    )
    plan = build_capability_preflight_plan(
        registry, snapshot(), mode=CapabilityPreflightMode.ECONOMY
    )
    reasons = {item.capability_id: item.reason_codes for item in plan.decisions}
    assert reasons["base"] == ("REQUIRED_DATA_MISSING:unknown",)
    assert reasons["dependent"] == ("DEPENDENCY_NOT_SCHEDULED:base",)
    assert reasons["expensive"] == ("EXPENSIVE_CAPABILITY_DEFERRED",)
    assert reasons["regime"] == ("REGIME_UNAVAILABLE",)

    bundle_registry = CapabilityBundleRegistry(
        (
            CapabilityBundleDefinition("bundle-a", ("base", "dependent")),
            CapabilityBundleDefinition("bundle-b", ("expensive", "regime")),
        ),
        registry,
    )
    bundle_plan = build_capability_bundle_preflight_plan(plan, bundle_registry)
    assert bundle_plan.skipped_bundle_ids == ("bundle-a", "bundle-b")
    with pytest.raises(ValueError, match="complete capability registry"):
        build_capability_bundle_preflight_plan(
            CapabilityPreflightPlan(
                CapabilityPreflightMode.STANDARD,
                (CapabilityPreflightDecision("base", True),),
            ),
            bundle_registry,
        )
    with pytest.raises(ValueError, match="bundle identities"):
        CapabilityBundlePreflightPlan(
            (
                CapabilityBundlePreflightDecision("bundle", ("a",), ()),
                CapabilityBundlePreflightDecision("bundle", ("b",), ()),
            )
        )


def test_preflight_required_data_branches_accept_explicit_snapshot_fields() -> None:
    rich_snapshot = replace(
        snapshot(),
        order_book_summary={"bid_depth": "present"},
        market_metadata={
            "benchmark_data": {"BTC": "present"},
            "market_regime": "TREND",
        },
        news_snapshot={"events": ()},
        sentiment_snapshot={"score": 0},
        derivatives_snapshot={"funding": 0},
        onchain_snapshot={"flows": ()},
    )
    registry = CapabilityRegistry(
        (
            _capability(
                "all-data",
                required_data=(
                    "ohlcv",
                    "order_book",
                    "benchmark_data",
                    "news_snapshot",
                    "sentiment_snapshot",
                    "derivatives_snapshot",
                    "onchain_snapshot",
                    "market_snapshot",
                ),
                compatible_regimes=("TREND",),
            ),
        )
    )
    plan = build_capability_preflight_plan(
        registry, rich_snapshot, mode=CapabilityPreflightMode.STANDARD
    )
    assert plan.scheduled_ids == ("all-data",)


def test_preflight_reports_runtime_timeframe_and_regime_blockers() -> None:
    registry = CapabilityRegistry(
        (
            _capability("runtime", runtime_eligible=False),
            replace(_capability("timeframe"), timeframes=("4h",)),
            _capability("regime", compatible_regimes=("RANGE",)),
        )
    )
    plan = build_capability_preflight_plan(
        registry,
        replace(snapshot(), market_metadata={"market_regime": "TREND"}),
        mode=CapabilityPreflightMode.STANDARD,
    )
    reasons = {item.capability_id: item.reason_codes for item in plan.decisions}
    assert reasons["runtime"] == ("RUNTIME_NOT_ELIGIBLE",)
    assert reasons["timeframe"] == ("TIMEFRAME_NOT_APPLICABLE",)
    assert reasons["regime"] == ("REGIME_NOT_COMPATIBLE",)

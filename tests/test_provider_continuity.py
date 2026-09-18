"""Runtime/provider continuity contracts for stream, recovery, and fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from ai4binance.exchange import (
    KlineIngestResult,
    PortfolioBucketPersistenceEvidence,
    ProviderFixtureEvaluation,
    ProviderFreshnessContract,
    PublicKlineIngestor,
    RuntimeProviderContinuityAssessment,
    RuntimeProviderContinuityInput,
    assess_connector_readiness,
    assess_runtime_provider_continuity,
)
from ai4binance.exchange.readiness import ConnectorReadinessAssessment
from ai4binance.execution import recover_paper_orders
from ai4binance.portfolio import (
    InventoryBuckets,
    PortfolioBucketStateStore,
)
from ai4binance.portfolio.reconciliation import OpenOrderView, ReconciliationReport
from tests.test_connector_stream_readiness import ready_input
from tests.test_paper_recovery_risk_flow import order_journal

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def live_ingest() -> KlineIngestResult:
    ingestor = PublicKlineIngestor("hotusdt", "1h")
    ingestor.bootstrap(snapshot_sequence=100, connected_at=NOW)
    return ingestor.ingest(
        json.dumps(
            {
                "e": "kline",
                "E": int((NOW + timedelta(seconds=1)).timestamp() * 1000),
                "s": "HOTUSDT",
                "k": {
                    "t": int((NOW - timedelta(hours=1)).timestamp() * 1000),
                    "T": int((NOW - timedelta(milliseconds=1)).timestamp() * 1000),
                    "s": "HOTUSDT",
                    "i": "1h",
                    "f": 101,
                    "L": 101,
                    "o": "100",
                    "c": "101",
                    "h": "102",
                    "l": "99",
                    "v": "123",
                    "n": 1,
                    "x": True,
                },
            }
        )
    )


def persisted_bucket_state(
    tmp_path: Path,
) -> PortfolioBucketPersistenceEvidence:
    store = PortfolioBucketStateStore(tmp_path / "portfolio-bucket-state.json")
    return store.save(
        bucket_state_id="portfolio-core",
        observed_at=NOW,
        buckets=InventoryBuckets(
            core_units=Decimal("10"),
            strategic_units=Decimal("2"),
            tactical_units=Decimal("1"),
            cash_quote=Decimal("100"),
            reserved_cash_quote=Decimal("10"),
            pending_rebuy_cash_quote=Decimal("5"),
            last_stage=2,
            last_side="BUY",
            last_stage_clock=42,
        ),
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"bucket_state_id": " "}, "identity is required"),
        ({"observed_at": datetime(2026, 8, 31, 12)}, "timezone-aware"),
        ({"path": " "}, "path is required"),
        ({"persisted": True, "blockers": ("WRITE_FAILED",)}, "cannot contain"),
        ({"persisted": False, "blockers": ()}, "must declare blockers"),
        ({"snapshot_hash": "x" * 64}, "lowercase SHA-256"),
        ({"execution_allowed": True}, "cannot authorize execution"),
        ({"live_eligibility_status": "LIVE_READY"}, "cannot authorize execution"),
    ],
)
def test_portfolio_bucket_persistence_evidence_rejects_invalid_states(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "bucket_state_id": "portfolio-core",
        "observed_at": NOW,
        "path": Path("portfolio-bucket-state.json"),
        "persisted": True,
        "snapshot_hash": "a" * 64,
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        PortfolioBucketPersistenceEvidence(**values)  # type: ignore[arg-type]


def test_portfolio_bucket_store_and_hash_reject_invalid_inputs(
    tmp_path: Path,
) -> None:
    from ai4binance.portfolio.bucket_state import snapshot_hash

    buckets = InventoryBuckets(
        core_units=Decimal("10"),
        strategic_units=Decimal("2"),
        tactical_units=Decimal("1"),
        cash_quote=Decimal("100"),
        reserved_cash_quote=Decimal("10"),
        pending_rebuy_cash_quote=Decimal("5"),
        last_stage=2,
        last_side="BUY",
        last_stage_clock=42,
    )
    store = PortfolioBucketStateStore(tmp_path / "portfolio-bucket-state.json")

    with pytest.raises(ValueError, match="timezone-aware"):
        store.save(
            bucket_state_id="portfolio-core",
            observed_at=datetime(2026, 8, 31, 12),
            buckets=buckets,
        )
    with pytest.raises(ValueError, match="identity is required"):
        store.save(bucket_state_id=" ", observed_at=NOW, buckets=buckets)
    with pytest.raises(ValueError, match="identity is required"):
        snapshot_hash(" ", NOW, buckets)
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshot_hash("portfolio-core", datetime(2026, 8, 31, 12), buckets)

    evidence = store.save(
        bucket_state_id=" portfolio-core ", observed_at=NOW, buckets=buckets
    )
    assert evidence.snapshot_hash == snapshot_hash("portfolio-core", NOW, buckets)


def test_portfolio_bucket_store_detects_failed_read_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai4binance.portfolio.bucket_state as bucket_state

    buckets = InventoryBuckets(
        core_units=Decimal("1"),
        strategic_units=Decimal("0"),
        tactical_units=Decimal("0"),
        cash_quote=Decimal("10"),
        reserved_cash_quote=Decimal("0"),
        pending_rebuy_cash_quote=Decimal("0"),
    )
    monkeypatch.setattr(json, "loads", lambda _value: {})

    with pytest.raises(ValueError, match="persistence verification failed"):
        bucket_state.PortfolioBucketStateStore(tmp_path / "state.json").save(
            bucket_state_id="portfolio-core",
            observed_at=NOW,
            buckets=buckets,
        )


def test_provider_freshness_contract_enforces_age_and_latency() -> None:
    fresh = ProviderFreshnessContract(
        provider_id="binance-spot-public",
        observed_at=NOW,
        source_published_at=NOW - timedelta(seconds=10),
        maximum_age=timedelta(seconds=30),
        measured_latency_ms=250.0,
        maximum_latency_ms=500.0,
    )

    assert fresh.age_ok is True
    assert fresh.latency_ok is True
    assert fresh.blockers == ()

    stale = ProviderFreshnessContract(
        provider_id="binance-spot-public",
        observed_at=NOW,
        source_published_at=NOW - timedelta(minutes=1),
        maximum_age=timedelta(seconds=30),
        measured_latency_ms=750.0,
        maximum_latency_ms=500.0,
    )
    assert stale.blockers == (
        "PROVIDER_DATA_STALE",
        "PROVIDER_LATENCY_BUDGET_EXCEEDED",
    )

    with pytest.raises(ValueError, match="bind measurement and budget"):
        ProviderFreshnessContract(
            provider_id="binance-spot-public",
            observed_at=NOW,
            source_published_at=NOW,
            maximum_age=timedelta(seconds=30),
            measured_latency_ms=10.0,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"provider_id": " "}, "identity is required"),
        ({"observed_at": datetime(2026, 8, 31, 12)}, "timezone-aware"),
        ({"maximum_age": timedelta(0)}, "maximum_age must be positive"),
        ({"source_published_at": NOW + timedelta(seconds=1)}, "chronology"),
        ({"measured_latency_ms": -1.0, "maximum_latency_ms": 1.0}, "negative"),
        ({"measured_latency_ms": 1.0, "maximum_latency_ms": 0.0}, "maximum latency"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ],
)
def test_provider_freshness_contract_rejects_invalid_evidence(
    overrides: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "provider_id": "binance-spot-public",
        "observed_at": NOW,
        "source_published_at": NOW,
        "maximum_age": timedelta(seconds=30),
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        ProviderFreshnessContract(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"fixture_id": " "}, "identity is required"),
        ({"observed_at": datetime(2026, 8, 31, 12)}, "timezone-aware"),
        ({"passed": True, "blockers": ("FAILED",)}, "cannot contain blockers"),
        ({"passed": False, "blockers": ()}, "must declare blockers"),
        ({"execution_allowed": True}, "cannot authorize execution"),
    ],
)
def test_provider_fixture_rejects_incomplete_or_authorizing_evidence(
    overrides: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "fixture_id": "fixture-1",
        "provider_id": "binance-spot-public",
        "observed_at": NOW,
        "passed": True,
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        ProviderFixtureEvaluation(**values)  # type: ignore[arg-type]


def test_runtime_provider_continuity_rejects_incomplete_or_nonpersistent_inputs() -> (
    None
):
    freshness = ProviderFreshnessContract(
        provider_id="binance-spot-public",
        observed_at=NOW,
        source_published_at=NOW,
        maximum_age=timedelta(seconds=30),
    )
    base: dict[str, object] = {
        "readiness": SimpleNamespace(blockers=()),
        "freshness": freshness,
        "latest_ingest": SimpleNamespace(
            blockers=(),
            transition=SimpleNamespace(accepted=False, blockers=("SEQUENCE_GAP",)),
        ),
        "paper_recovery": SimpleNamespace(blockers=(), recovery_complete=False),
        "open_order_reconciliation": None,
        "portfolio_bucket_persistence": SimpleNamespace(blockers=(), persisted=False),
        "provider_fixture": None,
    }
    assessment = assess_runtime_provider_continuity(
        RuntimeProviderContinuityInput(**base)  # type: ignore[arg-type]
    )
    assert assessment.blockers == (
        "SEQUENCE_GAP",
        "PAPER_RESTART_RECOVERY_INCOMPLETE",
        "OPEN_ORDER_RECONCILIATION_NOT_EVALUATED",
        "PORTFOLIO_BUCKET_STATE_NOT_PERSISTED",
        "PROVIDER_FIXTURE_EVALUATION_MISSING",
    )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        RuntimeProviderContinuityAssessment(
            continuity_ready=False,
            blockers=("EVIDENCE_MISSING",),
            execution_allowed=True,
        )


def test_runtime_continuity_records_missing_recovery_without_false_bucket_gap() -> None:
    assessment = assess_runtime_provider_continuity(
        RuntimeProviderContinuityInput(
            readiness=cast(ConnectorReadinessAssessment, SimpleNamespace(blockers=())),
            freshness=ProviderFreshnessContract(
                provider_id="binance-spot-public",
                observed_at=NOW,
                source_published_at=NOW,
                maximum_age=timedelta(seconds=30),
            ),
            paper_recovery=None,
            portfolio_bucket_persisted=True,
        )
    )
    assert "PAPER_RESTART_RECOVERY_NOT_EVALUATED" in assessment.blockers
    assert "PORTFOLIO_BUCKET_STATE_NOT_PERSISTED" not in assessment.blockers


def test_runtime_provider_continuity_passes_only_when_all_evidence_is_bound(
    tmp_path: Path,
) -> None:
    journal = order_journal(tmp_path / "paper-1.jsonl")
    bucket_state = persisted_bucket_state(tmp_path)
    report = assess_runtime_provider_continuity(
        RuntimeProviderContinuityInput(
            readiness=assess_connector_readiness(
                ready_input(
                    private_state_required=True,
                    wallet_known=True,
                    open_orders_reconciled=True,
                )
            ),
            freshness=ProviderFreshnessContract(
                provider_id="binance-spot-public",
                observed_at=NOW,
                source_published_at=NOW - timedelta(seconds=2),
                maximum_age=timedelta(seconds=30),
                measured_latency_ms=125.0,
                maximum_latency_ms=500.0,
            ),
            latest_ingest=live_ingest(),
            paper_recovery=recover_paper_orders(
                (journal,),
                exchange_open_orders=(
                    OpenOrderView("paper-1", "HOTUSDT", Decimal("2")),
                ),
            ),
            open_order_reconciliation=ReconciliationReport(1, 1, (), (), (), ()),
            portfolio_bucket_persistence=bucket_state,
            provider_fixture=ProviderFixtureEvaluation(
                fixture_id="binance-spot-kline-fixture",
                provider_id="binance-spot-public",
                observed_at=NOW,
                passed=True,
            ),
        )
    )

    assert report.continuity_ready is True
    assert report.blockers == ()
    assert bucket_state.persisted is True
    assert len(bucket_state.snapshot_hash) == 64
    assert report.execution_allowed is False
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_runtime_provider_continuity_accumulates_missing_and_failed_controls(
    tmp_path: Path,
) -> None:
    journal = order_journal(tmp_path / "paper-1.jsonl")
    degraded = assess_runtime_provider_continuity(
        RuntimeProviderContinuityInput(
            readiness=assess_connector_readiness(
                ready_input(
                    stream_connected=False,
                    sequence_contiguous=False,
                    rest_backfill_complete=False,
                    private_state_required=True,
                )
            ),
            freshness=ProviderFreshnessContract(
                provider_id="binance-spot-public",
                observed_at=NOW,
                source_published_at=NOW - timedelta(minutes=2),
                maximum_age=timedelta(seconds=30),
            ),
            latest_ingest=None,
            paper_recovery=recover_paper_orders((journal,)),
            open_order_reconciliation=ReconciliationReport(
                1,
                1,
                (),
                ("SPOT:unknown",),
                (),
                ("UNKNOWN_EXCHANGE_OPEN_ORDER",),
            ),
            portfolio_bucket_persisted=False,
            provider_fixture=ProviderFixtureEvaluation(
                fixture_id="binance-spot-kline-fixture",
                provider_id="binance-spot-public",
                observed_at=NOW,
                passed=False,
                blockers=("PROVIDER_FIXTURE_SEQUENCE_MISMATCH",),
            ),
        )
    )

    assert degraded.continuity_ready is False
    assert degraded.blockers == (
        "PUBLIC_STREAM_DISCONNECTED",
        "STREAM_SEQUENCE_GAP",
        "REST_BACKFILL_INCOMPLETE",
        "WALLET_STATE_UNKNOWN",
        "OPEN_ORDERS_NOT_RECONCILED",
        "PROVIDER_DATA_STALE",
        "PUBLIC_STREAM_EVIDENCE_NOT_AVAILABLE",
        "EXCHANGE_OPEN_ORDER_SNAPSHOT_NOT_SUPPLIED",
        "UNKNOWN_EXCHANGE_OPEN_ORDER",
        "PORTFOLIO_BUCKET_STATE_NOT_PERSISTED",
        "PROVIDER_FIXTURE_SEQUENCE_MISMATCH",
    )

    with pytest.raises(ValueError, match="readiness and blockers disagree"):
        RuntimeProviderContinuityAssessment(True, ("BLOCKED",))

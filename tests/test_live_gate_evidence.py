"""Independent live-gate validation evidence remains exact and fail-closed."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.validation.live_gate_evidence import (
    LiveGateEvidenceKind,
    LiveGateEvidenceRecord,
    LiveGateEvidenceRegistry,
    LiveGateEvidenceSourceKind,
    LiveGateEvidenceVerificationStatus,
)
from ai4binance.validation.promotion_evidence import PromotionEvidenceQuery

NOW = datetime(2026, 9, 9, 7, 30, tzinfo=UTC)
QUERY = PromotionEvidenceQuery(
    strategy_id="trend-continuation",
    strategy_version="1.0.0",
    strategy_sha256="1" * 64,
    symbol="HOTUSDT",
    market_type="SPOT",
    timeframe="15m",
    parameter_set_sha256="2" * 64,
    dataset_sha256="3" * 64,
    code_revision="4" * 40,
    as_of=NOW,
)


def evidence(
    kind: LiveGateEvidenceKind,
    *,
    evidence_id: str | None = None,
    observed_at: datetime = NOW,
) -> LiveGateEvidenceRecord:
    return LiveGateEvidenceRecord(
        evidence_id=evidence_id or f"evidence-{kind.value.lower()}",
        evidence_kind=kind,
        source_kind=LiveGateEvidenceSourceKind.GOVERNED_ARTIFACT,
        source_ref=f"governed://validation/{kind.value.lower()}",
        artifact_sha256={
            LiveGateEvidenceKind.BACKTEST: "a" * 64,
            LiveGateEvidenceKind.WALK_FORWARD: "b" * 64,
            LiveGateEvidenceKind.TUNING: "c" * 64,
            LiveGateEvidenceKind.OOS: "d" * 64,
        }[kind],
        observed_at=observed_at,
        verification_status=LiveGateEvidenceVerificationStatus.VERIFIED,
        strategy_id=QUERY.strategy_id,
        strategy_version=QUERY.strategy_version,
        strategy_sha256=QUERY.strategy_sha256,
        symbol=QUERY.symbol,
        market_type=QUERY.market_type,
        timeframe=QUERY.timeframe,
        parameter_set_sha256=QUERY.parameter_set_sha256,
        dataset_sha256=QUERY.dataset_sha256,
        code_revision=QUERY.code_revision,
    )


def complete_records() -> tuple[LiveGateEvidenceRecord, ...]:
    return tuple(evidence(kind) for kind in LiveGateEvidenceKind)


def expected_hash(registry: LiveGateEvidenceRegistry) -> str:
    value = registry.canonical_bundle_sha256(query=QUERY)
    assert value is not None
    return value


def test_complete_exact_bundle_resolves_four_independent_gates() -> None:
    registry = LiveGateEvidenceRegistry(complete_records())
    bundle_sha256 = expected_hash(registry)

    resolution = registry.resolve(
        query=QUERY,
        expected_bundle_sha256=bundle_sha256,
    )

    assert resolution.backtest_approved is True
    assert resolution.walk_forward_approved is True
    assert resolution.tuning_report_approved is True
    assert resolution.oos_approved is True
    assert resolution.validation_bundle_sha256 == bundle_sha256
    assert tuple(item[0] for item in resolution.evidence_refs) == tuple(
        kind.value for kind in LiveGateEvidenceKind
    )
    assert resolution.blockers == ()
    assert resolution.promotion_status is ValidationStatus.RESEARCH_ONLY
    assert resolution.execution_allowed is False
    assert resolution.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_record_order_does_not_change_canonical_bundle_hash() -> None:
    records = complete_records()

    assert expected_hash(LiveGateEvidenceRegistry(records)) == expected_hash(
        LiveGateEvidenceRegistry(tuple(reversed(records)))
    )


def test_one_evidence_class_cannot_satisfy_the_other_gates() -> None:
    registry = LiveGateEvidenceRegistry((evidence(LiveGateEvidenceKind.BACKTEST),))

    resolution = registry.resolve(
        query=QUERY,
        expected_bundle_sha256="f" * 64,
    )

    assert resolution.backtest_approved is False
    assert resolution.walk_forward_approved is False
    assert resolution.tuning_report_approved is False
    assert resolution.oos_approved is False
    assert resolution.blockers == (
        "LIVE_GATE_EVIDENCE_WALK_FORWARD_MISSING",
        "LIVE_GATE_EVIDENCE_TUNING_MISSING",
        "LIVE_GATE_EVIDENCE_OOS_MISSING",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"strategy_id": "mean-reversion"},
        {"strategy_version": "2.0.0"},
        {"strategy_sha256": "5" * 64},
        {"symbol": "BTCUSDT"},
        {"market_type": "USD_M_FUTURES"},
        {"timeframe": "1h"},
        {"parameter_set_sha256": "6" * 64},
        {"dataset_sha256": "7" * 64},
        {"code_revision": "8" * 40},
    ],
)
def test_cross_subject_oos_evidence_is_missing_for_exact_query(
    change: dict[str, object],
) -> None:
    records = list(complete_records())
    records[-1] = replace(records[-1], **change)  # type: ignore[arg-type]
    registry = LiveGateEvidenceRegistry(tuple(records))

    resolution = registry.resolve(query=QUERY, expected_bundle_sha256="f" * 64)

    assert resolution.oos_approved is False
    assert "LIVE_GATE_EVIDENCE_OOS_MISSING" in resolution.blockers


def test_bundle_hash_mismatch_blocks_every_validation_gate() -> None:
    registry = LiveGateEvidenceRegistry(complete_records())

    resolution = registry.resolve(query=QUERY, expected_bundle_sha256="f" * 64)

    assert resolution.validation_bundle_sha256 == expected_hash(registry)
    assert resolution.backtest_approved is False
    assert resolution.walk_forward_approved is False
    assert resolution.tuning_report_approved is False
    assert resolution.oos_approved is False
    assert resolution.blockers == ("LIVE_GATE_EVIDENCE_BUNDLE_HASH_MISMATCH",)


def test_malformed_expected_bundle_hash_fails_closed() -> None:
    registry = LiveGateEvidenceRegistry(complete_records())

    resolution = registry.resolve(query=QUERY, expected_bundle_sha256="not-a-hash")

    assert resolution.backtest_approved is False
    assert resolution.blockers == ("LIVE_GATE_EVIDENCE_BUNDLE_HASH_INVALID",)


@pytest.mark.parametrize(
    ("changed_oos", "max_age", "expected_blocker"),
    [
        (
            replace(
                evidence(LiveGateEvidenceKind.OOS),
                observed_at=NOW + timedelta(seconds=1),
            ),
            timedelta(days=90),
            "LIVE_GATE_EVIDENCE_OOS_FUTURE_DATED",
        ),
        (
            replace(
                evidence(LiveGateEvidenceKind.OOS),
                observed_at=NOW - timedelta(days=2),
            ),
            timedelta(days=1),
            "LIVE_GATE_EVIDENCE_OOS_STALE",
        ),
        (
            replace(
                evidence(
                    LiveGateEvidenceKind.OOS,
                    observed_at=NOW - timedelta(hours=2),
                ),
                expires_at=NOW - timedelta(hours=1),
            ),
            timedelta(days=90),
            "LIVE_GATE_EVIDENCE_OOS_EXPIRED",
        ),
        (
            replace(
                evidence(
                    LiveGateEvidenceKind.OOS,
                    observed_at=NOW - timedelta(hours=2),
                ),
                revoked_at=NOW - timedelta(hours=1),
            ),
            timedelta(days=90),
            "LIVE_GATE_EVIDENCE_OOS_REVOKED",
        ),
        (
            replace(
                evidence(LiveGateEvidenceKind.OOS),
                verification_status=(LiveGateEvidenceVerificationStatus.UNVERIFIED),
                blockers=("OOS_THRESHOLD_FAILED",),
            ),
            timedelta(days=90),
            "LIVE_GATE_EVIDENCE_OOS_NOT_VERIFIED",
        ),
        (
            replace(
                evidence(LiveGateEvidenceKind.OOS),
                source_kind=LiveGateEvidenceSourceKind.VALIDATION_ARTIFACT,
            ),
            timedelta(days=90),
            "LIVE_GATE_EVIDENCE_OOS_SOURCE_NOT_GOVERNED",
        ),
    ],
)
def test_non_current_or_untrusted_oos_blocks_the_whole_bound_bundle(
    changed_oos: LiveGateEvidenceRecord,
    max_age: timedelta,
    expected_blocker: str,
) -> None:
    records = (*complete_records()[:-1], changed_oos)
    registry = LiveGateEvidenceRegistry(records, max_evidence_age=max_age)

    resolution = registry.resolve(query=QUERY, expected_bundle_sha256="f" * 64)

    assert resolution.backtest_approved is False
    assert resolution.oos_approved is False
    assert expected_blocker in resolution.blockers
    assert registry.canonical_bundle_sha256(query=QUERY) is None


def test_ambiguous_latest_record_blocks_without_fallback() -> None:
    records = (
        *complete_records(),
        evidence(LiveGateEvidenceKind.OOS, evidence_id="evidence-oos-duplicate"),
    )
    registry = LiveGateEvidenceRegistry(records)

    resolution = registry.resolve(query=QUERY, expected_bundle_sha256="f" * 64)

    assert resolution.blockers == ("LIVE_GATE_EVIDENCE_OOS_AMBIGUOUS",)


def test_newer_unverified_record_blocks_without_older_verified_fallback() -> None:
    newer = replace(
        evidence(
            LiveGateEvidenceKind.OOS,
            evidence_id="evidence-oos-newer",
            observed_at=NOW + timedelta(minutes=1),
        ),
        verification_status=LiveGateEvidenceVerificationStatus.UNVERIFIED,
        blockers=("OOS_REVIEW_REQUIRED",),
    )
    query = replace(QUERY, as_of=NOW + timedelta(minutes=2))
    registry = LiveGateEvidenceRegistry((*complete_records(), newer))

    resolution = registry.resolve(query=query, expected_bundle_sha256="f" * 64)

    assert resolution.blockers == ("LIVE_GATE_EVIDENCE_OOS_NOT_VERIFIED",)


def test_duplicate_evidence_identity_is_rejected() -> None:
    duplicate = replace(
        evidence(LiveGateEvidenceKind.OOS),
        evidence_id="evidence-backtest",
    )
    records = (*complete_records()[:-1], duplicate)

    with pytest.raises(ValueError, match="identity must be unique"):
        LiveGateEvidenceRegistry(records)


@pytest.mark.parametrize(
    "change",
    [
        {"artifact_sha256": "bad"},
        {"observed_at": datetime(2026, 9, 9, 7, 30)},
        {
            "verification_status": LiveGateEvidenceVerificationStatus.VERIFIED,
            "blockers": ("CONTRADICTION",),
        },
        {
            "verification_status": LiveGateEvidenceVerificationStatus.UNVERIFIED,
            "blockers": (),
        },
        {"promotion_status": ValidationStatus.STAGED_CANDIDATE},
        {"execution_allowed": True},
        {"live_eligibility_status": "LIVE_ELIGIBLE"},
    ],
)
def test_malformed_or_authority_broadening_record_is_rejected(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="live gate evidence"):
        replace(
            evidence(LiveGateEvidenceKind.BACKTEST),
            **change,  # type: ignore[arg-type]
        )

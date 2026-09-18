"""Promotion evidence registry and ledger stay deterministic and bounded."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceLedger,
    PromotionEvidenceQuery,
    PromotionEvidenceRecord,
    PromotionEvidenceRegistry,
    PromotionEvidenceSourceKind,
)
from ai4binance.validation.summary import ValidationSummaryReader

NOW = datetime(2026, 7, 28, tzinfo=UTC)
STRATEGY_SHA256 = "1" * 64
PARAMETER_SET_SHA256 = "2" * 64
DATASET_SHA256 = "3" * 64
CODE_REVISION = "4" * 40

QUERY = PromotionEvidenceQuery(
    strategy_id="trend_continuation",
    strategy_version="1.0.0",
    strategy_sha256=STRATEGY_SHA256,
    symbol="HOTUSDT",
    market_type="SPOT",
    timeframe="15m",
    parameter_set_sha256=PARAMETER_SET_SHA256,
    dataset_sha256=DATASET_SHA256,
    code_revision=CODE_REVISION,
    as_of=NOW,
)


def exact_record(
    *,
    evidence_id: str = "ledger-1",
    observed_at: datetime = NOW,
    promotion_status: ValidationStatus = ValidationStatus.STAGED_CANDIDATE,
    blockers: tuple[str, ...] = (),
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> PromotionEvidenceRecord:
    return PromotionEvidenceRecord(
        evidence_id=evidence_id,
        symbol=QUERY.symbol,
        source_kind=PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
        source_ref=f"ledger:{evidence_id}",
        observed_at=observed_at,
        promotion_status=promotion_status,
        timeframe=QUERY.timeframe,
        blockers=blockers,
        strategy_id=QUERY.strategy_id,
        strategy_version=QUERY.strategy_version,
        strategy_sha256=QUERY.strategy_sha256,
        market_type=QUERY.market_type,
        parameter_set_sha256=QUERY.parameter_set_sha256,
        dataset_sha256=QUERY.dataset_sha256,
        code_revision=QUERY.code_revision,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


def write_run_card(root: Path, *, symbol: str = "HOTUSDT") -> None:
    path = root / symbol / "15m" / "trend_continuation.run-card.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "artifact_sha256": [["artifact.jsonl", "abc"]],
                "blockers": [],
                "created_at": "2026-07-28T00:00:00+00:00",
                "hypothesis_id": "hyp:trend_continuation:15m",
                "metrics": [["net_return", 1.0]],
                "promotion_status": "RESEARCH_ONLY",
                "run_id": "run:research",
                "symbol": symbol,
                "timeframe": "15m",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_promotion_registry_merges_summary_and_ledger_sources(tmp_path: Path) -> None:
    validation_root = tmp_path / "validation"
    write_run_card(validation_root)
    summary = ValidationSummaryReader(validation_root).summarize("HOTUSDT")
    registry = PromotionEvidenceRegistry.from_validation_summary(summary)

    assert registry.resolve(query=QUERY) is ValidationStatus.RESEARCH_ONLY
    assert registry.has_promotion_evidence(query=QUERY) is False

    registry = registry.with_record(exact_record())

    assert registry.resolve(query=QUERY) is ValidationStatus.STAGED_CANDIDATE
    assert registry.has_promotion_evidence(query=QUERY) is True


def test_promotion_ledger_persists_verified_records(tmp_path: Path) -> None:
    ledger = PromotionEvidenceLedger(tmp_path / "promotion-ledger.jsonl")
    record = exact_record(
        promotion_status=ValidationStatus.PAPER_APPROVED,
    )

    ledger.append(record)

    persisted = ledger.records()
    assert len(persisted) == 1
    assert persisted[0].symbol == "HOTUSDT"
    assert persisted[0].promotion_status is ValidationStatus.PAPER_APPROVED
    assert persisted[0].exact_subject_key == QUERY.subject_key
    assert ledger.as_registry().resolve(query=QUERY) is ValidationStatus.PAPER_APPROVED


def test_promotion_registry_uses_latest_exact_record_not_highest_status() -> None:
    registry = PromotionEvidenceRegistry.from_records(
        (
            exact_record(promotion_status=ValidationStatus.LIVE_ELIGIBLE),
            exact_record(
                evidence_id="ledger-2",
                observed_at=NOW + timedelta(hours=1),
                promotion_status=ValidationStatus.RESEARCH_ONLY,
            ),
        )
    )

    assert (
        registry.resolve(query=replace(QUERY, as_of=NOW + timedelta(hours=2)))
        is ValidationStatus.RESEARCH_ONLY
    )


def test_promotion_registry_rejects_ambiguous_latest_records() -> None:
    registry = PromotionEvidenceRegistry.from_records(
        (
            exact_record(promotion_status=ValidationStatus.LIVE_ELIGIBLE),
            exact_record(
                evidence_id="ledger-2",
                promotion_status=ValidationStatus.LIVE_ELIGIBLE,
            ),
        )
    )

    assert registry.resolve(query=QUERY) is ValidationStatus.RESEARCH_ONLY


@pytest.mark.parametrize(
    "record",
    [
        exact_record(
            promotion_status=ValidationStatus.LIVE_ELIGIBLE,
            blockers=("EVIDENCE_REJECTED",),
        ),
        exact_record(
            promotion_status=ValidationStatus.LIVE_ELIGIBLE,
            expires_at=NOW + timedelta(minutes=30),
        ),
        exact_record(
            promotion_status=ValidationStatus.LIVE_ELIGIBLE,
            revoked_at=NOW + timedelta(minutes=30),
        ),
    ],
)
def test_promotion_registry_rejects_blocked_expired_or_revoked_record(
    record: PromotionEvidenceRecord,
) -> None:
    query = replace(QUERY, as_of=NOW + timedelta(hours=1))

    assert (
        PromotionEvidenceRegistry.from_records((record,)).resolve(query=query)
        is ValidationStatus.RESEARCH_ONLY
    )


def test_newer_revocation_prevents_fallback_to_older_live_status() -> None:
    revoked_at = NOW + timedelta(minutes=30)
    registry = PromotionEvidenceRegistry.from_records(
        (
            exact_record(promotion_status=ValidationStatus.LIVE_ELIGIBLE),
            exact_record(
                evidence_id="revocation-1",
                observed_at=revoked_at,
                promotion_status=ValidationStatus.LIVE_ELIGIBLE,
                revoked_at=revoked_at,
            ),
        )
    )

    assert (
        registry.resolve(query=replace(QUERY, as_of=NOW + timedelta(hours=1)))
        is ValidationStatus.RESEARCH_ONLY
    )


def test_promotion_registry_rejects_stale_or_future_record() -> None:
    stale_registry = PromotionEvidenceRegistry.from_records(
        (exact_record(promotion_status=ValidationStatus.LIVE_ELIGIBLE),),
        max_evidence_age=timedelta(minutes=30),
    )
    future_registry = PromotionEvidenceRegistry.from_records(
        (
            exact_record(
                observed_at=NOW + timedelta(minutes=6),
                promotion_status=ValidationStatus.LIVE_ELIGIBLE,
            ),
        )
    )

    assert (
        stale_registry.resolve(query=replace(QUERY, as_of=NOW + timedelta(hours=1)))
        is ValidationStatus.RESEARCH_ONLY
    )
    assert future_registry.resolve(query=QUERY) is ValidationStatus.RESEARCH_ONLY


@pytest.mark.parametrize(
    "query",
    [
        replace(QUERY, strategy_id="different_strategy"),
        replace(QUERY, strategy_version="2.0.0"),
        replace(QUERY, strategy_sha256="5" * 64),
        replace(QUERY, symbol="BTCUSDT"),
        replace(QUERY, market_type="USD_M_FUTURES"),
        replace(QUERY, timeframe="1h"),
        replace(QUERY, parameter_set_sha256="6" * 64),
        replace(QUERY, dataset_sha256="7" * 64),
        replace(QUERY, code_revision="8" * 40),
    ],
)
def test_promotion_registry_rejects_cross_subject_evidence(
    query: PromotionEvidenceQuery,
) -> None:
    registry = PromotionEvidenceRegistry.from_records(
        (exact_record(promotion_status=ValidationStatus.LIVE_ELIGIBLE),)
    )

    assert registry.resolve(query=query) is ValidationStatus.RESEARCH_ONLY


def test_live_eligible_promotion_record_requires_complete_exact_identity() -> None:
    with pytest.raises(ValueError, match="must be exact-bound"):
        PromotionEvidenceRecord(
            evidence_id="legacy-live",
            symbol="HOTUSDT",
            source_kind=PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
            source_ref="legacy:live",
            observed_at=NOW,
            promotion_status=ValidationStatus.LIVE_ELIGIBLE,
            timeframe="15m",
        )

    with pytest.raises(ValueError, match="exact identity must be complete"):
        replace(exact_record(), dataset_sha256=None)

    with pytest.raises(ValueError, match="requires a governed artifact"):
        replace(
            exact_record(promotion_status=ValidationStatus.LIVE_ELIGIBLE),
            source_kind=PromotionEvidenceSourceKind.VALIDATION_LEDGER,
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: replace(exact_record(), evidence_id=" "), "identity"),
        (lambda: replace(exact_record(), timeframe=" "), "timeframe"),
        (
            lambda: replace(exact_record(), promotion_status=ValidationStatus.REJECTED),
            "status is invalid",
        ),
        (
            lambda: replace(exact_record(), expires_at=NOW - timedelta(minutes=1)),
            "expiry must follow",
        ),
        (
            lambda: replace(exact_record(), revoked_at=NOW - timedelta(minutes=1)),
            "revocation cannot predate",
        ),
        (
            lambda: replace(exact_record(), execution_allowed=True),
            "cannot grant execution",
        ),
    ],
)
def test_promotion_evidence_record_rejects_invalid_or_authorizing_shapes(
    factory: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: replace(QUERY, strategy_id=" "), "strategy_id"),
        (lambda: replace(QUERY, symbol="HOT/USDT"), "symbol identity"),
        (lambda: replace(QUERY, market_type="MARGIN"), "market type is invalid"),
        (lambda: replace(QUERY, strategy_sha256="bad"), "strategy_sha256"),
        (lambda: replace(QUERY, code_revision="bad"), "code revision"),
        (lambda: replace(QUERY, as_of=datetime(2026, 7, 28)), "timezone-aware"),
    ],
)
def test_promotion_query_rejects_invalid_exact_identity(
    factory: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


def test_promotion_ledger_skips_malformed_lines_and_duplicate_appends(
    tmp_path: Path,
) -> None:
    ledger = PromotionEvidenceLedger(tmp_path / "promotion-ledger.jsonl")
    record = exact_record()

    assert ledger.append_if_absent(record) is True
    assert ledger.append_if_absent(record) is False
    with (tmp_path / "promotion-ledger.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")
        stream.write("[]\n")
        stream.write('{"payload": []}\n')
        stream.write('{"payload": {"record": "invalid"}}\n')

    assert tuple(item.evidence_id for item in ledger.records()) == ("ledger-1",)

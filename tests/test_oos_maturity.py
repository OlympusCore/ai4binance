"""Maturity aggregation rejects unsupported, stale and conflicting evidence."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.validation.oos_maturity import (
    MAX_ARTIFACT_BYTES,
    REQUIRED_MEASUREMENTS,
    OOSArtifactReference,
    OOSMaturityEvidenceBundle,
    OOSMaturityGate,
    OOSValidationSubject,
    _matches,
    _validation_events,
    load_spot_oos_validation_specification,
    prepare_spot_oos_deployment,
)
from ai4binance.validation.promotion_evidence import (
    PromotionEvidenceQuery,
    PromotionEvidenceRecord,
    PromotionEvidenceRegistry,
    PromotionEvidenceSourceKind,
)
from ai4binance.validation.statistics import (
    MultipleTestingCorrection,
    assess_statistical_evidence,
)

NOW = datetime(2026, 9, 11, tzinfo=UTC)


def test_validation_events_accept_large_hash_bound_append_only_ledger(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "validation"
    artifact_root.mkdir()
    source = artifact_root / "trend_continuation.jsonl"
    prefix = json.dumps({"archived": "x" * MAX_ARTIFACT_BYTES}).encode() + b"\n"
    event_types = (
        "BACKTEST_RESULT",
        "WALK_FORWARD_REPORT",
        "TUNING_REPORT",
        "BACKTEST_ROBUSTNESS_REPORT",
    )
    current = b"".join(
        json.dumps(
            {
                "event_type": event_type,
                "payload": {"result": {"sequence": index}},
            }
        ).encode()
        + b"\n"
        for index, event_type in enumerate(event_types, start=1)
    )
    raw = prefix + current
    source.write_bytes(raw)

    events, reference = _validation_events(
        {"artifact_sha256": ((str(source), sha256(raw).hexdigest()),)},
        artifact_root,
    )

    assert set(events) == set(event_types)
    assert events["BACKTEST_RESULT"]["sequence"] == 1
    assert reference is not None
    assert reference.path == "trend_continuation.jsonl"
    assert reference.sha256 == sha256(raw).hexdigest()


def test_validation_events_reject_hash_mismatch(tmp_path: Path) -> None:
    artifact_root = tmp_path / "validation"
    artifact_root.mkdir()
    source = artifact_root / "trend_continuation.jsonl"
    source.write_text(
        json.dumps({"event_type": "BACKTEST_RESULT", "payload": {"result": {}}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="SPOT_OOS_SOURCE_HASH_INVALID"):
        _validation_events(
            {"artifact_sha256": ((str(source), "0" * 64),)},
            artifact_root,
        )


def test_active_spot_specification_prepares_exact_research_only_deployment(
    tmp_path: Path,
) -> None:
    specification_path = Path("config/research/virtual_market_acceptance.yaml")
    specification = load_spot_oos_validation_specification(specification_path)
    assert specification["status"] == "ACTIVE"
    assert specification["approval_status"] == "PENDING_INDEPENDENT_REVIEW"
    assert _matches(
        "2026-09-10T00:00:00+00:00",
        {"operator": "present", "value": True},
    )
    artifact_root = tmp_path / "validation"
    deployment_path = tmp_path / "config" / "runtime_validation_deployment.json"
    result = prepare_spot_oos_deployment(
        artifact_root=artifact_root,
        deployment_path=deployment_path,
        specification_path=specification_path,
        run_cards=(
            {
                "hypothesis_id": "hyp:trend_continuation:1h",
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "strategy_sha256": "a" * 64,
                "config_sha256": "b" * 64,
                "dataset_sha256": "c" * 64,
                "code_revision": "WORKTREE_UNVERIFIED",
                "fee_rate": 0.001,
                "slippage_rate": 0.0005,
                "promotion_status": "RESEARCH_ONLY",
                "execution_allowed": False,
            },
        ),
        observed_at=NOW,
    )
    assert result["status"] == "EVIDENCE_COLLECTION_IN_PROGRESS"
    assert result["subject_count"] == 1

    from ai4binance.agents.validation_gate import ValidationGate

    gate = ValidationGate.from_deployment(
        artifact_root=artifact_root,
        deployment_path=deployment_path,
        as_of=NOW,
    )
    assert not gate.evidence_load_blockers
    assert len(gate.expected_subjects) == 1
    maturity = OOSMaturityGate(artifact_root).evaluate(gate.evidence_bundles[0])
    assert maturity.status == "OOS_MATURITY_INCOMPLETE"
    assert "EVIDENCE_COLLECTION_IN_PROGRESS" in maturity.blockers
    assert "DATASET_EVIDENCE_MISSING" in maturity.blockers
    assert "PROMOTION_EVIDENCE_INCOMPLETE" in maturity.blockers
    assert "VALIDATION_SPECIFICATION_MISSING" not in maturity.blockers


def test_bonferroni_changes_the_interval_used_by_the_gate() -> None:
    single = assess_statistical_evidence(
        (0.01, 0.04, 0.03, 0.02),
        hypothesis_count=1,
        min_effective_sample_size=2,
        minimum_return=0.0,
        confidence_level=0.95,
        correction=MultipleTestingCorrection.BONFERRONI,
        confirmatory=True,
    )
    family = assess_statistical_evidence(
        (0.01, 0.04, 0.03, 0.02),
        hypothesis_count=1000,
        min_effective_sample_size=2,
        minimum_return=0.0,
        confidence_level=0.95,
        correction=MultipleTestingCorrection.BONFERRONI,
        confirmatory=True,
    )
    assert single.confidence_interval is not None
    assert family.confidence_interval is not None
    assert single.confidence_interval[0] > 0
    assert family.confidence_interval[0] < 0
    assert "OOS_RETURN_CONFIDENCE_INTERVAL_INSUFFICIENT" in family.blockers


def write(root: Path, name: str, payload: object) -> OOSArtifactReference:
    raw = json.dumps(payload, sort_keys=True).encode()
    (root / name).write_bytes(raw)
    return OOSArtifactReference(name, sha256(raw).hexdigest())


def reviewed(bundle: OOSMaturityEvidenceBundle) -> OOSMaturityEvidenceBundle:
    assert bundle.subject is not None
    q = bundle.subject.promotion
    record = PromotionEvidenceRecord(
        evidence_id="fixture-independent-review",
        symbol=q.symbol,
        source_kind=PromotionEvidenceSourceKind.GOVERNED_ARTIFACT,
        source_ref=f"oos-bundle:sha256:{bundle.bundle_sha256}",
        observed_at=NOW,
        promotion_status=ValidationStatus.STAGED_CANDIDATE,
        timeframe=q.timeframe,
        strategy_id=q.strategy_id,
        strategy_version=q.strategy_version,
        strategy_sha256=q.strategy_sha256,
        market_type=q.market_type,
        parameter_set_sha256=q.parameter_set_sha256,
        dataset_sha256=q.dataset_sha256,
        code_revision=q.code_revision,
    )
    return replace(bundle, promotion=PromotionEvidenceRegistry((record,)))


@pytest.fixture
def bundle(tmp_path: Path) -> OOSMaturityEvidenceBundle:
    query = PromotionEvidenceQuery(
        "trend",
        "1",
        "a" * 64,
        "BTCUSDT",
        "SPOT",
        "1d",
        "b" * 64,
        "c" * 64,
        "d" * 40,
        NOW,
    )
    values: dict[str, dict[str, object]] = {
        stage: dict.fromkeys(names, "PASS")
        for stage, names in REQUIRED_MEASUREMENTS.items()
    }
    values["backtest"]["cost_model_sha256"] = "e" * 64
    for measurements in values.values():
        measurements["blockers"] = []
        for name in (
            "expectancy",
            "net_return",
            "max_drawdown",
            "confidence_interval_lower",
            "profit_factor",
            "profitable_fold_ratio",
            "edge_concentration",
            "unknown_ratio",
            "observation_days",
        ):
            if name in measurements:
                measurements[name] = 0.1
        for name in (
            "trade_count",
            "fold_count",
            "regime_count",
            "hypothesis_count",
            "effective_sample_size",
            "missing_intervals",
            "duplicate_count",
            "purge",
            "embargo",
            "runtime_failures",
        ):
            if name in measurements:
                measurements[name] = 5
        for name in ("train_only_selection", "repository_clean", "replay_equal"):
            if name in measurements:
                measurements[name] = True
    values["paper_forward"].update(
        historical_oos_completed_at="2026-09-10T00:00:00+00:00",
        observation_started_at="2026-09-10T01:00:00+00:00",
        observation_ended_at="2026-09-10T02:00:00+00:00",
    )
    values["final_holdout"]["trade_count"] = 100
    values["final_holdout"]["expectancy"] = 1.2
    spec = write(
        tmp_path,
        "spec.json",
        {
            "status": "ACTIVE",
            "owner": "FixtureValidationOwner",
            "scope": list(query.subject_key[:6]),
            "requirements": {
                stage: {
                    name: {"operator": "eq", "value": value}
                    for name, value in measures.items()
                }
                for stage, measures in values.items()
            },
        },
    )
    subject = OOSValidationSubject(query, "trend", "f" * 64, "e" * 64, spec.sha256)
    refs = []
    for stage, measurements in values.items():
        source = write(
            tmp_path,
            f"{stage}-source.json",
            {"subject_key": subject.subject_key, **measurements},
        )
        payload: dict[str, Any] = {
            "subject_key": subject.subject_key,
            "stage": stage,
            "measurements": measurements,
            "observed_at": "2026-09-10T00:00:00+00:00",
            "expires_at": "2026-10-01T00:00:00+00:00",
            "blockers": [],
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            "source_artifacts": [{"path": source.path, "sha256": source.sha256}],
            "measurement_sources": {
                name: {"source_index": 0, "pointer": [name]} for name in measurements
            },
        }
        if stage == "final_holdout":
            partitions = dict(
                zip(
                    (
                        "development_start",
                        "development_end",
                        "walk_forward_start",
                        "walk_forward_end",
                        "holdout_start",
                        "holdout_end",
                    ),
                    (f"2025-0{i}-01T00:00:00+00:00" for i in range(1, 7)),
                    strict=True,
                )
            )
            history = write(
                tmp_path,
                "history.json",
                {
                    "dataset_sha256": query.dataset_sha256,
                    "partitions": partitions,
                    "accesses": [
                        {
                            "subject_key": subject.subject_key,
                            "accessed_at": "2026-09-10T00:00:00+00:00",
                        }
                    ],
                },
            )
            payload.update(
                partitions=partitions,
                candidate_frozen_at="2026-09-09T00:00:00+00:00",
                first_holdout_access_at="2026-09-10T00:00:00+00:00",
                holdout_history={"path": history.path, "sha256": history.sha256},
            )
        refs.append((stage, write(tmp_path, f"{stage}.json", payload)))
    return reviewed(OOSMaturityEvidenceBundle(subject, tuple(refs), spec))


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "wrong_hash",
        "stale",
        "tampered",
        "unbound",
        "wrong_candidate",
        "risk_veto",
        "missing_gate",
    ],
)
def test_runtime_validation_consumes_exact_maturity_and_keeps_all_vetoes(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle, case: str
) -> None:
    from datetime import timedelta

    from ai4binance.agents.validation_gate import ValidationGate
    from ai4binance.schemas import AgentResult, AgentStatus, DataQuality
    from tests.test_strategy_risk import approved_candidate, snapshot

    assert bundle.subject is not None
    subject = bundle.subject
    market = replace(
        snapshot(),
        symbol=subject.promotion.symbol,
        snapshot_id="gate-fixture",
        created_at=NOW,
        timeframes=(subject.promotion.timeframe,),
        ohlcv_by_timeframe={
            subject.promotion.timeframe: snapshot().ohlcv_by_timeframe["1h"]
        },
    )
    candidate = replace(
        approved_candidate(),
        snapshot_id=market.snapshot_id,
        timestamp=NOW,
        symbol=market.symbol,
        timeframe=subject.promotion.timeframe,
        setup_name=subject.setup_type,
    )
    risk = AgentResult(
        agent_name="risk",
        agent_version="1",
        snapshot_id=market.snapshot_id,
        timestamp=NOW,
        symbol=market.symbol,
        timeframes=market.timeframes,
        status=AgentStatus.SUCCESS,
        data_quality=DataQuality.DATA_VALID,
        applicable=True,
        directional_vote=0,
        score=100,
        confidence=1,
        reason_codes=("RISK_APPROVED",),
        calculation_metadata={"approved": True, "candidate_id": candidate.candidate_id},
    )
    if case == "wrong_hash":
        subject = replace(subject, feature_definition_sha256="9" * 64)
    if case == "stale":
        market = replace(market, created_at=NOW + timedelta(days=100))
        candidate = replace(candidate, timestamp=market.created_at)
        risk = replace(risk, timestamp=market.created_at)
    if case == "tampered":
        (tmp_path / bundle.artifacts[0][1].path).write_text("{}")
    if case == "wrong_candidate":
        candidate = replace(candidate, snapshot_id="another-snapshot")
    if case == "risk_veto":
        risk = replace(
            risk,
            status=AgentStatus.BLOCKED,
            blockers=("RISK.VETO",),
            calculation_metadata={
                "approved": False,
                "candidate_id": candidate.candidate_id,
            },
        )
    results = {"risk": risk}
    for name in ("data_quality", "universe_liquidity"):
        results[name] = replace(
            risk,
            agent_name=name,
            status=AgentStatus.SUCCESS,
            blockers=(),
            calculation_metadata={},
        )
    if case == "missing_gate":
        results.pop("data_quality")
    gate = ValidationGate(
        artifact_root=tmp_path,
        expected_subjects=() if case == "unbound" else (subject,),
        evidence_bundles=(bundle,),
    )
    decision = gate.validate(market, results, candidates=(candidate,))
    assert decision.execution_allowed is False
    if case == "valid":
        assert decision.validation_status is ValidationStatus.PAPER_APPROVED
        assert not decision.blockers
        assert any(
            ref.startswith("OOS_MATURITY:") for ref in decision.supporting_evidence
        )
    else:
        assert decision.validation_status is ValidationStatus.REJECTED
        assert decision.blockers
    if case == "risk_veto":
        assert "RISK.VETO" in decision.blockers
    if case == "unbound":
        assert any(
            blocker.startswith("OOS_SUBJECT_NOT_CONFIGURED:")
            for blocker in decision.blockers
        )


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "missing",
        "source_drift",
        "tampered_bundle",
        "identity",
        "duplicate",
        "traversal",
        "authority",
        "revoked",
    ],
)
def test_runtime_deployment_loads_bound_files_and_preserves_vetoes(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle, case: str
) -> None:
    from ai4binance.agents.validation_gate import ValidationGate
    from ai4binance.reporting import to_primitive
    from ai4binance.validation.oos_maturity import runtime_source_sha256

    assert bundle.subject is not None
    if case == "revoked":
        bundle = replace(
            bundle,
            promotion=PromotionEvidenceRegistry(
                (replace(bundle.promotion.records[0], revoked_at=NOW),)
            ),
        )
    safe = {
        "schema_version": "1.0",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    payload = {
        **safe,
        "subject": to_primitive(bundle.subject),
        "artifacts": {name: to_primitive(ref) for name, ref in bundle.artifacts},
        "specification": to_primitive(bundle.specification),
        "promotion_records": to_primitive(bundle.promotion.records),
        "blockers": [],
    }
    reference = write(tmp_path, "runtime-bundle.json", payload)
    subject = bundle.subject
    assert subject is not None
    if case == "identity":
        subject = replace(subject, feature_definition_sha256="9" * 64)
    if case == "traversal":
        reference = OOSArtifactReference("../runtime-bundle.json", reference.sha256)
    entry = {"subject": to_primitive(subject), "bundle": to_primitive(reference)}
    deployment = {
        **safe,
        "runtime_source_sha256": runtime_source_sha256(),
        "subjects": [entry, entry] if case == "duplicate" else [entry],
    }
    if case == "source_drift":
        deployment["runtime_source_sha256"] = "0" * 64
    if case == "authority":
        deployment["execution_allowed"] = True
    path = tmp_path / "deployment.json"
    if case != "missing":
        path.write_text(json.dumps(deployment), encoding="utf-8")
    if case == "tampered_bundle":
        (tmp_path / "runtime-bundle.json").write_text("{}", encoding="utf-8")
    loaded = ValidationGate.from_deployment(
        artifact_root=tmp_path, deployment_path=path, as_of=NOW
    )
    if case in {"valid", "revoked"}:
        assert loaded.expected_subjects == (subject,)
        result = OOSMaturityGate(tmp_path).evaluate(loaded.evidence_bundles[0])
        assert (result.status == "OOS_MATURITY_COMPLETE") is (case == "valid")
        assert result.execution_allowed is False
    else:
        assert loaded.evidence_load_blockers
        assert not loaded.evidence_bundles


def mutate(
    tmp_path: Path,
    bundle: OOSMaturityEvidenceBundle,
    stage: str,
    changes: dict[str, object],
) -> OOSMaturityEvidenceBundle:
    refs = dict(bundle.artifacts)
    payload = json.loads((tmp_path / refs[stage].path).read_bytes())
    payload.update(changes)
    refs[stage] = write(tmp_path, refs[stage].path, payload)
    return reviewed(replace(bundle, artifacts=tuple(refs.items())))


def test_complete_is_deterministic_and_never_grants_authority(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    result = OOSMaturityGate(tmp_path).evaluate(bundle)
    assert result.status == "OOS_MATURITY_COMPLETE", result.blockers
    assert not result.execution_allowed
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert result == OOSMaturityGate(tmp_path).evaluate(
        replace(bundle, artifacts=tuple(reversed(bundle.artifacts)))
    )


@pytest.mark.parametrize("stage", tuple(REQUIRED_MEASUREMENTS))
def test_every_stage_is_mandatory(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle, stage: str
) -> None:
    missing = reviewed(
        replace(
            bundle,
            artifacts=tuple(pair for pair in bundle.artifacts if pair[0] != stage),
        )
    )
    result = OOSMaturityGate(tmp_path).evaluate(missing)
    assert result.status == "OOS_MATURITY_INCOMPLETE"
    assert f"{stage.upper()}_EVIDENCE_MISSING" in result.blockers


@pytest.mark.parametrize(
    ("changes", "blocker"),
    [
        ({"subject_key": "0" * 64}, "EVIDENCE_IDENTITY_MISMATCH"),
        ({"execution_allowed": True}, "EVIDENCE_EXECUTION_AUTHORITY_FORBIDDEN"),
        ({"expires_at": "2026-01-01T00:00:00+00:00"}, "STALE_VALIDATION_EVIDENCE"),
        ({"observed_at": "2027-01-01T00:00:00+00:00"}, "STALE_VALIDATION_EVIDENCE"),
        ({"stage": "dataset"}, "EVIDENCE_STAGE_MISMATCH"),
        ({"blockers": None}, "EVIDENCE_BLOCKERS_INVALID"),
        ({"measurement_sources": {}}, "SOURCE_BINDING_MISSING"),
        ({"source_artifacts": []}, "UNDERLYING_EVIDENCE_MISSING"),
        ({"blockers": ["FRAGILE"]}, "FRAGILE"),
    ],
)
def test_artifacts_fail_closed(
    tmp_path: Path,
    bundle: OOSMaturityEvidenceBundle,
    changes: dict[str, object],
    blocker: str,
) -> None:
    result = OOSMaturityGate(tmp_path).evaluate(
        mutate(tmp_path, bundle, "robustness", changes)
    )
    assert result.status != "OOS_MATURITY_COMPLETE"
    assert any(blocker in item for item in result.blockers)


def test_changed_parameter_cannot_inherit_evidence(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    assert bundle.subject is not None
    subject = replace(
        bundle.subject,
        promotion=replace(bundle.subject.promotion, parameter_set_sha256="0" * 64),
    )
    result = OOSMaturityGate(tmp_path).evaluate(replace(bundle, subject=subject))
    assert result.status == "OOS_MATURITY_BLOCKED"
    assert "PROMOTION_EVIDENCE_INCOMPLETE" in result.blockers


def test_summary_cannot_replace_underlying_measurements(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    path = tmp_path / "final_holdout-source.json"
    payload = json.loads(path.read_bytes())
    payload["trade_count"] = 0
    source = write(tmp_path, path.name, payload)
    changed = mutate(
        tmp_path,
        bundle,
        "final_holdout",
        {"source_artifacts": [{"path": source.path, "sha256": source.sha256}]},
    )
    result = OOSMaturityGate(tmp_path).evaluate(changed)
    assert "FINAL_HOLDOUT:MEASUREMENT_SOURCE_MISMATCH" in result.blockers


def test_holdout_contamination_is_not_cleared_by_new_review(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    payload = json.loads((tmp_path / "history.json").read_bytes())
    payload["accesses"][0]["subject_key"] = "0" * 64
    history = write(tmp_path, "history.json", payload)
    changed = mutate(
        tmp_path,
        bundle,
        "final_holdout",
        {"holdout_history": {"path": history.path, "sha256": history.sha256}},
    )
    assert (
        "FINAL_HOLDOUT:HOLDOUT_CONTAMINATED"
        in OOSMaturityGate(tmp_path).evaluate(changed).blockers
    )


def test_tampering_and_path_escape_are_blocked(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    (tmp_path / "dataset.json").write_text("{}", encoding="utf-8")
    assert (
        "DATASET:EVIDENCE_HASH_MISMATCH"
        in OOSMaturityGate(tmp_path).evaluate(bundle).blockers
    )
    refs = dict(bundle.artifacts)
    refs["dataset"] = OOSArtifactReference("../outside.json", "a" * 64)
    assert (
        "DATASET:EVIDENCE_PATH_OUTSIDE_ROOT"
        in OOSMaturityGate(tmp_path)
        .evaluate(replace(bundle, artifacts=tuple(refs.items())))
        .blockers
    )


def test_no_spec_or_summary_only_promotion_cannot_close(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    assert (
        "VALIDATION_SPECIFICATION_MISSING"
        in OOSMaturityGate(tmp_path)
        .evaluate(replace(bundle, specification=None))
        .blockers
    )
    record = replace(
        bundle.promotion.records[0],
        source_kind=PromotionEvidenceSourceKind.VALIDATION_SUMMARY,
    )
    assert (
        "PROMOTION_EVIDENCE_INCOMPLETE"
        in OOSMaturityGate(tmp_path)
        .evaluate(replace(bundle, promotion=PromotionEvidenceRegistry((record,))))
        .blockers
    )


@pytest.mark.parametrize(
    ("value", "operator", "threshold", "expected"),
    [
        (None, "gte", 1, False),
        ("DATA_UNAVAILABLE", "eq", "DATA_UNAVAILABLE", False),
        ("NaN", "gte", 1, False),
        (True, "gte", 1, False),
        ("2.5", "gt", "2", True),
        (2, "gte", 2, True),
        (1, "lte", 2, True),
        ("PASS", "in", ["PASS"], True),
        (1, "unknown", 1, False),
        ("invalid", "gt", 1, False),
    ],
)
def test_metrics_never_manufacture_statistical_usability(
    value: object, operator: str, threshold: object, expected: bool
) -> None:
    assert _matches(value, {"operator": operator, "value": threshold}) is expected


def test_long_expiry_does_not_revive_stale_evidence(
    tmp_path: Path,
    bundle: OOSMaturityEvidenceBundle,
) -> None:
    changed = mutate(
        tmp_path, bundle, "statistics", {"observed_at": "2020-01-01T00:00:00+00:00"}
    )
    assert (
        "STATISTICS:STALE_VALIDATION_EVIDENCE"
        in OOSMaturityGate(tmp_path).evaluate(changed).blockers
    )


def test_conflicting_review_is_not_filtered_out(
    tmp_path: Path,
    bundle: OOSMaturityEvidenceBundle,
) -> None:
    rejection = replace(
        bundle.promotion.records[0],
        evidence_id="fixture-rejection",
        source_kind=PromotionEvidenceSourceKind.MANUAL_REVIEW,
        source_ref="review:rejected",
        blockers=("REJECTED_BY_REVIEW",),
    )
    changed = replace(
        bundle,
        promotion=PromotionEvidenceRegistry((*bundle.promotion.records, rejection)),
    )
    assert (
        "PROMOTION_EVIDENCE_INCOMPLETE"
        in OOSMaturityGate(tmp_path).evaluate(changed).blockers
    )


def test_underlying_veto_cannot_be_masked_by_wrapper(
    tmp_path: Path,
    bundle: OOSMaturityEvidenceBundle,
) -> None:
    source_payload = json.loads((tmp_path / "robustness-source.json").read_bytes())
    source_payload["blockers"] = ["FRAGILE"]
    source = write(tmp_path, "robustness-source.json", source_payload)
    changed = mutate(
        tmp_path,
        bundle,
        "robustness",
        {
            "source_artifacts": [{"path": source.path, "sha256": source.sha256}],
        },
    )
    assert (
        "ROBUSTNESS:MEASUREMENT_SOURCE_MISMATCH"
        in OOSMaturityGate(tmp_path).evaluate(changed).blockers
    )


@pytest.mark.parametrize("value", [float("inf"), float("nan"), float("-inf")])
def test_non_finite_equality_is_never_evidence(value: float) -> None:
    assert not _matches(value, {"operator": "eq", "value": value})


def test_relabeling_wrapper_cannot_rebind_another_subject_source(
    tmp_path: Path,
    bundle: OOSMaturityEvidenceBundle,
) -> None:
    payload = json.loads((tmp_path / "backtest-source.json").read_bytes())
    payload["subject_key"] = "0" * 64
    source = write(tmp_path, "backtest-source.json", payload)
    changed = mutate(
        tmp_path,
        bundle,
        "backtest",
        {
            "source_artifacts": [{"path": source.path, "sha256": source.sha256}],
        },
    )
    assert (
        "BACKTEST:SOURCE_EVIDENCE_IDENTITY_MISMATCH"
        in OOSMaturityGate(tmp_path).evaluate(changed).blockers
    )

"""OOS maturity preserves vetoes on malformed, unbound and conflicting evidence."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from ai4binance.validation import oos_maturity as maturity
from ai4binance.validation.oos_maturity import (
    OOSMaturityEvidenceBundle,
    OOSMaturityGate,
)
from tests.test_oos_maturity import NOW, mutate, write

pytest_plugins = ("tests.test_oos_maturity",)


@pytest.mark.parametrize(
    ("changes", "blocker"),
    [
        ({"stage": "wrong"}, "EVIDENCE_STAGE_MISMATCH"),
        ({"blockers": [None]}, "EVIDENCE_BLOCKERS_INVALID"),
        ({"source_artifacts": []}, "UNDERLYING_EVIDENCE_MISSING"),
        ({"measurement_sources": {}}, "SOURCE_BINDING_MISSING"),
    ],
)
def test_oos_rejects_unbound_stage_evidence(
    tmp_path: Path,
    bundle: OOSMaturityEvidenceBundle,
    changes: dict[str, Any],
    blocker: str,
) -> None:
    refs = dict(bundle.artifacts)
    payload = json.loads((tmp_path / refs["dataset"].path).read_text())
    payload.update(changes)
    refs["dataset"] = write(tmp_path, "changed.json", payload)
    result = OOSMaturityGate(tmp_path).evaluate(
        replace(bundle, artifacts=tuple(refs.items()))
    )
    assert any(blocker in item for item in result.blockers)
    assert result.status != "OOS_MATURITY_COMPLETE"
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"


@pytest.mark.parametrize(
    "case", ["identity", "governed", "scope", "unreadable", "duplicate", "unknown"]
)
def test_oos_rejects_invalid_specification_and_stage_inventory(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle, case: str
) -> None:
    assert bundle.subject is not None
    assert bundle.specification is not None
    expected = {
        "identity": "VALIDATION_SPECIFICATION_IDENTITY_MISMATCH",
        "governed": "VALIDATION_SPECIFICATION_NOT_GOVERNED",
        "scope": "VALIDATION_SCOPE_MISMATCH",
        "unreadable": "EVIDENCE_OBJECT_REQUIRED",
        "duplicate": "CONFLICTING_VALIDATION_EVIDENCE",
        "unknown": "UNKNOWN_VALIDATION_EVIDENCE_STAGE",
    }[case]
    if case in {"duplicate", "unknown"}:
        extra = (
            bundle.artifacts[0]
            if case == "duplicate"
            else ("unknown", bundle.artifacts[0][1])
        )
        changed = replace(bundle, artifacts=(*bundle.artifacts, extra))
    else:
        payload = json.loads((tmp_path / bundle.specification.path).read_text())
        if case == "governed":
            payload["owner"] = " "
        if case == "scope":
            payload["scope"] = []
        reference = write(
            tmp_path, "spec-new.json", [] if case == "unreadable" else payload
        )
        if case == "identity":
            changed = replace(
                bundle,
                subject=replace(bundle.subject, validation_config_sha256="0" * 64),
            )
        else:
            changed = replace(bundle, specification=reference)
    result = OOSMaturityGate(tmp_path).evaluate(changed)
    assert expected in result.blockers
    assert result.status == "OOS_MATURITY_BLOCKED"
    assert result.execution_allowed is False


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"expectancy": "bad"}, "NUMERIC_MEASUREMENT_INVALID"),
        ({"expectancy": "NaN"}, "NUMERIC_MEASUREMENT_INVALID"),
        ({"trade_count": -1}, "COUNT_INVALID"),
        ({"trade_count": True}, "COUNT_INVALID"),
        ({"fold_count": 0}, "SAMPLE_EMPTY"),
        ({"repository_clean": False}, "INVARIANT_NOT_PROVEN"),
    ],
)
def test_oos_measurements_reject_invalid_types(
    values: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        OOSMaturityGate._measurement_types(values)


@pytest.mark.parametrize(
    ("value", "operator", "expected", "result"),
    [
        (1, "in", [0, 1], True),
        (1, "in", [True], False),
        (1, "gte", 1, True),
        (2, "gt", 1, True),
        (1, "lte", 1, True),
        (True, "gt", 0, False),
        (float("inf"), "eq", 1, False),
        (1, "gt", float("nan"), False),
        ("bad", "gt", 1, False),
        ("NaN", "gt", 1, False),
        (1, "unknown", 1, False),
    ],
)
def test_governed_comparisons_are_typed_and_finite(
    value: object, operator: str, expected: object, result: bool
) -> None:
    assert maturity._matches(value, {"operator": operator, "value": expected}) is result


def test_oos_identity_and_artifact_guards(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    assert bundle.subject is not None
    with pytest.raises(ValueError, match="setup identity"):
        replace(bundle.subject, setup_type=" ")
    with pytest.raises(ValueError, match="SHA-256"):
        replace(bundle.subject, cost_model_sha256="bad")
    with pytest.raises(ValueError, match="path and SHA-256"):
        maturity.OOSArtifactReference("", "a" * 64)
    with pytest.raises(ValueError, match="OUTSIDE_ROOT"):
        OOSMaturityGate(tmp_path)._bytes(
            maturity.OOSArtifactReference("../outside", "a" * 64)
        )
    with pytest.raises(ValueError, match="DEPLOYMENT_MISSING"):
        OOSMaturityGate(tmp_path).load_deployment(tmp_path / "missing", as_of=NOW)
    with pytest.raises(ValueError, match="FIELD_INVALID"):
        maturity.OOSValidationSubject.from_payload({}, as_of=NOW)


@pytest.mark.parametrize("value", [None, "2026-09-01T00:00:00"])
def test_oos_timestamps_require_timezone(value: object) -> None:
    with pytest.raises(ValueError, match=r"TIMESTAMP_MISSING|TIMESTAMP_NOT_AWARE"):
        maturity._time(value)


def test_oos_pointer_traversal_is_bounded() -> None:
    assert maturity._at({"rows": [{"value": 3}]}, ["rows", 0, "value"]) == 3
    with pytest.raises(ValueError, match="POINTER_INVALID"):
        maturity._at([1], [2])


@pytest.mark.parametrize(
    "case", ["overlap", "freeze", "history_identity", "history_empty"]
)
def test_holdout_requires_frozen_disjoint_recorded_access(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle, case: str
) -> None:
    payload = json.loads((tmp_path / "final_holdout.json").read_text())
    changes: dict[str, Any] = {}
    expected = {
        "overlap": "HOLDOUT_PARTITIONS_OVERLAP",
        "freeze": "HOLDOUT_NOT_FROZEN_BEFORE_ACCESS",
        "history_identity": "HOLDOUT_HISTORY_IDENTITY_MISMATCH",
        "history_empty": "HOLDOUT_ACCESS_HISTORY_MISSING",
    }[case]
    if case == "overlap":
        payload["partitions"]["development_end"] = payload["partitions"][
            "development_start"
        ]
        changes["partitions"] = payload["partitions"]
    elif case == "freeze":
        changes["candidate_frozen_at"] = payload["first_holdout_access_at"]
    else:
        history = json.loads((tmp_path / "history.json").read_text())
        history["dataset_sha256" if case == "history_identity" else "accesses"] = (
            "0" * 64 if case == "history_identity" else []
        )
        ref = write(tmp_path, "history-new.json", history)
        changes["holdout_history"] = {"path": ref.path, "sha256": ref.sha256}
    result = OOSMaturityGate(tmp_path).evaluate(
        mutate(tmp_path, bundle, "final_holdout", changes)
    )
    assert f"FINAL_HOLDOUT:{expected}" in result.blockers
    assert result.status == "OOS_MATURITY_BLOCKED"
    assert result.execution_allowed is False


def test_paper_forward_rejects_reversed_observation_window(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    payload = json.loads((tmp_path / "paper_forward.json").read_text())
    source = json.loads((tmp_path / "paper_forward-source.json").read_text())
    value = "2026-09-09T00:00:00+00:00"
    payload["measurements"]["observation_ended_at"] = value
    source["observation_ended_at"] = value
    ref = write(tmp_path, "forward-new-source.json", source)
    payload["source_artifacts"] = [{"path": ref.path, "sha256": ref.sha256}]
    result = OOSMaturityGate(tmp_path).evaluate(
        mutate(tmp_path, bundle, "paper_forward", payload)
    )
    assert "PAPER_FORWARD:PAPER_FORWARD_CHRONOLOGY_INVALID" in result.blockers
    assert result.execution_allowed is False


def test_oos_limits_artifact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = write(tmp_path, "large.json", {"large": "x" * 50})
    monkeypatch.setattr(maturity, "MAX_ARTIFACT_BYTES", 10)
    with pytest.raises(ValueError, match="SIZE_LIMIT_EXCEEDED"):
        OOSMaturityGate(tmp_path)._bytes(ref)
    with pytest.raises(ValueError, match="DEPLOYMENT_INVALID"):
        OOSMaturityGate(tmp_path).load_deployment(tmp_path / ref.path, as_of=NOW)


def test_oos_runtime_hash_rejects_missing_and_oversized_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        maturity, "__file__", str(tmp_path / "validation/oos_maturity.py")
    )
    with pytest.raises(ValueError, match="RUNTIME_SOURCE_INVALID"):
        maturity.runtime_source_sha256()
    (tmp_path / "module.py").write_text("x" * 30, encoding="utf-8")
    monkeypatch.setattr(maturity, "MAX_ARTIFACT_BYTES", 10)
    with pytest.raises(ValueError, match="RUNTIME_SOURCE_INVALID"):
        maturity.runtime_source_sha256()


@pytest.mark.parametrize("case", ["subjects", "records"])
def test_oos_deployment_rejects_invalid_inventory(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle, case: str
) -> None:
    from ai4binance.reporting import to_primitive

    safe = {
        "schema_version": "1.0",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    ref = write(
        tmp_path,
        "bundle-invalid.json",
        {
            **safe,
            "subject": to_primitive(bundle.subject),
            "artifacts": {},
            "promotion_records": None,
            "blockers": [],
        },
    )
    deployment = {
        **safe,
        "runtime_source_sha256": maturity.runtime_source_sha256(),
        "subjects": []
        if case == "subjects"
        else [{"subject": to_primitive(bundle.subject), "bundle": to_primitive(ref)}],
    }
    path = tmp_path / "deployment-invalid.json"
    path.write_text(json.dumps(deployment), encoding="utf-8")
    with pytest.raises(ValueError, match=r"SUBJECTS_INVALID|BUNDLE_INVALID"):
        OOSMaturityGate(tmp_path).load_deployment(path, as_of=NOW)


def test_futures_oos_requires_all_derivative_measurements(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    assert bundle.subject is not None
    subject = replace(
        bundle.subject,
        promotion=replace(bundle.subject.promotion, market_type="USD_M_FUTURES"),
    )
    payload = json.loads((tmp_path / "dataset.json").read_text())
    source = json.loads((tmp_path / "dataset-source.json").read_text())
    payload["subject_key"] = source["subject_key"] = subject.subject_key
    reference = write(tmp_path, "futures-source.json", source)
    payload["source_artifacts"] = [{"path": reference.path, "sha256": reference.sha256}]
    changed = mutate(tmp_path, replace(bundle, subject=subject), "dataset", payload)
    result = OOSMaturityGate(tmp_path).evaluate(changed)
    for name in (
        "FUNDING_DATA_COVERAGE",
        "MARK_INDEX_COVERAGE",
        "MARGIN_SEMANTICS_STATUS",
        "LIQUIDATION_CONSTRAINTS_STATUS",
        "LONG_SHORT_COVERAGE",
    ):
        assert f"FUTURES_{name}_INSUFFICIENT" in result.blockers
    assert dict(result.stage_results)["dataset"] == "INCOMPLETE"
    assert result.execution_allowed is False


def test_oos_reads_bound_jsonl_measurements(
    tmp_path: Path, bundle: OOSMaturityEvidenceBundle
) -> None:
    payload = json.loads((tmp_path / "dataset.json").read_text())
    source = json.loads((tmp_path / "dataset-source.json").read_text())
    raw = (json.dumps(source) + "\n{}\n").encode()
    (tmp_path / "source.jsonl").write_bytes(raw)
    payload["source_artifacts"] = [
        {
            "path": "source.jsonl",
            "sha256": sha256(raw).hexdigest(),
            "identity_pointer": [0, "subject_key"],
        }
    ]
    for binding in payload["measurement_sources"].values():
        binding["pointer"].insert(0, 0)
    result = OOSMaturityGate(tmp_path).evaluate(
        mutate(tmp_path, bundle, "dataset", payload)
    )
    assert dict(result.stage_results)["dataset"] == "PASS"
    assert not any(item.startswith("DATASET:") for item in result.blockers)
    assert result.execution_allowed is False

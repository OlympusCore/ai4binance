"""Test-only exact-bound explanation persistence; never runtime authorization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from ai4binance.domain.research.canonical_cycle import (
    CycleArtifactKind,
    CycleArtifactRef,
)
from ai4binance.infrastructure.persistence.canonical_payloads import (
    CanonicalExplanationStore,
)
from tests.test_dashboard_decisions import SERVER


def explanation() -> tuple[CycleArtifactRef, dict[str, object]]:
    payload = {
        "action": "NO_TRADE",
        "reason_summary": "TEST_ONLY_VETO",
        "private": "TEST_ONLY_REDACT",
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    reference = CycleArtifactRef(
        "TEST_ONLY_DECISION",
        CycleArtifactKind.DECISION,
        "TEST_ONLY_CYCLE",
        "TEST_ONLY_SNAPSHOT",
        hashlib.sha256(encoded).hexdigest(),
    )
    return reference, {**reference.to_payload(), "payload": payload}


def test_missing_read_does_not_create_artifact_directory(tmp_path: Path) -> None:
    store = CanonicalExplanationStore(tmp_path / "explanations", boundary=tmp_path)
    reference, _ = explanation()
    assert store.read(reference) is None
    assert not store.directory.exists()


def test_saved_body_resolves_through_existing_dashboard_hash_checks(
    tmp_path: Path,
) -> None:
    store = CanonicalExplanationStore(tmp_path / "explanations", boundary=tmp_path)
    reference, body = explanation()
    store.save(reference, body)
    before = store.path_for(reference).read_bytes()
    store.save(reference, body)
    assert store.path_for(reference).read_bytes() == before
    projected = SERVER["decision_reference"](reference, {}, store)
    assert projected["status"] == "PAYLOAD_HASH_MATCH"
    assert projected["payload"]["reason_summary"] == "TEST_ONLY_VETO"
    assert "TEST_ONLY_REDACT" not in json.dumps(projected)
    other_cycle = replace(reference, cycle_id="TEST_ONLY_OTHER")
    assert store.read(other_cycle) is None
    assert (
        SERVER["decision_reference"](other_cycle, {}, store)["status"]
        == "PAYLOAD_UNAVAILABLE"
    )
    assert (
        SERVER["decision_reference"](reference, {reference.artifact_id: {}}, store)[
            "status"
        ]
        == "PAYLOAD_INVALID"
    )


@pytest.mark.parametrize("mutation", ["hash", "cycle", "snapshot", "oversize", "shape"])
def test_invalid_body_cannot_be_saved(tmp_path: Path, mutation: str) -> None:
    store = CanonicalExplanationStore(tmp_path / "explanations", boundary=tmp_path)
    reference, body = explanation()
    if mutation == "hash":
        body["payload"] = {"action": "BUY"}
    elif mutation in {"cycle", "snapshot"}:
        body[f"{mutation}_id"] = "TEST_ONLY_OTHER"
    elif mutation == "oversize":
        body["payload"] = {"reason_summary": "x" * 16_001}
    else:
        body["unexpected"] = "TEST_ONLY"
    with pytest.raises(ValueError, match="CANONICAL_EXPLANATION_"):
        store.save(reference, body)
    assert not store.directory.exists()


def test_corrupt_file_is_reported_and_never_overwritten(tmp_path: Path) -> None:
    store = CanonicalExplanationStore(tmp_path / "explanations", boundary=tmp_path)
    reference, body = explanation()
    store.save(reference, body)
    path = store.path_for(reference)
    path.write_text("{}", encoding="utf-8")
    assert (
        SERVER["decision_reference"](reference, {}, store)["status"]
        == "PAYLOAD_INVALID"
    )
    with pytest.raises(ValueError, match="CANONICAL_EXPLANATION_CONTEXT_MISMATCH"):
        store.save(reference, body)
    assert path.read_text(encoding="utf-8") == "{}"


def test_store_rejects_other_artifact_kinds_and_outside_boundary(
    tmp_path: Path,
) -> None:
    reference, body = explanation()
    store = CanonicalExplanationStore(tmp_path / "explanations", boundary=tmp_path)
    with pytest.raises(ValueError, match="KIND_NOT_ALLOWED"):
        store.read(replace(reference, artifact_kind=CycleArtifactKind.RISK_ASSESSMENT))
    outside = CanonicalExplanationStore(
        tmp_path.parent / "TEST_ONLY_OUTSIDE", boundary=tmp_path
    )
    with pytest.raises(ValueError, match="OUTSIDE_BOUNDARY"):
        outside.save(reference, body)

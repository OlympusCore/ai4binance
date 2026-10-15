"""Incomplete validation evidence cannot be aggregated into passing authority."""

import pytest

from ai4binance.governance import framework


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((), "MISSING"),
        (("PASS",), "PASS"),
        (("PASS", "FAIL"), "FAIL"),
        (("PASS", "PARTIAL"), "PARTIAL"),
        (("PASS", "MISSING"), "MISSING"),
        (("UNKNOWN",), "UNKNOWN"),
    ],
)
def test_regime_aggregation_preserves_the_strongest_evidence_gap(
    statuses: tuple[str, ...], expected: str
) -> None:
    evidence = framework.CapabilityValidationContract(
        validation_profile_id="test-only-regime-status",
        regime_status=tuple(
            (f"test-only-regime-{index}", framework.ValidationEvidenceStatus(status))
            for index, status in enumerate(statuses)
        ),
    )
    assert framework._aggregate_regime_status(evidence).value == expected
    assert dict(evidence.regime_status_map) == dict(evidence.regime_status)
    assert dict(evidence.stage_status_map) == dict(evidence.stage_status)
    with pytest.raises(TypeError):
        evidence.regime_status_map["new"] = framework.ValidationEvidenceStatus.PASS  # type: ignore[index]


def test_blank_evidence_and_malformed_hashes_do_not_count_as_valid_evidence() -> None:
    assert framework._present_as_pass(" ") is framework.ValidationEvidenceStatus.MISSING
    with pytest.raises(ValueError, match="cannot contain empty"):
        framework._require_unique("evidence", ("present", " "))
    for digest in ("a" * 63, "A" * 64, "g" * 64):
        with pytest.raises(ValueError, match="lowercase sha256"):
            framework._require_payload_hash(digest)

"""Failure-path coverage for governed quality-gate telemetry."""

from ai4binance.ops.quality_gate.telemetry import (
    build_compact_quality_console_summary,
    first_actionable_error,
    output_sha256,
)


def test_telemetry_sanitizes_fallback_output_and_hashes_redacted_text() -> None:
    """Error fallback must preserve diagnostics without preserving credentials."""
    output = "context only\naPi_Key = sensitive-value\n"
    assert first_actionable_error(output) == "context only\naPi_Key = [REDACTED]"
    sanitized = "context only\naPi_Key = [REDACTED]\n"
    assert output_sha256(output) == output_sha256(sanitized)


def test_telemetry_uses_bounded_generic_failure_when_no_error_is_available() -> None:
    """A failed run remains actionable when step and top-level text are absent."""
    summary = build_compact_quality_console_summary(
        status="FAIL",
        profile="full",
        run_id="run-1",
        duration_ms=1,
        selected_test_count=0,
        evidence_path="runtime/quality/run-1",
        steps=({"step_id": "pytest", "status": "FAIL"},),
    )
    assert summary == {
        "failed_step": "pytest",
        "exit_code": None,
        "first_actionable_error": "Quality gate failed; inspect evidence.",
        "evidence_path": "runtime/quality/run-1",
    }

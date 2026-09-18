"""Deterministic rule-based evaluation for advisory-only agent traces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|signature|private[_-]?key|passphrase)\b"
    r"\s*([:=])\s*([^\s,;]+)"
)


@dataclass(frozen=True, slots=True)
class AdvisoryTrace:
    trace_id: str
    fixture_id: str
    model_id: str
    prompt_revision: str
    input_sha256: str
    output_sha256: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...]
    started_at: datetime
    finished_at: datetime
    redacted: bool = True
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        values = (self.trace_id, self.fixture_id, self.model_id, self.prompt_revision)
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("advisory trace identity fields are invalid")
        if not _SHA256.fullmatch(self.input_sha256) or not _SHA256.fullmatch(
            self.output_sha256
        ):
            raise ValueError("advisory trace hashes are invalid")
        if len(set(self.citations)) != len(self.citations) or len(
            set(self.blockers)
        ) != len(self.blockers):
            raise ValueError("advisory trace evidence must be unique")
        for timestamp in (self.started_at, self.finished_at):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("advisory trace timestamps must be timezone-aware")
        if self.finished_at < self.started_at:
            raise ValueError("advisory trace finish precedes start")
        if not self.redacted or self.execution_allowed:
            raise ValueError("advisory trace must be redacted and non-executing")


@dataclass(frozen=True, slots=True)
class AdvisoryEvalExpectation:
    fixture_id: str
    required_citations: tuple[str, ...]
    required_blockers: tuple[str, ...]
    maximum_duration_ms: int

    def __post_init__(self) -> None:
        if not self.fixture_id.strip() or not 1 <= self.maximum_duration_ms <= 600_000:
            raise ValueError("advisory expectation is invalid")


@dataclass(frozen=True, slots=True)
class AdvisoryEvalResult:
    trace_id: str
    passed: bool
    blockers: tuple[str, ...]
    grader: str = "DETERMINISTIC_RULES"
    promotion_evidence: bool = False
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.passed == bool(self.blockers):
            raise ValueError("advisory evaluation and blockers disagree")
        if self.promotion_evidence or self.execution_allowed:
            raise ValueError("advisory evaluation cannot promote or execute")


@dataclass(frozen=True, slots=True)
class AdvisoryFixture:
    """A bounded, redacted fixture evaluated through an injected provider."""

    fixture_id: str
    prompt: str
    prompt_revision: str
    expectation: AdvisoryEvalExpectation

    def __post_init__(self) -> None:
        if (
            not self.fixture_id.strip()
            or not self.prompt.strip()
            or not self.prompt_revision.strip()
            or len(self.prompt) > 16_000
        ):
            raise ValueError("advisory fixture is invalid")
        if self.expectation.fixture_id != self.fixture_id:
            raise ValueError("advisory fixture expectation must match fixture ID")


@dataclass(frozen=True, slots=True)
class AdvisoryFixtureProviderResponse:
    """Provider response metadata retained only as redacted trace evidence."""

    model_id: str
    response_text: str
    citations: tuple[str, ...]
    blockers: tuple[str, ...]
    finished_at: datetime
    available: bool = True
    accepted: bool = True
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if not self.model_id.strip() or len(self.model_id) > 500:
            raise ValueError("advisory fixture provider model ID is invalid")
        if len(self.response_text) > 1_000_000:
            raise ValueError("advisory fixture provider response is too large")
        if len(set(self.citations)) != len(self.citations) or len(
            set(self.blockers)
        ) != len(self.blockers):
            raise ValueError("advisory fixture provider evidence must be unique")
        if self.finished_at.tzinfo is None or self.finished_at.utcoffset() is None:
            raise ValueError(
                "advisory fixture provider timestamp must be timezone-aware"
            )
        if self.accepted and not self.available:
            raise ValueError("unavailable advisory fixture provider cannot be accepted")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("advisory fixture provider cannot authorize execution")


class AdvisoryFixtureProvider(Protocol):
    """Local or remote provider adapter; runner authority remains advisory-only."""

    def run_fixture(
        self,
        prompt: str,
        *,
        fixture_id: str,
    ) -> AdvisoryFixtureProviderResponse: ...


@dataclass(frozen=True, slots=True)
class AdvisoryFixtureRun:
    """Fail-closed provider-backed fixture evaluation result."""

    fixture_id: str
    status: str
    trace: AdvisoryTrace | None
    evaluation: AdvisoryEvalResult | None
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    promotion_evidence: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.status not in {"PASS", "BLOCKED"}:
            raise ValueError("advisory fixture run status is invalid")
        if self.status == "PASS" and (
            self.trace is None or self.evaluation is None or self.blockers
        ):
            raise ValueError("passed advisory fixture run must have clean evidence")
        if self.status == "BLOCKED" and not self.blockers:
            raise ValueError("blocked advisory fixture run requires blockers")
        if (
            self.execution_allowed
            or self.promotion_evidence
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("advisory fixture run cannot promote or execute")


def evaluate_advisory_trace(
    trace: AdvisoryTrace,
    expectation: AdvisoryEvalExpectation,
) -> AdvisoryEvalResult:
    blockers: list[str] = []
    if trace.fixture_id != expectation.fixture_id:
        blockers.append("ADVISORY_FIXTURE_MISMATCH")
    if not set(expectation.required_citations).issubset(trace.citations):
        blockers.append("ADVISORY_REQUIRED_CITATION_MISSING")
    if not set(expectation.required_blockers).issubset(trace.blockers):
        blockers.append("ADVISORY_REQUIRED_BLOCKER_MISSING")
    duration_ms = int((trace.finished_at - trace.started_at).total_seconds() * 1_000)
    if duration_ms > expectation.maximum_duration_ms:
        blockers.append("ADVISORY_LATENCY_BUDGET_EXCEEDED")
    return AdvisoryEvalResult(trace.trace_id, not blockers, tuple(blockers))


def run_advisory_fixture(
    fixture: AdvisoryFixture,
    provider: AdvisoryFixtureProvider,
    *,
    started_at: datetime,
) -> AdvisoryFixtureRun:
    """Run a redacted fixture through a provider without granting authority."""
    if started_at.tzinfo is None or started_at.utcoffset() is None:
        raise ValueError("advisory fixture run timestamp must be timezone-aware")
    redacted_prompt = _redact_advisory_text(fixture.prompt)
    try:
        response = provider.run_fixture(redacted_prompt, fixture_id=fixture.fixture_id)
        if not isinstance(response, AdvisoryFixtureProviderResponse):
            raise TypeError("advisory fixture provider response is invalid")
        if not response.available:
            return _blocked_fixture_run(
                fixture.fixture_id, "ADVISORY_PROVIDER_UNAVAILABLE"
            )
        if not response.accepted:
            return _blocked_fixture_run(
                fixture.fixture_id,
                "ADVISORY_PROVIDER_RESPONSE_REJECTED",
            )
        redacted_response = _redact_advisory_text(response.response_text)
        trace = AdvisoryTrace(
            trace_id=_fixture_trace_id(fixture, redacted_prompt, redacted_response),
            fixture_id=fixture.fixture_id,
            model_id=response.model_id,
            prompt_revision=fixture.prompt_revision,
            input_sha256=_sha256(redacted_prompt),
            output_sha256=_sha256(redacted_response),
            citations=response.citations,
            blockers=tuple(dict.fromkeys(("LIVE_ORDER_BLOCKED", *response.blockers))),
            started_at=started_at,
            finished_at=response.finished_at,
        )
    except (OSError, TimeoutError):
        return _blocked_fixture_run(fixture.fixture_id, "ADVISORY_PROVIDER_UNAVAILABLE")
    except (TypeError, ValueError):
        return _blocked_fixture_run(
            fixture.fixture_id,
            "ADVISORY_PROVIDER_RESPONSE_INVALID",
        )
    evaluation = evaluate_advisory_trace(trace, fixture.expectation)
    if evaluation.passed:
        return AdvisoryFixtureRun(fixture.fixture_id, "PASS", trace, evaluation, ())
    return AdvisoryFixtureRun(
        fixture.fixture_id,
        "BLOCKED",
        trace,
        evaluation,
        evaluation.blockers,
    )


def _blocked_fixture_run(fixture_id: str, blocker: str) -> AdvisoryFixtureRun:
    return AdvisoryFixtureRun(fixture_id, "BLOCKED", None, None, (blocker,))


def _redact_advisory_text(value: str) -> str:
    return _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", value)


def _sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _fixture_trace_id(
    fixture: AdvisoryFixture,
    prompt: str,
    response: str,
) -> str:
    return f"trace:{_sha256(':'.join((fixture.fixture_id, prompt, response)))}"

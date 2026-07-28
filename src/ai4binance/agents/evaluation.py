"""Deterministic rule-based evaluation for advisory-only agent traces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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

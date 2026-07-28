"""Deterministic, fail-closed content compliance checks."""

import re
from dataclasses import dataclass

from ai4binance.content.models import ComplianceStatus

_PROFIT_PROMISES = (
    "garanti kazanç",
    "garantili kazanç",
    "kesin kazanç",
    "kesin yükselecek",
    "risksiz getiri",
    "guaranteed profit",
    "risk-free return",
)
_SECRET_PATTERN = re.compile(
    r"(?:api[_ -]?key|secret|token|password|authorization)\s*[:=]",
    re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_MENTION_PATTERN = re.compile(r"(?<!\w)@[A-Za-z0-9_]{1,15}\b")


@dataclass(frozen=True, slots=True)
class PolicyResult:
    """Stable compliance outcome with explicit machine-readable blockers."""

    status: ComplianceStatus
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContentCompliancePolicy:
    """Reject risky content before it reaches local human review."""

    max_characters: int = 280
    required_disclaimer: str = "Arastirma amaclidir; islem sinyali degildir."

    def __post_init__(self) -> None:
        if self.max_characters <= 0 or not self.required_disclaimer.strip():
            raise ValueError("content policy bounds must be positive and non-empty")

    def evaluate(self, content: str) -> PolicyResult:
        """Return all deterministic blockers in stable priority order."""
        normalized = " ".join(content.casefold().split())
        blockers: list[str] = []
        if not content.strip():
            blockers.append("CONTENT_EMPTY")
        if len(content) > self.max_characters:
            blockers.append("CONTENT_LENGTH_EXCEEDED")
        if self.required_disclaimer not in content:
            blockers.append("CONTENT_DISCLAIMER_MISSING")
        if any(phrase in normalized for phrase in _PROFIT_PROMISES):
            blockers.append("CONTENT_PROFIT_PROMISE_BLOCKED")
        if _URL_PATTERN.search(content):
            blockers.append("CONTENT_EXTERNAL_LINK_BLOCKED")
        if _MENTION_PATTERN.search(content):
            blockers.append("CONTENT_MENTION_BLOCKED")
        if _SECRET_PATTERN.search(content):
            blockers.append("CONTENT_SECRET_LIKE_TEXT_BLOCKED")
        return PolicyResult(
            status=(
                ComplianceStatus.PASSED if not blockers else ComplianceStatus.BLOCKED
            ),
            blockers=tuple(blockers),
        )

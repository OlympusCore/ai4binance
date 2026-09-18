"""Loopback-only adapter for advisory fixture evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from ai4binance.agents.evaluation import AdvisoryFixtureProviderResponse
from ai4binance.rag import AdvisoryProviderResult, RagSearchHit

_UNACCEPTED_PROVIDER_BLOCKERS = frozenset(
    {
        "LOCAL_LLM_EMPTY_RESPONSE",
        "LOCAL_LLM_RESPONSE_TRUNCATED",
    }
)
_UNAVAILABLE_PROVIDER_BLOCKER = "LOCAL_LLM_PROVIDER_UNAVAILABLE"


class LoopbackAdvisoryRunner(Protocol):
    """Existing loopback advisory-runner contract consumed without expansion."""

    def run(
        self,
        prompt: str,
        hits: tuple[RagSearchHit, ...],
    ) -> AdvisoryProviderResult: ...


@dataclass(frozen=True, slots=True)
class LoopbackAdvisoryFixtureProvider:
    """Adapt an injected local runner without creating a default network path."""

    runner: LoopbackAdvisoryRunner
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def run_fixture(
        self,
        prompt: str,
        *,
        fixture_id: str,
    ) -> AdvisoryFixtureProviderResponse:
        if not fixture_id.strip() or not prompt.strip():
            raise ValueError("advisory fixture request is invalid")
        result = self.runner.run(prompt, ())
        if result.prompt_sha256 != sha256(prompt.encode("utf-8")).hexdigest():
            raise ValueError("loopback advisory runner prompt hash mismatch")
        if (
            result.execution_allowed
            or result.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("loopback advisory runner attempted execution authority")
        finished_at = self.clock()
        if finished_at.tzinfo is None or finished_at.utcoffset() is None:
            raise ValueError("loopback advisory fixture clock must be timezone-aware")
        unavailable = _UNAVAILABLE_PROVIDER_BLOCKER in result.blockers
        accepted = (
            not unavailable
            and bool(result.response_text.strip())
            and not bool(_UNACCEPTED_PROVIDER_BLOCKERS.intersection(result.blockers))
        )
        return AdvisoryFixtureProviderResponse(
            model_id=result.model,
            response_text=result.response_text,
            citations=result.citations,
            blockers=result.blockers,
            finished_at=finished_at,
            available=not unavailable,
            accepted=accepted,
        )

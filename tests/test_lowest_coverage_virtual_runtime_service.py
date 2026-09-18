"""Fail-closed coverage for the canonical virtual runtime service bundle."""

from types import SimpleNamespace

import pytest

from ai4binance.application.services.virtual_runtime import (
    VirtualMarketCycleResult,
    evaluate_virtual_market_runtime,
)


def decision_bundle() -> tuple[object, object, object, object, object, object]:
    eligibility = SimpleNamespace(blockers=("RESEARCH_ONLY",))
    trade_intent = object()
    portfolio_before = object()
    portfolio_after = object()
    halt_review = object()
    decision = SimpleNamespace(
        eligibility=eligibility,
        trade_intent=trade_intent,
        portfolio_before=portfolio_before,
        portfolio_after=portfolio_after,
        audit_refs=("audit-1",),
        halt_review=halt_review,
        status=SimpleNamespace(value="RESEARCH_ONLY"),
        halted=True,
    )
    return (
        decision,
        eligibility,
        trade_intent,
        portfolio_before,
        portfolio_after,
        halt_review,
    )


def test_virtual_cycle_result_rejects_inconsistent_or_authorizing_values() -> None:
    decision, eligibility, intent, before, after, halt_review = decision_bundle()
    values: dict[str, object] = {
        "request": object(),
        "decision": decision,
        "eligibility": eligibility,
        "blockers": ("RESEARCH_ONLY",),
        "trade_intent": intent,
        "portfolio_before": before,
        "portfolio_after": after,
        "audit_refs": ("audit-1",),
        "halt_review": halt_review,
    }
    for overrides, message in (
        ({"execution_allowed": True}, "cannot grant execution"),
        ({"eligibility": object()}, "decision eligibility"),
        ({"blockers": ()}, "blockers are inconsistent"),
        ({"trade_intent": object()}, "trade intent is inconsistent"),
        ({"portfolio_before": object()}, "portfolio_before is inconsistent"),
        ({"portfolio_after": object()}, "portfolio_after is inconsistent"),
        ({"audit_refs": ()}, "audit refs are inconsistent"),
        ({"halt_review": object()}, "halt review is inconsistent"),
    ):
        attempt = dict(values)
        attempt.update(overrides)
        with pytest.raises(ValueError, match=message):
            VirtualMarketCycleResult(**attempt)

    result = VirtualMarketCycleResult(**values)
    assert result.to_payload()["decision_status"] == "RESEARCH_ONLY"
    assert result.halted is True
    assert result.to_payload()["execution_allowed"] is False


def test_virtual_runtime_service_uses_injected_runtime() -> None:
    request = object()
    runtime = SimpleNamespace(evaluate=lambda observed: ("evaluated", observed))

    assert evaluate_virtual_market_runtime(request, runtime=runtime) == (
        "evaluated",
        request,
    )

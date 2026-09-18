"""Deterministic access checks for governed memory retrieval and context use."""

from __future__ import annotations

from ai4binance.core.contracts.memory import MemoryAccessPolicy, MemoryRecord


def memory_access_request_blockers(
    policy: MemoryAccessPolicy,
    *,
    consumer: str,
    purpose: str,
    market_type: str | None,
    symbol: str | None,
    strategy_id: str | None,
) -> tuple[str, ...]:
    """Return deterministic hard blockers for a requested access scope."""
    blockers: list[str] = []
    if consumer not in policy.allowed_consumers:
        blockers.append("MEMORY_ACCESS_CONSUMER_DENIED")
    if purpose not in policy.allowed_purposes:
        blockers.append("MEMORY_ACCESS_PURPOSE_DENIED")
    for value, allowed_values, blocker in (
        (
            market_type,
            policy.allowed_market_types,
            "MEMORY_ACCESS_MARKET_NAMESPACE_DENIED",
        ),
        (
            symbol,
            policy.allowed_symbols,
            "MEMORY_ACCESS_SYMBOL_NAMESPACE_DENIED",
        ),
        (
            strategy_id,
            policy.allowed_strategy_ids,
            "MEMORY_ACCESS_STRATEGY_NAMESPACE_DENIED",
        ),
    ):
        if allowed_values is not None and value not in allowed_values:
            blockers.append(blocker)
    return tuple(blockers)


def memory_access_record_blockers(
    policy: MemoryAccessPolicy,
    record: MemoryRecord,
) -> tuple[str, ...]:
    """Return deterministic hard blockers for one candidate memory record."""
    blockers: list[str] = []
    if record.classification not in policy.allowed_classifications:
        blockers.append("MEMORY_ACCESS_CLASSIFICATION_DENIED")
    for value, allowed_values, blocker in (
        (
            record.market_type,
            policy.allowed_market_types,
            "MEMORY_ACCESS_MARKET_NAMESPACE_DENIED",
        ),
        (
            record.symbol,
            policy.allowed_symbols,
            "MEMORY_ACCESS_SYMBOL_NAMESPACE_DENIED",
        ),
        (
            record.strategy_id,
            policy.allowed_strategy_ids,
            "MEMORY_ACCESS_STRATEGY_NAMESPACE_DENIED",
        ),
    ):
        if allowed_values is not None and value not in allowed_values:
            blockers.append(blocker)
    return tuple(blockers)

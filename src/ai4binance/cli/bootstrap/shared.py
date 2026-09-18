"""Shared CLI contracts and payload helpers."""

from __future__ import annotations

from typing import cast

from ai4binance.config import Settings
from ai4binance.data import DataAcquisitionAgent
from ai4binance.data.acquisition import (
    LocalMarketPublicClient,
    LocalMarketSnapshotTransport,
)
from ai4binance.data.archive import ParquetOHLCVArchive
from ai4binance.governance.execution_authority import ExecutionSurface
from ai4binance.governance.execution_envelope import execution_envelope_for_surface

__all__ = (
    "virtual_market_gate_payload",
    "virtual_runtime_decision_payload",
)


def build_public_acquisition(settings: Settings) -> DataAcquisitionAgent:
    """Build the canonical local-only market snapshot boundary."""

    transport = LocalMarketSnapshotTransport(
        settings.dataset_directory / "spot" / "metadata",
        maximum_age_seconds=max(900, settings.market_history_live_interval_seconds * 3),
    )
    return DataAcquisitionAgent(
        client=LocalMarketPublicClient(transport),
        market_type=settings.market_type,
        candle_limit=settings.candle_limit,
        minimum_closed_candles=settings.minimum_closed_candles,
        max_workers=settings.max_data_workers,
        depth_path=(
            settings.dataset_directory / "depth" / "depth.sqlite3"
            if settings.market_depth_enabled
            else None
        ),
        archive=ParquetOHLCVArchive(settings.dataset_directory / "spot"),
    )


def virtual_market_gate_payload() -> dict[str, object]:
    """Return the canonical bounded virtual-market execution envelope payload."""

    envelope = execution_envelope_for_surface(ExecutionSurface.VIRTUAL_MARKET)
    return {
        "execution_surface": envelope.execution_surface.value,
        "automation_mode": envelope.automation_mode.value,
        "authority_profile_id": envelope.authority_profile_id,
        "manual_confirmation_required": envelope.manual_confirmation_required,
        "virtual_simulation_allowed": envelope.virtual_simulation_allowed,
        "auto_simulation_allowed": envelope.auto_simulation_allowed,
        "paper_execution_allowed": envelope.paper_execution_allowed,
        "external_order_allowed": envelope.external_order_allowed,
        "live_order_allowed": envelope.live_order_allowed,
        "bounded_simulation_only": envelope.bounded_simulation_only,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "blockers": envelope.reason_codes,
    }


def virtual_runtime_decision_payload(decision: object | None) -> object | None:
    """Normalize a virtual-runtime decision for CLI payload surfaces."""

    if decision is None:
        return None
    payload_builder = getattr(decision, "to_payload", None)
    if callable(payload_builder):
        return cast(object, payload_builder())
    eligibility = getattr(decision, "eligibility", None)
    eligibility_status = getattr(getattr(eligibility, "status", None), "value", None)
    eligibility_blockers = tuple(getattr(eligibility, "blockers", ()))
    live_eligibility_status = getattr(
        eligibility,
        "live_eligibility_status",
        "LIVE_ORDER_BLOCKED",
    )
    return {
        "status": getattr(getattr(decision, "status", None), "value", None),
        "eligibility": (
            {
                "status": eligibility_status,
                "blockers": eligibility_blockers,
                "live_eligibility_status": live_eligibility_status,
            }
            if eligibility is not None
            else None
        ),
        "blockers": eligibility_blockers,
        "trade_intent": getattr(decision, "trade_intent", None),
        "portfolio_before": getattr(decision, "portfolio_before", None),
        "portfolio_after": getattr(decision, "portfolio_after", None),
        "audit_refs": tuple(getattr(decision, "audit_refs", ())),
        "halt_review": getattr(decision, "halt_review", None),
        "halted": bool(getattr(decision, "halted", False)),
        "execution_allowed": False,
        "live_eligibility_status": live_eligibility_status,
    }


def __dir__() -> list[str]:
    return list(__all__)

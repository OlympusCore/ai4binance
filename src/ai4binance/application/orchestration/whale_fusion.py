"""Snapshot-consistent WHALE-FUSION application pipeline."""
# ruff: noqa: ANN401

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class WhaleFusionCycle:
    snapshot_id: str
    symbol: str
    asset: str
    whale_events: tuple[object, ...] = ()
    social_events: tuple[object, ...] = ()
    derivatives: object | None = None
    contradictions: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.asset.strip():
            raise ValueError("fusion cycle requires snapshot_id and asset")
        normalized_symbol = self.symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("fusion cycle symbol cannot be empty")
        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "asset", self.asset.strip().upper())


@dataclass(frozen=True, slots=True)
class WhaleFusionWorkflowResult:
    snapshot_id: str
    fusion: Any
    analysis: Any
    audit_written: bool | None
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("fusion workflow cannot grant execution authority")
        if self.live_eligibility_status != "LIVE_ORDER_BLOCKED":
            raise ValueError("fusion workflow must remain live blocked")
        if not self.snapshot_id.strip():
            raise ValueError("fusion workflow snapshot_id cannot be empty")
        if self.analysis.snapshot_id != self.snapshot_id:
            raise ValueError("fusion workflow analysis must use the fusion snapshot")


@dataclass(frozen=True, slots=True)
class WhaleFusionResearchService:
    engine: Any
    orchestrator: Any
    envelope_builder: Callable[[str, str, Any], Any]
    snapshot_attacher: Callable[[Any, Any], Any]
    audit_writer: Any | None = None

    def run(
        self,
        snapshot: Any,
        cycle: WhaleFusionCycle,
    ) -> WhaleFusionWorkflowResult:
        if cycle.snapshot_id != snapshot.snapshot_id:
            raise ValueError("fusion cycle and snapshot IDs must match")
        if cycle.symbol != snapshot.symbol:
            raise ValueError("fusion cycle and snapshot symbols must match")
        fusion = self.engine.evaluate(
            symbol=cycle.symbol,
            asset=cycle.asset,
            as_of=snapshot.created_at,
            whale_events=cycle.whale_events,
            social_events=cycle.social_events,
            derivatives=cycle.derivatives,
            contradictions=cycle.contradictions,
        )
        envelope = self.envelope_builder(
            snapshot.snapshot_id,
            snapshot.symbol,
            fusion,
        )
        audit_written: bool | None = None
        pipeline_blockers: list[str] = []
        if self.audit_writer is not None:
            try:
                audit_written = self.audit_writer.append(envelope)
            except (OSError, TypeError, ValueError):
                audit_written = False
                pipeline_blockers.append("FUSION_AUDIT_WRITE_FAILED")
                fusion = replace(
                    fusion,
                    blockers=tuple(
                        dict.fromkeys((*fusion.blockers, *pipeline_blockers))
                    ),
                )
                envelope = self.envelope_builder(
                    snapshot.snapshot_id,
                    snapshot.symbol,
                    fusion,
                )
        attached = self.snapshot_attacher(snapshot, envelope)
        analysis = self.orchestrator.analyze(attached)
        blockers = tuple(
            dict.fromkeys((*fusion.blockers, *pipeline_blockers, *analysis.blockers))
        )
        return WhaleFusionWorkflowResult(
            snapshot_id=snapshot.snapshot_id,
            fusion=fusion,
            analysis=analysis,
            audit_written=audit_written,
            blockers=blockers,
        )

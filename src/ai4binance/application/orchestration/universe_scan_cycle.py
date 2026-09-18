"""Application service that turns real universe data into scan reports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast


class MarketUniverseSnapshot(Protocol):
    spot_symbols: tuple[object, ...]
    futures_symbols: tuple[object, ...]
    blockers: tuple[str, ...]


class OpportunityScanReportLike(Protocol):
    command: str
    market: str
    candidates: tuple[object, ...]
    blockers: tuple[str, ...]
    funnel: object
    snapshot_id: str
    status: str


class MarketUniverseProvider(Protocol):
    def snapshot(
        self,
        priority_symbols: Sequence[str] = (),
    ) -> MarketUniverseSnapshot:
        """Return read-only market universe inputs."""


class OpportunityScanner(Protocol):
    def __call__(
        self,
        command: str,
        *,
        spot_symbols: Sequence[object],
        futures_symbols: Sequence[object],
    ) -> OpportunityScanReportLike: ...


@dataclass(frozen=True, slots=True)
class UniverseScanCycle:
    """Coordinate universe acquisition and deterministic opportunity scanning."""

    provider: object
    scanner: object
    priority_symbols: tuple[str, ...] = ()

    def run(self, command: str) -> OpportunityScanReportLike:
        snapshot = cast(Any, self.provider).snapshot(self.priority_symbols)
        report = cast(
            OpportunityScanReportLike,
            cast(Any, self.scanner)(
                command,
                spot_symbols=snapshot.spot_symbols,
                futures_symbols=snapshot.futures_symbols,
            ),
        )
        if not snapshot.blockers:
            return report
        report_type = cast(Any, report.__class__)
        return cast(
            OpportunityScanReportLike,
            report_type(
                command=report.command,
                market=report.market,
                candidates=report.candidates,
                blockers=tuple(dict.fromkeys((*snapshot.blockers, *report.blockers))),
                funnel=report.funnel,
                snapshot_id=report.snapshot_id,
                status="RUNNING_WITH_BLOCKERS",
            ),
        )

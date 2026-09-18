"""Common radar connector protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ai4binance.external_intel.core.enums import RadarName
from ai4binance.external_intel.core.models import ExternalFinding
from ai4binance.external_intel.core.validation import require_aware, require_text


@dataclass(frozen=True, slots=True)
class RadarRequest:
    run_id: str
    observed_at: datetime
    symbol: str | None = None
    topic: str | None = None

    def __post_init__(self) -> None:
        require_text("radar request run id", self.run_id, maximum=200)
        require_aware("radar request observed_at", self.observed_at)


class RadarConnector(Protocol):
    radar_name: RadarName

    def run(self, request: RadarRequest) -> tuple[ExternalFinding, ...]: ...

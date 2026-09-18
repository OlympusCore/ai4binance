"""Heuristic manipulation and copy-risk scoring."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.external_intel.core.validation import require_unit_interval


@dataclass(frozen=True, slots=True)
class ManipulationSignals:
    copy_ratio: float
    low_source_quality_ratio: float = 0.0
    urgency_language_ratio: float = 0.0
    referral_or_pump_ratio: float = 0.0
    synchronized_activity_ratio: float = 0.0

    def __post_init__(self) -> None:
        values = (
            ("copy_ratio", self.copy_ratio),
            ("low_source_quality_ratio", self.low_source_quality_ratio),
            ("urgency_language_ratio", self.urgency_language_ratio),
            ("referral_or_pump_ratio", self.referral_or_pump_ratio),
            ("synchronized_activity_ratio", self.synchronized_activity_ratio),
        )
        for name, value in values:
            require_unit_interval(name, value)


def score_manipulation(signals: ManipulationSignals) -> float:
    weighted = (
        signals.copy_ratio * 0.35
        + signals.low_source_quality_ratio * 0.20
        + signals.urgency_language_ratio * 0.15
        + signals.referral_or_pump_ratio * 0.15
        + signals.synchronized_activity_ratio * 0.15
    )
    return max(0.0, min(1.0, weighted))

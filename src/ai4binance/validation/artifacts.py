"""Read-only human approval artifacts for paper promotion resolution."""

from dataclasses import dataclass
from datetime import datetime

from ai4binance.domain import ValidationStatus


@dataclass(frozen=True, slots=True)
class StrategyApprovalArtifact:
    approval_id: str
    approved_at: datetime
    symbol: str
    timeframe: str
    playbook: str
    strategy_version: str
    config_hash: str
    status: ValidationStatus = ValidationStatus.PAPER_APPROVED

    def __post_init__(self) -> None:
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        if not all(
            value.strip()
            for value in (
                self.approval_id,
                self.symbol,
                self.timeframe,
                self.playbook,
                self.strategy_version,
                self.config_hash,
            )
        ):
            raise ValueError("approval artifact identity is required")
        if self.status is not ValidationStatus.PAPER_APPROVED:
            raise ValueError("artifact resolver cannot grant live eligibility")


@dataclass(frozen=True, slots=True)
class ValidationArtifactRegistry:
    artifacts: tuple[StrategyApprovalArtifact, ...] = ()

    def resolve(
        self,
        *,
        symbol: str,
        timeframe: str,
        playbook: str,
        strategy_version: str,
        config_hash: str,
    ) -> ValidationStatus:
        matches = tuple(
            item
            for item in self.artifacts
            if (
                item.symbol.upper(),
                item.timeframe,
                item.playbook,
                item.strategy_version,
                item.config_hash,
            )
            == (symbol.upper(), timeframe, playbook, strategy_version, config_hash)
        )
        if len(matches) != 1:
            return ValidationStatus.RESEARCH_ONLY
        return matches[0].status

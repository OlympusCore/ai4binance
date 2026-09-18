"""Fail-closed orchestration for exact-bound Futures OOS publication."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ai4binance.validation.futures_oos import (
    FuturesOosEvidenceWriter,
    FuturesOosEvidenceWriteResult,
)
from ai4binance.validation.futures_replay import RuntimeFuturesReplayDataset
from ai4binance.validation.models import (
    ParameterSet,
    WalkForwardConfig,
    WalkForwardFold,
)
from ai4binance.validation.walk_forward import (
    FuturesStrategyFactory,
    FuturesWalkForwardValidator,
    RegimeClassifier,
)
from ai4binance.whale_fusion.models import PriceOiRegime

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_GIT_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class FuturesOosRevisionSnapshot:
    """Attest one clean Git revision without granting repository authority."""

    code_revision: str
    repository_clean: bool

    def __post_init__(self) -> None:
        if not _GIT_REVISION_PATTERN.fullmatch(self.code_revision):
            raise ValueError("Futures OOS code revision must be a lowercase Git SHA-1")
        if not isinstance(self.repository_clean, bool):
            raise TypeError("Futures OOS repository cleanliness must be boolean")


FuturesOosRevisionResolver = Callable[[], FuturesOosRevisionSnapshot]


@dataclass(frozen=True, slots=True)
class FuturesOosPublicationResult:
    """Return exact publication identities with no execution authority."""

    report_id: str
    strategy_sha256: str
    dataset_sha256: str
    code_revision: str
    evidence: FuturesOosEvidenceWriteResult
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="STAGED_CANDIDATE", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)

    def __post_init__(self) -> None:
        if not self.report_id.strip():
            raise ValueError("Futures OOS publication report identity is required")
        if not _SHA256_PATTERN.fullmatch(self.strategy_sha256):
            raise ValueError("Futures OOS publication strategy hash is invalid")
        if not _SHA256_PATTERN.fullmatch(self.dataset_sha256):
            raise ValueError("Futures OOS publication dataset hash is invalid")
        if not _GIT_REVISION_PATTERN.fullmatch(self.code_revision):
            raise ValueError("Futures OOS publication code revision is invalid")
        if self.evidence.execution_allowed:
            raise ValueError("Futures OOS publication cannot grant execution authority")


@dataclass(frozen=True, slots=True)
class FuturesOosPublicationService:
    """Validate and publish one immutable, exact-bound Futures OOS result."""

    writer: FuturesOosEvidenceWriter
    revision_resolver: FuturesOosRevisionResolver
    validator: FuturesWalkForwardValidator = field(
        default_factory=FuturesWalkForwardValidator
    )
    execution_allowed: bool = field(default=False, init=False)
    promotion_status: str = field(default="RESEARCH_ONLY", init=False)
    live_eligibility_status: str = field(default="LIVE_ORDER_BLOCKED", init=False)

    def publish(
        self,
        *,
        dataset: RuntimeFuturesReplayDataset,
        setup: PriceOiRegime,
        parameters: tuple[ParameterSet, ...],
        strategy_factory: FuturesStrategyFactory,
        regime_classifier: RegimeClassifier,
        config: WalkForwardConfig,
    ) -> FuturesOosPublicationResult:
        """Publish only when dataset, strategy, and clean revision stay exact."""

        initial_revision = self._resolve_clean_revision()
        initial_dataset_sha256 = dataset.dataset_sha256
        report = self.validator.validate(
            dataset=dataset,
            setup=setup,
            parameters=parameters,
            strategy_factory=strategy_factory,
            regime_classifier=regime_classifier,
            config=config,
        )
        strategy_sha256 = self._selected_strategy_sha256(
            report.folds,
            strategy_factory,
        )
        final_dataset_sha256 = dataset.dataset_sha256
        if final_dataset_sha256 != initial_dataset_sha256:
            raise ValueError("FUTURES_OOS_DATASET_MUTATED_DURING_VALIDATION")
        final_revision = self._resolve_clean_revision()
        if final_revision != initial_revision:
            raise ValueError("FUTURES_OOS_CODE_REVISION_CHANGED_DURING_VALIDATION")
        evidence = self.writer.write(
            report,
            setup_name=setup.value,
            strategy_sha256=strategy_sha256,
            dataset_sha256=final_dataset_sha256,
            code_revision=final_revision.code_revision,
        )
        return FuturesOosPublicationResult(
            report_id=report.report_id,
            strategy_sha256=strategy_sha256,
            dataset_sha256=final_dataset_sha256,
            code_revision=final_revision.code_revision,
            evidence=evidence,
        )

    def _resolve_clean_revision(self) -> FuturesOosRevisionSnapshot:
        snapshot = self.revision_resolver()
        if not isinstance(snapshot, FuturesOosRevisionSnapshot):
            raise TypeError(
                "Futures OOS revision resolver must return FuturesOosRevisionSnapshot"
            )
        if not snapshot.repository_clean:
            raise ValueError("FUTURES_OOS_REPOSITORY_NOT_CLEAN")
        return snapshot

    @staticmethod
    def _selected_strategy_sha256(
        folds: tuple[WalkForwardFold, ...],
        strategy_factory: FuturesStrategyFactory,
    ) -> str:
        selected_parameters: list[ParameterSet] = []
        for fold in folds:
            parameter = fold.selected_parameters
            if parameter not in selected_parameters:
                selected_parameters.append(parameter)
        hashes = {
            getattr(strategy_factory(parameter), "strategy_sha256", "")
            for parameter in selected_parameters
        }
        if len(hashes) != 1:
            raise ValueError("FUTURES_OOS_SELECTED_STRATEGY_HASH_NOT_UNIQUE")
        strategy_sha256 = hashes.pop()
        if not isinstance(strategy_sha256, str) or not _SHA256_PATTERN.fullmatch(
            strategy_sha256
        ):
            raise ValueError("Futures OOS selected strategy hash is invalid")
        return strategy_sha256

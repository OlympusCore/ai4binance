"""Futures OOS publication requires exact identities and trusted revision evidence."""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest

from ai4binance.validation.futures_oos import (
    FuturesOosEvidenceWriter,
    FuturesOosEvidenceWriteResult,
)
from ai4binance.validation.futures_oos_publication import (
    FuturesOosPublicationResult,
    FuturesOosPublicationService,
    FuturesOosRevisionSnapshot,
)
from tests.test_futures_walk_forward import (
    PARAMETERS,
    SETUP,
    _config,
    _regime_classifier,
    _replay,
    _strategy_factory,
)


@pytest.mark.parametrize(
    ("revision", "clean", "error", "message"),
    [
        ("A" * 40, True, ValueError, "lowercase"),
        ("a" * 39, True, ValueError, "lowercase"),
        ("a" * 40, 1, TypeError, "boolean"),
    ],
)
def test_oos_revision_requires_exact_hash_and_boolean_cleanliness(
    revision: str, clean: bool, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        FuturesOosRevisionSnapshot(revision, clean)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("report_id", "", "identity"),
        ("strategy_sha256", "bad", "strategy hash"),
        ("dataset_sha256", "bad", "dataset hash"),
        ("code_revision", "bad", "code revision"),
    ],
)
def test_oos_publication_rejects_invalid_exact_bindings(
    field: str, value: object, message: str
) -> None:
    evidence = FuturesOosEvidenceWriteResult(
        "evidence.json", "artifact.json", "evidence-1", "a" * 64, True
    )
    result = FuturesOosPublicationResult(
        "report-1", "b" * 64, "c" * 64, "d" * 40, evidence
    )
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match=message):
        replace(result, **{field: cast(Any, value)})


def test_oos_publication_rejects_invalid_revision_provider_before_writing(
    tmp_path: Path,
) -> None:
    service = FuturesOosPublicationService(
        FuturesOosEvidenceWriter(tmp_path),
        revision_resolver=Mock(return_value="invalid"),
    )
    with pytest.raises(TypeError, match="must return FuturesOosRevisionSnapshot"):
        service.publish(
            dataset=_replay(),
            setup=SETUP,
            parameters=(PARAMETERS,),
            strategy_factory=_strategy_factory,
            regime_classifier=_regime_classifier,
            config=_config(),
        )
    assert not list(tmp_path.rglob("*.json"))

"""Focused fail-closed coverage for the strategy registry contracts."""

# ruff: noqa: I001

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from ai4binance.domain import ValidationStatus
from ai4binance.validation.summary import ValidationSummaryReader

# Initialize validation before importing the registry's validation dependency.
from ai4binance.strategies import registry
from ai4binance.strategies.registry import (
    GovernedStrategyRegistry,
    GovernedStrategyRegistryEntry,
    PlaybookRegistry,
    StrategyPlaybook,
    StrategyRiskProfile,
    StrategyRiskProfileRegistry,
    VirtualStrategyDefinition,
    VirtualStrategyPortfolioRegistry,
)


def _playbook(**changes: object) -> StrategyPlaybook:
    values: dict[str, object] = {
        "name": "playbook",
        "compatible_regimes": ("TREND",),
        "required_agents": ("risk",),
        "minimum_evidence": 1,
        "entry_trigger": "entry",
        "invalidation_rule": "invalidate",
        "stop_rule": "stop",
        "target_rule": "target",
        "trailing_rule": "trail",
        "rejection_rules": ("reject",),
        "required_oos_evidence": ("oos",),
        "implemented": True,
    }
    values.update(changes)
    return StrategyPlaybook(**values)  # type: ignore[arg-type]


def _profile(**changes: object) -> StrategyRiskProfile:
    values: dict[str, object] = {
        "strategy_id": "strategy",
        "version": "1",
        "stop_atr_multiple": Decimal("1"),
        "target_atr_multiple": Decimal("2"),
        "minimum_rr": Decimal("2"),
    }
    values.update(changes)
    return StrategyRiskProfile(**values)  # type: ignore[arg-type]


def _strategy(**changes: object) -> VirtualStrategyDefinition:
    values: dict[str, object] = {
        "strategy_id": "strategy",
        "strategy_version": "1",
        "supported_markets": ("SPOT",),
        "supported_regimes": ("TREND",),
        "entry_rule": "entry",
        "invalidation_rule": "invalidate",
        "exit_rule": "exit",
        "risk_profile": "risk",
        "playbooks": ("playbook",),
    }
    values.update(changes)
    return VirtualStrategyDefinition(**values)  # type: ignore[arg-type]


def _governed(**changes: object) -> GovernedStrategyRegistryEntry:
    values: dict[str, object] = {
        "strategy_id": "strategy",
        "version": "1",
        "implementation_ref": "module:strategy",
        "parameter_set_ref": "PARAMETER_SET_NOT_BOUND",
        "market_scope": ("SPOT",),
        "regime_scope": ("TREND",),
        "dataset_revision": "DATASET_REVISION_NOT_BOUND",
        "backtest_ref": "BACKTEST_REF_NOT_BOUND",
        "walk_forward_ref": "WALK_FORWARD_REF_NOT_BOUND",
        "oos_ref": "OOS_REF_NOT_BOUND",
        "robustness_ref": "ROBUSTNESS_REF_NOT_BOUND",
        "paper_ref": "PAPER_REF_NOT_BOUND",
        "owner": "governance",
        "playbooks": ("playbook",),
    }
    values.update(changes)
    return GovernedStrategyRegistryEntry(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _playbook(name=" "),
        lambda: _playbook(minimum_evidence=0),
        lambda: _playbook(required_agents=()),
        lambda: _playbook(promotion_status=ValidationStatus.LIVE_ELIGIBLE),
        lambda: _profile(strategy_id=" "),
        lambda: _profile(stop_atr_multiple=Decimal("0")),
        lambda: _profile(breakeven_trigger_r=Decimal("0")),
        lambda: _profile(trailing_atr_multiple=Decimal("0")),
        lambda: _profile(maximum_holding_bars=0),
        lambda: _strategy(strategy_id=" "),
        lambda: _strategy(supported_markets=()),
        lambda: _strategy(promotion_status=ValidationStatus.LIVE_ELIGIBLE),
        lambda: _strategy(live_eligibility_status="LIVE_ELIGIBLE"),
        lambda: _strategy(bounded_simulation_only=False),
        lambda: _governed(owner=" "),
        lambda: _governed(market_scope=()),
    ],
)
def test_strategy_contracts_reject_invalid_or_live_authority_inputs(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError, match=r"."):
        factory()


def test_risk_profiles_resolve_exact_baseline_and_normalize_overrides() -> None:
    baseline = _profile()
    exact = _profile(regime="TREND")
    registry_instance = StrategyRiskProfileRegistry((baseline, exact))

    assert registry_instance.resolve("strategy", regime="trend") == exact
    assert registry_instance.resolve(" strategy ", regime="RANGE") == baseline
    with pytest.raises(ValueError, match="not configured"):
        registry_instance.resolve("missing")
    with pytest.raises(ValueError, match="unique"):
        StrategyRiskProfileRegistry((baseline, _profile()))
    assert (
        _profile()
        .with_parameter_overrides(
            {
                "atr_stop_multiplier": "1.5",
                "take_profit_multiplier": "3",
                "maximum_holding_bars": True,
            }
        )
        .maximum_holding_bars
        == 1
    )
    with pytest.raises(TypeError, match="integer"):
        _profile().with_parameter_overrides({"maximum_holding_bars": Decimal("2")})


def test_strategy_portfolios_and_playbooks_preserve_unique_mappings() -> None:
    first = _strategy()
    second = _strategy(strategy_id="second", playbooks=("second-playbook",))
    portfolio = VirtualStrategyPortfolioRegistry((first, second))
    assert portfolio.get("strategy") == first
    assert portfolio.resolve_playbook("second-playbook") == second
    assert portfolio.supports_playbook("missing") is False
    with pytest.raises(ValueError, match="ids must be unique"):
        VirtualStrategyPortfolioRegistry((first, first))
    with pytest.raises(ValueError, match="playbooks must map"):
        VirtualStrategyPortfolioRegistry((first, _strategy(strategy_id="other")))

    playbook = _playbook()
    playbooks = PlaybookRegistry((playbook,))
    assert (
        playbooks.with_promotion("playbook", ValidationStatus.PAPER_APPROVED)
        .get("playbook")
        .promotion_status
        is ValidationStatus.PAPER_APPROVED
    )
    with pytest.raises(ValueError, match="implemented"):
        PlaybookRegistry((_playbook(implemented=False),)).with_promotion(
            "playbook", ValidationStatus.PAPER_APPROVED
        )
    with pytest.raises(ValueError, match="paper-only"):
        playbooks.with_promotion("playbook", ValidationStatus.RESEARCH_ONLY)
    with pytest.raises(ValueError, match="unique"):
        PlaybookRegistry((playbook, playbook))


def test_governed_registry_keeps_incomplete_evidence_research_only() -> None:
    entry = _governed()
    governed = GovernedStrategyRegistry((entry,))

    assert entry.evidence_complete is False
    assert entry.paper_ready is False
    assert len(entry.missing_evidence_refs) == 7
    assert governed.get("strategy") == entry
    assert governed.resolve_playbook("playbook") == entry
    with pytest.raises(ValueError, match="paper-only"):
        governed.with_promotion("strategy", ValidationStatus.RESEARCH_ONLY)
    with pytest.raises(ValueError, match="requires complete"):
        governed.with_promotion("strategy", ValidationStatus.PAPER_APPROVED)
    with pytest.raises(ValueError, match="ids must be unique"):
        GovernedStrategyRegistry((entry, entry))
    with pytest.raises(ValueError, match="playbooks must map"):
        GovernedStrategyRegistry((entry, replace(entry, strategy_id="other")))


def test_evidence_reference_helpers_are_path_safe_and_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert ValidationSummaryReader.__name__ == "ValidationSummaryReader"
    monkeypatch.setattr(registry, "_REPOSITORY_ROOT", tmp_path)
    relative = Path(
        "runtime/artifacts/research/backtest/validation/BTCUSDT/1h/run.json"
    )
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_text("{}", encoding="utf-8")

    assert registry._resolve_evidence_path(str(relative)) == target
    assert registry._resolve_evidence_path("missing.json") is None
    assert registry._resolve_evidence_root(str(target.parent)) == target.parent
    assert registry._resolve_evidence_root("missing") is None
    assert registry._infer_validation_symbol(target) == "BTCUSDT"
    assert registry._infer_validation_symbol(Path("not-validation/run.json")) is None
    assert registry._infer_validation_symbol(Path("validation/BTCUSDT")) is None
    assert registry._strategy_evidence_refs("TREND_PULLBACK")["paper_ref"].endswith(
        "validation"
    )

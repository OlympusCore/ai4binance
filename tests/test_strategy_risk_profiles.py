"""Deterministic strategy risk-profile resolution tests."""

from decimal import Decimal

import pytest

from ai4binance.strategies.registry import (
    StrategyRiskProfile,
    StrategyRiskProfileRegistry,
    build_strategy_risk_profile_registry,
)


def test_default_strategy_risk_profiles_preserve_virtual_market_baseline() -> None:
    profile = build_strategy_risk_profile_registry().resolve("trend_continuation")

    assert profile.version == "1"
    assert profile.stop_atr_multiple == Decimal("1.5")
    assert profile.target_atr_multiple == Decimal("3.0")
    assert profile.minimum_rr == Decimal("2.0")
    assert profile.trailing_atr_multiple == Decimal("1.5")
    assert profile.breakeven_trigger_r is None
    assert profile.maximum_holding_bars is None
    assert len(profile.config_hash) == 64


def test_regime_specific_profile_overrides_baseline_deterministically() -> None:
    registry = StrategyRiskProfileRegistry(
        (
            StrategyRiskProfile(
                strategy_id="compression_breakout",
                version="1",
                stop_atr_multiple=Decimal("1.5"),
                target_atr_multiple=Decimal("3.0"),
                minimum_rr=Decimal("2.0"),
                trailing_atr_multiple=Decimal("1.5"),
            ),
            StrategyRiskProfile(
                strategy_id="compression_breakout",
                version="2",
                regime="RANGE",
                stop_atr_multiple=Decimal("1.25"),
                target_atr_multiple=Decimal("3.25"),
                minimum_rr=Decimal("2.5"),
                breakeven_trigger_r=Decimal("1.0"),
                trailing_atr_multiple=Decimal("1.25"),
                maximum_holding_bars=6,
            ),
        )
    )

    first = registry.resolve("compression_breakout", regime="range")
    second = registry.resolve("compression_breakout", regime="RANGE")

    assert first == second
    assert first.version == "2"
    assert first.breakeven_trigger_r == Decimal("1.0")
    assert first.maximum_holding_bars == 6


def test_unknown_regime_falls_back_to_canonical_strategy_baseline() -> None:
    registry = build_strategy_risk_profile_registry()

    unknown = registry.resolve("trend_continuation", regime="UNKNOWN")
    baseline = registry.resolve("trend_continuation")

    assert unknown == baseline


def test_unknown_strategy_fails_closed() -> None:
    with pytest.raises(ValueError, match="not configured"):
        build_strategy_risk_profile_registry().resolve("nonexistent_strategy")

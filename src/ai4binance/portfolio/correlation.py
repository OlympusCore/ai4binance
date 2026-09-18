"""Proposal-only multi-symbol correlation and concentration diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt


@dataclass(frozen=True, slots=True)
class SymbolReturnSeries:
    symbol: str
    returns: tuple[float, ...]
    portfolio_weight: float

    def __post_init__(self) -> None:
        normalized = self.symbol.strip().upper()
        if not normalized.isascii() or not normalized.isalnum():
            raise ValueError("portfolio symbol is invalid")
        if not self.returns or any(not isfinite(item) for item in self.returns):
            raise ValueError("portfolio returns must be finite and non-empty")
        if not isfinite(self.portfolio_weight) or not 0 <= self.portfolio_weight <= 1:
            raise ValueError("portfolio weight must be between zero and one")
        object.__setattr__(self, "symbol", normalized)


@dataclass(frozen=True, slots=True)
class CorrelationPair:
    left_symbol: str
    right_symbol: str
    correlation: float


@dataclass(frozen=True, slots=True)
class PortfolioCorrelationReport:
    sample_size: int
    symbol_count: int
    pairs: tuple[CorrelationPair, ...]
    maximum_absolute_correlation: float
    concentration_hhi: float
    effective_asset_count: float
    correlated_exposure_weight: float
    blockers: tuple[str, ...]
    status: str = "RESEARCH_ONLY"
    execution_allowed: bool = False

    def __post_init__(self) -> None:
        if self.status != "RESEARCH_ONLY" or self.execution_allowed:
            raise ValueError("portfolio diagnostic cannot authorize execution")


def assess_portfolio_correlation(
    series: tuple[SymbolReturnSeries, ...],
    *,
    maximum_correlation: float = 0.80,
    maximum_correlated_weight: float = 0.70,
) -> PortfolioCorrelationReport:
    """Measure aligned-return correlation and correlated capital concentration."""
    if not series or len({item.symbol for item in series}) != len(series):
        raise ValueError("portfolio series must be unique and non-empty")
    sample_size = len(series[0].returns)
    if sample_size < 30 or any(len(item.returns) != sample_size for item in series):
        raise ValueError("portfolio correlation requires 30 aligned observations")
    if not 0 < maximum_correlation < 1 or not 0 < maximum_correlated_weight <= 1:
        raise ValueError("portfolio correlation policy is invalid")
    weight_sum = sum(item.portfolio_weight for item in series)
    if abs(weight_sum - 1.0) > 1e-9:
        raise ValueError("portfolio weights must sum to one")

    pairs: list[CorrelationPair] = []
    correlated_symbols: set[str] = set()
    for left_index, left in enumerate(series):
        for right in series[left_index + 1 :]:
            correlation = _pearson(left.returns, right.returns)
            pairs.append(CorrelationPair(left.symbol, right.symbol, correlation))
            if abs(correlation) >= maximum_correlation:
                correlated_symbols.update((left.symbol, right.symbol))
    maximum = max((abs(item.correlation) for item in pairs), default=1.0)
    hhi = sum(item.portfolio_weight**2 for item in series)
    effective_assets = 1.0 / hhi
    correlated_weight = sum(
        item.portfolio_weight for item in series if item.symbol in correlated_symbols
    )
    blockers: list[str] = []
    if len(series) < 2:
        blockers.append("MULTI_SYMBOL_EVIDENCE_UNAVAILABLE")
    if maximum >= maximum_correlation:
        blockers.append("PORTFOLIO_CORRELATION_CAP_EXCEEDED")
    if correlated_weight > maximum_correlated_weight:
        blockers.append("CORRELATED_EXPOSURE_CAP_EXCEEDED")
    return PortfolioCorrelationReport(
        sample_size=sample_size,
        symbol_count=len(series),
        pairs=tuple(pairs),
        maximum_absolute_correlation=maximum,
        concentration_hhi=hhi,
        effective_asset_count=effective_assets,
        correlated_exposure_weight=correlated_weight,
        blockers=tuple(blockers),
    )


def _pearson(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    covariance = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in right)
    denominator = sqrt(left_variance * right_variance)
    return covariance / denominator if denominator > 0 else 0.0

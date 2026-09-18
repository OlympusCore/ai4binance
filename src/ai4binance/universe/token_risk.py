"""Token risk filters for report-only opportunity scanning."""

from __future__ import annotations

from dataclasses import dataclass

from ai4binance.universe.filters import UniverseMarket, UniverseSymbol

_STABLE_BASE_ASSETS = frozenset(
    {"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "DAI", "USDP", "USDE"}
)
_LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S")
_WRAPPED_PREFIXES = ("W",)
_WRAPPED_BASES = frozenset({"WBTC", "WETH", "WBNB", "WSOL"})


@dataclass(frozen=True, slots=True)
class TokenRiskAssessment:
    symbol: str
    blockers: tuple[str, ...]
    execution_allowed: bool = False
    live_eligibility_status: str = "LIVE_ORDER_BLOCKED"

    @property
    def accepted(self) -> bool:
        return not self.blockers

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("token risk symbol is required")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("token risk blockers cannot be empty")
        if (
            self.execution_allowed
            or self.live_eligibility_status != "LIVE_ORDER_BLOCKED"
        ):
            raise ValueError("token risk assessment cannot authorize execution")


def assess_token_risk(symbol: UniverseSymbol) -> TokenRiskAssessment:
    """Reject scanner assets that are unsafe for generic Spot/Futures rotation."""
    blockers: list[str] = []
    base = symbol.base_asset.upper()
    if base in _STABLE_BASE_ASSETS:
        blockers.append("STABLECOIN_BASE_EXCLUDED")
    if base in _WRAPPED_BASES or (
        base.startswith(_WRAPPED_PREFIXES)
        and len(base) > 3
        and base[1:] in {"BTC", "ETH", "BNB"}
    ):
        blockers.append("WRAPPED_TOKEN_EXCLUDED")
    if (
        base.endswith(_LEVERAGED_SUFFIXES)
        and symbol.market is not UniverseMarket.USD_M_FUTURES
    ):
        blockers.append("LEVERAGED_TOKEN_EXCLUDED")
    return TokenRiskAssessment(symbol.symbol, tuple(dict.fromkeys(blockers)))

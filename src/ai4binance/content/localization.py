"""Localized phrases for bounded Turkish research-only content drafts."""

from __future__ import annotations

TR_RESEARCH_DISCLAIMER = "Arastirma amaclidir; islem sinyali degildir."

TR_PROFIT_PROMISE_PHRASES = (
    "garanti kazanç",
    "garantili kazanç",
    "kesin kazanç",
    "kesin yükselecek",
    "risksiz getiri",
)


def turkish_market_outlook_content(
    *,
    symbol: str,
    one_day_bias: str,
    four_hour_bias: str,
    one_hour_bias: str,
    regime: str,
    volatility: str,
    radar: str,
    rationale: str,
    disclaimer: str,
) -> str:
    return (
        f"{symbol} | Görünüm\n"
        f"1D:{one_day_bias} 4H:{four_hour_bias} 1H:{one_hour_bias}\n"
        f"Rejim: {regime} | Vol: {volatility}\n"
        f"Radar: {radar}\n"
        f"NO_TRADE: {rationale}\n"
        f"{disclaimer}"
    )

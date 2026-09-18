"""Localized strings for the Turkish read-only voice interface."""

from __future__ import annotations

from dataclasses import dataclass

# ruff: noqa: RUF001


TR_VOICE_WAKE_PHRASE = "asistan"

TR_VOICE_COMMAND_PHRASES = {
    "sistem durumu": "SYSTEM_STATUS",
    "spot görünümünü oku": "SPOT_OUTLOOK",
    "futures görünümünü oku": "FUTURES_OUTLOOK",
    "envanteri oku": "INVENTORY",
    "futures pozisyonlarını oku": "FUTURES_POSITIONS",
    "açık emirleri oku": "OPEN_ORDERS",
    "işlem engellerini oku": "BLOCKERS",
    "son raporu tekrarla": "REPEAT",
    "dinlemeyi durdur": "STOP_LISTENING",
    "mikrofonu kapat": "MUTE",
}


@dataclass(frozen=True, slots=True)
class TurkishVoiceMessages:
    repeat_unavailable: str = "Henüz okunmuş bir rapor yok."
    stop_listening: str = "Sesli asistan dinlemeyi durduruyor."
    mute: str = "Sesli raporlama sessize alındı."
    account_report_unavailable: str = "Read-only hesap raporu şu anda kullanılamıyor."
    none_value: str = "yok"
    speaker_verification_failed: str = "Speaker verification failed."
    local_session_failed: str = "Yerel ses oturumu doğrulanamadı."
    owner_verification_unavailable: str = "Kullanıcı ses doğrulaması yapılandırılmadı."
    owner_verification_failed: str = "Kullanıcı ses doğrulaması başarısız."
    wake_phrase_required: str = "Uyandırma ifadesi gerekli."
    intent_not_allowed: str = "Komut izin listesinde değil."
    voice_response_unavailable: str = "Voice response unavailable."

    def system_status(
        self,
        *,
        state: object,
        spot_wallet_status: object,
        futures_wallet_status: object,
        blockers: str,
    ) -> str:
        return (
            f"Sistem {state}. "
            f"Spot cüzdan {spot_wallet_status}. "
            f"Futures cüzdan {futures_wallet_status}. "
            f"Engeller: {blockers}. Canlı işlem kapalı."
        )

    def inventory(self, items: str) -> str:
        return f"Spot envanteri: {items}"

    def futures_positions(self, items: str) -> str:
        return f"Futures pozisyonları: {items}"

    def open_orders(self, items: str) -> str:
        return f"Açık emirler: {items}"

    def blockers(self, items: str) -> str:
        return f"İşlem engelleri: {items}"

    def inventory_item(self, *, asset: object, total: object) -> str:
        return f"{asset} toplam {total}"

    def futures_position_item(
        self,
        *,
        symbol: object,
        side: object,
        quantity: object,
        unrealized_pnl: object,
    ) -> str:
        return (
            f"{symbol} {side} miktar {quantity}, "
            f"gerçekleşmemiş kar zarar {unrealized_pnl}"
        )

    def open_order_item(
        self,
        *,
        market: object,
        symbol: object,
        side: object,
        status: object,
        remaining_quantity: object,
    ) -> str:
        return f"{market} {symbol} {side} durum {status}, kalan {remaining_quantity}"

    def market_outlook(
        self,
        *,
        label: str,
        action: object,
        bias: object,
        blockers: str,
    ) -> str:
        return (
            f"{label} önerisi {action}. "
            f"Yön {bias}. "
            f"Engeller {blockers}. Bu yalnız read-only öneridir."
        )


TR_VOICE_MESSAGES = TurkishVoiceMessages()

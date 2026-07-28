"""Configuration and audit serialization tests."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai4binance.config import Settings
from ai4binance.decision import build_no_trade_signal
from ai4binance.domain import Decision
from ai4binance.reporting import to_primitive


def test_settings_normalize_symbol_and_validate_timeframes() -> None:
    settings = Settings(
        symbol=" hotusdt ",
        validation_symbol=" btcusdt ",
        timeframes=("15m", "1h"),
    )
    assert settings.symbol == "HOTUSDT"
    assert settings.validation_symbol == "BTCUSDT"
    with pytest.raises(ValidationError, match="timeframes must be unique"):
        Settings(timeframes=("1h", "1h"))
    with pytest.raises(ValidationError, match="symbol cannot be empty"):
        Settings(symbol=" ")
    with pytest.raises(ValidationError, match="symbol cannot be empty"):
        Settings(validation_symbol=" ")
    with pytest.raises(ValidationError, match="non-empty"):
        Settings(timeframes=())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("public_api_base_url", "http://example.com", "credential-free HTTPS"),
        ("request_timeout_seconds", 0.0, "between 0.1 and 30"),
        ("request_max_attempts", 6, "between 1 and 5"),
        ("request_backoff_seconds", -1.0, "between 0 and 10"),
        ("candle_limit", 1, "between 2 and 1000"),
        ("minimum_closed_candles", 1, "at least 2"),
        ("max_data_workers", 9, "between 1 and 8"),
        ("accounting_collection_limit", 0, "between 1 and 1000"),
        ("accounting_freshness_minutes", 0, "between 1 and 1440"),
        ("runtime_cycle_interval_seconds", 4.0, "between 5 and 3600"),
        ("private_credentials_file", Path("other.env"), "Secrets/bnc.env"),
        ("portfolio_concentration_limit", "0", "concentration"),
        ("portfolio_maximum_gross_usdt", "0", "risk limits"),
        ("portfolio_maximum_symbol_usdt", "NaN", "finite number"),
        ("voice_capture_seconds", 0.5, "between 1 and 15"),
        ("voice_sample_rate", 44_100, "16000 or 48000"),
        ("voice_silence_rms", 0.0, "between zero and 0.2"),
        ("voice_report_interval_seconds", 30.0, "between 60 and 86400"),
        ("voice_tts_voice", "en-US-ZiraNeural", "Turkish Neural"),
        ("voice_state_max_bytes", 10, "outside the safe range"),
    ],
)
def test_settings_reject_unsafe_data_configuration(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**{field: value})  # type: ignore[arg-type]


def test_settings_reject_minimum_history_above_request_limit() -> None:
    with pytest.raises(ValidationError, match="cannot exceed candle_limit"):
        Settings(candle_limit=100, minimum_closed_candles=200)


def test_no_trade_factory_is_blocked_and_serializable() -> None:
    signal = build_no_trade_signal(symbol="HOTUSDT", timeframes=("1h",))
    payload = to_primitive(signal)
    assert isinstance(payload, dict)
    assert payload["decision_state"] == "NO_TRADE"
    assert payload["size_usdt"] == str(Decimal("0"))
    assert payload["blockers"] == ["ANALYSIS_NOT_AVAILABLE"]


def test_serializer_rejects_unknown_types() -> None:
    with pytest.raises(TypeError, match="unsupported audit value"):
        to_primitive(object())


def test_serializer_handles_audit_container_types() -> None:
    payload = to_primitive(
        {
            "decimal": Decimal("1.20"),
            "timestamp": datetime(2026, 7, 11, tzinfo=UTC),
            "state": Decision.NO_TRADE,
            "items": {"b", "a"},
        }
    )
    assert isinstance(payload, dict)
    assert payload["decimal"] == "1.20"
    assert payload["timestamp"] == "2026-07-11T00:00:00+00:00"
    assert payload["state"] == "NO_TRADE"
    assert sorted(payload["items"]) == ["a", "b"]

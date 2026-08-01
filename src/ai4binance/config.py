"""Environment-backed settings with capital-protection defaults."""

from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load non-secret runtime configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI4BINANCE_",
        extra="ignore",
    )

    exchange: Literal["Binance"] = "Binance"
    market_type: Literal["Spot"] = "Spot"
    symbol: str = "HOTUSDT"
    validation_symbol: str = "BTCUSDT"
    default_watch_symbol: str = "HOTUSDT"
    fixed_symbols: tuple[str, ...] = ()
    priority_watchlist: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ("15m", "1h", "4h", "1d")
    trading_mode: Literal["paper", "live"] = "paper"
    order_mode: Literal["manual", "dry_run", "paper", "auto", "live"] = "manual"
    allow_auto_live_orders: bool = False
    allow_auto_asset_conversion: bool = False
    allow_auto_wallet_transfer: bool = False
    allow_auto_position_close: bool = False
    prefer_no_trade: bool = True
    allow_short_spot: bool = False
    protected_assets: tuple[str, ...] = ()
    fee_reserve_assets: tuple[str, ...] = ("BNB",)
    preferred_quote_assets: tuple[str, ...] = ("USDT", "USDC")
    dust_value_threshold_usdt: Decimal = Decimal("5")
    public_api_base_url: str = "https://data-api.binance.vision"
    request_timeout_seconds: float = 10.0
    request_max_attempts: int = 3
    request_backoff_seconds: float = 0.25
    candle_limit: int = 250
    minimum_closed_candles: int = 200
    max_data_workers: int = 4
    audit_directory: Path = Path("Logs")
    dataset_directory: Path = Path("Data/market")
    validation_artifact_directory: Path = Path("Backtest/validation")
    evidence_artifact_directory: Path = Path("Artifacts")
    second_brain_index_path: Path = Path("State/second-brain-index.json")
    runtime_state_path: Path = Path("State/runtime.json")
    skill_discovery_state_path: Path = Path("State/skill-discovery.json")
    skill_discovery_ledger_path: Path = Path("Logs/skill_discovery_events.jsonl")
    skill_discovery_staging_directory: Path = Path("skill-staging/continuous-discovery")
    skill_discovery_interval_seconds: float = 3_600.0
    private_runtime_state_path: Path = Path("State/private/account-management.json")
    management_ledger_path: Path = Path("Logs/wallet_management_events.jsonl")
    manual_approval_queue_path: Path = Path("State/manual-approvals.jsonl")
    private_runtime_ledger_path: Path = Path(
        "State/private/account-management-events.jsonl"
    )
    binance_accounting_directory: Path = Path("State/private/binance-accounting")
    accounting_collection_limit: int = 100
    accounting_freshness_minutes: int = 30
    accounting_report_directory: Path = Path("Artifacts/accounting-ui")
    accounting_ws_event_limit: int = 100
    accounting_ws_collect_seconds: float = 30.0
    accounting_ws_receive_timeout_seconds: float = 5.0
    runtime_cycle_interval_seconds: float = 60.0
    private_credentials_file: Path = Path("Secrets/bnc.env")
    spot_ws_api_url: Literal[
        "wss://ws-api.binance.com:443/ws-api/v3",
        "wss://ws-api.testnet.binance.vision/ws-api/v3",
    ] = "wss://ws-api.binance.com:443/ws-api/v3"
    futures_private_ws_url: Literal["wss://fstream.binance.com/private"] = (
        "wss://fstream.binance.com/private"
    )
    ed25519_private_key_file: Path = Path("Secrets/binance_ed25519_private.pem")
    portfolio_concentration_limit: Decimal = Decimal("0.40")
    portfolio_maximum_gross_usdt: Decimal = Decimal("500")
    portfolio_maximum_symbol_usdt: Decimal = Decimal("250")
    portfolio_maximum_correlation_group_usdt: Decimal = Decimal("300")
    portfolio_maximum_strategy_usdt: Decimal = Decimal("250")
    voice_model_name: Literal["tiny", "base", "small"] = "small"
    voice_model_directory: Path = Path("Models/voice")
    voice_capture_seconds: float = 4.0
    voice_sample_rate: int = 16_000
    voice_silence_rms: float = 0.008
    voice_report_interval_seconds: float = 1_800.0
    voice_tts_voice: str = "tr-TR-EmelNeural"
    voice_state_max_bytes: int = 2_000_000

    @field_validator("symbol", "validation_symbol", "default_watch_symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize configured symbols while rejecting empty values."""
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol cannot be empty")
        return normalized

    @field_validator("fixed_symbols", "priority_watchlist")
    @classmethod
    def validate_symbol_tuple(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip().upper() for item in value))
        if any(not item or not item.isalnum() for item in normalized):
            raise ValueError("symbol lists must contain alphanumeric symbols")
        return normalized

    @field_validator(
        "protected_assets",
        "fee_reserve_assets",
        "preferred_quote_assets",
    )
    @classmethod
    def validate_asset_tuple(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip().upper() for item in value))
        if any(not item or not item.isalnum() for item in normalized):
            raise ValueError("asset lists must contain alphanumeric assets")
        return normalized

    @field_validator("dust_value_threshold_usdt")
    @classmethod
    def validate_dust_threshold(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value < Decimal("0"):
            raise ValueError(
                "dust_value_threshold_usdt must be finite and non-negative"
            )
        return value

    @field_validator("timeframes")
    @classmethod
    def validate_timeframes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Reject empty or duplicate timeframe configuration."""
        normalized = tuple(item.strip() for item in value)
        if not normalized or any(not item for item in normalized):
            raise ValueError("timeframes must contain non-empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("timeframes must be unique")
        return normalized

    @field_validator("public_api_base_url")
    @classmethod
    def validate_public_api_base_url(cls, value: str) -> str:
        """Require an HTTPS public endpoint without embedded credentials."""
        normalized = value.strip().rstrip("/")
        if not normalized.startswith("https://") or "@" in normalized:
            raise ValueError("public_api_base_url must be credential-free HTTPS")
        return normalized

    @field_validator("request_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if not 0.1 <= value <= 30.0:
            raise ValueError("request_timeout_seconds must be between 0.1 and 30")
        return value

    @field_validator("request_max_attempts")
    @classmethod
    def validate_attempts(cls, value: int) -> int:
        if not 1 <= value <= 5:
            raise ValueError("request_max_attempts must be between 1 and 5")
        return value

    @field_validator("request_backoff_seconds")
    @classmethod
    def validate_backoff(cls, value: float) -> float:
        if not 0.0 <= value <= 10.0:
            raise ValueError("request_backoff_seconds must be between 0 and 10")
        return value

    @field_validator("candle_limit")
    @classmethod
    def validate_candle_limit(cls, value: int) -> int:
        if not 2 <= value <= 1000:
            raise ValueError("candle_limit must be between 2 and 1000")
        return value

    @field_validator("minimum_closed_candles")
    @classmethod
    def validate_minimum_candles(cls, value: int) -> int:
        if value < 2:
            raise ValueError("minimum_closed_candles must be at least 2")
        return value

    @field_validator("max_data_workers")
    @classmethod
    def validate_data_workers(cls, value: int) -> int:
        if not 1 <= value <= 8:
            raise ValueError("max_data_workers must be between 1 and 8")
        return value

    @field_validator("accounting_collection_limit")
    @classmethod
    def validate_accounting_collection_limit(cls, value: int) -> int:
        if not 1 <= value <= 1_000:
            raise ValueError("accounting_collection_limit must be between 1 and 1000")
        return value

    @field_validator("accounting_freshness_minutes")
    @classmethod
    def validate_accounting_freshness_minutes(cls, value: int) -> int:
        if not 1 <= value <= 1_440:
            raise ValueError("accounting_freshness_minutes must be between 1 and 1440")
        return value

    @field_validator("accounting_ws_event_limit")
    @classmethod
    def validate_accounting_ws_event_limit(cls, value: int) -> int:
        if not 1 <= value <= 10_000:
            raise ValueError("accounting_ws_event_limit must be between 1 and 10000")
        return value

    @field_validator("accounting_ws_collect_seconds")
    @classmethod
    def validate_accounting_ws_collect_seconds(cls, value: float) -> float:
        if not 1.0 <= value <= 3_600.0:
            raise ValueError("accounting_ws_collect_seconds must be between 1 and 3600")
        return value

    @field_validator("accounting_ws_receive_timeout_seconds")
    @classmethod
    def validate_accounting_ws_receive_timeout_seconds(cls, value: float) -> float:
        if not 0.1 <= value <= 60.0:
            raise ValueError(
                "accounting_ws_receive_timeout_seconds must be between 0.1 and 60"
            )
        return value

    @field_validator("runtime_cycle_interval_seconds")
    @classmethod
    def validate_runtime_interval(cls, value: float) -> float:
        if not 5.0 <= value <= 3600.0:
            raise ValueError("runtime cycle interval must be between 5 and 3600")
        return value

    @field_validator("skill_discovery_interval_seconds")
    @classmethod
    def validate_skill_discovery_interval(cls, value: float) -> float:
        if not 300.0 <= value <= 86_400.0:
            raise ValueError("skill discovery interval must be between 300 and 86400")
        return value

    @field_validator("private_credentials_file")
    @classmethod
    def validate_private_credentials_file(cls, value: Path) -> Path:
        if value.is_absolute() or tuple(part.casefold() for part in value.parts) != (
            "secrets",
            "bnc.env",
        ):
            raise ValueError("private_credentials_file must be Secrets/bnc.env")
        return value

    @field_validator("ed25519_private_key_file")
    @classmethod
    def validate_ed25519_private_key_file(cls, value: Path) -> Path:
        if value.is_absolute() or tuple(part.casefold() for part in value.parts) != (
            "secrets",
            "binance_ed25519_private.pem",
        ):
            raise ValueError(
                "ed25519_private_key_file must be Secrets/binance_ed25519_private.pem"
            )
        return value

    @field_validator(
        "portfolio_maximum_gross_usdt",
        "portfolio_maximum_symbol_usdt",
        "portfolio_maximum_correlation_group_usdt",
        "portfolio_maximum_strategy_usdt",
    )
    @classmethod
    def validate_portfolio_limit(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("portfolio risk limits must be finite and positive")
        return value

    @field_validator("portfolio_concentration_limit")
    @classmethod
    def validate_concentration_limit(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or not Decimal("0") < value <= Decimal("1"):
            raise ValueError(
                "portfolio concentration limit must be between zero and one"
            )
        return value

    @field_validator("voice_capture_seconds")
    @classmethod
    def validate_voice_capture_seconds(cls, value: float) -> float:
        if not 1.0 <= value <= 15.0:
            raise ValueError("voice_capture_seconds must be between 1 and 15")
        return value

    @field_validator("voice_sample_rate")
    @classmethod
    def validate_voice_sample_rate(cls, value: int) -> int:
        if value not in {16_000, 48_000}:
            raise ValueError("voice_sample_rate must be 16000 or 48000")
        return value

    @field_validator("voice_silence_rms")
    @classmethod
    def validate_voice_silence_rms(cls, value: float) -> float:
        if not 0.0 < value <= 0.2:
            raise ValueError("voice_silence_rms must be between zero and 0.2")
        return value

    @field_validator("voice_report_interval_seconds")
    @classmethod
    def validate_voice_report_interval(cls, value: float) -> float:
        if not 60.0 <= value <= 86_400.0:
            raise ValueError("voice report interval must be between 60 and 86400")
        return value

    @field_validator("voice_tts_voice")
    @classmethod
    def validate_voice_tts_voice(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("tr-TR-") or not normalized.endswith("Neural"):
            raise ValueError("voice_tts_voice must be a Turkish Neural voice")
        return normalized

    @field_validator("voice_state_max_bytes")
    @classmethod
    def validate_voice_state_max_bytes(cls, value: int) -> int:
        if not 1_024 <= value <= 5_000_000:
            raise ValueError("voice_state_max_bytes is outside the safe range")
        return value

    @model_validator(mode="after")
    def validate_candle_window(self) -> Self:
        if self.minimum_closed_candles > self.candle_limit:
            raise ValueError("minimum_closed_candles cannot exceed candle_limit")
        if not self.preferred_quote_assets:
            raise ValueError("preferred_quote_assets must not be empty")
        if self.allow_auto_live_orders and (
            self.allow_auto_asset_conversion
            or self.allow_auto_wallet_transfer
            or self.allow_auto_position_close
        ):
            raise ValueError("automatic asset actions require a separate live approval")
        return self

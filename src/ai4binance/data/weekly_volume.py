"""Frozen public weekly quote-notional selection for acquisition only."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast

from ai4binance.core.errors import ExchangeError, ExchangeRateLimitError
from ai4binance.data.acquisition_profile import (
    SAFE_STATE,
    completed_boundary,
    content_digest,
    exact_quote_volume,
    sum_decimal_strings,
    validate_native_rows,
)
from ai4binance.data.market_history_sync import BinanceVisionArchiveCache
from ai4binance.domain.universe import classify_asset_eligibility
from ai4binance.infrastructure.persistence.safe_json import write_json_object_verified
from ai4binance.integrations.binance.market_universe_provider import PublicJsonTransport


def active_shared_circuit(root: Path, market: str, now: datetime) -> dict[str, object]:
    """Honor one persisted public-source cooldown across profile operations."""
    circuit = load_evidence(root / "retry" / f"{market}-circuit.json")
    if circuit and now < datetime.fromisoformat(str(circuit["next_retry_at"])):
        return circuit
    return {}


def record_shared_cooldown(
    root: Path, market: str, error: ExchangeRateLimitError
) -> None:
    """Start a typed exchange cooldown at response receipt, not pass start."""
    now = datetime.now(UTC)
    delay = error.retry_after_seconds or (86400 if error.status_code == 418 else 900)
    save_evidence(
        root / "retry" / f"{market}-circuit.json",
        {
            "observed_at": now.isoformat(),
            "next_retry_at": (now + timedelta(seconds=delay)).isoformat(),
            "scope": market,
            "status": "DEGRADED_WAIT",
            **SAFE_STATE,
        },
    )


def record_public_response(root: Path, url: str, payload: bytes) -> None:
    """Retain real GET response bytes and a local integrity receipt."""
    digest = sha256(payload).hexdigest()
    raw_path = root / "raw" / f"{digest}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if not raw_path.exists():
        BinanceVisionArchiveCache._atomic_write(raw_path, payload)
    if sha256(raw_path.read_bytes()).hexdigest() != digest:
        raise ValueError("raw public response integrity failed")
    save_evidence(
        root / "responses" / f"{sha256(url.encode()).hexdigest()}.json",
        {
            "source_url": url,
            "observed_at": datetime.now(UTC).isoformat(),
            "raw_path": str(raw_path),
            "raw_response_sha256": digest,
            "hash_scope": "LOCAL_RESPONSE_INTEGRITY_NOT_BINANCE_CHECKSUM",
            "parser_version": "TOP5_NATIVE_KLINE_V1",
            **SAFE_STATE,
        },
    )


def save_evidence(path: Path, payload: Mapping[str, object]) -> None:
    write_json_object_verified(
        path, payload, blocker="TOP5_EVIDENCE_WRITE_FAILED", indent=2
    )


def load_evidence(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 16_000_000:
        raise ValueError("profile evidence exceeds its boundary")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("profile evidence must be an object")
    return cast(dict[str, object], payload)


def candidate_inventory(
    spot: Mapping[str, object],
    futures: Mapping[str, object],
    *,
    futures_exclusions: tuple[str, ...] = (),
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Match exact official base identities; never strip a scaled contract prefix."""
    spot_by_asset = _active_listings(spot, "spot")
    future_by_asset = _active_listings(futures, "usd_m_futures")
    candidates: list[dict[str, object]] = []
    exclusions: list[dict[str, object]] = []
    for asset in sorted(spot_by_asset.keys() | future_by_asset.keys()):
        left, right = spot_by_asset.get(asset, []), future_by_asset.get(asset, [])
        reasons = list(
            classify_asset_eligibility(
                asset,
                spot_symbols=tuple(str(row["symbol"]) for row in left),
                futures_symbols=tuple(str(row["symbol"]) for row in right),
            ).exclusion_reasons
        )
        if not left or not right:
            reasons.append("NO_VERIFIED_COMMON_BASE_IDENTITY_OR_MAPPING")
        if len(left) > 1 or len(right) > 1:
            reasons.append("AMBIGUOUS_CONTRACT_IDENTITY")
        if right and str(right[0]["symbol"]) in futures_exclusions:
            reasons.append("CANONICAL_FUTURES_SYMBOL_EXCLUSION")
        if reasons:
            exclusions.append(
                {
                    "asset_id": asset,
                    "reasons": reasons,
                    "spot_symbols": [row["symbol"] for row in left],
                    "futures_symbols": [row["symbol"] for row in right],
                }
            )
        else:
            candidates.append(
                {
                    "asset_id": asset,
                    "spot_symbol": left[0]["symbol"],
                    "futures_symbol": right[0]["symbol"],
                    "futures_onboard_ms": right[0].get("onboardDate"),
                    "mapping_provenance": "EXACT_OFFICIAL_BASE_ASSET_IDENTITY",
                    "contract_multiplier": "1",
                }
            )
    return candidates, exclusions


def _active_listings(
    metadata: Mapping[str, object], market: str
) -> dict[str, list[dict[str, object]]]:
    rows = metadata.get("symbols")
    if not isinstance(rows, list) or not rows:
        raise ValueError("official exchange metadata is incomplete")
    result: dict[str, list[dict[str, object]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not isinstance(raw.get("baseAsset"), str):
            raise ValueError("official symbol metadata is malformed")
        if raw.get("status") != "TRADING" or raw.get("quoteAsset") != "USDT":
            continue
        if market != "spot" and (
            raw.get("contractType") != "PERPETUAL" or raw.get("marginAsset") != "USDT"
        ):
            continue
        if market == "spot" and raw.get("isSpotTradingAllowed") is not True:
            continue
        symbol = raw.get("symbol")
        asset = raw["baseAsset"]
        if (
            not isinstance(symbol, str)
            or not symbol.isalnum()
            or symbol != symbol.upper()
            or not 2 <= len(symbol) <= 24
            or not asset.isalnum()
            or asset != asset.upper()
        ):
            raise ValueError("official symbol identity is unsafe or malformed")
        result.setdefault(raw["baseAsset"], []).append(raw)
    return result


@dataclass(frozen=True, slots=True)
class ScopedRetryPolicy:
    """Persist retry reservations before requests so restart cannot erase budgets."""

    attempts_per_episode: int = 3
    attempts_per_hour: int = 6
    cooldown_seconds: int = 900
    maximum_backoff_seconds: int = 3600

    def __post_init__(self) -> None:
        if (
            not 1 <= self.attempts_per_episode <= 3
            or not self.attempts_per_episode <= self.attempts_per_hour <= 12
        ):
            raise ValueError("profile retry budget is invalid")
        if not 60 <= self.cooldown_seconds <= self.maximum_backoff_seconds <= 86400:
            raise ValueError("profile retry cooldown is invalid")

    def reserve(self, path: Path, now: datetime) -> bool:
        state = load_evidence(path)
        stamps = [
            datetime.fromisoformat(str(value))
            for value in cast(list[object], state.get("attempts", []))
        ]
        stamps = [stamp for stamp in stamps if now - timedelta(hours=1) < stamp]
        due = datetime.fromisoformat(str(state.get("next_retry_at", now.isoformat())))
        if now < due or len(stamps) >= self.attempts_per_hour:
            return False
        episode = int(str(state.get("episode_attempts", 0)))
        if episode >= self.attempts_per_episode:
            episode = 0
        episode += 1
        delay = min(self.maximum_backoff_seconds, 30 * 2 ** (episode - 1))
        if episode >= self.attempts_per_episode:
            delay = max(delay, self.cooldown_seconds)
        save_evidence(
            path,
            {
                **state,
                "attempts": [stamp.isoformat() for stamp in stamps] + [now.isoformat()],
                "episode_attempts": episode,
                "next_retry_at": (now + timedelta(seconds=delay)).isoformat(),
                "status": "ATTEMPT_RESERVED",
                **SAFE_STATE,
            },
        )
        return True

    def succeed(
        self, path: Path, now: datetime, *, useful_progress: bool = True
    ) -> None:
        state = load_evidence(path)
        attempts = cast(list[object], state.get("attempts", []))
        if not attempts:
            raise ValueError("successful retry completion requires a reservation")
        save_evidence(
            path,
            {
                **state,
                # Release this completed reservation; retain prior failures.
                "attempts": attempts[:-1],
                "episode_attempts": 0,
                "next_retry_at": now.isoformat(),
                "status": "PROGRESS" if useful_progress else "CURRENT",
                "last_useful_update": now.isoformat()
                if useful_progress
                else state.get("last_useful_update"),
                **SAFE_STATE,
            },
        )


@dataclass(frozen=True, slots=True)
class WeeklyVolumeRanking:
    """One bounded ranking pass; incomplete candidates remain explicit blockers."""

    spot: PublicJsonTransport
    futures: PublicJsonTransport
    evidence_root: Path
    retry_policy: ScopedRetryPolicy = ScopedRetryPolicy()
    futures_exclusions: tuple[str, ...] = ()

    def run(self, *, cutoff: datetime) -> dict[str, object]:
        now = datetime.now(UTC)
        end = completed_boundary(cutoff, "1h")
        start = end - timedelta(hours=168)
        metadata = self._metadata(now)
        if "blockers" in metadata:
            return metadata
        spot_info = cast(Mapping[str, object], metadata["spot"])
        futures_info = cast(Mapping[str, object], metadata["usd_m_futures"])
        candidates, exclusions = candidate_inventory(
            spot_info, futures_info, futures_exclusions=self.futures_exclusions
        )
        rows = [self._candidate(candidate, start, end, now) for candidate in candidates]
        verified = [row for row in rows if row["status"] == "VERIFIED"]
        verified.sort(
            key=lambda row: (
                Decimal(str(row["weekly_combined_quote_volume"])).copy_negate(),
                str(row["asset_id"]),
            )
        )
        blocked = [
            str(row["asset_id"]) for row in rows if row["status"] == "NOT_VERIFIED"
        ]
        status = "VERIFIED" if not blocked and len(verified) >= 5 else "NOT_VERIFIED"
        body: dict[str, object] = {
            "schema_version": "1.0",
            "status": status,
            "scope": "OFFICIAL_COMMON_USDT_SPOT_PERPETUAL_EXACT_IDENTITIES",
            "mapping_limit": "SCALED_OR_ALIASED_IDENTITIES_REQUIRE_REGISTERED_MAPPING",
            "ranking_start_utc": start.isoformat(),
            "ranking_end_utc": end.isoformat(),
            "observed_at": now.isoformat(),
            "metadata": {
                market: content_digest(metadata[market])
                for market in ("spot", "usd_m_futures")
            },
            "candidate_count": len(candidates),
            "candidates": rows,
            "excluded_assets": exclusions,
            "unverified_assets": blocked,
            "diagnostic_top5": verified[:5],
            "selected": verified[:5] if status == "VERIFIED" else [],
            "blockers": ["RANKING_COVERAGE_NOT_VERIFIED"]
            if blocked
            else ["FEWER_THAN_FIVE_VERIFIED_ELIGIBLE_ASSETS"]
            if len(verified) < 5
            else [],
            **SAFE_STATE,
        }
        body["selection_version"] = content_digest(
            {key: value for key, value in body.items() if key != "observed_at"}
        )
        save_evidence(
            self.evidence_root / "rankings" / f"{body['selection_version']}.json", body
        )
        save_evidence(self.evidence_root / "ranking-latest.json", body)
        if status == "VERIFIED":
            save_evidence(self.evidence_root / "selection-active.json", body)
        return body

    def _metadata(self, now: datetime) -> dict[str, object]:
        result: dict[str, object] = {}
        for market, transport, prefix in (
            ("spot", self.spot, "/api/v3/"),
            ("usd_m_futures", self.futures, "/fapi/v1/"),
        ):
            path = self.evidence_root / "metadata" / f"{market}.json"
            try:
                if active_shared_circuit(self.evidence_root, market, now):
                    raise ValueError("SHARED_SOURCE_COOLDOWN")
                retry_path = self.evidence_root / "retry" / f"{market}-metadata.json"
                if not self.retry_policy.reserve(retry_path, now):
                    raise ValueError("METADATA_RETRY_DEFERRED")
                payload = transport.get_json(
                    prefix + "exchangeInfo",
                    {"symbolStatus": "TRADING", "showPermissionSets": "false"}
                    if market == "spot"
                    else None,
                )
                if not isinstance(payload, dict):
                    raise ValueError("official metadata must be an object")
                save_evidence(
                    path,
                    {
                        "observed_at": now.isoformat(),
                        "source": prefix + "exchangeInfo",
                        "payload": payload,
                        "decoded_payload_sha256": content_digest(payload),
                        **SAFE_STATE,
                    },
                )
                result[market] = payload
                self.retry_policy.succeed(retry_path, now)
            except (ExchangeError, ValueError) as error:
                if isinstance(error, ExchangeRateLimitError):
                    record_shared_cooldown(self.evidence_root, market, error)
                cast(list[str], result.setdefault("blockers", [])).append(
                    f"{market}:METADATA_UNAVAILABLE:{type(error).__name__}"
                )
        if "blockers" in result:
            result = {
                "status": "NOT_VERIFIED",
                "selected": [],
                "blockers": result["blockers"],
                **SAFE_STATE,
            }
            save_evidence(self.evidence_root / "ranking-latest.json", result)
        return result

    def _candidate(
        self,
        candidate: dict[str, object],
        start: datetime,
        end: datetime,
        now: datetime,
    ) -> dict[str, object]:
        onboard = candidate.get("futures_onboard_ms")
        if isinstance(onboard, int) and onboard > int(start.timestamp() * 1000):
            return {
                **candidate,
                "status": "INELIGIBLE",
                "reason": "FULL_WEEK_LISTING_HISTORY_UNAVAILABLE",
            }
        volumes: dict[str, object] = {}
        for market, transport, prefix, symbol_key in (
            ("spot", self.spot, "/api/v3/", "spot_symbol"),
            ("usd_m_futures", self.futures, "/fapi/v1/", "futures_symbol"),
        ):
            symbol = str(candidate[symbol_key])
            key = f"{market}-{symbol}-{int(end.timestamp())}"
            try:
                rows, digest = self._ranking_rows(
                    key, transport, prefix, symbol, start, end, now
                )
                volumes[market] = {
                    "quote_volume": exact_quote_volume(rows, start, end),
                    "source_evidence_sha256": digest,
                    "actual_bars": len(rows),
                }
            except (ExchangeError, ValueError) as error:
                volumes[market] = {
                    "status": "NOT_VERIFIED",
                    "reason": type(error).__name__,
                }
        if any(
            "quote_volume" not in cast(dict[str, object], value)
            for value in volumes.values()
        ):
            return {**candidate, "status": "NOT_VERIFIED", "markets": volumes}
        left = str(cast(dict[str, object], volumes["spot"])["quote_volume"])
        right = str(cast(dict[str, object], volumes["usd_m_futures"])["quote_volume"])
        return {
            **candidate,
            "status": "VERIFIED",
            "weekly_spot_quote_volume": left,
            "weekly_futures_quote_volume": right,
            "weekly_combined_quote_volume": sum_decimal_strings([left, right]),
            "markets": volumes,
        }

    def _ranking_rows(
        self,
        key: str,
        transport: PublicJsonTransport,
        prefix: str,
        symbol: str,
        start: datetime,
        end: datetime,
        now: datetime,
    ) -> tuple[list[list[str]], str]:
        path = self.evidence_root / "ranking-bars" / f"{key}.json"
        cached = load_evidence(path)
        if cached:
            if (
                content_digest(cached["rows"]) != cached["decoded_rows_sha256"]
                or cached.get("symbol") != symbol
                or cached.get("start") != start.isoformat()
                or cached.get("end") != end.isoformat()
            ):
                raise ValueError("ranking evidence binding mismatch")
            return validate_native_rows(
                cached["rows"], start=start, end=end, timeframe="1h"
            ), content_digest(cached)
        retry_path = self.evidence_root / "retry" / f"{key}.json"
        market = "spot" if prefix == "/api/v3/" else "usd_m_futures"
        if active_shared_circuit(self.evidence_root, market, now):
            raise ValueError("SHARED_SOURCE_COOLDOWN")
        if not self.retry_policy.reserve(retry_path, now):
            raise ValueError("SCOPED_RETRY_DEFERRED")
        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": "1h",
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000) - 1,
            "limit": 168,
        }
        try:
            raw = transport.get_json(prefix + "klines", params)
        except ExchangeRateLimitError as error:
            record_shared_cooldown(self.evidence_root, market, error)
            raise
        rows = validate_native_rows(raw, start=start, end=end, timeframe="1h")
        exact_quote_volume(rows, start, end)
        packet: dict[str, object] = {
            "source": prefix + "klines",
            "symbol": symbol,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rows": rows,
            "decoded_rows_sha256": content_digest(rows),
            "hash_scope": "LOCAL_DECODED_JSON_NOT_EXCHANGE_CHECKSUM",
            "observed_at": now.isoformat(),
            **SAFE_STATE,
        }
        save_evidence(path, packet)
        self.retry_policy.succeed(retry_path, now)
        return rows, content_digest(packet)

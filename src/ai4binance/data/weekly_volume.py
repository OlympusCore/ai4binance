"""Frozen public weekly quote-notional selection for acquisition only."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast
from urllib.parse import urlencode

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
    alias = root / "responses" / f"{sha256(url.encode()).hexdigest()}.json"
    previous = load_evidence(alias)
    if previous:
        _retain_response_receipt(root, previous)
    receipt: dict[str, object] = {
        "source_url": url,
        "observed_at": datetime.now(UTC).isoformat(),
        "raw_path": str(raw_path),
        "raw_response_sha256": digest,
        "hash_scope": "LOCAL_RESPONSE_INTEGRITY_NOT_BINANCE_CHECKSUM",
        "parser_version": "TOP5_NATIVE_KLINE_V1",
        **SAFE_STATE,
    }
    _retain_response_receipt(root, receipt)
    save_evidence(alias, receipt)


def _retain_response_receipt(root: Path, receipt: Mapping[str, object]) -> None:
    digest = content_digest(receipt)
    path = root / "responses" / "history" / f"{digest}.json"
    if path.exists():
        if content_digest(load_evidence(path)) != digest:
            raise ValueError("immutable public response receipt integrity failed")
        return
    save_evidence(path, receipt)


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


def _verify_reconstructed_packet(
    root: Path,
    packet: Mapping[str, object],
    market: str,
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[list[str]]:
    body = {key: value for key, value in packet.items() if key != "content_sha256"}
    if (
        content_digest(body) != packet.get("content_sha256")
        or packet.get("market") != market
        or packet.get("symbol") != symbol
        or packet.get("start") != start.isoformat()
        or packet.get("end") != end.isoformat()
    ):
        raise ValueError("reconstructed packet binding mismatch")
    rows = validate_native_rows(packet["rows"], start=start, end=end, timeframe="1h")
    exact_quote_volume(rows, start, end)
    digest = str(packet["raw_response_sha256"])
    if len(digest) != 64 or any(value not in "0123456789abcdef" for value in digest):
        raise ValueError("reconstructed raw digest is invalid")
    raw_path = root / "raw" / f"{digest}.json"
    if raw_path.is_symlink():
        raise ValueError("reconstructed raw response cannot be a symlink")
    raw = raw_path.read_bytes()
    receipt = cast(Mapping[str, object], packet["receipt"])
    params = {
        "symbol": symbol,
        "interval": "1h",
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000) - 1,
        "limit": 168,
    }
    prefix = (
        "https://api.binance.com/api/v3/"
        if market == "spot"
        else "https://fapi.binance.com/fapi/v1/"
    )
    if (
        sha256(raw).hexdigest() != digest
        or receipt.get("raw_response_sha256") != digest
        or receipt.get("source_url")
        != prefix + "klines?" + urlencode(sorted(params.items()))
        or content_digest(rows) != packet["decoded_rows_sha256"]
        or validate_native_rows(json.loads(raw), start=start, end=end, timeframe="1h")
        != rows
    ):
        raise ValueError("reconstructed raw source receipt integrity failed")
    if (
        datetime.fromisoformat(str(receipt["observed_at"])).utcoffset() is None
        or datetime.fromisoformat(str(packet["recovered_at"])).utcoffset() is None
    ):
        raise ValueError("reconstruction receipt timestamps must be aware")
    if packet.get("recovery_mode") == "RECOVERED_ORIGINAL_HASH_BOUND_PACKET":
        original = cast(Mapping[str, object], packet["original_packet"])
        if (
            content_digest(original) != packet["original_expected_packet_sha256"]
            or original.get("rows") != rows
        ):
            raise ValueError("recovered original packet integrity failed")
    elif packet.get("recovery_mode") != "LATER_RETRIEVAL_NOT_PIT_AT_ORIGINAL_CUTOFF":
        raise ValueError("reconstruction recovery mode is invalid")
    return rows


def verify_frozen_reconstruction(
    root: Path, manifest: Mapping[str, object]
) -> dict[str, object]:
    """Reload and order every declared candidate without network access."""
    body = {key: value for key, value in manifest.items() if key != "evidence_revision"}
    if (
        content_digest(body) != manifest.get("evidence_revision")
        or manifest.get("status") != "RECONSTRUCTED"
        or manifest.get("failures")
    ):
        raise ValueError("full reconstructed manifest is required")
    original = load_evidence(root / "original-selection.json")
    original_body = {
        key: value
        for key, value in original.items()
        if key not in {"selection_version", "observed_at"}
    }
    if (
        content_digest(original_body) != original.get("selection_version")
        or original.get("selection_version") != manifest["original_selection_version"]
    ):
        raise ValueError("original selection binding failed")
    start, end = (
        datetime.fromisoformat(str(original[key]))
        for key in ("ranking_start_utc", "ranking_end_utc")
    )
    metadata = cast(Mapping[str, object], original["metadata"])
    for market in ("spot", "usd_m_futures"):
        if (
            content_digest(
                load_evidence(root / "metadata" / f"{market}.json").get("payload")
            )
            != metadata[market]
        ):
            raise ValueError("durable original metadata integrity failed")
    references = cast(list[dict[str, object]], manifest["packet_references"])
    by_identity = {
        (str(ref["asset_id"]), str(ref["market"])): ref for ref in references
    }
    if len(by_identity) != len(references):
        raise ValueError("reconstruction contains duplicate references")
    ranking: list[dict[str, object]] = []
    expected_keys: set[tuple[str, str]] = set()
    recovered = 0
    for candidate in cast(list[dict[str, object]], original["candidates"]):
        if candidate["status"] == "INELIGIBLE":
            continue
        result, original_count = _recompute_candidate(
            root, candidate, by_identity, start, end
        )
        ranking.append(result)
        recovered += original_count
        expected_keys.update(
            (str(candidate["asset_id"]), market) for market in ("spot", "usd_m_futures")
        )
    if set(by_identity) != expected_keys or len(ranking) < 5:
        raise ValueError("reconstruction does not cover exactly its declared universe")
    ranking.sort(
        key=lambda row: (
            Decimal(str(row["weekly_combined_quote_volume"])).copy_negate(),
            str(row["asset_id"]),
        )
    )
    return {
        "status": "VERIFIED_FULL_RECONSTRUCTION",
        "original_selection_version": original["selection_version"],
        "evidence_revision": manifest["evidence_revision"],
        "recomputed_candidates": ranking,
        "verified_packet_count": len(references),
        "original_packets_recovered": recovered,
        "later_retrieved_packets": len(references) - recovered,
        "top5_matches_original": [row["asset_id"] for row in ranking[:5]]
        == [
            row["asset_id"]
            for row in cast(list[dict[str, object]], original["selected"])
        ],
        "historical_availability": "ORIGINAL_AND_LATER_RETRIEVALS_REMAIN_DISTINCT",
        "selection_activation": "NOT_APPLIED",
        **SAFE_STATE,
    }


def _recompute_candidate(
    root: Path,
    candidate: Mapping[str, object],
    by_identity: Mapping[tuple[str, str], dict[str, object]],
    start: datetime,
    end: datetime,
) -> tuple[dict[str, object], int]:
    recovered = 0
    volumes: list[str] = []
    for market, symbol_key in (
        ("spot", "spot_symbol"),
        ("usd_m_futures", "futures_symbol"),
    ):
        identity = (str(candidate["asset_id"]), market)

        if identity not in by_identity:
            raise ValueError("reconstruction is missing declared candidate evidence")
        reference = by_identity[identity]
        relative = Path(str(reference["path"]))
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not relative.parts
            or relative.parts[0] != "packets"
        ):
            raise ValueError("reconstruction reference escapes durable packets")
        packet = load_evidence(root / relative)
        if packet.get("content_sha256") != reference["content_sha256"]:
            raise ValueError("reconstruction reference integrity failed")
        rows = _verify_reconstructed_packet(
            root, packet, market, str(candidate[symbol_key]), start, end
        )
        expected = cast(Mapping[str, Mapping[str, object]], candidate["markets"])[
            market
        ]["source_evidence_sha256"]
        if packet["original_expected_packet_sha256"] != expected:
            raise ValueError("reconstruction original packet reference changed")
        volumes.append(exact_quote_volume(rows, start, end))
        recovered += packet["recovery_mode"] == "RECOVERED_ORIGINAL_HASH_BOUND_PACKET"
    result = {
        "asset_id": candidate["asset_id"],
        "weekly_spot_quote_volume": volumes[0],
        "weekly_futures_quote_volume": volumes[1],
        "weekly_combined_quote_volume": sum_decimal_strings(volumes),
    }
    return result, recovered


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

    def reconstruct_frozen(
        self, frozen: Mapping[str, object], destination: Path
    ) -> dict[str, object]:
        """Restore the historical interval without replacing active selection."""
        version = str(frozen.get("selection_version", ""))
        root, start, end, declared = self._reconstruction_context(frozen, destination)
        references: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        for candidate in declared:
            if candidate["status"] == "INELIGIBLE":
                continue
            for market, transport, prefix, symbol_key in (
                ("spot", self.spot, "/api/v3/", "spot_symbol"),
                ("usd_m_futures", self.futures, "/fapi/v1/", "futures_symbol"),
            ):
                symbol = str(candidate[symbol_key])
                key = f"{market}-{symbol}-{int(end.timestamp())}"
                path = root / "packets" / f"{key}.json"
                try:
                    packet = self._reconstruct_packet(
                        root, candidate, market, transport, prefix, symbol, start, end
                    )
                    references.append(
                        {
                            "asset_id": candidate["asset_id"],
                            "market": market,
                            "symbol": symbol,
                            "path": path.relative_to(root).as_posix(),
                            "content_sha256": packet["content_sha256"],
                        }
                    )
                except (ExchangeError, OSError, ValueError, ArithmeticError) as error:
                    if isinstance(error, OSError) and error.errno in {13, 28, 30}:
                        raise
                    failures.append(
                        {
                            "asset_id": candidate["asset_id"],
                            "market": market,
                            "reason": type(error).__name__,
                        }
                    )
                save_evidence(
                    root / "progress.json",
                    {
                        "original_selection_version": version,
                        "completed_packets": len(references),
                        "failures": failures,
                        "observed_at": datetime.now(UTC).isoformat(),
                        **SAFE_STATE,
                    },
                )
        manifest: dict[str, object] = {
            "original_selection_version": version,
            "status": "NOT_VERIFIED" if failures else "RECONSTRUCTED",
            "ranking_start_utc": start.isoformat(),
            "ranking_end_utc": end.isoformat(),
            "packet_references": references,
            "failures": failures,
            "observed_at": datetime.now(UTC).isoformat(),
            "retention": "DURABLE_NO_AUTOMATIC_CLEANUP_OWNER_REVIEW_REQUIRED",
            "selection_activation": "NOT_APPLIED",
            **SAFE_STATE,
        }
        manifest["evidence_revision"] = content_digest(manifest)
        save_evidence(
            root / "revisions" / f"{manifest['evidence_revision']}.json", manifest
        )
        if not failures:
            result = verify_frozen_reconstruction(root, manifest)
            save_evidence(root / "verification-latest.json", result)
            return {**manifest, "verification": result}
        return manifest

    def _reconstruction_context(
        self, frozen: Mapping[str, object], destination: Path
    ) -> tuple[Path, datetime, datetime, list[dict[str, object]]]:
        version = str(frozen.get("selection_version", ""))
        body = {
            key: value
            for key, value in frozen.items()
            if key not in {"observed_at", "selection_version"}
        }
        if frozen.get("status") != "VERIFIED" or content_digest(body) != version:
            raise ValueError("frozen ranking manifest integrity failed")
        start, end = (
            datetime.fromisoformat(str(frozen[key]))
            for key in ("ranking_start_utc", "ranking_end_utc")
        )
        if end - start != timedelta(hours=168) or completed_boundary(end, "1h") != end:
            raise ValueError("frozen ranking interval is invalid")
        root = destination / version
        original_path = root / "original-selection.json"
        if original_path.exists() and content_digest(
            load_evidence(original_path)
        ) != content_digest(frozen):
            raise ValueError("reconstruction original manifest changed")
        if not original_path.exists():
            save_evidence(original_path, frozen)
        metadata: dict[str, Mapping[str, object]] = {}
        expected_metadata = cast(Mapping[str, object], frozen["metadata"])
        for market in ("spot", "usd_m_futures"):
            packet = load_evidence(self.evidence_root / "metadata" / f"{market}.json")
            if content_digest(packet.get("payload")) != expected_metadata[market]:
                raise ValueError("original identity metadata is missing or changed")
            metadata[market] = cast(Mapping[str, object], packet["payload"])
            save_evidence(root / "metadata" / f"{market}.json", packet)
        inventory, _ = candidate_inventory(
            metadata["spot"],
            metadata["usd_m_futures"],
            futures_exclusions=self.futures_exclusions,
        )
        declared = cast(list[dict[str, object]], frozen["candidates"])

        def identities(items: list[dict[str, object]]) -> list[tuple[str, str, str]]:
            return sorted(
                (
                    str(item["asset_id"]),
                    str(item["spot_symbol"]),
                    str(item["futures_symbol"]),
                )
                for item in items
            )

        if (
            identities(inventory) != identities(declared)
            or len(declared) != frozen["candidate_count"]
        ):
            raise ValueError(
                "frozen candidate identities disagree with original metadata"
            )
        return root, start, end, declared

    def _retrieve_reconstruction_wire(
        self,
        key: str,
        market: str,
        transport: PublicJsonTransport,
        prefix: str,
        params: dict[str, str | int],
        url: str,
        start: datetime,
        end: datetime,
    ) -> tuple[list[list[str]], bytes, dict[str, object]]:
        now = datetime.now(UTC)
        retry_path = self.evidence_root / "retry" / f"reconstruction-{key}.json"
        if active_shared_circuit(
            self.evidence_root, market, now
        ) or not self.retry_policy.reserve(retry_path, now):
            raise ValueError("RECONSTRUCTION_RETRY_DEFERRED")
        try:
            payload = transport.get_json(prefix + "klines", params)
        except ExchangeRateLimitError as error:
            record_shared_cooldown(self.evidence_root, market, error)
            raise
        rows = validate_native_rows(payload, start=start, end=end, timeframe="1h")
        exact_quote_volume(rows, start, end)
        receipt = load_evidence(
            self.evidence_root
            / "responses"
            / f"{sha256(url.encode()).hexdigest()}.json"
        )
        raw = (
            self.evidence_root
            / "raw"
            / f"{receipt.get('raw_response_sha256', '')}.json"
        ).read_bytes()
        if (
            sha256(raw).hexdigest() != receipt.get("raw_response_sha256")
            or receipt.get("source_url") != url
            or validate_native_rows(
                json.loads(raw),
                start=start,
                end=end,
                timeframe="1h",
            )
            != rows
        ):
            raise ValueError("ranking reconstruction requires a wire receipt")
        self.retry_policy.succeed(retry_path, datetime.now(UTC))
        return rows, raw, receipt

    def _reconstruct_packet(
        self,
        root: Path,
        candidate: Mapping[str, object],
        market: str,
        transport: PublicJsonTransport,
        prefix: str,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, object]:
        key = f"{market}-{symbol}-{int(end.timestamp())}"
        path = root / "packets" / f"{key}.json"
        if path.exists():
            packet = load_evidence(path)
            _verify_reconstructed_packet(root, packet, market, symbol, start, end)
            return packet
        original = load_evidence(self.evidence_root / "ranking-bars" / f"{key}.json")
        markets = cast(Mapping[str, Mapping[str, object]], candidate["markets"])
        expected = str(markets[market]["source_evidence_sha256"])
        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": "1h",
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000) - 1,
            "limit": 168,
        }
        host = (
            "https://api.binance.com"
            if market == "spot"
            else "https://fapi.binance.com"
        )
        url = host + prefix + "klines?" + urlencode(sorted(params.items()))
        receipt = load_evidence(
            self.evidence_root
            / "responses"
            / f"{sha256(url.encode()).hexdigest()}.json"
        )
        if receipt:
            retained_receipt = (
                root / "original-receipts" / f"{content_digest(receipt)}.json"
            )
            if not retained_receipt.exists():
                save_evidence(retained_receipt, receipt)
        raw_path = (
            self.evidence_root
            / "raw"
            / f"{receipt.get('raw_response_sha256', '')}.json"
        )
        recovered = bool(
            original and content_digest(original) == expected and raw_path.is_file()
        )
        if recovered:
            raw = raw_path.read_bytes()
            recovered = (
                sha256(raw).hexdigest() == receipt.get("raw_response_sha256")
                and receipt.get("source_url") == url
                and validate_native_rows(
                    json.loads(raw),
                    start=start,
                    end=end,
                    timeframe="1h",
                )
                == original["rows"]
            )
        if not recovered:
            rows, raw, receipt = self._retrieve_reconstruction_wire(
                key, market, transport, prefix, params, url, start, end
            )
        else:
            rows = validate_native_rows(
                original["rows"], start=start, end=end, timeframe="1h"
            )
        digest = sha256(raw).hexdigest()
        durable_raw = root / "raw" / f"{digest}.json"
        durable_raw.parent.mkdir(parents=True, exist_ok=True)
        if not durable_raw.exists():
            BinanceVisionArchiveCache._atomic_write(durable_raw, raw)
        packet = {
            "market": market,
            "symbol": symbol,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rows": rows,
            "decoded_rows_sha256": content_digest(rows),
            "raw_response_sha256": digest,
            "receipt": receipt,
            "original_expected_packet_sha256": expected,
            "original_packet": original if recovered else None,
            "recovery_mode": "RECOVERED_ORIGINAL_HASH_BOUND_PACKET"
            if recovered
            else "LATER_RETRIEVAL_NOT_PIT_AT_ORIGINAL_CUTOFF",
            "recovered_at": datetime.now(UTC).isoformat(),
            **SAFE_STATE,
        }
        packet["content_sha256"] = content_digest(packet)
        _verify_reconstructed_packet(root, packet, market, symbol, start, end)
        save_evidence(path, packet)
        return packet

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

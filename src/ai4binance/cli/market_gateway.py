"""Run the canonical REST-bootstrap plus WebSocket-live market-data gateway."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from websockets.exceptions import ConnectionClosed

from ai4binance.cli.market_data import (
    _priority_depth_markets,
    build_continuous_market_history,
    build_market_history_synchronizer,
)
from ai4binance.config import Settings
from ai4binance.data.market_data_gateway import MarketStreamGapError, build_gateway
from ai4binance.data.market_depth import MarketDepthCollector
from ai4binance.infrastructure.persistence.safe_json import write_json_object_verified
from ai4binance.ops.runtime import SingleInstanceLease

_SAFE_STATE: dict[str, object] = {
    "execution_allowed": False,
    "promotion_status": "RESEARCH_ONLY",
    "live_eligibility_status": "LIVE_ORDER_BLOCKED",
}


class _GatewayStateHeartbeat:
    """Refresh useful-cycle state only while validated live events arrive."""

    def __init__(self, path: Path, *, interval_seconds: float = 60.0) -> None:
        self._path = path
        self._interval_seconds = interval_seconds
        self._last_write = 0.0

    def __call__(self, observed_at: datetime) -> None:
        now = time.monotonic()
        if now - self._last_write < self._interval_seconds:
            return
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        payload = loaded if isinstance(loaded, dict) else {}
        raw_blockers = payload.get("blockers", [])
        blockers = (
            [str(item) for item in raw_blockers]
            if isinstance(raw_blockers, list | tuple)
            else ["MARKET_GATEWAY_STATE_BLOCKERS_INVALID"]
        )
        payload.update(
            {
                "observed_at": observed_at.astimezone(UTC).isoformat(),
                "status": "DEGRADED" if blockers else "READY",
                "ingestion_mode": "WEBSOCKET_LIVE",
                "blockers": blockers,
                **_SAFE_STATE,
            }
        )
        write_json_object_verified(
            self._path,
            payload,
            blocker="MARKET_GATEWAY_HEARTBEAT_WRITE_FAILED",
            subject_id="market-gateway:heartbeat",
        )
        self._last_write = now


def run_gateway(settings: Settings, *, max_cycles: int | None = None) -> int:
    """Bootstrap/recover with REST, then carry live data over combined streams."""

    if max_cycles is not None and max_cycles < 1:
        raise ValueError("max_cycles must be positive")
    synchronizer = build_market_history_synchronizer(settings)
    collector = build_continuous_market_history(
        settings,
        synchronizer,
        root=Path.cwd(),
        include_coin_m=False,
    )
    depth: MarketDepthCollector | None = None
    if getattr(settings, "market_depth_enabled", False):
        depth = MarketDepthCollector(
            synchronizer.archive_root / "depth",
            {
                "spot": collector.spot,
                "usd_m_futures": collector.futures,
            },
        )
    lock_path = _absolute(settings.market_history_state_path).with_suffix(".lock")
    heartbeat = _GatewayStateHeartbeat(_absolute(settings.market_history_state_path))
    completed = 0
    try:
        with SingleInstanceLease(lock_path):
            while max_cycles is None or completed < max_cycles:
                observed_at = datetime.now(UTC)
                if depth is not None:
                    depth_universe = synchronizer._eligible_universe(
                        observed_at, force_refresh=True
                    )
                    if not depth_universe.blockers:
                        depth.start(
                            _priority_depth_markets(
                                depth_universe,
                                collector.priority_symbols,
                                include_coin_m=False,
                            )
                        )
                bootstrap = collector.sync_cycle(observed_at=observed_at)
                blockers = _blockers(bootstrap)
                if "MARKET_DATA_BACKFILL_PENDING" in blockers and not (
                    blockers & _FATAL_INGESTION_BLOCKERS
                ):
                    time.sleep(min(60.0, settings.market_history_live_interval_seconds))
                    continue
                if blockers & _FATAL_INGESTION_BLOCKERS:
                    print(
                        json.dumps(
                            {
                                "command": "market-gateway-daemon",
                                "status": "DATA_BLOCKED",
                                "blockers": sorted(blockers),
                                **_SAFE_STATE,
                            },
                            sort_keys=True,
                        )
                    )
                    return 2
                universe = synchronizer._eligible_universe(
                    datetime.now(UTC), force_refresh=False
                )
                if universe.blockers:
                    return 2
                gateway = build_gateway(
                    _absolute(settings.dataset_directory),
                    spot_symbols=universe.spot_symbols,
                    futures_symbols=universe.futures_symbols,
                    spot_candidates=_adaptive_candidates(
                        bootstrap, "SPOT", settings.priority_watchlist
                    ),
                    futures_candidates=_adaptive_candidates(
                        bootstrap, "USD_M_FUTURES", settings.priority_watchlist
                    ),
                    activity_observer=heartbeat,
                )
                reconnect_attempt = 0
                while True:
                    try:
                        asyncio.run(gateway.run_once())
                    except MarketStreamGapError:
                        # The next outer loop performs bounded REST gap recovery
                        # before either WebSocket connection can resume.
                        break
                    except (ConnectionClosed, OSError, TimeoutError):
                        reconnect_attempt += 1
                        time.sleep(_reconnect_delay(reconnect_attempt))
                        continue
                    completed += 1
                    break
    except RuntimeError as error:
        blocker_code = (
            "MARKET_GATEWAY_ALREADY_RUNNING"
            if str(error) == "runtime instance is already active"
            else "MARKET_GATEWAY_RUNTIME_FAILURE"
        )
        print(
            json.dumps(
                {
                    "command": "market-gateway-daemon",
                    "status": "BLOCKED",
                    "blockers": [blocker_code],
                    **_SAFE_STATE,
                },
                sort_keys=True,
            )
        )
        return 2
    finally:
        if depth is not None:
            depth.close()
    return 0


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


_FATAL_INGESTION_BLOCKERS = frozenset(
    {
        "PUBLIC_MARKET_UNIVERSE_UNAVAILABLE",
        "PUBLIC_MARKET_UNIVERSE_EMPTY",
        "PUBLIC_MARKET_LIQUIDITY_UNIVERSE_UNAVAILABLE",
        "PUBLIC_MARKET_LIQUIDITY_UNIVERSE_EMPTY",
        "MARKET_DATA_SOURCE_OR_INTEGRITY_FAILURE",
        "MARKET_DATA_RANGE_UNAVAILABLE",
    }
)


def _blockers(state: dict[str, object]) -> frozenset[str]:
    raw = state.get("blockers", ())
    if not isinstance(raw, list | tuple):
        return frozenset({"MARKET_GATEWAY_BLOCKERS_INVALID"})
    return frozenset(str(item) for item in raw)


def _adaptive_candidates(
    state: dict[str, object], market: str, fallback: Sequence[str]
) -> tuple[str, ...]:
    projection = state.get("dashboard_opportunity_projection")
    market_projection = projection.get(market) if isinstance(projection, dict) else None
    opportunities = (
        market_projection.get("opportunities")
        if isinstance(market_projection, dict)
        else None
    )
    selected = [
        str(item["symbol"]).upper()
        for item in opportunities or ()
        if isinstance(item, dict)
        and isinstance(item.get("symbol"), str)
        and item.get("market") == market
    ]
    return tuple(dict.fromkeys((*selected, *(item.upper() for item in fallback))))[:10]


def _reconnect_delay(attempt: int) -> float:
    if attempt < 1:
        raise ValueError("reconnect attempt must be positive")
    return float(min(60, 2 ** min(attempt - 1, 6)))


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-cycles", type=int, default=None)
    parsed = parser.parse_args(arguments)
    return run_gateway(Settings(), max_cycles=parsed.max_cycles)


if __name__ == "__main__":
    raise SystemExit(main())

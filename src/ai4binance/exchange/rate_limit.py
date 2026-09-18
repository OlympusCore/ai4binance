"""Central weighted request governor for Binance public REST transports."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock

from ai4binance.core.errors import ExchangeHttpError


class RequestPriority(StrEnum):
    """Bounded public REST priorities; none can bypass the hard stop."""

    METADATA = "METADATA"
    GAP_RECOVERY = "GAP_RECOVERY"
    BOOTSTRAP = "BOOTSTRAP"
    SUPPLEMENTAL = "SUPPLEMENTAL"


@dataclass(frozen=True, slots=True)
class RateLimitBands:
    """Internal safety margins below provider-advertised limits."""

    soft_limit: float = 0.70
    warning: float = 0.80
    throttle: float = 0.85
    hard_stop: float = 0.90

    def __post_init__(self) -> None:
        if not (
            0 < self.soft_limit < self.warning < self.throttle < self.hard_stop < 1
        ):
            raise ValueError("rate-limit safety bands must be strictly increasing")


@dataclass(slots=True)
class _Window:
    seconds: int
    limit: int
    used: int = 0
    started_at: float = 0.0


@dataclass(slots=True)
class WeightedRateLimitGovernor:
    """Reserve weighted REST capacity using runtime provider limits and usage."""

    bands: RateLimitBands = field(default_factory=RateLimitBands)
    clock: Callable[[], float] = field(default=time.time, repr=False)
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)
    monotonic: Callable[[], float] = field(default=time.monotonic, repr=False)
    cooldown_until: float = 0.0
    _windows: dict[int, _Window] = field(default_factory=dict, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def configure_from_exchange_info(self, payload: object) -> None:
        """Replace runtime request-weight windows from ``exchangeInfo``."""

        if not isinstance(payload, Mapping):
            return
        raw_limits = payload.get("rateLimits")
        if not isinstance(raw_limits, list):
            return
        units = {"SECOND": 1, "MINUTE": 60, "HOUR": 3_600, "DAY": 86_400}
        configured: dict[int, _Window] = {}
        for item in raw_limits:
            if (
                not isinstance(item, Mapping)
                or item.get("rateLimitType") != "REQUEST_WEIGHT"
            ):
                continue
            try:
                seconds = units[str(item["interval"])] * int(str(item["intervalNum"]))
                limit = int(str(item["limit"]))
            except (KeyError, TypeError, ValueError):
                continue
            if seconds > 0 and limit > 0:
                configured[seconds] = _Window(seconds=seconds, limit=limit)
        if configured:
            now = self.clock()
            with self._lock:
                for window in configured.values():
                    window.started_at = now - (now % window.seconds)
                self._windows = configured

    def observe_headers(self, headers: Mapping[str, str]) -> None:
        """Reconcile locally reserved weight with Binance response headers."""

        normalized = {str(key).casefold(): str(value) for key, value in headers.items()}
        with self._lock:
            self._reset_elapsed_windows(self.clock())
            for seconds, window in self._windows.items():
                suffixes = (
                    "1s" if seconds == 1 else "",
                    "1m" if seconds == 60 else "",
                    "1h" if seconds == 3_600 else "",
                    "1d" if seconds == 86_400 else "",
                )
                for suffix in suffixes:
                    if not suffix:
                        continue
                    raw = normalized.get(f"x-mbx-used-weight-{suffix}")
                    if raw is not None:
                        try:
                            window.used = max(window.used, int(raw))
                        except ValueError:
                            pass

    def reserve(
        self,
        weight: int,
        *,
        priority: RequestPriority = RequestPriority.SUPPLEMENTAL,
    ) -> None:
        """Allow, delay, or reject one weighted request without limit bypasses."""

        if weight <= 0:
            raise ValueError("request weight must be positive")
        while True:
            delay = 0.0
            with self._lock:
                if self.monotonic() < self.cooldown_until:
                    raise ExchangeHttpError("shared public request budget cooldown")
                now = self.clock()
                self._reset_elapsed_windows(now)
                if not self._windows:
                    raise ExchangeHttpError("request-weight limits are not configured")
                for window in self._windows.values():
                    projected = window.used + weight
                    ratio = projected / window.limit
                    if ratio >= self.bands.hard_stop:
                        raise ExchangeHttpError("request-weight hard stop reached")
                    if ratio >= self.bands.throttle or (
                        ratio >= self.bands.warning
                        and priority is RequestPriority.SUPPLEMENTAL
                    ):
                        delay = max(delay, window.started_at + window.seconds - now)
                if delay <= 0:
                    for window in self._windows.values():
                        window.used += weight
                    return
            self.sleeper(max(0.001, delay))

    def apply_retry_after(self, seconds: float, *, banned: bool = False) -> None:
        """Enter a monotonic cooldown after 429 or 418 responses."""

        minimum = 120.0 if banned else 1.0
        duration = max(minimum, seconds)
        with self._lock:
            self.cooldown_until = max(self.cooldown_until, self.monotonic() + duration)

    def status(self) -> dict[str, object]:
        """Return bounded diagnostics without granting request authority."""

        with self._lock:
            self._reset_elapsed_windows(self.clock())
            windows = tuple(
                {
                    "window_seconds": window.seconds,
                    "limit": window.limit,
                    "used": window.used,
                    "usage_ratio": window.used / window.limit,
                }
                for window in sorted(
                    self._windows.values(), key=lambda item: item.seconds
                )
            )
        peak = max((float(item["usage_ratio"]) for item in windows), default=0.0)
        state = (
            "HARD_STOP"
            if peak >= self.bands.hard_stop
            else "THROTTLE"
            if peak >= self.bands.throttle
            else "WARNING"
            if peak >= self.bands.warning
            else "SOFT_LIMIT"
            if peak >= self.bands.soft_limit
            else "NORMAL"
        )
        return {
            "windows": windows,
            "state": state,
            "soft_limit": self.bands.soft_limit,
            "warning": self.bands.warning,
            "throttle": self.bands.throttle,
            "hard_stop": self.bands.hard_stop,
        }

    def _reset_elapsed_windows(self, now: float) -> None:
        for window in self._windows.values():
            started_at = now - (now % window.seconds)
            if started_at > window.started_at:
                window.started_at = started_at
                window.used = 0


def public_request_weight(
    path: str,
    params: Mapping[str, str | int] | None = None,
) -> int:
    """Return documented endpoint weight for the bounded collector surface."""

    query = params or {}
    endpoint = path.rsplit("/", 1)[-1]
    spot = path.startswith("/api/")
    if endpoint in {"klines", "markPriceKlines", "indexPriceKlines"}:
        limit = int(query.get("limit", 500))
        if not spot:
            if limit < 100:
                return 1
            if limit < 500:
                return 2
            if limit <= 1_000:
                return 5
            return 10
        return 2
    if endpoint == "depth":
        limit = int(query.get("limit", 100))
        if spot:
            return (
                5
                if limit <= 100
                else 25
                if limit <= 500
                else 50
                if limit <= 1_000
                else 250
            )
        return (
            2 if limit <= 100 else 5 if limit <= 500 else 10 if limit <= 1_000 else 20
        )
    if endpoint == "24hr":
        return 2 if "symbol" in query else (80 if spot else 40)
    if endpoint == "bookTicker":
        return 2 if "symbol" in query else (4 if spot else 5)
    return {
        "exchangeInfo": 20 if spot else 1,
        "premiumIndex": 10,
        "fundingRate": 1,
        "openInterestHist": 1,
        "time": 1,
    }.get(endpoint, 40)

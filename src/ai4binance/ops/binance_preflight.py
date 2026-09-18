"""Secret-safe Binance read-only preflight diagnostics."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self

from ai4binance.exchange.private import (
    PrivateCredentials,
    SignedReadOnlyRequestFactory,
    SignedUsdMReadOnlyRequestFactory,
)


@dataclass(frozen=True, slots=True)
class PreflightEndpoint:
    name: str
    request: urllib.request.Request
    expects_account_payload: bool = False


class ResponseLike(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def read(self, limit: int) -> bytes: ...


def build_preflight_report(
    credential_file: Path = Path("secrets/bnc.env"),
    *,
    timeout_seconds: float = 10.0,
    clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    opener: Callable[..., ResponseLike] = urllib.request.urlopen,
) -> dict[str, object]:
    """Return a redacted read-only API health report."""
    report: dict[str, object] = {
        "command": "binance-preflight",
        "credential_file": str(credential_file),
        "credential_status": "UNKNOWN",
        "endpoints": [],
        "blockers": [],
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }
    try:
        credentials = PrivateCredentials.from_environment_or_file(credential_file)
    except ValueError as error:
        report["credential_status"] = "BLOCKED"
        report["blockers"] = (f"CREDENTIALS:{error}",)
        return report

    report["credential_status"] = "PRESENT"
    endpoints = (
        PreflightEndpoint(
            "spot_server_time",
            _request("https://api.binance.com/api/v3/time"),
        ),
        PreflightEndpoint(
            "futures_server_time",
            _request("https://fapi.binance.com/fapi/v1/time"),
        ),
        PreflightEndpoint(
            "spot_account",
            SignedReadOnlyRequestFactory(credentials, clock_ms=clock_ms).build(
                "/api/v3/account"
            ),
            expects_account_payload=True,
        ),
        PreflightEndpoint(
            "futures_account",
            SignedUsdMReadOnlyRequestFactory(credentials, clock_ms=clock_ms).build(
                "/fapi/v2/account"
            ),
            expects_account_payload=True,
        ),
    )
    endpoint_rows = tuple(
        _probe_endpoint(endpoint, timeout_seconds=timeout_seconds, opener=opener)
        for endpoint in endpoints
    )
    blockers = tuple(
        f"{row['name']}:{row['status']}"
        for row in endpoint_rows
        if row["status"] != "OK"
    )
    report["endpoints"] = endpoint_rows
    report["blockers"] = blockers
    report["status"] = "READY" if not blockers else "DEGRADED"
    return report


def main() -> int:
    report = build_preflight_report()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("status") == "READY" else 2


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(  # noqa: S310 - fixed official Binance URL.
        url,
        headers={"Accept": "application/json", "User-Agent": "AI4Binance/0.1"},
        method="GET",
    )


def _probe_endpoint(
    endpoint: PreflightEndpoint,
    *,
    timeout_seconds: float,
    opener: Callable[..., ResponseLike],
) -> dict[str, object]:
    local_before = int(time.time() * 1000)
    try:
        response = opener(endpoint.request, timeout=timeout_seconds)
        with response:
            payload = response.read(2_000_000)
    except urllib.error.HTTPError as error:
        return {
            "name": endpoint.name,
            "status": "HTTP_ERROR",
            "http_status": error.code,
            **_binance_error(error),
        }
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        return {
            "name": endpoint.name,
            "status": "TRANSPORT_ERROR",
            "category": type(error).__name__,
        }
    local_after = int(time.time() * 1000)
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, JSONDecodeError):
        return {"name": endpoint.name, "status": "INVALID_JSON"}
    if not isinstance(decoded, dict):
        return {"name": endpoint.name, "status": "UNEXPECTED_PAYLOAD"}
    server_time = decoded.get("serverTime")
    if isinstance(server_time, int):
        local_midpoint = int((local_before + local_after) / 2)
        return {
            "name": endpoint.name,
            "status": "OK",
            "server_time_delta_ms": server_time - local_midpoint,
        }
    if endpoint.expects_account_payload:
        return {
            "name": endpoint.name,
            "status": "OK" if decoded else "EMPTY_ACCOUNT_PAYLOAD",
        }
    return {"name": endpoint.name, "status": "OK"}


def _binance_error(error: urllib.error.HTTPError) -> dict[str, object]:
    try:
        raw = error.read(64_000)
        payload: Any = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, JSONDecodeError):
        return {"binance_code": None, "binance_message": ""}
    if not isinstance(payload, dict):
        return {"binance_code": None, "binance_message": ""}
    return {
        "binance_code": payload.get("code"),
        "binance_message": str(payload.get("msg", ""))[:240],
    }


if __name__ == "__main__":
    raise SystemExit(main())

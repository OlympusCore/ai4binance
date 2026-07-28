"""Append-only local observability without prompt or evidence retention."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from ai4binance.governance import RunContext
from ai4binance.storage import SecretRedactor

_CONTENT_FRAGMENTS = (
    "prompt",
    "evidence",
    "content",
    "argument",
    "message",
    "response",
    "result_body",
    "tool_definition",
)


class LocalObserver:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._redactor = SecretRedactor()

    def emit(
        self,
        context: RunContext,
        event: str,
        status: str,
        *,
        duration_ms: float | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if not event.strip() or not status.strip():
            raise ValueError("observation event and status are required")
        safe_metadata = self._sanitize_metadata(metadata or {})
        payload = self._redactor.redact(
            {
                "schema_name": "ai4binance.local_observation",
                "schema_version": "1.0",
                "timestamp": datetime.now(UTC).isoformat(),
                "trace_id": _identifier_hash(context.run_id, 32),
                "span_id": _identifier_hash(
                    f"{context.run_id}:{context.step_id}:{event}",
                    16,
                ),
                "run_id": context.run_id,
                "step_id": context.step_id,
                "parent_event_id": context.parent_event_id,
                "event": event,
                "status": status,
                "duration_ms": (
                    round(duration_ms, 3) if duration_ms is not None else None
                ),
                "metadata": safe_metadata,
                "content_capture": False,
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.open("a", encoding="utf-8", newline="\n").write(
            json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n"
        )

    @contextmanager
    def measure(
        self,
        context: RunContext,
        event: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        except Exception as exc:
            self.emit(
                context,
                event,
                "FAILED",
                duration_ms=(perf_counter() - started) * 1000,
                metadata={**(metadata or {}), "error_type": type(exc).__name__},
            )
            raise
        self.emit(
            context,
            event,
            "COMPLETED",
            duration_ms=(perf_counter() - started) * 1000,
            metadata=metadata,
        )

    def _sanitize_metadata(self, metadata: dict[str, object]) -> dict[str, object]:
        safe: dict[str, object] = {}
        for key, value in metadata.items():
            lowered = key.casefold()
            if lowered.endswith("_id") and isinstance(value, str):
                safe[key] = f"sha256:{_identifier_hash(value, 16)}"
            elif any(fragment in lowered for fragment in _CONTENT_FRAGMENTS):
                safe[key] = "[CONTENT_NOT_CAPTURED]"
            elif isinstance(value, dict):
                safe[key] = self._sanitize_metadata(
                    {str(item_key): item for item_key, item in value.items()}
                )
            elif isinstance(value, (list, tuple)):
                safe[key] = [
                    self._sanitize_metadata({"value": item})["value"]
                    if not isinstance(item, dict)
                    else self._sanitize_metadata(
                        {str(item_key): nested for item_key, nested in item.items()}
                    )
                    for item in value
                ]
            else:
                safe[key] = value
        return safe


def _identifier_hash(value: str, length: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]

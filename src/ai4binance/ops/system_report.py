"""Secret-safe whole-system operator report generation."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.config import Settings
from ai4binance.enterprise.oek_compliance import audit_oek_constitution
from ai4binance.ops.runtime import SingleInstanceLease
from ai4binance.reporting import to_primitive
from ai4binance.skills.continuous_runtime import read_skill_discovery_status

_REQUIRED_SERVICES = ("runtime", "accounting", "accounting-ws", "skill-discovery")
_SERVICE_HEALTH_MAX_AGE_SECONDS = {
    "runtime": 120.0,
    "accounting": 120.0,
    "accounting-ws": 120.0,
    "skill-discovery": 180.0,
}
_LOCAL_ADVISORY_MODEL = "qwen3:8b"
_OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
_OLLAMA_RESPONSE_LIMIT_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SystemReportResult:
    payload: dict[str, object]
    markdown_path: Path
    json_path: Path
    latest_json_path: Path


def system_report_summary_payload(result: SystemReportResult) -> dict[str, object]:
    """Return a bounded interactive view while full evidence stays on disk."""
    payload = result.payload
    components = cast(dict[str, dict[str, object]], payload["components"])
    return {
        "command": "system-report",
        "report_id": payload.get("report_id"),
        "observed_at": payload.get("observed_at"),
        "status": payload.get("status"),
        "components": {
            name: {
                "status": component.get("status", component.get("state", "UNKNOWN")),
                "blockers": _blocker_tuple(component.get("blockers")),
            }
            for name, component in components.items()
        },
        "blockers": payload.get("blockers", ()),
        "markdown_path": str(result.markdown_path),
        "json_path": str(result.json_path),
        "latest_json_path": str(result.latest_json_path),
        "details": "FULL_EVIDENCE_PERSISTED_TO_JSON",
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def build_system_report(
    settings: Settings,
    *,
    observed_at: datetime | None = None,
    workspace_root: Path | None = None,
) -> SystemReportResult:
    """Build and persist a bounded whole-system report without private balances."""
    now = observed_at or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("system report observed_at must be timezone-aware")
    root = workspace_root or Path.cwd()
    (
        accounting_status_payload,
        lean_governance_payload,
        opportunities_payload,
        quality_system_audit_payload,
        repository_cleanup_audit_payload,
        validation_summary_payload,
    ) = _load_cli_component_builders()

    components = {
        "qaqc": _safe_component("qaqc", quality_system_audit_payload),
        "oek": _safe_component(
            "oek", lambda: _component_payload(audit_oek_constitution(root))
        ),
        "lean": _safe_component("lean", lambda: lean_governance_payload(settings)),
        "repository_cleanup": _safe_component(
            "repository_cleanup", repository_cleanup_audit_payload
        ),
        "startup": _safe_component(
            "startup", lambda: startup_health_payload(settings, datetime.now(UTC))
        ),
        "local_advisory": _safe_component(
            "local-advisory", lambda: local_advisory_health_payload(settings)
        ),
        "runtime": _safe_component(
            "runtime", lambda: runtime_state_payload(settings, datetime.now(UTC))
        ),
        "validation": _safe_component(
            "validation", lambda: validation_summary_payload(settings, settings.symbol)
        ),
        "opportunities": _safe_component(
            "opportunities", lambda: opportunities_payload(settings, settings.symbol)
        ),
        "accounting": _safe_component(
            "accounting", lambda: accounting_status_payload(settings, now)
        ),
        "skill_discovery": _safe_component(
            "skill_discovery", lambda: read_skill_discovery_status(settings)
        ),
    }
    component_blockers = _component_blockers(components)
    startup_component = components["startup"]
    startup_blockers = _blocker_tuple(startup_component.get("blockers", ()))
    status = (
        "DEGRADED"
        if startup_blockers
        else "RUNNING_WITH_BLOCKERS"
        if component_blockers
        else "READY"
    )
    payload: dict[str, object] = {
        "command": "system-report",
        "report_id": f"system-report:{int(now.timestamp())}",
        "observed_at": now,
        "workspace_root": str(root),
        "status": status,
        "components": components,
        "blockers": component_blockers,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "redaction": {
            "wallet_amounts": "omitted",
            "credentials": "omitted",
            "private_state": "summarized_only",
        },
    }
    return _persist_report(root, payload, now)


def startup_health_payload(
    settings: Settings, observed_at: datetime
) -> dict[str, object]:
    """Summarize resident service health files and lock evidence."""
    state_dir = settings.runtime_state_path.parent
    services = tuple(
        _service_health(service, state_dir, observed_at)
        for service in _REQUIRED_SERVICES
    )
    blockers = tuple(
        blocker
        for service in services
        for blocker in _blocker_tuple(service.get("blockers", ()))
    )
    return {
        "command": "startup-health",
        "status": "READY" if not blockers else "DEGRADED",
        "state_directory": str(state_dir),
        "services": services,
        "blockers": tuple(dict.fromkeys(blockers)),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def runtime_state_payload(
    settings: Settings, observed_at: datetime
) -> dict[str, object]:
    """Read the public runtime state without copying wallet/account fields."""
    path = settings.runtime_state_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return _blocked_component(
            "runtime-state",
            "DEGRADED",
            ("RUNTIME_REPORT_UNAVAILABLE",),
            path=str(path),
        )
    if not isinstance(payload, dict):
        return _blocked_component(
            "runtime-state",
            "DEGRADED",
            ("RUNTIME_REPORT_INVALID",),
            path=str(path),
        )
    payload = cast(dict[str, object], payload)

    created_at = _parse_datetime(payload.get("created_at"))
    blockers = _blocker_tuple(payload.get("blockers", ()))
    state = str(payload.get("state", "DEGRADED"))
    raw_health = payload.get("health")
    health: dict[str, object] = (
        cast(dict[str, object], raw_health) if isinstance(raw_health, dict) else {}
    )
    age_seconds = (
        (observed_at - created_at).total_seconds() if created_at is not None else None
    )
    issues: list[str] = []
    if created_at is None:
        issues.append("RUNTIME_REPORT_TIMESTAMP_INVALID")
    elif age_seconds is not None and (age_seconds < -5 or age_seconds > 180):
        issues.append("RUNTIME_REPORT_STALE")
    if state != "READY":
        issues.append(f"RUNTIME_{state}")
    return {
        "command": "runtime-state",
        "status": "READY" if not issues and not blockers else "RUNNING_WITH_BLOCKERS",
        "path": str(path),
        "state": state,
        "created_at": payload.get("created_at"),
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "health": {
            "status": health.get("status"),
            "last_attempt_at": health.get("last_attempt_at"),
            "last_success_at": health.get("last_success_at"),
            "consecutive_failures": health.get("consecutive_failures"),
        },
        "blockers": tuple(dict.fromkeys((*issues, *blockers))),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def local_advisory_health_payload(settings: Settings) -> dict[str, object]:
    """Verify the only production advisory route: loopback Ollama qwen3:8b."""
    blockers: list[str] = []
    state_path = settings.runtime_state_path.parent / "qwen-prompter-health.json"
    health: dict[str, object] = {}
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, dict):
            health = cast(dict[str, object], loaded)
        else:
            blockers.append("QWEN_PROMPTER_STATE_INVALID")
    except FileNotFoundError:
        blockers.append("QWEN_PROMPTER_STATE_MISSING")
    except (OSError, json.JSONDecodeError):
        blockers.append("QWEN_PROMPTER_STATE_INVALID")

    if health.get("status") != "RUNNING":
        blockers.append("QWEN_PROMPTER_NOT_RUNNING")
    if health.get("model") != _LOCAL_ADVISORY_MODEL:
        blockers.append("QWEN_PROMPTER_MODEL_MISMATCH")
    pid = _safe_int(health.get("pid"))
    if pid is None or pid < 1 or not SingleInstanceLease._pid_is_alive(pid):
        blockers.append("QWEN_PROMPTER_PID_NOT_ALIVE")

    installed_models: tuple[str, ...] = ()
    request = urllib.request.Request(  # noqa: S310 - fixed loopback-only URL.
        _OLLAMA_TAGS_URL,
        method="GET",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310  # nosec B310
            request,
            timeout=3.0,
        ) as response:
            payload = json.loads(response.read(_OLLAMA_RESPONSE_LIMIT_BYTES))
        raw_models = payload.get("models") if isinstance(payload, dict) else None
        if isinstance(raw_models, list):
            installed_models = tuple(
                str(model["name"])
                for model in raw_models
                if isinstance(model, dict) and isinstance(model.get("name"), str)
            )
        if _LOCAL_ADVISORY_MODEL not in installed_models:
            blockers.append("OLLAMA_QWEN3_8B_MODEL_UNAVAILABLE")
    except (
        OSError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        blockers.append("OLLAMA_PROVIDER_UNAVAILABLE")

    return {
        "command": "local-advisory-health",
        "status": "READY" if not blockers else "DEGRADED",
        "provider": "ollama",
        "endpoint": _OLLAMA_TAGS_URL,
        "model": _LOCAL_ADVISORY_MODEL,
        "loopback_only": True,
        "installed_models": installed_models,
        "prompter_state_path": str(state_path),
        "prompter_status": health.get("status"),
        "prompter_pid": pid,
        "blockers": tuple(dict.fromkeys(blockers)),
        "advisory_mode": "RESEARCH_ONLY",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _service_health(
    service: str,
    state_dir: Path,
    observed_at: datetime,
) -> dict[str, object]:
    path = state_dir / f"{service}-health.json"
    lock_path = state_dir / f"{service}.lock"
    label = service.upper().replace("-", "_")
    blockers: list[str] = []
    payload: dict[str, object] = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, dict):
            payload = cast(dict[str, object], loaded)
        else:
            blockers.append(f"{label}_STATE_INVALID")
    except FileNotFoundError:
        blockers.append(f"{label}_STATE_MISSING")
    except (OSError, json.JSONDecodeError):
        blockers.append(f"{label}_STATE_INVALID")

    updated_at = _parse_datetime(payload.get("updated_at"))
    age_seconds = (
        (observed_at - updated_at).total_seconds() if updated_at is not None else None
    )
    if updated_at is None:
        blockers.append(f"{label}_STATE_TIMESTAMP_INVALID")
    else:
        max_age = _SERVICE_HEALTH_MAX_AGE_SECONDS[service]
        if age_seconds is not None and (age_seconds < -5 or age_seconds > max_age):
            blockers.append(f"{label}_STATE_STALE")
    if payload.get("status") != "RUNNING":
        blockers.append(f"{label}_NOT_RUNNING")
    pid = _safe_int(payload.get("pid"))
    child_pid = _safe_int(payload.get("child_pid"))
    if pid is None or pid < 1 or not SingleInstanceLease._pid_is_alive(pid):
        blockers.append(f"{label}_PID_NOT_ALIVE")
    lock_pid = _read_lock_pid(lock_path)
    if lock_pid is None:
        blockers.append(f"{label}_LOCK_MISSING_OR_INVALID")
    elif not SingleInstanceLease._pid_is_alive(lock_pid):
        blockers.append(f"{label}_LOCK_PID_NOT_ALIVE")

    return {
        "service": service,
        "status": "READY" if not blockers else "DEGRADED",
        "health_path": str(path),
        "lock_path": str(lock_path),
        "pid": pid,
        "child_pid": child_pid,
        "updated_at": payload.get("updated_at"),
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "blockers": tuple(dict.fromkeys(blockers)),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _safe_component(
    command: str,
    builder: Callable[[], object],
) -> dict[str, object]:
    try:
        payload = builder()
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError):
        return _blocked_component(
            command,
            "DEGRADED",
            (f"{command.upper().replace('-', '_')}_UNAVAILABLE",),
        )
    primitive = to_primitive(payload)
    if not isinstance(primitive, dict):
        return _blocked_component(
            command,
            "DEGRADED",
            (f"{command.upper().replace('-', '_')}_PAYLOAD_INVALID",),
        )
    report = cast(dict[str, object], primitive)
    report.setdefault("command", command)
    report.setdefault("execution_allowed", False)
    report.setdefault("live_eligibility_status", "LIVE_ORDER_BLOCKED")
    report.setdefault("blockers", ())
    blockers = _blocker_tuple(report.get("blockers"))
    report.setdefault("status", "READY" if not blockers else "RUNNING_WITH_BLOCKERS")
    return report


def _load_cli_component_builders() -> tuple[
    Callable[[Settings, datetime], dict[str, object]],
    Callable[[Settings], dict[str, object]],
    Callable[[Settings, str | None], dict[str, object]],
    Callable[[], dict[str, object]],
    Callable[[], dict[str, object]],
    Callable[[Settings, str | None], dict[str, object]],
]:
    from ai4binance.cli.accounting import accounting_status_payload
    from ai4binance.cli.enterprise import (
        quality_system_audit_payload,
        repository_cleanup_audit_payload,
    )
    from ai4binance.cli.status import (
        lean_governance_payload,
        opportunities_payload,
        validation_summary_payload,
    )

    return (
        accounting_status_payload,
        lean_governance_payload,
        opportunities_payload,
        quality_system_audit_payload,
        repository_cleanup_audit_payload,
        validation_summary_payload,
    )


def _component_payload(payload: object) -> dict[str, object]:
    primitive = to_primitive(payload)
    if not isinstance(primitive, dict):
        raise ValueError("component payload must be a dictionary")
    return cast(dict[str, object], primitive)


def _blocked_component(
    command: str,
    status: str,
    blockers: tuple[str, ...],
    **extra: object,
) -> dict[str, object]:
    return {
        "command": command,
        "status": status,
        "blockers": blockers,
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        **extra,
    }


def _component_blockers(
    components: dict[str, dict[str, object]],
) -> tuple[str, ...]:
    blockers: list[str] = []
    for name, payload in components.items():
        blockers.extend(
            f"{name}:{blocker}" for blocker in _blocker_tuple(payload.get("blockers"))
        )
    return tuple(dict.fromkeys(str(item) for item in blockers))


def _persist_report(
    root: Path,
    payload: dict[str, object],
    observed_at: datetime,
) -> SystemReportResult:
    stamp = observed_at.strftime("%Y%m%dT%H%M%SZ")
    report_dir = root / "Reports" / "operations"
    artifact_dir = root / "Artifacts" / "system-audit"
    report_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / f"SYSTEM_REPORT_{stamp}.md"
    json_path = artifact_dir / f"system-report-{stamp}.json"
    latest_json_path = artifact_dir / "system-report-latest.json"
    payload["markdown_path"] = str(markdown_path)
    payload["json_path"] = str(json_path)
    payload["latest_json_path"] = str(latest_json_path)
    primitive = to_primitive(payload)
    json_text = json.dumps(primitive, ensure_ascii=False, indent=2, sort_keys=True)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    latest_json_path.write_text(json_text + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload, json_path), encoding="utf-8")
    return SystemReportResult(
        payload=payload,
        markdown_path=markdown_path,
        json_path=json_path,
        latest_json_path=latest_json_path,
    )


def _render_markdown(payload: dict[str, object], json_path: Path) -> str:
    components = cast(dict[str, dict[str, object]], payload["components"])
    lines = [
        f"# AI4BINANCE System Report - {payload['observed_at']}",
        "",
        "## ELI10",
        "",
        (
            "Bu rapor sistemin calisan parcalarini, guvenlik kilitlerini ve "
            "duzeltilmesi gereken blocker'lari tek yerde toplar. Canli emir "
            "yetkisi vermez; sadece operator gorunurlugu saglar."
        ),
        "",
        "## Summary",
        "",
        f"- status: `{payload['status']}`",
        f"- execution_allowed: `{payload['execution_allowed']}`",
        f"- live_eligibility_status: `{payload['live_eligibility_status']}`",
        f"- json: `{json_path}`",
        "",
        "## Components",
        "",
        "| Component | Status | Blockers |",
        "| --- | --- | --- |",
    ]
    for name, component in components.items():
        status = component.get("status", component.get("state", "UNKNOWN"))
        blockers = component.get("blockers", ())
        if isinstance(blockers, str):
            blocker_text = blockers
        elif isinstance(blockers, list | tuple):
            blocker_text = ", ".join(str(item) for item in blockers[:8])
        else:
            blocker_text = ""
        lines.append(f"| `{name}` | `{status}` | {blocker_text or '-'} |")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- `NO_TRADE` korunur.",
            "- `RESEARCH_ONLY` korunur.",
            "- `LIVE_ORDER_BLOCKED` korunur.",
            (
                "- Cuzdan bakiyeleri, credential ve private state degerleri "
                "rapora yazilmaz."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _blocker_tuple(value: object = ()) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return ()


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _read_lock_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None

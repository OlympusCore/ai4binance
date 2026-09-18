"""Manifest-backed local service health checks."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.config import Settings
from ai4binance.ops.runtime import SingleInstanceLease

DEFAULT_SERVICE_MANIFEST_PATH = Path("config/operations/services.json")


@dataclass(frozen=True, slots=True)
class ServiceHealthSpec:
    """Shared Python/PowerShell contract for one local service."""

    service: str
    task_name: str
    command: str
    mode: str
    required: bool
    health_file: str
    lock_file: str
    max_health_age_seconds: float
    startup_trigger: str
    allow_start_if_on_batteries: bool
    stop_if_going_on_batteries: bool
    order_writing_authority: bool
    health_mode: str = "RESIDENT"
    enabled: bool = True
    useful_state_file: str | None = None
    useful_timestamp_field: str | None = None
    max_useful_cycle_age_seconds: float | None = None

    @property
    def label(self) -> str:
        return self.service.upper().replace("-", "_")


def load_service_manifest(
    path: Path | None = None,
) -> tuple[ServiceHealthSpec, ...]:
    """Load the local service manifest without granting execution authority."""
    manifest_path = path or DEFAULT_SERVICE_MANIFEST_PATH
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("service manifest must be a JSON object")
    if payload.get("execution_allowed") is not False:
        raise ValueError("service manifest cannot allow execution")
    if payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED":
        raise ValueError("service manifest must keep live orders blocked")
    services = payload.get("services")
    if not isinstance(services, list) or not services:
        raise ValueError("service manifest must list services")
    specs = tuple(_service_spec(item) for item in services)
    names = tuple(spec.service for spec in specs)
    if len(set(names)) != len(names):
        raise ValueError("service manifest service names must be unique")
    return specs


def startup_health_from_manifest(
    settings: Settings,
    observed_at: datetime,
    *,
    manifest_path: Path | None = None,
    pid_is_alive: Callable[[int], bool] | None = None,
) -> dict[str, object]:
    """Summarize required service health from the shared manifest."""
    state_dir = settings.runtime_state_path.parent
    specs = tuple(
        spec for spec in load_service_manifest(manifest_path) if spec.required
    )
    checker = pid_is_alive or SingleInstanceLease._pid_is_alive
    lock_checker = (
        None if pid_is_alive is not None else SingleInstanceLease.lock_owner_is_active
    )
    services = tuple(
        service_health_from_spec(
            spec,
            state_dir,
            observed_at,
            pid_is_alive=checker,
            lock_owner_is_active=lock_checker,
        )
        for spec in specs
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
        "manifest_path": str(manifest_path or DEFAULT_SERVICE_MANIFEST_PATH),
        "services": services,
        "blockers": tuple(dict.fromkeys(blockers)),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def service_health_from_spec(
    spec: ServiceHealthSpec,
    state_dir: Path,
    observed_at: datetime,
    *,
    pid_is_alive: Callable[[int], bool],
    lock_owner_is_active: Callable[[Path], bool] | None = None,
) -> dict[str, object]:
    """Evaluate one service health file, useful cycle, and safety contract."""
    path = state_dir / spec.health_file
    lock_path = state_dir / spec.lock_file
    label = spec.label
    if not spec.enabled:
        return {
            "service": spec.service,
            "task_name": spec.task_name,
            "command": spec.command,
            "required": spec.required,
            "enabled": False,
            "health_mode": spec.health_mode,
            "startup_trigger": spec.startup_trigger,
            "allow_start_if_on_batteries": spec.allow_start_if_on_batteries,
            "stop_if_going_on_batteries": spec.stop_if_going_on_batteries,
            "status": "DISABLED",
            "health_path": str(path),
            "lock_path": str(lock_path),
            "pid": None,
            "child_pid": None,
            "updated_at": None,
            "last_success_at": None,
            "age_seconds": None,
            "blockers": (),
            "execution_allowed": False,
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
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
    last_success_at = _useful_cycle_timestamp(spec, state_dir, payload, blockers)
    state_age_seconds = (
        (observed_at - updated_at).total_seconds() if updated_at is not None else None
    )
    age_seconds = (
        (observed_at - last_success_at).total_seconds()
        if last_success_at is not None
        else None
    )
    if updated_at is None:
        blockers.append(f"{label}_STATE_TIMESTAMP_INVALID")
    elif state_age_seconds is not None and (
        state_age_seconds < -5 or state_age_seconds > spec.max_health_age_seconds
    ):
        blockers.append(f"{label}_STATE_STALE")
    if last_success_at is None:
        blockers.append(f"{label}_USEFUL_CYCLE_TIMESTAMP_INVALID")
    elif age_seconds is not None and (
        age_seconds < -5
        or age_seconds
        > (spec.max_useful_cycle_age_seconds or spec.max_health_age_seconds)
    ):
        blockers.append(f"{label}_USEFUL_CYCLE_STALE")
    expected_status = "READY" if spec.health_mode == "SCHEDULED" else "RUNNING"
    if payload.get("status") != expected_status:
        status_blocker = (
            f"{label}_SCHEDULED_NOT_READY"
            if spec.health_mode == "SCHEDULED"
            else f"{label}_NOT_RUNNING"
        )
        blockers.append(status_blocker)
    if payload.get("execution_allowed") is not False:
        blockers.append(f"{label}_EXECUTION_AUTHORITY_DRIFT")
    if payload.get("live_eligibility_status") != "LIVE_ORDER_BLOCKED":
        blockers.append(f"{label}_LIVE_AUTHORITY_DRIFT")
    if not spec.allow_start_if_on_batteries:
        blockers.append(f"{label}_BATTERY_START_BLOCKED")
    if spec.stop_if_going_on_batteries:
        blockers.append(f"{label}_BATTERY_STOP_ENABLED")
    if spec.order_writing_authority:
        blockers.append(f"{label}_ORDER_WRITING_AUTHORITY_DRIFT")
    pid = _safe_int(payload.get("pid"))
    child_pid = _safe_int(payload.get("child_pid"))
    if spec.health_mode == "RESIDENT":
        if pid is None or pid < 1 or not pid_is_alive(pid):
            blockers.append(f"{label}_PID_NOT_ALIVE")
        lock_pid = _read_lock_pid(lock_path)
        if lock_pid is None:
            blockers.append(f"{label}_LOCK_MISSING_OR_INVALID")
        elif lock_owner_is_active is not None and not lock_owner_is_active(lock_path):
            blockers.append(f"{label}_LOCK_PID_NOT_ALIVE")
        elif lock_owner_is_active is None and not pid_is_alive(lock_pid):
            blockers.append(f"{label}_LOCK_PID_NOT_ALIVE")

    return {
        "service": spec.service,
        "task_name": spec.task_name,
        "command": spec.command,
        "required": spec.required,
        "enabled": spec.enabled,
        "health_mode": spec.health_mode,
        "startup_trigger": spec.startup_trigger,
        "allow_start_if_on_batteries": spec.allow_start_if_on_batteries,
        "stop_if_going_on_batteries": spec.stop_if_going_on_batteries,
        "status": "READY" if not blockers else "DEGRADED",
        "health_path": str(path),
        "lock_path": str(lock_path),
        "pid": pid,
        "child_pid": child_pid,
        "updated_at": payload.get("updated_at"),
        "last_success_at": (
            last_success_at.isoformat() if last_success_at is not None else None
        ),
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "blockers": tuple(dict.fromkeys(blockers)),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _service_spec(value: object) -> ServiceHealthSpec:
    if not isinstance(value, dict):
        raise ValueError("service manifest entries must be objects")
    payload = cast(dict[str, object], value)
    service = _required_string(payload, "service")
    required = _required_bool(payload, "required")
    enabled = _required_bool(payload, "enabled")
    useful_state_file = _optional_safe_relative_path(payload, "useful_state_file")
    useful_timestamp_field = _optional_string(payload, "useful_timestamp_field")
    max_useful_cycle_age_seconds = _optional_positive_float(
        payload,
        "max_useful_cycle_age_seconds",
    )
    useful_contract = (
        useful_state_file,
        useful_timestamp_field,
        max_useful_cycle_age_seconds,
    )
    if any(item is not None for item in useful_contract) and not all(
        item is not None for item in useful_contract
    ):
        raise ValueError("service manifest useful cycle fields must be set together")
    if required and not enabled:
        raise ValueError("required service manifest entries cannot be disabled")
    return ServiceHealthSpec(
        service=service,
        task_name=_required_string(payload, "task_name"),
        command=_required_string(payload, "command"),
        mode=_required_string(payload, "mode"),
        required=required,
        health_file=_safe_relative_file(payload, "health_file"),
        lock_file=_safe_relative_file(payload, "lock_file"),
        max_health_age_seconds=_required_positive_float(
            payload,
            "max_health_age_seconds",
        ),
        startup_trigger=_required_string(payload, "startup_trigger"),
        allow_start_if_on_batteries=_required_bool(
            payload,
            "allow_start_if_on_batteries",
        ),
        stop_if_going_on_batteries=_required_bool(
            payload,
            "stop_if_going_on_batteries",
        ),
        order_writing_authority=_required_bool(payload, "order_writing_authority"),
        health_mode=_health_mode(payload),
        enabled=enabled,
        useful_state_file=useful_state_file,
        useful_timestamp_field=useful_timestamp_field,
        max_useful_cycle_age_seconds=max_useful_cycle_age_seconds,
    )


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"service manifest {key} must be a non-empty string")
    return value.strip()


def _required_bool(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"service manifest {key} must be a boolean")
    return value


def _health_mode(payload: dict[str, object]) -> str:
    value = payload.get("health_mode", "RESIDENT")
    if value not in {"RESIDENT", "SCHEDULED"}:
        raise ValueError("service manifest health_mode must be RESIDENT or SCHEDULED")
    return str(value)


def _required_positive_float(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool):
        raise ValueError(f"service manifest {key} must be positive")
    try:
        parsed = float(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"service manifest {key} must be positive") from error
    if parsed <= 0:
        raise ValueError(f"service manifest {key} must be positive")
    return parsed


def _optional_positive_float(payload: dict[str, object], key: str) -> float | None:
    if key not in payload:
        return None
    return _required_positive_float(payload, key)


def _safe_relative_file(payload: dict[str, object], key: str) -> str:
    value = _required_string(payload, key)
    path = Path(value)
    if path.is_absolute() or len(path.parts) != 1 or value in {".", ".."}:
        raise ValueError(f"service manifest {key} must be a simple file name")
    return value


def _optional_string(payload: dict[str, object], key: str) -> str | None:
    if key not in payload:
        return None
    return _required_string(payload, key)


def _optional_safe_relative_path(payload: dict[str, object], key: str) -> str | None:
    value = _optional_string(payload, key)
    if value is None:
        return None
    path = Path(value)
    unsafe_part = any(part in {"", ".", ".."} for part in path.parts)
    if path.is_absolute() or not path.parts or unsafe_part:
        raise ValueError(f"service manifest {key} must be a safe relative path")
    return value


def _useful_cycle_timestamp(
    spec: ServiceHealthSpec,
    state_dir: Path,
    health_payload: dict[str, object],
    blockers: list[str],
) -> datetime | None:
    if spec.useful_state_file is None:
        successful = _parse_datetime(health_payload.get("last_success_at"))
        return successful or _parse_datetime(health_payload.get("updated_at"))
    if spec.useful_timestamp_field is None or spec.max_useful_cycle_age_seconds is None:
        blockers.append(f"{spec.label}_USEFUL_CYCLE_CONTRACT_INVALID")
        return None
    useful_path = state_dir / spec.useful_state_file
    try:
        loaded = json.loads(useful_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        blockers.append(f"{spec.label}_USEFUL_CYCLE_STATE_MISSING")
        return None
    except (OSError, json.JSONDecodeError):
        blockers.append(f"{spec.label}_USEFUL_CYCLE_STATE_INVALID")
        return None
    if not isinstance(loaded, dict):
        blockers.append(f"{spec.label}_USEFUL_CYCLE_STATE_INVALID")
        return None
    return _parse_datetime(loaded.get(spec.useful_timestamp_field))


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
        return None
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
        return SingleInstanceLease._read_lock_owner(path)[0]
    except RuntimeError:
        return None

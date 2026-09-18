"""Secret-safe whole-system operator report generation."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ai4binance.config import Settings
from ai4binance.enterprise import GpuResourceGovernor
from ai4binance.enterprise.oek_compliance import audit_oek_constitution
from ai4binance.ops.runtime import SingleInstanceLease
from ai4binance.ops.service_health import startup_health_from_manifest
from ai4binance.ops.startup_replay import startup_replay_payload
from ai4binance.ops.user_reports import (
    canonical_system_root,
    render_professional_summary,
    user_report_paths,
    write_user_report_files,
)
from ai4binance.reporting import to_primitive
from ai4binance.skills.continuous_runtime import read_skill_discovery_status

__all__ = [
    "SystemReportResult",
    "build_system_report",
    "local_advisory_health_payload",
    "runtime_state_payload",
    "startup_health_payload",
    "startup_replay_payload",
    "system_report_summary_payload",
]

_LOCAL_ADVISORY_MODEL = "qwen3:8b"
_LOCAL_ADVISORY_PROVIDER = "llama.cpp"
_LOCAL_ADVISORY_ENDPOINT_PREFIX = "http://127.0.0.1:8080"
_AUTO_LEARN_CAPABILITIES = (
    "observe",
    "analyze",
    "extract_lessons",
    "detect_patterns",
    "generate_hypotheses",
    "propose_experiments",
    "propose_improvements",
)


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
    telemetry = _telemetry_assessment_snapshot(payload.get("telemetry_assessment"))
    contract = _advanced_contract_snapshot(
        payload.get("advanced_agent_operating_contract")
    )
    contract_preview = _bounded_advanced_contract_preview(contract)
    dashboard_cards = _system_report_dashboard_cards_payload(
        {
            "report_id": payload.get("report_id"),
            "status": payload.get("status"),
            "blockers": payload.get("blockers", ()),
            "live_eligibility_status": payload.get("live_eligibility_status"),
            "advanced_agent_operating_contract": contract,
        }
    )
    dashboard_cards_preview = _bounded_dashboard_cards_preview(dashboard_cards)
    return {
        "command": "system-report",
        "report_id": payload.get("report_id"),
        "observed_at": payload.get("observed_at"),
        "status": payload.get("status"),
        "components": {
            name: {
                "status": component.get("status", component.get("state", "UNKNOWN")),
                "blockers": _blocker_tuple(component.get("blockers")),
                **(
                    {"auto_learn": _auto_learn_preview(component.get("auto_learn"))}
                    if name == "local_advisory"
                    else {}
                ),
            }
            for name, component in components.items()
        },
        "telemetry_assessment": telemetry,
        "advanced_agent_operating_contract": contract_preview,
        "blockers": payload.get("blockers", ()),
        "markdown_path": str(result.markdown_path),
        "json_path": str(result.json_path),
        "latest_json_path": str(result.latest_json_path),
        "details": "FULL_EVIDENCE_PERSISTED_TO_JSON",
        "dashboard_cards": dashboard_cards_preview,
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _auto_learn_preview(payload: object) -> dict[str, object]:
    auto_learn = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
    engine_raw = auto_learn.get("engine")
    engine = cast(dict[str, object], engine_raw) if isinstance(engine_raw, dict) else {}
    return {
        "status": auto_learn.get("status", "UNKNOWN"),
        "mode": auto_learn.get("mode", "RESEARCH_ONLY"),
        "engine": {
            "provider": engine.get("provider", _LOCAL_ADVISORY_PROVIDER),
            "model": engine.get("model", _LOCAL_ADVISORY_MODEL),
        },
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
    root = canonical_system_root(workspace_root or Path.cwd())
    (
        accounting_status_payload,
        lean_governance_payload,
        opportunities_payload,
        quality_system_audit_payload,
        repository_cleanup_audit_payload,
        validation_summary_payload,
    ) = _load_cli_component_builders()
    advanced_contract_payload = _load_advanced_agent_contract_builder()
    telemetry_governor = GpuResourceGovernor()
    telemetry_snapshot = telemetry_governor.collect_telemetry()
    telemetry_assessment = telemetry_snapshot.assess(
        telemetry_governor.policy.vram_headroom_percent
    )

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
        "startup_replay": _safe_component(
            "startup-replay", lambda: startup_replay_payload(settings)
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
        "advanced_agent_contract": _safe_component(
            "advanced-agent-operating-contract",
            advanced_contract_payload,
        ),
    }
    component_blockers = _component_blockers(components)
    startup_component = components["startup"]
    startup_blockers = _blocker_tuple(startup_component.get("blockers", ()))
    startup_replay_component = components["startup_replay"]
    startup_replay_blockers = _blocker_tuple(
        startup_replay_component.get("blockers", ())
    )
    status = (
        "DEGRADED"
        if startup_blockers or startup_replay_blockers
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
        "advanced_agent_operating_contract": _advanced_contract_snapshot(
            components.get("advanced_agent_contract")
        ),
        "telemetry_assessment": to_primitive(telemetry_assessment),
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
    return startup_health_from_manifest(settings, observed_at)


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
    raw_learning = payload.get("controlled_learning")
    controlled_learning: dict[str, object] = (
        cast(dict[str, object], raw_learning)
        if isinstance(raw_learning, dict)
        else {
            "status": "NOT_RUN",
            "summary_id": None,
            "lesson_count": 0,
            "experiment_count": 0,
            "execution_allowed": False,
            "risk_change_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
        }
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
        "controlled_learning": {
            "status": controlled_learning.get("status", "NOT_RUN"),
            "summary_id": controlled_learning.get("summary_id"),
            "lesson_count": controlled_learning.get("lesson_count", 0),
            "experiment_count": controlled_learning.get("experiment_count", 0),
            "execution_allowed": False,
            "risk_change_allowed": False,
            "promotion_status": controlled_learning.get(
                "promotion_status", "RESEARCH_ONLY"
            ),
        },
        "blockers": tuple(dict.fromkeys((*issues, *blockers))),
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def local_advisory_health_payload(settings: Settings) -> dict[str, object]:
    """Verify the only production advisory route: loopback llama.cpp qwen3:8b."""
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

    if health.get("provider") != _LOCAL_ADVISORY_PROVIDER:
        blockers.append("LLAMA_CPP_PROVIDER_MISMATCH")
    if health.get("status") != "RUNNING":
        blockers.append("QWEN_PROMPTER_NOT_RUNNING")
    if health.get("model") != _LOCAL_ADVISORY_MODEL:
        blockers.append("QWEN_PROMPTER_MODEL_MISMATCH")
    endpoint = str(health.get("endpoint", ""))
    if not endpoint.startswith(_LOCAL_ADVISORY_ENDPOINT_PREFIX):
        blockers.append("LLAMA_CPP_ENDPOINT_NOT_LOOPBACK")

    pid = _safe_int(health.get("provider_pid"))
    if pid is None:
        pid = _safe_int(health.get("pid"))
    if pid is None or pid < 1 or not SingleInstanceLease._pid_is_alive(pid):
        blockers.append("QWEN_PROMPTER_PID_NOT_ALIVE")
    listener_pids = tuple(
        sorted(
            pid
            for pid in (
                _safe_int(value) for value in _as_sequence(health.get("listener_pids"))
            )
            if pid is not None
        )
    )
    if not listener_pids:
        blockers.append("QWEN_PROMPTER_LISTENER_MISSING")
    elif not any(SingleInstanceLease._pid_is_alive(value) for value in listener_pids):
        blockers.append("QWEN_PROMPTER_LISTENER_NOT_ALIVE")
    auto_learn = _auto_learn_payload(
        health,
        status=str(health.get("status", "UNKNOWN")),
    )

    return {
        "command": "local-advisory-health",
        "status": "READY" if not blockers else "DEGRADED",
        "provider": _LOCAL_ADVISORY_PROVIDER,
        "endpoint": endpoint or _LOCAL_ADVISORY_ENDPOINT_PREFIX,
        "model": _LOCAL_ADVISORY_MODEL,
        "loopback_only": True,
        "listener_pids": listener_pids,
        "prompter_state_path": str(state_path),
        "prompter_status": health.get("status"),
        "prompter_pid": pid,
        "auto_learn": auto_learn,
        "blockers": tuple(dict.fromkeys(blockers)),
        "advisory_mode": "RESEARCH_ONLY",
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _auto_learn_payload(
    health: Mapping[str, object],
    *,
    status: str,
) -> dict[str, object]:
    raw_auto_learn = health.get("auto_learn")
    auto_learn = (
        cast(dict[str, object], raw_auto_learn)
        if isinstance(raw_auto_learn, dict)
        else {}
    )
    raw_engine = auto_learn.get("engine")
    engine = cast(dict[str, object], raw_engine) if isinstance(raw_engine, dict) else {}
    raw_authority = auto_learn.get("authority")
    authority = (
        cast(dict[str, object], raw_authority)
        if isinstance(raw_authority, dict)
        else {}
    )
    raw_promotion = auto_learn.get("promotion")
    promotion = (
        cast(dict[str, object], raw_promotion)
        if isinstance(raw_promotion, dict)
        else {}
    )
    raw_execution = auto_learn.get("execution")
    execution = (
        cast(dict[str, object], raw_execution)
        if isinstance(raw_execution, dict)
        else {}
    )
    raw_learning = auto_learn.get("learning")
    learning = (
        cast(dict[str, object], raw_learning) if isinstance(raw_learning, dict) else {}
    )
    capabilities = cast(
        tuple[object, ...],
        auto_learn.get("capabilities", _AUTO_LEARN_CAPABILITIES),
    )
    return {
        "status": str(auto_learn.get("status", status)),
        "mode": str(auto_learn.get("mode", "RESEARCH_ONLY")),
        "engine": {
            "provider": str(engine.get("provider", _LOCAL_ADVISORY_PROVIDER)),
            "model": str(engine.get("model", _LOCAL_ADVISORY_MODEL)),
            "runtime": str(engine.get("runtime", _LOCAL_ADVISORY_PROVIDER)),
        },
        "capabilities": tuple(str(capability) for capability in capabilities),
        "authority": {
            "modify_runtime": bool(authority.get("modify_runtime", False)),
            "modify_strategy": bool(authority.get("modify_strategy", False)),
            "modify_parameters": bool(authority.get("modify_parameters", False)),
            "modify_risk_limits": bool(authority.get("modify_risk_limits", False)),
            "promote_strategy": bool(authority.get("promote_strategy", False)),
            "authorize_execution": bool(authority.get("authorize_execution", False)),
            "deploy_code": bool(authority.get("deploy_code", False)),
        },
        "promotion": {
            "human_approval_required": bool(
                promotion.get("human_approval_required", True)
            ),
        },
        "execution": {
            "live_execution": bool(execution.get("live_execution", False)),
        },
        "learning": {
            "model_weight_update": bool(learning.get("model_weight_update", False)),
            "external_memory": bool(learning.get("external_memory", True)),
            "evidence_registry": bool(learning.get("evidence_registry", True)),
            "lesson_registry": bool(learning.get("lesson_registry", True)),
            "experiment_registry": bool(learning.get("experiment_registry", True)),
        },
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


def _load_advanced_agent_contract_builder() -> Callable[[], dict[str, object]]:
    from ai4binance.cli.status import advanced_agent_operating_contract_payload

    return advanced_agent_operating_contract_payload


def _system_report_dashboard_cards_payload(
    report_summary: dict[str, object],
) -> dict[str, object]:
    from ai4binance.enterprise.dashboard import system_report_dashboard_cards_payload

    return system_report_dashboard_cards_payload(report_summary)


def _bounded_dashboard_cards_preview(
    payload: dict[str, object],
) -> dict[str, object]:
    blocked_metric_ids = _blocker_tuple(payload.get("blocked_metric_ids"))[:8]
    open_action_refs = _blocker_tuple(payload.get("open_action_refs"))[:4]
    return {
        "source": payload.get("source", "system-report"),
        "metric_count": payload.get("metric_count", 0),
        "blocked_metric_count": payload.get("blocked_metric_count", 0),
        "watch_metric_count": payload.get("watch_metric_count", 0),
        "blocked_metric_ids": blocked_metric_ids,
        "open_action_refs": open_action_refs,
    }


def _bounded_advanced_contract_preview(
    payload: dict[str, object],
) -> dict[str, object]:
    human_controls = payload.get("human_approval_controls")
    if isinstance(human_controls, dict):
        human_payload = cast(dict[str, object], human_controls)
    else:
        human_payload = {}
    return {
        "status": payload.get("status", "UNKNOWN"),
        "guardrails": _blocker_tuple(payload.get("guardrails"))[:8],
        "human_approval_controls": {
            "gates": _blocker_tuple(human_payload.get("gates"))[:8],
        },
    }


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


def _advanced_contract_snapshot(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {
            "status": "DEGRADED",
            "blockers": ("ADVANCED_AGENT_CONTRACT_UNAVAILABLE",),
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
    payload = cast(dict[str, object], value)
    human_controls = payload.get("human_approval_controls")
    if isinstance(human_controls, dict):
        human_payload = cast(dict[str, object], human_controls)
    else:
        human_payload = {}
    return {
        "status": payload.get("status", payload.get("state", "READY")),
        "orchestration": payload.get("orchestration"),
        "automation_scope": payload.get("automation_scope"),
        "execution_scope": payload.get("execution_scope"),
        "guardrails": _blocker_tuple(payload.get("guardrails")),
        "auditable_traceability": _blocker_tuple(payload.get("auditable_traceability")),
        "human_approval_controls": {
            "mode": human_payload.get("mode"),
            "required_at": human_payload.get("required_at"),
            "gates": _blocker_tuple(human_payload.get("gates")),
        },
        "blockers": _blocker_tuple(payload.get("blockers")),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }


def _telemetry_assessment_snapshot(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {
            "healthy": False,
            "source_label": "UNKNOWN",
            "blockers": ("CUDA_UNAVAILABLE",),
        }
    payload = cast(dict[str, object], value)
    return {
        "healthy": bool(payload.get("healthy", False)),
        "source_label": str(payload.get("source_label", "UNKNOWN")),
        "blockers": _blocker_tuple(payload.get("blockers")),
    }


def _persist_report(
    root: Path,
    payload: dict[str, object],
    observed_at: datetime,
) -> SystemReportResult:
    stamp = observed_at.strftime("%Y%m%dT%H%M%SZ")
    artifact_dir = root / "runtime" / "artifacts" / "system_audit"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    paths = user_report_paths(
        root,
        "audit",
        stamp,
        file_stem="system_report",
        latest_stem="system_latest",
    )
    markdown_path = paths.markdown_path
    json_path = artifact_dir / f"system-report-{stamp}.json"
    latest_json_path = artifact_dir / "system-report-latest.json"
    payload["markdown_path"] = str(markdown_path)
    payload["json_path"] = str(json_path)
    payload["latest_json_path"] = str(latest_json_path)
    payload["latest_markdown_path"] = str(paths.latest_markdown_path)
    payload["user_latest_json_path"] = str(paths.latest_json_path)
    primitive = to_primitive(payload)
    json_text = json.dumps(primitive, ensure_ascii=False, indent=2, sort_keys=True)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    latest_json_path.write_text(json_text + "\n", encoding="utf-8")
    write_user_report_files(
        paths,
        cast(dict[str, object], primitive),
        _render_markdown(payload, json_path),
    )
    return SystemReportResult(
        payload=payload,
        markdown_path=markdown_path,
        json_path=json_path,
        latest_json_path=latest_json_path,
    )


def _render_markdown(payload: dict[str, object], json_path: Path) -> str:
    components = cast(dict[str, dict[str, object]], payload["components"])
    telemetry = _telemetry_assessment_snapshot(payload.get("telemetry_assessment"))
    contract = _advanced_contract_snapshot(
        payload.get("advanced_agent_operating_contract")
    )
    human_controls = cast(
        dict[str, object],
        contract.get("human_approval_controls", {}),
    )
    guardrail_text = ", ".join(_blocker_tuple(contract.get("guardrails", ())))
    traceability_text = ", ".join(
        _blocker_tuple(contract.get("auditable_traceability", ()))
    )
    human_gate_text = ", ".join(_blocker_tuple(human_controls.get("gates", ())))
    telemetry_blockers_text = (
        ", ".join(_blocker_tuple(telemetry.get("blockers", ()))) or "-"
    )
    component_lines = [
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
        component_lines.append(f"| `{name}` | `{status}` | {blocker_text or '-'} |")
    return render_professional_summary(
        title=f"AI4BINANCE System Audit Report - {payload['observed_at']}",
        observed_at=payload["observed_at"],
        status=payload["status"],
        summary=(
            "This report summarizes system health, governance blockers, local "
            "advisory status, runtime readiness, validation visibility, and "
            "audit evidence. It is an operator report and does not grant "
            "execution authority."
        ),
        sections=(
            (
                "GPU Telemetry Assessment",
                (
                    f"- Healthy: `{telemetry.get('healthy', False)}`",
                    f"- Source: `{telemetry.get('source_label', 'UNKNOWN')}`",
                    f"- Blockers: {telemetry_blockers_text}",
                ),
            ),
            (
                "Advanced Agent Contract",
                (
                    f"- Orchestration: `{_contract_value(contract, 'orchestration')}`",
                    (
                        "- Automation scope: "
                        f"`{_contract_value(contract, 'automation_scope')}`"
                    ),
                    (
                        "- Execution scope: "
                        f"`{_contract_value(contract, 'execution_scope')}`"
                    ),
                    f"- Guardrails: {guardrail_text or '-'}",
                    f"- Auditable traceability: {traceability_text or '-'}",
                    (
                        "- Human approval mode: "
                        f"`{human_controls.get('mode', 'HUMAN_IN_THE_LOOP')}`"
                    ),
                    f"- Human approval gates: {human_gate_text or '-'}",
                ),
            ),
            ("Components", tuple(component_lines)),
            ("Evidence Paths", (f"- Full JSON evidence: `{json_path}`",)),
        ),
        blockers=_blocker_tuple(payload.get("blockers", ())),
    )


def _contract_value(contract: Mapping[str, object], key: str) -> object:
    defaults = {
        "orchestration": "MULTI_STEP_WORKFLOWS",
        "automation_scope": "REPETITIVE_OPERATIONS",
        "execution_scope": "END_TO_END_OPERATIONS",
    }
    return contract.get(key, defaults[key])


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


def _as_sequence(value: object) -> tuple[object, ...]:
    if isinstance(value, list | tuple):
        return tuple(value)
    if value is None:
        return ()
    return (value,)

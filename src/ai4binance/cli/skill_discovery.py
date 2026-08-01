"""CLI adapter for continuous Agent Skill discovery."""

from __future__ import annotations

from ai4binance.cli.output import render_payload
from ai4binance.config import Settings
from ai4binance.skills.continuous_runtime import (
    SkillDiscoverySupervisor,
    build_skill_discovery_runtime,
    read_skill_discovery_status,
    report_payload,
)


def run_skill_discovery_command(
    command: str,
    settings: Settings,
    *,
    output_format: str,
    source_file: str | None,
    max_candidates: int,
    min_score: float,
    interval_seconds: float | None,
    max_cycles: int | None,
) -> int:
    if command == "skill-discovery-status":
        payload = read_skill_discovery_status(settings)
        print(render_payload(payload, output_format=output_format, command=command))
        return 0 if not payload["blockers"] else 2

    runtime = build_skill_discovery_runtime(
        settings,
        source_file=source_file,
        max_candidates=max_candidates,
        min_score=min_score,
    )
    if command == "skill-discovery-once":
        report = runtime.run_once()
        payload = report_payload(command, report)
        print(render_payload(payload, output_format=output_format, command=command))
        return 0 if not payload["blockers"] else 2

    if command == "skill-discovery-daemon":
        supervisor = SkillDiscoverySupervisor(
            runtime=runtime,
            interval_seconds=(
                interval_seconds or settings.skill_discovery_interval_seconds
            ),
            lock_path=runtime.engine.state_path.with_name("skill-discovery.lock"),
        )
        try:
            completed = supervisor.run(max_cycles=max_cycles)
        except RuntimeError as error:
            payload = _daemon_blocked_payload(command, error)
            print(render_payload(payload, output_format=output_format, command=command))
            return 2
        payload = {
            "command": command,
            "status": "STOPPED",
            "completed_cycles": completed,
            "blockers": (),
            "execution_allowed": False,
            "installation_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        }
        print(render_payload(payload, output_format=output_format, command=command))
        return 0

    raise ValueError(f"unsupported skill discovery command: {command}")


def _daemon_blocked_payload(command: str, error: RuntimeError) -> dict[str, object]:
    message = str(error)
    blocker = (
        "SKILL_DISCOVERY_ALREADY_RUNNING"
        if message == "runtime instance is already active"
        else "SKILL_DISCOVERY_LOCK_REVIEW_REQUIRED"
    )
    return {
        "command": command,
        "status": "BLOCKED",
        "blockers": (blocker,),
        "reason": message,
        "execution_allowed": False,
        "installation_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

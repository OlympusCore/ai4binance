"""Adapt Codex lifecycle events to the canonical repository validator."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ai4binance.governance.constitution_sync import (
    build_quality_gate_workspace_attestation,
)
from ai4binance.governance.repository_validator import validate_repository
from ai4binance.infrastructure.persistence.safe_json import write_json_object_verified

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = Path("runtime/artifacts/repository_validation/governance/codex_hooks")
CONTEXT = (
    "For repository changes, resolve terminology, naming, and technology ownership "
    "through config/governance/governance_enforcement_fabric.yaml before editing. "
    "Reuse canonical owners and preserve unrelated changes. The Stop hook runs the "
    "existing repository validator after workspace changes; its result does not "
    "replace the required quality profile or human approval. Never claim completion "
    "with unresolved findings. Only repair changes already authorized by the user; "
    "read-only requests and protected-document approval boundaries still apply. "
    "Preserve RESEARCH_ONLY and LIVE_ORDER_BLOCKED."
)


def _write(path: Path, payload: dict[str, object]) -> None:
    write_json_object_verified(
        path, payload, blocker="CODEX_GOVERNANCE_EVIDENCE_WRITE_FAILED", indent=2
    )


def _snapshot(root: Path) -> dict[str, str]:
    snapshot = build_quality_gate_workspace_attestation(root).to_payload()
    if snapshot["git_commit"] == "UNKNOWN":
        raise ValueError("workspace Git subject is unavailable")
    return snapshot


def _blocked(reason: str, *, already_continued: bool) -> dict[str, object]:
    if already_continued:
        return {
            "continue": False,
            "stopReason": "CODEX_GOVERNANCE_BLOCKED",
            "systemMessage": reason,
        }
    return {"decision": "block", "reason": reason}


def handle_event(payload: dict[str, object], root: Path = ROOT) -> dict[str, object]:
    """Observe changes and delegate rules without creating another validator."""
    event = payload.get("hook_event_name")
    if event not in {"UserPromptSubmit", "Stop"}:
        raise ValueError("unsupported Codex hook event")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("Codex session identity is required")
    active = payload.get("stop_hook_active", False)
    if not isinstance(active, bool):
        raise ValueError("stop_hook_active must be a boolean")
    root = root.resolve()
    destination = (root / EVIDENCE_ROOT).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("hook evidence must remain inside the repository")
    state_path = destination / (sha256(session_id.encode()).hexdigest() + ".json")
    state: dict[str, object] = {}
    if state_path.exists():
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("hook state must be an object")
        state = loaded
    before = _snapshot(root)
    if event == "UserPromptSubmit":
        # A Stop continuation is a new prompt; retain the original failed baseline.
        if state.get("pending") is not True:
            _write(state_path, {"baseline": before, "pending": False})
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": CONTEXT,
            }
        }
    if state.get("baseline") == before and state.get("pending") is not True:
        # No source changes is not a declaration that the repository is compliant.
        return {}

    report = validate_repository(root)
    after = _snapshot(root)
    blockers = [
        {"kind": finding.kind.value, "path": finding.path}
        for finding in report.findings
        if finding.blocker
    ]
    if after != before:
        blockers.append({"kind": "WORKSPACE_CHANGED_DURING_VALIDATION", "path": "."})
    receipt_path = destination / "runs" / f"{uuid4().hex}.json"
    _write(
        receipt_path,
        {
            "schema_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "validator": "ai4binance.governance.repository_validator",
            "workspace_attestation": before,
            "workspace_stable": after == before,
            "repository_status": report.status.value,
            "artifact_count": report.artifact_count,
            "blockers": blockers,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    _write(state_path, {"baseline": after, "pending": bool(blockers) and not active})
    if blockers:
        summary = "; ".join(f"{item['kind']}: {item['path']}" for item in blockers[:8])
        return _blocked(
            "CODEX_GOVERNANCE_BLOCKED. Canonical repository validation found: "
            f"{summary}. Evidence: {receipt_path.relative_to(root).as_posix()}. "
            "Do not claim successful completion. Correct only already-authorized "
            "changes, preserve other work, and rerun the required quality profile. "
            "For read-only work, inherited blockers, or missing approval, report "
            "BLOCKED and the evidence instead of expanding scope. "
            "RESEARCH_ONLY; LIVE_ORDER_BLOCKED.",
            already_continued=active,
        )
    return {
        "systemMessage": (
            "Canonical repository validation passed for the observed stable "
            "workspace. Required quality and human approval remain independent. "
            f"Evidence: {receipt_path.relative_to(root).as_posix()}"
        )
    }


def main() -> int:
    """Emit the documented Codex hook protocol, including fail-closed errors."""
    payload: object = None
    try:
        raw = sys.stdin.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("hook input exceeds its bounded size")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be an object")
        result = handle_event(payload)
    except Exception as exc:  # Fail closed without leaking prompt or source content.
        result = _blocked(
            f"CODEX_GOVERNANCE_HOOK_ERROR: {type(exc).__name__}. "
            "Validation is NOT_VERIFIED. Report the hook failure; do not claim "
            "compliance or expand the authorized scope. LIVE_ORDER_BLOCKED.",
            already_continued=isinstance(payload, dict)
            and payload.get("stop_hook_active") is True,
        )
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

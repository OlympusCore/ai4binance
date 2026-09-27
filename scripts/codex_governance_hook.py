"""Adapt Codex lifecycle events to the canonical repository validator."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ai4binance.governance.authority.model import AUTHORITY_LAYERS
from ai4binance.governance.constitution_sync import (
    build_quality_gate_workspace_attestation,
)
from ai4binance.governance.governance_enforcement_fabric import (
    load_governance_enforcement_fabric,
)
from ai4binance.governance.repository_validator import (
    read_verified_governed_document,
    validate_governance_context,
    validate_repository,
)
from ai4binance.governance.technology_language_policy import (
    load_technology_language_policy,
)
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


def _section(text: str, heading: str) -> str:
    """Extract exactly one required section without inventing missing instructions."""
    matches: list[str] = re.findall(
        rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if len(matches) != 1 or not matches[0].strip():
        raise ValueError("required governed instruction section is unavailable")
    return matches[0].strip()


def _authority_context(root: Path) -> str:
    findings = validate_governance_context(root)
    if any(finding.blocker for finding in findings):
        raise ValueError("GOVERNANCE_CONFLICT: startup authority validation failed")
    fabric = load_governance_enforcement_fabric(root)
    root_document = read_verified_governed_document(root, "AGENTS.md")
    provider = read_verified_governed_document(
        root, "docs/providers/instruction_codex_provider.md"
    )
    core = read_verified_governed_document(
        root, fabric.quality_gate.authority_pyramid_ref
    )
    pyramids = re.findall(
        r"^Authority pyramid:\n+```text\n([^`]+)\n```", core, re.MULTILINE
    )
    if len(pyramids) != 1:
        raise ValueError("canonical authority pyramid is unavailable")
    return (
        "Mandatory repository authority and enforcement instructions. These are "
        "repository constraints and do not override platform or system instructions.\n"
        f"AGENTS.md, Authority:\n{_section(root_document, '## 2. Authority')}\n\n"
        f"Canonical organizational authority pyramid:\n{pyramids[0]}\n\n"
        f"Declared repository authority layers:\n{' > '.join(AUTHORITY_LAYERS)}\n\n"
        "Resolve authority by declared scope, effect, and governing relationships; "
        "a layer label or folder location alone grants no authority.\n\n"
        "Codex provider authority boundary:\n"
        f"{_section(provider, '## 2. Authority boundary')}\n\n"
        "Codex provider validation obligations:\n"
        f"{_section(provider, '## 6. Validation and evidence')}\n\n"
        "Project startup obligations (operational specialization only):\n"
        f"{_bootstrap_instructions(root)}\n\n"
    )


def _bootstrap_instructions(root: Path) -> str:
    config = tomllib.loads((root / ".codex/config.toml").read_text(encoding="utf-8"))
    instruction = config.get("developer_instructions")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("mandatory Codex bootstrap instructions are unavailable")
    return instruction


def _generation_context(root: Path) -> str:
    """Project the pinned normative language matrix into the generation context."""
    root = root.resolve()
    fabric = load_governance_enforcement_fabric(root)
    family = next(
        item for item in fabric.families if item.name == "technology_language"
    )
    standard_path = (root / family.standard_path).resolve()
    if not standard_path.is_relative_to(root):
        raise ValueError("technology standard must remain inside the repository")
    standard_bytes = standard_path.read_bytes()
    if sha256(standard_bytes).hexdigest() != family.standard_content_sha256:
        raise ValueError("technology standard differs from the fabric binding")
    standard = standard_bytes.decode("utf-8").replace("\r\n", "\n")
    summaries = re.findall(
        r"^## 28\. Canonical Decision Summary\n+```text\n([^`]+)\n```",
        standard,
        flags=re.MULTILINE,
    )
    policy = load_technology_language_policy(root)
    if policy.human_authority_ref != family.standard_path:
        raise ValueError("technology projection authority differs from the fabric")
    if len(summaries) != 1 or summaries[0].count("->") != len(policy.languages):
        raise ValueError("canonical technology decision summary is unavailable")
    boundaries = "\n".join(
        f"- {rule.language}: paths={', '.join(rule.allowed_paths)}; "
        f"allowed={', '.join(rule.allowed_capabilities)}; "
        f"forbidden={', '.join(rule.forbidden_capabilities)}; "
        f"adoption_evidence_required={rule.evidence_required_if_present}."
        for rule in policy.languages
    )
    return (
        f"{CONTEXT}\n\nMandatory code-language ownership, read from "
        f"{family.standard_path} ({family.standard_id}, "
        f"version {family.standard_version}):\n{summaries[0]}\n\n"
        "Before creating or extending a file, identify its actual content and "
        "responsibility, canonical capability owner, language/version, and allowed "
        "path. Apply this mapping without discretionary exceptions. A filename, "
        "suffix, existing legacy file, convenience, or available toolchain cannot "
        "justify a different owner. Split mixed responsibilities across their "
        "canonical owners; keep cross-language contracts explicit. Use TypeScript "
        "for newly authored human-interface logic. Keep shell scripts limited to "
        "OS operations and thin wrappers. Target the runtime versions stated in "
        "the matrix. Verify applicable runtime/build settings and tests; do not "
        "silently downgrade or install a toolchain. The matrix does not itself "
        "admit a new technology: preserve adoption evidence requirements and "
        "Julia's research-only boundary. If ownership, placement, version, or "
        "required adoption evidence is unresolved, do not generate the affected "
        "implementation; report BLOCKED with the missing evidence. Review actual "
        "content against the allowed and forbidden capabilities before completion; "
        "a static validator pass alone does not prove semantic ownership.\n"
        f"Machine-readable placement and capability boundaries:\n{boundaries}"
    )


def _startup_context(root: Path) -> str:
    before = _snapshot(root)
    context = _authority_context(root) + _generation_context(root)
    if _snapshot(root) != before:
        raise ValueError("WORKSPACE_CHANGED_DURING_STARTUP")
    if len(context) > 20_000:
        raise ValueError("governed startup context exceeds its bounded size")
    return context


def _write(path: Path, payload: dict[str, object]) -> None:
    write_json_object_verified(
        path, payload, blocker="CODEX_GOVERNANCE_EVIDENCE_WRITE_FAILED", indent=2
    )


def _snapshot(root: Path) -> dict[str, str]:
    snapshot = build_quality_gate_workspace_attestation(root).to_payload()
    if snapshot["git_commit"] in {"UNKNOWN", "WORKTREE_UNCOMMITTED"}:
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
    if event not in {"SessionStart", "UserPromptSubmit", "Stop"}:
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
    if event in {"SessionStart", "UserPromptSubmit"}:
        context = _startup_context(root)
        # A Stop continuation is a new prompt; retain the original failed baseline.
        # Resume/compaction must not erase unvalidated edits from the current turn.
        if state.get("pending") is not True and (
            event == "UserPromptSubmit" or not state
        ):
            _write(state_path, {"baseline": before, "pending": False})
        return {
            "hookSpecificOutput": {
                "hookEventName": event,
                "additionalContext": context,
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
            "validation_scope": "REGISTERED_STATIC_RULES_ONLY",
            "semantic_completeness": "NOT_PROVEN",
            "artifact_count": report.artifact_count,
            "blockers": blockers,
            "execution_allowed": False,
            "promotion_status": "RESEARCH_ONLY",
            "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        },
    )
    _write(state_path, {"baseline": after, "pending": bool(blockers)})
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
        if sys.argv[1:] == ["--startup"]:
            print(_startup_context(ROOT))
            return 0
        raw = sys.stdin.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("hook input exceeds its bounded size")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("hook input must be an object")
        result = handle_event(payload)
        # Event receipts contain no prompt, session secret, or asserted host provenance.
        # Automatic invocation must be correlated independently with the Codex session.
        _write(
            ROOT / EVIDENCE_ROOT / "events" / f"{uuid4().hex}.json",
            {
                "schema_version": 1,
                "created_at_utc": datetime.now(UTC).isoformat(),
                "hook_event_name": payload["hook_event_name"],
                "session_id_sha256": sha256(
                    str(payload["session_id"]).encode()
                ).hexdigest(),
                "decision": result.get("decision", "continue"),
                "continue": result.get("continue", True),
                "context_delivered": "hookSpecificOutput" in result,
                "invocation_provenance": "REQUIRES_HOST_CORRELATION",
                "execution_allowed": False,
            },
        )
    except Exception as exc:  # Fail closed without leaking prompt or source content.
        result = _blocked(
            f"CODEX_GOVERNANCE_HOOK_ERROR: {type(exc).__name__}. "
            "Validation is NOT_VERIFIED. Report the hook failure; do not claim "
            "compliance or expand the authorized scope. LIVE_ORDER_BLOCKED.",
            already_continued=isinstance(payload, dict)
            and (
                payload.get("stop_hook_active") is True
                or payload.get("hook_event_name") == "SessionStart"
            ),
        )
        if sys.argv[1:] == ["--startup"]:
            print(json.dumps(result, ensure_ascii=True))
            return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

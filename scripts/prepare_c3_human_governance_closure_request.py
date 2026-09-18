from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_GOVERNANCE_GATE_REPORT = Path(
    "runtime/artifacts/quality/gate/governance_gate_latest.json"
)
DEFAULT_OUTPUT_JSON = Path(
    "runtime/artifacts/quality/gate/c3_human_governance_closure_request_latest.json"
)
DEFAULT_OUTPUT_MARKDOWN = Path(
    "runtime/artifacts/quality/gate/c3_human_governance_closure_request_latest.md"
)
CANONICAL_APPROVAL_TARGET = "runtime/artifacts/quality/gate/approval_record_latest.json"
CANONICAL_GOVERNANCE_TARGET = (
    "runtime/artifacts/quality/gate/governance_gate_latest.json"
)
REQUIRED_C3_ROLES = ("GovernanceOwner", "ConstitutionOwner")
DEFAULT_APPROVAL_ROLE = "GovernanceOwner"
LIFECYCLE_DEFINITION_PATH = Path("src/ai4binance/governance_primitives.py")
APPROVAL_CHECKLIST = (
    "Confirm the subject SHA-256 matches the reviewed governance gate artifact.",
    "Confirm the scope hash matches the reviewed change set.",
    "Use a unique approver_id and a unique principal_id for each approval.",
    (
        "Keep execution_allowed set to false and "
        "live_eligibility_status set to LIVE_ORDER_BLOCKED."
    ),
    (
        "Save the independently prepared approval artifact to the "
        "canonical approval record path."
    ),
    (
        "Re-run scripts/quality.ps1 with -ApprovalRecordPath pointing "
        "to the independent approval artifact."
    ),
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("governance gate report must be a JSON object")
    return payload


def _get_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"governance gate report field {key} must be an object")
    return value


def _get_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"governance gate report field {key} must be non-empty text")
    return value


def _get_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"governance gate report field {key} must be an integer")
    return value


def _optional_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _optional_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return list(value) if isinstance(value, list) else []


def _canonical_sha256(payload: dict[str, str]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lifecycle_definition_sha256(repository_root: Path) -> str:
    return hashlib.sha256(
        (repository_root / LIFECYCLE_DEFINITION_PATH).read_bytes()
    ).hexdigest()


def _relative_or_posix(path: Path, repository_root: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _required_roles(change_class: str, required_approval_count: int) -> tuple[str, ...]:
    if required_approval_count < 1:
        raise ValueError(
            "approval-required closure requests require at least one approval"
        )
    if change_class == "C3_GOVERNED" and required_approval_count == 2:
        return REQUIRED_C3_ROLES
    if required_approval_count == 1:
        return (DEFAULT_APPROVAL_ROLE,)
    return tuple(
        f"{DEFAULT_APPROVAL_ROLE}_{index}"
        for index in range(1, required_approval_count + 1)
    )


def _title_for_change_class(change_class: str) -> str:
    if change_class == "C3_GOVERNED":
        return "C3 Human Governance Closure Request"
    return f"{change_class} Human Governance Closure Request"


def _risk_level_for_change_class(change_class: str) -> str:
    if change_class == "C4_CONSEQUENTIAL":
        return "HIGH"
    if change_class == "C3_GOVERNED":
        return "MEDIUM"
    if change_class == "C2_BEHAVIORAL":
        return "MEDIUM"
    if change_class == "C1_LOW_RISK":
        return "LOW"
    return "INFO"


def build_closure_request(
    *,
    repository_root: Path,
    governance_gate_report_path: Path,
) -> dict[str, Any]:
    governance_gate = _load_json(governance_gate_report_path)
    approval_verification = _get_object(governance_gate, "approval_verification")
    subject_digest = _get_object(governance_gate, "subject_digest")
    change_set = _get_object(governance_gate, "change_set")
    deterministic_quality_gate = _get_object(
        governance_gate, "deterministic_quality_gate"
    )
    authority_baseline = _get_object(governance_gate, "authority_baseline")

    change_class = _get_text(approval_verification, "change_class")

    required_approval_count = _get_int(approval_verification, "required_approval_count")
    if required_approval_count < 1:
        raise ValueError(
            "closure request preparation requires approval-required changes"
        )
    required_roles = _required_roles(change_class, required_approval_count)

    prepared_at = datetime.now(UTC).replace(microsecond=0)
    expires_at = prepared_at + timedelta(days=1)
    source_governance_gate_report = _relative_or_posix(
        governance_gate_report_path,
        repository_root,
    )
    quality_gate_evidence_sha256 = _get_text(
        deterministic_quality_gate,
        "gate_evidence_sha256",
    )
    governance_gate_evidence_sha256 = _get_text(
        governance_gate,
        "gate_evidence_sha256",
    )
    evidence_hash = _optional_text(approval_verification, "evidence_hash")
    if not evidence_hash:
        evidence_hash = _canonical_sha256(
            {
                "deterministic_governance_gate_evidence_sha256": (
                    governance_gate_evidence_sha256
                ),
                "deterministic_quality_gate_evidence_sha256": (
                    quality_gate_evidence_sha256
                ),
            }
        )
    authority_family_sha256 = _get_text(
        approval_verification
        if _optional_text(approval_verification, "authority_family_sha256")
        else subject_digest,
        "authority_family_sha256",
    )
    lifecycle_definition_sha256 = _optional_text(
        approval_verification,
        "lifecycle_definition_sha256",
    ) or _lifecycle_definition_sha256(repository_root)
    authority_sources = [
        str(item).strip()
        for item in _optional_list(authority_baseline, "authority_sources")
        if str(item).strip()
    ]
    changed_paths = [
        str(item).strip()
        for item in _optional_list(change_set, "changed_paths")
        if str(item).strip()
    ]
    rollback_plan = [
        (
            "Revert only the reviewed change-set paths and regenerate the "
            "deterministic "
            "quality and governance gate artifacts for the reverted subject."
        ),
        (
            "Invalidate or replace any stale approval packet when subject SHA-256, "
            "scope hash, or evidence hashes change."
        ),
        (
            "Re-run scripts/quality.ps1 with the independently prepared "
            "approval record "
            "path only after the refreshed subject and evidence envelope are confirmed."
        ),
    ]
    behavior_risk_impact = {
        "summary": (
            "Approval packet authorizes implementation review state only; execution "
            "authority remains fail-closed."
        ),
        "risk_level": _risk_level_for_change_class(change_class),
        "execution_allowed": False,
        "promotion_status": "RESEARCH_ONLY",
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
    }

    template_records = []
    for index, role in enumerate(required_roles, start=1):
        template_records.append(
            {
                "approval_id": f"<set-by-independent-approver-{index}>",
                "work_order_id": f"c3-approval-work-order-{index}",
                "run_id": f"c3-approval-run-{index}",
                "trace_id": f"c3-approval-trace-{index}",
                "approver_id": f"<{role}-approver-id>",
                "principal_id": f"<{role}-principal-id>",
                "approver_role": role,
                "subject_ref": source_governance_gate_report,
                "status": "APPROVED_FOR_IMPLEMENTATION",
                "evidence_refs": [
                    "artifact:governance-report",
                    "artifact:deterministic-quality-gate",
                ],
                "change_class": change_class,
                "subject_sha256": _get_text(subject_digest, "subject_id"),
                "scope_hash": _get_text(change_set, "change_set_sha256"),
                "quality_gate_evidence_sha256": quality_gate_evidence_sha256,
                "governance_gate_evidence_sha256": governance_gate_evidence_sha256,
                "evidence_hash": evidence_hash,
                "authority_family_sha256": authority_family_sha256,
                "lifecycle_definition_sha256": lifecycle_definition_sha256,
                "approved_at_utc": "<set-by-independent-approver-utc>",
                "expires_at_utc": "<optional-expiry-utc>",
                "execution_allowed": False,
                "live_eligibility_status": "LIVE_ORDER_BLOCKED",
            }
        )

    return {
        "schema_version": "1.0.0",
        "artifact_origin": "deterministic_governance_closure_request",
        "prepared_at_utc": prepared_at.isoformat().replace("+00:00", "Z"),
        "recommended_expiry_utc": expires_at.isoformat().replace("+00:00", "Z"),
        "repository_root": str(repository_root.resolve()),
        "source_governance_gate_report": source_governance_gate_report,
        "canonical_approval_record_target": CANONICAL_APPROVAL_TARGET,
        "change_class": change_class,
        "required_approval_count": required_approval_count,
        "required_roles": list(required_roles),
        "subject_ref": source_governance_gate_report,
        "subject_sha256": _get_text(subject_digest, "subject_id"),
        "scope_hash": _get_text(change_set, "change_set_sha256"),
        "quality_gate_evidence_sha256": quality_gate_evidence_sha256,
        "governance_gate_evidence_sha256": governance_gate_evidence_sha256,
        "evidence_hash": evidence_hash,
        "authority_family_sha256": authority_family_sha256,
        "lifecycle_definition_sha256": lifecycle_definition_sha256,
        "affected_authority_surfaces": authority_sources,
        "affected_change_surfaces": changed_paths,
        "rollback_plan": rollback_plan,
        "behavior_risk_impact": behavior_risk_impact,
        "expected_post_approval_state": {
            "observed_approval_count": required_approval_count,
            "approval_verification": "PASS",
            "approved_transition_hard_veto": False,
        },
        "execution_allowed": False,
        "live_eligibility_status": "LIVE_ORDER_BLOCKED",
        "instructions": [
            (
                "Independent human approvers must create the final approval "
                "records out of band."
            ),
            "Each approval must use a unique approver_id and unique principal_id.",
            (
                "After independent approval, save the final artifact to "
                f"{CANONICAL_APPROVAL_TARGET}."
            ),
            (
                "Re-run scripts/quality.ps1 with -ApprovalRecordPath pointing "
                "to the independently prepared approval artifact."
            ),
        ],
        "approval_checklist": list(APPROVAL_CHECKLIST),
        "approval_record_template": template_records,
    }


def render_closure_request_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {_title_for_change_class(str(payload['change_class']))}",
        "",
        "## Status",
        f"- Prepared at (UTC): {payload['prepared_at_utc']}",
        f"- Recommended expiry (UTC): {payload['recommended_expiry_utc']}",
        f"- Change class: {payload['change_class']}",
        f"- Required approval count: {payload['required_approval_count']}",
        f"- Required roles: {', '.join(payload['required_roles'])}",
        f"- Execution allowed: {payload['execution_allowed']}",
        f"- Live eligibility status: {payload['live_eligibility_status']}",
        "",
        "## Bound Evidence",
        f"- Source governance gate report: {payload['source_governance_gate_report']}",
        (
            "- Canonical approval record target: "
            f"{payload['canonical_approval_record_target']}"
        ),
        f"- Subject SHA-256: `{payload['subject_sha256']}`",
        f"- Scope hash: `{payload['scope_hash']}`",
        (
            "- Deterministic quality gate evidence SHA-256: "
            f"`{payload['quality_gate_evidence_sha256']}`"
        ),
        (
            "- Deterministic governance gate evidence SHA-256: "
            f"`{payload['governance_gate_evidence_sha256']}`"
        ),
        f"- Approval evidence hash: `{payload['evidence_hash']}`",
        f"- Authority family SHA-256: `{payload['authority_family_sha256']}`",
        f"- Lifecycle definition SHA-256: `{payload['lifecycle_definition_sha256']}`",
        "",
        "## Affected Surfaces",
    ]
    lines.extend(
        f"- Authority surface: {item}"
        for item in payload["affected_authority_surfaces"]
    )
    lines.extend(
        f"- Change surface: {item}" for item in payload["affected_change_surfaces"]
    )
    behavior_risk_impact = payload["behavior_risk_impact"]
    expected_state = payload["expected_post_approval_state"]
    lines.extend(
        [
            "",
            "## Behavior And Risk Impact",
            f"- Summary: {behavior_risk_impact['summary']}",
            f"- Risk level: {behavior_risk_impact['risk_level']}",
            f"- Execution allowed: {behavior_risk_impact['execution_allowed']}",
            f"- Promotion status: {behavior_risk_impact['promotion_status']}",
            (
                "- Live eligibility status: "
                f"{behavior_risk_impact['live_eligibility_status']}"
            ),
            "",
            "## Expected Post-Approval State",
            (
                "- Expected observed approval count: "
                f"{expected_state['observed_approval_count']}"
            ),
            (
                "- Expected approval verification: "
                f"{expected_state['approval_verification']}"
            ),
            (
                "- Approved transition hard veto: "
                f"{expected_state['approved_transition_hard_veto']}"
            ),
            "",
            "## Rollback Plan",
        ]
    )
    lines.extend(f"- {item}" for item in payload["rollback_plan"])
    lines.extend(
        [
            "",
            "## Instructions",
        ]
    )
    lines.extend(f"- {item}" for item in payload["instructions"])
    lines.extend(
        [
            "",
            "## Approval Checklist",
        ]
    )
    lines.extend(f"- {item}" for item in payload["approval_checklist"])
    lines.extend(
        [
            "",
            "## Approval Template Roles",
        ]
    )
    for record in payload["approval_record_template"]:
        lines.extend(
            [
                f"### {record['approver_role']}",
                f"- Approval ID placeholder: `{record['approval_id']}`",
                f"- Approver ID placeholder: `{record['approver_id']}`",
                f"- Principal ID placeholder: `{record['principal_id']}`",
                f"- Subject ref: `{record['subject_ref']}`",
                f"- Status: `{record['status']}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a non-authoritative closure request for approval-required "
            "human governance changes."
        )
    )
    parser.add_argument("--repository-root", required=True)
    parser.add_argument(
        "--governance-gate-report",
        default=str(DEFAULT_GOVERNANCE_GATE_REPORT),
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-markdown", default=str(DEFAULT_OUTPUT_MARKDOWN))
    args = parser.parse_args(argv)

    repository_root = Path(args.repository_root).resolve()
    governance_gate_report = Path(args.governance_gate_report)
    if not governance_gate_report.is_absolute():
        governance_gate_report = (repository_root / governance_gate_report).resolve()
    output_json = Path(args.output_json)
    if not output_json.is_absolute():
        output_json = (repository_root / output_json).resolve()
    output_markdown = Path(args.output_markdown)
    if not output_markdown.is_absolute():
        output_markdown = (repository_root / output_markdown).resolve()

    payload = build_closure_request(
        repository_root=repository_root,
        governance_gate_report_path=governance_gate_report,
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(
        render_closure_request_markdown(payload),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

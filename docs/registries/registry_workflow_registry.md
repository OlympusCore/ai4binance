---
document_id: AI4B-GOV-REG-WFL-001
title: AI4BINANCE Workflow Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Operations Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: workflow_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_workflow_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Workflow Registry

## ELI10

This registry lists governed workflows and their validation boundaries.

## Registry Contract

Workflow entries must identify triggers, inputs, outputs, side effects, human approval points, and evidence outputs.

| workflow_id | name | owner | lifecycle_status | trigger | side_effect_boundary | evidence_output |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING | Pending canonical workflow entry | Operations Governance | DRAFT | PENDING | REPORT_ONLY | PENDING |
| AIO-MAO-001 | AI orchestration and multi-agent orchestration control flow | Enterprise Governance | ACTIVE | User request, system event, assurance finding, research need, or improvement candidate requiring coordinated AI/agent work | REPORT_ONLY unless a separate deterministic contract, tests, and explicit human approval grant a narrower action | Pattern selection, task package, dependency graph, worker outputs, deterministic merge result, blockers, review outcome |
| QG-PROFILE-001 | Quality gate profile workflow | Enterprise Quality Governance | ACTIVE | Manual or automated quality verification request through `scripts/quality.ps1 -Profile fast`, `scripts/quality.ps1 -Profile standard`, or `scripts/quality.ps1 -Profile full` | REPORT_ONLY; `FAST` and `STANDARD` cannot claim `FULL_VERIFIED`; `FULL` is canonical technical quality evidence only and does not grant production, promotion, exchange execution, or live-trading authority | `runtime/quality/latest.json`, `runtime/quality/history.jsonl`, `runtime/quality/<run_id>/summary.json`, `runtime/quality/<run_id>/timings.json`, `runtime/quality/<run_id>/*.log`; canonical runbook: `docs/workflows/runbook_quality_gate_profiles.md` |

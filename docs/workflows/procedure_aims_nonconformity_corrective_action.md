---
document_id: AI4B-AIMS-PROC-002
title: AI4BINANCE AIMS Nonconformity and Corrective Action Procedure
document_type: PROCEDURE
version: 1.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: aims_nonconformity_corrective_action
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: aims_nonconformity_corrective_action_workflow
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/procedure_aims_nonconformity_corrective_action.md
---

# AI4BINANCE AIMS Nonconformity and Corrective Action Procedure

## ELI10

This procedure explains what happens when the AI management system finds a gap.
The gap is recorded, the cause is reviewed, a corrective action is assigned,
and closure requires evidence.

## Trigger

Create an AIMS nonconformity record when:

- ISO/IEC 42001 crosswalk status is `BLOCKED` or unsupported;
- SoA applicability or justification is missing;
- AI system inventory is missing a material AI capability;
- risk or impact assessment evidence is missing for a material change;
- repository validator or documentation hygiene identifies a governance blocker;
- audit finds a repeated, stale, or unverified AIMS claim;
- a safety boundary such as `LIVE_ORDER_BLOCKED` is weakened without authority.

## CAPA Workflow

```text
Finding
-> classify nonconformity
-> contain unsafe effect
-> identify root cause
-> define corrective action
-> assign owner and due date
-> implement bounded correction
-> verify evidence
-> update AIMS records
-> close or escalate
```

## Minimum Record

Each CAPA record must include:

- `capa_id`
- `source_finding`
- `severity`
- `affected_ai_system_id`
- `affected_control`
- `containment`
- `root_cause`
- `corrective_action`
- `owner`
- `due_date`
- `verification_method`
- `evidence_refs`
- `closure_status`
- `reviewer`

## Severity

| severity | criteria | required action |
|---|---|---|
| CRITICAL | Could affect live execution, secrets, risk limits, or irreversible harm | Block, escalate, require human governance review |
| HIGH | Could invalidate AIMS evidence or remove required controls | Correct before readiness claim |
| MEDIUM | Creates partial or stale evidence | Correct through planned CAPA |
| LOW | Documentation or traceability weakness without immediate safety impact | Track and verify |

## Closure Rules

A CAPA item may close only when:

- corrective action is implemented or the gap is explicitly accepted by
  authorized governance;
- evidence references are present and reviewable;
- affected AIMS crosswalk, SoA, inventory, or workflow records are updated;
- targeted tests or documentation hygiene checks pass when applicable;
- live trading and risk boundaries remain unchanged unless separately approved.

## Safety

Corrective action must not delete negative evidence, suppress findings, disable
validators, bypass compliance gates, or weaken fail-closed trading states.

Unresolved safety-related CAPA keeps:

```text
RUNNING_WITH_BLOCKERS
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```



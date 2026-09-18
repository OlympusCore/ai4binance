---
document_id: AI4B-AIMS-PROC-001
title: AI4BINANCE AI Risk and Impact Assessment Procedure
document_type: PROCEDURE
version: 1.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: ai_risk_impact_assessment
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: ai_risk_impact_assessment_workflow
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/procedure_ai_risk_impact_assessment.md
---

# AI4BINANCE AI Risk and Impact Assessment Procedure

## ELI10

This procedure explains how to review an AI system before it changes behavior.
It checks intended use, risk, affected people and systems, required evidence,
and whether the safe answer is to block, wait, or keep the capability research-only.

## Trigger

Run this procedure when:

- a new AI system, agent, model, skill, provider, or workflow is introduced;
- an existing AI capability changes intended use;
- an AI capability touches trading decisions, risk, security, privacy, external
  evidence, or human oversight;
- AIMS crosswalk or SoA evidence changes;
- audit findings identify AI risk, impact, or evidence gaps.

## Assessment Workflow

```text
Identify AI system
-> confirm intended and prohibited use
-> identify affected parties and assets
-> assess risk and impact
-> define controls and evidence
-> decide status
-> record findings
-> verify corrective actions
-> update inventory, crosswalk, and SoA
```

## Minimum Assessment Record

Each assessment must record:

- `assessment_id`
- `ai_system_id`
- `change_description`
- `intended_use`
- `prohibited_use`
- `affected_parties`
- `affected_data`
- `affected_decisions`
- `risk_sources`
- `impact_sources`
- `existing_controls`
- `required_controls`
- `evidence_refs`
- `residual_risk`
- `decision`
- `owner`
- `reviewer`
- `review_date`

## Decision States

| decision | meaning |
|---|---|
| APPROVE_RESEARCH_ONLY | Evidence is sufficient for advisory or research use only |
| REQUIRE_EVIDENCE | Evidence is missing or stale |
| REQUIRE_CONTROL | A missing control must be implemented before use expands |
| BLOCK | Risk or impact is unacceptable in the current scope |
| ESCALATE | Human governance review is required |

## Hard Blocks

The assessment must block expansion when any of these are true:

- live execution authority would be created without explicit approval;
- risk limits would increase without governance approval;
- secret, wallet, account, or personal data would be exposed;
- validation evidence is missing for a behavior-changing claim;
- human oversight is removed from a consequential decision;
- external provider evidence lacks provenance, freshness, or trust controls;
- an LLM would become sole authority for trading, risk, promotion, or execution.

## Outputs

Assessment outputs must update or reference:

- `docs/registries/registry_ai_system_inventory.md`
- `docs/compliance/matrix_iso_42001_aims_crosswalk.md`
- `docs/compliance/statement_of_applicability_iso_42001.md`
- `docs/workflows/procedure_aims_nonconformity_corrective_action.md`
- relevant tests, reports, or audit evidence

## Safety

This procedure cannot approve live trading, production deployment, or risk
increase. If evidence is missing, the safe state is:

```text
REQUIRE_EVIDENCE
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```



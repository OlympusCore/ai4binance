---
document_id: AI4B-GOV-AGT-GOV-001
title: AI4BINANCE Governance Scope Agent Instructions
document_type: INSTRUCTION
version: 1.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: REPOSITORY
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: governance_implementation_operations
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: OPERATIONAL
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: src/ai4binance/governance/AGENTS.md
language: en-US
scope: src/ai4binance/governance
---

# AI4BINANCE Governance Scope Instructions

## ELI10

Root first; these controls apply only inside `src/ai4binance/governance/`.

## Local Controls

- Route only to affected policy, contract, schema, registry, and tests.
- Preserve fail-closed blockers and exact approval, subject, scope, and evidence bindings.
- Separate enforcement from diagnostics; advisory evidence grants no authority.
- Cover both success and deterministic rejection paths.

## Verification

Run affected tests, then the smallest required canonical profile. Report
technical quality, governance eligibility, and approval separately; keep
`LIVE_ORDER_BLOCKED`.

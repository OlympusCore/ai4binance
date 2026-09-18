---
document_id: AI4B-GOV-AGT-TEST-001
title: AI4BINANCE Test Scope Agent Instructions
document_type: INSTRUCTION
version: 1.0.1
status: ACTIVE
owner: Quality Governance
authority_level: REPOSITORY
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: test_implementation_operations
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: OPERATIONAL
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: tests/AGENTS.md
language: en-US
scope: tests
---

# AI4BINANCE Test Scope Instructions

## ELI10

Root first; these controls apply only inside `tests/`.

## Local Controls

- Use deterministic local fixtures and bounded temporary directories; never use Binance, credentials, wallet state, or uncontrolled network services.
- Cover success, invalid, missing, stale, conflicting, duplicate, and fail-closed outcomes.
- Preserve `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` assertions on sensitive paths.
- Never weaken assertions, coverage, or material controls to make a gate pass.

## Verification

Run affected tests, then the smallest required canonical profile. A focused
pass does not replace a required profile.

---
document_id: AI4B-GOV-EVID-RSM-001
title: AI4BINANCE Runtime State Migration Manifest
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: runtime_state_migration_manifest
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/report_runtime_state_migration_manifest.md
created_at_utc: 2026-08-28T19:56:58.4676545Z
---

# AI4BINANCE Runtime State Migration Manifest

## ELI10

This manifest records the repository-wide relocation of the legacy top-level
`state/` tree into `runtime/state/`. It is evidence-only and does not grant
authority to keep a separate `state/` root.

## Scope

The migration covers the entire legacy `state/` tree and all tracked children.

Representative moved roots:

```text
state/
state/binance-accounting-local/
state/private/
state/runtime_research/
state/runtime-research/
state/paper/
```

Canonical targets:

```text
runtime/state/
runtime/state/binance-accounting-local/
runtime/state/private/
runtime/state/runtime_research/
runtime/state/runtime-research/
runtime/state/paper/
```

## Migration Record

| source_path | target_path | reason | authority_level | status | requires_link_update | requires_reference_update | risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `state/**` | `runtime/state/**` | Relocate mutable runtime state under the canonical runtime workspace. | REPOSITORY | MOVED | true | true | LOW |

## Safety

- This manifest is evidence-only.
- It does not authorize live execution, promotion, or deletion of protected data.
- The legacy top-level `state/` root should remain absent after the migration cutover.

---
document_id: AI4B-GOV-EVID-REPO-STRUCT-DIFFPLAN-001
title: AI4BINANCE Repository Structure Diff Plan
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: repository_structure_diffplan
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/report_repository_structure_diffplan.md
created_at_utc: 2026-08-29T00:00:00Z
---

# AI4BINANCE Repository Structure Diff Plan

## ELI10

This report compares the requested target tree with the current canonical
repository layout. It is evidence-only. It does not authorize filesystem moves,
delete protected state, or create duplicate sources of truth.

## Verified Canonical Surfaces

- `config/quality/coverage-targets.json` is the current executable coverage
  target configuration.
- `config/governance/governed_document_lock_manifest.json` is the current
  governed document lock manifest.
- `docs/controls/control_repository_validation_rules.md` is the machine-readable
  repository validation control.
- `docs/standards/standard_repository_structure_governance.md` is the current
  canonical repository tree decision.
- `docs/standards/standard_repository_validator_governance.md` is the validator
  governance standard.
- `runtime/` is the canonical grouping root for mutable, generated,
  reproducible, and execution/run-produced outputs.

## Gap Analysis

| Requested surface | Current canonical surface | Status | Redteam note |
| --- | --- | --- | --- |
| `config/quality/coverage-targets.json` | `config/quality/coverage-targets.json` | `IMPLEMENTED` | Canonical coverage input now lives under `config/quality/coverage-targets.json`; resolved run snapshots must stay under `runtime/artifacts/coverage/runs/`. |
| `policies/repository-validator/manifest-policy.json` | `policies/repository-validator/manifest-policy.json` | `IMPLEMENTED` | Canonical repository-validator policy now lives outside `runtime/`; per-run policy evidence belongs under `runtime/audit/repository-validator/runs/` as a snapshot, not as a second source of truth. |
| `runtime/artifacts/coverage/runs/` | `runtime/artifacts/coverage/runs/` | `IMPLEMENTED` | Coverage run evidence is already grouped under run-scoped directories and remains non-canonical runtime output. |
| `runtime/audit/repository-validator/runs/` | `runtime/audit/repository-validator/runs/` | `IMPLEMENTED` | Durable repository-validator audit evidence is already grouped under the audit run subtree. |
| `runtime/test/acl/` | `runtime/test/acl/` | `IMPLEMENTED` | Canonical ACL test-runtime root exists and remains segregated from source and durable audit evidence. |
| `runtime/test/hypothesis/` | `runtime/test/hypothesis/` | `IMPLEMENTED` | Canonical Hypothesis runtime root exists and keeps generated test output outside source-of-truth surfaces. |
| `runtime/test/pytest/` | `runtime/test/pytest/` | `IMPLEMENTED_WITH_TRANSIENT_OVERLAY` | Canonical stable test output exists; disposable pytest basetemp runs are process-owned under `runtime/tmp/process/pytest/`. |
| `runtime/test/repository-validator/runs/` | `runtime/test/repository-validator/runs/` | `IMPLEMENTED` | Canonical repository-validator run grouping is governed by `RuntimeRunRetention`: preserve all runs younger than 7 days, keep at least the latest 20, and fail closed for active or protected paths. |
| `analysis/` | `runtime/analysis/` for generated analysis evidence; `analysis/` remains a legacy compatibility root | `LEGACY_COMPAT` | Do not promote legacy analysis outputs into authoritative source. |
| `artifacts/` | `runtime/artifacts/` | `LEGACY_COMPAT` | New generated evidence should target `runtime/artifacts/`; legacy roots remain read-compatible only. |
| `data/` | `runtime/data/` | `LEGACY_COMPAT` | Keep new mutable runtime data under `runtime/data/`. |
| `logs/` | `runtime/logs/` | `LEGACY_COMPAT` | New runtime logs should target `runtime/logs/`. |
| `reports/` | `runtime/reports/` | `LEGACY_COMPAT` | New generated reports should target `runtime/reports/`. |
| `state/` | `runtime/state/` | `LEGACY_COMPAT` | Keep new mutable runtime state under `runtime/state/`. |
| `wallet/` | `runtime/state/private/` when explicitly governed | `LEGACY_COMPAT` | Private portfolio state must remain fail-closed and local-only. |
| `orders/` | `runtime/artifacts/decisions/` or `runtime/state/` depending on evidence type | `LEGACY_COMPAT` | Do not let order evidence become live execution authority. |
| `opportunities/` | `runtime/artifacts/` or `runtime/reports/` depending on evidence type | `LEGACY_COMPAT` | Keep opportunity evidence auditable and separated from source code. |

## Redteam Conclusions

1. The target runtime skeleton is now largely implemented for coverage,
   repository-validator audit, and test-output subtrees.
2. Canonical governance inputs remain outside `runtime/`, including coverage
   targets and repository-validator policy.
3. The remaining hygiene gap is not structural absence but residual loose
   temporary output and broader repository-validator blockers unrelated to this
   layout slice.
4. Legacy roots may remain compatibility surfaces until a governed migration
   record explicitly moves their contents.

## Recommended Next Slices

1. Fold residual loose `runtime/test/repository-validator/tmp-*` outputs into
   run-scoped retention or governed cleanup.
2. Keep the governed document lock manifest as the only lock-policy source.
3. Continue routing newly generated coverage, audit, and validator evidence
   under the canonical `runtime/` subtree.
4. Address current repository-validator blockers separately from this structure
   alignment slice.

## Safety

- This report does not authorize filesystem moves.
- This report does not authorize deletion of legacy compatibility roots.
- This report does not change live eligibility, which remains
  `LIVE_ORDER_BLOCKED`.

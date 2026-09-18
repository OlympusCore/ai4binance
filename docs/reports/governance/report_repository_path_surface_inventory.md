---
document_id: AI4B-GOV-EVID-PATH-SURFACE-001
title: AI4BINANCE Repository Path Surface Inventory
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: repository_path_surface_inventory
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/report_repository_path_surface_inventory.md
---

# AI4BINANCE Repository Path Surface Inventory

## ELI10

This report groups repository fields and documentation terms that describe mirror, backup, junction, or related path surfaces. It is evidence-only and does not change policy, permissions, or runtime behavior.

## Scope

- Search scope: `docs`, `src`, `tests`, `.agents`
- Excluded: `runtime`
- Focus terms: `mirror_path`, `backup_path`, `junction_target`, `workspace_junction`, `workspace_junction_target`, `mirror_manifest_path`, `backup_manifest_path`, `source_attachment`, `local_reference_path`

## Summary

- Present as a stored field or variable: `mirror_path`, `mirror_manifest_path`, `workspace_junction`, `workspace_junction_target`, `junction_target`
- Present only as governance wording or examples: `source_attachment`, `local_reference_path`
- Not found as a direct symbol in the searched tree: `backup_path`, `backup_manifest_path`

## Inventory

| Term | Status | Evidence | Notes |
|---|---|---|---|
| `mirror_path` | Present | [docs/standards/standard_repository_validator_governance.md:243](../../standards/standard_repository_validator_governance.md#L243), [docs/schemas/reference_repository_artifact_schema.md:274](../../schemas/reference_repository_artifact_schema.md#L274), [docs/standards/standard_repository_naming_governance.md:364](../../standards/standard_repository_naming_governance.md#L364) | Governance docs allow mirror-visible paths only as non-canonical evidence metadata. |
| `mirror_manifest_path` | Present | [src/ai4binance/governance/repository_validator.py:896](../../../src/ai4binance/governance/repository_validator.py#L896), [src/ai4binance/governance/repository_validator.py:913](../../../src/ai4binance/governance/repository_validator.py#L913), [src/ai4binance/governance/repository_validator.py:1261](../../../src/ai4binance/governance/repository_validator.py#L1261), [src/ai4binance/governance/repository_validator.py:3191](../../../src/ai4binance/governance/repository_validator.py#L3191), [tests/test_repository_validator.py:560](../../../tests/test_repository_validator.py#L560), [tests/test_repository_validator.py:2177](../../../tests/test_repository_validator.py#L2177), [tests/test_repository_validator.py:2238](../../../tests/test_repository_validator.py#L2238) | Used by mirror-hygiene validation and report output. |
| `workspace_junction` | Present | [src/ai4binance/ops/repository_cleanup_audit.py:31](../../../src/ai4binance/ops/repository_cleanup_audit.py#L31), [src/ai4binance/ops/repository_cleanup_audit.py:221](../../../src/ai4binance/ops/repository_cleanup_audit.py#L221) | Report-only field that records a workspace alias when the requested root resolves to the canonical root. |
| `workspace_junction_target` | Present | [src/ai4binance/ops/repository_cleanup_audit.py:32](../../../src/ai4binance/ops/repository_cleanup_audit.py#L32), [src/ai4binance/ops/repository_cleanup_audit.py:224](../../../src/ai4binance/ops/repository_cleanup_audit.py#L224) | Records the resolved junction target as a string. |
| `junction_target` | Present | [src/ai4binance/ops/repository_cleanup_audit.py:208](../../../src/ai4binance/ops/repository_cleanup_audit.py#L208), [src/ai4binance/ops/repository_cleanup_audit.py:216](../../../src/ai4binance/ops/repository_cleanup_audit.py#L216) | Local variable used while building `workspace_junction_target`. |
| `source_attachment` | Present in docs only | [docs/standards/standard_repository_naming_governance.md:364](../../standards/standard_repository_naming_governance.md#L364) | Mentioned as a machine-specific path label, not as a canonical path. |
| `local_reference_path` | Present in docs only | [docs/standards/standard_repository_naming_governance.md:364](../../standards/standard_repository_naming_governance.md#L364) | Mentioned as a machine-specific path label, not as a canonical path. |
| `backup_path` | Not found | Search of `docs`, `src`, `tests`, and `.agents` returned no direct symbol hit. | No repository symbol or documented field with this exact name was found. |
| `backup_manifest_path` | Not found | Search of `docs`, `src`, `tests`, and `.agents` returned no direct symbol hit. | The repo uses backup-manifest concepts, but not this exact field name. |

## Notes

- `mirror` and `backup` often appear as policy or evidence vocabulary, not as path-address fields.
- `canonical_path` remains the repository-relative source-of-truth path contract.
- `repository_cleanup_audit.py` is the only source in this pass that exposes a `junction_*` path surface.

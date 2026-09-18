---
document_id: AI4B-GOV-REG-POL-001
title: AI4BINANCE Policy Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: policy_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_policy_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Policy Registry

## ELI10

This registry points to active policies and avoids multiple active policy sources for the same concept.

## Registry Contract

Policy entries must reference one authoritative source and may reference many derived consumers.

| policy_id | title | owner | lifecycle_status | canonical_path | source_of_truth | machine_enforceable |
| --- | --- | --- | --- | --- | --- | --- |
| AI4B-GOV-POL-CUDA-001 | AI4BINANCE CUDA and GPU Resource Usage Policy | Enterprise Governance | ACTIVE | docs/governance/policy_cuda_gpu_resource_usage.md | true | true |
| AI4B-GOV-POL-MANIFEST-001 | AI4BINANCE Manifest Governance Policy | Enterprise Governance | ACTIVE | docs/governance/policy_manifest_governance.md | true | true |
| PENDING | Pending canonical policy entry | Enterprise Governance | DRAFT | PENDING | true | true |

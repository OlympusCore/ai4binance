---
document_id: AI4B-GOV-REG-IND-001
title: AI4BINANCE Indicator Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Quant Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: indicator_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_indicator_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Indicator Registry

## ELI10

This registry prevents the same indicator from being calculated in incompatible ways.

## Registry Contract

Canonical indicators must define input data, parameters, warmup behavior, missing-data behavior, and validation tests before reuse.

| indicator_id | name | owner | lifecycle_status | canonical_calculation | parameter_ref | validated_by |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING | Pending canonical indicator entry | Quant Governance | DRAFT | PENDING | PENDING | PENDING |

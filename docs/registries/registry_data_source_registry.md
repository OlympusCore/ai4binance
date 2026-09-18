---
document_id: AI4B-GOV-REG-DATA-001
title: AI4BINANCE Data Source Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Data Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: data_source_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_data_source_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Data Source Registry

## ELI10

This registry tracks where data comes from and how it is validated before analysis.

## Registry Contract

Data source entries must define provenance, freshness, trust boundary, schema, and degraded-state behavior.

| data_source_id | name | owner | lifecycle_status | provenance_required | freshness_rule | degraded_state |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING | Pending canonical data source entry | Data Governance | DRAFT | true | PENDING | DATA_UNAVAILABLE |

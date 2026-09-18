---
document_id: AI4B-GOV-REG-PAR-001
title: AI4BINANCE Parameter Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Risk Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: parameter_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_parameter_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Parameter Registry

## ELI10

This registry tracks governed parameters so live-risk values cannot drift silently.

## Registry Contract

Risk-sensitive parameters require owner, lifecycle, validation evidence, and promotion state before use outside research.

| parameter_id | name | owner | lifecycle_status | default_value_ref | risk_sensitive | promotion_status |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING | Pending canonical parameter entry | Risk Governance | DRAFT | PENDING | true | RESEARCH_ONLY |

---
document_id: AI4B-GOV-REG-RISK-001
title: AI4BINANCE Risk Rule Registry
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Risk Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: risk_rule_registry
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_risk_rule_registry.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
validated_by:
  - src/ai4binance/governance/repository_validator.py
  - tests/test_repository_validator.py
---

# AI4BINANCE Risk Rule Registry

## ELI10

This registry lists risk rules that can veto research, paper, or execution eligibility.

## Registry Contract

Risk rules are deterministic controls. They must not be overridden by aggregate signal scores or LLM recommendations.

| risk_rule_id | name | owner | lifecycle_status | veto_scope | implementation_ref | validated_by |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING | Pending canonical risk rule entry | Risk Governance | DRAFT | LIVE_ORDER_BLOCKED | PENDING | PENDING |

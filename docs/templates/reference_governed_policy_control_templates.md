---
document_id: AI4B-GOV-TPL-DKG-102
title: Governed Policy Control and Standard Templates Reference
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: governed_policy_control_templates
content_role: DERIVED
source_of_truth: false
canonical_path: docs/templates/reference_governed_policy_control_templates.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Governed Policy Control and Standard Templates Reference

## ELI10

This file keeps policy, control, standard, framework, regulation, and registry templates together.

## Source Lineage

- Source file: `docs/templates/reference_governed_knowledge_object_template.md`
- Source section start: `## 38. Policy Format`
- This file preserves a bounded section of the governed source document.

## 38. Policy Format

This section defines the required content contract for `Policy Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Policy Statement
Objective
Scope
Authority
Owner
Controls
Mandatory Requirements
Prohibitions
Hard Gates
Exceptions
Exception Authority
Enforcement
Violation Classification
Monitoring
Audit Evidence
Review Cycle
Related Standards
```
```text
Policy
→ Control
→ Implementation
→ Test
→ Evidence
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 39. Control Format

This section defines the required content contract for `Control Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```yaml
control_id: CTRL-RISK-001

name: stale_market_data_block

implements:
  - AI4B-RISK-POL-004

control_type: HARD_GATE

condition:
  market_data_age > max_allowed_age

result:
  decision: NO_TRADE

severity: CRITICAL

machine_enforceable: true

test_required: true
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 40. Standard Format

This section defines the required content contract for `Standard Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Purpose
Scope
Normative Language
Definitions
Principles
Mandatory Requirements
Recommended Requirements
Architecture Rules
Naming Rules
Validation Rules
Compliance Criteria
Exceptions
Audit Requirements
Acceptance Criteria
Review Cycle
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 41. Framework Format

This section defines the required content contract for `Framework Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Purpose
Principles
Domains
Layers
Components
Roles
Processes
Lifecycle
Control Model
Decision Model
Evidence Model
Interfaces
Governance
Metrics
Maturity Model
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 42. Regulation Format

This section defines the required content contract for `Regulation Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Regulation Identity
Jurisdiction
Issuing Authority
Official Source
Effective Date
Applicability
Relevant Provisions
Obligations
Prohibitions
Internal Mapping
Controls
Evidence
Compliance Owner
Monitoring
Review Trigger
```
```text
source_requirement
internal_interpretation
internal_requirement
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 43. Registry Format

This section defines the required content contract for `Registry Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
authoritative index
```
```text
YAML / JSON
```
```text
generated human view
```
```yaml
registry_id:
object_id:
object_type:
version:
owner:
status:
authority:
approval_status:
validation_status:
allowed_scope:
prohibited_scope:
created_at:
updated_at:
supersedes:
dependencies:
evidence_ids:
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

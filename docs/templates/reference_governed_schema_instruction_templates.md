---
document_id: AI4B-GOV-TPL-DKG-101
title: Governed Schema and Instruction Templates Reference
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: governed_schema_instruction_templates
content_role: DERIVED
source_of_truth: false
canonical_path: docs/templates/reference_governed_schema_instruction_templates.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Governed Schema and Instruction Templates Reference

## ELI10

This file keeps schema, instruction, entity rule, and relationship rule templates together.

## Source Lineage

- Source file: `docs/templates/reference_governed_knowledge_object_template.md`
- Source section start: `## 34. Schema Knowledge Format`
- This file preserves a bounded section of the governed source document.

## 34. Schema Knowledge Format

This section defines the required content contract for `Schema Knowledge Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Purpose
Schema Identity
Scope
Object Definition
Fields
Data Types
Required Fields
Optional Fields
Enums
Constraints
Defaults
Validation Rules
Cross-field Rules
Serialization
Compatibility
Versioning
Valid Examples
Invalid Examples
Migration Rules
Audit Requirements
```
```text
VALID
INVALID
REQUIRED
OPTIONAL
FORBIDDEN
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 35. Instruction Knowledge Format

This section defines the required content contract for `Instruction Knowledge Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Role
Mission
Scope
Inputs
Preconditions
Required Behaviour
Decision Logic
MUST Rules
MUST NOT Rules
SHOULD Rules
Blockers
Escalation Rules
Failure Behaviour
Missing Data Behaviour
Output Contract
Evidence Requirements
Audit Requirements
Authority Boundaries
Acceptance Criteria
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 36. Entity Rule Format

This section defines the required content contract for `Entity Rule Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Entity ID
Entity Name
Definition
Purpose
Domain
Owner
Identity Rule
Required Attributes
Optional Attributes
Lifecycle
State Model
Allowed Operations
Validation Rules
Constraints
Relationships
Forbidden Relationships
Evidence Requirements
Retention
Examples
```
```text
data structure
+
identity
+
lifecycle
+
constraints
+
relationships
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 37. Relationship Rule Format

This section defines the required content contract for `Relationship Rule Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Relationship ID
Source Entity
Target Entity
Relationship Type
Direction
Cardinality
Required / Optional
Temporal Constraint
Ownership
Validation
Inverse Relationship
Delete Behaviour
Lifecycle Behaviour
Forbidden Conditions
Evidence Requirement
```
```yaml
relationship_id: REL_DECISION_EVIDENCE

source: TradeDecision
relation: EVIDENCED_BY
target: EvidenceArtifact

cardinality:
  source: one
  target: one_or_more

required: true

delete_behavior: RESTRICT
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

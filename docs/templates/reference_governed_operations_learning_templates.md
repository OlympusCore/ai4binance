---
document_id: AI4B-GOV-TPL-DKG-106
title: Governed Operations and Learning Templates Reference
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: governed_operations_learning_templates
content_role: DERIVED
source_of_truth: false
canonical_path: docs/templates/reference_governed_operations_learning_templates.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Governed Operations and Learning Templates Reference

## ELI10

This file keeps failure, recovery, escalation, alert, retention, procedure, runbook, learning, experiment, failure pattern, drift, improvement, directory, location, and metadata templates together.

## Source Lineage

- Source file: `docs/templates/reference_governed_knowledge_object_template.md`
- Source section start: `## 74. Failure Policy`
- This file preserves a bounded section of the governed source document.

## 74. Failure Policy

This section preserves the complete source-standard requirement for `Failure Policy` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Failure Type
Severity
Detection
Immediate Action
Fallback
Retry
Escalation
Recovery
Blocking Behaviour
Audit Evidence
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 75. Recovery Rule

This section preserves the complete source-standard requirement for `Recovery Rule` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Trigger
Required Preconditions
Recovery Steps
Validation
Rollback
State Reconciliation
Audit
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 76. Escalation Rule

This section preserves the complete source-standard requirement for `Escalation Rule` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Condition
Severity
Target
Required Context
Timeout
Fallback
Audit
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 77. Alert Rule

This section preserves the complete source-standard requirement for `Alert Rule` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Alert ID
Trigger
Threshold
Window
Severity
Deduplication
Cooldown
Recipients
Escalation
Evidence Link
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 78. Retention Rule

This section preserves the complete source-standard requirement for `Retention Rule` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Artifact Type
Retention Period
Immutability
Archive Policy
Deletion Authority
Legal Hold
Security Classification
Evidence Requirement
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 79. Procedure Format

This section defines the required content contract for `Procedure Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Purpose
Trigger
Preconditions
Inputs
Steps
Decision Points
Outputs
Failure Handling
Roles
Evidence
Completion Criteria
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 80. Runbook Format

This section defines the required content contract for `Runbook Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Incident / Condition
Symptoms
Initial Checks
Diagnosis
Safe Actions
Escalation
Recovery
Validation
Post-event Review
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 81. Learning Object Lifecycle

This section defines lifecycle and version control for `Learning Object Lifecycle`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```text
OBSERVED
↓
ANALYZED
↓
CANDIDATE
↓
VALIDATION_REQUIRED
↓
VALIDATED
↓
GOVERNANCE_REVIEW
↓
PROMOTED
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 82. Experiment Format

This section defines the required content contract for `Experiment Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Hypothesis
Scope
Dataset
Baseline
Candidate
Method
Metrics
Leakage Controls
Results
OOS Results
Interpretation
Limitations
Decision
Evidence
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 83. Failure Pattern

This section preserves the complete source-standard requirement for `Failure Pattern` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Pattern ID
Observed Failure
Context
Frequency
Severity
Affected Components
Root Causes
Evidence
Mitigation Candidate
Validation Required
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 84. Drift Observation

This section preserves the complete source-standard requirement for `Drift Observation` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Drift Type
Baseline
Observed State
Magnitude
Window
Affected Components
Risk
Required Action
Evidence
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 85. Improvement Candidate

This section preserves the complete source-standard requirement for `Improvement Candidate` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
candidate_id
problem
proposal
expected_benefit
risk
affected_components
validation_plan
promotion_requirements
status
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 92. Document Directory Standard

This section preserves the complete source-standard requirement for `Document Directory Standard` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
docs/
│
├── architecture/
├── governance/
├── policies/
├── standards/
├── frameworks/
├── instructions/
├── ontology/
├── regulations/
├── controls/
├── contracts/
├── procedures/
├── runbooks/
├── adr/
├── references/
└── generated/
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 93. Machine-readable Knowledge Locations

This section preserves the complete source-standard requirement for `Machine-readable Knowledge Locations` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
schemas/
policies/
ontology/
registry/
config/
workflows/
controls/
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 94. Documentation Metadata Header

This section preserves the complete source-standard requirement for `Documentation Metadata Header` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```yaml
---
document_id: AI4B-GOV-POL-001
title: Decision Governance Policy
document_type: POLICY

version: 2.1.0
status: ACTIVE

owner: governance
technical_owner: platform_engineering
validation_owner: qaqc

authority_level: ENFORCEABLE
content_role: AUTHORITATIVE

effective_date: 2026-08-14
review_cycle_days: 90

source_of_truth: true
machine_enforceable: true
audit_required: true

classification: INTERNAL

supersedes:
related_documents:
---
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

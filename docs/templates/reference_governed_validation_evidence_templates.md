---
document_id: AI4B-GOV-TPL-DKG-104
title: Governed Validation and Evidence Templates Reference
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: governed_validation_evidence_templates
content_role: DERIVED
source_of_truth: false
canonical_path: docs/templates/reference_governed_validation_evidence_templates.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Governed Validation and Evidence Templates Reference

## ELI10

This file keeps validation, test, evidence, provenance, lineage, and decision record templates together.

## Source Lineage

- Source file: `docs/templates/reference_governed_knowledge_object_template.md`
- Source section start: `## 53. Validation Specification Format`
- This file preserves a bounded section of the governed source document.

## 53. Validation Specification Format

This section defines the required content contract for `Validation Specification Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Validation ID
Subject Type
Scope
Dataset Requirements
Backtest Requirements
Walk-forward Requirements
OOS Requirements
Regime Requirements
Robustness Requirements
Metrics
Thresholds
Minimum Sample
Failure Criteria
Promotion Criteria
Evidence Requirements
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 54. Test Contract Format

This section defines the required content contract for `Test Contract Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Test Contract ID
Subject
Required Test Types
Test Data
Preconditions
Expected Behaviour
Failure Conditions
Coverage Requirements
Regression Requirements
Evidence Output
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 55. Evidence Requirement Format

This section defines the required content contract for `Evidence Requirement Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```yaml
claim:
  BREAKOUT_CONFIRMED

required_evidence:
  - structure_break
  - retest_confirmation
  - relative_volume
  - spread_check

minimum_evidence_count: 3
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 56. Provenance Format

This section defines the required content contract for `Provenance Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
origin
source
ingestion
transformation
processor
timestamp
version
checksum
parent_artifacts
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 57. Lineage Format

This section defines the required content contract for `Lineage Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
SourceData
   ↓
MarketSnapshot
   ↓
FeatureSet
   ↓
Evidence
   ↓
Decision
   ↓
Execution
   ↓
ClosureReview
   ↓
LearningLesson
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 58. Decision Record

This section defines the required content contract for `Decision Record` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
decision_id
snapshot_id
rules
evidence
blockers
scores
policy_version
strategy_version
parameter_set
risk_result
decision
execution_allowed
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

---
document_id: AI4B-GOV-TPL-DKG-105
title: Governed Strategy Agent and Authority Templates Reference
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: governed_strategy_agent_templates
content_role: DERIVED
source_of_truth: false
canonical_path: docs/templates/reference_governed_strategy_agent_templates.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Governed Strategy Agent and Authority Templates Reference

## ELI10

This file keeps strategy, setup, feature, indicator, regime, risk, execution, parameter, agent, prompt, tool, permission, authority, exception, and ADR templates together.

## Source Lineage

- Source file: `docs/templates/reference_governed_knowledge_object_template.md`
- Source section start: `## 59. Strategy Definition Format`
- This file preserves a bounded section of the governed source document.

## 59. Strategy Definition Format

This section defines the required content contract for `Strategy Definition Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Strategy ID
Objective
Allowed Markets
Allowed Timeframes
Allowed Regimes
Setup Requirements
Entry Logic
Exit Logic
Risk Logic
Required Evidence
Blockers
Parameters
Validation Status
Promotion Status
Known Failure Modes
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 60. Setup Definition Format

This section defines the required content contract for `Setup Definition Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```yaml
setup_id:

required_conditions:

optional_confirmations:

blockers:

allowed_regimes:

allowed_timeframes:

invalidation:

minimum_quality:

evidence_required:
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 61. Feature Definition

This section defines the required content contract for `Feature Definition` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Feature ID
Definition
Calculation
Input
Timeframe
Unit
Normalization
Missing Data
Version
Producer
Consumers
Look-ahead Risk
Validation
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 62. Indicator Definition

This section preserves the complete source-standard requirement for `Indicator Definition` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Indicator ID
Formula / Implementation
Inputs
Parameters
Allowed TF
Role
Score Contribution
Hard Gate Eligibility
False Positive Risk
OOS Validation
Promotion Status
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 63. Regime Definition

This section preserves the complete source-standard requirement for `Regime Definition` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Regime ID
Definition
Detection Rules
Required Features
Transition Rules
Confidence Rules
Allowed Strategies
Blocked Strategies
Validation Evidence
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 64. Risk Model Format

This section defines the required content contract for `Risk Model Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Risk Model ID
Risk Types
Inputs
Scoring
Hard Blockers
Soft Penalties
Risk Budget
Position Sizing
Portfolio Interaction
Invalidation
Escalation
Validation
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 65. Execution Profile

This section defines the required content contract for `Execution Profile` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Mode
Order Mode
Allowed Markets
Allowed Order Types
Margin Mode
Leverage Rules
Filters
Slippage Caps
Spread Caps
Confirmation Rules
Kill Switch
Failure Behaviour
Audit Requirements
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 66. Parameter Set

This section defines the required content contract for `Parameter Set` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
parameter_set_id
strategy_id
version
parameters
source
training_window
validation_result
regime_scope
promotion_status
effective_from
rollback_target
```
```text
CANDIDATE
→ VALIDATED
→ PAPER_APPROVED
→ PROMOTED
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 67. Agent Contract

This section preserves the complete source-standard requirement for `Agent Contract` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Agent ID
Role
Mission
Inputs
Outputs
Dependencies
Allowed Tools
Authority
Forbidden Actions
Evidence Requirements
Failure Behaviour
Timeout Behaviour
Conflict Behaviour
Escalation
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 68. Prompt Contract

This section preserves the complete source-standard requirement for `Prompt Contract` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Prompt ID
Purpose
Model Scope
Input Contract
Output Contract
Authority Boundary
Forbidden Behaviour
Version
Test Cases
Evaluation
Known Failure Modes
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 69. Tool Contract

This section preserves the complete source-standard requirement for `Tool Contract` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Tool ID
Provider
Purpose
Allowed Operations
Forbidden Operations
Required Permissions
Input Schema
Output Schema
Timeout
Retry
Failure Behaviour
Audit Logging
Security Classification
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 70. Permission Profile

This section preserves the complete source-standard requirement for `Permission Profile` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
read
write
execute
approve
promote
override
delete
live_order
```
```yaml
permission_profile:

  explain: true
  recommend: true
  propose_experiment: true

  override_risk: false
  bypass_gate: false
  execute_live_order: false
  promote_parameter: false
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 71. Authority Matrix

This section defines the required content contract for `Authority Matrix` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Actor
Resource
Action
Environment
Allowed
Approval Required
Constraint
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 72. Exception and Waiver

This section defines the required content contract for `Exception and Waiver` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
explicit
scoped
temporary
approved
traceable
expiring
```
```yaml
waiver_id:
target_rule:
scope:
reason:
approved_by:
effective_from:
expires_at:
risk_assessment:
live_execution_allowed:
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 73. ADR: Architecture Decision Record

This section defines the required content contract for `ADR: Architecture Decision Record` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Context
Decision
Alternatives Considered
Rationale
Consequences
Risks
Status
Related Components
Supersedes
Superseded By
```
```text
Why did we choose this architecture?
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

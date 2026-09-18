---
document_id: AI4B-GOV-TPL-DKG-103
title: Governed Contract and Decision Templates Reference
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: governed_contract_decision_templates
content_role: DERIVED
source_of_truth: false
canonical_path: docs/templates/reference_governed_contract_decision_templates.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# Governed Contract and Decision Templates Reference

## ELI10

This file keeps output, data, event, interface, decision, invariant, constraint, state, and workflow templates together.

## Source Lineage

- Source file: `docs/templates/reference_governed_knowledge_object_template.md`
- Source section start: `## 44. Output Contract Format`
- This file preserves a bounded section of the governed source document.

## 44. Output Contract Format

This section defines the required content contract for `Output Contract Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Output ID
Producer
Consumer
Serialization
Schema
Mandatory Fields
Optional Fields
Ordering
Units
Precision
Null Behaviour
Missing Data Behaviour
Error Format
Status Codes
Compatibility
Valid Example
Invalid Example
```
```text
DATA_UNAVAILABLE
LOW_CONFIDENCE
WAIT
NO_TRADE
LIVE_ORDER_BLOCKED
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 45. Data Contract Format

This section defines the required content contract for `Data Contract Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
What does the data look like?
```
```text
Who produces it?
Who consumes it?
How fresh?
How reliable?
What happens on failure?
```
```yaml
data_contract_id:

producer:

consumers:

schema:

freshness:

quality_rules:

availability:

allowed_latency:

missing_data_policy:

failure_behavior:

lineage_required:

owner:
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 46. Event Contract Format

This section defines the required content contract for `Event Contract Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
MarketSnapshotReady
SignalCandidateCreated
DecisionEvaluated
RiskGateFailed
PaperOrderAccepted
PositionClosed
TrailingStopTriggered
ValidationCompleted
PolicyViolationDetected
StrategyPromoted
```
```yaml
event_type:
event_version:
producer:
consumers:
payload_schema:
required_fields:
idempotent:
ordering_required:
correlation_id_required:
trace_id_required:
delivery_semantics:
failure_policy:
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 47. Interface Contract Format

This section defines the required content contract for `Interface Contract Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
Interface ID
Provider
Consumer
Operations
Inputs
Outputs
Preconditions
Postconditions
Errors
Timeout
Retry
Idempotency
Security
Version
Compatibility
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 48. Decision Rule Format

This section defines the required content contract for `Decision Rule Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```yaml
decision_rule_id:

scope:

priority:

conditions:

result:

blockers:

dependencies:

evidence_required:

implemented_by:

tested_by:
```
```text
IF data_quality = FAIL
THEN decision = NO_TRADE
AND execution_allowed = false
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 49. Invariant Format

This section defines the required content contract for `Invariant Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
INV-EXEC-001

LLM MUST NOT possess autonomous live-order authority.
```
```text
INV-RISK-002

NO_TRADE MUST imply execution_allowed = false.
```
```text
MUST be
machine-testable where practical.
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 50. Constraint Format

This section defines the required content contract for `Constraint Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
max_open_position
supported_timeframe
valid_symbol
max_latency
max_spread
```
```text
hard
soft
contextual
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 51. State Model Format

This section defines the required content contract for `State Model Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
State Model ID
Entity
States
Initial State
Terminal States
Allowed Transitions
Forbidden Transitions
Transition Conditions
Transition Authority
Events
Rollback Behaviour
Audit Requirements
```
```text
RESEARCH
→ BACKTESTED
→ WF_VALIDATED
→ OOS_VALIDATED
→ PAPER_APPROVED
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 52. Workflow Format

This section defines the required content contract for `Workflow Format` knowledge objects.

The object must state its identity, owner, authority, lifecycle status, source-of-truth behavior, dependencies, validation evidence and audit trail. If the source section defines fields or options, they are preserved below as canonical machine-readable content.

Canonical options, fields or structures preserved from the source standard:

```text
workflow_id
version
owner
trigger
inputs
preconditions
steps
dependencies
gates
outputs
failure_policy
retry_policy
rollback_policy
audit_requirements
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

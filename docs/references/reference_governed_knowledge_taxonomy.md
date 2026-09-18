---
document_id: AI4B-GOV-REF-DKG-TAX-001
title: AI4BINANCE Governed Knowledge Taxonomy Reference
document_type: REFERENCE
version: 1.0.0
status: DRAFT
owner: Enterprise Knowledge Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: governed_knowledge_taxonomy
content_role: EXPLANATORY
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/references/reference_governed_knowledge_taxonomy.md
split_from:
  document_id: AI4B-GOV-STD-DKG-001
  source_file: docs/standards/standard_documentation_knowledge_governance.md
parent_standard: docs/standards/standard_documentation_knowledge_governance.md
---

# AI4BINANCE Governed Knowledge Taxonomy Reference

> Source basis: split from `docs/standards/standard_documentation_knowledge_governance.md` (`document_id: AI4B-GOV-STD-DKG-001`).
> Split timestamp: 2026-08-17T18:23:00Z.
> This split preserves the original governed terminology and section numbering while reducing operational load for Codex/Drive mirror review.

## ELI10

This reference keeps the detailed governed knowledge taxonomy that was split out of the core standard. It is explanatory and does not replace the active standard.

## Purpose

This reference preserves the taxonomy, classification and system-of-systems knowledge model sections from the original DKG standard. It is a companion reference, not an independent normative authority. Normative authority remains in `docs/standards/standard_documentation_knowledge_governance.md`.

| Output file | Original sections |
|---|---|
| `standard_documentation_knowledge_governance.md` | Preface, Repository Content Language, 1-3, 15-33, 86-90, 95-101, 107-111, 114-115, Constitutional Lock |
| `reference_governed_knowledge_taxonomy.md` | 4-14, 91, 102-106, 112-113 |
| `docs/templates/reference_governed_knowledge_object_template.md` | 34-85, 92-94 |


## 4. Governed System Knowledge Taxonomy

This section preserves the complete source-standard requirement for `Governed System Knowledge Taxonomy` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
GOVERNED SYSTEM KNOWLEDGE
│
├── 1. Normative Knowledge
├── 2. Semantic Knowledge
├── 3. Structural Knowledge
├── 4. Behavioral Knowledge
├── 5. Authority Knowledge
├── 6. Operational Knowledge
├── 7. Validation Knowledge
├── 8. Evidence Knowledge
├── 9. Learning Knowledge
└── 10. Governance Metadata
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 5. Normative Knowledge

This section defines the `Normative Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
What MUST / MUST NOT / SHOULD happen?
```
```text
REGULATION
POLICY
STANDARD
CONTROL
INSTRUCTION
CONSTRAINT
INVARIANT
EXCEPTION
WAIVER
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 6. Semantic Knowledge

This section defines the `Semantic Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
DEFINITION
GLOSSARY
ENTITY_RULE
RELATIONSHIP_RULE
VOCABULARY
ONTOLOGY_MAPPING
TAXONOMY
CLASSIFICATION_RULE
```
```text
same term
=
same meaning
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 7. Structural Knowledge

This section defines the `Structural Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
SCHEMA
DATA_CONTRACT
INTERFACE_CONTRACT
EVENT_CONTRACT
OUTPUT_CONTRACT
API_CONTRACT
DEPENDENCY_RULE
ARCHITECTURE_DEFINITION
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 8. Behavioral Knowledge

This section defines the `Behavioral Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
DECISION_RULE
STATE_MODEL
WORKFLOW
STRATEGY_DEFINITION
SETUP_DEFINITION
RISK_MODEL
EXECUTION_PROFILE
PORTFOLIO_RULE
PLAYBOOK
REGIME_DEFINITION
FEATURE_DEFINITION
INDICATOR_DEFINITION
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 9. Authority Knowledge

This section defines the `Authority Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
ROLE
OWNER
PERMISSION_PROFILE
AUTHORITY_MATRIX
APPROVAL_RULE
RESPONSIBILITY_ASSIGNMENT
AGENT_AUTHORITY
LLM_AUTHORITY
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 10. Operational Knowledge

This section defines the `Operational Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
PROCEDURE
RUNBOOK
FAILURE_POLICY
RECOVERY_RULE
ESCALATION_RULE
ALERT_RULE
RETENTION_RULE
BACKUP_RULE
RESTORE_RULE
INCIDENT_RESPONSE_RULE
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 11. Validation Knowledge

This section defines the `Validation Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
VALIDATION_SPEC
TEST_CONTRACT
ACCEPTANCE_CRITERIA
BENCHMARK_DEFINITION
PROMOTION_RULE
ROBUSTNESS_REQUIREMENT
OOS_REQUIREMENT
WALK_FORWARD_REQUIREMENT
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 12. Evidence Knowledge

This section defines the `Evidence Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
EVIDENCE_REQUIREMENT
EVIDENCE_ARTIFACT
PROVENANCE
LINEAGE
VALIDATION_RESULT
AUDIT_FINDING
DECISION_RECORD
EXECUTION_RECORD
CONTROL_EXECUTION_RECORD
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 13. Learning Knowledge

This section defines the `Learning Knowledge` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
EXPERIMENT
LESSON
FAILURE_PATTERN
FALSE_POSITIVE_RECORD
FALSE_NEGATIVE_RECORD
DRIFT_OBSERVATION
IMPROVEMENT_CANDIDATE
PARAMETER_CANDIDATE
STRATEGY_CANDIDATE
ROOT_CAUSE_ANALYSIS
```
```text
MUST NOT
automatically become
Production Authority
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 14. Governance Metadata

This section preserves the complete source-standard requirement for `Governance Metadata` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
REGISTRY
VERSION
LIFECYCLE
SOURCE_OF_TRUTH
AUTHORITY_LEVEL
CLASSIFICATION
DEPENDENCY
OWNERSHIP
ADR
CHANGE_RECORD
CHECKSUM
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 91. Knowledge Classification

This section preserves the complete source-standard requirement for `Knowledge Classification` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
PUBLIC
INTERNAL
CONFIDENTIAL
RESTRICTED
SECRET
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 102. Regulation Mapping Model

This section preserves the complete source-standard requirement for `Regulation Mapping Model` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Regulation
    │
    └── imposes
          ↓
Requirement
          │
          └── implemented_by
                 ↓
Policy / Control
                 │
                 └── verified_by
                        ↓
Evidence
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 103. Architecture Knowledge Model

This section preserves the complete source-standard requirement for `Architecture Knowledge Model` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
ArchitectureDefinition
      ↓
ADR
      ↓
Component
      ↓
InterfaceContract
      ↓
DependencyRule
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 104. Agent Knowledge Model

This section preserves the complete source-standard requirement for `Agent Knowledge Model` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Agent
  │
  ├── governed_by → AgentContract
  ├── uses → ToolContract
  ├── receives → EventContract
  ├── produces → OutputContract
  ├── constrained_by → PermissionProfile
  ├── implements → Instruction
  └── validated_by → TestContract
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 105. Decision Knowledge Model

This section preserves the complete source-standard requirement for `Decision Knowledge Model` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Decision
 │
 ├── generated_from → MarketSnapshot
 ├── follows → DecisionRule
 ├── constrained_by → Policy
 ├── evaluated_by → Control
 ├── evidenced_by → EvidenceArtifact
 ├── uses → ParameterSet
 └── executed_under → ExecutionProfile
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 106. Learning Knowledge Model

This section defines the `Learning Knowledge Model` family of governed system knowledge.

Objects in this family must be classified explicitly, owned, versioned, authority-scoped, traceable to evidence and checked by deterministic validation where practical.

Canonical options, fields or structures preserved from the source standard:

```text
Execution
   ↓
ClosureReview
   ↓
FailurePattern
   ↓
Lesson
   ↓
ImprovementCandidate
   ↓
Experiment
   ↓
Validation
   ↓
PromotionCandidate
```
```text
Lesson
→ Direct Production Change
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 112. Recommended Knowledge Governance Architecture

This section preserves the complete source-standard requirement for `Recommended Knowledge Governance Architecture` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
                  AI4BINANCE
                       │
                       ▼
           SYSTEM KNOWLEDGE GOVERNANCE
                       │
      ┌────────────────┼────────────────┐
      │                │                │
      ▼                ▼                ▼
  Taxonomy         Authority         Lifecycle
      │                │                │
      └────────────────┼────────────────┘
                       ▼
              Knowledge Registry
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
    Metadata       Contracts       Relations
        │              │              │
        └──────────────┼──────────────┘
                       ▼
              Validation Engine
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
        PASS         WARNING       BLOCK
                       │
                       ▼
                 Audit Evidence
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 113. System-of-Systems Knowledge Model

This section preserves the complete source-standard requirement for `System-of-Systems Knowledge Model` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
Regulation
   ↓
Requirement
   ↓
Policy
   ↓
Standard
   ↓
Control
   ↓
Constraint / Invariant
   ↓
Schema / Contract
   ↓
DecisionRule / Workflow
   ↓
Implementation
   ↓
Test
   ↓
Validation
   ↓
Evidence
   ↓
Decision
   ↓
Execution
   ↓
Review
   ↓
Learning
   ↓
Improvement Candidate
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.


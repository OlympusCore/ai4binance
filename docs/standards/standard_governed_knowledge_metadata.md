---
document_id: AI4B-GOV-STD-DKG-101
title: AI4BINANCE Governed Knowledge Metadata Standard
document_type: STANDARD
version: 1.0.2
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: governed_knowledge_metadata
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/standards/standard_governed_knowledge_metadata.md
---
# AI4BINANCE Governed Knowledge Metadata Standard

## ELI10

This standard section defines governed knowledge metadata, IDs, types, authority, lifecycle, source-of-truth rules, and the required `canonical_path` field.

## Source Lineage

- Source file: `docs/standards/standard_documentation_knowledge_governance.md`
- Source section start: `## 15. Mandatory GovernedKnowledgeObject Schema`
- This file preserves a bounded section of the governed source document.

## 15. Mandatory GovernedKnowledgeObject Schema

This section preserves the complete source-standard requirement for `Mandatory GovernedKnowledgeObject Schema` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```yaml
GovernedKnowledgeObject:

  knowledge_id:
    type: string
    required: true
    immutable: true

  knowledge_type:
    type: enum
    required: true

  title:
    type: string
    required: true

  version:
    type: semver
    required: true

  lifecycle_status:
    type: enum
    required: true

  authority_level:
    type: enum
    required: true
    role: legacy_frontmatter_compatibility_alias

  authority_layer:
    type: enum
    required: true

  authority_effect:
    type: enum
    required: true

  authority_scope:
    type: string
    required: false
    pattern: lower_snake_case
    required_when:
      authority_effect: OPERATIONAL_SPECIALIZATION

  content_role:
    type: enum
    required: true

  owner:
    type: string
    required: true

  technical_owner:
    type: string
    required: false

  validation_owner:
    type: string
    required: false

  source_of_truth:
    type: boolean
    required: true

  canonical_path:
    type: string
    required: true

  source_of_truth_scope:
    type: enum
    required: false
    allowed_values:
      - canonical
      - family_index
      - provider_adapter
      - reference
      - generated
    operational_source_of_truth_pattern:
      - <authority_scope>_workflow
      - <authority_scope>_procedure
      - <authority_scope>_runbook

  effective_from:
    type: datetime
    required: false

  valid_until:
    type: datetime
    required: false

  review_due:
    type: datetime
    required: false

  supersedes:
    type: string
    required: false

  superseded_by:
    type: string
    required: false

  dependencies:
    type: list[string]

  related_objects:
    type: list[string]

  implemented_by:
    type: list[string]

  validated_by:
    type: list[string]

  evidence_required:
    type: boolean

  classification:
    type: enum

  machine_enforceable:
    type: boolean

  audit_required:
    type: boolean

  checksum:
    type: string
    required: false
```

Markdown frontmatter compatibility note:

- governed Markdown serializes the lifecycle field as `status` for validator compatibility;
- `status` is the frontmatter alias of the canonical `lifecycle_status` concept;
- do not assign a second, independent meaning to `status` in governed knowledge metadata.
- `authority_level` remains a legacy frontmatter compatibility alias and must not be treated as the canonical authority layer.
- `authority_layer` defines repository-layer placement.
- `authority_effect` defines how the knowledge specializes or constrains behavior.
- `authority_scope` defines the semantic domain of that specialization when applicable.

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- source-of-truth scope is explicit when present;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 16. Knowledge ID Standard

This section preserves the complete source-standard requirement for `Knowledge ID Standard` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
AI4B-<DOMAIN>-<TYPE>-<NUMBER>
```
```text
AI4B-GOV-POL-001
AI4B-RISK-CTRL-004
AI4B-DEC-RULE-021
AI4B-ONT-ENT-017
AI4B-ONT-REL-013
AI4B-DATA-SCH-004
AI4B-ARCH-ADR-006
AI4B-EXEC-EVT-011
```
```text
identity
```
```text
human-readable locator
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- source-of-truth scope is explicit when present;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 17. Knowledge Type Registry

This section preserves the complete source-standard requirement for `Knowledge Type Registry` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
registry/knowledge/knowledge_type_registry.yaml
```
```yaml
knowledge_types:

  - REGULATION
  - POLICY
  - STANDARD
  - FRAMEWORK
  - CONTROL
  - INSTRUCTION
  - SCHEMA
  - ENTITY_RULE
  - RELATIONSHIP_RULE
  - OUTPUT_CONTRACT
  - DATA_CONTRACT
  - EVENT_CONTRACT
  - INTERFACE_CONTRACT
  - DECISION_RULE
  - STATE_MODEL
  - WORKFLOW
  - CONSTRAINT
  - INVARIANT
  - DEFINITION
  - GLOSSARY
  - ROLE
  - PERMISSION_PROFILE
  - AUTHORITY_MATRIX
  - VALIDATION_SPEC
  - TEST_CONTRACT
  - EVIDENCE_REQUIREMENT
  - PROVENANCE
  - LINEAGE
  - PROCEDURE
  - RUNBOOK
  - FAILURE_POLICY
  - RECOVERY_RULE
  - ESCALATION_RULE
  - ALERT_RULE
  - RETENTION_RULE
  - STRATEGY_DEFINITION
  - SETUP_DEFINITION
  - FEATURE_DEFINITION
  - INDICATOR_DEFINITION
  - REGIME_DEFINITION
  - RISK_MODEL
  - EXECUTION_PROFILE
  - PARAMETER_SET
  - AGENT_CONTRACT
  - PROMPT_CONTRACT
  - TOOL_CONTRACT
  - MODEL_CARD
  - AGENT_CARD
  - STRATEGY_CARD
  - EXPERIMENT
  - LESSON
  - FAILURE_PATTERN
  - DRIFT_OBSERVATION
  - IMPROVEMENT_CANDIDATE
  - EXCEPTION
  - WAIVER
  - ADR
  - REGISTRY
```

Compatibility note for generated report surfaces:

- `EVIDENCE_REQUIREMENT` remains the governed metadata type for generated
  report and evidence records under `docs/reports/**` when those documents
  capture evidence mappings, findings, readiness records, inventories, split
  manifests, or migration manifests;
- in that bounded family, filename prefixes such as `report_` and `evidence_`
  are presentation-oriented locator forms and do not by themselves redefine the
  governed metadata type;
- if the repository later adopts distinct governed metadata types such as
  `REPORT` or `EVIDENCE`, that change must be versioned and migrated as one
  explicit taxonomy change.

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 18. Normative Language

This section preserves the complete source-standard requirement for `Normative Language` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 19. Authority Levels

This section defines authority handling for `Authority Levels`.

Authority must be declared, not inferred. Conflicts, duplicate source-of-truth claims and ambiguous precedence fail closed until a governed resolution exists.

Canonical options, fields or structures preserved from the source standard:

```text
EXTERNAL_AUTHORITY
ENFORCEABLE
NORMATIVE
ADVISORY
INFORMATIONAL
```
```text
Policy
Control
Invariant
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 20. Authority Precedence

This section defines authority handling for `Authority Precedence`.

Authority must be declared, not inferred. Conflicts, duplicate source-of-truth claims and ambiguous precedence fail closed until a governed resolution exists.

Canonical options, fields or structures preserved from the source standard:

```text
External Law / Regulation
          ↓
Security / Safety Hard Requirement
          ↓
Enterprise Governance Policy
          ↓
Domain Policy
          ↓
Invariant
          ↓
Control
          ↓
Standard
          ↓
Schema / Contract
          ↓
Decision Rule
          ↓
Instruction
          ↓
Procedure
          ↓
Framework
          ↓
Guideline
          ↓
Reference
```
```yaml
precedence: 850
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 21. Conflict Resolution

This section defines authority handling for `Conflict Resolution`.

Authority must be declared, not inferred. Conflicts, duplicate source-of-truth claims and ambiguous precedence fail closed until a governed resolution exists.

Canonical options, fields or structures preserved from the source standard:

```text
1 Authority Level
2 Explicit Precedence
3 Scope Specificity
4 Effective Date
5 Version
6 Source-of-Truth Status
7 Governance Decision
```
```text
KNOWLEDGE_CONFLICT
```
```text
GOVERNANCE_BLOCKER
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 22. Content Role

This section preserves the complete source-standard requirement for `Content Role` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
AUTHORITATIVE
EXPLANATORY
GENERATED
DERIVED
HISTORICAL
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 23. Source-of-Truth Governance

This section defines authority handling for `Source-of-Truth Governance`.

Authority must be declared, not inferred. Conflicts, duplicate source-of-truth claims and ambiguous precedence fail closed until a governed resolution exists.

Canonical options, fields or structures preserved from the source standard:

```text
Risk limits
→ config/risk/risk_limits.yaml
```
```text
max_risk_per_trade = 1%
```
```text
Source:
risk_limits.yaml

Reference:
AI4B-RISK-CONFIG-001
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 24. Authoritative vs Explanatory Separation

This section preserves the complete source-standard requirement for `Authoritative vs Explanatory Separation` in English.

The requirement applies to non-code repository knowledge and must be interpreted through the `GovernedKnowledgeObject` model, repository policy, artifact schema, validator reports and full quality_gate evidence.

Canonical options, fields or structures preserved from the source standard:

```text
schemas/decision/trade_decision.schema.json
```
```text
content_role = AUTHORITATIVE
```
```text
docs/contracts/TradeDecision-OutputContract.md
```
```text
content_role = EXPLANATORY
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 25. Document Lifecycle

This section defines lifecycle and version control for `Document Lifecycle`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```text
DRAFT
  ↓
REVIEW
  ↓
APPROVED
  ↓
ACTIVE
  ↓
SUPERSEDED
  ↓
DEPRECATED
  ↓
ARCHIVED
```
```text
SUSPENDED
QUARANTINED
REJECTED
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 26. Lifecycle Transition Rules

This section defines lifecycle and version control for `Lifecycle Transition Rules`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```text
DRAFT → ACTIVE
FORBIDDEN

DRAFT → REVIEW
ALLOWED

REVIEW → APPROVED
ALLOWED_IF validation = PASS

APPROVED → ACTIVE
ALLOWED_IF authority approval exists

ACTIVE → SUPERSEDED
ALLOWED_IF replacement exists

SUPERSEDED → ARCHIVED
ALLOWED

QUARANTINED → ACTIVE
ALLOWED_IF revalidation = PASS
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 27. Production Authority Rule

This section defines authority handling for `Production Authority Rule`.

Authority must be declared, not inferred. Conflicts, duplicate source-of-truth claims and ambiguous precedence fail closed until a governed resolution exists.

Canonical options, fields or structures preserved from the source standard:

```text
ACTIVE
```
```text
controlled research
paper experiment
sandbox
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 28. Versioning Standard

This section defines lifecycle and version control for `Versioning Standard`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```text
MAJOR.MINOR.PATCH
```
```text
2.4.1
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 29. MAJOR Version

This section defines lifecycle and version control for `MAJOR Version`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```text
breaking schema change
authority change
semantic rule change
incompatible event change
decision behavior change
removed required field
changed lifecycle semantics
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 30. MINOR Version

This section defines lifecycle and version control for `MINOR Version`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```text
new optional field
new advisory rule
new enum value with compatibility
additional evidence metadata
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 31. PATCH Version

This section defines lifecycle and version control for `PATCH Version`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```text
typo
clarification
broken reference fix
format correction
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 32. Version Immutability

This section defines lifecycle and version control for `Version Immutability`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```text
silently updating the contents of v1.2.0
```
```text
v1.2.1
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

## 33. Supersession

This section defines lifecycle and version control for `Supersession`.

Behavior-affecting knowledge must be versioned. Active content may guide current behavior only when its metadata, ownership, source-of-truth status and validation evidence are valid.

Canonical options, fields or structures preserved from the source standard:

```yaml
supersedes: AI4B-GOV-POL-001@2.0.0
```
```yaml
superseded_by: AI4B-GOV-POL-001@2.1.0
```

Minimum acceptance rules:

- the object role is clear;
- owner, authority and lifecycle are explicit;
- source-of-truth behavior is declared;
- evidence and validation expectations are visible;
- unsupported or conflicting authority fails closed;
- trading-sensitive implications remain `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` unless separately authorized gates pass.

---
document_id: AI4B-GOV-SCHEMA-RFG-001
title: AI4BINANCE Repository Artifact Schema
document_type: REFERENCE
version: 1.0.3
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: NORMATIVE
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: repository_artifact_schema
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/schemas/reference_repository_artifact_schema.md
created_date: 2026-08-17
parent_standard: docs/standards/standard_repository_file_governance.md
machine_schema_path: schemas/governance/repository_artifact.schema.json
---

# AI4BINANCE Repository Artifact Schema

## ELI10

This schema describes the metadata every governed repository artifact should expose so validators can track ownership, lifecycle, location, and evidence.

## 1. Purpose

This schema defines the canonical metadata model for repository artifacts. It supports deterministic repository validation, ownership tracking, canonical path checks, lifecycle control, source/runtime separation and audit evidence.

This document is the human-readable schema reference. The machine-enforceable JSON Schema should be maintained at:

```text
schemas/governance/repository_artifact.schema.json
```

Use lifecycle_status as the canonical field; status is the frontmatter alias.

## 2. RepositoryArtifact Entity

```yaml
RepositoryArtifact:
  artifact_id: string
  file_id: string
  artifact_type: enum
  artifact_class: SOURCE | GOVERNANCE | RUNTIME | CACHE | REPORT | ARCHIVE
  domain: string
  owner: string
  canonical_path: string
  path: string
  filename: string
  mime_type: string
  size: integer
  modified_time: string
  shared_status: enum
  schema_version: semver
  lifecycle_status: enum
  generated: boolean
  immutable: boolean
  sensitive: boolean
  git_tracked: boolean
  checksum: string | null
  authority_layer: string | null
  authority_effect: string | null
  authority_scope: string | null
  observed_expected_layer: string
  authority_basis: list[string]
  action: enum
  result: enum
  proposed_path: string | null
  source_of_truth: boolean
  machine_enforceable: boolean
  audit_required: boolean
  classification: enum
  evidence_refs: list[string]
  validated_by: list[string]
  related_documents: list[string]
```

## 3. Required Fields

```yaml
required:
  - artifact_id
  - file_id
  - artifact_type
  - artifact_class
  - domain
  - owner
  - canonical_path
  - path
  - filename
  - mime_type
  - size
  - modified_time
  - shared_status
  - schema_version
  - lifecycle_status
  - generated
  - immutable
  - sensitive
  - git_tracked
  - checksum
  - authority_layer
  - authority_effect
  - authority_scope
  - observed_expected_layer
  - authority_basis
  - action
  - result
  - source_of_truth
  - machine_enforceable
  - audit_required
  - classification
```

## 4. Artifact ID

`artifact_id` must be stable, unique and repository-governed.

Pattern:

```text
AI4B-<DOMAIN>-<TYPE>-<NNN>
```

Examples:

```text
AI4B-GOV-STD-RFG-001
AI4B-GOV-SCHEMA-RFG-001
AI4B-GOV-CTRL-RFG-001
AI4B-GOV-RUN-RFG-001
```

## 5. Artifact Type Enum

```yaml
artifact_type:
  source:
    - SOURCE_CODE
    - TEST
    - CONFIG
    - SCHEMA
    - POLICY
    - GOVERNANCE
    - ONTOLOGY
    - WORKFLOW
    - ARTIFACT
  runtime:
    - DATA
    - MODEL
    - REPORT
    - LOG
    - STATE
    - RUNTIME
    - CACHE
    - EVIDENCE
  lifecycle:
    - ARCHIVE
```

## 6. Artifact Class Enum

```yaml
artifact_class:
  - SOURCE
  - GOVERNANCE
  - RUNTIME
  - CACHE
  - REPORT
  - ARCHIVE
```

`artifact_class` is the root-level filing governance classification. It is intentionally broader than `artifact_type` so the inventory can separate governed source, governance records, runtime state, cache output, reports/evidence and archive material before any migration.

## 7. Governance Layer Pyramid

```yaml
authority_layer:
  L0_EXTERNAL_MANDATORY_CONSTRAINTS:
    examples:
      - external laws
      - regulations
      - exchange terms
  L1_CORE_CONSTITUTION:
    examples:
      - docs/governance/policy_organization_constitution_handbook.md
  L2_GOVERNANCE_COMPLIANCE:
    examples:
      - docs/governance
      - docs/compliance
  L3_CANONICAL_CONTRACTS_SCHEMAS:
    examples:
      - docs/contracts
      - schemas
  L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES:
    examples:
      - docs/standards
      - docs/controls
      - docs/quality
      - policies
  L5_REGISTRIES_ROADMAP:
    examples:
      - docs/registries
      - docs/roadmap
  L6_ARCHITECTURE_ONTOLOGY_ADR:
    examples:
      - docs/architecture
      - docs/adr
      - ontology
  L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS:
    examples:
      - AGENTS.md
      - docs/governance/instruction_core_custom_instructions.md
      - docs/providers
      - docs/workflows
      - docs/procedures
      - docs/runbooks
      - src
      - tests
      - config
      - scripts
  L8_REPORTS_EVIDENCE_INVENTORIES:
    examples:
      - docs/reports
      - docs/inventories
      - runtime
  L9_REFERENCES_TEMPLATES:
    examples:
      - docs/references
      - docs/templates
  L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS:
    examples:
      - docs/archive
      - archive
```

`authority_layer` is the canonical repository authority layer carried by the
artifact record. `authority_basis` must record the evidence used to derive
`authority_layer`. Authority is not inferred from folder location alone. The
required evidence classes are metadata, registered policy, canonical path
validation, validation state, and downstream usage. For non-governed artifacts
or governed artifacts missing explicit authority metadata, `authority_layer`
may be `null`; `observed_expected_layer` remains a diagnostic filing hint only.

When `authority_layer` is `L0_EXTERNAL_MANDATORY_CONSTRAINTS`, the artifact
must be backed by a registry-level external-constraint record carrying
`external_constraint_id`, `source_uri`, `jurisdiction_or_provider`,
`effective_version`, `effective_date`, `retrieved_at`, `content_hash`,
`validation_status`, `supersedes`, `authority_scope`, and `affected_objects`.

`authority_effect` and `authority_scope` surface the explicit governed metadata
when the artifact is backed by a governed knowledge object. For non-governed
artifacts they remain `null`; they are not inferred from path, title,
`document_type`, `content_role`, or `source_of_truth`.

`observed_expected_layer` is a validator-computed filing signal based on
canonical placement expectations. It is diagnostic evidence only and must not
be treated as a source of authority.

## 8. Lifecycle Status Enum

```yaml
lifecycle_status:
  - DRAFT
  - RESEARCH
  - BACKTESTED
  - WALK_FORWARD_VALIDATED
  - OOS_VALIDATED
  - PAPER_APPROVED
  - LIVE_CANDIDATE
  - LIVE_APPROVED
  - ACTIVE
  - SUSPENDED
  - DEPRECATED
  - REJECTED
  - QUARANTINED
  - ARCHIVED
```

Use lifecycle_status as the canonical field; status is the frontmatter alias.

## 7. Classification Enum

```yaml
classification:
  - PUBLIC
  - INTERNAL
  - CONFIDENTIAL
  - RESTRICTED
  - SECRET
```

Repository artifacts must not contain secrets merely because they are classified as restricted or secret. Secret values belong outside Git and outside governed Markdown.

## 8. Canonical Path Rules

`canonical_path` must be repository-relative and use `/` separators.

Valid:

```text
docs/standards/standard_repository_file_governance.md
src/ai4binance/governance/repository/repository_validator.py
schemas/governance/repository_artifact.schema.json
```

Invalid:

```text
docs/standards/standard_repository_file_governance.md
C:\vscode-projects\ai4binance\docs\standard.md
H:\BackUP\Downloads\Repository-FileGovernanceStandard.md
```

Drive mirror paths may be recorded as `mirror_path` but must not replace `canonical_path`.

## 9. Filename Rules

Default filename style:

```text
lower_snake_case
```

Governed Markdown files:

```text
<document_type>_<domain>_<subject>.md
```

Runtime artifacts:

```text
<artifact_type>_<utc_timestamp>_<short_id>.<ext>
```

Reserved conventional exceptions:

```text
README.md
AGENTS.md
LICENSE
CHANGELOG.md
CODEOWNERS
SECURITY.md
CONTRIBUTING.md
Dockerfile
Makefile
```

## 10. Source of Truth Rules

Only one active source-of-truth artifact may define the same governed concept.

```yaml
source_of_truth_policy:
  duplicate_active_source_of_truth_allowed: false
  unresolved_conflict_status:
    - GOVERNANCE_CONFLICT
    - RUNNING_WITH_BLOCKERS
  trading_sensitive_status:
    - RESEARCH_ONLY
    - LIVE_ORDER_BLOCKED
```

## 11. Generated Artifact Rules

Generated artifacts must state or imply:

```yaml
generated: true
source_of_truth: false
```

Exceptions require explicit promotion through governance and validation evidence.

Generated artifacts must not be written under:

```text
src/
docs/standards/
docs/policies/
docs/governance/
schemas/
```

## 12. Git Tracking Rules

```yaml
git_tracking_policy:
  source_code: tracked
  tests: tracked
  configs_without_secrets: tracked
  governed_docs: tracked
  schemas: tracked
  generated_artifacts: usually_untracked_or_selectively_tracked
  runtime_state: untracked
  logs: untracked
  secrets: never_tracked
  caches: never_tracked
```

## 13. Sensitive Artifact Rules

Sensitive artifacts must not expose credentials, private keys, tokens, raw API secrets, restricted account data or live-order bypass material.

```yaml
sensitive_artifact_policy:
  secrets_in_repository: forbidden
  secrets_in_logs: forbidden
  full_api_keys_in_reports: forbidden
  private_keys_in_docs: forbidden
  wallet_private_keys_anywhere: forbidden
```

## 14. Evidence and Validation Fields

Recommended optional fields:

```yaml
evidence_refs:
  - artifacts/audits/repository_audit_20260817T184900Z.json
validated_by:
  - tests/test_repository_validator.py
  - tests/test_docs_hygiene.py
implemented_by:
  - src/ai4binance/governance/repository_validator.py
quality_gate:
  - scripts/quality.ps1
```

## 15. Minimal YAML Example

```yaml
artifact_id: AI4B-GOV-STD-RFG-001
artifact_type: STANDARD
domain: governance
owner: Enterprise Engineering Governance
canonical_path: docs/standards/standard_repository_file_governance.md
filename: standard_repository_file_governance.md
schema_version: 1.0.0
lifecycle_status: ACTIVE
generated: false
immutable: false
sensitive: false
git_tracked: true
checksum: null
source_of_truth: true
machine_enforceable: true
audit_required: true
classification: INTERNAL
evidence_refs: []
validated_by:
  - tests/test_repository_validator.py
related_documents:
  - docs/controls/control_repository_validation_rules.md
```

## 16. JSON Schema Draft

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://ai4binance.local/schemas/governance/repository_artifact.schema.json",
  "title": "AI4BINANCE RepositoryArtifact",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "artifact_id",
    "artifact_type",
    "domain",
    "owner",
    "canonical_path",
    "filename",
    "schema_version",
    "lifecycle_status",
    "generated",
    "sensitive",
    "git_tracked",
    "authority_layer",
    "observed_expected_layer",
    "authority_basis",
    "source_of_truth",
    "machine_enforceable",
    "audit_required",
    "classification"
  ],
  "properties": {
    "artifact_id": {"type": "string", "pattern": "^AI4B-[A-Z0-9]+-[A-Z0-9]+-[0-9]{3}$"},
    "artifact_type": {"type": "string"},
    "domain": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
    "owner": {"type": "string", "minLength": 1},
    "canonical_path": {"type": "string", "pattern": "^[a-z0-9_./-]+$"},
    "filename": {"type": "string", "minLength": 1},
    "schema_version": {"type": "string", "pattern": "^[0-9]+\.[0-9]+\.[0-9]+$"},
    "lifecycle_status": {
      "type": "string",
      "description": "Use lifecycle_status as the canonical field; status is the frontmatter alias.",
      "enum": ["DRAFT", "RESEARCH", "BACKTESTED", "WALK_FORWARD_VALIDATED", "OOS_VALIDATED", "PAPER_APPROVED", "LIVE_CANDIDATE", "LIVE_APPROVED", "ACTIVE", "SUSPENDED", "DEPRECATED", "REJECTED", "QUARANTINED", "ARCHIVED"]
    },
    "generated": {"type": "boolean"},
    "immutable": {"type": "boolean"},
    "sensitive": {"type": "boolean"},
    "git_tracked": {"type": "boolean"},
    "checksum": {"type": ["string", "null"]},
    "authority_layer": {
      "type": "string",
      "description": "Canonical authority layer derived from governed evidence and authority_basis.",
      "enum": [
        "L0_EXTERNAL_MANDATORY_CONSTRAINTS",
        "L1_CORE_CONSTITUTION",
        "L2_GOVERNANCE_COMPLIANCE",
        "L3_CANONICAL_CONTRACTS_SCHEMAS",
        "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        "L5_REGISTRIES_ROADMAP",
        "L6_ARCHITECTURE_ONTOLOGY_ADR",
        "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "L8_REPORTS_EVIDENCE_INVENTORIES",
        "L9_REFERENCES_TEMPLATES",
        "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS"
      ]
    },
    "authority_effect": {
      "type": [
        "string",
        "null"
      ],
      "description": "Explicit authority effect from governed metadata when present; null for non-governed artifacts.",
      "enum": [
        "MANDATORY_CONSTRAINT",
        "NORMATIVE_CONSTRAINT",
        "OPERATIONAL_SPECIALIZATION",
        "IMPLEMENTATION",
        "EVIDENCE_ONLY",
        "REFERENCE_ONLY",
        "ARCHIVE_ONLY",
        null
      ]
    },
    "observed_expected_layer": {
      "type": "string",
      "enum": [
        "L0_EXTERNAL_MANDATORY_CONSTRAINTS",
        "L1_CORE_CONSTITUTION",
        "L2_GOVERNANCE_COMPLIANCE",
        "L3_CANONICAL_CONTRACTS_SCHEMAS",
        "L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES",
        "L5_REGISTRIES_ROADMAP",
        "L6_ARCHITECTURE_ONTOLOGY_ADR",
        "L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS",
        "L8_REPORTS_EVIDENCE_INVENTORIES",
        "L9_REFERENCES_TEMPLATES",
        "L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS"
      ]
    },
    "authority_basis": {
      "type": "array",
      "minItems": 1,
      "items": {"type": "string", "minLength": 1},
      "uniqueItems": true
    },
    "source_of_truth": {"type": "boolean"},
    "machine_enforceable": {"type": "boolean"},
    "audit_required": {"type": "boolean"},
    "classification": {"type": "string", "enum": ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "SECRET"]},
    "evidence_refs": {"type": "array", "items": {"type": "string"}},
    "validated_by": {"type": "array", "items": {"type": "string"}},
    "related_documents": {"type": "array", "items": {"type": "string"}}
  }
}
```

## 17. Acceptance Criteria

A RepositoryArtifact record is valid only when:

- required fields are present;
- canonical path is repository-relative;
- filename complies with naming rules or reserved exceptions;
- lifecycle is explicit;
- owner is explicit;
- source-of-truth behavior is explicit;
- generated and runtime artifacts are not confused with governed source documents;
- sensitive artifacts do not expose secrets;
- evidence references are stable where required.



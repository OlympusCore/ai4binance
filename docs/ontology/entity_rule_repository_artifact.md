---
document_id: AI4B-GOV-ONT-001
title: AI4BINANCE RepositoryArtifact Ontology Note
document_type: ENTITY_RULE
version: 1.0.3
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L6_ARCHITECTURE_ONTOLOGY_ADR
authority_scope: repository_artifact
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/ontology/entity_rule_repository_artifact.md
---

# RepositoryArtifact Ontology Note

## ELI10

This note names the repository artifact entity fields used by the validator and
points to the machine schema that enforces the detailed contract.

`RepositoryArtifact` is the governed entity used to describe repository files in
a path-independent way.

Minimum identity fields:

- artifact_id
- file_id
- artifact_type
- domain
- owner
- canonical_path
- path
- filename
- mime_type
- size
- modified_time
- shared_status
- lifecycle_status
- generated
- immutable
- sensitive
- git_tracked
- checksum
- authority_layer
- observed_expected_layer
- authority_basis
- action
- result
- proposed_path

The canonical machine schema is
`schemas/governance/repository_artifact.schema.json`.

`authority_basis` records why the validator assigned the Authority Pyramid
layer. It must include evidence from governed metadata, registered policy,
canonical path validation, validation status, and downstream usage. Folder
placement alone is not authority.

The canonical `authority_layer` values are:

- `L0_EXTERNAL_MANDATORY_CONSTRAINTS`
- `L1_CORE_CONSTITUTION`
- `L2_GOVERNANCE_COMPLIANCE`
- `L3_CANONICAL_CONTRACTS_SCHEMAS`
- `L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES`
- `L5_REGISTRIES_ROADMAP`
- `L6_ARCHITECTURE_ONTOLOGY_ADR`
- `L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS`
- `L8_REPORTS_EVIDENCE_INVENTORIES`
- `L9_REFERENCES_TEMPLATES`
- `L10_ARCHIVE_STRUCTURAL_PLACEHOLDERS`

Executable code and file placement may implement or consume authority, but they
do not create semantic authority by themselves. The validator must derive
`authority_layer` from governed evidence, not from implementation location
alone. The validator may compute `observed_expected_layer` from canonical
placement as a filing signal, but that value is not authority.

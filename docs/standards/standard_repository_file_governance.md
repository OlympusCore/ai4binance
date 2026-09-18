---
document_id: AI4B-GOV-STD-RFG-001
title: AI4BINANCE Repository File Governance Standard
document_type: STANDARD
version: 1.2.5
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: repository_file_governance
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/standards/standard_repository_file_governance.md
supersedes_document_ids:
  - AI4B-GOV-REPO-001
retired_source_filenames:
  - docs/standards/standard_repository_file_governance.md
  - Repository-FileGovernanceStandard.md
governs:
  - folder_structure
  - folder_names
  - file_structure
  - file_names
  - canonical_paths
  - source_runtime_separation
  - generated_artifacts
  - repository_hygiene
  - governed_document_locking
  - rename_move_delete_control
  - repository_migration_records
  - path_security
  - deterministic_repository_validation
delegates_knowledge_governance_to:
  - docs/standards/standard_documentation_knowledge_governance.md
references:
  - docs/schemas/reference_repository_artifact_schema.md
  - docs/controls/control_repository_validation_rules.md
  - docs/runbooks/runbook_repository_migration_hygiene.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
implemented_by:
  - src/ai4binance/governance/repository_validator.py
validated_by:
  - tests/test_repository_validator.py
  - tests/test_docs_hygiene.py
  - tests/test_artifact_hygiene_scripts.py
quality_gate:
  - scripts/quality.ps1
---
# AI4BINANCE Repository File Governance Standard

## ELI10

This standard controls where repository files belong, how they are named, and how deterministic validation keeps unsafe layout visible.

## 1. Purpose

`AI4B-GOV-REPO-001` defines repository file and folder governance for AI4BINANCE.
The implementation contract is enforced by `RepositoryPolicy`, the `RepositoryArtifact Schema`, `repository_validator.py`, and the quality gate.
The standard keeps `RUNNING_WITH_BLOCKERS`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` visible when blockers remain.

## 2. Scope Boundary

This index preserves the stable source-of-truth path for repository file governance.
Detailed normative sections are split into the files below.

## 3. Authority and Source-of-Truth

This document and its split standards form one governed standard family.

## Split Standard Files

| File | Scope |
| --- | --- |
| `docs/standards/standard_repository_structure_governance.md` | AI4BINANCE Repository Structure Governance Standard |
| `docs/standards/standard_repository_naming_governance.md` | AI4BINANCE Repository Naming Governance Standard |
| `docs/standards/standard_repository_artifact_separation_governance.md` | AI4BINANCE Repository Artifact Separation Governance Standard |
| `docs/standards/standard_repository_validator_governance.md` | AI4BINANCE Repository Validator Governance Standard |

## 32. Minimum Acceptance Criteria

- Repository layout, source/runtime separation, governed Markdown naming, and artifact placement are deterministic.
- The `docs/README.md` documentation authority index remains an explicit docs-root naming exception and does not redefine higher authority.
- Canonical governed Markdown documentation remains under `docs/` except approved repository entrypoint and scope-local instruction files.
- Allowlisted governed operational Markdown exceptions remain explicitly enumerated and do not expand by convention.
- Non-canonical operational state Markdown outside `runtime/` must remain non-authoritative and fail closed on canonical authority claims.
- Generated Markdown under `runtime/` remains non-canonical until an explicit governed promotion process reclassifies it.
- Generated artifact lifecycle, provenance, retention, cleanup, and run-isolation rules remain under `artifact_hygiene` regardless of whether the artifact uses `.md`, `.json`, `.csv`, or another extension.
- Full quality_gate evidence is required before reporting completion for behavior-changing governance work.
- `LIVE_ORDER_BLOCKED` remains unchanged.

## 33. Quality Gate Integration

Repository governance validation must remain part of the quality gate.

## 33.1 Governed Document Lock

Active governed Markdown documents that are `source_of_truth: true`,
`machine_enforceable: true`, or `content_role: POLICY_AS_CODE` are locked by
default. Locked documents must remain registered in
`config/governance/governed_document_lock_manifest.json` with a current SHA-256
baseline and `LOCKED` state.

The governed document lock manifest is itself a protected governance manifest.
It must declare a `manifest_lock_policy` requiring `LOCKED` state,
`WRITTEN_OWNER_APPROVAL_REQUIRED`, written owner approval, and filesystem write
protection where the host filesystem supports it.

Each locked document record must carry enough governance registration metadata
to validate the full control chain before hash acceptance:

```text
Governed Markdown
      -> manifest registration
      -> canonical_path / authority_level / document_status / version
      -> expected_hash / source_of_truth / supersedes / allowed_change_process
      -> filesystem lock state
      -> hash and approval-aware integrity verification
      -> PASS or GOVERNED_DOCUMENT_LOCK_VIOLATION
```

Changing a locked governed document, removing it from the manifest, changing its
baseline hash, or weakening its approval policy requires explicit written owner
approval before the change may be treated as compliant. Without matching written
approval evidence, repository validation must report:

```text
GOVERNED_DOCUMENT_LOCK_VIOLATION
RUNNING_WITH_BLOCKERS
```

The lock mechanism protects governance conditions and machine-enforceable
repository rules. It does not authorize live trading, deployment, destructive
Git operations, or financial execution.

## 34. Final Governing Principle

Correctness, auditability, and fail-closed operation take precedence over cosmetic cleanup.


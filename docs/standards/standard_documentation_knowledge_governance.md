---
document_id: AI4B-GOV-STD-DKG-CORE-001
title: AI4BINANCE Documentation and Knowledge Governance Core Standard
document_type: STANDARD
version: 1.1.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: documentation_knowledge_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/standards/standard_documentation_knowledge_governance.md
supersedes_document_ids:
  - AI4B-GOV-STD-DKG-001
split_from:
  document_id: AI4B-GOV-STD-DKG-001
  retired_source_filename: docs/standards/standard_documentation_knowledge_governance.md
companion_documents:
  taxonomy_reference: docs/references/reference_governed_knowledge_taxonomy.md
  templates: docs/templates/reference_governed_knowledge_object_template.md
delegates_to:
  repository_file_governance:
    canonical_path: docs/standards/standard_repository_file_governance.md
    scope: physical_paths_folder_structure_file_names_runtime_artifacts
---
# AI4BINANCE Documentation and Knowledge Governance Core Standard

## ELI10

This core standard keeps repository knowledge governed instead of free-form Markdown. Detailed standard sections are split into smaller authoritative files.

Governed Markdown frontmatter should use `canonical_path` as the single canonical location field. The older path spelling is retired and must not be reintroduced. Where a document declares `source_of_truth: true`, its frontmatter should also declare `source_of_truth_scope` so the authority boundary is visible. Governed Markdown frontmatter serializes lifecycle state with `status` for validator compatibility; the canonical lifecycle concept remains `lifecycle_status` and must not diverge semantically.

## Split Design

| File | Scope |
| --- | --- |
| `docs/standards/standard_governed_knowledge_metadata.md` | AI4BINANCE Governed Knowledge Metadata Standard |
| `docs/standards/standard_governed_knowledge_registry_change.md` | AI4BINANCE Governed Knowledge Registry and Change Standard |
| `docs/standards/standard_governed_knowledge_authority_workflow.md` | AI4BINANCE Governed Knowledge Authority and Workflow Standard |
| `docs/standards/standard_terminology_governance.md` | AI4BINANCE Terminology Governance Standard |

## Scope Boundary

Physical folder structure, file naming, canonical file paths, runtime artifact placement and repository hygiene are delegated to `docs/standards/standard_repository_file_governance.md`.

The canonical `docs/` information architecture is defined by
`docs/standards/standard_repository_structure_governance.md`. Under that
structure, governance knowledge is organized by `constitution/`, `authority/`,
`decision/`, `execution/`, `promotion/`, and `repository/`, while architecture
knowledge is organized by `system/`, `data/`, `decision/`, `runtime/`, and
`integration/`. Transitional legacy support folders do not redefine the
canonical taxonomy.

## Repository Content Language

This required core section remains anchored here and is detailed in the split governed standards above.

## Purpose

This required core section remains anchored here and is detailed in the split governed standards above.

## Core Principles

This required core section remains anchored here and is detailed in the split governed standards above.

## Mandatory GovernedKnowledgeObject Schema

This required core section remains anchored here and is detailed in the split governed standards above.

## Knowledge ID Standard

This required core section remains anchored here and is detailed in the split governed standards above.

## Authority Levels

This required core section remains anchored here and is detailed in the split governed standards above.

## Authority Precedence

This required core section remains anchored here and is detailed in the split governed standards above.

## Conflict Resolution

This required core section remains anchored here and is detailed in the split governed standards above.

## Source-of-Truth Governance

This required core section remains anchored here and is detailed in the split governed standards above.

## LLM Knowledge Boundary

This required core section remains anchored here and is detailed in the split governed standards above.

## Minimum Acceptance Criteria

This required core section remains anchored here and is detailed in the split governed standards above.

## Constitutional Lock

This required core section remains anchored here and is detailed in the split governed standards above.

## Target State

This required core section remains anchored here and is detailed in the split governed standards above.

The `AI4B-GOV-DKG-001` Documentation and Knowledge Governance Standard requires `GovernedKnowledgeObject`, `RepositoryPolicy`, `RepositoryArtifact schema`, deterministic repository_validator, full quality gate evidence, duplicate active source-of-truth concept conflicts, concept-level `authority_scope` ownership resolution, lower-authority semantic override blockers, non-code repository content language = en-US, `canonical_path` as the single canonical location field, `source_of_truth_scope` for active authoritative documents, `RUNNING_WITH_BLOCKERS`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED`.


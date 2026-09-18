---
document_id: AI4B-GOV-RUN-RFG-001
title: AI4BINANCE Repository Migration and Hygiene Runbook
document_type: RUNBOOK
version: 1.0.1
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: repository_migration_hygiene
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: repository_migration_hygiene_runbook
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/runbooks/runbook_repository_migration_hygiene.md
created_date: 2026-08-17
parent_standard: docs/standards/standard_repository_file_governance.md
related_controls: 
related_schema: 
  - docs/controls/control_repository_validation_rules.md
  - docs/schemas/reference_repository_artifact_schema.md
  - schemas/governance/repository_backup_manifest.schema.json
---

# AI4BINANCE Repository Migration and Hygiene Runbook

## ELI10

This runbook explains how repository moves, renames, cleanup, and hygiene work should be planned, approved, validated, and recorded.

## 1. Purpose

This runbook defines the controlled workflow for repository rename, move, cleanup, hygiene and migration activities.

It supports safe normalization from legacy paths such as:

```text
docs/standards/standard_repository_file_governance.md
```

to canonical paths such as:

```text
docs/standards/standard_repository_file_governance.md
```

## 2. Safety Boundary

This runbook is not authorization to delete, move, rename, stage, commit, push, reset, clean or rewrite history.

Default state:

```text
NO_CHANGE
RESEARCH_ONLY
NOT_VERIFIED
LIVE_ORDER_BLOCKED
```

Operations remain blocked until explicit human authorization and required validation evidence exist.

## 3. Controlled Workflow

```text
INSPECT
-> UNDERSTAND
-> ASSESS
-> PLAN
-> IMPACT_ANALYSIS
-> APPROVAL
-> IMPLEMENT
-> TEST
-> REVIEW
-> REPORT
```

No step may be silently skipped.

## 4. Migration Scope Types

```yaml
migration_scope_types:
  DOCS_NORMALIZATION:
    examples:
      - docs/ -> docs/
      - ALL_CAPS.md -> lower_snake_case.md
  SOURCE_REFACTOR:
    examples:
      - ambiguous module rename
      - folder domain correction
  RUNTIME_CLEANUP:
    examples:
      - cache exclusion
      - generated artifact relocation
  SECURITY_CLEANUP:
    examples:
      - secret exposure removal
      - log redaction
  ARCHIVE_MIGRATION:
    examples:
      - deprecated document retention
      - superseded artifact movement
```

## 5. Pre-Migration Inspection

Before any change, inspect:

```text
AGENTS.md
README.md
docs/registries/registry_documentation_index.md
docs/standards/standard_documentation_knowledge_governance.md
docs/standards/standard_repository_file_governance.md
schemas/governance/repository_artifact.schema.json
tests/test_repository_validator.py
tests/test_docs_hygiene.py
scripts/quality.ps1
```

If any file is missing, mark the migration:

```text
RUNNING_WITH_BLOCKERS
NOT_VERIFIED
```

## 6. Migration Record Format

```yaml
repository_migration_record:
  migration_id: RFG-MIG-20260817-001
  created_at_utc: 2026-08-17T18:49:00Z
  requested_by: Huseyin Cicek
  scope: DOCS_NORMALIZATION
  source_path: docs/standards/standard_repository_file_governance.md
  target_path: docs/standards/standard_repository_file_governance.md
  action: RENAME_AND_MOVE
  reason: normalize_to_lower_snake_case_document_type_pattern
  impact:
    links: true
    canonical_path: true
    tests: true
    compliance_matrix: true
    codex_instructions: true
    drive_mirror: true
  required_checks:
    - link_check
    - canonical_path_check
    - repository_validator
    - docs_hygiene_tests
    - governance_constitution_sync_tests
  approval:
    required: true
    status: PENDING
  execution:
    status: NOT_EXECUTED
  final_status:
    - NO_CHANGE
    - NOT_VERIFIED
```

## 7. docs Normalization Target Map

Recommended repository paths:

```text
docs/standards/standard_repository_file_governance.md
docs/schemas/reference_repository_artifact_schema.md
docs/controls/control_repository_validation_rules.md
docs/runbooks/runbook_repository_migration_hygiene.md
```

Related DKG split paths:

```text
docs/standards/standard_documentation_knowledge_governance.md
docs/references/reference_governed_knowledge_taxonomy.md
docs/templates/reference_governed_knowledge_object_template.md
```

## 8. Impact Analysis Checklist

Before implementation, check:

```yaml
impact_analysis_checklist:
  source_exists: required
  target_folder_exists: required
  target_path_not_existing_or_intentionally_overwritten: required
  internal_links_identified: required
  front_matter_canonical_path_identified: required
  docs_readme_references_identified: required
  compliance_matrix_references_identified: required
  AGENTS_or_provider_instruction_references_identified: required
  test_references_identified: required
  import_references_identified_if_source_code: conditional
  git_case_collision_risk_checked: required
  drive_mirror_boundary_checked: required
  rollback_plan_defined: required
```

## 9. Link Update Checklist

Update references in:

```text
docs/registries/registry_documentation_index.md
docs/compliance/registry_compliance_matrix.md
AGENTS.md
Claude.md
docs/governance/instruction_core_custom_instructions.md
.codex/
.github/
tests/
scripts/
schemas/
```

Only update files that actually contain old references.

## 10. Canonical Path Update Checklist

For each moved governed document, update:

```yaml
canonical_path: <new_repository_relative_path>
related_documents: <new_paths_if_needed>
supersedes: <old_paths_if_needed>
```

Do not use Google Drive paths as canonical paths.

## 11. Case-Only Rename Procedure for Windows

Windows and some Drive mirrors may not reliably process case-only renames.

If renaming only by case, use an intermediate path:

```text
docs/ -> docs_tmp_migration/ -> docs/
scripts/ -> scripts_tmp_migration/ -> scripts/
```

Check for collisions before and after.

## 12. Safe Execution Sequence

For approved changes only:

```text
1. Create missing target folders.
2. Move or rename one logical group at a time.
3. Update front matter canonical_path fields.
4. Update internal links.
5. Update registries and compliance matrix references.
6. Run repository validator.
7. Run docs hygiene tests.
8. Run quality gate.
9. Review git diff.
10. Generate migration report.
```

Do not batch unrelated migrations.

## 13. Forbidden Actions Without Explicit Authorization

```text
rm -rf
git clean -fdx
git reset --hard
git push --force
history rewrite
secret rotation
credential deletion
mass delete
mass rename
live execution config changes
```

## 14. Drive Mirror Hygiene

Drive mirror is not canonical source-of-truth.

Exclude or ignore:

```text
.git/
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.hypothesis/
.ruff_cache/
.coverage
.pytest-tmp-*/
logs/runtime/
runtime/state/local/
secrets/
```

If a Drive-visible artifact is excluded, do not promote it to governed documentation merely because it exists in the mirror.

Backup manifests are evidence-only records. They must use the repository backup
manifest schema and preserve these invariants:

```yaml
authority: BACKUP_ONLY
source_of_truth: false
contains_secrets: false
may_override_repository: false
may_define_authority: false
may_promote_runtime_artifacts: false
```

Backup manifests may include local checkout paths, Drive mirror paths, checksum
files, and commit identifiers as recovery evidence. They must not create a new
source-of-truth, override canonical repository paths, promote runtime output, or
store secrets.

## 15. Repository Cleanup Categories

```yaml
cleanup_categories:
  KEEP:
    meaning: valid canonical artifact
  MOVE:
    meaning: valid artifact in wrong location
  RENAME:
    meaning: valid artifact with non-compliant name
  RENAME_AND_MOVE:
    meaning: valid artifact with wrong name and wrong location
  ARCHIVE:
    meaning: retained but no longer active
  DELETE_CANDIDATE:
    meaning: requires explicit review before deletion
  EXCLUDE_FROM_GIT:
    meaning: local/runtime/cache/secrets artifact
  CONTENT_REVIEW_REQUIRED:
    meaning: cannot classify safely from path or metadata alone
```

## 16. Validation Commands

Use repository-approved commands only. Example intended commands:

```powershell
.\scripts\quality.ps1
python -m pytest tests/test_repository_validator.py tests/test_docs_hygiene.py
```

If commands are not executed, report:

```text
NOT_VERIFIED
```

Never claim tests passed without actual execution evidence.

## 17. Rollback Plan

Every migration must include rollback information:

```yaml
rollback_plan:
  old_path: docs/standards/standard_repository_file_governance.md
  new_path: docs/standards/standard_repository_file_governance.md
  rollback_action: MOVE_BACK_AND_RESTORE_REFERENCES
  prerequisites:
    - preserve_git_history
    - preserve_backup_or_commit_reference
    - preserve_migration_record
```

Rollback must not discard unrelated user work.

## 18. Post-Migration Report

```yaml
repository_migration_report:
  migration_id: RFG-MIG-20260817-001
  completed_at_utc: null
  files_moved: []
  files_renamed: []
  files_archived: []
  files_deleted: []
  links_updated: []
  canonical_paths_updated: []
  tests_executed: []
  validator_status: NOT_EXECUTED
  final_status:
    - NOT_VERIFIED
    - NO_CHANGE
```

## 19. Acceptance Criteria

A migration is complete only when:

- source and target paths are recorded;
- canonical path metadata is updated;
- internal links are updated;
- registries are updated;
- case collisions are absent;
- excluded Drive artifacts remain excluded;
- repository validator evidence exists;
- docs hygiene test evidence exists;
- quality gate evidence exists;
- final report is created;
- no live trading or execution authority is changed.

## 20. Final Safety Rule

If the migration state is unknown, inconsistent, unvalidated, unauthorized, stale or unsafe, do not change files.

Return:

```text
NO_CHANGE
RUNNING_WITH_BLOCKERS
NOT_VERIFIED
LIVE_ORDER_BLOCKED
```





---
document_id: AI4B-GOV-STD-RFG-104
title: AI4BINANCE Repository Validator Governance Standard
document_type: STANDARD
version: 1.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: repository_validator_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/standards/standard_repository_validator_governance.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# AI4BINANCE Repository Validator Governance Standard

## ELI10

This standard section defines import boundaries, RepositoryArtifact schema, relationship rules, hard rules, forbidden filenames, mirror rules, migration records, repository_validator.py, quality gate, and live-blocked safety outcomes.

## Source Lineage

- Source file: `docs/standards/standard_repository_file_governance.md`
- Source section start: `## 22. Import Boundary Rules`
- This file preserves a bounded section of the governed source document.

## 22. Import Boundary Rules

Layered import boundaries must be deterministic.

Recommended rules:

```yaml
import_boundary_rules:
  core:
    may_import: []
  domain:
    may_import:
      - core
    must_not_import:
      - infrastructure
      - integrations
      - cli
  application:
    may_import:
      - core
      - domain
  infrastructure:
    may_import:
      - core
      - domain
      - application
  integrations:
    may_import:
      - core
      - domain
      - application
  cli:
    may_import:
      - core
      - application
      - infrastructure
      - integrations
```

Trading-sensitive code must not bypass:

```text
Decision Governance Engine
Risk Governance
Execution Authorization
Audit Logging
```

Any bypass must be reported as:

```text
GOVERNANCE_BYPASS
LIVE_ORDER_BLOCKED
RUNNING_WITH_BLOCKERS
```

## 23. RepositoryArtifact Schema Reference

Every governed repository artifact should be representable as a `RepositoryArtifact`.

Minimum fields:

```yaml
artifact_id: string
artifact_type: SOURCE | TEST | CONFIG | SCHEMA | POLICY | DOC | DATA | ARTIFACT | REPORT | STATE | LOG | TOOL | MIGRATION | ARCHIVE
domain: string
owner: string
canonical_path: string
filename: string
schema_version: string
lifecycle_status: DRAFT | ACTIVE | DEPRECATED | SUPERSEDED | ARCHIVED
generated: boolean
immutable: boolean
sensitive: boolean
git_tracked: boolean
checksum: string
```

The normative schema reference is:

```text
docs/schemas/reference_repository_artifact_schema.md
```

The machine-readable schema should be maintained at:

```text
schemas/governance/repository_artifact.schema.json
```

## 24. Repository Relationship Rules

Repository artifacts may have relationships such as:

```text
IMPLEMENTS
VALIDATED_BY
CONFIGURED_BY
GENERATES
DERIVES_FROM
REFERENCES
SUPERSEDES
OWNED_BY
EVIDENCED_BY
BLOCKED_BY
```

Relationship rules:

1. A source file may be validated by one or more tests.
2. A governed document may reference schemas, controls, tests, and implementation files.
3. A generated report must derive from one or more machine-readable artifacts.
4. A runtime artifact must not supersede a governed source document.
5. An archived artifact must not be an active source-of-truth.
6. A schema must not be silently duplicated under another folder.
7. A config file must not override a normative policy without explicit authority.

## 25. Repository Hard Rules

Hard rules:

```yaml
hard_rules:
  source_code_inside_src: required
  tests_inside_tests: required
  active_repository_root_resolution: runtime_dynamic
  generated_artifacts_inside_src: forbidden
  runtime_state_inside_src: forbidden
  secrets_in_repository: forbidden
  hardcoded_absolute_paths: forbidden
  duplicate_authoritative_documents: forbidden
  ambiguous_filenames: forbidden
  source_of_truth_filename_uppercase: forbidden
  source_of_truth_reserved_filename_exceptions:
    - AGENTS.md
    - README.md
  canonical_path_required: true
  owner_required: true
  artifact_type_required: true
  path_traversal: forbidden
  llm_delete_without_approval: forbidden
  llm_rename_without_approval: forbidden
  llm_move_without_approval: forbidden
  validator_bypass: forbidden
```

A hard-rule violation must produce at least:

```text
RUNNING_WITH_BLOCKERS
```

Security-critical violations must produce:

```text
SECURITY_CRITICAL
RUNNING_WITH_BLOCKERS
```

If trading execution may be affected:

```text
LIVE_ORDER_BLOCKED
```

## 26. Forbidden Filename Dictionary

Forbidden or discouraged filename patterns:

```text
utils
helpers
common
misc
functions
manager
data
temp
tmp
new
old
copy
copy_of
backup
bak
final
final_v2
test2
untitled
draft_final
really_final
```

These names may be allowed only when a narrow, explicit domain meaning exists and is documented.

Preferred replacements:

```text
symbol_normalizer.py
timestamp_parser.py
price_rounding.py
risk_budget_calculator.py
decision_lineage_builder.py
repository_validator.py
```

## 27. Drive Mirror and Local-Only Artifact Rules

Google Drive mirror paths are review and assistant-context mirrors only.

They must not override repository-relative canonical paths.

Correct:

```yaml
canonical_path: docs/standards/standard_repository_file_governance.md
mirror_path: .\GoogleDrive\Projects\CanonicalRepoMirror\docs\standards\standard_repository_file_governance.md
```

Incorrect:

```yaml
canonical_path: C:\vscode-projects\ai4binance\docs\standards\standard_repository_file_governance.md
```

Mirror-visible artifacts that are excluded by default:

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

Presence in Google Drive does not imply governance status.

## 28. Rename / Move / Delete Control

Rename, move, and delete operations are controlled changes.

They require:

- impact analysis
- link update plan
- canonical path update plan
- registry update plan
- validator execution
- test execution when relevant
- rollback plan
- human approval for destructive or high-impact changes

LLMs may draft migration plans and impact summaries.

LLMs must not independently delete, rename, move, hide, or bypass governed files.

## 29. Repository Migration Record Format

Every controlled move or rename should produce a migration record.

Example:

```yaml
migration_id: RFG-MIG-20260817-001
source_path: docs/standards/standard_repository_file_governance.md
target_path: docs/standards/standard_repository_file_governance.md
action: RENAME_AND_MOVE
reason: normalize_to_lower_snake_case_document_type_pattern
risk: MEDIUM
impact:
  links: true
  canonical_path: true
  tests: true
  compliance_matrix: true
  codex_instructions: true
required_checks:
  - link_check
  - canonical_path_check
  - repository_validator
  - docs_hygiene_tests
  - artifact_hygiene_tests
  - governance_constitution_sync_tests
status: PROPOSED
```

Migration records should be stored under:

```text
migrations/repository/
```

or as human-readable reports under:

```text
docs/reports/
```

## 30. Deterministic Repository Validator

The repository validator should check:

```text
folder naming
file naming
dynamic active repository root resolution
canonical paths
forbidden names
source-of-truth filename uppercase
case collisions
path traversal
source/runtime separation
generated artifact placement
documentation metadata
duplicate source-of-truth documents
schema references
ownership metadata
hardcoded absolute paths
secret exposure
import boundaries
orphaned artifacts
broken internal links
```

The validator must treat `runtime/` as the canonical grouping root for
mutable, generated, reproducible, and execution/run-produced outputs before it
validates subfolder placement. Files whose deletion would make the repository
undefined do not belong under `runtime/`.

Validator output must be machine-readable.

Recommended output location:

```text
runtime/artifacts/repository_validation/
```

Human-readable summaries may be written to:

```text
runtime/reports/repository_validation/
```

The validator must not grant live trading authority.

## 30.0 Hygiene Control Boundary

`doc_hygiene` and `artifact_hygiene` are related but distinct repository
hygiene control planes.

- `doc_hygiene` governs canonical governed human-readable documentation under
  `docs/**`, including authority metadata, canonical placement, duplicate and
  superseded document detection, broken internal references, and constitution /
  governance / compliance semantic sync.
- `artifact_hygiene` governs generated artifacts regardless of file extension,
  including generated Markdown under `runtime/**`, coverage outputs, validator
  outputs, audit evidence, benchmark results, and run-scoped retention or
  cleanup behavior.
- `doc_hygiene` may inspect generated Markdown only for misclassification,
  unauthorized canonical claims, or promotion-boundary violations. It does not
  own runtime artifact lifecycle, provenance, retention, cleanup, or storage
  rules.

Recommended validator rule families:

```text
DOC-*
ARTIFACT-*
RUNTIME-*
```

## 30.1 Canonical Governance Decision Anchor

The repository validator and its supporting standards must preserve the
following decision anchor without semantic drift:

```text
Docs are authority.
Validator is enforcement.
Quality gate is evidence.
Human governance is consequential authority.
Runtime is not source-of-truth.
LLM is not authority.
Scores cannot hide blockers.
LIVE remains blocked.
```

Interpretation:

- Governed documents define authority and source-of-truth boundaries.
- `repository_validator.py` is the deterministic enforcement surface for repository governance rules.
- The quality gate contributes verification evidence; it does not redefine authority or grant execution permission.
- Human-governed review and approval remain the consequential approval boundary.
- Runtime outputs, reports, logs, and generated Markdown remain non-authoritative unless an explicit governed promotion process reclassifies them.
- LLM output may assist analysis, drafting, and review, but it does not become authority.
- Health, confidence, repository, or strategy scores must not mask active blockers.
- `LIVE_ORDER_BLOCKED` remains the fail-closed live eligibility state until every explicit gate passes.

## 31. Repository Health Score and Blocker Rules

A repository health score must not hide blockers.

Example:

```text
health_score: 97
critical_findings:
  - SECRET_EXPOSURE
status: CRITICAL
```

Severity model:

```yaml
severity:
  INFO:
    blocks_quality_gate: false
  WARNING:
    blocks_quality_gate: false
  REVIEW_REQUIRED:
    blocks_quality_gate: false
  BLOCKER:
    blocks_quality_gate: true
  CRITICAL:
    blocks_quality_gate: true
  SECURITY_CRITICAL:
    blocks_quality_gate: true
```

Finding contract:

```yaml
finding_id: RFG-NAMING-001
severity: BLOCKER
rule_id: repository_naming.lower_snake_case
artifact_path: docs/standards/standard_repository_file_governance.md
expected: docs/standards/standard_repository_file_governance.md
actual: docs/standards/standard_repository_file_governance.md
remediation: rename_and_update_canonical_path
quality_gate_effect: RUNNING_WITH_BLOCKERS
```

## 32. Minimum Acceptance Criteria

Minimum acceptance criteria:

1. All governed artifacts have canonical repository-relative paths.
2. Active repository root paths are resolved dynamically from runtime context.
3. Source code is separated from runtime state and generated artifacts.
4. Governed Markdown files follow the naming standard.
5. Active source-of-truth filenames do not use uppercase letters except
   reserved conventional filename exceptions.
6. Python packages and modules use `lower_snake_case`.
7. Reserved filename exceptions are explicit.
8. Secrets are not committed, logged, or embedded.
9. Hardcoded absolute paths are not present in production code.
10. Generated artifacts are not written into `src/`, `docs/`, or `tests/`.
11. Mutable, generated, reproducible, and execution/run-produced outputs are
    grouped under `runtime/`.
12. Runtime state is stored under `runtime/state/`.
13. Human-readable reports are stored under `runtime/reports/`.
14. Machine-readable artifacts are stored under `runtime/artifacts/`.
15. Rename/move/delete operations have migration records.
16. Case-collision risks are detected.
17. Repository validator output is preserved as evidence.
18. Trading-sensitive uncertainty fails closed.

## 33. Quality Gate Integration

The quality gate should execute repository governance checks before claiming completion.

Required checks may include:

```text
repository_validator
docs_hygiene_tests
artifact_hygiene_tests
schema_validation
link_check
secret_scan
case_collision_check
import_boundary_check
absolute_path_check
generated_artifact_location_check
```

Quality gate statuses:

```text
PASS
PASS_WITH_WARNINGS
RUNNING_WITH_BLOCKERS
FAILED
SECURITY_CRITICAL
NOT_VERIFIED
```

A missing validator run must be reported as:

```text
NOT_VERIFIED
```

A blocker must not be downgraded by aggregate health scores.

## 34. Final Governing Principle

The final governing principle is:

```text
Every repository artifact must have a clear identity, owner, purpose, location,
type, lifecycle, schema expectation, lineage, validation evidence, and audit trail.
```

Repository structure is not cosmetic. It is part of decision quality, security, reproducibility, auditability, and trading safety.

When repository evidence is missing:

```text
NOT_VERIFIED
```

When governance conflicts are unresolved:

```text
GOVERNANCE_CONFLICT
RUNNING_WITH_BLOCKERS
```

When trading execution may be affected:

```text
LIVE_ORDER_BLOCKED
```

When no safe repository change is authorized:

```text
NO_CHANGE
```

---
document_id: AI4B-GOV-CTRL-RFG-001
title: AI4BINANCE Repository Validation Rules
document_type: CONTROL
version: 1.0.9
status: ACTIVE
owner: Enterprise Engineering Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: repository_validation_rules
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/controls/control_repository_validation_rules.md
created_date: 2026-08-17
parent_standard: docs/standards/standard_repository_file_governance.md
schema_refs:
  - docs/schemas/reference_repository_artifact_schema.md
implemented_by:
  - src/ai4binance/governance/repository_validator.py
validated_by:
  - tests/test_repository_validator.py
  - tests/test_docs_hygiene.py
  - tests/test_artifact_hygiene_scripts.py
---

# AI4BINANCE Repository Validation Rules

## ELI10

This control turns repository file governance rules into deterministic checks and evidence reports. It reports issues but does not change files or approve execution.

## 1. Purpose

This control defines deterministic repository validation rules for AI4BINANCE. It converts the Repository File Governance Standard into machine-checkable controls and quality_gate findings.

The validator must report evidence. It must not silently fix, delete, move, rename, bypass or approve artifacts.
The validator treats `runtime/` as the canonical grouping root for mutable,
generated, reproducible, and execution/run-produced outputs. If deleting a file
would make the repository undefined, that file is not runtime output.

`doc_hygiene` governs canonical governed human-readable documentation under
`docs/**`, including authority metadata, canonical placement, semantic sync,
broken links, and duplicate or superseded documentation controls.
`artifact_hygiene` governs generated artifacts regardless of extension,
including generated Markdown, and owns lifecycle, provenance, retention,
cleanup, run isolation, and runtime storage rules. `doc_hygiene` may inspect
generated Markdown only to detect canonical misclassification or unauthorized
promotion claims.

## 2. Validation Scope

The repository validator covers:

- folder naming;
- file naming;
- governed Markdown naming;
- governed Markdown location and exception boundaries;
- canonical path metadata;
- repository artifact inventory fields;
- proposed governance layer classification;
- migration map records before move or rename;
- `docs/` structure;
- source/runtime/artifact/report separation;
- `runtime/` grouping root enforcement;
- external helper process isolation for quality-gate and `artifact_hygiene`
  support scripts;
- large-output capture paths that must remain file-backed and run-scoped rather
  than unbounded in-memory buffers;
- timeout-bound descendant process cleanup for PowerShell and Python helper
  commands that emit runtime artifacts or validator evidence;
- generated artifacts inside forbidden folders;
- hard-coded absolute paths;
- path traversal risks;
- case-only path collisions;
- secret exposure;
- import boundary violations;
- missing ownership metadata;
- broken internal references where practical;
- untracked or misplaced governed artifacts;
- Drive mirror exclusion boundaries.

## 3. Severity Model

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

Aggregate scores must not mask blockers.

## 4. Finding Contract

```yaml
finding:
  finding_id: RFG-NAMING-001
  severity: BLOCKER
  rule_id: repository_naming.lower_snake_case
  artifact_path: docs/standards/standard_repository_file_governance.md
  expected: docs/standards/standard_repository_file_governance.md
  actual: docs/standards/standard_repository_file_governance.md
  remediation: rename_and_update_canonical_path
  quality_gate_effect: RUNNING_WITH_BLOCKERS
```

Required fields:

```yaml
required_finding_fields:
  - finding_id
  - severity
  - rule_id
  - artifact_path
  - expected
  - actual
  - remediation
  - quality_gate_effect
```

Repository inventory records must include:

```yaml
required_inventory_fields:
  - file_id
  - path
  - mime_type
  - size
  - modified_time
  - owner
  - shared_status
  - artifact_type
  - artifact_class
  - authority_layer
  - observed_expected_layer
  - authority_basis
  - action
  - result
```

Root inventory records must use `artifact_class` to classify each root file as
`SOURCE`, `GOVERNANCE`, `RUNTIME`, `CACHE`, `REPORT`, or `ARCHIVE`. This root
classification is report-only evidence and does not authorize moving, deleting
or renaming files.

`authority_layer` must be derived from `authority_basis`. The basis must combine
governed metadata, registered policy, canonical path validation, validator
state, and downstream usage evidence. Folder placement is a filing signal, not
an independent source of authority. When explicit governed metadata is absent,
`authority_layer` remains `null` and the validator may emit only
`observed_expected_layer` plus a `validation:placement_hint_only` basis entry.

`observed_expected_layer` is a validator-computed filing expectation based on
canonical placement rules. It is diagnostic evidence only and must not be
treated as a source of authority.

Canonical `authority_layer` values:

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

`L0_EXTERNAL_MANDATORY_CONSTRAINTS` does not require repository-local source
files, but it must have registry-level representation before it is treated as
active authority. The representation must bind at least:

```yaml
external_constraint_record:
  - external_constraint_id
  - source_uri
  - jurisdiction_or_provider
  - effective_version
  - effective_date
  - retrieved_at
  - content_hash
  - validation_status
  - supersedes
  - authority_scope
  - affected_objects
```

Migration map records must be generated before any governed move or rename:

```yaml
required_migration_map_fields:
  - source_path
  - target_path
  - reason
  - authority_level
  - status
  - requires_link_update
  - requires_reference_update
  - risk
```

## 5. Policy-as-Code Baseline

```yaml
repository_validation_policy:
  folder_names:
    style: lower_snake_case
    spaces: forbidden
    uppercase: forbidden
    turkish_characters: forbidden
    hyphens: forbidden_for_python_packages
  file_names:
    default_style: lower_snake_case
    ambiguous_names: forbidden
    version_suffix_in_source_filename: forbidden
    lifecycle_state_in_source_filename: forbidden
  governed_markdown:
    pattern: "<document_type>_<domain>_<subject>.md"
    canonical_path_required: true
    front_matter_required: true
    canonical_location: docs/**
    approved_docs_index_exceptions:
      - docs/README.md
    approved_root_exceptions:
      - README.md
      - AGENTS.md
      - CLAUDE.md
      - GEMINI.md
    approved_scoped_instruction_pattern:
      - "**/AGENTS.md"
    governed_operational_exception_paths:
      - factory/brief.md
      - factory/guide.md
      - factory/handoff.md
      - factory/plan.md
      - factory/review.md
    noncanonical_operational_state_paths:
      - factory/log.md
      - factory/progress.md
      - factory/state.md
    runtime_markdown_class: GENERATED_RUNTIME_MD
    runtime_markdown_canonical_authority_allowed: false
    noncanonical_operational_state_canonical_authority_allowed: false
  source_of_truth_files:
    filename_case: lower_snake_case
    uppercase_filename_allowed: false
    reserved_conventional_exceptions:
      - AGENTS.md
      - README.md
  governed_document_locks:
    manifest: config/governance/governed_document_lock_manifest.json
    locked_when:
      - status: ACTIVE
      - source_of_truth: true
      - machine_enforceable: true
      - content_role: POLICY_AS_CODE
    lock_state: LOCKED
    approval_policy: WRITTEN_OWNER_APPROVAL_REQUIRED
    manifest_lock_policy_required: true
    missing_manifest_effect: RUNNING_WITH_BLOCKERS
    hash_mismatch_without_approval_effect: RUNNING_WITH_BLOCKERS
  hardcoded_absolute_paths:
    allowed: false
  active_repository_root:
    resolution: runtime_dynamic
    allowed_sources:
      - current_workspace
      - cli_repository_root_argument
      - vscode_workspaceFolder
    hardcoded_machine_path_allowed: false
  generated_artifacts_inside_src:
    allowed: false
  runtime_state_inside_src:
    allowed: false
  secrets_in_repository:
    allowed: false
  secrets_in_logs:
    allowed: false
  case_only_path_collisions:
    allowed: false
  path_traversal_tokens:
    allowed: false
  owner_required: true
  artifact_type_required: true
  migration_map_before_move:
    required: true
  broken_link_or_path_after_change:
    allowed: false
```

## 6. Rule RFG-NAMING-001: Folder Naming

Folders must use `lower_snake_case` unless explicitly reserved.

Invalid examples:

```text
docs/
scripts/
MarketRegime/
market-regime/
market regime/
```

Expected examples:

```text
docs/
scripts/
market_regime/
support_resistance/
```

Severity:

```yaml
severity: BLOCKER
```

## 7. Rule RFG-NAMING-002: Source Filename Naming

Source files must use responsibility-specific `lower_snake_case`.

Forbidden/discouraged names:

```text
utils.py
helpers.py
common.py
misc.py
functions.py
manager.py
data.py
temp.py
new.py
test2.py
final.py
final_v2.py
```

Severity:

```yaml
severity: REVIEW_REQUIRED
```

If the file name masks trading, risk, execution or security behavior, severity becomes `BLOCKER`.

## 8. Rule RFG-DOCS-001: Governed Markdown Naming

Governed Markdown files under `docs/` must follow:

```text
<document_type>_<domain>_<subject>.md
```

Reserved exception:

```text
docs/registries/registry_documentation_index.md
```

Bounded taxonomy compatibility:

- `docs/reports/**` may use `report_` and `evidence_` filename families while
  preserving `document_type: EVIDENCE_REQUIREMENT`;
- this compatibility is limited to generated findings, audit outputs,
  inventories, readiness records, split manifests, and migration manifests;
- the validator must treat this as a documented taxonomy rule, not as a silent
  naming waiver for unrelated document families.

Severity:

```yaml
severity: BLOCKER
```

## 8.1 Rule DOC-GOV-001: Canonical Governed Markdown Location

Canonical governed Markdown documentation must reside under `docs/` unless the
path is an approved docs-index exception, repository root exception, or a
scope-local `AGENTS.md` instruction file whose location is required for
discovery or scope semantics.

Approved docs-index exceptions:

```text
docs/README.md
```

Approved root exceptions:

```text
README.md
AGENTS.md
CLAUDE.md
GEMINI.md
```

Severity:

```yaml
severity: BLOCKER
```

## 8.2 Rule DOC-GOV-002: Runtime Markdown Canonical Authority Prohibition

Generated Markdown under `runtime/` must not declare itself canonical or
source-of-truth. Runtime Markdown must not use:

```text
source_of_truth: true
source_of_truth_scope: canonical|family_index|provider_adapter
authority_level: REPOSITORY|NORMATIVE|ENFORCEABLE|PROVIDER_ADAPTER|EXTERNAL_AUTHORITY
authority_layer: L0..L10 canonical layer values
authority_effect: MANDATORY_CONSTRAINT|NORMATIVE_CONSTRAINT|OPERATIONAL_SPECIALIZATION|IMPLEMENTATION|EVIDENCE_ONLY|REFERENCE_ONLY|ARCHIVE_ONLY
authority_scope: lower_snake_case semantic scope
content_role: AUTHORITATIVE|POLICY_AS_CODE
```

A runtime Markdown artifact may become governed documentation only through an
explicit review, classification, and promotion process outside the runtime
namespace.

Severity:

```yaml
severity: BLOCKER
```

## 8.3 Rule DOC-GOV-003: Approved Root Exceptions

`README.md`, `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` are approved repository
entrypoint or provider-adapter Markdown exceptions. Their root location is part
of discovery semantics and must not be treated as a documentation placement
violation by itself.

Severity:

```yaml
severity: INFO
```

## 8.4 Rule DOC-GOV-004: Provider Adapter Alignment

Provider adapter Markdown must not contradict, weaken, or silently redefine the
canonical governance documented under `docs/`.

The repository validator must resolve governed concept ownership by
`authority_scope`. If an active lower-authority governed object reuses an
active higher-authority `authority_scope`, the state is a semantic override
attempt, not a harmless metadata coincidence. The validator must emit
`KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT`, `RUNNING_WITH_BLOCKERS`, and preserve
`LIVE_ORDER_BLOCKED`. Operational specialization is allowed only when the lower
layer moves to a narrower derived `authority_scope` and matching derived
`source_of_truth_scope`; reusing the higher-authority owner scope is forbidden.

Severity:

```yaml
severity: BLOCKER
```

## 8.5 Rule DOC-GOV-005: Runtime Promotion Requirement

A runtime Markdown file cannot become authoritative without an explicit
governed promotion process that reclassifies the artifact outside the runtime
namespace.

Severity:

```yaml
severity: BLOCKER
```

## 8.6 Rule DOC-GOV-006: Governed Operational Exception Allowlist

The following Markdown files are approved governed operational exceptions
outside `docs/`:

```text
factory/brief.md
factory/guide.md
factory/handoff.md
factory/plan.md
factory/review.md
```

They remain governed workflow surfaces, not a general license for new canonical
Markdown outside `docs/`. Additional exception paths require explicit
governance approval and validator coverage.

Severity:

```yaml
severity: BLOCKER
```

## 8.7 Rule DOC-GOV-007: Non-Canonical Operational State Markdown

The following Markdown files are approved non-canonical operational state
surfaces outside `runtime/`:

```text
factory/log.md
factory/progress.md
factory/state.md
```

These files may support workflow continuity, but they must not declare
canonical authority, `source_of_truth: true`, authoritative content roles, or
canonical source-of-truth scope metadata.

Severity:

```yaml
severity: BLOCKER
```

## 9. Rule RFG-DOCS-002: Source-of-Truth Filename Case

Governed Markdown files with `source_of_truth: true` must use
repository-relative lower-case filenames. Uppercase letters in source-of-truth
filenames are forbidden unless the file is an explicitly reserved conventional
filename such as `AGENTS.md` or `README.md`.

Invalid:

```text
docs/governance/Policy_Main_Source.md
docs/standards/StandardRepositoryRules.md
```

Expected:

```text
docs/governance/policy_main_source.md
docs/standards/standard_repository_rules.md
```

Severity:

```yaml
severity: BLOCKER
```

## 10. Rule RFG-PATH-001: Canonical Path Metadata

Governed documents must include a current `canonical_path` in front matter.

Invalid:

```yaml
canonical_path: docs/standards/standard_repository_file_governance.md
```

Expected:

```yaml
canonical_path: docs/standards/standard_repository_file_governance.md
```

Severity:

```yaml
severity: BLOCKER
```

## 11. Rule RFG-PATH-002: Absolute Path Prohibition

Production code and governed repository documents must not embed machine-specific absolute paths as operational dependencies.

Repository file paths are dynamic. Tools, VS Code tasks, scripts, validators and
agent workflows must resolve the active repository root at runtime from the
current workspace, explicit CLI `--repository-root` argument, or
`${workspaceFolder}`. A local checkout path such as `C:\...\ai4binance` is
runtime context, not canonical repository identity, and must not be hard-coded
into production code.

Blocked examples:

```text
C:\vscode-projects\ai4binance\data
H:\BackUP\Downloads
```

Expected:

```text
${workspaceFolder}/data
.\data
Path.cwd() / "data"
repository_root / "data"
```

External source attachment references may appear only as provenance fields and must not become canonical paths.

Severity:

```yaml
severity: BLOCKER
```

## 12. Rule RFG-PATH-003: Path Traversal Security

Blocked tokens:

```text
../
..\
/
\
:
*
?
"
<
>
|
```

These tokens must not be accepted from external/user-provided path segments without normalization and validation.

Severity:

```yaml
severity: SECURITY_CRITICAL
```

## 13. Rule RFG-STRUCT-001: Source Runtime Separation

Generated artifacts, runtime state, reports and logs must not be written under `src/`.

Invalid:

```text
src/ai4binance/trading/reports/
src/ai4binance/runtime_state.json
```

Expected:

```text
runtime/reports/trading/
runtime/state/paper/current_positions.json
runtime/artifacts/decisions/paper/
```

Severity:

```yaml
severity: BLOCKER
```

## 13. Rule RFG-DATA-001: Data Lifecycle Structure

Runtime data folders must follow:

```text
runtime/data/raw/
runtime/data/staged/
runtime/data/normalized/
runtime/data/curated/
runtime/data/feature_store/
runtime/data/reference/
runtime/data/cache/
```

Agents must not maintain duplicate local OHLCV copies. A shared validated market snapshot should be used for a decision cycle.

Severity:

```yaml
severity: REVIEW_REQUIRED
```

If duplicate data affects trading decisions, severity becomes `BLOCKER`.

## 14. Rule RFG-CASE-001: Case Collision

The repository must not contain paths that differ only by case.

Examples:

```text
docs/
docs/
scripts/
scripts/
```

Severity:

```yaml
severity: BLOCKER
```

## 15. Rule RFG-SECRETS-001: Secret Exposure

Secrets must not be committed, logged or embedded in repository files.

Blocked values include:

```text
API keys
private keys
wallet private keys
raw credentials
live-order bypass tokens
session tokens
unredacted secrets
```

Severity:

```yaml
severity: SECURITY_CRITICAL
quality_gate_effect: LIVE_ORDER_BLOCKED
```

## 16. Rule RFG-DRIVE-001: Drive Mirror Boundary

Google Drive mirror paths are review and assistant-context mirrors only. Presence in Drive does not imply governance status.

Excluded artifacts:

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

Severity:

```yaml
severity: REVIEW_REQUIRED
```

If a mirror-only path is used as canonical path, severity becomes `BLOCKER`.

## 17. Rule RFG-IMPORT-001: Import Boundary

```yaml
import_boundary_rules:
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

Severity:

```yaml
severity: BLOCKER
```

If import boundary violation bypasses decision, risk or execution controls, severity becomes `CRITICAL` and `LIVE_ORDER_BLOCKED`.

## 18. Rule RFG-COMPLEXITY-001: Complexity Review

```yaml
complexity_events:
  FILE_REVIEW_REQUIRED:
    trigger: lines > 500
    blocks_quality_gate: false
  REFACTOR_CANDIDATE:
    trigger: lines > 700
    blocks_quality_gate: false
  COMPLEXITY_BLOCKER:
    trigger: cyclomatic_complexity >= 15
    blocks_quality_gate: true
```

Severity depends on triggered event.

## 19. Rule RFG-MIGRATION-001: Rename/Move Impact Analysis

Rename, move and delete operations require migration records.

Required checks:

```yaml
required_checks:
  - link_check
  - canonical_path_check
  - repository_validator
  - docs_hygiene_tests
  - artifact_hygiene_tests
  - governance_constitution_sync_tests
```

Severity:

```yaml
severity: BLOCKER
```

## 19.1 Rule RFG-LOCK-001: Governed Document Lock

Active governed Markdown documents that are `source_of_truth: true`,
`machine_enforceable: true`, or `content_role: POLICY_AS_CODE` must be locked in
`config/governance/governed_document_lock_manifest.json`.

Required lock fields:

```yaml
required_lock_fields:
  - path
  - canonical_path
  - authority_level
  - document_status
  - version
  - expected_hash
  - sha256
  - source_of_truth
  - supersedes
  - allowed_change_process
  - lock_state
  - approval_policy
```

Required values:

```yaml
lock_state: LOCKED
approval_policy: WRITTEN_OWNER_APPROVAL_REQUIRED
allowed_change_process: WRITTEN_OWNER_APPROVAL_REQUIRED
written_owner_approval_required: true
manifest_lock_policy:
  lock_state: LOCKED
  approval_policy: WRITTEN_OWNER_APPROVAL_REQUIRED
  written_owner_approval_required: true
  filesystem_lock_required: true
```

The validator must compare each manifest registration record with the governed
Markdown frontmatter before accepting the hash baseline:

```yaml
registration_integrity:
  canonical_path: must match governed Markdown canonical_path
  authority_level: must match governed Markdown authority_level
  authority_layer: must match governed Markdown authority_layer when declared
  authority_effect: must match governed Markdown authority_effect when declared
  authority_scope: must match governed Markdown authority_scope when declared
  document_status: must match governed Markdown status
  version: must match governed Markdown version
  expected_hash: must equal sha256
  source_of_truth: must match governed Markdown source_of_truth
  supersedes: must match governed Markdown supersedes/supersedes_document_ids
  allowed_change_process: WRITTEN_OWNER_APPROVAL_REQUIRED
```

Source-of-truth documents under `docs/workflows/`, `docs/procedures/`, and
`docs/runbooks/` must declare explicit `authority_layer`,
`authority_effect`, and `authority_scope` frontmatter. Their
`source_of_truth_scope` must be derived from `authority_scope` as
`<authority_scope>_workflow`, `<authority_scope>_procedure`, or
`<authority_scope>_runbook` according to the canonical directory family. Their
governed document lock registrations must carry the same explicit authority
fields.

These operational documents may specialize higher-authority governance only
through a narrower concept owner surface. They must not reuse an active
higher-authority `authority_scope`, because same-scope reuse is treated as a
semantic weaken/contradict/override attempt instead of operational
specialization.

If a locked document's current SHA-256 differs from the manifest baseline, the
validator may treat the state as compliant only when a matching approved written
owner approval record names that document and current SHA-256.

Severity:

```yaml
severity: BLOCKER
quality_gate_effect: RUNNING_WITH_BLOCKERS
finding_kind: GOVERNED_DOCUMENT_LOCK_VIOLATION
```

## 20. Quality Gate Effects

```yaml
quality_gate_effects:
  no_blockers:
    status: PASS
  blocker_present:
    status: RUNNING_WITH_BLOCKERS
  security_critical_present:
    status:
      - SECURITY_CRITICAL
      - LIVE_ORDER_BLOCKED
  governance_conflict_present:
    status:
      - GOVERNANCE_CONFLICT
      - RUNNING_WITH_BLOCKERS
  governed_document_lock_violation:
    status:
      - GOVERNED_DOCUMENT_LOCK_VIOLATION
      - RUNNING_WITH_BLOCKERS
  unverified_repository_state:
    status:
      - NOT_VERIFIED
      - NO_CHANGE
```

## 21. Validator Output Contract

```yaml
repository_validation_report:
  report_id: RFG-VAL-20260817T184900Z
  generated_at_utc: 2026-08-17T18:49:00Z
  repository_root: C:\vscode-projects\ai4binance
  status: RUNNING_WITH_BLOCKERS
  total_findings: 0
  blocker_count: 0
  security_critical_count: 0
  findings: []
  evidence_artifacts: []
  tests_executed: []
  not_verified:
    - tests_not_executed_unless_actual_test_run_evidence_exists
```

## 22. LLM Boundary

LLMs may draft findings, propose migration plans and summarize risks. They must not execute destructive operations, bypass validators or approve their own changes.

```yaml
llm_repository_authority:
  draft_findings: true
  draft_migration_plan: true
  propose_rename: true
  propose_refactor: true
  execute_delete: false
  execute_move_without_approval: false
  execute_rename_without_approval: false
  bypass_validator: false
  approve_own_changes: false
```

## 23. Acceptance Criteria

A validation run passes only if:

- no blocker findings exist;
- no security critical findings exist;
- no governed document has stale `canonical_path`;
- no case-only collision exists;
- no secret exposure is detected;
- source/runtime/artifact/report separation is preserved;
- runtime grouping root is preserved;
- Drive mirror artifacts are not treated as canonical source;
- migration records exist for rename/move/delete changes;
- tests are only claimed when actually executed.



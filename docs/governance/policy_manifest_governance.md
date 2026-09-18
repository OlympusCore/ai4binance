---
document_id: AI4B-GOV-POL-MANIFEST-001
title: AI4BINANCE Manifest Governance Policy
document_type: POLICY
version: 1.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: manifest_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/governance/policy_manifest_governance.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
parent_controls:
  - docs/controls/control_repository_validation_rules.md
implements:
  - governed_manifest_registration
  - governed_document_integrity
  - governed_document_locking
  - manifest_lock_policy
implemented_by:
  - src/ai4binance/governance/repository_validator.py
validated_by:
  - tests/test_repository_validator.py
---

# AI4BINANCE Manifest Governance Policy

## ELI10

This policy defines how AI4BINANCE uses governance manifests to register,
protect, validate, and audit governed repository artifacts. A read-only file is
not compliant by itself; the manifest, metadata, hash, lock state, and approval
evidence must agree.

## 1. Purpose

This policy establishes mandatory requirements for manifests that identify,
classify, protect, version, supersede, validate, and audit governed AI4BINANCE
repository artifacts.

Filesystem protection alone must not constitute governance compliance. A
governed artifact is compliant only when its repository state, manifest
registration, authority classification, lifecycle state, integrity evidence, and
change-control evidence are mutually consistent.

The required control chain is:

```text
Governed Artifact
      -> Governance Registry / Manifest
      -> canonical_path / authority_level / document_status / version
      -> expected_hash / source_of_truth / supersedes / allowed_change_process
      -> filesystem protection
      -> hash and integrity verification
      -> PASS
```

## 2. Scope

This policy applies to governed repository artifacts, including:

- constitutions;
- governance policies;
- standards;
- controls;
- canonical contracts;
- schemas;
- ontologies;
- taxonomies;
- registries;
- architecture specifications;
- decision and risk rules;
- validation and execution policies;
- compliance artifacts;
- security policies;
- provider instructions;
- agent instructions;
- prompt governance artifacts;
- workflow definitions;
- critical repository metadata.

The policy may govern source code, tests, configuration, generated schemas, and
other artifacts only when they are explicitly registered as governed.

## 3. Authority

Manifest declarations must respect the AI4BINANCE authority hierarchy:

```text
External Mandatory Constraints
        -> Core Constitution
        -> Governance / Compliance
        -> Canonical Contracts
        -> Repository Instructions
        -> Provider Adapters
        -> Scoped Instructions / Skills
        -> Code / Configuration
        -> Tests / Evidence / Runtime
```

A lower-authority artifact must not override, weaken, silently reinterpret,
duplicate with different semantics, or bypass a higher-authority rule.

When authority cannot be deterministically resolved, repository validation must
report:

```text
GOVERNANCE_CONFLICT
RUNNING_WITH_BLOCKERS
```

If the conflict can affect trading execution, risk limits, validation, or live
eligibility, `LIVE_ORDER_BLOCKED` also applies.

## 4. Manifest as Governance Registry

A governance manifest is a machine-readable registry. It must not be only a list
of protected files.

Each governed artifact registration must identify:

- what the artifact is;
- where the canonical artifact is located;
- why it is governed;
- who owns it;
- what authority it has;
- which version is authoritative;
- whether it is active;
- what it supersedes;
- how integrity is verified;
- how it may be changed;
- which validation rules apply.

Each governed artifact must have no more than one active canonical registration
for the same governance identity and version.

## 5. Required Manifest Fields

Each governed artifact lock entry must include:

```text
path
canonical_path
authority_level
document_status
version
expected_hash
sha256
source_of_truth
supersedes
allowed_change_process
lock_state
approval_policy
```

For governed document locks, `expected_hash` and `sha256` must match the current
SHA-256 of the registered artifact unless a valid written owner approval record
authorizes a bounded in-flight change.

## 6. Canonical Path Policy

Every governed artifact must declare exactly one `canonical_path`.

The canonical path must:

- be repository-relative;
- use normalized forward-slash notation;
- resolve to exactly one expected artifact;
- not depend on workstation-specific absolute paths;
- not redirect silently to a duplicate artifact;
- match the artifact frontmatter when frontmatter declares `canonical_path`.

The following must not be canonical manifest paths:

```text
C:\Users\...
C:\vscode-projects\...
/home/user/...
../external-copy/...
Google Drive mirror path
temporary runtime path
```

Environment-specific repository roots may differ, but the canonical
repository-relative identity must remain stable.

## 7. Source-of-Truth Policy

`source_of_truth: true` may be used only when the artifact is authoritative for
the governed subject.

Duplicate active source-of-truth artifacts for the same governed concept are
governance defects. A duplicate active source-of-truth condition must remain
visible until resolved through registry, manifest, and validation evidence.

Provider adapters, generated artifacts, report outputs, runtime logs, backup
copies, and mirrors must not become independent active sources of truth.

## 8. Lifecycle and Supersession

Manifest lifecycle state must match governed artifact metadata. For Markdown
governed knowledge, `document_status` in the manifest must match frontmatter
`status`.

Supersession must be explicit. A superseding artifact must identify prior
document identifiers through `supersedes` or equivalent governed metadata, and
the manifest must retain enough information to validate the relationship.

An obsolete artifact must not remain registered as an active source of truth for
the same governed concept.

## 9. Integrity Control

The manifest must store SHA-256 integrity evidence for governed artifacts when
integrity verification is required.

Repository validation must compare the registered hash to the current artifact
hash. A mismatch without valid approval evidence must produce:

```text
GOVERNED_DOCUMENT_LOCK_VIOLATION
RUNNING_WITH_BLOCKERS
```

Hash verification must occur after manifest registration metadata is checked.
Hash acceptance must not hide registration drift, authority drift, lifecycle
drift, or source-of-truth drift.

## 10. Filesystem Protection

Active governed Markdown documents that declare any of the following metadata
must remain locked by default:

```text
source_of_truth: true
machine_enforceable: true
content_role: POLICY_AS_CODE
```

Where the host filesystem supports it, protected governed Markdown must use both
read-only attributes and filesystem ACL write-protection.

Filesystem protection does not replace manifest registration, hash verification,
approval evidence, or deterministic validation.

## 11. Manifest Lock Policy

A manifest that protects governed documents is itself a protected governance
manifest. It must declare a `manifest_lock_policy` requiring:

```text
lock_state: LOCKED
approval_policy: WRITTEN_OWNER_APPROVAL_REQUIRED
written_owner_approval_required: true
filesystem_lock_required: true
```

Weakening, removing, bypassing, or failing to validate the manifest lock policy
must be treated as a governed document lock violation.

## 12. Change Control

Protected governed artifacts may be changed only through:

```text
WRITTEN_OWNER_APPROVAL_REQUIRED
```

After approval:

1. unlock only the affected artifact or artifacts;
2. make only the approved bounded correction;
3. update required registry and manifest entries;
4. refresh SHA-256 baselines;
5. run deterministic validation;
6. immediately restore filesystem locks.

Unlocked governed documents must not be left writable after an approved change.

## 13. Validation and Enforcement

Repository validation must fail closed when any required manifest state,
frontmatter metadata, filesystem lock, integrity hash, approval record, or
authority relationship cannot be verified.

The validation result must preserve explicit blocker states instead of converting
them into warnings or aggregate scores.

## 14. Anti-Hallucination Evidence and Coverage Ratio Policy

Governance manifests, manifest-backed Markdown, and evidence payloads must not
convert assumed, estimated, stale, partial, or unexecuted evidence into a
verified completion claim.

When a manifest or manifest-backed evidence record declares
`anti_hallucination`, the declaration must require:

- explicit source references for factual claims;
- deterministic provenance for generated or summarized evidence;
- `NOT_VERIFIED` when source evidence is unavailable;
- `PARTIALLY_VERIFIED` when only a bounded subset was checked;
- `RUNNING_WITH_BLOCKERS` when missing evidence affects governance, quality,
  validation, risk, execution, or live eligibility;
- no inferred PASS, COMPLETE, READY, or GREEN state without matching validation
  evidence.

When a manifest or manifest-backed evidence record declares `coverage_ratio`,
the value must be clean, realistic, and evidence-derived:

- represent a numeric ratio in the closed interval `[0.0, 1.0]`;
- be calculated from the same executed evidence source as any corresponding
  `coverage_percent`;
- equal `coverage_percent / 100` when both fields are present, subject only to
  explicit decimal precision rules;
- identify `coverage_source`, command, timestamp, and evidence artifact path;
- never be guessed, rounded upward, copied from stale output, inferred from a
  focused `--no-cov` test run, or treated as equivalent to full quality-gate
  evidence;
- fail closed as `NOT_VERIFIED` or `RUNNING_WITH_BLOCKERS` when the supporting
  evidence cannot be read or reproduced.

Coverage claims for repository completion must remain tied to full quality-gate
evidence. A manifest-backed completion claim must not be considered green unless
the current quality evidence carries `TECHNICAL_QUALITY_PASS`,
`pytest_pass_count`, `coverage_percent`, and `coverage_source` from an actually
executed gate, and the same evidence envelope closes as
`full_assurance_status=FULL_ASSURANCE_GREEN`.

For consequential changes, `approval_verification` is a hard veto. An approval
record that does not match the active `scope_hash`, `evidence_hash`,
`DQG_result`, `DGG_result`, `lifecycle_definition_sha256`, or
`authority_family_sha256` is not eligible to green-light completion. A record
with `revoked_at_utc` set is also invalid. The loader may fall back only to the
canonical `runtime/artifacts/quality/gate/approval_record_latest.json`
artifact, never to lower-authority defaults. In that state the manifest claim
must remain `RUNNING_WITH_BLOCKERS`, `consequential_change_allowed=false`, and
`LIVE_ORDER_BLOCKED`.

`coverage_ratio` and `coverage_percent` are quality-evidence indicators only.
They do not prove strategy validity, OOS robustness, operational readiness,
security posture, compliance certification, live eligibility, or execution
authority.

## 15. Trading Safety Boundary

Manifest compliance does not authorize live trading, production deployment,
financial execution, risk-limit increases, or strategy promotion.

Governance manifest compliance is necessary evidence for repository integrity,
but trading eligibility still requires the separate risk, validation, execution,
and human-governed promotion controls.

## 16. Final Principle

A governed artifact is not compliant because it exists, is listed, or is
read-only. It is compliant only when registration, authority, lifecycle state,
integrity evidence, change control, validation, and filesystem protection agree.

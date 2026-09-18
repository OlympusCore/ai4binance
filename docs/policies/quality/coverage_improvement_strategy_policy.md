---
document_id: AI4B-QUALITY-POL-001
title: AI4BINANCE Coverage Improvement Strategy Policy
document_type: POLICY
version: 1.1.0
status: ACTIVE
owner: Quality Governance
authority_level: NORMATIVE
authority_layer: L4_REPOSITORY_STANDARDS_CONTROLS_QUALITY_POLICIES
authority_scope: coverage_improvement_strategy_policy
content_role: POLICY_AS_CODE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/policies/quality/coverage_improvement_strategy_policy.md
manifest_refs:
  - config/governance/governed_document_lock_manifest.json
implemented_by:
  - config/quality/coverage-targets.json
  - src/ai4binance/ops/coverage_architecture.py
  - src/ai4binance/ops/coverage_audit.py
  - src/ai4binance/ops/coverage_policy.py
  - scripts/coverage_audit.ps1
  - scripts/quality.ps1
validated_by:
  - tests/test_coverage_architecture.py
  - tests/test_coverage_audit.py
  - tests/test_coverage_policy.py
  - tests/test_artifact_hygiene_scripts.py
---

# AI4BINANCE Coverage Improvement Strategy Policy

## ELI10

This policy explains how AI4BINANCE should improve tests without pretending that
a higher percentage makes trading safer by itself. The executable rules live in
the quality configuration and the quality gate.

## Purpose

AI4BINANCE uses governed coverage targets to make weak test areas visible,
ordered, and auditable. Coverage is a quality signal only. It never authorizes
live orders, risk-limit changes, strategy promotion, or execution authority.

The executable coverage target configuration is:

```text
config/quality/coverage-targets.json
```

The executable evaluator is:

```text
src/ai4binance/ops/coverage_policy.py
```

Architecture assurance is derived by the evidence-only evaluator:

```text
src/ai4binance/ops/coverage_architecture.py
```

It resolves canonical logical component and relation identifiers into source,
test-assertion, statement/branch, and typed runtime-evidence states. Missing,
stale, unverified, or unknown proof remains a non-passing state and cannot grant
execution, risk, validation, governance, or strategy-promotion authority.

The quality gate invokes the evaluator after the current `coverage.py` JSON
artifact is generated.

The focused manual remediation audit is:

```text
scripts/coverage_audit.ps1
```

It lists files below the selected coverage threshold and converts raw uncovered
line and branch evidence into coverage, risk, and remediation views.

## Governed Families

The governed family set is:

- `adapter`
- `id`
- `ontology`
- `policy`
- `opportunity`
- `position`
- `handoff`
- `repository_validator`

Actual source membership is configuration-driven and must use repository-relative
paths. Placeholder paths are not valid evidence.

## Threshold Model

The governed minimum target is `95.00%`.

The governed branch minimum target is `95.00%`.

The repository-wide minimum total coverage target is `93.00%`.

The remediation trigger is `93.00%`.

Files below `93.00%` in manual coverage audits must be raised to at least
`95.00%` with meaningful behavioral tests.

High-authority governance, decision governance, risk, execution, validation,
and portfolio-accounting surfaces may declare higher target coverage in:

```text
config/quality/coverage-targets.json
```

For these surfaces, the audit target shown to the developer must use the higher
declared target rather than the default `95.00%`.

Current migration behavior is `baseline_migration`: the quality gate records
coverage debt in machine-readable evidence without silently converting existing
baseline debt into a new gate failure. When the governed family baseline reaches
the required level, enforcement can be promoted to `enforced` through the same
governed change process used for quality-gate behavior.

## Ordering Rule

The coverage view must be ranked from weakest to strongest:

```text
statement coverage ascending
missing branches descending
missing lines descending
target name ascending
```

The risk view must be ranked by:

```text
priority score descending
criticality score descending
target name ascending
```

The remediation view must be ranked by:

```text
remediation efficiency descending
remediation value descending
target name ascending
```

The weakest coverage target is not automatically the first remediation
candidate. Governance, decision governance, risk, validation, execution,
economic impact, branch pressure, and blast radius can raise a file above a
lower-coverage support file.

## Manual Audit Output Contract

The manual coverage audit must preserve these views:

- `coverage_view`
- `risk_view`
- `remediation_view`

Each file row should include:

- coverage, risk, and remediation ranks;
- priority and tier;
- statement and branch coverage;
- target coverage and coverage gap to target;
- missing line, branch, and total counts;
- branch pressure;
- complexity;
- criticality score;
- authority class;
- economic impact;
- execution impact;
- blast radius;
- test gap types;
- recommended test types;
- estimated effort;
- priority score;
- remediation value;
- remediation efficiency;
- manual instruction.

The manual script must support filtering or ordering by:

```text
-SortBy Coverage
-SortBy Risk
-SortBy BranchPressure
-SortBy Remediation
-Priority P0
-Tier T0
-Authority GOVERNANCE
-TargetOnly
```

## AI4BINANCE Gap Categories

The audit may classify uncovered behavior with AI4BINANCE-specific categories,
including:

- `HARD_BLOCKER_PATH`
- `RISK_VETO_PATH`
- `VALIDATION_VETO_PATH`
- `GOVERNANCE_CONFLICT_PATH`
- `LIVE_ORDER_BLOCK_PATH`
- `STALE_DATA_PATH`
- `INSUFFICIENT_EVIDENCE_PATH`
- `SERIALIZATION_PATH`
- `REPLAY_PATH`
- `RECOVERY_PATH`
- `COUNTERFACTUAL_PATH`

## Test Quality Rule

Coverage improvement must use meaningful behavioral tests. The following
patterns are not acceptable as coverage remediation:

- import-only tests;
- assertion-free tests;
- `assert True` tests;
- mocking the unit under test itself;
- branch execution without outcome assertions;
- blanket coverage exclusions without governed justification.

Tests should cover relevant happy paths, boundary cases, invalid inputs, missing
inputs, stale inputs, fail-closed blockers, idempotency, serialization,
deserialization, and contract violations.

## Evidence

The quality gate must preserve:

- total coverage evidence;
- governed family results;
- policy failures;
- not-measured targets;
- coverage scope conflicts;
- promotion status;
- live eligibility status.

Coverage evidence must remain machine-readable and must not be inferred from
cached terminal output.

## Safety Boundary

Coverage cannot override:

- `GOVERNANCE_CONFLICT`
- `SECURITY_FAILURE`
- `VALIDATION_FAILURE`
- `RISK_VETO`
- `LIVE_EXECUTION_DISABLED`
- `LIVE_ORDER_BLOCKED`

The default remains:

```text
PAPER_TRADING
MANUAL_CONFIRMATION
LIVE_EXECUTION_DISABLED
RESEARCH_ONLY
LIVE_ORDER_BLOCKED
```

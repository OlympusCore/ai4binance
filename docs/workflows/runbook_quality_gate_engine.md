---
document_id: AI4B-QA-RUN-003
title: AI4BINANCE Quality Gate Engine Helper Workflow
document_type: RUNBOOK
version: 1.0.0
status: ACTIVE
owner: Enterprise Quality Governance
authority_level: REFERENCE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: quality_gate_engine_helper_workflow
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: EXPLANATORY
source_of_truth: false
source_of_truth_scope: quality_gate_profile_workflow
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/runbook_quality_gate_engine.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
policy_refs:
  - config/quality/gates.yaml
implementation_refs:
  - src/ai4binance/ops/quality_gate/__init__.py
  - src/ai4binance/ops/quality_gate/__main__.py
  - src/ai4binance/ops/quality_gate/cli.py
  - src/ai4binance/ops/quality_gate/policy.py
  - src/ai4binance/ops/quality_gate/telemetry.py
  - scripts/quality.ps1
validated_by:
  - tests/test_quality_gate_profiles.py
  - tests/test_artifact_hygiene_scripts.py
---

# AI4BINANCE Quality Gate Engine Helper Workflow

## ELI10

This helper keeps quality gate test selection small, explicit, and safe. It
helps the Windows wrapper decide which tests to run for `FAST` and `STANDARD`
profiles without pretending that a short run is the same as the full quality
gate.

## Purpose

This supporting workflow documents the Python helper surface used by the
Windows quality gate wrapper. The canonical quality profile decision remains in
`docs/workflows/runbook_quality_gate_profiles.md`; the machine-readable profile
policy remains `config/quality/gates.yaml`.

## Helper Boundary

The `src/ai4binance/ops/quality_gate/` package is an internal quality helper. It
does not grant execution, deployment, trading, promotion, risk-limit, or
approval authority.

The helper may:

- load the configured quality gate profile policy,
- resolve `FAST` affected pytest arguments,
- resolve `STANDARD` required pytest arguments,
- return fail-closed escalation evidence for unknown affected scope,
- build compact timing and console evidence summaries.

The helper must not:

- mark `FAST` or `STANDARD` as `FULL_VERIFIED`,
- treat `dmypy` as canonical type authority,
- skip unknown affected-test scope,
- suppress subprocess failures,
- write outside `runtime/` evidence paths,
- weaken Ruff, MyPy, Pytest, governance, privacy, financial leak, or
  deterministic gate requirements.

## Implementation Responsibilities

`src/ai4binance/ops/quality_gate/policy.py` owns policy loading, profile
validation, changed-path discovery, affected-test selection, and required-test
selection.

`src/ai4binance/ops/quality_gate/cli.py` owns the shell-safe
`python -m ai4binance.ops.quality_gate select-tests` command used by
`scripts/quality.ps1`.

`src/ai4binance/ops/quality_gate/telemetry.py` owns compact, redacted,
token-bounded telemetry helpers for future console/evidence rendering.

`src/ai4binance/ops/quality_gate/__main__.py` is an entry point for the helper
CLI and is intentionally retained by repository cleanup audit.

## Evidence Rules

Profile evidence must preserve:

- profile,
- verification status,
- selected pytest arguments for scoped profiles,
- selected test count for scoped profiles,
- step timestamps,
- step duration,
- exit code,
- step status,
- output size when available,
- evidence artifact path when available.

Full logs remain under `runtime/quality/` and compatibility quality artifacts
remain under `runtime/artifacts/quality/gate/`.

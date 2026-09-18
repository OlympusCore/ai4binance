---
document_id: AI4B-QA-RUN-004
title: AI4BINANCE Python Runtime Migration Benchmark
document_type: RUNBOOK
version: 1.0.0
status: ACTIVE
owner: Enterprise Quality Governance
authority_level: REFERENCE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: python_runtime_migration_benchmark_workflow
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: EXPLANATORY
source_of_truth: false
source_of_truth_scope: performance_regression_gate
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/runbook_python_runtime_migration_benchmark.md
policy_refs:
  - docs/compliance/registry_compliance_matrix.md
implementation_refs:
  - src/ai4binance/ops/performance.py
  - src/ai4binance/ops/python_migration_benchmark.py
validated_by:
  - tests/test_performance_guard.py
  - tests/test_python_migration_benchmark.py
---

# AI4BINANCE Python Runtime Migration Benchmark

## ELI10

This runbook compares two local CPython environments by executing the same
deterministic decision and event-replay workloads. A runtime migration remains
blocked when outputs differ, the canonical runtime policy is invalid, or the
measured median regression exceeds the configured limit.

## Authority And Scope

The canonical measurement and comparison contracts remain in
`src/ai4binance/ops/performance.py`. The migration-specific runner is
`src/ai4binance/ops/python_migration_benchmark.py`. This runbook explains that
runner and does not redefine the performance policy, approve promotion, or
grant execution authority.

Measurements are host-bound and compare only the same environment identity,
code revision, driver hash, workload identity, iteration count, and semantic
output. Cross-host comparisons are invalid.

## Measurement Workflow

Run each environment against the same checkout and environment identifier:

```powershell
$env:PYTHONPATH = "src"
$env:PYTHONDONTWRITEBYTECODE = "1"

<baseline-python> -B -m ai4binance.ops.python_migration_benchmark measure `
  --environment-id <host-and-workload-id> `
  --code-revision <reviewed-revision> `
  --output <baseline-evidence-path>

<current-python> -B -m ai4binance.ops.python_migration_benchmark measure `
  --environment-id <host-and-workload-id> `
  --code-revision <reviewed-revision> `
  --output <current-evidence-path>
```

Compare the artifacts with the canonical runtime:

```powershell
.venv\Scripts\python.exe -B `
  -m ai4binance.ops.python_migration_benchmark compare `
  --baseline <baseline-evidence-path> `
  --current <current-evidence-path> `
  --baseline-version <baseline-version> `
  --current-version 3.14.7 `
  --max-regression-percent 10 `
  --output <comparison-evidence-path>
```

## Fail-Closed Interpretation

The comparison returns a non-zero exit code and `BLOCKED` when any of these
conditions occurs:

- runtime identity, architecture, standard-GIL, SOABI, or JIT policy mismatch;
- code revision, driver hash, benchmark set, or iteration mismatch;
- decision or replay semantic digest mismatch;
- insufficient samples or median regression above the configured threshold.

A passing benchmark is migration evidence only. Every artifact retains:

```text
execution_allowed=false
promotion_status=RESEARCH_ONLY
live_eligibility_status=LIVE_ORDER_BLOCKED
```

It cannot authorize live orders, risk changes, deployment, or promotion.

---
document_id: AI4B-QA-RUN-002
title: AI4BINANCE Quality Gate Profile Workflow
document_type: RUNBOOK
version: 1.0.2
status: ACTIVE
owner: Enterprise Quality Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: quality_gate_profile_workflow
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: quality_gate_profile_workflow_workflow
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/runbook_quality_gate_profiles.md
schema_refs:
  - schemas/governance/repository_artifact.schema.json
policy_refs:
  - config/quality/gates.yaml
implementation_refs:
  - scripts/quality.ps1
registry_refs:
  - docs/registries/registry_workflow_registry.md
validated_by:
  - tests/test_artifact_hygiene_scripts.py
  - tests/test_docs_hygiene.py
---

# AI4BINANCE Quality Gate Profile Workflow

## ELI10

This workflow defines the active quality-gate profiles. `FAST` is the local
change loop, `STANDARD` is the scoped confidence gate, and `FULL` is the
canonical technical quality authority. Ruff, MyPy, dmypy acceleration, pytest
scope selection, fail-fast behavior, timing, and compact evidence must be
controlled by one quality-gate policy and one canonical runner. All profiles
write compact, timestamped quality evidence under `runtime/quality/`.

## Authority And Source Links

This runbook is the governed workflow reference for quality-gate profiles. The
canonical machine-readable profile policy is `config/quality/gates.yaml`; the
canonical Windows execution wrapper is `scripts/quality.ps1`; governed workflow
registration is discoverable through `docs/registries/registry_workflow_registry.md`.

Quality evidence is written to `runtime/quality/`. Compatibility evidence for
the deterministic quality gate remains available under
`runtime/artifacts/quality/gate/`.

## Governance Decision

The active profile decision is:

- `KEEP_RUFF`,
- `KEEP_MYPY`,
- `KEEP_PYTEST`,
- `DMYPY_LOCAL_ACCELERATOR_ONLY`,
- `NO_MYPY_PLUS_DMYPY_DUPLICATION`,
- `FAST_STANDARD_FULL_PROFILES`,
- `AFFECTED_TESTS_FOR_FAST`,
- `SCOPED_REQUIRED_TESTS_FOR_STANDARD`,
- `FULL_TEST_SUITE_FOR_FULL`,
- `FAIL_CLOSED_TEST_SELECTION`,
- `TIMING_FIRST`,
- `COMPACT_CONSOLE_OUTPUT`,
- `FULL_LOG_TO_RUNTIME`,
- `ONE_GATE_ORCHESTRATOR`,
- `CONFIG_DRIVEN_PROFILES`,
- `NO_QUALITY_REDUCTION`,
- `NO_SILENT_TEST_SKIPPING`,
- `NO_FALSE_FULL_VERIFICATION`.

PowerShell may remain the Windows entrypoint, but quality-gate behavior must not
be duplicated across separate user-facing scripts. If future implementation
moves orchestration internals into Python helpers, `scripts/quality.ps1` must
remain a thin compatibility entrypoint that preserves profile semantics and
exit-code propagation.

## Required Architecture

```text
                QUALITY GATE
                     |
      +--------------+--------------+
      |              |              |
    FAST         STANDARD          FULL
      |              |              |
    Ruff           Ruff           Ruff
    dmypy          mypy           mypy
affected tests   scoped tests    full tests
      |              |              |
      +--------------+--------------+
                     |
                     v
              QUALITY EVIDENCE
                     |
         timestamp / duration
           result / scope
            compact output
                     |
                     v
             runtime/quality/
```

## Profile Rules

`FAST` runs Ruff format/check, Ruff lint, `dmypy`, and affected tests resolved
from `config/quality/gates.yaml`. If the affected-test scope cannot be resolved
safely, the run must escalate instead of silently passing. `FAST` reports
`FAST_VERIFIED` and is not full verification.

`STANDARD` runs Ruff format/check, Ruff lint, MyPy, and the configured scoped
test set. The scoped set must include required unit, contract, governance, and
determinism checks when the changed path can affect governed behavior.
`STANDARD` reports `STANDARD_VERIFIED` and is not full verification.

`FULL` runs Ruff format/check, Ruff lint, MyPy, and the full pytest suite.
Only `FULL` may report `FULL_VERIFIED` and act as canonical technical quality
authority. `FULL` still does not grant production deployment, strategy
promotion, live execution, or live-trading authority.

`dmypy` and MyPy must not run sequentially inside the same profile. `dmypy` is
allowed only for `FAST`; MyPy is mandatory for `STANDARD` and `FULL`.

## FULL Approval Replay

An approval-required `FULL` run is a two-phase workflow. The first phase runs
the complete technical profile, writes the provisional deterministic governance
result, and freezes its replay inputs under the run-scoped compatibility
directory. The closure request must bind its `subject_ref` to that frozen
`governance-gate-approval-required.json` artifact instead of a mutable `latest`
alias.

The second phase supplies an independently prepared approval artifact through
`-ApprovalRecordPath`. It must not rerun Ruff, MyPy, pytest, coverage, Bandit,
or the deterministic quality gate. Before replaying the deterministic
governance gate, the wrapper must verify all of the following:

- the frozen result has only approval blockers and its technical gates pass;
- the current Git commit, repository tree, and change-set hashes equal the
  frozen subject;
- the frozen deterministic-quality, repository-validator, pytest, coverage,
  Bandit, and hygiene evidence exists and matches its bound hashes;
- approval records share the frozen subject reference and preserve
  `execution_allowed=false` and `LIVE_ORDER_BLOCKED`.

Any missing artifact, ambiguous subject reference, hash mismatch, workspace
drift, authority-family drift, lifecycle drift, or approval mismatch must fail
closed. The replay may emit canonical `FULL_VERIFIED` evidence only after the
replayed deterministic governance gate reports `PASS` and the normal FULL green
evidence invariants pass. A direct governance-gate invocation is diagnostic
evidence only and does not establish canonical FULL verification.

## Pytest Scope Model

The canonical test taxonomy is:

- `unit`,
- `contract`,
- `governance`,
- `determinism`,
- `replay`,
- `integration`,
- `regression`,
- `security`,
- `resilience`,
- `performance`,
- `research`,
- `paper`,
- `slow`,
- `external`.

Folder taxonomy is the primary classification. Pytest markers are execution and
property metadata. A marker must not create an independent source of truth that
contradicts folder ownership, governed contracts, or profile policy.

## Affected-Test Mapping Rules

Affected-test selection starts from changed repository paths, classifies the
affected domain, and then resolves the required pytest scope. The current
machine-readable mapping lives in `config/quality/gates.yaml`; the active
Windows implementation is `Get-FastAffectedPytestArguments` in
`scripts/quality.ps1`.

The minimum canonical mappings are:

| Changed path family | FAST scope | STANDARD scope |
| --- | --- | --- |
| `scripts/`, `config/quality/` | quality-gate script tests | required quality-gate tests |
| `src/ai4binance/governance/`, `config/governance/`, `policies/` | governance and repository-validator tests | governance, contract, and determinism-sensitive tests |
| `schemas/`, `contracts/` | repository-validator tests | contract and governance tests |
| `docs/` | docs hygiene and repository-validator tests | governed-doc checks where applicable |
| `tests/` | changed tests | changed tests plus required impacted scopes |

Unknown impact must fail closed:

```text
affected scope cannot be determined confidently
        |
        v
STANDARD scope
```

Unknown dependency must never result in skipped tests.

## Critical Escalation Rules

Changes under these families are critical:

- `risk/`,
- `validation/`,
- `decision/`,
- `governance/`,
- `execution/`,
- `core/contracts/`,
- `schemas/`,
- `config/policies/`,
- `policies/`.

For critical changes, `FAST` must include the directly mapped critical tests
when the mapping is deterministic. `STANDARD` must include contract,
governance, and determinism checks. If critical impact cannot be mapped
confidently, the run must escalate to `STANDARD` or `FULL`.

These invariants must remain protected:

- same snapshot plus same policy produces the same decision,
- stale data results in `NO_TRADE`,
- missing critical evidence results in `NO_TRADE`,
- risk veto results in `NO_TRADE`,
- validation veto results in `NO_TRADE`,
- governance conflict results in `BLOCKED`,
- live disabled results in `LIVE_ORDER_BLOCKED`,
- duplicate event delivery produces no duplicate side effect.

## Evidence Rules

Every profile run must produce compact evidence with:

- timestamp,
- duration,
- result,
- profile,
- test scope,
- step exit codes,
- compact stdout or log tail references,
- command or command hash,
- selected tests where a scoped pytest profile is used.

The active evidence layout is:

- `runtime/quality/latest.json`,
- `runtime/quality/history.jsonl`,
- `runtime/quality/<run_id>/summary.json`,
- `runtime/quality/<run_id>/timings.json`,
- `runtime/quality/<run_id>/*.log`.

The compatibility deterministic-gate run layout may retain:

- `runtime/artifacts/quality/gate/deterministic_quality_gate_latest.json`,
- `runtime/artifacts/quality/gate/governance_gate_latest.json`,
- `runtime/artifacts/quality/gate/runs/<run_id>/pytest-output.txt`,
- `runtime/artifacts/quality/gate/runs/<run_id>/bandit-output.txt`.

Generated evidence must remain under `runtime/`. Governed source, policy,
schema, registry, and documentation artifacts must remain outside `runtime/`.

## Console Output Rules

A passing profile emits exactly one compact JSON object with `profile`,
`run_id`, `status`, `duration`, `tools`, `selected_test_count`, and
`evidence_path`. `duration` is measured in milliseconds.

A failing profile emits exactly one compact JSON object with `failed_step`,
`exit_code`, `first_actionable_error`, and `evidence_path`. The actionable error
must be bounded and secret-redacted.

Full stdout, warning streams, tracebacks, profiler data, and pytest progress
must remain file-backed under the run-scoped `runtime/` evidence paths. Generic
tool output is stored under
`runtime/artifacts/quality/gate/runs/<run_id>/<step_id>-output.txt`. Do not load
those files into LLM context unless targeted troubleshooting requires a
specific section.

## Fail-Fast Rules

`FAST` and `STANDARD` are fail-fast profiles:

- Ruff failure stops the run,
- type-check failure stops the run,
- critical pytest failure stops the run.

`FULL` may collect broader evidence, but it may not report
`TECHNICAL_QUALITY_PASS` unless every required gate passes.

## Timing And Baseline Rules

Timing must be captured before performance optimization is claimed. Every tool
step should preserve `started_at_utc`, `ended_at_utc`, `wall_time_ms`,
`exit_code`, `status`, output size, and evidence path where available.

Optimization claims require a before/after evidence baseline. Without measured
baseline evidence, performance claims remain `NOT_VERIFIED`.

## Slow-Test And Benchmark Rules

`FULL` or an internal benchmark mode may collect slowest test modules, slowest
setup or teardown phases, pytest collection duration, pytest execution duration,
cache-hit status, console bytes, and profile trends. Default user-facing output
must remain bounded to the top actionable slow items.

## Safety Rules

`FAST` and `STANDARD` are acceleration profiles only. They must not claim
`FULL_VERIFIED`, must not set canonical technical quality authority, and must
not replace the full quality gate when full assurance evidence is required.

`dmypy` is a local accelerator for `FAST`; it does not weaken the required MyPy
check for `STANDARD` or `FULL`.

No quality profile grants exchange execution, live-order authority, risk-limit
changes, production deployment, or strategy promotion. AI4BINANCE remains
fail-closed; `RESEARCH_ONLY`, `NO_TRADE`, and `LIVE_ORDER_BLOCKED` remain
unchanged unless separate governed live gates explicitly pass.

## Active Commands

```powershell
.\scripts\quality.ps1 -Profile fast
.\scripts\quality.ps1 -Profile standard
.\scripts\quality.ps1 -Profile full
.\scripts\quality.ps1 -Profile full -ApprovalRecordPath <independent-approval.json>
```

## Acceptance Criteria

- `config/quality/gates.yaml` declares `fast`, `standard`, and `full`.
- `FAST` uses `dmypy` and affected tests.
- `STANDARD` uses MyPy and scoped tests.
- `FULL` uses MyPy and the full pytest suite.
- `dmypy` is not the canonical quality authority.
- MyPy and `dmypy` do not run sequentially in the same profile.
- Unknown affected-test scope escalates instead of skipping tests.
- Critical path families trigger critical tests or escalation.
- Passing and failing console output use only their governed compact JSON fields.
- Full tool output remains file-backed under run-scoped `runtime/` paths.
- Quality evidence is written under `runtime/quality/`.
- Compatibility deterministic-gate evidence remains under
  `runtime/artifacts/quality/gate/`.
- Tests preserve that `FAST` and `STANDARD` cannot claim `FULL_VERIFIED`.
- FULL approval replay accepts only frozen, hash-bound, same-subject technical
  evidence and fails closed on drift.

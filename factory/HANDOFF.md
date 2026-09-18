---
document_id: AI4B-FACTORY-PROC-001
title: AI4BINANCE Factory Handoff
document_type: PROCEDURE
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: handoff
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: factory/handoff.md
---

# Factory Handoff

## ELI10

This file carries handoff rules so work can continue with context, proof, and boundaries intact.


## Work Order

Implement only the approved factory bootstrap scope:

- factory state files and templates;
- factory skill suite;
- factory contract validator;
- focused contract tests;
- owner-facing factory documentation.

## Execution Boundary

- Do not change trading signal logic.
- Do not change order execution logic.
- Do not change risk limits.
- Do not read or print secrets.
- Do not enable live trading.
- Do not add unattended background execution in this phase.
- Do not add auto-start, scheduled task, or hidden unattended execution in this
  phase.

## Background Work Mode

`BACKGROUND_SHIFT` is the intended future model: one approved task at a time,
while the computer is on, with visible progress, interruption support, bounded
repair attempts, and mandatory proof before review.

## Required Commands

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\factory\scripts\validate_factory_state.py .
.\.venv\Scripts\python.exe -m pytest tests/test_factory_contracts.py --no-cov
.\scripts\quality.ps1
```

## Completion Contract

Report:

1. changed files;
2. validation commands and results;
3. safety effects;
4. remaining blockers;
5. live eligibility status.

## Live Eligibility

`LIVE_ORDER_BLOCKED`

## Work Order 2026-08-04: Full System Hardening

Implement the ordered slices in `factory/plan.md` one at a time. The initially
allowed files are the persistence, runtime-health, system-report, accounting
diagnostic, validation-checkpoint, local advisory provider, focused test, and
documentation files named by the approved audit diff plan.

Forbidden changes:

- `secrets/` and raw credential values;
- live order, transfer, withdrawal, or risk-limit authority;
- hosted LLM/API routing;
- deletion of wallet, order, validation, or research evidence;
- an all-at-once rewrite of governance or accounting modules.

Required proof after each behavior slice:

```powershell
.\.venv\Scripts\python.exe -m pytest <focused-tests> --no-cov
```

Final proof:

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\factory\scripts\validate_factory_state.py .
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\quality.ps1
```

Stop if a change would require secrets, hosted provider credentials, live
execution authority, or weakening an existing blocker.

## Completion Evidence 2026-08-04

- Factory contract validator: passed.
- Focused persistence, accounting, system-report, Qwen, Lean, and validation
  checkpoint suites: passed.
- Full `scripts/quality.ps1`: 1533 passed; total coverage 90.05%.
- Loopback Ollama probe: provider `ollama`, model `qwen3:8b`, non-empty response.
- Startup control plane: runtime, accounting REST/WS, skill discovery, and
  visible Qwen scheduled tasks are running.
- Safety result: `execution_allowed=false`, `RESEARCH_ONLY`,
  `LIVE_ORDER_BLOCKED`.

Remaining review items are fail-closed domain evidence: inventory reconstruction,
portfolio exposure limits, Futures OOS approval, external opportunity evidence,
and locked stale pytest folders. They are not bypassed by this handoff.

## Work Order 2026-08-08: Local Qwen Stability And Read-Only Workbench

Selected workflow: `HUMAN_IN_THE_LOOP_PROMPT_CHAIN`.

Allowed files:

- `scripts/start_qwen_prompter.ps1`;
- `scripts/start_local_llm.ps1`;
- `scripts/ollama_advisory_common.ps1`;
- `src/ai4binance/local_agent/**`;
- focused tests and this handoff record.

Stopping point and review rule:

- Qwen may receive bounded, secret-free, read-only repository evidence and may
  propose analysis or diffs.
- Qwen must stop before applying a patch, running an arbitrary command,
  changing configuration, or making a trading/risk/wallet/order decision.
- A human-approved bounded work order and the repository quality gate are
  required before any proposed code is applied.

Acceptance:

- healthy IPv4 or IPv6 loopback Ollama ownership never starts a second provider;
- wildcard/non-loopback Ollama listeners fail closed;
- startup races use bounded retries and the visible prompter self-recovers;
- provider/model drift fails closed unless the route is loopback Ollama exact
  model `qwen3:8b`;
- repository evidence tools block secrets, runtime state, absolute paths, and
  path traversal;
- outputs remain `RESEARCH_ONLY`, `execution_allowed=false`, and
  `LIVE_ORDER_BLOCKED`.

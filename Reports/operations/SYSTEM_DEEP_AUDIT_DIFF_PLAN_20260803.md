# AI4BINANCE System Deep Audit and Diff Plan - 2026-08-03

## ELI10

Sistem çalışıyor, ama her parçası "tam sağlıklı" değil. Güvenlik tarafı iyi:
canlı işlem kapalı, OEK kontrolü çalışıyor, kalite denetimi geçiyor. Sorun
daha çok operasyon tarafında: arka plan görevleri çalışsa da sağlık dosyaları
bayat görünüyor, runtime `DEGRADED`, validation sonuçları hâlâ
`RESEARCH_ONLY`, fırsat motoru hazır işlem adayı üretmiyor.

## Scope

- Repository: `C:\vscode-projects\ai4binance`
- Mode: report-only audit + one safe background task start
- Trading authority: none
- Execution state: `execution_allowed=false`
- Live state: `LIVE_ORDER_BLOCKED`
- Promotion state: `RESEARCH_ONLY`

## Commands Run

| Check | Result | Notes |
| --- | --- | --- |
| `quality-system-audit` | `PASSED` | 10 governance checks passed, including `QUALITY_GATE_GREEN` and OEK compliance. |
| `oek-gap-analysis` | `PASSED` | Workflow manifest for background system audit had all required controls. |
| `repository-cleanup-audit` | `REVIEW_REQUIRED` | No cleanup candidates; broad exception and large-module work packages remain. |
| `lean-governance` | `REVIEW_REQUIRED` | 5S, Hoshin, and Six Sigma blockers remain; Poka-Yoke passed. |
| `skills-audit --skills-root .agents\skills` | `BLOCKED` | Expected `SKILL_SCRIPT_REVIEW_REQUIRED`; metadata gaps are resolved. |
| `runtime-once` | `DEGRADED` | Read-only cycle runs but portfolio/research blockers prevent readiness. |
| `validation-summary --symbol HOTUSDT` | `RESEARCH_ONLY` | 20 runs, 20 research-only, 0 staged candidates. |
| `opportunities --symbol HOTUSDT` | `BLOCKED` | No ready candidate; data, OOS, order-book and macro evidence blockers. |
| `accounting-status` | `DEGRADED` | Reconciliation is blocked. |
| `skill-discovery-status` | `DEGRADED` | 10 candidates seen, 0 kept; quarantine filters are active. |
| `startup_status.ps1` | `DEGRADED` | Tasks run, but health timestamps/lock PID proof are inconsistent. |

## Current Background State

After starting `AI4BINANCE-Accounting-Collector`, these Scheduled Tasks are
running:

- `AI4BINANCE-ReadOnly-Runtime`
- `AI4BINANCE-Accounting-Collector`
- `AI4BINANCE-Accounting-WebSocket-Collector`
- `AI4BINANCE-Skill-Discovery`

This proves the always-on surface is active while the computer session is open.
It does not yet prove complete health because `startup_status.ps1` reports:

- `RUNTIME_STATE_STALE`
- `ACCOUNTING_WS_STATE_STALE`
- `RUNTIME_LOCK_PID_MISMATCH`
- `ACCOUNTING_LOCK_PID_MISMATCH`
- `ACCOUNTING_WS_LOCK_PID_MISMATCH`
- `RUNTIME_DEGRADED`

## Gap Analysis

| Area | Current State | Gap | Impact |
| --- | --- | --- | --- |
| QAQC/OEK | Passed | None for governance command path | Strong guardrail; no live authority drift. |
| Background runtime | Tasks running | Health heartbeat and lock proof inconsistent | Operator cannot fully trust status screen. |
| Runtime decision cycle | Runs read-only | Domain blockers keep state `DEGRADED` | Correctly blocks action, but needs clearer remediation. |
| Validation | 20 HOTUSDT runs | 0 staged candidates; unstable OOS and cost stress blockers | No strategy promotion; research loop needs targeted experiments. |
| Opportunity engine | Produces watchlist only | Missing order-book depth, macro/TPO/composite evidence and approvals | Low actionable interaction. |
| Accounting | Files exist | Reconciliation blocked | Cost basis and portfolio risk signals stay degraded. |
| Skill discovery | Quarantine works | No admitted candidates; pinned revision and review blockers | Safe but low adoption velocity. |
| Cleanup/stability | No delete candidates | Six deferred broad exception sites and large modules | Stability and maintainability debt remains. |
| 5S | Docs/reports improved | Stale temp review still required | Workspace hygiene needs bounded cleanup pass. |
| Six Sigma | Measurement present | Target DPMO not met | Defect-reduction loop not controlled yet. |

## Lean, Kaizen, Six Sigma, 5S Findings

### 5S

- Sort: generated cleanup candidates are empty, good.
- Set in order: Docs vs Reports separation is improved.
- Shine: stale temp review remains; do not force ACL ownership.
- Standardize: `Docs/CLI.md` and ELI10 convention are in place.
- Sustain: add recurring health report with fresh timestamp and task/process proof.

### Kaizen

Smallest useful next improvement: make the background status report truthful and
self-refreshing. This reduces confusion without touching trading logic.

### Lean

Biggest waste sources:

- status says stale while processes are alive;
- opportunities list many blockers without a ranked remediation path;
- validation produces many research-only records but no next experiment queue;
- large modules slow review and increase defect risk.

### Six Sigma

Primary defects:

- stale health proof;
- lock PID mismatch;
- reconciliation blocked;
- validation candidate instability;
- broad exception boundaries without focused tests.

## Diff Plan

### P1 - Background Health Truthfulness

Files:

- `Scripts/install_startup_task.ps1`
- `Scripts/startup_status.ps1`
- `tests/test_runtime_supervisor.py` or a new PowerShell-script contract test

Change:

- Make service wrappers write periodic heartbeat while child daemon is alive.
- Store both launcher PID and child PID.
- Update status checker to validate exact service command line and venv path.
- Include `AI4BINANCE-Skill-Discovery` in `startup_status.ps1`.

Acceptance:

- `startup_status.ps1` reports `READY` when tasks are running and domain state is
  fresh.
- If runtime is domain-degraded, status must show `RUNNING_WITH_BLOCKERS`
  instead of mixing process-health failure with trading/research blockers.

### P1 - Operator Report Generator

Files:

- `src/ai4binance/ops/system_report.py`
- `src/ai4binance/cli/commands.py`
- `src/ai4binance/cli.py`
- `Docs/CLI.md`
- `tests/test_system_report.py`

Change:

- Add `system-report` CLI that aggregates QAQC, OEK, Lean, runtime, startup,
  validation, opportunities, accounting and skill-discovery summaries.
- Persist Markdown + JSON under `Reports/operations` and
  `Artifacts/system-audit`.
- Redact wallet amounts and secrets.

Acceptance:

- One command gives a human-readable system report.
- `Docs/CLI.md` updates automatically with the new CLI entry.
- Report always includes `execution_allowed=false` and `LIVE_ORDER_BLOCKED`.

### P2 - Accounting Reconciliation Recovery

Files:

- `src/ai4binance/accounting/reconciliation.py`
- `src/ai4binance/accounting/collectors.py`
- focused accounting tests

Change:

- Add a reconciliation diagnostic summary that names the missing/mismatched
  evidence category without printing balances.
- Add recovery action labels for cost-basis mismatch, stale trade history, and
  blocked reconciliation.

Acceptance:

- `accounting-status` explains the remediation path without private values.
- Runtime portfolio blockers become more actionable.

### P2 - Validation Experiment Queue

Files:

- `src/ai4binance/validation/summary.py`
- `src/ai4binance/research_governance.py`
- `src/ai4binance/cli/research.py`

Change:

- Convert top validation blockers into an ordered experiment queue.
- Prioritize `UNSTABLE_PARAMETER_SENSITIVITY`,
  `OOS_RETURN_CONFIDENCE_INTERVAL_INSUFFICIENT`, and
  `WEAK_OOS_FOLD_CONSISTENCY`.

Acceptance:

- `validation-summary` returns top next experiment candidates.
- No strategy is promoted without OOS evidence.

### P2 - Opportunity Interaction Improvement

Files:

- `src/ai4binance/opportunities.py`
- `src/ai4binance/outlook/engine.py`
- relevant opportunity tests

Change:

- Add blocker grouping: data, validation, execution, macro/context, portfolio.
- Add "next safe action" labels such as `FETCH_ORDER_BOOK_DEPTH`,
  `RUN_VALIDATION_QUEUE`, `REVIEW_MACRO_CONTEXT`.

Acceptance:

- Opportunities remain `RESEARCH_ONLY`.
- User sees fewer duplicate blockers and clearer next actions.

### P3 - Stability Refactor Packages

Files:

- `src/ai4binance/agents/base.py`
- `src/ai4binance/governance/tool_gateway.py`
- `src/ai4binance/observability/local.py`
- `src/ai4binance/ops/runtime.py`

Change:

- Narrow six deferred broad exception sites only with focused fail-closed tests.

Acceptance:

- Same blockers are returned for expected runtime failures.
- Unexpected fatal exceptions are not silently swallowed.

### P3 - Large Module Split

Files:

- `src/ai4binance/accounting/records.py`
- `src/ai4binance/governance/workflow.py`
- `src/ai4binance/research_catalog.py`
- `src/ai4binance/skills/discovery_pipeline.py`

Change:

- Split by behavior-preserving extraction packages.
- Keep public imports stable.

Acceptance:

- Focused module tests pass.
- Full quality gate passes.

## Stop Rules

- Do not widen live authority.
- Do not start order-writing or withdrawal-capable services.
- Do not force ACL ownership on stale temp folders.
- Do not promote validation candidates while all HOTUSDT runs are
  `RESEARCH_ONLY`.
- Do not treat a running Windows task as healthy unless heartbeat, lock and
  latest report all agree.

## Recommended Execution Order

1. P1 background health truthfulness.
2. P1 operator report generator.
3. P2 accounting reconciliation recovery.
4. P2 validation experiment queue.
5. P2 opportunity blocker grouping.
6. P3 exception narrowing.
7. P3 large module split.

## Current Safety Status

- `NO_TRADE`: preserved
- `RESEARCH_ONLY`: preserved
- `LIVE_ORDER_BLOCKED`: preserved
- `execution_allowed`: false
- Real order authority: not granted

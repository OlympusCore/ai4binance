# AI4BINANCE Repository Cleanup and Stability Audit Runbook

## ELI10

Bu belge repo temizligi icin guvenli kontrol yolunu anlatir. Once sadece rapor
hazirlanir; kaynak kod, gizli dosya, kanit, cuzdan durumu veya canli ayar onaysiz
degistirilmez.


This runbook turns repository cleanup, lean-code refactor and stability
optimization into a governed AI4BINANCE process. It is adapted from the local
instruction document `AI4BINANCE Repository Cleanup and Stability Optimization.docx`.

## Purpose

Use this runbook to inspect AI4BINANCE for stale files, duplicated
responsibilities, unclear runtime dependencies, performance bottlenecks and
stability risks without weakening trading safety.

The first pass is report-only. Code, docs, folders, dependencies, Git history,
wallet state, exchange state and live settings must not be changed during the
audit pass unless the user explicitly approves a bounded diff.

## Fixed Safety Boundary

- Keep deterministic signal, risk and execution gates authoritative.
- Keep LLM/agent output advisory only.
- Keep `NO_TRADE` as the default for weak, missing or contradictory evidence.
- Keep incomplete OOS evidence `RESEARCH_ONLY`.
- Keep every live path `LIVE_ORDER_BLOCKED` unless all explicit live gates pass.
- Do not read or copy secrets.
- Keep local machine profile details behind the `Computer.md` boundary.
- Do not delete, move, rename, format, install, uninstall, commit, push, merge or
  reset in the first audit pass.
- Do not treat static import absence as proof that a file is unused.

## Root and Junction Rule

Before any inventory or cleanup decision, verify that:

- `C:\AI-Workspace\02_Projects\ai4binance` may be a junction.
- The canonical working tree is `C:\vscode-projects\ai4binance` when the
  junction target points there.
- The two paths must not be treated as duplicate repositories.

## Excluded From Source Analysis

Exclude generated or protected paths from source-dependency conclusions:

- `.git`
- `.venv`, `venv`
- `__pycache__`
- `.pytest_cache`, `.mypy_cache`, `.ruff_cache`
- `.coverage`, `.coverage.*`, `coverage.xml`, `htmlcov`
- `Artifacts`, except generated-hygiene summaries
- `Logs`
- `State`, especially `State/private`
- `Secrets`
- `Models`
- `Data`
- `Backtest/validation`
- `Wallet`
- `Orders`
- `Opportunities`

These paths may be reported for hygiene, retention or owner decisions, but not
bulk-read, bulk-deleted or staged without a separate owner decision.

## Inventory Contract

For each reviewed file or folder, collect evidence where practical:

| Field | Meaning |
| --- | --- |
| Path | Repository-relative path |
| Type | Python, Markdown, TOML, YAML, JSON, script, generated, evidence |
| Size | Approximate size |
| Modified | Last modified timestamp |
| Role | Observed or inferred responsibility |
| Imported By | Static import references |
| Imports | Static dependencies |
| Entry Point | CLI, script, worker, service or `__main__` use |
| Test Coverage | Direct or indirect test references |
| Runtime Evidence | CLI/config/registry/workflow proof |
| Duplicate Risk | Similar responsibility elsewhere |
| Status | `KEEP`, `REFACTOR`, `MERGE`, `ARCHIVE`, `QUARANTINE_CANDIDATE`, `DELETE_CANDIDATE`, `UNKNOWN_DYNAMIC_USAGE` |
| Confidence | High, Medium or Low |
| Evidence | File, line, command or measured output |

## Dynamic Usage Guard

Mark a file as `UNKNOWN_DYNAMIC_USAGE` instead of unused when any of these
signals exist:

- `importlib`, `__import__`, `getattr`, reflection or dependency injection
- agent, skill, strategy, model, CLI or plugin registry
- config-driven class/module loading
- YAML, JSON or TOML references
- subprocess or script entry point
- test fixture use
- RAG loader, MCP server or worker process
- `__main__` entry point

## Audit Phases

1. Verify repository root and junction target.
2. Count source, test, docs, scripts and agent-skill files while excluding
   generated/protected folders.
3. Identify CLI scripts, PowerShell scripts and `__main__` entry points.
4. Build a static AST import graph and flag exact cycles.
5. Flag dynamic-usage surfaces and do not classify them as dead code.
6. Identify large modules, broad exception handlers and duplicated
   responsibilities as refactor candidates.
7. Run quality gates in non-live mode and record exact pass/fail evidence.
8. Run artifact hygiene dry-run and record generated-only candidates.
9. Produce RF work packages; do not implement them without explicit approval.

## Classification Rules

- `KEEP`: active runtime, test, config, security, evidence or compliance role.
- `REFACTOR`: active but too large, mixed responsibility, fragile or slow.
- `MERGE`: same responsibility as another active module and behavior can be
  preserved by a canonical implementation.
- `ARCHIVE`: historical or audit value, not active runtime.
- `QUARANTINE_CANDIDATE`: no active proof yet, but observation period required.
- `DELETE_CANDIDATE`: only after no import, config, CLI, registry, test,
  dynamic-use, audit or replacement uncertainty remains and user approval exists.
- `UNKNOWN_DYNAMIC_USAGE`: static analysis cannot prove safe removal.

## Performance Baseline Targets

Measure before optimizing:

- CLI startup time
- single research or runtime cycle duration
- OHLCV preparation by timeframe
- indicator computation time
- agent/orchestrator duration
- LLM/RAG call count when enabled
- peak RAM, CPU and disk I/O where available
- network and Binance request count
- duplicate downloads or repeated indicator computation
- backtest, walk-forward and tuning duration

Only recommend cache, async, batching or lazy initialization after a measured
bottleneck is found. Do not move CPU-bound work into async merely for style.

## Stability Checks

Review these without changing behavior:

- timeout, retry, backoff and jitter handling
- HTTP 429/418 and stale data behavior
- websocket reconnect and REST fallback contracts
- atomic write, duplicate prevention and JSON recovery
- lock files, process conflicts and restart recovery
- UTC-aware timestamps, config hash and dataset revision
- broad `except Exception`, swallowed traceback and unsafe fallback behavior

Safe fallback expectations:

- missing data -> `NO_TRADE`
- unknown risk -> `NO_TRADE`
- unknown wallet/filter -> `EXECUTION_BLOCKED`
- inconsistent state -> `SAFE_MODE`
- missing live gate -> `LIVE_ORDER_BLOCKED`

## Refactor Package Format

Each proposed package must be explicit:

| Field | Content |
| --- | --- |
| ID | `RF-001`, `RF-002`, ... |
| Priority | P0 security/data integrity, P1 stability, P2 performance, P3 clean code, P4 archive/hygiene |
| Problem | Current issue |
| Evidence | File, line, command or metric |
| Proposed Change | Smallest safe diff |
| Files Affected | Expected scope |
| Risk | Low, Medium or High |
| Tests | Required checks |
| Rollback | How to revert |
| Expected Benefit | Measurable outcome |
| Approval | Explicit user approval required |

## Output Contract

The first audit report must include:

- executive summary
- repository inventory
- entry point and runtime map
- dependency and dynamic-usage findings
- dead-code or archive candidates, if any
- performance baseline signals
- stability and technical-debt risks
- prioritized RF work packages
- validation status
- unchanged live eligibility status

The first audit pass ends with:

```text
AUDIT_COMPLETED -- AWAITING_EXPLICIT_IMPLEMENTATION_APPROVAL
```

## Approved Implementation Rule

After the user approves one or more RF packages, implement only the approved
scope. Update related Markdown instructions under `WRITTEN_APPROVAL_DOC_SYNC`
when the system rule changes. Run targeted checks and the full quality gate when
the diff changes runtime behavior.


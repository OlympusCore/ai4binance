# Repo Cleanup Diff Plan - 2026-07-28

This is a source-grounded cleanup plan for `C:\vscode-projects\ai4binance`.
It is intentionally staged because the checkout has no baseline commit yet and
many files are untracked. No trading authority is widened by this plan.

## Current Audit Snapshot

- Git baseline: no commits yet on `main`.
- Git status entries: 215 total; 13 added, 17 added-modified, 185 untracked.
- Source surface: 227 Python source files under `src/ai4binance`.
- Test surface: 111 `test_*.py` files under `tests`.
- Documentation surface: 20 Markdown files under `Docs`.
- Script surface: 14 PowerShell scripts under `Scripts`.
- Current folder audit blockers: `STALE_GENERATED_FOLDER_PRESENT`,
  `PYTEST_GENERATED_FOLDER_PRESENT`.
- Current remaining P1 folder: `.pytest_cache`.
- Largest non-venv roots observed:
  - `Models`: 463.72 MB
  - `Backtest`: 388.05 MB
  - `Logs`: 171.78 MB
  - `State`: 156.82 MB
  - `Artifacts`: 88.59 MB
  - `Tools`: 62.05 MB
  - `Data`: 19.63 MB

## Safety Boundary

- Do not read, copy, stage, or delete secret values.
- Do not bulk-delete `Secrets`, `State/private`, `Models`, `Wallet`, `Orders`,
  `Opportunities`, `Backtest/validation`, or `Data`.
- Keep `NO_TRADE`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` unchanged.
- Treat generated cleanup as repo hygiene only, not live readiness evidence.
- Focused tests may use `--no-cov`; full completion requires
  `Scripts/quality.ps1`.

## Slice 0 - Baseline Snapshot Before Cleanup

Purpose: make cleanup reversible before wider churn.

Planned diff:

- Add no product behavior.
- Create a local-only status artifact under ignored `Artifacts/` if needed.
- Capture:
  - `git status --short --branch`
  - `git diff --stat`
  - `Scripts/folder_structure_audit.ps1`
  - `Scripts/cleanup_generated_artifacts.ps1 -IncludeTestTemp -IncludeLogs`

Validation:

- Confirm generated reports are ignored.
- Confirm `Secrets/*` remains ignored except `Secrets/.gitkeep`.

## Slice 1 - Generated Folder Hygiene

Purpose: remove quality-gate noise without losing evidence.

Planned diff:

- `Scripts/cleanup_generated_artifacts.ps1`
  - Keep dry-run as default.
  - Add explicit mode names for `Caches`, `TestTempRetention`, and
    `LogsArchive`.
  - Persist dry-run manifests under ignored `Artifacts/maintenance-archive`.
- `src/ai4binance/ops/folder_structure_audit.py`
  - Keep schema `1.1` fields:
    `cleanup_probe_status`, `delete_probe_status`, `acl_readable`,
    `exclusive_access`, `cleanup_blocker`.
  - Add a dedicated `.pytest_cache` ACL diagnostic recommendation if deletion
    fails again.
- `.gitignore`
  - Keep generated roots ignored:
    `.pytest_cache/`, `.pytest-audit-temp*/`, `.pytest-money-audit-*/`,
    `Artifacts/TestTemp/`, `Artifacts/maintenance-archive/`,
    `Artifacts/folder-structure-audit/`, `Logs/**/*.log`, `Logs/**/*.jsonl`.

Do not do automatically:

- Do not force-take ownership of `.pytest_cache` without explicit approval.
- Do not delete `Logs` wholesale.

Validation:

- `python -m pytest tests/test_folder_structure_audit.py --no-cov -q`
- `python -m ruff check src/ai4binance/ops/folder_structure_audit.py tests/test_folder_structure_audit.py`
- `python -m mypy src/ai4binance/ops/folder_structure_audit.py tests/test_folder_structure_audit.py`

## Slice 2 - VS Code and Search Hygiene

Purpose: reduce editor load and accidental broad scans.

Planned diff:

- `.vscode/settings.json`
  - Normalize generated-folder casing in excludes, especially `Logs` vs `logs`.
  - Keep `.venv`, `Artifacts`, `Backtest`, `Data`, `Models`, `Secrets`,
    `State`, caches, and `Tools/llama.cpp` out of watcher/search/indexing.
  - Keep `python.analysis.diagnosticMode=openFilesOnly`.
- `.vscode/tasks.json`
  - Keep `Quality: all` as the canonical full gate.
  - Keep `runOptions.instanceLimit=1`.
  - Add a dry-run hygiene task only if it does not run destructive cleanup.

Validation:

- Parse JSON.
- Run `code` reload manually if desired; no CLI reload requirement.

## Slice 3 - Folder Ownership Tightening

Purpose: turn unclear root folders into explicit keep/archive/delete decisions.

Planned diff:

- `Docs/FOLDER_OWNERSHIP.md`
  - Add owner and action columns for empty roots:
    `Alerts`, `Futures`, `News`, `Orders`, `Spot`, `Wallet`, `intelligence`.
  - Mark each as one of:
    `KEEP_DOMAIN_ROOT`, `MOVE_UNDER_DOCS`, `ARCHIVE_LOCAL`, `DELETE_EMPTY`.
- Optional future script:
  - Add a report-only folder-owner checker that flags roots missing ownership.

Recommended decisions:

- Keep: `Spot`, `Wallet`, `Orders`, `Opportunities`, `Data`, `Backtest`,
  `State`, `Models`, `Tools`.
- Review before keep/delete: `Alerts`, `Analysis`, `Futures`, `News`,
  `intelligence`, `skill-staging`, `factory`.
- Never broad-delete: `Secrets`, `State/private`.

Validation:

- Documentation-only diff: no runtime validation required beyond Markdown review.

## Slice 4 - Commit Slicing / Baseline Construction

Purpose: make future cleanup safe by separating baseline from evolution.

Proposed staging groups:

1. Hygiene and local tooling
   - `.gitignore`
   - `.vscode/*`
   - `Scripts/quality.ps1`
   - `Scripts/*cleanup*`
   - `Docs/FOLDER_OWNERSHIP.md`
   - `Docs/REPO_CLEANUP_DIFF_PLAN_20260728.md`
2. Core package baseline
   - `pyproject.toml`
   - `requirements.txt`
   - `src/ai4binance/**`
3. Tests baseline
   - `tests/**`
4. Documentation baseline
   - `README.md`
   - `Docs/**`
   - root instruction documents
5. Local runtime placeholders only
   - `Secrets/.gitkeep`
   - `Models/.gitkeep`

Do not stage:

- `.env`
- `.coverage`
- `Logs/**`
- `Artifacts/**`
- `Backtest/validation/**`
- `State/**`
- private model binaries or downloaded tool zips

Validation:

- `git diff --check`
- `Scripts/quality.ps1`
- Confirm full quality gate result is not claimed green if coverage or formatting
  fails.

## Slice 5 - Evidence Retention Policy

Purpose: keep audit evidence but avoid unbounded growth.

Planned diff:

- `Docs/FOLDER_OWNERSHIP.md`
  - Add retention values:
    - `Artifacts/TestTemp`: keep last 2 days by default.
    - `Logs`: archive files older than 7 days by default.
    - `Backtest/validation`: archive only by explicit symbol/timeframe scope.
- `Scripts/cleanup_generated_artifacts.ps1`
  - Add `-WhatIfSummaryPath` or equivalent manifest-only output path.
  - Keep `-Apply` required for mutation.

Validation:

- Dry-run candidate count before apply.
- After apply, rerun `Scripts/folder_structure_audit.ps1`.

## Recommended Next Diff

Start with Slice 2 plus the non-destructive parts of Slice 3:

- Normalize `.vscode/settings.json` casing/excludes.
- Add a `Quality: hygiene dry-run` VS Code task.
- Extend `Docs/FOLDER_OWNERSHIP.md` with explicit owner decisions.

This gives immediate editor stability and repo readability without touching
private state, research evidence, or trading behavior.

Final state remains:

- `execution_allowed=false`
- `live_eligibility_status=LIVE_ORDER_BLOCKED`

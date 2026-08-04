---
name: quality-gate-loop
description: Run a strict, self-checking Python repository quality loop that requires green pytest tests, zero Ruff lint findings, and zero MyPy type errors. Use when asked to fix tests, make CI or quality gates green, iterate on failures, apply a Discover-Plan-Execute-Verify workflow, or stop after a bounded number of repair attempts.
metadata:
  ai4binance.authority: advisory-only
  ai4binance.version: 1.0.0
  ai4binance.owner: QualityDepartmentManager
  ai4binance.trust_level: review-required
  ai4binance.last_reviewed: 2026-08-03
  ai4binance.trigger_examples: quality gate loop; fix tests; make CI green
---

# Quality Gate Loop

Drive one repository from a reproducible manual quality run to a strict green gate.
Fix one highest-impact failure class per iteration and stop after eight iterations.

## Discover

- Inspect repository instructions, status, test layout, and Python configuration.
- Preserve unrelated user changes.
- Prefer the repository-local Python interpreter.
- If the requested test path does not exist, state the assumption and use the
  configured test suite. Do not silently invent tests.
- Get one reliable manual gate run before editing application code.

## Gate

On Windows, run the bundled gate from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  <skill-path>\scripts\invoke_gate.ps1 -RepositoryRoot <repo-root>
```

The script always runs pytest, Ruff, and MyPy independently. One failure must not
hide the other results. Exit code zero is the only passing result.

## Loop

For iterations 1 through 8:

1. PLAN: state the single next step.
2. DO: run the complete gate and read every failure. If it fails, select the one
   highest-impact failure class and make the smallest safe change that fixes it.
3. VERIFY: rerun the complete gate. Score tests, lint, and types from 1 to 10.
   A passing check scores 10. A failing check must score below 8 and list its exact
   remaining weakness. Never award a soft pass.
4. DECIDE:
   - Print `FINAL` and stop only when pytest, Ruff, and MyPy all exit zero.
   - Otherwise print `ITERATING` and start the next pass with the weakest check.
   - Stop after iteration 8 even if red.

Each pass must fix only the selected failure class. Do not combine unrelated cleanup.
Add or update regression tests when application behavior changes.

## Stop report

On either stop condition, summarize:

- iteration count and stop reason;
- changed files and the failure each change addressed;
- exact final pytest, Ruff, and MyPy results;
- anything still failing;
- safety or validation limitations.

Do not schedule this workflow until one manual gate run is green. Scheduling is a
separate explicit action; preserve the same gate and eight-iteration stop condition.

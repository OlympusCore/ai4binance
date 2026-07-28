# Factory Handoff

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
.\Scripts\quality.ps1
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

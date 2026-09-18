---
name: factory-tests
description: Use when adding proof contracts, acceptance criteria, and exact verification commands to AI4BINANCE factory tasks before code is written.
metadata:
  ai4binance.authority: advisory-only
  ai4binance.version: 1.0.0
  ai4binance.owner: QualityDepartmentManager
  ai4binance.trust_level: local
  ai4binance.last_reviewed: 2026-08-03
  ai4binance.trigger_examples: /factory-tests; acceptance contract; proof requirements
---

# Factory Tests

Act as the professor. No implementation task is ready until it has a concrete
exam that can prove success or force iteration.

## Required Contract Per Task

Each task in `factory/PLAN.md` must define:

- observable acceptance criteria;
- exact command or manual proof path;
- expected result;
- degraded or failure path;
- stop condition;
- safety boundary.

## Preferred Proof Commands

Use focused checks first, then the full gate when the implementation is ready:

```powershell
.\.venv\Scripts\python.exe -m pytest <focused-test> --no-cov
.\Scripts\quality.ps1
```

For factory-only changes:

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\factory\scripts\validate_factory_state.py .
.\.venv\Scripts\python.exe -m pytest tests/test_factory_contracts.py --no-cov
```

## Proof Rules

- Do not accept screenshots, generated prose, or LLM agreement as the only
  proof for code behavior.
- Do not mark a task done while tests, lint, types, dependency checks, or
  safety checks are red.
- Do not call a sub-threshold coverage run green.
- Keep incomplete live gates reported as `LIVE_ORDER_BLOCKED`.
- Do not require network, credentials, Binance access, browser automation, or
  model availability unless the task explicitly needs them.

## Output

Update task contracts and report missing proof, risky assumptions, and commands
to run.

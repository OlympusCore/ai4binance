# AI4BINANCE Governed Software Factory

## ELI10

Bu belge yazilim fabrikasinin nasil calistigini anlatir. Bir fikir once kucuk ve
kontrollu is paketine donusur, sonra test ve inceleme ile ilerler; fabrika tek
basina canli islem yetkisi uretmez.


The factory is a repo-local context and work-order system for AI4BINANCE. It
turns user-approved ideas into briefed, planned, test-contracted, reviewable
tasks while preserving validation-first trading safety.

## Design Principles

- Keep deterministic trading code in charge of signals, risk, exchange filters,
  execution permission, and audit trails.
- Keep LLM and agent output advisory-only.
- Prefer small vertical slices with explicit proof commands.
- Require a fresh review before treating a task as complete.
- Keep owner documentation current so the human decision-maker understands the
  system.
- Treat background execution as `BACKGROUND_SHIFT`: computer-on,
  user-visible, interruptible, and bounded.

## Factory Phases

1. `/factory`: read `factory/STATE.md`, detect the next phase, and route.
2. `/factory-plan`: interview for missing context and write `BRIEF.md`.
3. `/factory-plan`: convert an approved brief into `PLAN.md`.
4. `/factory-tests`: attach acceptance criteria and proof commands.
5. `/factory-explain`: explain the plan in plain language and diagrams.
6. `/factory-handoff`: package a bounded work order.
7. `BACKGROUND_SHIFT`: while the computer is on, build one approved task, test
   it, log it, and stop on blockers or user interruption.
8. `/factory-review`: re-run tests and try to break the result.
9. `/factory-explain`: update `GUIDE.md` with what actually exists.

## Safety Boundary

This factory does not provide live trading authority. Any task that touches
secrets, wallet state, live execution, risk limits, provider routing, or external
publishing requires explicit user approval and must still return
`LIVE_ORDER_BLOCKED` unless every live gate passes.

## First Validation Commands

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\factory\scripts\validate_factory_state.py .
.\.venv\Scripts\python.exe -m pytest tests/test_factory_contracts.py --no-cov
.\Scripts\quality.ps1
```


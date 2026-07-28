---
name: factory
description: Route governed AI4BINANCE software factory work. Use when the user asks for /factory, factory orchestration, project state routing, next factory step selection, or converting an idea into the correct factory phase while preserving NO_TRADE, RESEARCH_ONLY, and LIVE_ORDER_BLOCKED safety boundaries.
---

# Factory Foreman

Act as the foreman for the AI4BINANCE factory. Read `factory/STATE.md` first,
then route the user to the correct phase without widening authority.

## Required Inputs

- User request.
- `factory/STATE.md`.
- Existing factory artifacts if present: `BRIEF.md`, `PLAN.md`, `HANDOFF.md`,
  `REVIEW.md`, `GUIDE.md`, `progress.md`, and `log.md`.
- Relevant repo instructions and affected source files.

## Routing

- Missing or vague product intent: use `factory-plan` interview mode.
- Approved brief but no ordered tasks: use `factory-plan` blueprint mode.
- Tasks without proof: use `factory-tests`.
- Human understanding bottleneck: use `factory-explain`.
- Ready for bounded implementation: use `factory-handoff`.
- Ready for background work preparation: use `factory-handoff` and require
  `BACKGROUND_SHIFT` constraints.
- Completed implementation: use `factory-review`.
- Reviewed implementation needing owner docs: use `factory-explain`.

## Safety Rails

- Do not authorize live trading.
- Do not read or expose secrets.
- Do not alter wallet state, risk limits, order modes, provider routing, or
  production parameters without explicit user approval.
- Keep final trading authority in deterministic code.
- Preserve `NO_TRADE`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` defaults.
- Stop when the next action requires credentials, legal authority, external
  publishing, or autonomous live execution.
- Treat background work as `BACKGROUND_SHIFT`: computer-on, user-visible,
  interruptible, and bounded to one approved task at a time.

## Output

Return:

1. detected phase;
2. evidence read;
3. recommended next skill;
4. missing context;
5. safety status;
6. exact next artifact to edit.

## Validator

Run this when changing factory artifacts:

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\factory\scripts\validate_factory_state.py .
```

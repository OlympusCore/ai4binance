---
name: factory-plan
description: Interview for missing product context and turn approved AI4BINANCE factory briefs into small ordered testable plans. Use for /factory-plan, BRIEF.md creation, PLAN.md creation, roadmap decomposition, task slicing, and planning before implementation.
---

# Factory Plan

Create either `factory/BRIEF.md` or `factory/PLAN.md` depending on the current
phase. Keep planning source-grounded and small enough for a bounded execution
agent.

## Interview Mode

Use when product intent is incomplete.

Ask one important question at a time unless the answer is already discoverable
from the repository. Capture:

- product intent;
- user need;
- existing codebase context;
- constraints;
- unknowns;
- recommendation.

Write or update `factory/BRIEF.md`.

## Blueprint Mode

Use after the brief is approved.

Break work into ordered tasks. Each task must include:

- goal;
- affected files or likely modules;
- acceptance criteria;
- proof command placeholder;
- stop conditions;
- safety notes.

Write or update `factory/PLAN.md`.

## AI4BINANCE Boundaries

- Do not plan live order authority unless the user explicitly asks for it and
  live gates are represented as blockers.
- Do not let wallet state affect historical backtests.
- Mark weak evidence as `RESEARCH_ONLY`.
- Mark incomplete live gates as `LIVE_ORDER_BLOCKED`.
- Prefer the smallest vertical slice that can be tested.

## Output

Return the changed artifact, the next factory phase, and any unresolved
questions.

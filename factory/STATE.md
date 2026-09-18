# AI4BINANCE Factory State

This file is the foreman memory for governed factory work. Keep it short,
current, and source-grounded. If this file conflicts with repository code,
tests, or user instructions, treat the code/tests/user instructions as the
source of truth and update this file.

## Current Phase

phase: review
status: AWAITING_INDEPENDENT_REVIEW
updated_at: 2026-09-06

## Mission

Build AI4BINANCE changes through small, testable, reviewable work orders while
preserving deterministic trading safety, advisory-only LLM boundaries, and
repo-local Python 3.14.7 validation.

## Safety Defaults

- Trading output defaults to `NO_TRADE` when evidence is weak or incomplete.
- Weak or incomplete validation evidence defaults to `RESEARCH_ONLY`.
- Live execution defaults to `LIVE_ORDER_BLOCKED`.
- Background work mode is `BACKGROUND_SHIFT`: run only while the computer is
  on, the user session is active, and progress remains inspectable.
- LLM output is advisory only and must not own final signals, risk gates,
  exchange validation, order authorization, wallet state, or production
  parameter promotion.
- Secrets must not be read into prompts, logs, reports, examples, or tests.
- Factory work must not change `secrets/`, live order authority, risk limits,
  order modes, or provider routing without explicit user approval.

## Required Artifacts

- `factory/brief.md`: user goal, context, constraints, unknowns.
- `factory/plan.md`: small ordered tasks with acceptance contracts.
- `factory/handoff.md`: bounded work order for an execution agent.
- `factory/review.md`: fresh review results and remaining blockers.
- `factory/guide.md`: owner-facing explanation of what exists.
- `factory/progress.md`: concise progress diary.
- `factory/log.md`: append-only operational notes.
- `factory/decisions.jsonl`: one JSON object per durable decision.

## Allowed Factory Phases

1. interview
2. blueprint
3. test-contract
4. explain
5. handoff
6. background-shift
7. review
8. owner-guide

## Background Shift Rules

- Run only while the computer is awake and the user can inspect or interrupt
  the work.
- Process one approved task at a time.
- Log progress after each meaningful step.
- Stop on failed proof after the bounded repair budget.
- Do not create startup tasks, scheduled tasks, or unattended execution loops
  unless the user explicitly approves a separate automation diff.
- Do not continue when the user session locks, the machine sleeps, required
  tools disappear, or the working tree becomes unsafe for the current task.

## Stop Conditions

- User intent is ambiguous and the safest assumption would affect live trading,
  secrets, wallet state, risk limits, or external publishing.
- Required data, provider credentials, model binaries, or legal authority are
  missing.
- Quality gate fails after the bounded repair budget.
- Worktree contains unrelated changes in files that the current task must edit.
- A task asks for autonomous live execution or promotion without validation.
- A task asks for unattended background work, auto-start, or hidden execution
  without an explicit automation approval.

## Validation Command

Use repo-local Python and quality gates:

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\factory\scripts\validate_factory_state.py .
.\.venv\Scripts\python.exe -m pytest tests/test_factory_contracts.py --no-cov
.\scripts\quality.ps1
```

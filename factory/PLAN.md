# Factory Plan

## Task 1: Bootstrap Factory State

Goal: Add source-controlled factory artifacts that make project state,
constraints, and stop conditions explicit.

Acceptance:

- `factory/STATE.md` exists and names the active phase.
- Safety defaults include `NO_TRADE`, `RESEARCH_ONLY`, and
  `LIVE_ORDER_BLOCKED`.
- Stop conditions cover secrets, live trading, provider changes, and failed
  quality gates.

Proof:

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\factory\scripts\validate_factory_state.py .
```

## Task 2: Add Factory Skills

Goal: Add routeable skills for the foreman, planning, tests, explanation,
handoff, and review.

Acceptance:

- Each skill has valid YAML frontmatter with `name` and `description`.
- Skill bodies describe inputs, outputs, safety rails, and stop conditions.
- `/factory` routes phases without authorizing live execution.

Proof:

```powershell
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-plan
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-tests
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-explain
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-handoff
.\.venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" .\.agents\skills\factory-review
```

## Task 3: Add Factory Contract Test

Goal: Add deterministic tests that protect the factory contract from drifting
into unsafe automation.

Acceptance:

- Tests check required artifacts, required skill names, safety terms, and the
  validator script.
- Tests do not require network, credentials, Binance connectivity, browser
  automation, or local LLM availability.

Proof:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_factory_contracts.py --no-cov
```

## Deferred: Background Shift

`BACKGROUND_SHIFT` is intentionally deferred. It must run only while the
computer is on and the user can inspect or interrupt progress. Before
implementation, define:

- max tasks per run;
- max repair attempts;
- allowed file globs;
- forbidden file globs;
- logging format;
- approval gates;
- review handoff rules.
- behavior when the session locks, the machine sleeps, or the user interrupts.

## Deferred: Auto Loom Proof

Browser recording and narrated proof are deferred until the factory contract,
review cycle, and local proof strategy are stable.

## 2026-08-04: System Hardening And Local Qwen Work Order

Goal: Apply the approved audit diff plan in bounded slices while keeping the
deterministic trading core independent from the local advisory LLM.

Ordered slices:

1. Replace whole-file JSONL destination read-back with bounded tail read-back.
2. Reduce runtime audit overproduction with compact verified event envelopes.
3. Unify service, task, and provider health evidence.
4. Add report-only accounting reconciliation diagnostics.
5. Reduce repeated audit/test scans and add performance controls.
6. Apply safe 5S and modularity guards without deleting protected evidence.
7. Add checkpointable validation visibility.
8. Prove all advisory LLM paths use loopback Ollama `qwen3:8b`.

Acceptance:

- Every slice has focused deterministic tests and rollback remains one scoped diff.
- `Scripts/quality.ps1` passes after implementation.
- Ollama is loopback-only and the selected advisory model is `qwen3:8b`.
- Signals, risk, validation, and execution permission remain deterministic.
- `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` remain intact.

Implementation result:

- Bounded JSONL read-back and bounded accounting tail reads are implemented.
- Research runtime audit events use compact hashes, refs, stage/blocker summaries.
- System report includes service/PID/lock state and local Ollama/Qwen health.
- Interactive system-report output is bounded; full evidence remains persisted.
- Validation checkpoints bind dataset, config, implementation, and artifact hashes.
- Safe 5S cleanup ran without ACL takeover; locked stale temp folders remain blockers.
- Advisory production routing uses loopback Ollama `qwen3:8b` only.
- Full gate passed: 1533 tests, 90.05% coverage, Ruff/MyPy/Bandit/dependencies clean.

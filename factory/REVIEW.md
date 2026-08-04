# Factory Review

## Review Status

status: PASS_WITH_LIMITATIONS
reviewer: same-thread-audit-not-independent
reviewed_at: 2026-08-04

## Review Checklist

- Re-read `factory/BRIEF.md`, `factory/PLAN.md`, and `factory/HANDOFF.md`.
- Confirm implementation stayed inside the approved scope.
- Confirm no secret values were read, logged, copied, or committed.
- Confirm no live trading authority, order mode, risk limit, wallet state, or
  provider routing was widened.
- Run the factory validator and focused factory tests.
- Run the full repository quality gate when practical.
- Try to identify stale state, vague acceptance criteria, missing blockers, and
  false proof.

## Findings

### Passed proof

- The factory contract validator passes.
- The full repository quality gate passes: Ruff, MyPy, dependency integrity,
  1533 Pytest tests, and 90.05% total coverage.
- QA/QC, agent-stack, OEK constitution, privacy, accounting reconciliation, and
  the bounded OEK gap check pass without blockers.
- A real Ollama generation using the exact `qwen3:8b` model succeeds and
  preserves `ADVISORY_ONLY`, `execution_allowed=false`, and
  `LIVE_ORDER_BLOCKED` boundaries.

### P0 - Local Ollama startup race and duplicate ownership

- The visible Qwen scheduled task initially reported
  `OLLAMA_PROVIDER_UNAVAILABLE` even though Ollama App already owned port 11434
  through an IPv6 listener.
- `Scripts/start_qwen_prompter.ps1` detects only a `127.0.0.1` listener, may
  start a second `ollama serve`, performs a one-shot readiness probe, and then
  waits without self-recovery after the startup race.
- Restarting the Qwen task recovered health and a real local generation, but
  the underlying code defect and duplicate server ownership remain open.

### P1 - Runtime and research-effect blockers

- Runtime remains fail-closed for inventory reconstruction, wallet/trade
  quantity mismatch, unavailable cost basis, portfolio exposure limits, and
  unapproved futures OOS evidence.
- Twenty validation runs produced zero staged candidates. The dominant causes
  are unstable parameter sensitivity, weak OOS consistency, insufficient OOS
  return/confidence, negative cost stress, high bootstrap loss probability,
  and low trade count.
- Opportunity generation is active, while execution correctly remains blocked
  by missing ready candidates, external/order-book/derivatives/whale evidence,
  trade and risk plans, backtest/walk-forward/OOS proof, and risk approval.

### P1 - Performance and 5S limitations

- The current full gate passed but took materially longer than the immediately
  preceding run; repeated controlled measurements are required before assigning
  a cause.
- The generated-artifact dry run found 26 review candidates. The active
  research event log is approximately 773 MB and needs verified rotation and
  archival rather than deletion.
- Eighteen stale test-temp directories are ACL blocked. No ownership or ACL
  takeover was attempted.

### Review limitation

This is a same-thread evidence review, not the fresh independent review required
by the factory workflow. `factory/STATE.md` must remain
`AWAITING_INDEPENDENT_REVIEW` until that separate review occurs.

## Verdict

`PASS_WITH_LIMITATIONS`

Trading and parameter-promotion status remains `RESEARCH_ONLY`; live eligibility
remains `LIVE_ORDER_BLOCKED`.

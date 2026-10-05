---
document_id: AI4B-FACTORY-PROC-002
title: AI4BINANCE Factory Review
document_type: PROCEDURE
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: review
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: factory/review.md
---

# Factory Review

## ELI10

This file defines how factory work is reviewed before it can be considered complete.


## Review Status

status: PASS_WITH_LIMITATIONS
reviewer: same-thread-audit-not-independent
reviewed_at: 2026-08-08

## Review Checklist

- Re-read `factory/brief.md`, `factory/plan.md`, and `factory/handoff.md`.
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
  1591 Pytest tests, and 90.16% total coverage.
- QA/QC, agent-stack, OEK constitution, privacy, accounting reconciliation, and
  the bounded OEK gap check pass without blockers.
- A real Ollama generation using the exact `qwen3:8b` model succeeds and
  preserves `ADVISORY_ONLY`, `execution_allowed=false`, and
  `LIVE_ORDER_BLOCKED` boundaries.

### Resolved P0 - Local Ollama startup race and duplicate ownership

- Shared PowerShell supervision now probes the real loopback API before process
  creation, recognizes any existing port-11434 listener, rejects wildcard or
  non-loopback listeners, uses bounded readiness retries, and exposes
  provider/listener ownership in health evidence.
- The verified obsolete provider was a child of the old Qwen prompter. It was
  stopped after parent/command verification; Ollama App remained untouched.
- The visible task was restarted with the new code. It reports `RUNNING`, exact
  model `qwen3:8b`, one `127.0.0.1:11434` listener, and one task-owned provider,
  `execution_allowed=false`, and `LIVE_ORDER_BLOCKED`.

### Completed - Read-only local Qwen workbench

- `python -m ai4binance.local_agent` provides bounded repo status, allowlisted
  search, allowlisted file reads, and latest-system-audit evidence to loopback
  Ollama exact model `qwen3:8b`.
- Absolute paths, traversal, secrets, runtime state, oversized files, hosted
  provider drift, model drift, malformed/truncated output, and missing safety
  stamps fail closed.
- Provider output is proposal-only. It cannot apply patches, run arbitrary
  commands, change configuration, or own trading/risk/wallet/order decisions.
- A real UTF-8 Turkish generation passed in 19.8 seconds with one provider
  attempt and a destination-verified report under
  `artifacts/local-qwen-workbench`.

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
by the factory workflow. `factory/state.md` must remain
`AWAITING_INDEPENDENT_REVIEW` until that separate review occurs.

The workbench is intentionally not full Codex capability parity. External app
connectors, web access, unrestricted shell, patch application, and autonomous
deployment remain outside this approved read-only slice.

## Verdict

`PASS_WITH_LIMITATIONS`

Trading and parameter-promotion status remains `RESEARCH_ONLY`; live eligibility
remains `LIVE_ORDER_BLOCKED`.

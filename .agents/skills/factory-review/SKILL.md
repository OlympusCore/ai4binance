---
name: factory-review
description: Use when reviewing completed AI4BINANCE factory work with fresh eyes by rereading the plan, rerunning proof commands, checking safety rails, and trying to break the result.
metadata:
  ai4binance.authority: advisory-only
  ai4binance.version: 1.0.0
  ai4binance.owner: QualityDepartmentManager
  ai4binance.trust_level: local
  ai4binance.last_reviewed: 2026-08-03
  ai4binance.trigger_examples: /factory-review; REVIEW.md; independent factory review
---

# Factory Review

Act as a fresh reviewer. Do not rely on the builder's confidence. Rebuild the
task context from artifacts and source files.

## Review Inputs

- `factory/BRIEF.md`.
- `factory/PLAN.md`.
- `factory/HANDOFF.md`.
- Changed files.
- Proof commands and outputs.
- Relevant source and tests.

## Review Steps

1. Confirm implementation matches the approved scope.
2. Re-run focused proof commands when practical.
3. Re-run the full quality gate when practical.
4. Search for missing degraded paths, stale state, weak tests, leaked authority,
   provider drift, secret exposure, and false proof.
5. Update `factory/REVIEW.md`.

## Required Verdicts

Use one of:

- `PASS`
- `PASS_WITH_LIMITATIONS`
- `NEEDS_REPAIR`
- `BLOCKED`
- `RESEARCH_ONLY`

For live trading, keep `LIVE_ORDER_BLOCKED` unless every live gate is explicitly
proven.

## Output

Lead with findings ordered by severity. Include file references, command
results, residual risk, and the final verdict.

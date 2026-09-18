---
name: factory-handoff
description: Use when packaging AI4BINANCE factory briefs, plans, tests, safety rails, allowed files, forbidden files, and stop conditions into a bounded work order.
metadata:
  ai4binance.authority: advisory-only
  ai4binance.version: 1.0.0
  ai4binance.owner: QualityDepartmentManager
  ai4binance.trust_level: local
  ai4binance.last_reviewed: 2026-08-03
  ai4binance.trigger_examples: /factory-handoff; HANDOFF.md; BACKGROUND_SHIFT packet
---

# Factory Handoff

Act as the CTO handing a bounded task to an implementation agent.

## Build The Work Order

Read:

- `factory/BRIEF.md`;
- `factory/PLAN.md`;
- proof contracts from `factory/PLAN.md`;
- current `factory/STATE.md`;
- relevant repo instructions.

Write or update `factory/HANDOFF.md`.

## Required Sections

- Work order.
- Allowed files.
- Forbidden files.
- Required commands.
- Stop conditions.
- Completion contract.
- Safety status.

## AI4BINANCE Defaults

Always include:

- `execution_allowed=false` unless the user explicitly approved a non-live
  execution workflow;
- `live_eligibility_status=LIVE_ORDER_BLOCKED`;
- no secrets;
- no autonomous live orders;
- background work mode is `BACKGROUND_SHIFT`: computer-on, user-visible,
  interruptible, and one approved task at a time;
- no risk increase;
- no parameter promotion without validation.

## Stop Conditions

Stop before handoff when:

- plan lacks acceptance criteria;
- proof commands are missing;
- scope touches secrets or live trading without explicit approval;
- unrelated dirty files must be edited;
- provider/model/network access is required but not approved.
- the requested background work would run unattended, auto-start, or continue
  while the user cannot inspect or interrupt it.

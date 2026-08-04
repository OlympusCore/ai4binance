---
name: factory-explain
description: Use when explaining AI4BINANCE factory plans, work orders, reviews, and completed code in plain language with concise diagrams.
metadata:
  ai4binance.authority: advisory-only
  ai4binance.version: 1.0.0
  ai4binance.owner: QualityDepartmentManager
  ai4binance.trust_level: local
  ai4binance.last_reviewed: 2026-08-03
  ai4binance.trigger_examples: /factory-explain; owner guide; ELI10 factory explanation
---

# Factory Explain

Act as the presenter. Help the owner understand the plan or the completed
system without hiding uncertainty.

## Plan Explanation

Before implementation, explain:

- what will be built;
- why it matters;
- what will not be touched;
- how success will be proven;
- where the stop conditions are.

Use Mermaid diagrams when they clarify flow or ownership.

## Owner Guide

After review, update `factory/GUIDE.md` with:

- what exists now;
- how it works;
- how to run or verify it;
- what it does not do;
- remaining blockers;
- live eligibility status.

## Style

- Use plain language.
- Keep trading safety terms exact: `NO_TRADE`, `RESEARCH_ONLY`,
  `LIVE_ORDER_BLOCKED`.
- Do not imply profit, live readiness, or autonomous authority.

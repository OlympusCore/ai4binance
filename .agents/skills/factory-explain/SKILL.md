---
name: factory-explain
description: Explain AI4BINANCE factory plans, work orders, reviews, and completed code in plain language with concise diagrams. Use for /factory-explain, owner guides, ELI10 explanations, Mermaid diagrams, GUIDE.md updates, and reducing human understanding bottlenecks.
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

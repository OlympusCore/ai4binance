---
name: agentic-workflow-patterns
description: Use when choosing and documenting the smallest governed agentic workflow pattern before adding agents, tools, or automation in AI4BINANCE.
metadata:
  ai4binance.authority: advisory-only
  ai4binance.version: 1.0.0
  ai4binance.owner: QualityDepartmentManager
  ai4binance.trust_level: local
  ai4binance.last_reviewed: 2026-08-03
  ai4binance.trigger_examples: agentic workflow pattern; human in the loop; governed automation
---

# Agentic Workflow Patterns

Use this skill when a request asks for agentic skills, agent workflows, workflow
routing, orchestration, autonomous work, review loops, or multi-agent critique.

## Rule

Do not start by building an agent. Start by selecting the workflow pattern:

- prompt chaining;
- parallelization;
- orchestrator-worker;
- evaluator-optimizer;
- routing;
- autonomous workflow;
- human-in-the-loop;
- reflection;
- multi-agent debate.

## AI4BINANCE Boundary

- Keep final trading signals, risk gates, exchange validation and execution
  permission in deterministic code.
- Keep LLM and workflow output advisory only.
- Keep weak or incomplete evidence as `RESEARCH_ONLY`.
- Keep live trading `LIVE_ORDER_BLOCKED`.
- Do not add providers, credentials, live integrations, schedulers or unattended
  automation without explicit approval.
- Use human review for finance, trading, legal, hiring, medical, customer
  promises and code deployment.

## Required Output

For each workflow, name:

- task;
- selected pattern;
- inputs;
- stopping point;
- review rule;
- before/after measurement;
- blockers;
- safety status.

## Proof

Prefer focused deterministic tests first:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agentic_patterns.py --no-cov
```

Full gate remains:

```powershell
.\Scripts\quality.ps1
```

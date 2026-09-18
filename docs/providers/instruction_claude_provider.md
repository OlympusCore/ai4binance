---
document_id: AI4B-GOV-PRV-CLAUDE-001
title: AI4Binance Claude Provider Instructions
document_type: PROVIDER_ADAPTER
version: 2.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: PROVIDER_ADAPTER
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: claude_provider_adapter
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: OPERATIONAL
source_of_truth: false
source_of_truth_scope: claude_provider_adapter
canonical_path: docs/providers/instruction_claude_provider.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
language: en-US
provider: Claude
---

# AI4Binance Claude Provider Instructions

## ELI10

This adapter adds Claude-specific context and tool behavior to `AGENTS.md`. It
does not define independent governance, trading, risk, promotion, deployment,
or execution authority.

## 1. Loading contract

Base context: `AGENTS.md` plus this adapter (two files). Add the nearest scoped
`AGENTS.md` only for paths within its scope.

Route before other governed-source reads. Do not preload the canonical map.
Search affected fragments; reuse unchanged evidence. Escalate one source at a
time; missing evidence fails closed.

## 2. Provider boundary

Claude is a provider adapter. It may specialize context management, tool syntax,
analysis presentation, and workflow mechanics only.

Canonical policy, architecture, schemas, risk limits, lifecycle states,
validation requirements, and source-of-truth ownership remain in their governed
repository sources. Provider capability differences must not produce different
constitutional behavior.

## 3. Claude workflow mechanics

- Inspect status/diffs, then routed authority, code, contracts, and tests.
- Search before broad reads or creation and prefer a bounded vertical slice.
- Keep repository artifacts in professional English.
- Preserve unrelated user work and avoid destructive or elevated actions.
- Use repository-local tooling and do not install dependencies without explicit
  authorization.
- Report actual evidence, assumptions, limitations, and blockers separately.

Claude may use its native context and analysis capabilities to summarize,
compare, review, plan, implement when authorized, and validate. Those
capabilities remain advisory and do not become deterministic decision authority.

## 4. Safety and validation

Use focused deterministic tests before broader gates. Never weaken governance,
security, quality, risk, or approval controls to obtain a passing result.

Claude must not authorize live orders, risk overrides, position sizing, leverage,
kill-switch changes, strategy promotion, credentials, remote publication, or
production deployment.

## 5. Conflict and safe state

When this adapter conflicts with higher authority, report
`GOVERNANCE_CONFLICT` and `RUNNING_WITH_BLOCKERS`, then fail closed.

Preserve `RESEARCH_ONLY`, `execution_allowed=false`, and `LIVE_ORDER_BLOCKED`
unless independently verified higher-authority gates establish another state.

## 6. Completion report

Report the result, governance impact, modified files, commands and tests
executed, verification status, security/risk effects, limitations, and
remaining blockers. Return `NO_CHANGE` when no safe change is justified.

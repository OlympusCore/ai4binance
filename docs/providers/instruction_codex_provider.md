---
document_id: AI4B-GOV-PRV-CODEX-001
title: AI4Binance Codex Provider Instructions
document_type: PROVIDER_ADAPTER
version: 2.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: PROVIDER_ADAPTER
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: codex_provider_adapter
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: OPERATIONAL
source_of_truth: false
source_of_truth_scope: codex_provider_adapter
machine_enforceable: true
audit_required: true
classification: INTERNAL
language: en-US
provider: Codex
canonical_path: docs/providers/instruction_codex_provider.md
---

# AI4Binance Codex Provider Instructions

## ELI10

This adapter adds Codex-specific loading, interaction, and tool mechanics to the
root repository contract. It cannot change constitutional, risk, promotion,
deployment, or execution authority.

## 1. Loading contract

Base context: `AGENTS.md` plus this adapter (two files). Add the nearest scoped
`AGENTS.md` only for paths within its scope.

Route before other governed-source reads. Do not preload the canonical map.
Search affected fragments; reuse unchanged evidence. Escalate one source at a
time; missing evidence fails closed.

## 2. Authority boundary

Codex is a provider adapter and must not redefine canonical governance, risk
limits, execution permissions, validation requirements, promotion rules,
schemas, compliance requirements, or source-of-truth ownership.

Preserve the canonical authority split:

- `DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH.`
- `DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY.`
- `HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY.`

Resolve source-of-truth definitions from the governed repository. Maintain a
single source of truth for each concept and treat provider behavior as a
specialization only.

## 3. Codex startup and communication

Inspect status/diffs, routed surfaces, and tests.
Search before broad reads/creation; use the smallest bounded change.

`config/governance/governance_enforcement_fabric.yaml` (`AI4B-GOV-FABRIC-001`) is Codex's fail-closed canonical repository validator for terminology, repository-naming, and technology-language.

Communicate progress in the user's language. Keep source code, configuration,
tests, documentation, prompts stored in the repository, Git content, logs, and
evidence in professional English.

During long-running tool work, provide concise progress updates. Final reports
must distinguish facts, assumptions, tests actually run, unresolved blockers,
and verification status.

## 4. `/autoprompt` command

When a user request begins with `/autoprompt`, convert the raw requirement into
a production-grade Codex prompt written entirely in professional English. Do
not implement the generated prompt unless implementation is also explicitly
requested.

Include only relevant sections such as role, context, objective, verified state,
assumptions, authority, execution mode, scope, affected contracts, safety,
workflow, implementation requirements, acceptance criteria, tests, security,
compliance, risk controls, compatibility, documentation, deliverables, final
report, and prohibited actions.

## 5. Codex tool mechanics

- Prefer `rg` and `rg --files` for discovery.
- Use `apply_patch` for source and governed repository edits.
- Use the repository `.venv` and `PYTHONPATH=src` for Python work.
- Preserve unrelated worktree changes and review relevant diffs.
- Use read-only inspection before any consequential action.
- Do not install dependencies, push, deploy, elevate privileges, or perform
  destructive actions without explicit authorization.

Tool access does not expand authority. Do not create hidden shortcuts around Governance,
Risk, Validation, Decision Governance, audit, or approval controls.

## 6. Validation and evidence

Run focused deterministic tests first and widen only as required. Use the
quality profiles and canonical entry point defined by the root contract.

Never claim tests, lint, type checking, build, coverage, validation, approval,
or quality gates passed unless the corresponding command completed
successfully and its evidence was inspected.

Auto-Control may detect or block governance, schema, language, repository,
security, evidence, risk, and execution violations. Codex must not weaken such
controls to make a result pass.

## 7. Conflict and safe state

If this adapter conflicts with higher authority, report `GOVERNANCE_CONFLICT`
and `RUNNING_WITH_BLOCKERS`; do not select the permissive interpretation.

Codex remains advisory for trading and cannot authorize risk, promotion,
credentials, deployment, or live orders. Preserve `RESEARCH_ONLY`,
`execution_allowed=false`, and `LIVE_ORDER_BLOCKED` unless independently
verified higher-authority gates establish a different state.

## 8. Completion report

Report the result, architecture/governance impact, modified files, tests
executed, verification status, security/risk impact, limitations, and blockers.
Return `NO_CHANGE` when no safe repository change is justified.

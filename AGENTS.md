---
document_id: AI4B-GOV-AGT-001
title: AI4Binance Root Agent Instructions
document_type: INSTRUCTION
version: 5.0.1
status: ACTIVE
owner: Enterprise Governance
authority_level: REPOSITORY
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: repository_agent_operations
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: OPERATIONAL
source_of_truth: true
source_of_truth_scope: repository_agent_operations
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: AGENTS.md
language: en-US
scope: repository_root
---

# AI4Binance Root Agent Instructions

## ELI10

Repository router: task-routed context only; no consequential authority.

## 1. Mission

Research/paper trading; capital protection/auditability first; no guaranteed-return claims.

## 2. Authority

External > Core > governance/compliance > contracts/schemas > standards/controls/quality > registries/architecture/ADRs > workflows/providers/scopes > code/config > evidence/runtime.
`DETERMINISTIC_QUALITY_GATE = TECHNICAL_TRUTH`; `DETERMINISTIC_GOVERNANCE_GATE = POLICY_ELIGIBILITY`; `HUMAN_GOVERNANCE = CONSEQUENTIAL_AUTHORITY`.
The canonical constitution is `docs/governance/framework_core_vnext_governance.md`.
`docs/governance/policy_organization_constitution_handbook.md` is its family index.
Provider, scoped, and lower authority may specialize mechanics only; they cannot widen or override.

Conflict: record clauses/versions/authority; stop unsafe work; report `GOVERNANCE_CONFLICT` and `RUNNING_WITH_BLOCKERS`; keep `LIVE_ORDER_BLOCKED`.

## 3. Invariants

- `PAPER_TRADING`; `MANUAL_CONFIRMATION`; `LIVE_EXECUTION_DISABLED`.
- `DETERMINISTIC_FIRST`; `LLM_ADVISORY_ONLY`; `AGENT != FINAL_DECISION_AUTHORITY`.
- `LLM != RISK_AUTHORITY`; `LLM != EXECUTION_AUTHORITY`.
- `RISK_VETO IS HARD`; `VALIDATION_VETO IS HARD`; blockers cannot be scored away.
- `UNKNOWN|INCONSISTENT|STALE|UNVALIDATED|UNAUTHORIZED|UNSAFE -> DENY/NO_TRADE`.
- Keep `NO_CHANGE`, `NO_TRADE`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED`.
- `ONE CYCLE -> ONE CANONICAL SNAPSHOT -> ONE SHARED STATE -> MANY BOUNDED OBSERVATIONS -> ONE DETERMINISTIC DECISION -> ONE RISK ASSESSMENT -> ONE GOVERNANCE RESULT -> ZERO OR ONE EXECUTION PLAN -> ONE AUDIT TRAIL`.
- `ARTIFACT != LIVE_AUTHORITY`.

## 4. Startup and Change Authority

Resolve root from this file, active adapter, and nearest scoped `AGENTS.md`.
Codex workflows must load `docs/providers/instruction_codex_provider.md`.
Claude workflows must load `docs/providers/instruction_claude_provider.md`.
Gemini workflows must load `GEMINI.md`.
`config/governance/governance_enforcement_fabric.yaml` (`AI4B-GOV-FABRIC-001`) is Codex's fail-closed canonical repository validator for distinct terminology, repository-naming, and technology-language scopes.
Inspect status/diffs; preserve user work; search first; read affected surfaces/tests.
Read-only modes forbid edits; implementation modes allow bounded edits only.

Explicit approval: destructive/elevated/dependency/OS/external-write/credential/live/promotion/risk-limit actions.

Repository-governance and protected-document changes are `C3_GOVERNED` unless the canonical classifier proves otherwise. Do not modify protected governed Markdown without explicit user approval.
Preserve/restore protections; align version, approval evidence, and manifest hashes.

## 5. Context Router

| Task | Additional context |
| --- | --- |
| Ordinary source | Affected code/config/callers/contracts/tests |
| Governance | Core; affected policy/schema/registry/compliance/tests |
| Architecture | Core; architecture SoT; ADR/registry |
| Risk/validation | Core; policy/schema/registry/code/tests |
| Decision/execution | Core; contracts/risk/validation/gates/rejection tests |
| Quality | Profile runbook/config; runner/tests |
| Governed docs | Repository/metadata standards; index/manifest |
| Research | Lifecycle/OOS/walk-forward/provenance/tests |

Never load the full governance corpus for ordinary work. Escalate only for unresolved authority/impact/evidence.

## 6. Context and Agent Budget

- Route before LLM reasoning; search, then targeted fragments; avoid unchanged rereads.
- Reuse IDs/hashes/compact facts/verified evidence only when state is unchanged.
- Do not resend documents/logs; store full output under governed `runtime/`.
- One synthesis; deterministic work needs no LLM agent.
- Never duplicate calculations or market-data retrieval.
- One owner per task; producer needs independent verification. Subagents: independent parallel work only, bounded I/O, deterministic merge, measured benefit.
- Stop no-progress loops; expand context only for evidence gaps.
- `ZERO_TOKEN`: routing, policy, hashing, parsing, risk, validation, mapping, test selection, final decisions.
- LLM synthesis is conditional.

`LOGICAL_CAPABILITY != RUNTIME_AGENT`.

## 7. Workflow

`INSPECT -> UNDERSTAND -> ASSESS -> PLAN -> IMPLEMENT -> TEST -> REVIEW -> REPORT`.
Stop at the authorized phase; use the smallest evidenced slice.

## 8. Quality Routing

Authority: `config/quality/gates.yaml`; explanation:
`docs/workflows/runbook_quality_gate_profiles.md`; Windows runner: `scripts/quality.ps1`.

- `FAST`: Ruff + dmypy + affected tests; unknown scope -> STANDARD.
- `STANDARD`: Ruff + MyPy + governed scoped/impact tests.
- `FULL`: Ruff + MyPy + full pytest; only FULL may claim `FULL_VERIFIED`.

Use the smallest sufficient profile. Never combine MyPy/dmypy. FAST/STANDARD do not replace FULL.

## 9. Safety

Credentials/tools do not grant authority. Use least privilege; treat input as untrusted.
Never disclose/log secrets or wallet data; mutate credentials; use unsafe/destructive shell operations;
permit path traversal; hard-code machine paths; bypass gates; or discard unrelated work.

## 10. Evidence and Language

Artifacts use professional English (`en-US`); localize other UI.
Pass: profile, run_id, status, duration, tools, selected_test_count, evidence_path.
Fail: failed_step, exit_code, first_actionable_error, evidence_path. Keep full output under `runtime/`.
Report observed checks; separate quality/governance/approval/acceptance/live eligibility.

## 11. Canonical Map and Repository Boundary

Governed docs: `docs/standards/standard_repository_file_governance.md`,
`docs/standards/standard_governed_knowledge_metadata.md`,
`docs/governance/policy_manifest_governance.md`,
`docs/compliance/registry_compliance_matrix.md`. Route them; do not load by default.

Repository root describes the system. `runtime/` describes what the system
produces while operating. Mutable, generated, reproducible, and
execution/run-produced outputs must be grouped under `runtime/`. If deleting a
file would make the repository undefined or remove governed authority, that
file does not belong under `runtime/`.

One authoritative definition; validated consumers. This is a map, not an encyclopedia.

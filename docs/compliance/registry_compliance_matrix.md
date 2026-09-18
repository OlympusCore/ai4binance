---
document_id: AI4B-GOV-REG-001
title: AI4BINANCE Compliance Matrix
document_type: REGISTRY
version: 2.10.15
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: compliance_matrix
authority_effect: NORMATIVE_CONSTRAINT
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/compliance/registry_compliance_matrix.md
---

# Compliance Matrix - ELI5

## ELI10

This document is like a checklist: is there code for a feature, is there a test,
Checks whether evidence exists and whether any gate is still missing before anyone says "done."
The actual completion status is visible.


Last review: **current local quality gate**

This document is not about "is there a file?" but about "is there code, is there test, is it dependent on real flow?"
Does the required external evidence exist?" questions are evaluated separately.

Canonical Core vNext governance and standards mapping source:
[`docs/governance/framework_core_vnext_governance.md`](/docs/governance/framework_core_vnext_governance.md).

No separate subsystem is created for external standards. The shared ontology chain is used:

```text
ExternalFramework
-> Requirement
-> Risk
-> Control
-> Implementation
-> Evidence
-> Test
-> Finding
-> Remediation
```

When capability status is interpreted, `MISSING` is never treated as `PASS`.

Canonical governance decision anchor:

```text
Docs are authority.
Validator is enforcement.
Quality gate is evidence.
Human governance is consequential authority.
Runtime is not source-of-truth.
LLM is not authority.
Scores cannot hide blockers.
LIVE remains blocked.
```

## Status Key

- **COMPLETED**: Code, test, and required application connection are available.
- **PARTIAL**: Secure base available; provider, real data proof, or end-to-end connection missing.
- **RESEARCH**: Calculation is present but no OOS/promotion proof.
- **NOT APPLIED**: Property not applied or intentionally closed for security reasons.

## AI4Binance vNext requirement convergence index

This is the canonical human-readable index for the approved vNext design-input
requirements. The detailed machine-readable enforcement mirror is
`config/governance/enforcement_inventory.yaml` under `requirement_traceability`.
The mirror may preserve or narrow a state to fail closed; it must not upgrade an
unverified requirement.

| Requirement | Canonical meaning / owner | Trace status | Conservative convergence state |
|---|---|---|---|
| RQ-001 | Safety defaults and fail-closed live boundary / Core Constitution | AUDIT_VERIFIED | SATISFIED |
| RQ-002 | One source of truth and authority / Enterprise Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-003 | Immutable snapshot and shared-state architecture / Architecture Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-004 | Deterministic decision chain / Decision Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-005 | Independent Risk and Validation hard vetoes / Core Constitution | AUDIT_VERIFIED | SATISFIED |
| RQ-006 | Governed contract and schema fabric / Contract Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-007 | Bounded agent architecture / Agent Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-008 | Advisory model gateway / Model Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-009 | Governed non-authoritative memory / Knowledge Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-010 | Event, journal, idempotency, and replay / Event Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-011 | Optional bounded GPU with CPU fallback / Compute Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-012 | Virtual market and paper execution / Research Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-013 | Research, OOS, and human-governed promotion lifecycle / Validation Governance | AUDIT_VERIFIED | BLOCKED_BY_OOS_PROMOTION_EVIDENCE |
| RQ-014 | Cold-path external intelligence and GitHub Radar / External Intelligence Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-015 | Security, privacy, and local-only sensitive data / Security Governance | AUDIT_VERIFIED | BLOCKED_BY_EXTERNAL_SECURITY_EVIDENCE |
| RQ-016 | Dependency-guarded architecture migration / Architecture Governance | AUDIT_VERIFIED | BLOCKED_BY_COMPATIBILITY_EVIDENCE |
| RQ-017 | Quality and evidence closure / Quality Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-018 | Documentation factual and lock alignment / Knowledge Governance | AUDIT_VERIFIED | SATISFIED |
| RQ-019 | No live authority / Core Constitution | AUDIT_VERIFIED | SATISFIED_LIVE_ORDER_BLOCKED |
| RQ-020 | No unnecessary dependency or service / Architecture Governance | AUDIT_VERIFIED | SATISFIED |

## Current platform matrix

| Capability | Code and test proof | Status | Remaining obstacle |
|---|---|---|---|
| Secure Spot defaults | `config.py`, `safety.py`, `test_config_reporting.py`, `test_safety.py` | COMPLETED | Live conscious closed |
| Immutable snapshot and shared agent contract | `schemas.py`, `test_schemas.py` | COMPLETED | — |
| Terminology, repository naming, and technology-language enforcement fabric | `docs/standards/standard_terminology_governance.md`, `docs/standards/standard_repository_naming_governance.md`, `docs/standards/standard_technology_language_ownership.md`, `config/governance/governance_enforcement_fabric.yaml`, the family projections and schemas, `docs/registries/registry_authority_graph.yaml`, `src/ai4binance/governance/governance_enforcement_fabric.py`, `src/ai4binance/governance/repository_validator.py`, and `tests/governance/terminology/test_governance_enforcement_fabric.py` | PARTIALLY_VERIFIED | Three L4 normative standards retain separate authority scopes and bind to one non-authoritative deterministic fabric. The authority graph records each standard, terminology projection, and shared fabric so declared impact traversal includes the closure. The repository validator remains the execution point; the fabric provides technical conformance evidence only and cannot grant policy eligibility, consequential change authority, promotion, or live execution. `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` remain unchanged. |
| Dependency-aware parallel orchestrator | `agents/orchestrator.py`, `agents/telemetry.py`, related tests | COMPLETED | Hard process-timeout only possible with isolated backend |
| Agent governance registry | `agents/catalog.py`, `agents/registry.py`, `test_agent_registry.py` | COMPLETED | No hard-gate promotion proof |
| Agentic workflow pattern catalog | `governance/agentic_patterns.py`, `.agents/skills/agentic-workflow-patterns`, `test_agentic_patterns.py` | COMPLETED | Pattern selection and plan contract exist; autonomous/live execution missing |
| AI orchestration and multi-agent orchestration pyramid framework | `docs/governance/framework_orchestration_ai_multi_agent.md`, `src/ai4binance/governance/agentic_patterns.py`, `.agents/skills/agentic-workflow-patterns/SKILL.md`, `tests/test_agentic_patterns.py`, `docs/registries/registry_agent_registry.md`, `docs/registries/registry_workflow_registry.md`, `docs/registries/registry_ai_system_inventory.md`, `docs/registries/registry_evidence_registry.md`, `docs/reports/governance/evidence_ai_orchestration_operational_readiness.md`, `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md`, `docs/reports/governance/evidence_ai_orchestration_risk_impact_records.md`, `docs/reports/governance/report_platform_blocker_closure_map.md`, `docs/reports/governance/report_repository_governance_findings.md` | COMPLETED | Governance logic, runtime pattern-selection tests, end-to-end orchestration KPI evidence, per-agent role-package review records, AIMS risk-impact records, blocker closure mapping, and repository governance findings are complete for report-only and advisory AI orchestration readiness. This does not grant autonomous execution, deployment, live trading, risk-limit changes, strategy promotion, or external certification; `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` remain preserved. |
| Enterprise holding governance | `enterprise/`, `docs/governance/policy_holding_governance.md`, `test_enterprise_*` | COMPLETED | General Manager/QAQC/work-order layer management and audit generation; execution permissions not granted |
| Agent lifecycle state machine | `enterprise/agent_lifecycle.py`, `test_enterprise_agent_lifecycle.py` | COMPLETED | Typed `IDLE` → `PERCEIVE` → `REASON` → `PLAN` → `ACT` → `OBSERVE` → `HUMAN_CHECK` → terminal flow exists; live permissions missing |
| Privacy boundary / `docs/archive/reference_local_computer_profile.md` | `privacy_boundary.py`, `enterprise/quality_audit.py`, `test_privacy_boundary.py`, `test_enterprise_quality_audit.py` | COMPLETED | Local computer profile is only usable with reference to `docs/archive/reference_local_computer_profile.md`; copying to another file generates QAQC blocker |
| QAQC system audit | `enterprise/quality_audit.py`, `cli/enterprise.py`, `test_enterprise_quality_audit.py` | COMPLETED | `quality-system-audit` report-only mode; `WRITTEN_APPROVAL_DOC_SYNC`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` are constants |
| OEK Constitution Authority Source, Compliance and Gap Audit | `docs/governance/policy_organization_constitution_handbook.md`, `enterprise/contracts.py`, `enterprise/prompt_intake.py`, `enterprise/oek_compliance.py`, `enterprise/quality_audit.py`, `cli/enterprise.py`, `test_enterprise_contracts.py`, `test_enterprise_prompt_intake.py`, `test_enterprise_quality_audit.py`, `test_cli.py` | COMPLETED | `BoardDirective` and GM prompt-order chain cannot be established without `OEK_AUTHORITY_SOURCE:docs/governance/policy_organization_constitution_handbook.md` and `OEK_CONSTITUTION_COMPLIANCE`; OEK entity/version/core principle/live-blocked boundary is checked; `oek-gap-analysis` agent/skill/workflow/config change manifests are linked to OEK controls; OEK alone does not grant production, risk, promotion, or live trading authority |
| EAACIE and central Audit Trigger Engine instructions | `docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md`, `docs/workflows/instruction_audit_trigger_engine.md`, `src/ai4binance/ops/continuous_assurance.py`, `src/ai4binance/ops/auto_audit_loop.py`, `tests/test_continuous_assurance.py`, `tests/test_auto_audit_loop.py` | COMPLETED | EAACIE is a continuous-assurance instruction and hybrid trigger instruction for event/risk/scheduled/anomaly/lifecycle, which are mutually dependent; runtime payload and auto-audit markdown output carry both instructions via `instruction_refs`; audit report-only remains, `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` are constants |
| Trust, Assurance & Governance Plane / TIAF-lite | `docs/governance/framework_trust_assurance_governance_plane.md`, `docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md`, `docs/workflows/instruction_audit_trigger_engine.md`, `src/ai4binance/trust/plane.py`, `src/ai4binance/ops/continuous_assurance.py`, `tests/test_trust_plane.py`, `tests/test_continuous_assurance.py` | COMPLETED | A separate `ai4binance.trust` plane has been established. 20 controls are categorized as P0/P1/P2; at runtime, `build_conditional_trust_plane_assessment()` generates local-active controls for P0 checks, while P1/P2 advanced layers are conditionally managed under `conditional_layers` with values of `NOT_REQUESTED`, `EVIDENCE_REQUIRED`, or `STAGED_RESEARCH_ONLY`. If there is no P1/P2 request or layer evidence, active control does not occur; if evidence is present, staged/research-only control occurs. Each `ContinuousAssurancePlan` payload carries `AI4BINANCE_TIAF_LITE` under `governance_plane.framework=AI4BINANCE_TRUST_ASSURANCE_GOVERNANCE_PLANE`, along with decision provenance, policy-as-code, uncertainty/abstention, semantic contracts, and evidence-graph-lite; the invariants `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` are preserved |
| ISO/IEC 42001 AIMS documentation baseline | `docs/governance/policy_ai_management_system_scope.md`, `docs/registries/registry_ai_system_inventory.md`, `docs/registries/registry_evidence_registry.md`, `docs/compliance/matrix_iso_42001_aims_crosswalk.md`, `docs/compliance/statement_of_applicability_iso_42001.md`, `docs/workflows/procedure_ai_risk_impact_assessment.md`, `docs/workflows/procedure_aims_nonconformity_corrective_action.md`, `docs/reports/governance/report_repository_layer_file_inventory.md`, `docs/reports/governance/report_platform_blocker_closure_map.md`, `docs/reports/governance/report_repository_governance_findings.md`, `docs/reports/governance/evidence_ai_orchestration_operational_readiness.md`, `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md`, `docs/reports/governance/evidence_ai_orchestration_risk_impact_records.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md`, `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md`, `docs/reports/governance/evidence_aims_provider_control_review.md`, `docs/reports/governance/evidence_aims_internal_audit_schedule.md`, `docs/reports/governance/evidence_aims_management_review_minutes.md`, `docs/reports/governance/evidence_aims_capa_records.md` | COMPLETED | The internal AIMS documentation baseline now includes scope, interested parties, AI system inventory, evidence registry, ISO/IEC 42001 crosswalk, SoA, risk and impact procedures, per-system risk-impact records, provider-control review, internal audit schedule, management review minutes, CAPA records, repository layer inventory, blocker closure mapping, repository governance findings, and quality evidence links. This is not a certification claim and does not grant autonomous execution, deployment, live trading, risk-limit changes, or strategy promotion; `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` are preserved |
| Core vNext digital company / LOOPS / Web Intelligence Radar | `docs/governance/framework_core_vnext_governance.md`, `docs/architecture/framework_external_intelligence_evidence_fabric.md`, `src/ai4binance/governance/framework.py`, `tests/test_governance_framework_v2.py` | COMPLETED | Pyramid of authority model, digital company operating model, Web Intelligence Radar, and LOOPS self-improvement contract have been formalized. All remain research/advisory-only; they do not guarantee profit, do not generate execution authority, and uphold the `LIVE_ORDER_BLOCKED` and `NO_TRADE` boundaries. |
| Logical Architecture Registry enforcement mirror | `docs/registries/registry_logical_architecture.yaml`, `schemas/architecture/logical_component.schema.json`, `schemas/architecture/logical_relation.schema.json`, `schemas/architecture/logical_architecture.schema.json`, `src/ai4binance/governance/architecture/__init__.py`, `src/ai4binance/governance/architecture/model.py`, `src/ai4binance/governance/architecture/loader.py`, `src/ai4binance/governance/architecture/graph.py`, `src/ai4binance/ops/kaizen_quality.py`, `tests/governance/architecture/test_logical_architecture_registry.py`, `tests/test_kaizen_quality.py`, `docs/reports/governance/report_logical_architecture_registry.md` | PARTIAL | The registry is a local schema-validated enforcement mirror for declared components and typed relations. The loader now also performs bounded static runtime-conformance validation for the scoped decision chain: one canonical `TradeDecision` owner, an exact `GovernedDecision = TradeDecision` compatibility alias, one registered Decision Governance producer, and mandatory Risk and Validation handoff references. It rejects side effects and decision, risk-override, validation-override, source-of-truth, and execution authority. Broader post-DGE Policy, TradePlan, Execution Gate, and migration compatibility proof remain separate governed slices; `RQ-016`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` remain unchanged. |
| Decision candidate to trade decision governance chain | `docs/governance/framework_core_vnext_governance.md`, `src/ai4binance/governance/framework.py`, `src/ai4binance/governance/dge_models.py`, `src/ai4binance/governance/dge_engine.py`, `src/ai4binance/governance/rules.py`, `src/ai4binance/governance/adapters.py`, `src/ai4binance/governance/replay.py`, `src/ai4binance/governance/shadow.py`, `tests/test_governance_framework_v2.py`, `tests/test_dge_models.py`, `tests/test_dge_engine.py`, `tests/test_dge_recovery_replay_shadow.py`, `tests/governance/architecture/test_logical_architecture_registry.py` | PARTIAL | `RR-007` requires `DeterministicCore -> DecisionCandidate`; `RR-008`, `RR-021`, and `RR-022` independently require the Risk, Validation, and Decision Governance links before the post-DGE `TradeDecision` exists. `DgeGovernanceContext.validation_approved` is fail-closed by default, `DGE_VALIDATION_APPROVED` is a hard rule, replay preserves the field with a fail-closed legacy default, and mutation-style conformance tests reject missing Risk or Validation handoffs and alternate final-decision producers. `DgeTradeCandidate` and `GovernedDecision` remain compatibility aliases and cannot act as parallel semantic owners. The chain neither authorizes TradePlan or Execution nor changes promotion; broader post-DGE convergence remains separate, and `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` remain mandatory. |
| Virtual Market DGE application boundary | `docs/governance/framework_decision_governance_engine.md`, `src/ai4binance/core/contracts/virtual_governance.py`, `src/ai4binance/application/research.py`, `src/ai4binance/governance/adapters.py`, `src/ai4binance/governance/dge_engine.py`, `src/ai4binance/governance/rules.py`, `src/ai4binance/governance/replay.py`, `src/ai4binance/governance/shadow.py`, `src/ai4binance/research/virtual_runtime_request.py`, `src/ai4binance/research_runtime.py`, `tests/test_research_application.py`, `tests/test_dge_recovery_replay_shadow.py` | PARTIAL | `VirtualGovernanceResult` is the dependency-neutral result contract; the application layer owns only the evaluator port, `VirtualMarketDgeAdapter` owns deterministic candidate/context conversion and canonical DGE invocation, and `research_runtime.py` binds the concrete adapter at the composition boundary. The adapter derives the independent validation handoff from the validated analysis result; recovery input remains fail-closed when no independent validation result exists. Only `APPROVED_PAPER_ONLY` without DGE blockers can enter bounded Virtual Market simulation. This route reuses canonical virtual execution and accounting, remains fail-closed, and never grants live authority. Fresh FULL evidence and distinct C3 approval replay remain required; `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` are mandatory. |
| MCP Gateway policy route | `src/ai4binance/governance/mcp_gateway.py`, `src/ai4binance/governance/tool_policy.py`, `tests/test_governance_tool_gateway.py`, `docs/contracts/interface_contract_read_only_evidence_mcp.md` | COMPLETED | Agent -> MCP shortcut is disabled. Canonical route is `Agent -> Tool Policy -> Authorization -> MCP Gateway -> Tool`; Filesystem/GitHub/PostgreSQL/Research/future Binance READ-ONLY surfaces are consolidated under the default-deny contract. `filesystem.delete`, `shell.admin`, `exchange.place_order` remain denied; trading/live authority is not generated. |
| Constitutional change control | `src/ai4binance/governance/framework.py`, `src/ai4binance/governance/gate.py`, `src/ai4binance/governance/lean.py`, `src/ai4binance/governance_primitives.py`, `tests/test_governance_framework_v2.py`, `tests/test_governance_gate.py`, `tests/test_governance_primitives.py`, `docs/governance/framework_core_vnext_governance.md`, `docs/governance/instruction_core_custom_instructions.md`, `AGENTS.md`, `docs/providers/instruction_codex_provider.md`, `docs/registries/registry_documentation_index.md`, `config/governance/governed_document_lock_manifest.json` | COMPLETED | Constitutional authority is split into three primitives: `DETERMINISTIC_QUALITY_GATE=TECHNICAL_TRUTH`, `DETERMINISTIC_GOVERNANCE_GATE=POLICY_ELIGIBILITY`, and `HUMAN_GOVERNANCE=CONSEQUENTIAL_AUTHORITY`. `risk-tiered human governance` applies only to consequential changes. `src/ai4binance/governance_primitives.py` is the canonical lifecycle and authority primitive surface, and `src/ai4binance/governance/gate.py` plus `src/ai4binance/governance/lean.py` consume that same first-class lifecycle primitive across deterministic quality evidence, governance eligibility, approval-verification payloads, and poka-yoke gate checks. `approval_verification` is a hard veto, not an informational check: if the approval packet is missing, unauthorized, expired, revoked, scope-mismatched, evidence-mismatched, lifecycle-definition-mismatched, authority-family-mismatched, or blocker-tainted, consequential transitions remain vetoed and `LIVE_ORDER_BLOCKED` stays true. `C2_BEHAVIORAL` changes require an ELI10-backed `Approval Packet`; `C3_GOVERNED` changes require explicit review of the relevant policy/instructions plus double approval and same-diff constitution sync; `C4_CONSEQUENTIAL` changes require explicit high-assurance approval. Code-constitution conflict is not considered complete. |
| Governance alignment / loose-code audit | `AGENTS.md`, `src/ai4binance/governance/audit.py`, `src/ai4binance/governance/constitution_sync.py`, `src/ai4binance/governance/gate.py`, `src/ai4binance/governance/lean.py`, `src/ai4binance/governance_primitives.py`, `src/ai4binance/ops/repository_cleanup_audit.py`, `src/ai4binance/storage/jsonl.py`, `tests/test_dge_recovery_replay_shadow.py`, `tests/test_governance_constitution_sync.py`, `tests/test_governance_gate.py`, `tests/test_governance_primitives.py`, `tests/test_repository_cleanup_audit.py`, `tests/test_docs_hygiene.py`, `tests/test_kaizen_quality.py`, `tests/test_quality_gate_profiles.py`, `tests/test_storage.py`, `scripts/quality.ps1`, `config/quality/gates.yaml`, `config/governance/governed_document_lock_manifest.json`, `runtime/artifacts/quality/gate/approval_record_latest.json`, `runtime/artifacts/quality/gate/latest.json` | COMPLETED | Core documentation, root `AGENTS.md`, Custom Instructions, Codex, and the compliance matrix must carry the same `TECHNICAL_TRUTH` / `POLICY_ELIGIBILITY` / `CONSEQUENTIAL_AUTHORITY` agreement. A mismatch across core/root/custom/codex/compliance appears as `CONSTITUTION_FAMILY_MISMATCH`. An empty-source-file change that does not carry test, compliance, or written rule evidence results in `RUNNING_WITH_BLOCKERS`. Governed cleanup audit registry records must jointly display source, test, compliance matrix, and core documentation evidence, plus written owner approval lineage when governed Markdown changes. The request "Expand the scope of governance" requires an aggressive yet realistic gap analysis using secure tools, current CPU/RAM/GPU capacity, extensive testing, and parallel read-only analysis. Capability OOS/operational evidence gaps remain visible as `RESEARCH_ONLY` / `PARTIAL` / `MISSING`. Full technical quality evidence does not produce the claim COMPLETE unless the current quality evidence carries `TECHNICAL_QUALITY_PASS`, `pytest_pass_count`, `coverage_percent`, and `coverage_source`, and the same evidence envelope reports `full_assurance_status=FULL_ASSURANCE_GREEN`. The approval loader fallback consumes `runtime/artifacts/quality/gate/approval_record_latest.json` as the first-class approval artifact for the same scope/evidence envelope, binds `evidence_hash`, `authority_family_sha256`, and `lifecycle_definition_sha256`, and never downgrades to lower-authority defaults; if approval verification fails, the same envelope must remain `RUNNING_WITH_BLOCKERS`, `consequential_change_allowed=false`, and `LIVE_ORDER_BLOCKED`. Governance and replay-ready DGE decision journals now use the same first-class tamper-evident JSONL audit primitive with durable write-through, read-back verification, and fail-closed chain validation before append; coverage rate cannot be inferred from outside full quality_gate evidence. Human governance is consequential authority, not generic bureaucracy; `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` are constants. |
| Universal governed-object enforcement fabric | `docs/standards/standard_governed_object_enforcement.md`, `src/ai4binance/governance/enforcement/__init__.py`, `src/ai4binance/governance/enforcement/contracts.py`, `src/ai4binance/governance/enforcement/engine.py`, `src/ai4binance/governance/enforcement/registry.py`, `src/ai4binance/governance/enforcement/adapters.py`, `src/ai4binance/governance/enforcement/inventory.py`, `config/governance/enforcement_profiles.yaml`, `config/governance/enforcement_inventory.yaml`, `tests/test_governed_object_enforcement.py` | COMPLETED | The governed-object enforcement capability now exposes one shared `GovernedObjectEnvelope -> EnforcementRequest -> EnforcementDecision` contract, deterministic gate ordering, profile coverage checks, adapter reuse for repository/governed knowledge, and a machine-readable inventory of consequential entrypoints. Every consequential inventory entrypoint is now classified as either canonical `ROUTED` or explicit fail-closed `BLOCKED`, `ADAPTER_REQUIRED` and `REPORT_ONLY` exit gaps have been removed from the canonical inventory, and routed consequential paths do not retain a documented bypass route. Lower-level helper surfaces may still exist as implementation primitives, but they are non-authoritative for promotion or execution claims unless their inventory entrypoint is `ROUTED`. `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` remain unchanged. |
| Repository & File Governance Standard | `docs/standards/standard_repository_file_governance.md`, `src/ai4binance/governance/repository_validator.py`, `tests/test_repository_validator.py`, `tests/test_artifact_hygiene_scripts.py`, `scripts/quality.ps1` | COMPLETED | The `AI4B-GOV-REPO-001` standard has been transitioned to a permanent governance standard. The file/folder structure is not a one-time Codex cleanup decision; it is continuously enforced using the triple of `RepositoryPolicy + RepositoryArtifact schema + deterministic repository_validator`. The validator operates in report-only and fail-closed modes; it makes visible findings such as unknown top-level paths, unsafe Python naming, source filename versioning, source/runtime mixing, generated artifacts under src, and unapproved absolute paths. It cannot mitigate health score hard blockers; `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` are constants. |
| Documentation & Knowledge Governance Standard | `AGENTS.md`, `docs/providers/instruction_codex_provider.md`, `docs/governance/instruction_core_custom_instructions.md`, `docs/governance/framework_core_vnext_governance.md`, `docs/compliance/registry_compliance_matrix.md`, `docs/standards/standard_documentation_knowledge_governance.md`, `docs/controls/control_repository_validation_rules.md`, `src/ai4binance/governance/repository_validator.py`, `tests/test_repository_validator.py`, `tests/test_docs_hygiene.py`, `tests/test_governance_constitution_sync.py`, `scripts/quality.ps1` | COMPLETED | The `AI4B-GOV-DKG-001` standard has been transitioned to the active knowledge-governance standard. Critical system knowledge is not free Markdown; core/root/custom/codex/compliance and active standards carry `GovernedKnowledgeObject` metadata. The `RepositoryPolicy + RepositoryArtifact schema + deterministic repository_validator` chain enforces full quality gate within. Missing/broken document_id, semver, lifecycle, authority_level, content_role, owner, source_of_truth, duplicate knowledge_id, duplicate active source-of-truth concept, or lower-authority reuse of an active higher-authority `authority_scope` generates `RUNNING_WITH_BLOCKERS`. The validator now resolves concept ownership by `authority_scope`, emits `KNOWLEDGE_AUTHORITY_OVERRIDE_CONFLICT` when a lower layer attempts to weaken/contradict/override the higher owner scope, and allows operational specialization only through a narrower derived `authority_scope` plus matching derived `source_of_truth_scope`; governed repository/file standards and machine governance contracts are locked to professional English (`en-US`) and language drift in those controlled surfaces is `NON_CODE_CONTENT_LANGUAGE_VIOLATION`; `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED` remain constant. |
| EAACIE Security Core, weekly deep audit and security assurance proof | `docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md`, `docs/workflows/instruction_audit_trigger_engine.md`, `src/ai4binance/ops/continuous_assurance.py`, `src/ai4binance/ops/auto_audit_loop.py`, `src/ai4binance/ops/security_assurance.py`, `src/ai4binance/cli.py`, `src/ai4binance/cli/commands.py`, `tests/test_continuous_assurance.py`, `tests/test_auto_audit_loop.py`, `tests/test_security_assurance.py` | COMPLETED | Eight security domains, eight event/schedule triggers, default-on control profile, policy-typed domain routing, human review, and Auto-Audit daily-quick payload have been applied. `security-weekly-deep-audit` generates SBOM-lite, validates CVE/advisory evidence file, checks MFA provider attestation, backup/restore proof, external immutable/WORM storage proof, and weekly CLI scheduler integration. It does not generate a PASS claim if external evidence is missing; it fails-closed with blockers such as `CVE_ADVISORY_SOURCE_MISSING`, `MFA_PROVIDER_ATTESTATION_MISSING`, `RESTORE_TEST_EVIDENCE_MISSING`, or `WORM_STORAGE_EVIDENCE_MISSING` |
| MultiOps control plane | `multiops/`, `enterprise/multiops_control.py`, `ops/jobs.py`, `tests/test_agent_runtime_governance.py`, `tests/test_enterprise_multiops_control.py` | COMPLETED | AIOps/MLOps/LLMOps/RAGOps/AgentOps/DataOps/DevSecOps/TradeOps typed registry exists and unattended runner admission now binds the runner manifest, capability manifest, authority ceiling, side-effect allowlist, universal enforcement, run card, persistent evidence, and audit record together in a fail-closed report-only chain. `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` remain preserved, and scheduled execution still has no live-order authority. |
| Agent skills governance | `skills/`, `governance/supply_chain.py`, `docs/governance/policy_skills_governance.md`, `test_skill_linter.py` | COMPLETED | External skill/tool declaration requires quarantine and human review; no live execution |
| Public Spot REST acquisition | `exchange/client.py`, `data/acquisition.py`, related tests | COMPLETED | Not WebSocket streaming |
| Binance Vision historical ingestion | `data/binance_vision.py`, `test_binand_vision.py` | COMPLETED | Long-term dataset really download is an operator task |
| Binance Vision integrity/security | SHA-256, host allowlist, HTTPS, bounded response | COMPLETED | Upstream accessibility is an external dependency |
| Read-only private account reader | `exchange/private.py`, `portfolio/wallet.py`, `application/runtime.py` | COMPLETED | `secrets/bnc.env` allowlist loader, narrow ACL, and real Spot/USD-M GET smoke proof exist; no write permissions |
| Spot inventory and SELL semantics | `domain.py`, `risk.py`, wallet capture tests | PARTIAL | Real account open-order reconciliation proof is required |
| Rebalancing proposal agent | — | MISSING | Wallet, target allocation and human approval workflow required |
| Core technical indicators | `indicators.py`, `agents/technical.py`, related tests | RESEARCH | Multi-mode OOS promotion is required |
| Market Outlook Intelligent Engine | `outlook/`, `application/research.py`, `test_market_outlook.py` | PARTIAL | Real macro calendar/news provider and full TPO/composite auction profile are required |
| Advanced technical agents | `agents/advanced.py`, `test_advanced_agents.py` | RESEARCH | Some are proxy/diagnostic; contextual statistics missing |
| Trend events and cross management | `agents/trend_events.py`, `test_trend_events_agent.py` | RESEARCH | OOS promotion required |
| PriceAction SUCCESS/PARTIAL agreement | `schemas.py`, `strategies/price_action.py`, orchestrator integration test | COMPLETED | Setup edge proof also required |
| Strategy registry | `strategies/registry.py`, `strategies/compression.py`, `strategies/regime_playbooks.py` | PARTIAL | 10/20 playbook calculations generated; new candidates wait OOS |
| Candidate arbitration | `strategies/arbitration.py`, `test_stage_governance.py` | COMPLETED | Portfolio-wide correlation optimization missing |
| WHALE-FUSION | `whale_fusion/`, application and integration tests | RESEARCH | Provider envelope/replay provenance-freshness-finality gate exists; real provider and OOS proof missing |
| WHALE-FUSION → Strategy interaction | bounded supplementary ±5 modifier, `test_stage_governance.py` | COMPLETED | Cannot act as standalone trigger/hard-gate |
| Confluence correlation governance | `agents/specialists.py`, `test_agents.py` | COMPLETED | OOS weight calibration missing |
| RiskEngine and Binance filters | `risk.py`, `exchange/filters.py` | COMPLETED | Does not approve without real wallet context |
| First 5 candidates risk assessment | `RiskEngine.evaluate_many`, RiskAgent metadata tests | COMPLETED | Total portfolio risk distribution partial |
| Paper execution and lifecycle | `execution/`, paper/lifecycle tests | COMPLETED | Exchange-like persistent order state machine partial |
| Backtest realism checks | `backtest/`, realism and robustness tests | COMPLETED | Real long-term BTCUSDT validation report is missing in the repository |
| Look-ahead / recursive / lineage integrity | `validation/integrity.py`, `test_validation_integrity.py` | COMPLETED | Should be run for every feature family in the real artifact flow |
| Walk-forward and OOS | `validation/`, statistical evidence, `test_walk_forward.py` | COMPLETED | Real multi-regime promotion artifact is missing |
| Purge/embargo and overfit statistics | `validation/overfit.py`, walk-forward config, related tests | COMPLETED | Promotion pipeline mandatory connection and real data proof required |
| Tuning and sensitivity | `tuning/`, tuning governance tests | COMPLETED | Dataset revision exists; Optuna is only optional isolated benchmark and promotion unauthorized |
| Promotion Board → Strategy Registry | `tuning/promotion.py`, `test_tuning_governance.py` | COMPLETED | Only PAPER_APPROVED; live permission missing |
| Controlled learning engine | `learning/`, `application/learning_loop.py`, `tests/test_wallet_learning.py` | COMPLETED | Controlled learning remains advisory-only. `LearningSummary`, `ProfitabilityOptimizationLoop`, `ProfitabilityExperiment`, and `ExperimentCandidate` now carry canonical `application_state=NOT_APPLIED` plus explicit `promotion_evidence_required=true` and `closure_evidence_required=true`, so the engine may generate lessons and improvement candidates but cannot claim that an improvement was applied without separate promotion and closure evidence. It cannot change production parameters, execution authority, or risk limits. |
| Learning application wiring | `application/learning_loop.py`, `application/research.py` | COMPLETED | Default is closed; must be explicitly configured |
| Append-only audit and secret redaction | `storage/jsonl.py`, `learning/storage.py`, `tests/test_storage.py`, `tests/test_wallet_learning.py` | COMPLETED | Append-only JSONL audit records use secret redaction, destination read-back verification, and an optional tamper-evident hash chain. Consequential governance and learning audit writers use the sealed mode with durable write-through and fail-closed chain validation; external WORM/immutable retention remains a separate control and centralized retention/rotation policy is still missing. |
| Deterministic event/order replay | `events/journal.py`, `execution/order_state.py`, `test_event_journal.py` | COMPLETED | Startup replay wiring now opens the durable journal on runtime start and surfaces restart evidence without granting execution authority |
| Connector readiness | `exchange/readiness.py`, runtime smoke test, `test_connector_stream_readiness.py` | PARTIAL | Real private GET connection is validated; continuous WebSocket/session lifecycle is missing |
| Public stream recovery | `exchange/stream_state.py`, `exchange/public_stream.py`, related tests | PARTIAL | Official kline/parser/lifecycle contract is ready; real WebSocket/REST runtime adapter is missing |
| Paper restart reconciliation | `execution/recovery.py`, `test_paper_recovery_risk_flow.py` | PARTIAL | Journal recovery is ready; real exchange snapshot provider is not connected |
| Risk-flow circuit breakers | `portfolio/risk_flow.py`, related tests | COMPLETED | Proposal-only; does not grant live permissions |
| Governed research radar | `research_catalog.py`, `test_research_catalog.py` | COMPLETED | External candidates' revision/license/reproduction proof should also be generated |
| External skill supply-chain gate | `governance/supply_chain.py`, governance tests | COMPLETED | Pinned commit/hash/license scan is required for every real candidate |
| Development assurance run card and authority resolution API | `src/ai4binance/governance/development.py`, `src/ai4binance/governance/__init__.py`, `src/ai4binance/governance/authority_resolution.py`, `tests/test_governance_hardening.py`, `tests/test_authority_resolution.py` | COMPLETED | Atomic persistence and append-only audit wiring now exist for development run cards. The exported authority resolver deterministically selects one declared active source of truth and fails closed for duplicate, missing, or ambiguous authority; it cannot grant execution authority. |
| Governed lesson lifecycle | `learning/governance.py`, `learning/lifecycle.py`, `application/learning_loop.py`, `tests/test_stage_governance.py` | COMPLETED | The local worker persists staged lessons and tamper-evident audit records, accepts only explicit human-governed transition requests, and expires nonterminal lessons deterministically. It cannot originate approval, execution, risk, parameter, promotion, or live-order authority. |
| Capability-bounded jobs | `ops/jobs.py`, `enterprise/multiops_control.py`, nightly manifest and admission tests, `tests/test_agent_runtime_governance.py`, `tests/test_enterprise_multiops_control.py` | COMPLETED | Admission is now bound to every unattended runner through the canonical manifest chain and persistent evidence surface. The runner remains report-only, `execution_allowed=false`, `RESEARCH_ONLY`, and `LIVE_ORDER_BLOCKED` stay unchanged, and no live execution authority is granted. |
| Advisory fixture evaluation | `agents/evaluation.py`, `local_agent/advisory_fixture.py`, `local_agent/advisory_harness.py`, `local_agent/advisory_runner.py`, `local_agent/advisory_evidence.py`, `ops/jobs.py`, `tests/test_agent_runtime_governance.py`, `tests/test_local_qwen_workbench.py` | PARTIAL | A redacted, bounded fixture runner is attached through an injected advisory-provider contract. The loopback adapter verifies the prompt hash, rejects empty or truncated responses, and fails closed on unavailable or invalid provider responses. A sequential in-memory harness preserves caller order, caps each batch at 32 fixtures, and blocks the entire batch on any failed fixture. Its singleton, network- and secret-denied `RESEARCH_ONLY` admission manifest is bound to a manual runner that calls only the injected loopback provider after admission. When explicitly configured with the local writer, the runner atomically persists both admitted and admission-blocked redacted outcomes with tamper-evident local audit records; writer failures are not suppressed. No provider or continuous worker is configured by default; real provider deployment and promotion proof remain separate. |
| Read-only Market Outlook DAG | `governance/workflow.py`, runtime governance tests | COMPLETED | No visualization UI; graph processing permission not granted |
| Visual sidecar security gate | `governance/sidecar.py`, runtime governance tests | COMPLETED | Langflow not installed/launched; separate explicit permission and pinned image required |
| Performance regression gate | `ops/performance.py`, `test_performance_guard.py` | COMPLETED | Only compares same environment metrics; external technology benchmarks expected |
| Exchange resilience gate | `exchange/resilience.py`, relevant tests | COMPLETED | No continuous WebSocket runtime |
| Open-order reconciliation | `portfolio/reconciliation.py`, relevant tests | PARTIAL | Real exchange order snapshot wiring required |
| Portfolio risk budget | `portfolio/risk_budget.py`, `portfolio/rebalancing.py`, `portfolio/bucket_state.py`, `portfolio/correlation.py`, relevant tests | PARTIAL | Correlation/HHI diagnostics are ready; durable bucket-state persistence now exists, but multi-symbol portfolio backtest proof is still missing |
| Advisory Agent v2 | `agents/advisory.py`, `test_advisory_v2.py` | COMPLETED | Provider/LLM call is explicitly separated; signal/execution permission missing |
| Research run card / hypothesis / decay | `research_governance.py`, relevant tests | COMPLETED | Real long-term artifact flow operator usage required |
| News/context provider ingestion | `market_context.py`, application wiring, relevant tests | PARTIAL | Real provider selection/adapter and freshness SLA required |
| Crew/Local LLM/RAG process plan | `governance/crew.py`, `rag.py`, `local_agent/advisory_harness.py`, `local_agent/advisory_runner.py`, `ops/jobs.py`, relevant tests | PARTIAL | Stdlib index, loopback provider runner, HTML UI, bounded local-only batch evaluation harness, research-only runner admission manifest, and an on-demand admitted local runner are available; continuous worker and provider deployment remain separate. |
| CUDA and GPU resource usage policy | `docs/governance/policy_cuda_gpu_resource_usage.md`, `docs/registries/registry_gpu_compute_policy.md`, `src/ai4binance/config.py`, `src/ai4binance/enterprise/gpu.py`, `src/ai4binance/enterprise/resources.py`, `src/ai4binance/backtest/runtime_economics.py`, `src/ai4binance/cli/status.py`, `src/ai4binance/cli/voice.py`, `src/ai4binance/cli/commands.py`, `src/ai4binance/cli/output.py`, `src/ai4binance/learning/model_adaptation.py`, `tests/test_cuda_gpu_resource_usage_policy.py`, `tests/test_gpu_compute_governor.py`, `tests/test_model_adaptation_gpu_governance.py`, `tests/test_config_reporting.py`, `tests/test_enterprise_resources.py`, `tests/test_backtest_runtime_economics.py`, `tests/test_cli.py` | COMPLETED | CPU default remains canonical; CUDA is optional; GPU access is lease-governed; LLM inference and training stay mutually exclusive; backtest runtime economics stay profile-driven and fail-closed; memory telemetry and VRAM headroom are required before GPU promotion. |
| Experiment sandbox | `sandbox.py`, AST and backend capability tests | PARTIAL | Real Docker/OS isolation backend is required |
| Optional security scan | `security_scan.py`, evidence-first adapter tests | PARTIAL | Pinned Strix setup and no separate authorized CI job |
| Ed25519 WebSocket `session.logon` | `exchange/ws_api.py`, `execution/live_spot.py`, `test_ed25519_ws_live.py` | PARTIAL | Signature/session/read/order methods are ready; real testnet auth, reconnect soak, and subscription lifecycle are missing |
| Live Spot order adapter | `execution/live_spot.py`, `execution/live_spot_adapter.py`, `test_ed25519_ws_live.py` | PARTIAL | Adapter shell exists, but real testnet auth and end-to-end live write proof remain missing |

## Current Comparison of Two Past Projects

### Those Remaining from the First Quality/Spot-Native Work

- Python 3.14.7, Ruff, MyPy, Pytest, and secure defaults are being preserved.
- The single source of dependencies is `pyproject.toml`; `requirements.txt` for editable extras
It remains as the redirection.
- Futures data is only available in the WHALE-FUSION supplementary research channel;
  Does not manage spot order semantics.
- The old "127 tests and low coverage" result is outdated.

### Gaps closed after staged performance/stability study

- Immutable snapshot, shared `AgentResult`, fail-closed live gate, public data,
  technical agents, candidate/risk, paper lifecycle, backtest, walk-forward,
  tuning, promotion, WHALE-FUSION, and controlled-learning components were added.
- Candidate arbitration, PriceAction `SUCCESS/PARTIAL` acceptance, initial 5 candidates risk
  evaluation, and connection to Promotion Board/Strategy Registry were implemented.
- Quality script runs fail-fast; format, lint, type, test, and Bandit gates are present.
- Permanent event journal, stream gap/backfill state machine, paper restart recovery,
  risk-flow circuit breaker, collaborative research radar, and environment-dependent performance
  regression gate were added.

## Unfinished Major Tasks with Intent

1. Ed25519 Spot WebSocket real testnet auth, reconnect soak, and subscription lifecycle proof.
2. Real provider-based on-chain, social, news, and liquidation stream ingestion.
3. Account-wide Spot/Futures inventory, position, and open-order reconciliation report.
4. Permanent bucket-state and OOS-governed allocation policy for proposal-only rebalancing.
5. RAG/CAG/FAISS knowledge governance and real Docker/OS experiment sandbox backend.
6. Long-term real BTCUSDT data with multi-regime OOS promotion proof.
7. Live Spot order adapter shell and complete live eligibility proof.

 These items are not minor fixes. They require external services, user permissions, data sets, or
 separate security design; they should not be marked as done.

## Final Verification Summary

```text
Python: 3.14.7
Pytest pass count: evidence-bound
Coverage: evidence-bound
Ruff format/lint: evidence-bound
MyPy strict: evidence-bound
Bandit: evidence-bound
Candidate arbitration 100k: 0.278356 s
Agent orchestrator 100-cycle mean: 5.024 ms/cycle
Agent orchestrator 100-cycle p95: 6.584 ms/cycle
```

Coverage and pass count can be read from the full quality gate proof:
`runtime/artifacts/quality/gate/latest.json`. Benchmark values are local measurements on the same machine;
they are not performance guaranteed across hardware.

## Unchanged Security Outcome

```text
NO_TRADE when evidence is weak
RESEARCH_ONLY when OOS is incomplete
LIVE_ORDER_BLOCKED when any live gate is missing
```

## Operational Quality Loop

Nightly Quality Triage; Ruff format/lint, MyPy, Pytest/coverage and Bandit
runs the gates independently. Single lock for execution, command/job timeout,
bounded-secret-redacted output, atomic `state.json` and append-only `runs.jsonl`
proof has been applied. GitHub Actions permission is only `contents: read` for automatic
has no authority for fixes, commits, pushes, merges, deployments, trading, or parameter promotion.

Proof: `src/ai4binance/ops/quality_triage.py`,
`tests/test_quality_triage.py`, `.github/workflows/nightly_quality_triage.yml`.

## Priority reinforcement slice A-G

Applied secure vertical slices:

1. Append-only disk event journal, checkpoint validation, and restart replay.
2. Public/private connector readiness proof distinction.
3. Sequence-gap, backpressure, staleness and REST backfill stream state machine.
4. Paper order restart recovery, pending-cancel, and unknown order quarantine.
5. Quote-speed, active order, turnover, ret series, and cooldown risk-flow gates.
6. Revision/license/hypothesis/OOS staged, unauthorized research radar.
7. Same environment-bound benchmark proof and fail-closed performance regression gate.

This is the tested infrastructure. Real provider/socket connection, external
candidate reproduction conditions and live trading authority are out of scope.

## Agent Management Enhancement Phase H-M

1. Pinned commit, SHA-256, license, and capability quarantine gate for external skill/plugin.
2. Spec → red test → minimal implementation → two reviews → quality gate run card.
3. Deduplication, contradiction, validation, human approval, and expiry lesson lifecycle.
4. Proven admission manifest for nightly jobs including path/capability/lock/timeout.
5. Redacted hash, citation, blocker, and latency fixture grader for advisory trace.
6. Live unauthorized typed DAG and visual sidecar default-deny gate for Market Outlook.

Langflow, Hermes, or another external agent runtime has not been installed and initialized.
Sidecar is only allowed if pinned image, localhost, auth, SSRF, air-gapped operation, read-only
artifact, resource limit, and absence of secrets/exchange-adapter are proven
You can proceed to the evaluation.

## Read-only Evidence MCP enhancement section

1. Market Outlook, research study after atomic `state.json` as
It is published; execution permission in Outlook is denied.
2. Quality Triage and Market Outlook are read only from fixed allowlist paths.
3. Dimension, JSON format, required fields, timezone, freshness, SHA-256 and blocker
Boundaries are validated in fail-closed mode.
4. Similar secret fields are redacted before the MCP response.
5. MCP SDK is not a core dependency; `mcp>=1.27,<2` is an optional extra.
is limited.
6. Quant Research MCP and Wolfram MCP registration remain cold-path verification
surfaces. Missing external Wolfram endpoint or credential configuration returns
fail-closed blockers and does not become LLM, strategy, paper, or live authority.
7. Codex/ChatGPT record is not automatically created. HTTP, OAuth, credential, wallet and order
These vehicles are outside the scope of this vertical domain.

Evidence: `src/ai4binance/mcp/`, `src/ai4binance/outlook/storage.py`,
`tests/test_mcp_evidence.py`, `tests/test_mcp_server.py`,
`tests/test_mcp_quant_research.py`, `tests/test_research_application.py`,
`docs/contracts/interface_contract_read_only_evidence_mcp.md`,
`docs/contracts/interface_contract_mcp_fabric.md`.

## Evidence-Backed X Draft Queue Enhancement Section

1. The `EvidenceGateway` output is directly deterministic `ContentDraftEngine` input.
2. Only fresh, read-only, and live-blocked Market Outlook evidence is accepted.
3. The source SHA-256, timestamp, artifact path, and field-based claim bindings are stored.
4. The fail-closed controller checks 280-character length, disclaimer, profit
   promise, external link, mention, and secret-like text.
5. Drafts are idempotently added to the local append-only queue; approval/reject/expiry
Transitions are immutable audit events.
6. X API/OAuth/credential, network call, and publishing adapter is absent. Local
   `APPROVED` state does not grant publishing permissions.

Status: **P0 COMPLETED**, **P2 this vertical slice is COMPLETED**; P1/P3/P5 are still **NOT AVAILABLE**.

Evidence: `src/ai4binance/content/`, `src/ai4binance/content/localization.py`,
`tests/test_content_draft_queue.py`,
`reports/operations/EVIDENCE_BACKED_X_DRAFT_QUEUE.md`.

## Explicit social publishing gateway

1. X, Telegram, and LinkedIn text request adapters are implemented according to
   official endpoint contracts.
2. Platform allowlist is default-deny; credentials are only read via environment
   variables and are not written to audit artifacts.
3. Exact approved-draft match and platform/draft user confirmation are mandatory.
4. Durable intent-before-send, single attempt, idempotency, freshness, rate-limit and
   Append-only outcome audit gates have been applied.
5. Provider success is determined only by HTTP status and validated remote
   post/message ID acceptance.
6. Automatic publishing, retry, media, thread/reply, delete/edit and OAuth login flow
   is out of scope.

Status: **P4 Partial**. Code and deterministic tests are complete; real X/Telegram/LinkedIn
credential, scope/role, account and provider proof of access are missing, so real publishing
preparation remains `EXTERNAL_AUTH_BLOCKED`.

Proof: `src/ai4binance/content/publishing*.py`
`tests/test_social_publishing.py`, `docs/procedures/procedure_social_publishing_gateway.md`.

## OpenBB / Freqtrade inspired validation and provider management

1. Look-ahead and recursive-stability checks were merged into the promotion
   report as a single fail-closed indicator integrity control.
2. The combined report only produces promotion evidence; it cannot grant
   execution or live-order authority.
3. Market-context providers must report revision, license ID, host/category allowlist
   and maximum data age.
4. Expired, future-timestamped, modified, unwanted-category or allowlist-excluded
   proof events are rejected and produce an explicit blocker.
5. Provider provenance is preserved in the Market Outlook news snapshot.
6. The OpenBB/Freqtrade package is not installed, source code is not copied, and license limits
   have not been expanded.

Status: local contract and deterministic tests **COMPLETE**; all real indicators
Families have artifact-based batch processing **PARTIAL**; real external provider
Adapter `EXTERNAL_PROVIDER_BLOCKED`; promotion `RESEARCH_ONLY`; live trading
`LIVE_ORDER_BLOCKED`.

Proof: `src/ai4binance/validation/integrity.py`,
`src/ai4binance/market_context.py`, `tests/test_validation_integrity.py`,
`tests/test_governed_extensions.py`,
`reports/operations/OPENBB_FREQTRADE_STRENGTHENING.md`.

## Official Binance Public Spot Stream contract

1. Raw/combined kline and `serverShutdown` payloads are bounded, typed and
   fail-closed validated.
2. Only `5m`, `15m`, `1h`, `4h`, `1d` and only closed candles can be proof.
3. Trade-ID continuity is connected to the existing gap/backfill state machine.
4. Duplicate/old/open/sequence unsupported candles generate open blockers.
5. 23 hours 55 minutes planned rollover, server shutdown and bounded subscription
   policy contracts have been applied.
6. Closed candle hash-linked `SPOT_KLINE_CLOSED` journal event can be transitioned to.

Status: payload, lifecycle and journal contract are **COMPLETED**; real WebSocket
transport and REST backfill runtime wiring is **PARTIAL**; private user-data
`EXTERNAL_AUTH_BLOCKED`; live trading `LIVE_ORDER_BLOCKED`.

Proof: `src/ai4binance/exchange/public_stream.py`
`src/ai4binance/exchange/stream_state.py`, `tests/test_public_spot_stream.py`,
`tests/test_connector_stream_readiness.py`, `docs/contracts/event_contract_public_spot_stream.md`.

## Wallet-first Resident Runtime and Voice Security Boundary

1. Spot and USD-M Futures private readers only use official host and fixed signed-GET
   allowlist; do not include order or withdraw endpoints.
2. `ReadOnlyRuntimeCycle` wallet controls are executed before public market acquisition.
   Missing wallet control leaves both markets in `NO_TRADE` and `DEGRADED`
   status.
3. Spot and Futures advisory states are separate. Futures direction context comes
   from public derivatives evidence, but because OOS evidence is deficient,
   `RESEARCH_ONLY` and `FUTURES_OOS_NOT_APPROVED` remain.
4. Resident supervisor single-instance lock, stale-PID recovery, atomic state
   writing, balance-safe state content, and the Windows Logon Task installation
   script are present.
5. Voice gateway accepts only speaker + liveness verification and exact-match
   read-only intent. Voice cannot ever grant execution authority.
6. Real microphone/ASR/wake-word/speaker enrollment dependencies and owner-only
   audio runtime setup remain `EXTERNAL_SETUP_BLOCKED`.

Status: resident wallet-first runtime and Windows startup **COMPLETED**; real credential
with dual-market smoke **EXTERNAL_AUTH_BLOCKED**; voice security contract **COMPLETED**;
microphone-enabled owner-only voice runtime **EXTERNAL_SETUP_BLOCKED**; live processing
`LIVE_ORDER_BLOCKED`.

Proof: `src/ai4binance/application/runtime.py`
`src/ai4binance/portfolio/futures.py`, `src/ai4binance/ops/runtime.py`,
`src/ai4binance/voice/`, `src/ai4binance/voice/localization.py`,
`tests/test_runtime_cycle.py`,
`tests/test_runtime_supervisor.py`, `tests/test_voice_gateway.py`,
`scripts/install_startup_task.ps1`, `docs/runbooks/runbook_read_only_runtime.md`.

## Investment Management Assistant

1. Spot and USD-M Futures open order payload fields include order ID, side, type,
   status, price, original/executed/remaining quantity, and fail-closed
   normalization.
2. Current Spot inventory, Futures LONG/SHORT positions, open orders, and new
   setup radar systems are evaluated within the same wallet-first cycle.
3. Only `HOLD_REVIEW`, `REDUCE_RISK_REVIEW`, `OPEN_ORDER_REVIEW`, `WATCHLIST` and
`NO_ACTION` labels can be generated.
4. Suggestion tags do not grant permission for order create/cancel, position
   close, risk change, or live mode; `execution_allowed=false` and
   `LIVE_ORDER_BLOCKED` are constants.
5. If there is no wallet or Futures account snapshot, management report
   recommendations are not generated and a blocker is returned.

Status: typed management engine and resident runtime connection **COMPLETE**; real wallet
suggestions are `EXTERNAL_AUTH_BLOCKED`; automatic portfolio mutation **NONE** and conscious
scope is excluded.

Proof: `src/ai4binance/portfolio/orders.py`,
`src/ai4binance/portfolio/investment.py`, `src/ai4binance/application/runtime.py`,
`src/ai4binance/accounting/ui_reports.py`, `tests/test_investment_management.py`,
`tests/test_runtime_cycle.py`, `tests/test_accounting_collectors.py`.

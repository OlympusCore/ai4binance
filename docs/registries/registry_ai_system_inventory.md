---
document_id: AI4B-AIMS-REG-001
title: AI4BINANCE AI System Inventory
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: ai_system_inventory
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/registries/registry_ai_system_inventory.md
---

# AI4BINANCE AI System Inventory

## ELI10

This registry lists AI-enabled system components, what they are allowed to do,
what they must not do, and what evidence is needed before their role can expand.

## Registry Contract

Each AI system entry must state its intended use, prohibited use, owner,
lifecycle state, risk posture, human oversight, and evidence requirements.

The registry is advisory for inventory visibility. It does not grant live
trading authority or production promotion.

## Inventory

| ai_system_id | name | owner | lifecycle_status | intended_use | prohibited_use | oversight | risk_posture | evidence_status |
|---|---|---|---|---|---|---|---|---|
| AIMS-AI-001 | LLM-assisted repository development | Engineering Governance | ACTIVE | Draft, review, explain, and implement bounded repository changes under governed instructions | Bypass governance, alter live risk, expose secrets, or self-approve production authority | Human review and repository quality gates | MEDIUM | COMPLETED_FOR_INTERNAL_AIMS_BASELINE |
| AIMS-AI-002 | Agent registry and specialist advisory agents | Agent Governance | ACTIVE | Produce evidence, blockers, scores, and advisory research outputs | Place orders, grant execution authority, or act as sole decision authority | Deterministic orchestration and risk/validation veto | HIGH | COMPLETED_FOR_INTERNAL_AIMS_BASELINE |
| AIMS-AI-003 | Trust, Assurance and Governance Plane | Enterprise Governance | ACTIVE | Map controls, evidence, uncertainty, policy-as-code, and fail-closed blockers | Certify external compliance, remove blockers, or authorize trading | Governance owner review and deterministic payload tests | MEDIUM | COMPLETED_FOR_INTERNAL_AIMS_BASELINE |
| AIMS-AI-004 | External Intelligence Evidence Fabric | Research Governance | RESEARCH | Collect bounded external research evidence with provenance and source trust | Treat external claims as verified truth or bypass freshness/provenance gates | Research review and hostile-input assumptions | HIGH | COMPLETED_FOR_INTERNAL_AIMS_BASELINE |
| AIMS-AI-005 | Auto-Audit and Continuous Assurance | Quality Governance | ACTIVE | Generate report-only evidence for deviations, controls, and assurance findings | Deploy changes, suppress negative evidence, or close findings without verification | Human-governed CAPA and audit review | MEDIUM | COMPLETED_FOR_INTERNAL_AIMS_BASELINE |
| AIMS-AI-006 | Auto-Learn improvement candidate flow | Validation Governance | ACTIVE | Analyze validated historical evidence, synthesize lessons, and propose research candidates | Self-deploy, promote live parameters, or increase risk limits | Human-governed promotion and validation | HIGH | COMPLETED_FOR_INTERNAL_AIMS_BASELINE |
| AIMS-AI-007 | Decision Governance and risk-supported trading research | Risk Governance | ACTIVE | Produce deterministic decision-support, risk rejection, and paper-only controls | Guarantee profit, force trades, or authorize live orders without gates | Risk, validation, and human confirmation | CRITICAL | COMPLETED_FOR_INTERNAL_AIMS_BASELINE |
| AIMS-AI-008 | AI orchestration and multi-agent orchestration governance | Enterprise Governance | ACTIVE | Coordinate AI systems, agents, and workflows through pyramid layers, bounded task packages, deterministic merge rules, and evidence records | Create new authority, bypass gates, hide blockers, self-approve worker outputs, or authorize live execution | Governance owner review, workflow registry, agentic pattern tests, and AIMS risk assessment | HIGH | COMPLETED_FOR_ADVISORY_ORCHESTRATION |

## Required Fields for New Entries

New AI system entries must include:

- `ai_system_id`
- `name`
- `owner`
- `lifecycle_status`
- `intended_use`
- `prohibited_use`
- `oversight`
- `risk_posture`
- `evidence_status`

## Evidence Links

- `docs/governance/policy_ai_management_system_scope.md`
- `docs/compliance/matrix_iso_42001_aims_crosswalk.md`
- `docs/compliance/statement_of_applicability_iso_42001.md`
- `docs/governance/framework_orchestration_ai_multi_agent.md`
- `docs/reports/governance/evidence_ai_orchestration_operational_readiness.md`
- `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md`
- `docs/reports/governance/evidence_ai_orchestration_risk_impact_records.md`
- `docs/reports/governance/evidence_aims_baseline_control_record.md`
- `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md`
- `docs/reports/governance/evidence_aims_provider_control_review.md`
- `docs/reports/governance/evidence_aims_internal_audit_schedule.md`
- `docs/reports/governance/evidence_aims_management_review_minutes.md`
- `docs/reports/governance/evidence_aims_capa_records.md`
- `docs/registries/registry_evidence_registry.md`
- `docs/reports/governance/report_platform_blocker_closure_map.md`
- `docs/reports/governance/report_repository_governance_findings.md`
- `docs/workflows/procedure_ai_risk_impact_assessment.md`
- `docs/workflows/procedure_aims_nonconformity_corrective_action.md`
- `docs/reports/governance/report_repository_layer_file_inventory.md`

## Safety

An inventory entry is not approval. Missing evidence keeps the related
capability in `PARTIAL`, `RESEARCH_ONLY`, or `LIVE_ORDER_BLOCKED` state.

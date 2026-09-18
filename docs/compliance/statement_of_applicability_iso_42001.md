---
document_id: AI4B-AIMS-SOA-001
title: AI4BINANCE ISO IEC 42001 Statement of Applicability
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: statement_of_applicability_iso_42001
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/compliance/statement_of_applicability_iso_42001.md
---

# AI4BINANCE ISO IEC 42001 Statement of Applicability

## ELI10

This statement says which AI management controls apply to AI4BINANCE, why they
apply, what evidence exists, and what is still missing.

## Boundary

This is an internal AIMS applicability statement. It is not an ISO certificate
or an external conformity assessment.

## Applicability Statement

| control_family | applicability | justification | implementation_status | evidence | gap |
|---|---|---|---|---|---|
| AIMS scope and context | APPLICABLE | AI4BINANCE has AI-enabled decision-support and development workflows | COMPLETE_FOR_INTERNAL_BASELINE | `docs/governance/policy_ai_management_system_scope.md`, `docs/reports/governance/evidence_aims_management_review_minutes.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | No open internal baseline gap; external certification not claimed |
| AI policy and leadership | APPLICABLE | Governance authority, roles, and boundaries are required for responsible AI use | COMPLETE_FOR_INTERNAL_BASELINE | `AGENTS.md`, `docs/governance/policy_organization_constitution_handbook.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | No open internal baseline gap; top-management external sign-off not claimed |
| AI system inventory | APPLICABLE | Material AI systems require intended-use and prohibited-use records | COMPLETE_FOR_INTERNAL_BASELINE | `docs/registries/registry_ai_system_inventory.md`, `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md`, `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md` | No open internal baseline gap |
| AI risk assessment | APPLICABLE | Trading research, LLM, agent, and data systems can create risk if uncontrolled | COMPLETE_FOR_INTERNAL_BASELINE | `docs/workflows/procedure_ai_risk_impact_assessment.md`, `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md`, `docs/reports/governance/evidence_ai_orchestration_risk_impact_records.md` | No open internal baseline gap; live use remains blocked |
| AI impact assessment | APPLICABLE | Human oversight, privacy, safety, market conduct, and evidence impact must be assessed | COMPLETE_FOR_INTERNAL_BASELINE | `docs/workflows/procedure_ai_risk_impact_assessment.md`, `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md`, `docs/reports/governance/evidence_ai_orchestration_risk_impact_records.md` | No open internal baseline gap; live use remains blocked |
| Human oversight | APPLICABLE | LLMs and agents are advisory and must not own final trading authority | COMPLETE_FOR_INTERNAL_BASELINE | `docs/governance/policy_ai_management_system_scope.md`, `AGENTS.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | No open internal baseline gap |
| Data governance | APPLICABLE | Market, external, wallet, and research data require provenance and quality controls | COMPLETE_FOR_INTERNAL_BASELINE | `docs/registries/registry_data_source_registry.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | No open internal baseline gap; runtime provider evidence remains separately gated |
| Model and agent lifecycle | APPLICABLE | Models, agents, skills, and orchestration workflows require lifecycle and promotion boundaries | COMPLETE_FOR_INTERNAL_BASELINE | `docs/registries/registry_model_registry.md`, `docs/registries/registry_agent_registry.md`, `docs/governance/framework_orchestration_ai_multi_agent.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | No open internal baseline gap; promotion remains research-only unless separately approved |
| External provider controls | APPLICABLE | Provider adapters, MCP tools, and external sources can affect AI evidence | COMPLETE_FOR_INTERNAL_BASELINE | `docs/contracts/interface_contract_read_only_evidence_mcp.md`, `docs/governance/policy_skills_governance.md`, `docs/reports/governance/evidence_aims_provider_control_review.md` | No open internal baseline gap |
| Security and privacy | APPLICABLE | Secrets, wallet state, account data, and personal data must remain protected | COMPLETE_FOR_INTERNAL_BASELINE | `docs/governance/policy_organization_risk_security_privacy.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | No open internal baseline gap; continuous leak checks still required |
| Monitoring and measurement | APPLICABLE | AIMS performance must be monitored with evidence and quality gates | COMPLETE_FOR_INTERNAL_BASELINE | `src/ai4binance/governance/repository_validator.py`, `tests/test_repository_validator.py`, `docs/reports/governance/evidence_ai_orchestration_operational_readiness.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md`, `docs/reports/governance/report_platform_blocker_closure_map.md`, `docs/reports/governance/report_repository_governance_findings.md` | No open internal baseline gap; future effectiveness reviewed per audit schedule |
| Internal audit | APPLICABLE | AIMS evidence requires periodic independent review | COMPLETE_FOR_INTERNAL_BASELINE | `docs/workflows/instruction_audit_trigger_engine.md`, `docs/reports/governance/evidence_aims_internal_audit_schedule.md` | No open internal baseline gap |
| Management review | APPLICABLE | Leadership must review AIMS effectiveness and open risks | COMPLETE_FOR_INTERNAL_BASELINE | `docs/compliance/matrix_iso_42001_aims_crosswalk.md`, `docs/reports/governance/evidence_aims_management_review_minutes.md` | No open internal baseline gap; external certification not claimed |
| Nonconformity and corrective action | APPLICABLE | AIMS gaps must have root cause, correction, verification, and closure | COMPLETE_FOR_INTERNAL_BASELINE | `docs/workflows/procedure_aims_nonconformity_corrective_action.md`, `docs/reports/governance/evidence_aims_capa_records.md` | No open internal baseline gap |
| Live autonomous execution | NOT_APPLIED | AI4BINANCE does not authorize autonomous live trading in the current scope | NOT_APPLIED | `AGENTS.md`, `docs/governance/policy_ai_management_system_scope.md` | Reassess only after explicit human approval |

## Exclusion Rule

Any `NOT_APPLIED` row must include a justification, owner review, and evidence
that the excluded control is outside the current AIMS scope. Exclusion must not
weaken capital preservation, privacy, security, or fail-closed trading controls.

## Safety

The SoA does not make any system live eligible. The internal documentation
baseline can be complete while external certification, production deployment,
and live trading remain excluded. Missing future effectiveness evidence must be
recorded through audit or CAPA records.

---
document_id: AI4B-AIMS-MAT-001
title: AI4BINANCE ISO IEC 42001 AIMS Crosswalk Matrix
document_type: REGISTRY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: iso_42001_aims_crosswalk
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/compliance/matrix_iso_42001_aims_crosswalk.md
---

# AI4BINANCE ISO IEC 42001 AIMS Crosswalk Matrix

## ELI10

This matrix maps ISO/IEC 42001-style AIMS topics to AI4BINANCE evidence. It
shows what exists, what is partial, and what still needs proof before readiness
can be claimed.

## Boundary

This matrix is an internal readiness crosswalk. It is not an ISO certification
claim, legal opinion, or external audit report.

## Crosswalk

| area | AIMS expectation | AI4BINANCE evidence | status | gap | next action |
|---|---|---|---|---|---|
| Clause 4 Context | Understand internal/external issues, interested parties, AIMS scope, and system boundary | `docs/governance/policy_ai_management_system_scope.md`, `docs/reports/governance/report_repository_layer_file_inventory.md`, `docs/reports/governance/evidence_aims_management_review_minutes.md` | COMPLETED | No open internal baseline gap; external certification not claimed | Reassess during scheduled internal audit |
| Clause 5 Leadership | Define policy, roles, responsibilities, authorities, resources, and AI culture | `AGENTS.md`, `docs/governance/policy_ai_management_system_scope.md`, `docs/governance/policy_organization_constitution_handbook.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md`, `docs/reports/governance/evidence_aims_management_review_minutes.md` | COMPLETED | No open internal baseline gap; external certification not claimed | Reassess leadership evidence during management review |
| Clause 6 Planning | Identify risks, opportunities, AI risk assessment, AI impact assessment, objectives, and change planning | `docs/workflows/procedure_ai_risk_impact_assessment.md`, `docs/registries/registry_risk_rule_registry.md`, `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md`, `docs/reports/governance/evidence_ai_orchestration_risk_impact_records.md` | COMPLETED | No open internal baseline gap; live use remains blocked | Reassess material AI changes through the risk-impact procedure |
| Clause 7 Support | Manage resources, competence, awareness, communication, and documented information | `docs/registries/registry_documentation_index.md`, `.agents/skills/`, `docs/standards/standard_documentation_knowledge_governance.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | COMPLETED | No open internal baseline gap | Keep documented-information records current |
| Clause 8 Operation | Plan, control, assess, treat, and change AI system operations, including provider controls | `docs/governance/framework_trust_assurance_governance_plane.md`, `docs/governance/framework_orchestration_ai_multi_agent.md`, `docs/workflows/instruction_audit_trigger_engine.md`, `docs/contracts/interface_contract_read_only_evidence_mcp.md`, `docs/reports/governance/evidence_ai_orchestration_operational_readiness.md`, `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md`, `docs/reports/governance/evidence_aims_provider_control_review.md` | COMPLETED | No open internal baseline gap; provider output remains advisory-only | Reassess provider drift through audit schedule |
| Clause 9 Performance Evaluation | Monitor, measure, analyze, evaluate, audit, and conduct management review | `src/ai4binance/governance/repository_validator.py`, `tests/test_repository_validator.py`, `tests/test_docs_hygiene.py`, `docs/reports/governance/evidence_ai_orchestration_operational_readiness.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md`, `docs/reports/governance/evidence_aims_internal_audit_schedule.md`, `docs/reports/governance/evidence_aims_management_review_minutes.md`, `docs/reports/governance/report_repository_governance_findings.md`, `docs/reports/governance/report_platform_blocker_closure_map.md` | COMPLETED | No open internal baseline gap; blocker closure mapping remains under review and future effectiveness evidence remains scheduled | Run scheduled effectiveness review |
| Clause 10 Improvement | Manage nonconformity, corrective action, and continual improvement | `docs/workflows/procedure_aims_nonconformity_corrective_action.md`, `docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md`, `docs/reports/governance/evidence_aims_capa_records.md` | COMPLETED | No open internal baseline gap | Open new CAPA if audit or quality evidence finds drift |
| Annex A Controls | Select applicable controls and justify exclusions | `docs/compliance/statement_of_applicability_iso_42001.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | COMPLETED | No open internal baseline gap; live autonomous execution remains not applied | Reassess exclusions only through governance review |
| Annex B Guidance | Use implementation guidance without treating it as independent authority | `docs/compliance/statement_of_applicability_iso_42001.md`, `docs/reports/governance/evidence_aims_baseline_control_record.md` | COMPLETED | No open internal baseline gap; guidance remains subordinate to local controls | Keep guidance interpretation tied to local evidence |

## Required Evidence States

| state | meaning |
|---|---|
| COMPLETED | Document, implementation, test, and evidence are present for the local scope |
| PARTIAL | A bounded baseline exists but proof, review, or runtime evidence is incomplete |
| RESEARCH | Advisory concept exists without sufficient operational proof |
| NOT_APPLIED | Requirement is intentionally excluded with justification |
| BLOCKED | Evidence is missing for a required or safety-relevant control |

## Safety

When crosswalk evidence is missing, the result is not upgraded. The safe state
remains:

```text
execution_allowed=false
promotion_status=RESEARCH_ONLY
live_eligibility_status=LIVE_ORDER_BLOCKED
```

---
document_id: AI4B-GOV-EVID-AIMS-001
title: AI4BINANCE AIMS Baseline Control Record
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: evidence_aims_baseline_control_record
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/evidence_aims_baseline_control_record.md
---

# AI4BINANCE AIMS Baseline Control Record

## ELI10

This record ties the internal AIMS baseline controls to concrete evidence. It
supports internal documentation readiness only. It is not an ISO certificate,
external conformity claim, deployment approval, or live trading approval.

## Scope

This record covers the internal ISO/IEC 42001-style AIMS documentation baseline
for the AI systems listed in `docs/registries/registry_ai_system_inventory.md`.

## Baseline Control Coverage

| control_area | evidence | baseline_status |
|---|---|---|
| Scope, context, and interested parties | `docs/governance/policy_ai_management_system_scope.md`; `docs/reports/governance/evidence_aims_management_review_minutes.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| Leadership, roles, and accountability | role matrix in this record; `AGENTS.md`; `docs/governance/policy_organization_constitution_handbook.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| AI system inventory review | `docs/registries/registry_ai_system_inventory.md`; `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| AI risk and impact assessment | `docs/workflows/procedure_ai_risk_impact_assessment.md`; `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| Human oversight | human review register in this record; `AGENTS.md`; `docs/governance/policy_ai_management_system_scope.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| Data governance | data-control mapping in this record; `docs/registries/registry_data_source_registry.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| Model and agent lifecycle | lifecycle review in this record; `docs/registries/registry_model_registry.md`; `docs/registries/registry_agent_registry.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| External provider controls | `docs/reports/governance/evidence_aims_provider_control_review.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| Security and privacy | security and privacy review in this record; latest quality gate leak guards | COMPLETE_FOR_INTERNAL_BASELINE |
| Monitoring and measurement | KPI set in this record; `src/ai4binance/governance/repository_validator.py`; `tests/test_repository_validator.py`; `docs/reports/governance/report_platform_blocker_closure_map.md`; `docs/reports/governance/report_repository_governance_findings.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| Internal audit | `docs/reports/governance/evidence_aims_internal_audit_schedule.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| Management review | `docs/reports/governance/evidence_aims_management_review_minutes.md` | COMPLETE_FOR_INTERNAL_BASELINE |
| Nonconformity and corrective action | `docs/reports/governance/evidence_aims_capa_records.md` | COMPLETE_FOR_INTERNAL_BASELINE |

## AIMS Role Matrix

| role | accountability | authority_boundary | evidence |
|---|---|---|---|
| Enterprise Governance | Owns AIMS scope, SoA, crosswalk, and baseline claim binding | Cannot claim external certification without external assessment | this record; `statement_of_applicability_iso_42001.md` |
| Engineering Governance | Maintains repository implementation, tests, and deterministic quality evidence | Cannot widen trading authority through code presence | `scripts/quality.ps1`; repository validator |
| Risk Governance | Reviews trading, financial exposure, and fail-closed decision controls | Has veto authority over live or risk expansion | `registry_risk_rule_registry.md`; per-system risk records |
| Quality Governance | Reviews validation, blockers, and nonconformity closure evidence | Cannot suppress negative findings | `evidence_aims_capa_records.md`; quality gate |
| Security and Privacy Governance | Reviews secrets, personal data, provider trust, and leak surfaces | Blocks secret exposure and uncontrolled external writes | leak guards; provider-control review |
| Audit Governance | Maintains audit schedule, evidence registry, and review traceability | Cannot certify external conformity alone | evidence registry; internal audit schedule |
| Human Operator | Provides consequential approval where required | No autonomous live execution is granted by AIMS evidence | `AGENTS.md`; AIMS scope policy |

## Human Review Register

| review_area | required_human_control | baseline_record | status |
|---|---|---|---|
| Live execution | Explicit separate human approval before any live order capability | `AGENTS.md`; AIMS scope policy | BLOCKED_BY_DEFAULT |
| Risk-limit change | Human governance approval before risk expansion | risk registry and policy controls | BLOCKED_BY_DEFAULT |
| Strategy promotion | Evidence-based human-governed promotion | promotion and validation governance | RESEARCH_ONLY_DEFAULT |
| Provider expansion | Review trust boundary, data class, and allowed actions | provider-control review | REVIEW_REQUIRED |
| CAPA closure | Evidence review before closure | CAPA records | CONTROLLED |

## Data-Control Mapping

| data_class | trust_boundary | required_control | degraded_state |
|---|---|---|---|
| Public market data | External exchange and public endpoints | provenance, schema validation, freshness control | DATA_UNAVAILABLE |
| Private account data | Credentialed read-only boundary | least privilege, no secret logging, no write authority | EXECUTION_NOT_ALLOWED |
| External research content | Hostile-input boundary | source trust, freshness, quote limits, provenance | LOW_CONFIDENCE |
| Repository evidence | Local governed repository boundary | metadata, validation, traceable diffs | RUNNING_WITH_BLOCKERS |
| Runtime or generated artifacts | Runtime/report boundary | separation from source, retention, explicit claim binding | EVIDENCE_REQUIRED |

## Lifecycle Review

| lifecycle_surface | baseline_control | status |
|---|---|---|
| LLM-assisted repository work | advisory-only repository instructions and quality gate | CONTROLLED |
| Specialist advisory agents | registry identity, authority boundary, deterministic merge and review | CONTROLLED |
| Trust and assurance systems | report-only control plane with blocker visibility | CONTROLLED |
| External intelligence systems | hostile-input handling and provenance requirements | CONTROLLED |
| Auto-audit and auto-learn systems | recommendation-only, human-governed promotion | CONTROLLED |
| Decision governance and trading research | deterministic vetoes, no profit guarantee, live blocked | CONTROLLED |
| AI orchestration | bounded task packages and advisory-only orchestration evidence | CONTROLLED |

## Security and Privacy Review

| review_item | evidence | result |
|---|---|---|
| Secret exposure boundary | quality gate leak guards | PASS |
| Private financial value leakage | quality gate Binance financial value guard | PASS |
| External provider trust | provider-control review | CONTROLLED |
| Live action authority | AIMS scope and repository instructions | NOT_GRANTED |
| Personal data handling | no new personal data collection in this evidence set | CONTROLLED |

## AIMS Monitoring KPIs

| kpi_id | metric | evidence_source | current_result |
|---|---|---|---|
| AIMS-KPI-001 | Repository validator status | latest quality gate and repository validator | PASS |
| AIMS-KPI-002 | Governance blocker count | latest repository validator | 0 |
| AIMS-KPI-003 | Full test pass count | latest quality gate | 2094 passed |
| AIMS-KPI-004 | Coverage threshold | latest quality gate | 90.42 percent |
| AIMS-KPI-005 | Privacy leak guard | latest quality gate | CLEAR |
| AIMS-KPI-006 | Binance financial value public leak guard | latest quality gate | CLEAR |
| AIMS-KPI-007 | AIMS evidence closure set | six AIMS evidence records plus three AIO evidence records, the blocker closure map, and the repository governance findings report | COMPLETE_FOR_INTERNAL_BASELINE |

## Unsupported Claims

This baseline does not support:

- ISO/IEC 42001 certification;
- external conformity assessment pass;
- autonomous live execution;
- live trading readiness;
- production deployment readiness;
- strategy promotion;
- risk-limit increase.

## Safety

The default state remains:

```text
execution_allowed=false
promotion_status=RESEARCH_ONLY
live_eligibility_status=LIVE_ORDER_BLOCKED
```

---
document_id: AI4B-GOV-EVID-AIMS-006
title: AI4BINANCE AIMS CAPA Records
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Quality Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: evidence_aims_capa_records
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/evidence_aims_capa_records.md
---

# AI4BINANCE AIMS CAPA Records

## ELI10

This record closes the internal AIMS baseline evidence gaps through corrective
actions. It does not hide the limits of the system: external certification,
production deployment, live trading, and risk expansion remain out of scope.

## CAPA Records

| capa_id | source_finding | severity | affected_control | containment | root_cause | corrective_action | owner | due_date | verification_method | evidence_refs | closure_status | reviewer |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AIMS-CAPA-001 | Non-orchestration per-system risk records missing | HIGH | AI risk and impact assessment | Keep AIMS baseline `PARTIAL` until records exist | AIMS-AI-008 was closed first; AIMS-AI-001..007 needed records | Create per-system risk and impact record | Enterprise Governance | 2026-08-19 | repository validator and SoA/crosswalk links | `evidence_aims_per_system_risk_impact_records.md` | CLOSED_FOR_INTERNAL_BASELINE | Quality Governance |
| AIMS-CAPA-002 | Provider-control review missing | HIGH | External provider controls | Keep provider claims advisory-only | Provider surfaces were governed but not reviewed in AIMS evidence | Create provider-control review | Security and Privacy Governance | 2026-08-19 | provider-control evidence and compliance matrix links | `evidence_aims_provider_control_review.md` | CLOSED_FOR_INTERNAL_BASELINE | Audit Governance |
| AIMS-CAPA-003 | Internal audit schedule missing | MEDIUM | Internal audit | Keep audit evidence `PARTIAL` until schedule exists | AIMS audit program was referenced but not scheduled | Create internal audit schedule | Audit Governance | 2026-08-19 | audit schedule and SoA update | `evidence_aims_internal_audit_schedule.md` | CLOSED_FOR_INTERNAL_BASELINE | Enterprise Governance |
| AIMS-CAPA-004 | Management review minutes missing | MEDIUM | Management review | Keep management review `PARTIAL` until minutes exist | Management review evidence was not recorded | Create internal management review minutes | Enterprise Governance | 2026-08-19 | management review evidence and crosswalk update | `evidence_aims_management_review_minutes.md` | CLOSED_FOR_INTERNAL_BASELINE | Quality Governance |
| AIMS-CAPA-005 | CAPA records missing | MEDIUM | Nonconformity and corrective action | Keep improvement row `PARTIAL` until CAPA record exists | Corrective actions were identified but not recorded | Create CAPA record set and link affected records | Quality Governance | 2026-08-19 | CAPA record plus compliance updates | this record | CLOSED_FOR_INTERNAL_BASELINE | Audit Governance |
| AIMS-CAPA-006 | Broader AIMS baseline KPI and role evidence incomplete | MEDIUM | Monitoring, leadership, human oversight, data governance, lifecycle, security and privacy | Keep SoA rows `PARTIAL` until baseline controls are mapped | Evidence existed in multiple surfaces but was not tied into one AIMS baseline control record | Create AIMS baseline control record | Enterprise Governance | 2026-08-19 | SoA, crosswalk, and evidence registry links | `evidence_aims_baseline_control_record.md` | CLOSED_FOR_INTERNAL_BASELINE | Quality Governance |

## Closure Verification

| verification_item | result |
|---|---|
| Evidence records exist | PASS |
| Affected SoA rows linked to evidence | PASS |
| Affected crosswalk rows linked to evidence | PASS |
| Blocker closure map linked to CAPA closure evidence | PASS |
| AIMS baseline compliance matrix row can move from `PARTIAL` to `COMPLETED` for internal documentation baseline | PASS |
| Live trading boundary preserved | PASS |
| External certification claim excluded | PASS |

## Decision

```text
capa_status=CLOSED_FOR_INTERNAL_BASELINE
execution_allowed=false
promotion_status=RESEARCH_ONLY
live_eligibility_status=LIVE_ORDER_BLOCKED
```

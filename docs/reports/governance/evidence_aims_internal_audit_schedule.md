---
document_id: AI4B-GOV-EVID-AIMS-004
title: AI4BINANCE AIMS Internal Audit Schedule
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Audit Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: evidence_aims_internal_audit_schedule
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/evidence_aims_internal_audit_schedule.md
---

# AI4BINANCE AIMS Internal Audit Schedule

## ELI10

This schedule says when the AIMS baseline should be audited and what evidence
must be checked. It supports internal readiness tracking only and does not
replace an external certification audit.

## Audit Program

| audit_id | planned_date | scope | criteria | owner | output |
|---|---|---|---|---|---|
| AIMS-AUD-2026-Q3-BASELINE | 2026-08-19 | AIMS documentation baseline closure | AIMS scope policy, SoA, crosswalk, inventory, risk-impact records, provider review, management review, CAPA | Audit Governance | baseline evidence review |
| AIMS-AUD-2026-Q4-EFFECTIVENESS | 2026-11-16 | AIMS effectiveness and residual gaps | quality gate, repository validator, CAPA effectiveness, provider-control drift, inventory drift | Audit Governance | effectiveness review record |
| AIMS-AUD-2027-Q1-RECERTIFICATION-PREP | 2027-02-16 | external-assessment preparation readiness | evidence completeness, management review minutes, open CAPA, exclusions, audit trail | Audit Governance | external-readiness gap list |

## Audit Checklist

| checklist_item | evidence | required_result |
|---|---|---|
| AIMS scope remains bounded | `policy_ai_management_system_scope.md` | no live or deployment authority added |
| AI system inventory is current | `registry_ai_system_inventory.md` | every material AI system has intended and prohibited use |
| Blocker closure map is current | `docs/reports/governance/report_platform_blocker_closure_map.md` | closure mapping remains under review but traceable |
| Risk and impact records exist | per-system and orchestration risk-impact evidence | complete for internal baseline |
| Provider controls are reviewed | provider-control review | no provider authority drift |
| Internal baseline KPIs are reviewed | AIMS baseline control record and quality gate | pass or CAPA |
| CAPA actions are tracked | CAPA evidence records | closed or escalated with owner |
| Management review is recorded | management review minutes | decisions and residual risks visible |

## Independence Rule

Audit review must preserve negative evidence. Audit Governance may report,
verify, and escalate, but must not suppress findings, approve live trading, or
claim external certification.

## Decision

```text
internal_audit_schedule=COMPLETE_FOR_INTERNAL_BASELINE
execution_allowed=false
promotion_status=RESEARCH_ONLY
live_eligibility_status=LIVE_ORDER_BLOCKED
```

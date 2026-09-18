---
document_id: AI4B-GOV-EVID-AIMS-002
title: AI4BINANCE AIMS Per-System Risk and Impact Records
document_type: EVIDENCE_REQUIREMENT
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: ADVISORY
authority_layer: L8_REPORTS_EVIDENCE_INVENTORIES
authority_scope: evidence_aims_per_system_risk_impact_records
content_role: GENERATED
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/reports/governance/evidence_aims_per_system_risk_impact_records.md
---

# AI4BINANCE AIMS Per-System Risk and Impact Records

## ELI10

This record reviews each non-orchestration AI system in the AIMS inventory. The
decision is advisory or research-only use. No row grants live trading,
deployment, strategy promotion, or risk-limit authority.

## Assessment Basis

| field | value |
|---|---|
| procedure | `docs/workflows/procedure_ai_risk_impact_assessment.md` |
| inventory | `docs/registries/registry_ai_system_inventory.md` |
| review_date | 2026-08-19 |
| scope | `AIMS-AI-001` through `AIMS-AI-007` |
| excluded_from_this_record | `AIMS-AI-008`, covered by `evidence_ai_orchestration_risk_impact_records.md` |
| reviewer | Quality Governance |

## Per-System Records

| assessment_id | ai_system_id | risk_posture | affected_decisions | principal_risks | controls | residual_risk | decision |
|---|---|---|---|---|---|---|---|
| AIMS-RIA-SYS-001 | AIMS-AI-001 | MEDIUM | repository edits, reviews, explanations, local implementation support | governance bypass, unsafe code change, secret exposure, false completion claim | repository instructions, quality gate, diff review, leak guards, no live authority | LOW_FOR_REPOSITORY_ADVISORY_USE | APPROVE_RESEARCH_ONLY |
| AIMS-RIA-SYS-002 | AIMS-AI-002 | HIGH | specialist evidence, blockers, advisory research outputs | agent self-approval, hidden authority, non-deterministic aggregation | agent registry, deterministic orchestration, risk and validation veto, per-agent review | MEDIUM_CONTROLLED_FOR_ADVISORY_USE | APPROVE_RESEARCH_ONLY |
| AIMS-RIA-SYS-003 | AIMS-AI-003 | MEDIUM | control mapping, blocker visibility, uncertainty and policy evidence | false certification claim, unsupported control effectiveness claim | crosswalk, SoA, repository validator, trust plane tests, blocker closure map, repository governance findings report | LOW_FOR_INTERNAL_BASELINE | APPROVE_RESEARCH_ONLY |
| AIMS-RIA-SYS-004 | AIMS-AI-004 | HIGH | external research synthesis and source-trust scoring | hostile input, stale claims, provenance loss, quote or copyright misuse | provenance, freshness, hostile-input assumption, bounded evidence fabric | MEDIUM_CONTROLLED_FOR_RESEARCH_USE | APPROVE_RESEARCH_ONLY |
| AIMS-RIA-SYS-005 | AIMS-AI-005 | MEDIUM | audit findings, continuous assurance reports, corrective-action routing | suppressing negative findings, closing without verification, report overclaim | audit trigger workflow, CAPA workflow, evidence registry, human review | LOW_FOR_REPORT_ONLY_USE | APPROVE_RESEARCH_ONLY |
| AIMS-RIA-SYS-006 | AIMS-AI-006 | HIGH | learning recommendations and improvement candidates | self-deployment, parameter promotion, negative evidence suppression | research-only lifecycle, human-governed promotion, validation gates | MEDIUM_CONTROLLED_FOR_RESEARCH_USE | APPROVE_RESEARCH_ONLY |
| AIMS-RIA-SYS-007 | AIMS-AI-007 | CRITICAL | deterministic decision support, risk rejection, paper-only controls | live-order inference, forced trade, profit guarantee, risk-limit bypass | risk veto, validation veto, no profit guarantee, manual confirmation, live blocked | HIGH_BUT_BLOCKED_FOR_LIVE_USE | APPROVE_RESEARCH_ONLY |

## Impact Records

| ai_system_id | safety | security | privacy | financial_exposure | human_oversight | auditability |
|---|---|---|---|---|---|---|
| AIMS-AI-001 | CONTROLLED | CONTROLLED | CONTROLLED | NOT_GRANTED | REQUIRED | TRACEABLE |
| AIMS-AI-002 | CONTROLLED | CONTROLLED | CONTROLLED | NOT_GRANTED | REQUIRED | TRACEABLE |
| AIMS-AI-003 | CONTROLLED | CONTROLLED | CONTROLLED | NOT_GRANTED | REQUIRED | TRACEABLE |
| AIMS-AI-004 | CONTROLLED_WITH_HOSTILE_INPUT_ASSUMPTION | CONTROLLED | CONTROLLED | NOT_GRANTED | REQUIRED | TRACEABLE |
| AIMS-AI-005 | CONTROLLED | CONTROLLED | CONTROLLED | NOT_GRANTED | REQUIRED | TRACEABLE |
| AIMS-AI-006 | CONTROLLED | CONTROLLED | CONTROLLED | NOT_GRANTED | REQUIRED | TRACEABLE |
| AIMS-AI-007 | FAIL_CLOSED | CONTROLLED | CONTROLLED | LIVE_ORDER_BLOCKED | REQUIRED | TRACEABLE |

## Decision

```text
decision=APPROVE_RESEARCH_ONLY
execution_allowed=false
promotion_status=RESEARCH_ONLY
live_eligibility_status=LIVE_ORDER_BLOCKED
```

## Safety

These records complete the internal AIMS risk-impact baseline for
non-orchestration AI systems. They do not prove live readiness, profitability,
or external certification.

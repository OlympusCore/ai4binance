---
document_id: AI4B-GOV-OEK-106
title: AI4BINANCE Organization Incident Change and Appendices Policy
document_type: POLICY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: organization_incident_change_appendices
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/governance/policy_organization_incident_change_appendices.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# AI4BINANCE Organization Incident Change and Appendices Policy

## ELI10

This policy section defines incident management, authority matrices, change control, appendices, and approval records.

## Source Lineage

- Source file: `docs/governance/policy_organization_constitution_handbook.md`
- Source section start: `# 29. INCIDENT MANAGEMENT, BUSINESS CONTINUITY AND DISASTER RECOVERY`
- This file preserves a bounded section of the governed source document.

# 29. INCIDENT MANAGEMENT, BUSINESS CONTINUITY AND DISASTER RECOVERY



## 29.1 Incident Types

- Market/data: stale feed, bad tick, provider outage, timestamp mismatch.

- Trading/finance: duplicate order, reconciliation mismatch, unexpected position, venue failure.

- Software/AI: regression, runaway agent, model drift, incorrect config, prompt injection.

- Cyber/privacy: unauthorized access, malware, secret leak, personal/health data breach.

- Infrastructure: disk failure, GPU/CPU overload, power/network outage, backup failure.

## 29.2 BCP/DR Minimum Controls

| **Control**    | **Standard**                                                                       |
|----------------|------------------------------------------------------------------------------------|
| RTO/RPO        | Defined based on service and data class; Health Vault and financial ledger are separate targets. |
| Backup         | Encrypted, versioned, offline/immutable copy; periodic restore test.               |
| Failover       | Read-only/research mode; stale decision expire; live action remains secure.        |
| Reconciliation | Post-recovery comparison with authoritative state from exchange/bank/broker.     |
| Communication  | YKB/GM/CISO/DPO/Risk and vendor contact matrix.                                     |
| Post-Incident  | RCA, CAPA, loss assessment, lessons learned and control update.                     |

<a id="bolum-30"></a>
# 30. AUTHORITY, VETO AND APPROVAL MATRIX



| **Activity**               | **YKB**   | **GM**          | **Production Unit**    | **Risk/Compliance/CISO/DPO** | **QA/QC/Validation** | **Execution/Ops** |
|----------------------------|-----------|-----------------|----------------------|------------------------|----------------------|-------------------|
| New market/product         | A         | R/C             | R                    | C/V                    | C                    | I                 |
| New model/strategy         | I/A\*     | C               | R                    | C/V                    | A/V                  | I                 |
| Production release         | I/A\*     | C               | R                    | C/V                    | A/V                  | I                 |
| Risk limit change          | A         | C               | I                    | R/V                    | C                    | I                 |
| Live trading authorization  | A         | C               | R recommendation     | V                      | V                    | R (after gate)   |
| Money transfer/withdrawal  | A         | C               | I                    | V                      | I                    | R (double approval)|
| Personal/health data processing | A/Consent | I               | R only Health Office | DPO/CISO V             | Audit C              | I                 |
| Kritik siber olay          | I/A       | Incident Coord. | R support            | CISO/DPO R/V           | Audit C              | Ops R             |
| NCR/CAPA kapatma           | I         | C               | R action             | C                      | A/V                  | I                 |

*A = Accountable, R = Responsible, C = Consulted, I = Informed, V = Veto. A* = approval by YKB/committee based on policy and risk class.*

## 30.1 Authorization Levels

| **Level**        | **Definition**                                                                                   |
|-------------------|---------------------------------------------------------------------------------------------|
| OBSERVE           | Data and status okuma.                                                                        |
| RESEARCH          | Analysis, hypothesis, report and experiment proposal.                                                    |
| SANDBOX           | Testing and prototyping in an isolated environment.                                                    |
| PAPER/SHADOW      | Simulation and real-time shadow decision.                                                   |
| MANUAL_RECOMMEND  | Recommendation for human application.                                                                |
| CONTROLLED_ACTION | Time-bound, limited, explicitly approved and gated action.                                             |
| PROHIBITED        | Withdrawal, self-authorized live, unapproved risk increase, unauthorized health processing. |

<a id="bolum-31"></a>
# 31. CHANGE, EXCEPTION, APPROVAL AND EFFECTIVITY



## 31.1 OEK Change

- Change request; presented with problem, source, impact/gap, risk, privacy/security, cost, test and migration plan.

- Changes that weaken immutable core principles are not accepted; unless it is a legally applicable change, the change must be justified with a rationale for re-writing.

- The approved version is published with effective date, migration, training and compliance attestation.

- All agent charter, prompt, config, workflow and runbook are subject to gap analysis against the new version.

## 31.2 Exception Management

| **Field**            | **Required**                                                 |
|----------------------|--------------------------------------------------------------|
| Reason             | Why is the standard not being applied?                          |
| Scope/Duration      | Which agent, data, system, and end date?                   |
| Risk                 | Inherent/residual risk and worst-case.                        |
| Compensating Control | Temporary mitigation and monitoring.                                     |
| Owner/Approval           | Business owner + relevant control owner + YKB/committee level. |
| Closure              | Expiration, return to standard operation and evidence.        |

## 31.3 Post-Effective Mandatory Actions

13. All repository/worktree, agent, workflow, config, model, strategy, API permission, and data flow gap analysis for OEK v3.0.

14. Implementation of YKB–GM Executive Intake and Prompt Order schemas.

15. Always-on scheduler is set up with Observe/Research/Sandbox boundaries; live action is default closed.

16. YKB Email Management Report Template, Recipient Allowlist, and Mail Security Controls Preparation.

17. Separate PIA/DPIA, consent, and access design for Health Vault and Health Advisor.

18. Agent capability baseline, repository health baseline, cyber/privacy baseline, and initial Management Review Report.

<a id="ek-a"></a>
# Appendix A - Standard Decision Packet



| **Field** | **Content**                                                      |
|----------|-----------------------------------------------------------------|
| identity | decision_id, prompt_id, snapshot_id, owner, timestamp, expiry   |
| context  | market, account, portfolio, regime, correlation, user objective |
| evidence | data/source, specialist results, counter-evidence, uncertainty  |
| proposal | action/experiment/change/report and alternatives                |
| risk     | size, drawdown, liquidity, correlation, operational/model risk  |
| controls | data/risk/compliance/privacy/security/validation statuses       |
| approval | required approvers, approval_id, scope, expiry                  |
| outcome  | executed/rejected/deferred, result, reconciliation, lesson      |

<a id="ek-b"></a>
# Appendix B — YKB Management Report Decision Form



| **Decision Area**           | **Option / Record**                            |
|---------------------------|------------------------------------------------|
| Subject                   |                                                |
| Recommended Decision            | APPROVE / REJECT / DEFER / RETURN FOR EVIDENCE |
| Expected Benefit          |                                                |
| Ana Risk and Residual Risk |                                                |
| Cost / Resource          |                                                |
| Control Comments         | Risk / Compliance / CISO / DPO / QAQC / Validation   |
| Approval Scope and Timeline    |                                                |
| YKB Decision / Date        |                                                |

<a id="ek-c"></a>
# APPENDIX C — HEALTH AND LIFESTYLE COACH REGISTRATION SCHEMA



| **Category**   | **Minimum Field**                                                    | **Privacy**         |
|----------------|------------------------------------------------------------------------|---------------------|
| Profile         | Age range, confirmed diagnosis/history by physician, allergies, emergency contact.     | SPECIAL/HEALTH      |
| Medication      | Name, dose, time, prescribing physician, start/end, notes.                | SPECIAL/HEALTH      |
| Test            | Test name, date, lab, result, reference, physician comment/follow-up. | SPECIAL/HEALTH      |
| Appointment     | Specialty, institution, date, preparation, documents.                            | CONFIDENTIAL/HEALTH |
| Lifestyle       | Sleep, activity, nutrition goal, alignment, restrictions and review.                 | SPECIAL/HEALTH      |
| Consent/Access  | Purpose, legal basis/consent, access list, retention, revocation.         | RESTRICTED          |

<a id="ek-d"></a>
# APPENDIX D — CONTROL CHECKLIST



| **Area**       | **Control Questions**                                                                    |
|----------------|-----------------------------------------------------------------------------------------|
| Governance     | Owner, RACI, approval, conflict and segregation defined?                              |
| Agent          | Is the charter, scope, tool allowlist, output schema, and kill criteria up to date?                 |
| Data           | Are freshness, provenance, quality, license, privacy, and retention evidence present?            |
| Model/Strategy | OOS, robustness, cost, capacity, drift and rollback sufficient mi?                          |
| Software       | Branch/worktree, tests, SAST/SCA/SBOM, performance and documentation compliant mu?           |
| Cyber          | MFA, secrets, access, endpoint, monitoring and incident readiness effective mi?              |
| Privacy/Health | Are PIA/DPIA, minimization, consent/legal basis, rights, and Health Vault isolation in place?   |
| Execution      | Has approval, OMS/EMS, idempotency, limits, reconciliation, and withdrawal-off been validated? |
| Learning       | Has the training been validated; has controlled promotion to production been done?                        |

<a id="ek-e"></a>
# EK E — SOURCE AND COMPLIANCE REFERENCE DOCUMENTS



## E.1 Controlled Internal Sources

- AI4BINANCE Agentic AI Human Characteristics and Cognitive Architecture Specification — specification for purpose, skills, character, behavior, authority, memory, and cognitive loop internal requirements.

- AI4BINANCE Organizational Constitution and Handbook v2.0 — constitutional norms, hierarchy, correlation, strategy factory, cyber/privacy, and audit structure.

- AI4BINANCE EnterpriseAI vNext / Custom Instructions Core — deterministic multi-agent, shared snapshot, validation, paper/manual, and LIVE_ORDER_BLOCKED approach.

- AI4BINANCE Dynamic Portfolio and Opportunity Management application guidelines — objective holding vs opportunity, liquidity, correlation and manual approval.

- Secure computer operation rules defined by YKB and the digital holding/software organization model approved in this discussion.

## E.2 Official External Sources

**KVKK – Personal Data Protection Board —** [https://www.kvkk.gov.tr/](https://www.kvkk.gov.tr/) — Law No. 6698, secondary regulations, special category personal data and technical/administrative measures.

**KVKK Council Decision 2018/10 —** [https://www.kvkk.gov.tr/Icerik/4110/2018-10](https://www.kvkk.gov.tr/Icerik/4110/2018-10) — Adequate measures to be taken in processing special category personal data.

**KVKK User Security Notice —** [https://www.kvkk.gov.tr/Icerik/7177/Kullanici-Guvenligine-Iliskin-Veri-Sorumlulari-Tarafindan-Alinmasi-Tavsiye-Edilen-Teknik-ve-Idari-Tedbirlere-Iliskin-Kamuoyu-Duyurusu](https://www.kvkk.gov.tr/Icerik/7177/Kullanici-Guvenligine-Iliskin-Veri-Sorumlulari-Tarafindan-Alinmasi-Tavsiye-Edilen-Teknik-ve-Idari-Tedbirlere-Iliskin-Kamuoyu-Duyurusu) — Technical/administrative measures approach under Article 12 of the Law.

**EUR-Lex – GDPR Regulation (EU) 2016/679 —** [https://eur-lex.europa.eu/eli/reg/2016/679/oj](https://eur-lex.europa.eu/eli/reg/2016/679/oj) — Especially Articles 5, 9, 25, 32 and 35.

**California Privacy Protection Agency —** [https://cppa.ca.gov/regulations/](https://cppa.ca.gov/regulations/) — CCPA/CPRA regulations, risk assessment, cybersecurity audit and ADMT regulations.

**NIST Cybersecurity Framework 2.0 —** [https://www.nist.gov/cyberframework](https://www.nist.gov/cyberframework) — GOVERN, IDENTIFY, PROTECT, DETECT, RESPOND, RECOVER.

**NIST AI Risk Management Framework —** [https://www.nist.gov/itl/ai-risk-management-framework](https://www.nist.gov/itl/ai-risk-management-framework) — Trustworthy and responsible AI risk management.

*Access date: August 2, 2026. Applicability and currency are regularly verified by the Compliance/Legal/Confidentiality function.*

<a id="ek-f"></a>
# Appendix F - Abbreviations



| **Abbreviation**  | **Description**                                                                 |
|---------------|------------------------------------------------------------------------------|
| YKB           | Chairman of the Board                                                       |
| GM            | Chief Executive Officer / Holding Orchestrator                           |
| CIO           | Chief Investment Officer                                                     |
| CRO           | Chief Risk Officer                                                           |
| CISO          | Chief Information Security Officer                                           |
| CCO           | Chief Compliance Officer                                                     |
| DPO           | Data Protection Officer / Privacy Officer                                  |
| OMS/EMS       | Order / Execution Management System                                          |
| PIA/DPIA      | Privacy / Data Protection Impact Assessment                                  |
| KPI/KRI       | Key Performance / Risk Indicator                                             |
| NCR/CAPA      | Non-Conformity / Corrective and Preventive Action                            |
| OOS           | Out-of-Sample                                                                |
| RACI          | Responsible, Accountable, Consulted, Informed                                |
| RTO/RPO       | Recovery Time / Recovery Point Objective                                     |
| SAST/SCA/SBOM | Static Analysis / Software Composition Analysis / Software Bill of Materials |
| SRE           | Site Reliability Engineering                                                 |
| RAG/CAG       | Retrieval / Cache Augmented Generation                                       |

<a id="management-board-approval"></a>
# BOARD OF DIRECTORS APPROVAL PAGE



This document is recognized as an outstanding internal standard for the governance, agent authority, cognitive architecture, continuous background operations, market/technology intelligence, software/AI development, risk, cybersecurity, privacy, health data isolation, audit and controlled profitability management of AI4BINANCE Digital Markets Holding.

| **Role**                                               | **Name/Surname** | **Date** | **Signature** |
|-------------------------------------------------------|--------------|-----------|----------|
| Chairman of the Board (YKB)                          |              |           |          |
| Chief Executive Officer / Holding Orchestrator Owner              |              |           |          |
| Chairman of the Risk Committee                                 |              |           |          |
| Chairman of the Audit and Ethics Committee                      |              |           |          |
| Chair of the AI and Model Governance Committee             |              |           |          |
| Chair of the Cybersecurity–Confidentiality–Resilience Committee |              |           |          |
| Governance Office                                     |              |           |          |

> [!IMPORTANT]
> **LIVE CONDITION**
> This draft does not create production authorization without YKB approval and a defined effective date. The current security rule remains in effect: files are not modified without explicit approval, programs are not installed, files are not deleted, administrator privileges are not used, and real financial transactions are not performed without authorization.

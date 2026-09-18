---
document_id: AI4B-AIMS-POL-001
title: AI4BINANCE AI Management System Scope
document_type: POLICY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: ai_management_system_scope
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/governance/policy_ai_management_system_scope.md
---

# AI4BINANCE AI Management System Scope

## ELI10

This policy defines the AI management system boundary for AI4BINANCE. It says
which AI-enabled capabilities are governed, which activities are out of scope,
and which evidence is required before anyone can claim ISO/IEC 42001 readiness.

## Purpose

AI4BINANCE maintains an AI management system baseline for responsible,
evidence-based development and operation of advisory AI capabilities.

This policy supports ISO/IEC 42001 alignment, but it is not a certification
claim, legal opinion, or external audit certificate.

## Scope

The AIMS scope includes repository-governed AI and AI-adjacent capabilities that
affect research, decision support, assurance, validation, documentation,
automation, or controlled improvement.

In scope:

- LLM-assisted repository work and provider adapters.
- Agent registries, skills, and workflow instructions.
- Trust, assurance, governance, policy-as-code, uncertainty, and evidence graph
  controls.
- Market-research and paper-trading decision-support components.
- Data-quality, validation, replay, risk, security, privacy, and audit controls.
- Continuous assurance, auto-audit, auto-learn, and improvement-candidate
  processes.
- Repository artifact governance, documentation governance, and evidence
  inventory.

Out of scope:

- Live order authorization.
- Autonomous live financial execution.
- Increasing live risk limits.
- Production deployment approval.
- External certification claims.
- Legal, investment, or regulatory advice.
- Secret, wallet, account, or private-key disclosure.

## Interested Parties

| Party | Need | AIMS response |
|---|---|---|
| Enterprise Governance | Controlled authority and evidence | Source-of-truth governance, policy-as-code, audit trails |
| Engineering | Clear implementation boundaries | Repository layers, contracts, tests, validation gates |
| Risk and Validation | Fail-closed controls | `RESEARCH_ONLY`, `NO_TRADE`, `LIVE_ORDER_BLOCKED` |
| Security and Privacy | Least privilege and no secret leakage | Secret boundaries, DLP, privacy controls |
| Human Operator | Explainable, bounded decision support | Evidence records, human review, no autonomous live trading |
| External Auditor | Traceable management-system evidence | Crosswalk, SoA, inventory, CAPA and review records |

## AIMS Boundary

The AIMS boundary follows the repository governance pyramid:

```text
L1 Core Constitution
-> L2 Governance / Compliance
-> L3 Canonical Contracts
-> L4 Repository Instructions
-> L5 Standards / Policies / Controls
-> L6 Registries / Ontology / Workflows
-> L7 Code / Configuration
-> L8 Evidence / Runtime / Reports
```

The boundary is enforced through:

- `docs/governance/policy_organization_constitution_handbook.md`
- `docs/governance/framework_orchestration_ai_multi_agent.md`
- `docs/governance/framework_trust_assurance_governance_plane.md`
- `docs/compliance/matrix_iso_42001_aims_crosswalk.md`
- `docs/compliance/statement_of_applicability_iso_42001.md`
- `docs/registries/registry_ai_system_inventory.md`
- `docs/workflows/procedure_ai_risk_impact_assessment.md`
- `docs/workflows/procedure_aims_nonconformity_corrective_action.md`
- `src/ai4binance/governance/repository_validator.py`
- `tests/test_repository_validator.py`
- `tests/test_docs_hygiene.py`

## Mandatory Requirements

1. Every AI capability must have a registered intended use and prohibited use.
2. AI components must remain advisory unless deterministic governance explicitly
   grants a narrower machine-enforced role.
3. The LLM must not own final trading decisions, risk overrides, leverage,
   live-order authorization, kill-switch decisions, or strategy promotion.
4. Missing AIMS evidence must be visible as `PARTIAL`, `EVIDENCE_REQUIRED`, or
   `RUNNING_WITH_BLOCKERS`; it must not be treated as pass evidence.
5. AIMS evidence must not expose secrets, account data, wallet state, private
   keys, or personal data.
6. AIMS improvement actions must preserve human-governed promotion for
   consequential changes.

## Acceptance Criteria

The AIMS baseline is acceptable only when the following evidence exists:

- AI system inventory entry for each material AI capability.
- ISO/IEC 42001 crosswalk status for clauses and control families.
- Statement of applicability with applicability, justification, status, and
  evidence references.
- AI risk and impact assessment record for each material AI system change.
- Nonconformity and corrective-action workflow for AIMS findings.
- Repository validator and documentation hygiene evidence.

## Safety

This policy does not authorize live trading, external deployment, credential
use, risk-limit increases, or production promotion. The default execution state
remains:

```text
execution_allowed=false
promotion_status=RESEARCH_ONLY
live_eligibility_status=LIVE_ORDER_BLOCKED
```

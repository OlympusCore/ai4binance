---
document_id: AI4B-AUDIT-INS-001
title: AI4BINANCE Audit Trigger Engine Instruction
document_type: INSTRUCTION
version: 1.0.1
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L7_WORKFLOWS_PROCEDURES_RUNBOOKS_PROVIDERS
authority_scope: audit_trigger_engine
authority_effect: OPERATIONAL_SPECIALIZATION
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: audit_trigger_engine_workflow
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/workflows/instruction_audit_trigger_engine.md
---

# AI4BINANCE Audit Trigger Engine Instruction

```text
instruction_id: AI4B-AUDIT-TRIGGER-ENGINE-001
version: 1.3
status: ACTIVE
authority: OEK six operational instructions
canonical_path: docs/workflows/instruction_audit_trigger_engine.md
parent_instruction: docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md
source: user-approved EAACIE hybrid trigger design, 2026-08-09
```

## ELI10

This instruction is the main rule for the question "When should I start an audit?" in the system.
Normal monitoring only observes; Audit Trigger Engine starts a documented,
fail-closed, human-reviewed audit process when state deviates from expected or
allowed status.
Starts.

## Objective and Scope

Audit Trigger Engine is the central trigger layer for the Continuous Assurance,
Continuous Improvement, and Governance System defined in `docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md`.
It is not a single cron job or single event type; it is a hybrid trigger that is
event-driven, risk-driven, scheduled, anomaly-driven, and lifecycle-driven.

This instruction covers the following surfaces:

- State, decision, data, configuration, model, operation, and system behavior.
- Code, configuration, instruction, parameter, data quality, drift, market regime,
  execution, stop-loss, trailing stop, false-positive, and manual/scheduled audit.
- KVKK/privacy, cybersecurity, trading assurance, backtest QA, parameter
  governance, AutoLearn governance, and DGE assurance.

## Upper norm and related files

- Upper norm: `docs/governance/policy_organization_constitution_handbook.md`.
- Upper EAACIE instruction: `docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md`.
- Trust Plane instruction: `docs/governance/framework_trust_assurance_governance_plane.md`.
- Document map: `docs/registries/registry_documentation_index.md`.
- Compliance certificate: `docs/compliance/registry_compliance_matrix.md`.
- Runtime instruction link: `src/ai4binance/ops/continuous_assurance.py`.
- Auto-audit loop link: `src/ai4binance/ops/auto_audit_loop.py`.
- Weekly security deep-audit link:
  `src/ai4binance/ops/security_assurance.py`.
- Test certificate: `tests/test_continuous_assurance.py`
  `tests/test_auto_audit_loop.py`, `tests/test_security_assurance.py`.

OEK does not independently authorize live processing, production deployment, risk
increase, or parameter promotion. This instruction respects the same boundary.

## Central Rule

An audit is initiated when state, decision, data, configuration, model,
operation, or system behavior deviates from expected or allowed status.

Starting an audit is not execution permission. The audit outcome is:

- Does not send orders.
- Does not increase the risk limit.
- Does not promote production parameters.
- Does not publish secret, wallet, account, or KVKK data.
- Cannot use `LIVE_ORDER_BLOCKED` as a standalone result.

## Monitoring != Audit

Monitoring only observes signal or telemetry observations. Audit generates evidence, scope, root
cause, finding, corrective action, verification and close/escalation cycle.
Therefore, every monitoring event is not an audit; but audit is required if there is a deviation from expected/allowed state,
high risk or scheduled baseline is present.

## Trigger modes

Runtime equivalent is `AuditTriggerMode` enum:

| Mode | When to use |
|---|---|
| `EVENT_DRIVEN` | When event, decision, lifecycle event, instruction or workflow change occurs |
| `RISK_DRIVEN` | When risk score, severity or high risk domain comes into play |
| `SCHEDULED` | Periodic baseline audit is required; generates audit even if no deviation exists |
| `ANOMALY_DRIVEN` | Drift, data quality, performance, or behavior anomaly detected |
| `LIFECYCLE_DRIVEN` | State transition, execution lifecycle, stop/trailing/closure overlay |

## Observed entity types

Runtime equivalent is the `AuditObservedEntity` enum:

- `STATE`
- `DECISION`
- `DATA`
- `CONFIGURATION`
- `MODEL`
- `OPERATION`
- `SYSTEM_BEHAVIOR`

## Audit event ontology

Mandatory runtime concepts:

- `AuditTriggerSignal`: Monitored entity, trigger mode, comparison, severity,
Carries the risk score and evidence references.
- `AuditStateComparison`: Comparison of expected/observed or allowed-values.
- `ContinuousAuditEvent`: normalized event entering the audit loop.
- `AuditRouteDecision`: Event domain, workflow pattern, storm status, blocker
  and generates the action reference decision.
- `ContinuousAssurancePlan`: A plan that includes one or more route decisions in a fail-closed manner
  as paketler.
- `TrustAssuranceBundle`: EAACIE TIAF-lite packet; it adds decision provenance,
  policy evaluation, uncertainty/abstention, semantic contract and
  evidence-graph-lite records to the plan payload.
- `TrustPlaneAssessment`: A separate Trust, Assurance & Governance Plane catalog,
  P0/P1/P2 controls and ISO/IEC 42001, ISO/IEC 23894 and NIST AI RMF mapping,
  which is carried under `trust_assurance.governance_plane`.

Every payload carries `instruction_ref: docs/workflows/instruction_audit_trigger_engine.md` and
`instruction_refs: [docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md, docs/workflows/instruction_audit_trigger_engine.md]` references
are carried.

## Trigger tree

The audit trigger tree covers the following families:

- `SYSTEM`
- `DATA`
- `MARKET`
- `INTELLIGENCE`
- `STRATEGY`
- `RISK`
- `EXECUTION`
- `LEARNING`
- `SOFTWARE`
- `SCHEDULE`

## Security Trigger Family

Security triggers are normalized into EAACIE Security Core through the
`SecurityAuditTriggerType` enum. They are not a new agent or scheduler; they are
typed routes inside the central AuditTriggerEngine:

| Trigger | Security domain route |
|---|---|
| `CODE_CHANGE` | `APPSEC`, `SECRETS`, `DLP`, `AUDIT` |
| `CONFIG_CHANGE` | `ACCESS`, `SECRETS`, `APPSEC`, `DLP`, `AUDIT`, `RECOVERY` |
| `DEPENDENCY_CHANGE` | `APPSEC`, `VULNERABILITY`, `AUDIT` |
| `CREDENTIAL_SECRET_EVENT` | `ACCESS`, `SECRETS`, `DLP`, `AUDIT`, `RECOVERY` |
| `GIT_CLOUD_EVENT` | `PRIVACY`, `SECRETS`, `DLP`, `AUDIT` |
| `SECURITY_INCIDENT` | All eight Security Core domains |
| `SCHEDULED_DAILY_QUICK` | All eight domains; bounded/offline/freshness focused |
| `SCHEDULED_WEEKLY_DEEP` | All eight domains; deep proof including dependencies/restore |

`SCHEDULED_DAILY_QUICK` is routed report-only inside the existing Auto-Audit cycle.
This route does not install a scanner, read credentials, or create a Windows Task
Scheduler task. `SCHEDULED_WEEKLY_DEEP` is run through the
`security-weekly-deep-audit` CLI command; SBOM-lite, CVE/advisory evidence,
MFA attestation, backup/restore proof, and external immutable/WORM proof
binds the control checks to the proof package. CLI integration is available, but OS scheduler
task automatically.

### Security trigger kurallari

- A security trigger cannot generate an event with an incomplete subset of the
  domains defined in policy; mismatches fail closed with `ValueError`.
- All security routes are connected to the `CYBERSECURITY` and/or `PRIVACY_KVKK`
  high-risk domains and require human review.
- Credential/secret events and security incidents generate the
  `SECURITY_INCIDENT_RESPONSE_REQUIRED` blocker.
- Dependency changes generate the `DEPENDENCY_SECURITY_REVIEW_REQUIRED` blocker;
  Git/cloud events generate the `DLP_REVIEW_REQUIRED` blocker.
- Every security route preserves the `SECURITY_AUDIT_REPORT_ONLY`, `RESEARCH_ONLY`,
  and `LIVE_ORDER_BLOCKED` boundaries.
- A daily/weekly schedule does not mean that every control passed; only the relevant
  Generates a route for the collection and evaluation of control evidence.
- If weekly deep audit evidence is missing, `CVE_ADVISORY_SOURCE_MISSING`,
  `MFA_PROVIDER_ATTESTATION_MISSING`, `RESTORE_TEST_EVIDENCE_MISSING`, or
  `WORM_STORAGE_EVIDENCE_MISSING` blockers remain fail-closed.

## Severity and Decision

| Severity | Meaning | Minimum impact |
|---|---|---|
| `P0` | Critical security, money, secret, KVKK or live-authority risk | Audit + human review |
| `P1` | High-risk governance or execution deviation | Audit + human review |
| `P2` | Significant evidence, quality or lifecycle deviation | Audit |
| `P3` | Normal improvement/audit signal | Route based on audit threshold |
| `P4` | Low priority observation | Audit if scheduled or proven deviation exists |

`P0` and `P1` always require an audit. If risk score is `>= 70`, a risk-driven
audit is initiated even without a deviation.

## Audit storm protection

Default storm policy:

- `cooldown_seconds: 900`
- `correlation_window_seconds: 300`
- `max_parallel_audits: 4`
- `max_recursion_depth: 3`
- `same_root_cause_merge: true`
- `dedup: true`

If the same root cause repeats, it is merged; duplicate event within cooldown
It is reported as suppressed; if the recursion depth is exceeded, the audit loop fails-closed
is blocked.

## Invariantlar

- Evidence is required for audit conclusion.
- Promotion is required if OOS is not present.
- No execution eligibility without risk approval.
- If the corrective action is not taken, the finding remains open.
- Automatic closure is not allowed in domains requiring human review.
- Do not change the production parameters for Auto-audit and AutoLearn.
- DGE generates review decisions; does not grant live order authority.
- A directive or code change requires OEK gap analysis.

## Auto-Audit, AutoLearn and DGE Permission Separation

- Auto-Audit: Collects evidence, routes it, generates blockers, and suggests corrective actions.
- AutoLearn: can suggest a lesson candidate and validation plan; it cannot
  promote parameters.
- DGE: evaluates decision quality and governance context; it does not provide
  execution permission.
- Deterministic core: owns final signal, risk gate, exchange filter, and
  execution permission decisions.
- TIAF-lite: explains the audit plan with the `AI4BINANCE_TIAF_LITE` trust
  package; reduces the Graph RAG/XAI/AI Ethics vision to local evidence graph,
  policy-as-code, semantic contract, and abstention records; P1/P2 advanced layers
  create staged controls only conditionally with request + layer evidence;
  it does not slow down the trading hot path.

## Runtime Compatibility Condition

The code must adhere to the following conditions:

- Timestamp values must be timezone-aware.
- Trigger mode, comparison field, and evidence refs cannot be duplicated.
- The security trigger and security domain route must match policy exactly.
- Evidence refs cannot be empty or blank.
- Audit is generated even if there is no scheduled trigger deviation.
- Audits are not generated for values within allowed-values and low-risk states.
- Deviation, `P0/P1` severity, or `risk_score >= 70` generates an audit.
- Route payloads carry `execution_allowed: false`
  `promotion_status: RESEARCH_ONLY`,
  `live_eligibility_status: LIVE_ORDER_BLOCKED`.
- Plan payloads carry `trust_assurance.framework: AI4BINANCE_TIAF_LITE`,
  deterministic `provenance_hash`, and `bundle_hash`.
- If hidden trading authority is detected, it fails-closed with a `ValueError`.

## Test Evidence

Focus validation:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_continuous_assurance.py tests\test_auto_audit_loop.py --no-cov
.venv\Scripts\python.exe -m pytest tests\test_security_assurance.py --no-cov
```

Full quality gate:

```powershell
scripts\quality.ps1
```

Every new trigger or domain addition must update this document, the runtime
mapping, and the proof tests together.





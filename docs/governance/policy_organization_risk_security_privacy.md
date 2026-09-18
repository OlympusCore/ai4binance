---
document_id: AI4B-GOV-OEK-104
title: AI4BINANCE Organization Risk Security and Privacy Policy
document_type: POLICY
version: 1.0.0
status: ACTIVE
owner: Enterprise Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: organization_risk_security_privacy
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/governance/policy_organization_risk_security_privacy.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
---
# AI4BINANCE Organization Risk Security and Privacy Policy

## ELI10

This policy section defines execution governance, software governance, data governance, security, and privacy.

## Source Lineage

- Source file: `docs/governance/policy_organization_constitution_handbook.md`
- Source section start: `# 18. Risk, Compliance, Validation and Execution Governance`
- This file preserves a bounded section of the governed source document.

# 18. Risk, Compliance, Validation and Execution Governance



## 18.1 Mandatory Decision Flow

```text
SHARED SNAPSHOT
-> DATA QUALITY
-> MARKET / RESEARCH AGENTS
-> CONFLUENCE
-> PORTFOLIO FIT
-> PRE-TRADE RISK
-> COMPLIANCE / PRIVACY / SECURITY
-> INDEPENDENT VALIDATION
-> HUMAN APPROVAL (if needed)
-> OMS / EMS
-> RECONCILIATION
```


## 18.2 Veto Yetkileri

| **Control**   | **Veto Reason**                                                             | **Outcome**                              |
|---------------|-----------------------------------------------------------------------------|----------------------------------------|
| Data Quality  | Missing/stale/corrupt data or no provenance.                               | DATA_INVALID / NO_TRADE                |
| Risk          | Drawdown, liquidity, leverage, concentration, correlation, or capacity breach. | Size reduction / freeze / NO_TRADE     |
| Compliance    | Regulation, market conduct, restricted asset, license, or transfer risk.    | BLOCKED / legal review                 |
| Privacy       | Use of data for purposes other than those intended, legal basis, notice/rights/transfer issues.              | PROCESSING_BLOCKED                     |
| Security      | Secret, access, injection, supply-chain, or account anomaly.                | QUARANTINE / revoke / isolate          |
| Validation    | OOS, robustness, reproducibility, or insufficient evidence.                 | RESEARCH_ONLY / PAPER_ONLY             |
| Execution     | Approval missing, OMS/EMS gate, account or venue status is not compliant.             | LIVE_ORDER_BLOCKED                     |
| Health Safety | Exceeding medical diagnosis/treatment authorization or urgent indicators.                        | HEALTH_ESCALATION / clinician referral |

## 18.3 Execution Security Principles

- The strategy agent does not have direct access to the exchange/bank/broker endpoint; it passes through OMS/EMS and control gateways.

- Approval_id, idempotency key, expiry, amount/price tolerance, and account scope are present for each action.

- Withdrawal permissions are default disabled; transfer and conversion require separate approval classes.

- Read-only, paper, and trade API keys are separated; production secrets are not found in source code, prompts, or email.

- Live mode can only be silently opened via config change; multi-approval and change record are required.

<a id="bolum-19"></a>
# 19. Software Engineering and Repository/Worktree Constitution



Software Engineering is the holding's main production unit; however, it cannot independently make investment decisions, risk policies, privacy interpretations, or its own release approvals.

## 19.1 Safe Work Practice Rule

> [!CAUTION]
> **YKB Computer Safe Work Practice Rule**
> Review first; then write the plan and impact. Obtain approval before modifying files. Do not install programs, delete files, use administrator privileges, or perform financial transactions without approval.


## 19.2 Repository and Worktree Standards

| **Control**        | **Constitutional Rule**                                                                       |
|--------------------|------------------------------------------------------------------------------------------|
| Canonical Repo     | Single true source; duplicate project and ambiguous junction/symlink records are inventoried. |
| Worktree           | Isolated worktree/branch for each experiment/issue; does not mix with production branch.              |
| Branch Protection  | main protected; merge not allowed without peer review, test, security scan and approval.          |
| Small Changes      | Targeted, small, reversible changes; no unnecessary zero-from-writing.                 |
| Clean Structure    | Domain boundaries, low coupling, no circular dependency, shared contracts are versioned.   |
| Repository Governance | `AI4B-GOV-REPO-001` is constitutional. Folder/file structure is enforced by RepositoryPolicy, RepositoryArtifact schema and deterministic repository_validator evidence. |
| Dead Code          | First inventory/usage test/deprecation; deletion only with YKB approval and rollback.           |
| Dependencies       | Pin/lock, SCA, license, CVE, unused dependency and vendor risk control.                   |
| Configuration      | Separated from code, schema validation, environment separation and secret redaction.             |
| Performance Budget | Latency, memory, CPU/GPU, disk, network and startup budget regression testleri.           |
| Stability          | Retry/backoff, idempotency, circuit breaker, timeout, graceful degradation and recovery.  |
| Observability      | Structured log, metric, trace, correlation ID; secret/PII/health redaction.              |
| Documentation      | ADR, architecture, config reference, runbook, migration/rollback and known limitations.   |

## 19.3 Secure SDLC Gates

| **Stage**    | **Mandatory Controls**                                                                   |
|--------------|---------------------------------------------------------------------------------------|
| Inspect/Plan | Repo map, impact/gap, threat/privacy/financial impact, acceptance and rollback.        |
| Design       | Least privilege, segregation, failure modes, data class, observability.               |
| Develop      | Protected branch, peer review, secret scan, type/lint, unit tests.                    |
| Build        | SAST, SCA, SBOM, signed artefact, reproducible environment.                           |
| Test         | Integration, contract, regression, performance, chaos/failover, security, simulation. |
| Stage        | Paper/shadow, masked data, migration/rollback rehearsal.                              |
| Release      | Independent QA/QC, CISO/DPO/risk review as applicable, change approval.               |
| Operate      | SLO, telemetry, incident, drift, rollback and post-release review.                     |

## 19.4 Repo Health Audit

- Monthly: duplicate/dead code, stale branch/worktree, test coverage, complexity, dependency, CVE, secret, performance and disk usage report.

- Critical finding: owner, severity, root cause, temporary control, CAPA, due date, and verification.

- Cleaning can be automatically suggested; destructive changes are only executed with an approved change plan.

<a id="bolum-20"></a>
# 20. DATA, AI, MLOPS/LLMOPS AND MODEL GOVERNANCE



## 20.1 Data Governance

- Each dataset carries owner, source, license, timestamp, lineage, quality, privacy class and retention.

- Agents in the same decision loop use immutable shared snapshots; they do not re-download and re-calculate the same data.

- Ensures point-in-time correctness of the feature store; training-serving skew and leakage are tested.

- Layers are separated: raw, staging, validated, feature, model-output, and audit.

## 20.2 AI/LLM Permission Boundary

| **LLM/Agent Yapabilir**                                                  | **LLM/Agent Yapamaz**                                                  |
|--------------------------------------------------------------------------|------------------------------------------------------------------------|
| Description, summary, comparison, critique, hypothesis, report, and experiment proposal | Obtain final trading signal or override risk/validation |
| Bring information via research-based approach and RAG/CAG | Carrying secret, health data, or unnecessary personal data into prompt/log |
| Generate plan/diff/test proposal for code change | Deploy production code/config/parameters without approval |
| Analyze agent performance and performance gap | Increase own permissions, tool allowlist, or risk limits |

## 20.3 Model/Agent Monitoring

- Accuracy alone is not sufficient: calibration, drift, stability, latency, cost, explainability, security, and policy compliance are monitored.

- Champion–challenger, shadow testing, and canary approaches are applied.

- Changes to models/agents are recorded in the registry with version, owner, evidence, promotion, and rollback.

- Regression, jailbreak/prompt injection, and privacy leakage tests are mandatory after prompt/model updates.

<a id="bolum-21"></a>
# 21. CYBER SECURITY AND DIGITAL ASSET PROTECTION CONSTITUTION



Cybersecurity is not an afterthought control, but rather a matter of governance at the YKB and GM levels, and a default characteristic of the entire design. The control model aligns with the functions of the NIST CSF 2.0: GOVERN–IDENTIFY–PROTECT–DETECT–RESPOND–RECOVER.

## 21.1 Critical Assets

- API keys, private keys, account and wallet identifiers, authentication tokens.

- Source code, strategy/model artifacts, training data, decision memory, and audit logs.

- YKB personal data, email, financial records, and Health Vault.

- Repository, CI/CD, package supply chain, local LLM and agent tools.

## 21.2 Minimum Security Controls

| **Area**          | **Mandatory Measures**                                                                                   |
|-------------------|------------------------------------------------------------------------------------------------------|
| Identity & Access | MFA, least privilege, RBAC/ABAC, periodic review, JIT access, break-glass logging.                   |
| Secrets           | Vault/OS credential store, rotation, no hardcode/log/email, environment separation.                  |
| Exchange Security | Withdrawal off, IP restriction, read-only first, separate Spot/Futures keys, amount/venue scope.     |
| Endpoint/Network  | EDR, patching, firewall, segmentation, secure DNS, encrypted transport, remote access control.       |
| Application       | Threat model, secure coding, SAST/DAST/SCA, SBOM, signed artefact, dependency pinning.               |
| Data              | Encryption at rest/in transit, backup, integrity, DLP, masking, secure deletion.                     |
| Monitoring        | SIEM, anomaly detection, account/login/order/config/secret alerts, immutable audit.                  |
| Incident          | Triage, containment, credential revoke, evidence preservation, notification and lessons learned.     |
| Supply Chain      | Trusted registry, checksum/signature, provenance, license/CVE, compromised package response.         |
| AI Threats        | Prompt injection, tool abuse, data poisoning, model extraction, exfiltration, unsafe autonomy tests. |

## 21.3 Security Incident Severity

| **Level** | **Example**                                                                  | **Mandatory Action**                                                           |
|------------|----------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| SEV-1      | Secret/account compromise, unauthorized action, health data leak.          | Immediate isolate/revoke, YKB+CISO+DPO, incident command, legal assessment. |
| SEV-2      | Malware, privilege misuse, critical vulnerability, data integrity failure. | Contain, service restriction, RCA/CAPA, controlled recovery.                |
| SEV-3      | Failed attack, noncritical CVE, repeated auth anomaly.                     | Investigate, patch, monitor, trend report.                                  |
| SEV-4      | Policy deviation or low-risk warning.                                      | Backlog, owner, due date, verification.                                     |

<a id="bolum-22"></a>
# 22. KVKK, GDPR AND CCPA/CPRA PRIVACY FRAMEWORKS



## 22.1 Privacy-by-Design and Default

- Every new agent, data source, email report, Health Vault, analytics or model training activity starts with a data inventory and purpose definition.

- Data minimization, pseudonymization/masking, strict access, short retention, and privacy-safe defaults are applied.

- PIAs/DPIAs are mandatory for high-risk systematic monitoring, profiling, sensitive/health data, or new technology usage.

- Legal mechanism, contract, vendor risk, and transfer analysis are performed before personal data is sent to third-party LLM/cloud providers beyond the data subject.

## 22.2 Compliance Control Matrix

| **Framework** | **OEK Application**                                                                                                                                                                                                      |
|-------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| KVKK        | Compliance with law and good faith, accuracy/validity, specific/transparent/legal purpose, processing that is linked-restricted-measured, storage limits; data security; data subject rights; sufficient measures for special category data.                        |
| GDPR        | Lawfulness/transparency, purpose limitation, data minimisation, accuracy, storage limitation, integrity/confidentiality, accountability; privacy by design/default; security; DPIA and special-category health data controls. |
| CCPA/CPRA   | Notice, access/delete/correct, opt-out of sale/sharing, limit sensitive personal information, GPC; risk assessment, cybersecurity audit and ADMT requirements threshold-based analysis.                            |

## 22.3 Data Classes

| **Class**        | **Example**                                                 | **Control**                                                                          |
|------------------|-----------------------------------------------------------|--------------------------------------------------------------------------------------|
| PUBLIC           | Public market data and published content.                  | Source/license/provenance; still injection control.                                |
| INTERNAL         | Architecture, SOP, test, genel rapor.                           | Authenticated access, need-to-know.                                                  |
| CONFIDENTIAL     | Portfolio, P&L, wallet summary, strategy/model details.   | Encryption, strict RBAC, email redaction.                                            |
| RESTRICTED       | API secrets, identity, account, private financial data.   | Vault, JIT access, no email/prompt/log.                                              |
| SPECIAL / HEALTH | Medical history, test, medication, appointment, family history.           | Separate Health Vault, explicit consent/legal basis, minimum access, no financial reuse. |

## 22.4 Data Owner Rights and Data Lifecycle

- Notice/Notification, access/Access, correction/Correction, deletion/Deletion, restriction/Restriction, and portability/Portability applicability analysis.

- Retention schedule; secure deletion or anonymization upon purpose termination, backup deletion propagation, and legal hold.

- Vendor/DPA, subprocessor, breach notification, and data transfer records.

- Secret, detailed health data, identity, and unnecessary wallet/address information are not present in email reports.

<a id="bolum-23"></a>

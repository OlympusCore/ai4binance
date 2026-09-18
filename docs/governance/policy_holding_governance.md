---
document_id: AI4B-HOLDING-POL-001
title: AI4BINANCE Holding Governance
document_type: POLICY
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L2_GOVERNANCE_COMPLIANCE
authority_scope: holding_governance
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
canonical_path: docs/governance/policy_holding_governance.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# AI4BINANCE Holding Governance

## ELI10

This document is similar to company management rules. A user request is converted
into a safe work order, secret information is not distributed, and departments
only operate within their authority.


This document defines the fail-closed management rules for the AI4BINANCE
enterprise holding layer.

## Codex Prompt Intake

- Raw prompts written by Codex or the user may only be read by
  `GeneralManagerController`.
- Raw prompts are not forwarded to department managers, expert agents, meetings,
  committees, or interdepartmental messages.
- Departments are only provided with a redacted summary, purpose, constraints, scope, permissions,
  evidence references, and blocker list.
- Raw prompt evidence is stored as a `prompt-sha256:<hash>` reference, not as text.
- Prompt intake, prompt access decisions, and work-order creation events can be
  written to verified JSONL audit records through `EnterpriseAuditJournal`.
- Interdepartmental messages containing raw prompts, API keys, secret values, or
  wallet balances are stopped with `PROMPT_ACCESS_BLOCKED`.

## Safety Boundary

This layer generates order and management preview. It does not grant live order authority,
risk gates are not widened, and production parameters are not promoted.

Local computer profile, hardware, editor, and runtime details are stored only in
`docs/archive/reference_local_computer_profile.md`. Code, tests, reports, prompts, meeting notes, or other documents
must not copy these values; when needed, they may only use a `docs/archive/reference_local_computer_profile.md`
reference. QAQC verifies this boundary fail-closed through the
`COMPUTER_MD_PRIVACY_BOUNDARY` control.

## Written Approval Documentation Sync

According to the `WRITTEN_APPROVAL_DOC_SYNC` rule, when the user provides written
approval for system correction or improvement, the relevant `.md` instruction and
decision documents can be updated in the same bounded diff. This update only
records the redacted system rule, scope boundary, quality evidence, and blocker
status.

Raw prompts, secret values, local computer profile, wallet balances, or credentials
are not copied. If local computer information is needed, documents only use a
`docs/archive/reference_local_computer_profile.md` reference. A `.md` update alone is not sufficient application evidence;
the related code, tests, QAQC, and quality gate must also pass.

Updatable instruction surfaces are:

- `docs/registries/registry_documentation_index.md`
- `docs/governance/policy_holding_governance.md`
- `docs/compliance/registry_compliance_matrix.md`
- `docs/registries/registry_repository_folder_ownership_retention.md`
- `docs/governance/policy_skills_governance.md`
- `docs/governance/policy_model_adaptation_governance.md`

Default states are preserved:

- `NO_TRADE`
- `RESEARCH_ONLY`
- `HUMAN_REVIEW_REQUIRED`
- `LIVE_ORDER_BLOCKED`

## OEK Anayasal Emir Kaynagi

for `docs/governance/policy_organization_constitution_handbook.md`, `BoardDirective`, and the GM prompt-order chain
as the direct constitutional authority source. Every board directive must include
`OEK_AUTHORITY_SOURCE:docs/governance/policy_organization_constitution_handbook.md` and
must carry `OEK_CONSTITUTION_COMPLIANCE`; if these values are missing, the directive
is not created.

This source defines the order of authority, but does not include live trading, money transfer,
secret access, risk increase, production deployment, or model/strategy promotion.
It grants no authority. These areas also require human approval, quality, risk and
security checks, control evidence, and live gate requests.

## Quality Department System Audit

The Quality Department oversees the system with the `quality-system-audit` command:

```powershell
.\.venv\Scripts\python.exe -m ai4binance.cli quality-system-audit --format text
```

The audit covers the following controls:

- Independent control and veto authority of the `QUALITY_AUDIT` department.
- No local computer profile leakage outside `docs/archive/reference_local_computer_profile.md`.
- Raw prompts are read only by `GeneralManagerController`.
- Raw prompt leakage in interdepartmental messages is stopped with
  `PROMPT_ACCESS_BLOCKED`.
- Prompt intake, prompt access, and work-order audit event surfaces exist in
  `EnterpriseAuditJournal`.
- Skill linter, enterprise task tracker, corrective RAG gate, and model
  adaptation research board surfaces are importable.
- The agent lifecycle state machine defines `IDLE`, `PERCEIVE`, `REASON`,
  `PLAN`, `ACT`, `OBSERVE`, `HUMAN_CHECK`, `DONE`, and `ERROR` states as a typed
  contract.
- Local computer profile is stored only in `docs/archive/reference_local_computer_profile.md` and copying into other
  documents, code, test fixtures, or logs is prevented by the
  `COMPUTER_MD_PRIVACY_BOUNDARY` control.
- Written approval for system fixes in the relevant Markdown instructions
  surfaces is kept synchronized in a redacted and provable way by the
  `WRITTEN_APPROVAL_DOC_SYNC` control that verifies it.
- `OEK_CONSTITUTION_COMPLIANCE` control that verifies `docs/governance/policy_organization_constitution_handbook.md`
  exists as the canonical OEK Constitution, carries the `AI4B-OEK-003` / `3.0`
  identity, preserves immutable core principles, and verifies the
  `NO_TRADE` / `RESEARCH_ONLY` / `LIVE_ORDER_BLOCKED` boundary.
- `BoardDirective` contract cannot be created without
  `OEK_AUTHORITY_SOURCE:docs/governance/policy_organization_constitution_handbook.md` and `OEK_CONSTITUTION_COMPLIANCE`.
- The registered `oek-gap-analysis` surface ensures agent, skill, workflow, and
  config changes pass through manifest-backed OEK gap analysis. This surface
  applies OEK as a manifesto; however, it remains report-only and does not grant
  live processing, risk increase, secret access, or production promotion authority.
- Governance CLI commands are registered.
- This holding governance document should include the basic security terminology

The report remains `RESEARCH_ONLY` and `LIVE_ORDER_BLOCKED`. Audit findings
The correction action is suggested; it does not issue live orders, increase risk, or perform production transfers

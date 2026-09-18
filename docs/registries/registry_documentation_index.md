---
document_id: AI4B-DOC-REG-001
title: AI4BINANCE Documentation Map
document_type: REGISTRY
version: 1.0.3
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L5_REGISTRIES_ROADMAP
authority_scope: documentation_index
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: family_index
canonical_path: docs/registries/registry_documentation_index.md
machine_enforceable: true
audit_required: true
classification: INTERNAL
---

# Document Map — ELI10

## ELI10

This file is a map of the documentation hub. If you are curious about a
particular topic, it tells you which document to read; permanent rules live in
`docs`, and temporary operation records live in `runtime/reports`.

## Role Boundary

`docs/registries/registry_documentation_index.md` is the canonical
documentation family index and registration surface for the documentation hub.
It may define durable reading order, split-family relationships, and registry-
first navigation rules for governed documentation families.

`docs/README.md` is a docs-root navigator and interpretation aid. It may
summarize authority layers and point readers into the documentation hub, but it
must not replace this registry as the canonical family index.

If the two documents diverge:

- `docs/registries/registry_documentation_index.md` governs family-index and
  registration semantics;
- `docs/README.md` must be corrected as the lower-authority navigator surface.

The purpose of this folder is to make it easier to answer the question 'which document should I look at?'

## Canonical Docs Information Architecture

The canonical governed documentation navigation tree is:

```text
docs/
├── README.md
├── governance/
│   ├── constitution/
│   ├── authority/
│   ├── decision/
│   ├── execution/
│   ├── promotion/
│   └── repository/
├── architecture/
│   ├── system/
│   ├── data/
│   ├── decision/
│   ├── runtime/
│   └── integration/
├── standards/
├── policies/
├── controls/
├── contracts/
├── registries/
├── ontology/
├── workflows/
├── compliance/
├── security/
├── assurance/
├── runbooks/
├── adr/
└── references/
```

Legacy or support surfaces such as `archive/`, `procedures/`, `providers/`,
`reports/`, `roadmap/`, `schemas/`, and `templates/` may still exist during an
approved migration period, but they do not redefine the canonical `docs/`
taxonomy. Operational run-produced Markdown must use `runtime/reports/`.

1. If you're new, read the `README.md` file at the root.
2. Read `docs/governance/framework_core_vnext_governance.md` for Core vNext
   governance, schema, entity/relationship rules, output format, the
   policy-as-code backbone, the pyramid authority model, the digital-company
   operating model, LOOPS, and the Web Intelligence Radar contracts.
3. Read `docs/governance/instruction_core_custom_instructions.md` for the core
   custom instruction source governed as an L4 repository instruction.
4. Read `docs/governance/policy_organization_constitution_handbook.md` for the stable constitutional family index and OEK entrypoint.
5. Read `docs/governance/framework_core_vnext_governance.md` for the canonical core constitution that governs system boundaries, immutable principles, and fail-closed operating rules.
6. Read `docs/standards/standard_engineering_python_clean_code_vscode_development.md`
   for the Python clean-code and VS Code development standard governed under
   repository standards.
6.1. Read `docs/standards/standard_governed_object_enforcement.md` for the
   universal governed-object enforcement contract, profile coverage invariant,
   deterministic gate order, and fail-closed decision semantics.
6.2. Read `docs/standards/standard_technology_language_ownership.md` for the
   canonical language ownership, implementation-boundary, interoperability, and
   evidence-before-adoption rules.
6.3. Read `docs/standards/standard_terminology_governance.md` and
   `docs/standards/standard_repository_naming_governance.md` for their distinct
   L4 terminology and naming scopes. Their non-authoritative projections are
   connected to technology-language enforcement only through
   `config/governance/governance_enforcement_fabric.yaml`.
7. Read `docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md` for the Enterprise Auto-Audit, Continuous Improvement, and
   eight-domain security core instruction.
8. For Graph RAG, XAI Evidence Graph, AI Ethics, and the AI risk control plane,
   read `docs/governance/framework_trust_assurance_governance_plane.md`.
9. For the central audit and event-driven security trigger instruction,
   read `docs/workflows/instruction_audit_trigger_engine.md`.
10. CLI command for the weekly deep security audit
   `security-weekly-deep-audit`; the proof agreement is in `docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md`.
11. Read `ARCHITECTURE.md` to see how the parts are connected.
12. Read `docs/roadmap/registry_product_roadmap.md` to see what's been completed.
13. Read `docs/compliance/registry_compliance_matrix.md` to see the code proof of an allegation.
14. Read `docs/governance/policy_holding_governance.md` for the Holding/CEO/QAQC boundary.
15. Read `docs/governance/policy_skills_governance.md` for skill supply-chain and agent authority limits.
16. Read `docs/governance/policy_manifest_governance.md` for governed manifest registration,
   integrity, lock, hash, and approval requirements.
17. For model adaptation and fine-tuning limits
   read `docs/governance/policy_model_adaptation_governance.md`.
17.1. Read `docs/governance/policy_cuda_gpu_resource_usage.md` for CPU default,
   optional CUDA, and GPU arbitration rules.
17.2. Read `docs/registries/registry_gpu_compute_policy.md` for GPU workload
   profiles, lease kinds, telemetry fields, and runtime selection rules.
18. Read `docs/registries/registry_repository_folder_ownership_retention.md` for cleanup and retention decisions.
19. Read the registry-first governance files under `docs/registries/` for
    agents, strategies, models, indicators, parameters, policies, risk rules,
    workflows, data sources, and evidence.
20. For repository cleanup and stability audit runbook
    read `docs/runbooks/runbook_repository_cleanup_stability_audit.md`.
21. Temporary operation plans, diff plans, watchlists, and implementation
    reports use the `runtime/reports/operations/` folder.
22. Read `docs/providers/runbook_tradingview_mcp_codex_connection.md` for the TradingView connection.
23. Read `docs/contracts/interface_contract_read_only_evidence_mcp.md` for the read-only Codex/ChatGPT evidence layer.
24. `docs/contracts/interface_contract_binance_websocket_api_reference.md` is the index for split Binance WebSocket API reference snapshots; it does not prove that the current application uses WebSocket.
25. Read `docs/architecture/framework_external_intelligence_evidence_fabric.md` for the EIEF layer
    that integrates X, News, Reddit, Telegram, GitHub, Security, and Regulatory
    radars into one evidence factory.
26. Read `docs/workflows/instruction_technology_intelligence_analyzer.md` for
    the governed research criteria, scoring gates, and advisory-only authority
    boundary used by the Technology Intelligence Analyzer.
27. Read `docs/governance/policy_ai_management_system_scope.md` for the
    ISO/IEC 42001-aligned AIMS scope, boundaries, interested parties and
    readiness evidence requirements.
28. Read `docs/compliance/matrix_iso_42001_aims_crosswalk.md` and
    `docs/compliance/statement_of_applicability_iso_42001.md` for the internal
    AIMS crosswalk and statement of applicability.
29. Read `docs/registries/registry_ai_system_inventory.md` for the AI system
    inventory, intended uses, prohibited uses and oversight boundaries.
30. Read `docs/workflows/procedure_ai_risk_impact_assessment.md` and
    `docs/workflows/procedure_aims_nonconformity_corrective_action.md` for AIMS
    risk, impact, nonconformity and corrective-action workflows.
31. Read `docs/governance/framework_orchestration_ai_multi_agent.md` for the
    AI orchestration, AI agent orchestration, and multi-agent orchestration
    pyramid-management framework.
32. Read `docs/reports/governance/evidence_ai_orchestration_operational_readiness.md`,
    `docs/reports/governance/evidence_ai_orchestration_agent_review_records.md`,
    and `docs/reports/governance/evidence_ai_orchestration_risk_impact_records.md`
    for AI orchestration KPI evidence, per-agent review records, and AIMS
    risk-impact closure evidence.
33. Read `docs/reports/governance/evidence_aims_baseline_control_record.md`,
    `docs/reports/governance/evidence_aims_per_system_risk_impact_records.md`,
    `docs/reports/governance/evidence_aims_provider_control_review.md`,
    `docs/reports/governance/evidence_aims_internal_audit_schedule.md`,
    `docs/reports/governance/evidence_aims_management_review_minutes.md`,
    `docs/reports/governance/evidence_aims_capa_records.md`,
    `docs/reports/governance/report_platform_blocker_closure_map.md`, and
    `docs/reports/governance/report_repository_governance_findings.md` for the
    internal AIMS documentation baseline evidence package.
34. Read `docs/reports/governance/report_repository_governance_findings.md`
    for the repository governance findings summary that now points to the
    evidence registry, blocker closure map, and internal AIMS evidence package.

## Split Document Families

The largest governed Markdown files are kept as stable index documents and split
into smaller canonical files using the `document_type_domain_subject.md` naming
pattern.

| Index | Split files |
| --- | --- |
| `docs/contracts/interface_contract_binance_websocket_api_reference.md` | `docs/contracts/interface_contract_binance_websocket_api_foundation.md`, `docs/contracts/interface_contract_binance_websocket_api_session_authentication.md`, `docs/contracts/interface_contract_binance_websocket_api_general_requests.md`, `docs/contracts/interface_contract_binance_websocket_api_market_data.md`, `docs/contracts/interface_contract_binance_websocket_api_authentication_requests.md`, `docs/contracts/interface_contract_binance_websocket_api_order_requests.md`, `docs/contracts/interface_contract_binance_websocket_api_order_list_requests.md`, `docs/contracts/interface_contract_binance_websocket_api_account_requests.md`, `docs/contracts/interface_contract_binance_websocket_api_user_data_stream_requests.md` |
| `docs/governance/policy_organization_constitution_handbook.md` | `docs/governance/policy_organization_foundation_operating_model.md`, `docs/governance/policy_organization_authority_agent_lifecycle.md`, `docs/governance/policy_organization_market_strategy_validation.md`, `docs/governance/policy_organization_risk_security_privacy.md`, `docs/governance/policy_organization_improvement_quality_reporting.md`, `docs/governance/policy_organization_incident_change_appendices.md` |
| `docs/standards/standard_documentation_knowledge_governance.md` | `docs/standards/standard_governed_knowledge_metadata.md`, `docs/standards/standard_governed_knowledge_registry_change.md`, `docs/standards/standard_governed_knowledge_authority_workflow.md`, `docs/standards/standard_terminology_governance.md` |
| `docs/standards/standard_repository_file_governance.md` | `docs/standards/standard_repository_structure_governance.md`, `docs/standards/standard_repository_naming_governance.md`, `docs/standards/standard_repository_artifact_separation_governance.md`, `docs/standards/standard_repository_validator_governance.md` |
| `docs/templates/reference_governed_knowledge_object_template.md` | `docs/templates/reference_governed_schema_instruction_templates.md`, `docs/templates/reference_governed_policy_control_templates.md`, `docs/templates/reference_governed_contract_decision_templates.md`, `docs/templates/reference_governed_validation_evidence_templates.md`, `docs/templates/reference_governed_strategy_agent_templates.md`, `docs/templates/reference_governed_operations_learning_templates.md` |

## Registry-First Governance

These registry files define the canonical registration surfaces. They do not
grant live trading authority or promote candidates by their existence.

| Registry | Scope |
| --- | --- |
| `docs/registries/registry_agent_registry.md` | Agent identities, owners, lifecycle and authority boundaries |
| `docs/registries/registry_strategy_registry.md` | Strategy identities, market scope, lifecycle and promotion state |
| `docs/registries/registry_model_registry.md` | Model identities, permitted use and prohibited use |
| `docs/registries/registry_indicator_registry.md` | Canonical indicator calculations and validation references |
| `docs/registries/registry_parameter_registry.md` | Governed parameters and risk-sensitive defaults |
| `docs/registries/registry_policy_registry.md` | Active policy source-of-truth references |
| `docs/registries/registry_risk_rule_registry.md` | Deterministic risk veto rules |
| `docs/registries/registry_workflow_registry.md` | Governed workflows, triggers, side effects and evidence outputs |
| `docs/registries/registry_data_source_registry.md` | Data provenance, freshness and degraded-state rules |
| `docs/registries/registry_evidence_registry.md` | Audit, validation and decision-lineage evidence records |
| `docs/registries/registry_ai_system_inventory.md` | AI system identities, intended uses, prohibited uses, oversight and AIMS evidence status |

## One-sentence status

Research and paper infrastructure is operational; WebSocket/Ed25519, real wallet wiring,
Live trading is disabled because long-term OOS proof and live order execution are not completed.

## OEK Constitutional Source

`docs/governance/policy_organization_constitution_handbook.md` is the stable
OEK constitutional family index and `BoardDirective` entrypoint. The canonical
core constitution file for immutable governance semantics is
`docs/governance/framework_core_vnext_governance.md`.

The GM prompt-order chain uses
`OEK_AUTHORITY_SOURCE:docs/governance/policy_organization_constitution_handbook.md`
for the stable constitutional entrypoint and cannot generate directives without
`OEK_CONSTITUTION_COMPLIANCE`. The handbook preserves the order hierarchy and
family index semantics; it does not replace the canonical core constitution and
does not grant live trading, money transfer, secret access, risk increase,
production deployment, or promotion authority by itself.

## Local Privacy Boundary

Local computer profile is only maintained within `docs/archive/reference_local_computer_profile.md`. Other Markdown,
code, test fixture, log or reports do not copy these special values; instead,
only reference to `docs/archive/reference_local_computer_profile.md` is used when necessary.

## Software Approval and Instruction Synchronization

When a user provides software approval for a system update, the relevant `.md`
instruction can be updated within the same bounded diff. The
`WRITTEN_APPROVAL_DOC_SYNC` rule only records the revised system rule, scope
boundary, quality proof, and blocker status; values outside the special
`docs/archive/reference_local_computer_profile.md` profile and any secret values must not be copied.

A stronger constitutional lock is applied for code changes that alter behavior:
in the first approval, ELI10 system impact, plus/minus, affected contract, validation and
live status are explained. In reapproval or partial approval, the policy related to the code,
instructions, schema, entity/relationship rules, output format and framework
documents are synchronized and revised within the same bounded diff. If the code conflicts with written
constitution, the change is not considered completed.

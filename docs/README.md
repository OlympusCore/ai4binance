---
document_id: AI4B-DOCS-REG-001
title: AI4Binance Documentation Authority Pyramid
document_type: REGISTRY
version: 1.0.2
status: ACTIVE
owner: Enterprise Governance
authority_level: REFERENCE
authority_layer: L9_REFERENCES_TEMPLATES
authority_scope: documentation_readme
content_role: EXPLANATORY
source_of_truth: false
machine_enforceable: false
audit_required: true
classification: INTERNAL
canonical_path: docs/README.md
---

# AI4Binance Documentation Authority Pyramid

This index maps `./docs/**` to the AI4Binance authority hierarchy.
It is an index and interpretation aid, not a source of higher authority.

`docs/README.md` is an approved documentation-index filename exception. It is a
navigation entrypoint, not a canonical naming-pattern violation.

## Status

- Artifact: `docs/README.md`
- Scope: `docs/**`
- Mode: `DOCUMENTATION_INDEX`
- Default execution posture: `PAPER_TRADING`
- Default live execution posture: `LIVE_EXECUTION_DISABLED`
- LLM authority: `ADVISORY_ONLY`

## Authority Principle

Lower-level documentation may specialize higher-level documentation, but it must not contradict, weaken, bypass, or silently reinterpret it.

If documents conflict, the repository must fail closed and apply the higher-authority document until the conflict is resolved.

```text
External Mandatory Constraints
        ↓
Core Constitution
        ↓
Governance / Compliance
        ↓
Canonical Contracts / Schemas
        ↓
Repository Standards / Controls
        ↓
Registries / Roadmap
        ↓
Architecture / Ontology / ADR
        ↓
Workflows / Procedures / Runbooks / Providers
        ↓
Reports / Evidence / Inventories
        ↓
References / Templates / Archive
```

## Authority Layer 0 - External Mandatory Constraints

External mandatory constraints are not stored as a single local source of truth under `./docs/**`, but local documentation may reference or implement them.

Examples include applicable laws, regulations, exchange rules, security requirements, ISO standards, OpenAPI/JSON Schema conventions, Binance interface requirements, and mandatory platform constraints.

No local document may override mandatory external constraints.

## Index Artifact

This file is the navigation surface for `docs/**`; it is not a higher-authority source than the documents it lists.

## Role Boundary

`docs/README.md` is the docs-root navigator and interpretation aid for
`docs/**`.

`docs/registries/registry_documentation_index.md` is the canonical
documentation family index and registration surface. It governs durable
family-index semantics, split-family relationships, and registry-first
navigation rules when this README and the registry differ.

This README may summarize authority layers and provide an entrypoint into the
hub, but it must not redefine the canonical family index role.

## Canonical Docs Information Architecture

The canonical documentation information architecture for `docs/` is:

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

This tree is the target source-of-truth navigation model for governed
documentation under `docs/`.

Legacy or support documentation roots that still exist physically, such as
`archive/`, `procedures/`, `providers/`, `reports/`, `roadmap/`, `schemas/`,
and `templates/`, are transitional surfaces. They may remain readable during
approved migration work, but they do not redefine the canonical `docs/`
taxonomy.

| Filename | Summary |
|---|---|
| [README.md](README.md) | Current documentation authority index for `docs/**`; navigator only, not a higher-authority source. |

## ELI10

This index helps people and agents find governed documents in `docs/` and related report surfaces. It is a navigation aid, not a source of higher authority.

## Authority Layer 1 - Core Constitution

These documents define the highest local project authority and behavioral boundaries.

| Filename | Summary |
|---|---|
| [governance/framework_core_vnext_governance.md](governance/framework_core_vnext_governance.md) | Canonical core constitution for AI4BINANCE governance semantics, system boundaries, and fail-closed operating rules. |
| [governance/policy_organization_constitution_handbook.md](governance/policy_organization_constitution_handbook.md) | Stable constitutional family index and OEK entrypoint that organizes the constitution policy family without replacing the canonical constitution file. |

## Authority Layer 2 - Governance and Compliance

These documents define governance systems, compliance posture, assurance expectations, and management-system alignment.

| Filename | Summary |
|---|---|
| [compliance/matrix_iso_42001_aims_crosswalk.md](compliance/matrix_iso_42001_aims_crosswalk.md) | AI4BINANCE ISO IEC 42001 AIMS Crosswalk Matrix |
| [compliance/registry_compliance_matrix.md](compliance/registry_compliance_matrix.md) | AI4BINANCE Compliance Matrix |
| [compliance/statement_of_applicability_iso_42001.md](compliance/statement_of_applicability_iso_42001.md) | AI4BINANCE ISO IEC 42001 Statement of Applicability |
| [governance/framework_decision_governance_engine.md](governance/framework_decision_governance_engine.md) | AI4BINANCE Decision Governance Engine |
| [governance/framework_orchestration_ai_multi_agent.md](governance/framework_orchestration_ai_multi_agent.md) | AI4BINANCE AI Orchestration and Multi-Agent Orchestration Framework |
| [governance/framework_trust_assurance_governance_plane.md](governance/framework_trust_assurance_governance_plane.md) | AI4BINANCE Trust Assurance Governance Plane |
| [governance/instruction_core_custom_instructions.md](governance/instruction_core_custom_instructions.md) | AI4BINANCE Core Custom Instructions |
| [governance/policy_ai_management_system_scope.md](governance/policy_ai_management_system_scope.md) | AI4BINANCE AI Management System Scope |
| [governance/policy_cuda_gpu_resource_usage.md](governance/policy_cuda_gpu_resource_usage.md) | AI4BINANCE CUDA and GPU Resource Usage Policy |
| [governance/policy_holding_governance.md](governance/policy_holding_governance.md) | AI4BINANCE Holding Governance |
| [governance/policy_manifest_governance.md](governance/policy_manifest_governance.md) | AI4BINANCE Manifest Governance Policy |
| [governance/policy_model_adaptation_governance.md](governance/policy_model_adaptation_governance.md) | AI4BINANCE Model Adaptation Governance |
| [governance/policy_organization_authority_agent_lifecycle.md](governance/policy_organization_authority_agent_lifecycle.md) | AI4BINANCE Organization Authority and Agent Lifecycle Policy |
| [governance/policy_organization_foundation_operating_model.md](governance/policy_organization_foundation_operating_model.md) | AI4BINANCE Organization Foundation and Operating Model Policy |
| [governance/policy_organization_improvement_quality_reporting.md](governance/policy_organization_improvement_quality_reporting.md) | AI4BINANCE Organization Improvement Quality and Reporting Policy |
| [governance/policy_organization_incident_change_appendices.md](governance/policy_organization_incident_change_appendices.md) | AI4BINANCE Organization Incident Change and Appendices Policy |
| [governance/policy_organization_market_strategy_validation.md](governance/policy_organization_market_strategy_validation.md) | AI4BINANCE Organization Market Strategy and Validation Policy |
| [governance/policy_organization_risk_security_privacy.md](governance/policy_organization_risk_security_privacy.md) | AI4BINANCE Organization Risk Security and Privacy Policy |
| [governance/policy_skills_governance.md](governance/policy_skills_governance.md) | AI4BINANCE Skills Governance |

## Authority Layer 3 - Canonical Contracts and Schemas

These documents define interface contracts, API contracts, event contracts, and schema references. They constrain implementation and adapter behavior.

| Filename | Summary |
|---|---|
| [contracts/event_contract_public_spot_stream.md](contracts/event_contract_public_spot_stream.md) | AI4BINANCE Public Spot Stream Contract |
| [contracts/interface_contract_binance_websocket_api_account_requests.md](contracts/interface_contract_binance_websocket_api_account_requests.md) | Binance WebSocket API Account Requests Reference |
| [contracts/interface_contract_binance_websocket_api_authentication_requests.md](contracts/interface_contract_binance_websocket_api_authentication_requests.md) | Binance WebSocket API Authentication Requests Reference |
| [contracts/interface_contract_binance_websocket_api_foundation.md](contracts/interface_contract_binance_websocket_api_foundation.md) | Binance WebSocket API Foundation Reference |
| [contracts/interface_contract_binance_websocket_api_general_requests.md](contracts/interface_contract_binance_websocket_api_general_requests.md) | Binance WebSocket API General Requests Reference |
| [contracts/interface_contract_binance_websocket_api_market_data.md](contracts/interface_contract_binance_websocket_api_market_data.md) | Binance WebSocket API Market Data Reference |
| [contracts/interface_contract_binance_websocket_api_order_list_requests.md](contracts/interface_contract_binance_websocket_api_order_list_requests.md) | Binance WebSocket API Order List Requests Reference |
| [contracts/interface_contract_binance_websocket_api_order_requests.md](contracts/interface_contract_binance_websocket_api_order_requests.md) | Binance WebSocket API Order Requests Reference |
| [contracts/interface_contract_binance_websocket_api_reference.md](contracts/interface_contract_binance_websocket_api_reference.md) | Binance WebSocket API Reference |
| [contracts/interface_contract_binance_websocket_api_session_authentication.md](contracts/interface_contract_binance_websocket_api_session_authentication.md) | Binance WebSocket API Session Authentication Reference |
| [contracts/interface_contract_binance_websocket_api_user_data_stream_requests.md](contracts/interface_contract_binance_websocket_api_user_data_stream_requests.md) | Binance WebSocket API User Data Stream Requests Reference |
| [contracts/interface_contract_cli_command.md](contracts/interface_contract_cli_command.md) | AI4BINANCE CLI Command Contract |
| [contracts/interface_contract_live_order_lifecycle.md](contracts/interface_contract_live_order_lifecycle.md) | AI4BINANCE Live Order Lifecycle Contract |
| [contracts/interface_contract_mcp_fabric.md](contracts/interface_contract_mcp_fabric.md) | AI4BINANCE MCP Fabric Interface Contract |
| [contracts/interface_contract_read_only_evidence_mcp.md](contracts/interface_contract_read_only_evidence_mcp.md) | AI4BINANCE Read-Only Evidence MCP |
| [schemas/reference_repository_artifact_schema.md](schemas/reference_repository_artifact_schema.md) | AI4BINANCE Repository Artifact Schema |

## Authority Layer 4 - Repository Standards, Controls, and Quality Policies

These documents define repository-level rules, controls, naming, validation, file governance, and quality policy.

| Filename | Summary |
|---|---|
| [controls/control_repository_validation_rules.md](controls/control_repository_validation_rules.md) | AI4BINANCE Repository Validation Rules |
| [policies/quality/coverage_improvement_strategy_policy.md](policies/quality/coverage_improvement_strategy_policy.md) | AI4BINANCE Coverage Improvement Strategy Policy |
| [standards/standard_blocker_taxonomy_enforcement.md](standards/standard_blocker_taxonomy_enforcement.md) | AI4BINANCE Blocker Taxonomy and Enforcement Standard |
| [standards/standard_documentation_knowledge_governance.md](standards/standard_documentation_knowledge_governance.md) | AI4BINANCE Documentation and Knowledge Governance Core Standard |
| [standards/standard_engineering_python_clean_code_vscode_development.md](standards/standard_engineering_python_clean_code_vscode_development.md) | AI4BINANCE Python Clean Code and VS Code Development Guide |
| [standards/standard_governed_knowledge_authority_workflow.md](standards/standard_governed_knowledge_authority_workflow.md) | AI4BINANCE Governed Knowledge Authority and Workflow Standard |
| [standards/standard_governed_knowledge_metadata.md](standards/standard_governed_knowledge_metadata.md) | AI4BINANCE Governed Knowledge Metadata Standard |
| [standards/standard_governed_knowledge_registry_change.md](standards/standard_governed_knowledge_registry_change.md) | AI4BINANCE Governed Knowledge Registry and Change Standard |
| [standards/standard_repository_artifact_separation_governance.md](standards/standard_repository_artifact_separation_governance.md) | AI4BINANCE Repository Artifact Separation Governance Standard |
| [standards/standard_repository_file_governance.md](standards/standard_repository_file_governance.md) | AI4BINANCE Repository File Governance Standard |
| [standards/standard_repository_naming_governance.md](standards/standard_repository_naming_governance.md) | AI4BINANCE Repository Naming Governance Standard |
| [standards/standard_repository_structure_governance.md](standards/standard_repository_structure_governance.md) | AI4BINANCE Repository Structure Governance Standard |
| [standards/standard_repository_validator_governance.md](standards/standard_repository_validator_governance.md) | AI4BINANCE Repository Validator Governance Standard |
| [standards/standard_terminology_governance.md](standards/standard_terminology_governance.md) | AI4BINANCE Global Terminology and Taxonomy Standard |
| [standards/standard_technology_language_ownership.md](standards/standard_technology_language_ownership.md) | AI4BINANCE Technology Language Ownership and Usage Standard |

## Authority Layer 5 - Registries and Roadmap

These documents record governed objects, ownership, lifecycle status, and traceability.

| Filename | Summary |
|---|---|
| [registries/registry_agent_registry.md](registries/registry_agent_registry.md) | AI4BINANCE Agent Registry |
| [registries/registry_ai_system_inventory.md](registries/registry_ai_system_inventory.md) | AI4BINANCE AI System Inventory |
| [registries/registry_data_source_registry.md](registries/registry_data_source_registry.md) | AI4BINANCE Data Source Registry |
| [registries/registry_documentation_index.md](registries/registry_documentation_index.md) | AI4BINANCE Documentation Map |
| [registries/registry_evidence_registry.md](registries/registry_evidence_registry.md) | AI4BINANCE Evidence Registry |
| [registries/registry_gpu_compute_policy.md](registries/registry_gpu_compute_policy.md) | AI4BINANCE GPU Compute Policy Registry |
| [registries/registry_indicator_registry.md](registries/registry_indicator_registry.md) | AI4BINANCE Indicator Registry |
| [registries/registry_model_registry.md](registries/registry_model_registry.md) | AI4BINANCE Model Registry |
| [registries/registry_parameter_registry.md](registries/registry_parameter_registry.md) | AI4BINANCE Parameter Registry |
| [registries/registry_policy_registry.md](registries/registry_policy_registry.md) | AI4BINANCE Policy Registry |
| [registries/registry_repository_folder_ownership_retention.md](registries/registry_repository_folder_ownership_retention.md) | AI4BINANCE Folder Ownership Registry |
| [registries/registry_risk_rule_registry.md](registries/registry_risk_rule_registry.md) | AI4BINANCE Risk Rule Registry |
| [registries/registry_strategy_registry.md](registries/registry_strategy_registry.md) | AI4BINANCE Strategy Registry |
| [registries/registry_workflow_registry.md](registries/registry_workflow_registry.md) | AI4BINANCE Workflow Registry |
| [roadmap/registry_product_roadmap.md](roadmap/registry_product_roadmap.md) | AI4BINANCE Roadmap |

## Authority Layer 6 - Architecture, Ontology, and ADRs

These documents describe system architecture, decision records, and semantic structure. They must remain aligned with higher authority.

| Filename | Summary |
|---|---|
| [adr/adr_canonical_repository_tree.md](adr/adr_canonical_repository_tree.md) | AI4BINANCE Canonical Repository Tree Decision |
| [architecture/framework_architecture_overview.md](architecture/framework_architecture_overview.md) | AI4BINANCE Architecture Overview |
| [architecture/framework_external_intelligence_evidence_fabric.md](architecture/framework_external_intelligence_evidence_fabric.md) | External Intelligence and Evidence Fabric Architecture |
| [ontology/entity_rule_repository_artifact.md](ontology/entity_rule_repository_artifact.md) | AI4BINANCE RepositoryArtifact Ontology Note |

## Authority Layer 7 - Workflows, Procedures, Runbooks, and Providers

These documents define operational steps, repeatable execution guidance, and provider-adapter support.

| Filename | Summary |
|---|---|
| [procedures/procedure_social_publishing_gateway.md](procedures/procedure_social_publishing_gateway.md) | AI4BINANCE Social Publishing Gateway |
| [procedures/procedure_source_project_integration.md](procedures/procedure_source_project_integration.md) | AI4BINANCE Source Project Integration |
| [providers/instruction_claude_provider.md](providers/instruction_claude_provider.md) | AI4Binance Claude Provider Instructions |
| [providers/instruction_codex_provider.md](providers/instruction_codex_provider.md) | AI4Binance Codex Provider Instructions |
| [providers/runbook_tradingview_mcp_codex_connection.md](providers/runbook_tradingview_mcp_codex_connection.md) | Codex TradingView MCP ELI10 Guide |
| [runbooks/runbook_read_only_runtime.md](runbooks/runbook_read_only_runtime.md) | AI4BINANCE Read-Only Runtime |
| [runbooks/runbook_repository_cleanup_stability_audit.md](runbooks/runbook_repository_cleanup_stability_audit.md) | AI4BINANCE Repository Cleanup and Stability Audit |
| [runbooks/runbook_repository_migration_hygiene.md](runbooks/runbook_repository_migration_hygiene.md) | AI4BINANCE Repository Migration and Hygiene Runbook |
| [security/runbook_norton_360_allowlist_windows.md](security/runbook_norton_360_allowlist_windows.md) | AI4BINANCE Norton 360 Allowlist for Windows |
| [security/runbook_security_tooling.md](security/runbook_security_tooling.md) | AI4BINANCE Security Tooling |
| [workflows/instruction_audit_trigger_engine.md](workflows/instruction_audit_trigger_engine.md) | AI4BINANCE Audit Trigger Engine Instruction |
| [workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md](workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md) | AI4BINANCE Enterprise Auto-Audit and Continuous Improvement Engine Instruction |
| [workflows/instruction_technology_intelligence_analyzer.md](workflows/instruction_technology_intelligence_analyzer.md) | AI4BINANCE Technology Intelligence Analyzer Instruction |
| [workflows/procedure_ai_risk_impact_assessment.md](workflows/procedure_ai_risk_impact_assessment.md) | AI4BINANCE AI Risk and Impact Assessment Procedure |
| [workflows/procedure_aims_nonconformity_corrective_action.md](workflows/procedure_aims_nonconformity_corrective_action.md) | AI4BINANCE AIMS Nonconformity and Corrective Action Procedure |
| [workflows/procedure_continuous_skill_discovery.md](workflows/procedure_continuous_skill_discovery.md) | AI4BINANCE Continuous Skill Discovery |
| [workflows/runbook_github_radar_engine.md](workflows/runbook_github_radar_engine.md) | AI4BINANCE GitHub Radar Engine |
| [workflows/runbook_governed_software_factory.md](workflows/runbook_governed_software_factory.md) | AI4BINANCE Factory Operating Guide |
| [workflows/runbook_nightly_quality_triage.md](workflows/runbook_nightly_quality_triage.md) | AI4BINANCE Nightly Quality Triage |

## Authority Layer 8 - Reports, Evidence, and Inventories

These documents record findings, audit outputs, evidence requirements, and machine-readable inventories. They do not override higher-level governance.

| Filename | Summary |
|---|---|
| [reports/governance/evidence_ai_orchestration_agent_review_records.md](reports/governance/evidence_ai_orchestration_agent_review_records.md) | AI4BINANCE AI Orchestration Agent Review Records |
| [reports/governance/evidence_ai_orchestration_operational_readiness.md](reports/governance/evidence_ai_orchestration_operational_readiness.md) | AI4BINANCE AI Orchestration Operational Readiness Evidence |
| [reports/governance/evidence_ai_orchestration_risk_impact_records.md](reports/governance/evidence_ai_orchestration_risk_impact_records.md) | AI4BINANCE AI Orchestration AIMS Risk and Impact Records |
| [reports/governance/evidence_aims_baseline_control_record.md](reports/governance/evidence_aims_baseline_control_record.md) | AI4BINANCE AIMS Baseline Control Record |
| [reports/governance/evidence_aims_capa_records.md](reports/governance/evidence_aims_capa_records.md) | AI4BINANCE AIMS CAPA Records |
| [reports/governance/evidence_aims_internal_audit_schedule.md](reports/governance/evidence_aims_internal_audit_schedule.md) | AI4BINANCE AIMS Internal Audit Schedule |
| [reports/governance/evidence_aims_management_review_minutes.md](reports/governance/evidence_aims_management_review_minutes.md) | AI4BINANCE AIMS Management Review Minutes |
| [reports/governance/evidence_aims_per_system_risk_impact_records.md](reports/governance/evidence_aims_per_system_risk_impact_records.md) | AI4BINANCE AIMS Per-System Risk and Impact Records |
| [reports/governance/evidence_aims_provider_control_review.md](reports/governance/evidence_aims_provider_control_review.md) | AI4BINANCE AIMS Provider Control Review |
| [reports/governance/report_documentation_taxonomy_alignment_diffplan.md](reports/governance/report_documentation_taxonomy_alignment_diffplan.md) | Bounded diff plan for repairing `docs/README.md` authority-layer indexing and report taxonomy semantics. |
| [reports/governance/report_governance_migration_map.md](reports/governance/report_governance_migration_map.md) | AI4BINANCE Repository Governance Migration Map |
| [reports/governance/report_platform_blocker_closure_map.md](reports/governance/report_platform_blocker_closure_map.md) | AI4BINANCE Platform Blocker Closure Map |
| [reports/governance/report_repository_governance_findings.md](reports/governance/report_repository_governance_findings.md) | AI4BINANCE Repository Governance Findings |
| [reports/governance/report_repository_layer_file_inventory.md](reports/governance/report_repository_layer_file_inventory.md) | AI4BINANCE Repository Layer File Inventory |
| [reports/governance/report_repository_path_surface_inventory.md](reports/governance/report_repository_path_surface_inventory.md) | AI4BINANCE Repository Path Surface Inventory |
| [reports/governance/report_repository_structure_diffplan.md](reports/governance/report_repository_structure_diffplan.md) | AI4BINANCE Repository Structure Diff Plan |
| [reports/governance/report_runtime_state_migration_manifest.md](reports/governance/report_runtime_state_migration_manifest.md) | AI4BINANCE Runtime State Migration Manifest |
| [reports/governance/repository_governance_inventory.json](reports/governance/repository_governance_inventory.json) | Machine-readable repository governance inventory for audit and traceability. |
| [reports/report_documentation_knowledge_governance_split_manifest.md](reports/report_documentation_knowledge_governance_split_manifest.md) | AI4BINANCE Documentation Knowledge Governance Split Manifest |
| [reports/report_repository_file_governance_split_manifest.md](reports/report_repository_file_governance_split_manifest.md) | AI4BINANCE Repository File Governance Split Manifest |

## Authority Layer 9 - References and Templates

These folders support implementation, review, or documentation generation. They do not define authority unless explicitly adopted by higher-level documents.

| Filename | Summary |
|---|---|
| [references/reference_global_terminology_and_taxonomy.md](references/reference_global_terminology_and_taxonomy.md) | AI4BINANCE Global Terminology and Taxonomy Reference |
| [references/reference_governed_knowledge_taxonomy.md](references/reference_governed_knowledge_taxonomy.md) | AI4BINANCE Governed Knowledge Taxonomy Reference |
| [templates/reference_governed_contract_decision_templates.md](templates/reference_governed_contract_decision_templates.md) | Governed Contract and Decision Templates Reference |
| [templates/reference_governed_knowledge_object_template.md](templates/reference_governed_knowledge_object_template.md) | AI4BINANCE Governed Knowledge Object Templates |
| [templates/reference_governed_operations_learning_templates.md](templates/reference_governed_operations_learning_templates.md) | Governed Operations and Learning Templates Reference |
| [templates/reference_governed_policy_control_templates.md](templates/reference_governed_policy_control_templates.md) | Governed Policy Control and Standard Templates Reference |
| [templates/reference_governed_schema_instruction_templates.md](templates/reference_governed_schema_instruction_templates.md) | Governed Schema and Instruction Templates Reference |
| [templates/reference_governed_strategy_agent_templates.md](templates/reference_governed_strategy_agent_templates.md) | Governed Strategy Agent and Authority Templates Reference |
| [templates/reference_governed_validation_evidence_templates.md](templates/reference_governed_validation_evidence_templates.md) | Governed Validation and Evidence Templates Reference |

## Authority Layer 10 - Archive and Structural Placeholders

Archive content is retained for history and traceability. Structural placeholders keep folder shape only and do not carry substantive authority.

| Filename | Summary |
|---|---|
| [adr/.gitkeep](adr/.gitkeep) | Structural placeholder that preserves the ADR folder; no substantive authority. |
| [archive/reference_local_computer_profile.md](archive/reference_local_computer_profile.md) | Local-only private machine profile for AI4BINANCE development; do not sync or publish to cloud systems. |
| [ontology/.gitkeep](ontology/.gitkeep) | Structural placeholder that preserves the ontology folder; no substantive authority. |

## Interpretation Rules

1. A file named `framework_*` usually defines a governed conceptual or architectural framework.
2. A file named `policy_*` usually defines normative rules and constraints.
3. A file named `standard_*` usually defines repository-wide rules, conventions, and validation expectations.
4. A file named `interface_contract_*` or `event_contract_*` defines implementation-facing contracts.
5. A file named `registry_*` records governed objects, ownership, lifecycle status, and traceability.
6. A file named `control_*` defines enforceable or auditable controls.
7. A file named `procedure_*` defines operational steps.
8. A file named `runbook_*` defines repeatable operational execution guidance.
9. A file named `report_*` records findings or analysis and does not override policy.
10. A file named `evidence_*` records evidence and does not override policy.
11. A file inside `archive/` is non-authoritative unless explicitly reactivated.

## Conflict Handling

When documentation conflicts, the higher-authority document governs until a formal resolution updates the source of truth.

If the conflict affects trading, execution, risk, governance, validation, security, compliance, or live-order behavior, the system must return a fail-closed result such as:

```text
GOVERNANCE_CONFLICT
RUNNING_WITH_BLOCKERS
NO_TRADE
LIVE_ORDER_BLOCKED
```

## Maintenance Rules

- This README must be updated when files are added, moved, renamed, deprecated, or promoted under `./docs/**`.
- This README must not silently reclassify a document into a higher authority layer without corresponding governance evidence.
- New files under `./docs/**` should include governed metadata where applicable.
- Generated reports and evidence must not be promoted to normative authority without review.
- Archive files must remain non-authoritative by default.
- This README remains an approved `DOCUMENTATION_INDEX` exception to the
  `<document_type>_<domain>_<subject>.md` filename rule.
- `docs/README.md` is an index and interpretation aid; it is not higher authority than the documents it lists.

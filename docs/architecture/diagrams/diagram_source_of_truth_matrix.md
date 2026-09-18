---
document_id: AI4B-ARCH-DIAG-SOT-001
title: Architecture Diagram Source-of-Truth Matrix
document_type: REFERENCE
version: 1.0.0
status: ACTIVE
owner: Enterprise Architecture
authority_level: INFORMATIONAL
authority_layer: L6_ARCHITECTURE_ONTOLOGY_ADR
authority_scope: architecture_diagram_projection
authority_effect: EVIDENCE_ONLY
content_role: EXPLANATORY
source_of_truth: false
source_of_truth_scope: reference
canonical_path: docs/architecture/diagrams/diagram_source_of_truth_matrix.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# Architecture Diagram Source-of-Truth Matrix

## ELI10

This matrix maps P0 diagrams to governing repository evidence. Diagrams remain `source_of_truth: false`.

| Diagram | Title | Repository evidence | Status |
| --- | --- | --- | --- |
| `D003` | Canonical End-to-End Architecture Diagram | `docs/governance/framework_core_vnext_governance.md`<br>`docs/architecture/framework_architecture_overview.md`<br>`docs/registries/registry_logical_architecture.yaml` | `CURRENT_PARTIAL` |
| `D101` | Authority Pyramid | `AGENTS.md`<br>`docs/governance/framework_core_vnext_governance.md`<br>`docs/registries/registry_authority_graph.yaml`<br>`src/ai4binance/governance/enforcement/engine.py` | `CURRENT_PARTIAL` |
| `D104` | Governance Control Plane | `AGENTS.md`<br>`docs/governance/framework_core_vnext_governance.md`<br>`docs/registries/registry_authority_graph.yaml`<br>`src/ai4binance/governance/enforcement/engine.py` | `CURRENT_PARTIAL` |
| `D202` | Modular Monorepo Architecture | `docs/architecture/framework_architecture_overview.md`<br>`docs/registries/registry_logical_architecture.yaml`<br>`src/ai4binance/governance/architecture/graph.py` | `CURRENT_PARTIAL` |
| `D204` | Dependency Direction Diagram | `docs/architecture/framework_architecture_overview.md`<br>`docs/registries/registry_logical_architecture.yaml`<br>`src/ai4binance/governance/architecture/graph.py` | `CURRENT_PARTIAL` |
| `D310` | Canonical Market Data Architecture | `src/ai4binance/exchange/client.py`<br>`src/ai4binance/data/acquisition.py`<br>`src/ai4binance/data/market_history_continuous.py`<br>`schemas/snapshots/market_snapshot.schema.json` | `CURRENT_PARTIAL` |
| `D406` | Immutable Shared Snapshot Flow | `src/ai4binance/data/acquisition.py`<br>`src/ai4binance/agents/orchestrator.py`<br>`schemas/snapshots/market_snapshot.schema.json` | `CURRENT_PARTIAL` |
| `D501` | Canonical Event Fabric | `src/ai4binance/events/models.py`<br>`src/ai4binance/events/bus.py`<br>`src/ai4binance/events/journal.py`<br>`schemas/events/event_envelope.schema.json` | `CURRENT_PARTIAL` |
| `D601` | Intelligence Capability Map | `src/ai4binance/agents/catalog.py`<br>`src/ai4binance/agents/preflight.py`<br>`src/ai4binance/agents/bundles.py`<br>`src/ai4binance/agents/orchestrator.py` | `CURRENT_PARTIAL` |
| `D701` | Multi-TF Architecture | `src/ai4binance/research/futures_multitf.py`<br>`src/ai4binance/data/market_history_continuous.py`<br>`src/ai4binance/application/opportunity_monitor.py` | `CURRENT_PARTIAL` |
| `D901` | Evidence Architecture | `src/ai4binance/governance/evidence_contracts.py`<br>`src/ai4binance/external_intel/evidence/evidence_graph.py`<br>`schemas/evidence/evidence_bundle.schema.json` | `CURRENT_PARTIAL` |
| `D1102` | Risk Engine | `src/ai4binance/risk.py`<br>`src/ai4binance/agents/risk_gate.py`<br>`src/ai4binance/governance/risk_assessment.py`<br>`schemas/risk/risk_assessment_v2.schema.json` | `CURRENT_PARTIAL` |
| `D1201` | Validation Engine | `src/ai4binance/application/validation_pipeline.py`<br>`src/ai4binance/agents/validation_gate.py`<br>`src/ai4binance/validation`<br>`schemas/validation/validation_result.schema.json` | `CURRENT_PARTIAL` |
| `D1302` | Deterministic Decision Engine | `src/ai4binance/governance/framework.py`<br>`src/ai4binance/governance/dge_models.py`<br>`src/ai4binance/governance/dge_engine.py`<br>`docs/registries/registry_logical_architecture.yaml` | `CURRENT_PARTIAL` |
| `D1303` | Decision Governance Engine | `src/ai4binance/governance/framework.py`<br>`src/ai4binance/governance/dge_models.py`<br>`src/ai4binance/governance/dge_engine.py`<br>`docs/registries/registry_logical_architecture.yaml` | `CURRENT_PARTIAL` |
| `D1403` | Paper Execution Architecture | `src/ai4binance/execution/paper.py`<br>`src/ai4binance/execution/lifecycle.py`<br>`src/ai4binance/execution/ledger.py` | `CURRENT_PARTIAL` |
| `D1501` | Virtual Market Architecture | `src/ai4binance/application/virtual_runtime.py`<br>`src/ai4binance/research/virtual_market.py`<br>`src/ai4binance/virtual_wallet_journal.py`<br>`config/research/virtual_market_acceptance.yaml` | `CURRENT_PARTIAL` |
| `D1602` | Opportunity Lifecycle | `src/ai4binance/opportunity_ledger.py`<br>`src/ai4binance/opportunity_outcomes.py`<br>`src/ai4binance/application/opportunity_monitor.py` | `CURRENT_PARTIAL` |
| `D1802` | Experiment Lifecycle | `src/ai4binance/research_governance.py`<br>`src/ai4binance/research/backtesting`<br>`src/ai4binance/validation/walk_forward.py`<br>`src/ai4binance/validation/oos_maturity.py` | `CURRENT_PARTIAL` |
| `D1901` | Research Promotion State Machine | `src/ai4binance/tuning/promotion.py`<br>`src/ai4binance/validation/promotion_evidence.py`<br>`src/ai4binance/domain/research/lifecycle.py` | `CURRENT_PARTIAL` |
| `D2001` | Continuous Improvement Loop | `src/ai4binance/ops/kaizen_quality.py`<br>`docs/workflows/instruction_enterprise_auto_audit_continuous_improvement_engine.md` | `CURRENT_PARTIAL` |
| `D2101` | Technology Intelligence Architecture | `docs/architecture/framework_external_intelligence_evidence_fabric.md`<br>`docs/workflows/instruction_technology_intelligence_analyzer.md`<br>`src/ai4binance/external_intel/technology/analyzer.py` | `CURRENT_PARTIAL` |
| `D2201` | Enterprise Ontology | `src/ai4binance/ontology/contracts.py`<br>`src/ai4binance/ontology/semantic_graph.py`<br>`config/governance/canonical_terminology_registry.yaml` | `CURRENT_PARTIAL` |
| `D2301` | Master Registry Architecture | `docs/registries/registry_logical_architecture.yaml`<br>`docs/registries/registry_agent_registry.md`<br>`docs/registries/registry_strategy_registry.md`<br>`docs/registries/registry_evidence_registry.md` | `CURRENT_PARTIAL` |
| `D2401` | Assurance Plane | `docs/governance/framework_trust_assurance_governance_plane.md`<br>`src/ai4binance/trust/plane.py`<br>`src/ai4binance/ops/continuous_assurance.py` | `CURRENT_PARTIAL` |
| `D2501` | Security Architecture | `docs/governance/policy_organization_risk_security_privacy.md`<br>`src/ai4binance/infrastructure/security/scanner.py`<br>`src/ai4binance/ops/security_assurance.py` | `CURRENT_PARTIAL` |
| `D2601` | Observability Architecture | `src/ai4binance/observability/local.py`<br>`src/ai4binance/ops/decision_telemetry.py`<br>`src/ai4binance/agents/telemetry.py` | `CURRENT_PARTIAL` |
| `D2802` | Process Topology | `src/ai4binance/ops/runtime.py`<br>`src/ai4binance/skills/continuous_runtime.py`<br>`src/ai4binance/cli/runtime.py`<br>`config/governance/runtime_artifact_layout_manifest.json` | `CURRENT_PARTIAL` |
| `D2901` | Test Architecture | `config/quality/gates.yaml`<br>`scripts/quality.ps1`<br>`docs/workflows/runbook_quality_gate_profiles.md`<br>`src/ai4binance/ops/quality_gate` | `CURRENT_PARTIAL` |

The remaining `449` IDs are `NOT_VERIFIED` until evidence owners, contracts, schemas, policies, code, and tests are inspected.

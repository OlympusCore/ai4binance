---
document_id: AI4B-ARCH-DIAG-003
title: Canonical End-to-End Architecture Diagram
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
canonical_path: docs/architecture/diagrams/00_main/d003_canonical_end_to_end_architecture_diagram.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# Canonical End-to-End Architecture Diagram

## ELI10

This evidence-backed diagram explains one bounded current part of AI4Binance. It is not new trading, risk, promotion, or execution authority.

Diagram ID: `D003`

| Field | Value |
| --- | --- |
| Diagram level | `L0` |
| Architecture family | `D000 — MAIN / MASTER` |
| Status | `CURRENT_PARTIAL` |
| Authority | `INFORMATIONAL_PROJECTION` |
| Designation | Canonical editable Mermaid source; supporting projection |
| Last verified | `2026-09-17` |

## 1. Purpose

Document the repository-grounded `Canonical End-to-End Architecture Diagram` boundary and its relationship to the deterministic, fail-closed architecture.

## 2. Scope

This is a logical view. It does not imply a separate process, service, agent, database, Python layer, or live capability unless the listed evidence explicitly proves one.

## 3. Architectural Status

`CURRENT_PARTIAL`. The shown spine is repository-backed; adjacent coverage and operational maturity remain explicit gaps.

## 4. Authority and Source of Truth

This document is `source_of_truth: false`. `docs/governance/framework_core_vnext_governance.md`, affected contracts and schemas, and metadata-declared canonical owners govern on conflict.

## 5. Repository Evidence

- `docs/governance/framework_core_vnext_governance.md`
- `docs/architecture/framework_architecture_overview.md`
- `docs/registries/registry_logical_architecture.yaml`

## 6. Diagram

```mermaid
flowchart TB
 G[Governance] --> E[Event Fabric] --> D[Canonical Data] --> S[Immutable Snapshot] --> I[Intelligence and Evidence] --> C[Deterministic Core] --> X[DecisionCandidate]
 X --> R[RiskAssessment] --> DG[Decision Governance]
 X --> V[Validation] --> DG
 DG --> T[TradeDecision] --> Q{Execution eligibility}
 Q -->|blocked| N[NO_TRADE / LIVE_ORDER_BLOCKED]
 Q -->|paper only| P[Paper Execution] --> L[Closure and Learning]
```

## 7. Components

The nodes are bounded architectural roles derived from the evidence above. Labels do not create runtime agents or authority classes.

## 8. Responsibilities

- Preserve one canonical owner per concept.
- Separate deterministic controls from advisory analysis.
- Keep missing evidence and blockers visible.

## 9. Inputs

Typed, provenance-aware repository inputs appropriate to this family, including identity, timestamps, scope, and required control context.

## 10. Outputs

Bounded typed results, explicit reason codes, lineage, and a visible blocked or unavailable state where evidence is insufficient.

## 11. Dependency Rules

Higher-authority governance, contracts, schemas, and registries constrain implementation. Logical plane, bounded context, package layer, process, service, workflow, and agent remain distinct.

## 12. Architectural Invariants

- `DETERMINISTIC_FIRST`; `LLM_ADVISORY_ONLY`.
- `RISK_VETO IS HARD`; `VALIDATION_VETO IS HARD`.
- Unknown, stale, inconsistent, unvalidated, unauthorized, or unsafe state fails closed.
- `LIVE_EXECUTION_DISABLED` and `LIVE_ORDER_BLOCKED` remain unchanged.

## 13. State / Flow Semantics

Solid arrows show allowed current information or control flow. Dashed arrows show constraints or prohibited authority shortcuts. Arrows never grant authority by themselves.

## 14. Governance Controls

Technical quality, policy eligibility, and consequential human authority are separate gates. Scores cannot hide blockers.

## 15. Risk Controls

Hard risk and validation vetoes take precedence over confidence or opportunity scores. Credentials and tool availability do not imply permission.

## 16. Security Considerations

Inputs remain untrusted until validated. Least privilege, secret isolation, path safety, provenance, and allowlists apply where relevant.

## 17. Observability

Required observations include input identity, lineage, gate outcomes, reason codes, timestamps, and explicit degraded or blocked state.

## 18. Failure Modes

Missing, corrupt, stale, inconsistent, unauthorized, or unvalidated inputs produce a visible deny, blocked, unavailable, `WAIT`, or `NO_TRADE` outcome rather than permissive fallback.

## 19. Validation / Test Evidence

- `NOT_VERIFIED`

The paths are relevant test surfaces, not a claim that they passed in this change. Executed evidence is recorded in `diagram_validation_report.md`.

## 20. Known Gaps

Full cross-family, operational, and migration proof is incomplete. The `CURRENT_PARTIAL` label must remain until stronger machine-readable and executed evidence exists.

## 21. Current vs Target Differences

Only the solid repository-backed current spine is shown. No unimplemented target is presented as current.

## 22. Related Diagrams

- [D101 — Authority Pyramid](../01_governance/d101_authority_pyramid.md)
- [D104 — Governance Control Plane](../01_governance/d104_governance_control_plane.md)
- [D202 — Modular Monorepo Architecture](../02_repository/d202_modular_monorepo_architecture.md)
- [D204 — Dependency Direction Diagram](../02_repository/d204_dependency_direction_diagram.md)
- [D310 — Canonical Market Data Architecture](../03_data/d310_canonical_market_data_architecture.md)
- [D406 — Immutable Shared Snapshot Flow](../04_features_snapshot/d406_immutable_shared_snapshot_flow.md)
- [D501 — Canonical Event Fabric](../05_event_fabric/d501_canonical_event_fabric.md)
- [D601 — Intelligence Capability Map](../06_intelligence/d601_intelligence_capability_map.md)
- [D701 — Multi-TF Architecture](../07_multi_timeframe/d701_multi_tf_architecture.md)
- [D901 — Evidence Architecture](../09_evidence/d901_evidence_architecture.md)
- [D1102 — Risk Engine](../11_risk/d1102_risk_engine.md)
- [D1201 — Validation Engine](../12_validation/d1201_validation_engine.md)
- [D1302 — Deterministic Decision Engine](../13_decision/d1302_deterministic_decision_engine.md)
- [D1303 — Decision Governance Engine](../13_decision/d1303_decision_governance_engine.md)
- [D1403 — Paper Execution Architecture](../14_execution/d1403_paper_execution_architecture.md)
- [D1501 — Virtual Market Architecture](../15_virtual_market/d1501_virtual_market_architecture.md)
- [D1602 — Opportunity Lifecycle](../16_opportunity_observability/d1602_opportunity_lifecycle.md)
- [D1802 — Experiment Lifecycle](../18_research/d1802_experiment_lifecycle.md)
- [D1901 — Research Promotion State Machine](../19_promotion/d1901_research_promotion_state_machine.md)
- [D2001 — Continuous Improvement Loop](../20_continuous_improvement/d2001_continuous_improvement_loop.md)
- [D2101 — Technology Intelligence Architecture](../21_technology_intelligence/d2101_technology_intelligence_architecture.md)
- [D2201 — Enterprise Ontology](../22_ontology_contracts/d2201_enterprise_ontology.md)
- [D2301 — Master Registry Architecture](../23_registries/d2301_master_registry_architecture.md)
- [D2401 — Assurance Plane](../24_assurance/d2401_assurance_plane.md)
- [D2501 — Security Architecture](../25_security/d2501_security_architecture.md)
- [D2601 — Observability Architecture](../26_observability/d2601_observability_architecture.md)
- [D2802 — Process Topology](../28_runtime/d2802_process_topology.md)
- [D2901 — Test Architecture](../29_testing/d2901_test_architecture.md)

## 23. Change Impact

Semantic changes require registry, evidence, relation, contract, schema, test, security, risk, and current-vs-target review. This document does not implement runtime behavior.

## 24. Open Questions

- Which relations require stronger machine-readable proof for `CURRENT_VERIFIED`?
- Which operational evidence must be refreshed at the next review?

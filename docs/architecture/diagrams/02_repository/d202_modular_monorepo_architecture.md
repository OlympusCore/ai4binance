---
document_id: AI4B-ARCH-DIAG-202
title: Modular Monorepo Architecture
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
canonical_path: docs/architecture/diagrams/02_repository/d202_modular_monorepo_architecture.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# Modular Monorepo Architecture

## ELI10

This evidence-backed diagram explains one bounded current part of AI4Binance. It is not new trading, risk, promotion, or execution authority.

Diagram ID: `D202`

| Field | Value |
| --- | --- |
| Diagram level | `L1` |
| Architecture family | `D200 — REPOSITORY & SOFTWARE ARCHITECTURE` |
| Status | `CURRENT_PARTIAL` |
| Authority | `INFORMATIONAL_PROJECTION` |
| Designation | Canonical editable Mermaid source; supporting projection |
| Last verified | `2026-09-17` |

## 1. Purpose

Document the repository-grounded `Modular Monorepo Architecture` boundary and its relationship to the deterministic, fail-closed architecture.

## 2. Scope

This is a logical view. It does not imply a separate process, service, agent, database, Python layer, or live capability unless the listed evidence explicitly proves one.

## 3. Architectural Status

`CURRENT_PARTIAL`. The shown spine is repository-backed; adjacent coverage and operational maturity remain explicit gaps.

## 4. Authority and Source of Truth

This document is `source_of_truth: false`. `docs/governance/framework_core_vnext_governance.md`, affected contracts and schemas, and metadata-declared canonical owners govern on conflict.

## 5. Repository Evidence

- `docs/architecture/framework_architecture_overview.md`
- `docs/registries/registry_logical_architecture.yaml`
- `src/ai4binance/governance/architecture/graph.py`

## 6. Diagram

```mermaid
flowchart TB
 A[ai4binance] --> B[Core and Domain]
 A --> C[Application]
 A --> D[Infrastructure and Integrations]
 A --> E[Governance and Assurance]
 A --> F[Ops and Observability]
 A --> G[CLI]
 C --> B
 D --> B
 G --> C
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

- `tests/governance/architecture/test_logical_architecture_registry.py`
- `tests/test_architecture_projection.py`

The paths are relevant test surfaces, not a claim that they passed in this change. Executed evidence is recorded in `diagram_validation_report.md`.

## 20. Known Gaps

Full cross-family, operational, and migration proof is incomplete. The `CURRENT_PARTIAL` label must remain until stronger machine-readable and executed evidence exists.

## 21. Current vs Target Differences

Only the solid repository-backed current spine is shown. No unimplemented target is presented as current.

## 22. Related Diagrams

- [D003 — Canonical End-to-End Architecture Diagram](../00_main/d003_canonical_end_to_end_architecture_diagram.md)
- [D204 — Dependency Direction Diagram](d204_dependency_direction_diagram.md)

## 23. Change Impact

Semantic changes require registry, evidence, relation, contract, schema, test, security, risk, and current-vs-target review. This document does not implement runtime behavior.

## 24. Open Questions

- Which relations require stronger machine-readable proof for `CURRENT_VERIFIED`?
- Which operational evidence must be refreshed at the next review?

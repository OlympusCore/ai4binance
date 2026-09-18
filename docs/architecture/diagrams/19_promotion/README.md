---
document_id: AI4B-ARCH-DIAG-INDEX-D1900-001
title: PROMOTION LIFECYCLE Diagram Family
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
canonical_path: docs/architecture/diagrams/19_promotion/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# PROMOTION LIFECYCLE Diagram Family

## ELI10

This index lists every required diagram in the family and distinguishes evidence-backed sources from deferred work.

## Status

- Registered: `14`
- Documented P0: `1`
- Deferred: `13`

Deferred `NOT_VERIFIED` entries intentionally have no placeholder Mermaid source.

## Diagram Catalog

| ID | Title | Level | Status |
| --- | --- | --- | --- |
| [D1901](d1901_research_promotion_state_machine.md) | Research Promotion State Machine | `L4` | `CURRENT_PARTIAL` |
| `D1902` | Strategy Promotion Flow | `L3` | `NOT_VERIFIED` |
| `D1903` | Model Promotion Flow | `L3` | `NOT_VERIFIED` |
| `D1904` | Parameter Promotion Flow | `L3` | `NOT_VERIFIED` |
| `D1905` | Policy Promotion Flow | `L3` | `NOT_VERIFIED` |
| `D1906` | RESEARCH → BACKTEST | `L1` | `NOT_VERIFIED` |
| `D1907` | BACKTEST → WALK_FORWARD | `L1` | `NOT_VERIFIED` |
| `D1908` | WALK_FORWARD → OOS | `L1` | `NOT_VERIFIED` |
| `D1909` | OOS → ROBUSTNESS | `L1` | `NOT_VERIFIED` |
| `D1910` | ROBUSTNESS → PAPER | `L1` | `NOT_VERIFIED` |
| `D1911` | PAPER → LIVE_CANDIDATE | `L1` | `NOT_VERIFIED` |
| `D1912` | LIVE_CANDIDATE → LIVE_APPROVED | `L1` | `NOT_VERIFIED` |
| `D1913` | Suspension / Quarantine | `L1` | `NOT_VERIFIED` |
| `D1914` | Rollback / Deprecation | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

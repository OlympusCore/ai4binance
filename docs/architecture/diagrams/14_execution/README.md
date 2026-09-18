---
document_id: AI4B-ARCH-DIAG-INDEX-D1400-001
title: EXECUTION ARCHITECTURE Diagram Family
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
canonical_path: docs/architecture/diagrams/14_execution/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# EXECUTION ARCHITECTURE Diagram Family

## ELI10

This index lists every required diagram in the family and distinguishes evidence-backed sources from deferred work.

## Status

- Registered: `16`
- Documented P0: `1`
- Deferred: `15`

Deferred `NOT_VERIFIED` entries intentionally have no placeholder Mermaid source.

## Diagram Catalog

| ID | Title | Level | Status |
| --- | --- | --- | --- |
| `D1401` | Execution Plane | `L1` | `NOT_VERIFIED` |
| `D1402` | Execution Eligibility Gate | `L1` | `NOT_VERIFIED` |
| [D1403](d1403_paper_execution_architecture.md) | Paper Execution Architecture | `L1` | `CURRENT_PARTIAL` |
| `D1404` | Spot Execution Flow | `L3` | `NOT_VERIFIED` |
| `D1405` | Futures Execution Flow | `L3` | `NOT_VERIFIED` |
| `D1406` | Order Lifecycle State Machine | `L4` | `NOT_VERIFIED` |
| `D1407` | Order Validation Flow | `L3` | `NOT_VERIFIED` |
| `D1408` | Fill Simulation | `L1` | `NOT_VERIFIED` |
| `D1409` | Slippage Simulation | `L1` | `NOT_VERIFIED` |
| `D1410` | Fee / Funding Simulation | `L1` | `NOT_VERIFIED` |
| `D1411` | Execution Reconciliation | `L1` | `NOT_VERIFIED` |
| `D1412` | Duplicate Order Protection | `L1` | `NOT_VERIFIED` |
| `D1413` | Execution Failure Flow | `L3` | `NOT_VERIFIED` |
| `D1414` | Testnet Execution Boundary | `L1` | `NOT_VERIFIED` |
| `D1415` | Live Execution Boundary | `L1` | `NOT_VERIFIED` |
| `D1416` | Manual Confirmation Gate | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

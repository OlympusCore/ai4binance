---
document_id: AI4B-ARCH-DIAG-INDEX-D2600-001
title: OBSERVABILITY Diagram Family
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
canonical_path: docs/architecture/diagrams/26_observability/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# OBSERVABILITY Diagram Family

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
| [D2601](d2601_observability_architecture.md) | Observability Architecture | `L1` | `CURRENT_PARTIAL` |
| `D2602` | Logs Architecture | `L1` | `NOT_VERIFIED` |
| `D2603` | Metrics Architecture | `L1` | `NOT_VERIFIED` |
| `D2604` | Tracing Architecture | `L1` | `NOT_VERIFIED` |
| `D2605` | Correlation-ID Flow | `L3` | `NOT_VERIFIED` |
| `D2606` | Cycle-ID Flow | `L3` | `NOT_VERIFIED` |
| `D2607` | Snapshot-ID Flow | `L3` | `NOT_VERIFIED` |
| `D2608` | Decision-ID Flow | `L3` | `NOT_VERIFIED` |
| `D2609` | Execution-ID Flow | `L3` | `NOT_VERIFIED` |
| `D2610` | End-to-End Trace | `L1` | `NOT_VERIFIED` |
| `D2611` | Health Monitoring | `L1` | `NOT_VERIFIED` |
| `D2612` | Alert Architecture | `L1` | `NOT_VERIFIED` |
| `D2613` | Trading Observability Dashboard | `L1` | `NOT_VERIFIED` |
| `D2614` | Governance Observability Dashboard | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

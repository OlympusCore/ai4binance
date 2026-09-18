---
document_id: AI4B-ARCH-DIAG-INDEX-D500-001
title: EVENT-DRIVEN ARCHITECTURE Diagram Family
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
canonical_path: docs/architecture/diagrams/05_event_fabric/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# EVENT-DRIVEN ARCHITECTURE Diagram Family

## ELI10

This index lists every required diagram in the family and distinguishes evidence-backed sources from deferred work.

## Status

- Registered: `12`
- Documented P0: `1`
- Deferred: `11`

Deferred `NOT_VERIFIED` entries intentionally have no placeholder Mermaid source.

## Diagram Catalog

| ID | Title | Level | Status |
| --- | --- | --- | --- |
| [D501](d501_canonical_event_fabric.md) | Canonical Event Fabric | `L1` | `CURRENT_PARTIAL` |
| `D502` | Event Taxonomy | `L1` | `NOT_VERIFIED` |
| `D503` | Event Producer / Consumer Map | `L1` | `NOT_VERIFIED` |
| `D504` | Event Lifecycle | `L4` | `NOT_VERIFIED` |
| `D505` | Correlation / Causation Flow | `L3` | `NOT_VERIFIED` |
| `D506` | Idempotency Architecture | `L1` | `NOT_VERIFIED` |
| `D507` | Event Replay Flow | `L3` | `NOT_VERIFIED` |
| `D508` | Duplicate Event Protection | `L1` | `NOT_VERIFIED` |
| `D509` | Dead-Letter / Failure Flow | `L3` | `NOT_VERIFIED` |
| `D510` | Decision Cycle State Machine | `L4` | `NOT_VERIFIED` |
| `D511` | Event-to-State Transition Map | `L1` | `NOT_VERIFIED` |
| `D512` | Event Failure Propagation Diagram | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

---
document_id: AI4B-ARCH-DIAG-INDEX-D000-001
title: MAIN / MASTER Diagram Family
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
canonical_path: docs/architecture/diagrams/00_main/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# MAIN / MASTER Diagram Family

## ELI10

This index lists every required diagram in the family and distinguishes evidence-backed sources from deferred work.

## Status

- Registered: `10`
- Documented P0: `1`
- Deferred: `9`

Deferred `NOT_VERIFIED` entries intentionally have no placeholder Mermaid source.

## Diagram Catalog

| ID | Title | Level | Status |
| --- | --- | --- | --- |
| `D001` | Enterprise System Context Diagram | `L1` | `NOT_VERIFIED` |
| `D002` | Enterprise Logical Architecture Diagram | `L1` | `NOT_VERIFIED` |
| [D003](d003_canonical_end_to_end_architecture_diagram.md) | Canonical End-to-End Architecture Diagram | `L0` | `CURRENT_PARTIAL` |
| `D004` | Enterprise Plane Architecture Diagram | `L1` | `NOT_VERIFIED` |
| `D005` | End-to-End Decision Pipeline Diagram | `L3` | `NOT_VERIFIED` |
| `D006` | End-to-End Trading Lifecycle Diagram | `L4` | `NOT_VERIFIED` |
| `D007` | Authority + Architecture Overlay Diagram | `L1` | `NOT_VERIFIED` |
| `D008` | Hot Path vs Cold Path Diagram | `L1` | `NOT_VERIFIED` |
| `D009` | Runtime + Governance Integrated Diagram | `L1` | `NOT_VERIFIED` |
| `D010` | Canonical System Capability Map | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

---
document_id: AI4B-ARCH-DIAG-INDEX-D200-001
title: REPOSITORY & SOFTWARE ARCHITECTURE Diagram Family
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
canonical_path: docs/architecture/diagrams/02_repository/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# REPOSITORY & SOFTWARE ARCHITECTURE Diagram Family

## ELI10

This index lists every required diagram in the family and distinguishes evidence-backed sources from deferred work.

## Status

- Registered: `16`
- Documented P0: `2`
- Deferred: `14`

Deferred `NOT_VERIFIED` entries intentionally have no placeholder Mermaid source.

## Diagram Catalog

| ID | Title | Level | Status |
| --- | --- | --- | --- |
| `D201` | Canonical Repository Tree | `L1` | `NOT_VERIFIED` |
| [D202](d202_modular_monorepo_architecture.md) | Modular Monorepo Architecture | `L1` | `CURRENT_PARTIAL` |
| `D203` | Python Layer Architecture | `L1` | `NOT_VERIFIED` |
| [D204](d204_dependency_direction_diagram.md) | Dependency Direction Diagram | `L2` | `CURRENT_PARTIAL` |
| `D205` | Import Boundary Diagram | `L1` | `NOT_VERIFIED` |
| `D206` | Bounded Context Map | `L1` | `NOT_VERIFIED` |
| `D207` | Domain Component Diagram | `L2` | `NOT_VERIFIED` |
| `D208` | Application Layer Diagram | `L1` | `NOT_VERIFIED` |
| `D209` | Infrastructure Layer Diagram | `L1` | `NOT_VERIFIED` |
| `D210` | Integration Adapter Diagram | `L1` | `NOT_VERIFIED` |
| `D211` | Ports and Adapters Diagram | `L1` | `NOT_VERIFIED` |
| `D212` | Package Dependency Graph | `L2` | `NOT_VERIFIED` |
| `D213` | Module Ownership Diagram | `L1` | `NOT_VERIFIED` |
| `D214` | Runtime Process Topology | `L2` | `NOT_VERIFIED` |
| `D215` | Repository Authority-to-Code Mapping | `L1` | `NOT_VERIFIED` |
| `D216` | Source-of-Truth Mapping | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

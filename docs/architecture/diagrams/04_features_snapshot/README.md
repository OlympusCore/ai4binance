---
document_id: AI4B-ARCH-DIAG-INDEX-D400-001
title: FEATURE & SNAPSHOT ARCHITECTURE Diagram Family
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
canonical_path: docs/architecture/diagrams/04_features_snapshot/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# FEATURE & SNAPSHOT ARCHITECTURE Diagram Family

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
| `D401` | Canonical Feature Architecture | `L1` | `NOT_VERIFIED` |
| `D402` | Feature Calculation Ownership | `L1` | `NOT_VERIFIED` |
| `D403` | Feature Dependency Graph | `L2` | `NOT_VERIFIED` |
| `D404` | Feature Store Architecture | `L1` | `NOT_VERIFIED` |
| `D405` | MarketSnapshot Architecture | `L1` | `NOT_VERIFIED` |
| [D406](d406_immutable_shared_snapshot_flow.md) | Immutable Shared Snapshot Flow | `L3` | `CURRENT_PARTIAL` |
| `D407` | Snapshot Creation Sequence | `L3` | `NOT_VERIFIED` |
| `D408` | Snapshot Validation Flow | `L3` | `NOT_VERIFIED` |
| `D409` | Snapshot Freshness State Machine | `L4` | `NOT_VERIFIED` |
| `D410` | Snapshot Replay Architecture | `L1` | `NOT_VERIFIED` |
| `D411` | Multi-Timeframe Snapshot | `L1` | `NOT_VERIFIED` |
| `D412` | Snapshot-to-Decision Lineage | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

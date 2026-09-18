---
document_id: AI4B-ARCH-DIAG-INDEX-D700-001
title: MULTI-TIMEFRAME TRADING INTELLIGENCE Diagram Family
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
canonical_path: docs/architecture/diagrams/07_multi_timeframe/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# MULTI-TIMEFRAME TRADING INTELLIGENCE Diagram Family

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
| [D701](d701_multi_tf_architecture.md) | Multi-TF Architecture | `L1` | `CURRENT_PARTIAL` |
| `D702` | 15m → 1h → 4h Confirmation Flow | `L3` | `NOT_VERIFIED` |
| `D703` | Higher-Timeframe Bias Flow | `L3` | `NOT_VERIFIED` |
| `D704` | Lower-Timeframe Trigger Flow | `L3` | `NOT_VERIFIED` |
| `D705` | Multi-TF Conflict Resolution | `L1` | `NOT_VERIFIED` |
| `D706` | Multi-TF Structure Alignment | `L1` | `NOT_VERIFIED` |
| `D707` | Multi-TF Momentum Alignment | `L1` | `NOT_VERIFIED` |
| `D708` | Multi-TF Volume Confirmation | `L1` | `NOT_VERIFIED` |
| `D709` | Multi-TF Opportunity Scoring | `L1` | `NOT_VERIFIED` |
| `D710` | Multi-TF Invalidation Flow | `L3` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

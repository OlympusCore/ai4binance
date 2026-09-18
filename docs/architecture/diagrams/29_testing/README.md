---
document_id: AI4B-ARCH-DIAG-INDEX-D2900-001
title: TESTING / QA / QUALITY GATES Diagram Family
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
canonical_path: docs/architecture/diagrams/29_testing/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# TESTING / QA / QUALITY GATES Diagram Family

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
| [D2901](d2901_test_architecture.md) | Test Architecture | `L1` | `CURRENT_PARTIAL` |
| `D2902` | Test Pyramid | `L1` | `NOT_VERIFIED` |
| `D2903` | Unit Test Flow | `L3` | `NOT_VERIFIED` |
| `D2904` | Contract Test Flow | `L3` | `NOT_VERIFIED` |
| `D2905` | Integration Test Flow | `L3` | `NOT_VERIFIED` |
| `D2906` | Governance Test Flow | `L3` | `NOT_VERIFIED` |
| `D2907` | Security Test Flow | `L3` | `NOT_VERIFIED` |
| `D2908` | Determinism Test | `L1` | `NOT_VERIFIED` |
| `D2909` | Replay Test | `L1` | `NOT_VERIFIED` |
| `D2910` | Regression Test | `L1` | `NOT_VERIFIED` |
| `D2911` | Performance Test | `L1` | `NOT_VERIFIED` |
| `D2912` | Resilience Test | `L1` | `NOT_VERIFIED` |
| `D2913` | Paper Validation Gate | `L1` | `NOT_VERIFIED` |
| `D2914` | FAST Gate | `L1` | `NOT_VERIFIED` |
| `D2915` | PR Gate | `L1` | `NOT_VERIFIED` |
| `D2916` | RELEASE Gate | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

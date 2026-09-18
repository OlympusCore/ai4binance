---
document_id: AI4B-ARCH-DIAG-INDEX-D1300-001
title: DECISION ARCHITECTURE Diagram Family
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
canonical_path: docs/architecture/diagrams/13_decision/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# DECISION ARCHITECTURE Diagram Family

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
| `D1301` | Decision Candidate Flow | `L3` | `NOT_VERIFIED` |
| [D1302](d1302_deterministic_decision_engine.md) | Deterministic Decision Engine | `L2` | `CURRENT_PARTIAL` |
| [D1303](d1303_decision_governance_engine.md) | Decision Governance Engine | `L2` | `CURRENT_PARTIAL` |
| `D1304` | Decision State Machine | `L4` | `NOT_VERIFIED` |
| `D1305` | Decision Eligibility Flow | `L3` | `NOT_VERIFIED` |
| `D1306` | Hard Blocker Architecture | `L1` | `NOT_VERIFIED` |
| `D1307` | Score vs Gate Diagram | `L1` | `NOT_VERIFIED` |
| `D1308` | Risk + Validation + Governance Fusion | `L1` | `NOT_VERIFIED` |
| `D1309` | WAIT Decision Flow | `L3` | `NOT_VERIFIED` |
| `D1310` | WATCH_ONLY Decision Flow | `L3` | `NOT_VERIFIED` |
| `D1311` | NO_TRADE Decision Flow | `L3` | `NOT_VERIFIED` |
| `D1312` | PAPER_ELIGIBLE Decision Flow | `L3` | `NOT_VERIFIED` |
| `D1313` | Decision Reproducibility | `L1` | `NOT_VERIFIED` |
| `D1314` | Decision Explainability | `L1` | `NOT_VERIFIED` |
| `D1315` | Decision Reason-Code Architecture | `L1` | `NOT_VERIFIED` |
| `D1316` | Decision Lineage | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

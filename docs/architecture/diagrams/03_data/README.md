---
document_id: AI4B-ARCH-DIAG-INDEX-D300-001
title: DATA PLANE Diagram Family
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
canonical_path: docs/architecture/diagrams/03_data/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# DATA PLANE Diagram Family

## ELI10

This index lists every required diagram in the family and distinguishes evidence-backed sources from deferred work.

## Status

- Registered: `20`
- Documented P0: `1`
- Deferred: `19`

Deferred `NOT_VERIFIED` entries intentionally have no placeholder Mermaid source.

## Diagram Catalog

| ID | Title | Level | Status |
| --- | --- | --- | --- |
| `D301` | Data Source Architecture | `L1` | `NOT_VERIFIED` |
| `D302` | Binance Market Data Architecture | `L1` | `NOT_VERIFIED` |
| `D303` | External Data Source Map | `L1` | `NOT_VERIFIED` |
| `D304` | Market Data Ingestion Pipeline | `L3` | `NOT_VERIFIED` |
| `D305` | Raw Data Flow | `L3` | `NOT_VERIFIED` |
| `D306` | Data Normalization Flow | `L3` | `NOT_VERIFIED` |
| `D307` | Data Quality Pipeline | `L3` | `NOT_VERIFIED` |
| `D308` | Cross-Source Reconciliation | `L1` | `NOT_VERIFIED` |
| `D309` | Freshness / Staleness Flow | `L3` | `NOT_VERIFIED` |
| [D310](d310_canonical_market_data_architecture.md) | Canonical Market Data Architecture | `L1` | `CURRENT_PARTIAL` |
| `D311` | Data Lineage Diagram | `L1` | `NOT_VERIFIED` |
| `D312` | Data Provenance Diagram | `L1` | `NOT_VERIFIED` |
| `D313` | Spot Data Architecture | `L1` | `NOT_VERIFIED` |
| `D314` | Futures Data Architecture | `L1` | `NOT_VERIFIED` |
| `D315` | Order Book Pipeline | `L3` | `NOT_VERIFIED` |
| `D316` | Trade / Tick Pipeline | `L3` | `NOT_VERIFIED` |
| `D317` | Historical Data Architecture | `L1` | `NOT_VERIFIED` |
| `D318` | Data Retention Lifecycle | `L4` | `NOT_VERIFIED` |
| `D319` | Data Quality Failure Flow | `L3` | `NOT_VERIFIED` |
| `D320` | Data Provider Failover Diagram | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

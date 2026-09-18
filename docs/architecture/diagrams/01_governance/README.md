---
document_id: AI4B-ARCH-DIAG-INDEX-D100-001
title: GOVERNANCE & AUTHORITY Diagram Family
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
canonical_path: docs/architecture/diagrams/01_governance/README.md
machine_enforceable: false
audit_required: true
classification: INTERNAL
language: en-US
---

# GOVERNANCE & AUTHORITY Diagram Family

## ELI10

This index lists every required diagram in the family and distinguishes evidence-backed sources from deferred work.

## Status

- Registered: `20`
- Documented P0: `2`
- Deferred: `18`

Deferred `NOT_VERIFIED` entries intentionally have no placeholder Mermaid source.

## Diagram Catalog

| ID | Title | Level | Status |
| --- | --- | --- | --- |
| [D101](d101_authority_pyramid.md) | Authority Pyramid | `L1` | `CURRENT_PARTIAL` |
| `D102` | Authority Graph | `L1` | `NOT_VERIFIED` |
| `D103` | Authority Dependency Map | `L2` | `NOT_VERIFIED` |
| [D104](d104_governance_control_plane.md) | Governance Control Plane | `L1` | `CURRENT_PARTIAL` |
| `D105` | Governance Enforcement Flow | `L3` | `NOT_VERIFIED` |
| `D106` | Decision Authority Matrix | `L4` | `NOT_VERIFIED` |
| `D107` | Human Authority Matrix | `L4` | `NOT_VERIFIED` |
| `D108` | LLM Authority Boundary | `L1` | `NOT_VERIFIED` |
| `D109` | Policy Hierarchy | `L1` | `NOT_VERIFIED` |
| `D110` | Policy-as-Code Architecture | `L1` | `NOT_VERIFIED` |
| `D111` | Governance Conflict Resolution Flow | `L3` | `NOT_VERIFIED` |
| `D112` | Governance Veto Flow | `L3` | `NOT_VERIFIED` |
| `D113` | Governed Object Lifecycle | `L4` | `NOT_VERIFIED` |
| `D114` | Governance Registry Architecture | `L1` | `NOT_VERIFIED` |
| `D115` | Promotion Authority Flow | `L3` | `NOT_VERIFIED` |
| `D116` | Change Approval Flow | `L3` | `NOT_VERIFIED` |
| `D117` | Live Execution Authority Gate | `L1` | `NOT_VERIFIED` |
| `D118` | Human-in-the-Loop Architecture | `L1` | `NOT_VERIFIED` |
| `D119` | Governance Evidence Chain | `L1` | `NOT_VERIFIED` |
| `D120` | Governance Assurance Loop | `L1` | `NOT_VERIFIED` |

## Authority and Safety

This index is `source_of_truth: false`. `PAPER_TRADING`, `MANUAL_CONFIRMATION`, `LIVE_EXECUTION_DISABLED`, and `LIVE_ORDER_BLOCKED` remain unchanged.

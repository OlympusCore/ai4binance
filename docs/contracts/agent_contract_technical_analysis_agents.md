---
document_id: AI4B-AGENT-CONTRACT-001
title: AI4BINANCE Technical Analysis Agents
document_type: AGENT_CONTRACT
version: 1.0.0
status: ACTIVE
owner: Enterprise Knowledge Governance
authority_level: NORMATIVE
authority_layer: L3_CANONICAL_CONTRACTS_SCHEMAS
authority_scope: technical_analysis_agents
content_role: AUTHORITATIVE
source_of_truth: true
source_of_truth_scope: canonical
machine_enforceable: true
audit_required: true
classification: INTERNAL
canonical_path: docs/contracts/agent_contract_technical_analysis_agents.md
---

# Technical Analysis Agents

## ELI10

This file explains the technical-analysis agent families. Agents produce evidence and blockers; they do not issue orders or grant execution authority.


> **ELI5:** Agents generate evidence; they do not issue commands. Current agent count and real
The implementation status is stored in `docs/compliance/registry_compliance_matrix.md`.

Each technical family must be a separate, deterministic and testable module.
Each agent produces `role`, `allowed_timeframes`, `score_contribution`, `blockers`,
`false_positive_risk`, `required_oos_validation`, and `promotion_status` are generated.

Trend, structure and price action primary; volatility risk filter; momentum and
volume secondary; Fibonacci, formation, and macro cycle advisory.
A single subjective pattern or observation alone cannot constitute a hard gate. OOS and multi-mode proof
All non-compliant candidates remain as `RESEARCH_ONLY` or `STAGED_CANDIDATE`.
